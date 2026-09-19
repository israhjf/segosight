"""Header counters for the Overview screen."""

from __future__ import annotations

from fastapi import APIRouter

from ...curated.alerts import TABLE as ALERTS
from ...curated.extraction import PENDING, TABLE as INSIGHTS
from ...curated.promotion import COMMITMENT_TABLE, ensure_schema
from ..dependencies import get_connection
from ..schemas import Overview

router = APIRouter(prefix="/api", tags=["overview"])


@router.get("/health")
def health() -> dict:
    conn = get_connection()
    tables = conn.execute(
        """SELECT count(*) FROM information_schema.tables
           WHERE table_schema IN ('raw','clean','canonical','curated')"""
    ).fetchone()[0]
    return {"status": "ok" if tables else "empty", "tables": tables}


@router.get("/overview", response_model=Overview)
def overview() -> Overview:
    conn = get_connection()
    ensure_schema(conn)
    row = conn.execute(
        f"""
        SELECT
            (SELECT max(as_of_date) FROM {ALERTS}),
            (SELECT count(*) FROM {INSIGHTS} WHERE status = '{PENDING}'),
            (SELECT count(*) FROM {ALERTS}),
            (SELECT count(*) FROM {ALERTS} WHERE severity = 'critical'),
            (SELECT count(*) FROM {ALERTS} WHERE evidence_basis = 'prose_pending_review'),
            (SELECT count(*) FROM {COMMITMENT_TABLE} WHERE status = 'open')
        """
    ).fetchone()
    return Overview(
        as_of_date=row[0], pending_review=row[1], active_alerts=row[2],
        critical_alerts=row[3], alerts_awaiting_prose_review=row[4],
        open_commitments=row[5],
    )
