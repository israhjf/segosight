"""Pipeline execution as a product action.

DuckDB allows one read-write process, and the API holds it. Rather than treat
that as a limitation, the rebuild is exposed here: incorporating a new data
batch becomes something Dana does in the product, with the before/after counts
visible, instead of a terminal command run by whoever has the repository.

The run is idempotent by construction -- the raw tier is content-addressed, so
re-running over unchanged files inserts nothing -- which is what makes it safe
to expose as a button.
"""

from __future__ import annotations

import datetime as dt
import io
import time
from contextlib import redirect_stdout

from fastapi import APIRouter, HTTPException

from segosight.features.chemistry.canonical import series as events
from segosight.features.identity.canonical import crosswalk as identity
from segosight.features.identity.canonical import entities
from segosight.features.service.canonical import visits
from segosight.features.chemistry.clean import readings
from segosight.features.ingestion.clean import versioning
from segosight.features.alerts.curated import aggregation as alerts
from segosight.features.chemistry.curated import assessments, trends
from segosight.features.compliance.curated import microbio
from segosight.features.review.curated import extraction
from segosight.features.service.curated import coverage
from segosight.features.alerts.curated.aggregation import TABLE as ALERTS
from segosight.features.review.curated.extraction import PENDING, TABLE as INSIGHTS
from segosight.features.chemistry.programs import load_config
from segosight.features.review.raw import documents
from segosight.features.ingestion.raw.landing import TABLE as RAW, land_all
from segosight.features.ingestion.registry import load_registry
from segosight.app.dependencies import get_connection, write_lock
from segosight.app.schemas import PipelineResult

router = APIRouter(prefix="/api/pipeline", tags=["pipeline"])


def _snapshot(conn) -> dict:
    return {
        "raw_records": conn.execute(f"SELECT count(*) FROM {RAW}").fetchone()[0],
        "alerts": conn.execute(f"SELECT count(*) FROM {ALERTS}").fetchone()[0],
        "pending_review": conn.execute(
            f"SELECT count(*) FROM {INSIGHTS} WHERE status = '{PENDING}'"
        ).fetchone()[0],
        "reading_events": conn.execute(
            "SELECT count(*) FROM canonical.reading_event"
        ).fetchone()[0],
    }


@router.post("/run", response_model=PipelineResult)
def run_pipeline() -> PipelineResult:
    """Rebuild every tier from the source material and report what changed.

    Reviewer decisions survive: they live in `curated.extracted_insight` and
    `curated.customer_commitment`, and the extraction step preserves any row
    that has already been decided rather than resetting it to pending.
    """
    conn = get_connection()
    started = time.perf_counter()
    buffer = io.StringIO()

    with write_lock():
        before = _snapshot(conn)
        decisions = conn.execute(
            f"""SELECT insight_id, status, review_decision, reviewed_by, reviewed_at
                FROM {INSIGHTS} WHERE status <> '{PENDING}'"""
        ).fetchall()

        try:
            with redirect_stdout(buffer):
                registry = load_registry()
                programs = load_config()
                land_all(conn, registry)
                versioning.build(conn)
                readings.build(conn, corpus=registry.corpus)
                identity.build(conn)
                entities.build(conn)
                events.build(conn)
                visits.build(conn, corpus=registry.corpus)
                assessments.build(conn, programs)
                trends.build(conn, programs)
                coverage.build(conn, programs)
                microbio.build(conn, programs)
                alerts.build(conn, programs)
                documents.build(conn)
                extraction.build(conn)
                alerts.attach_prose(conn, programs)

            # Re-apply decisions the rebuild would otherwise have reset. A
            # reviewer's judgement is not a derived value.
            for insight_id, status, decision, reviewer, reviewed_at in decisions:
                conn.execute(
                    f"""UPDATE {INSIGHTS}
                        SET status = ?, review_decision = ?, reviewed_by = ?,
                            reviewed_at = ?
                        WHERE insight_id = ?""",
                    [status, decision, reviewer, reviewed_at, insight_id],
                )
        except Exception as error:  # noqa: BLE001 - surfaced to the operator
            raise HTTPException(
                status_code=500, detail=f"pipeline failed: {error}"
            ) from error

        after = _snapshot(conn)

    return PipelineResult(
        ran_at=dt.datetime.now().replace(microsecond=0),
        duration_seconds=round(time.perf_counter() - started, 2),
        before=before,
        after=after,
        delta={key: after[key] - before[key] for key in after},
        log=[line for line in buffer.getvalue().splitlines() if line.strip()],
    )
