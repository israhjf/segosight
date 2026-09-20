"""Upload, profile, review and confirm a data drop.

The flow is deliberately three calls rather than one. Uploading stages files
and profiles them; confirming is a separate, explicit act. Nothing an upload
does touches a governed table until Dana has seen what would happen and said
yes -- which is the same rule the prose review queue enforces, applied to
structured data.

Confirmation rebuilds into a warehouse beside the live one and swaps it in, so
a failure leaves the serving database untouched. Reviewer decisions are carried
across that swap by hand: they live in the warehouse, a fresh build does not
have them, and a rebuild that silently discarded Dana's approvals would be
worse than one that failed.
"""

from __future__ import annotations

import datetime as dt
import io
import os
import time
from contextlib import redirect_stdout
from pathlib import Path

import duckdb
from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from segosight.app import dependencies
from segosight.app.dependencies import get_connection, write_lock
from segosight.app.schemas import (
    ConfirmRequest,
    ConfirmResult,
    DocumentPlan,
    EntityPlan,
    IngestFinding,
    IngestProfile,
    UnmatchedItem,
)
from segosight.features.alerts.curated.aggregation import TABLE as ALERTS
from segosight.features.ingestion import profile as profiling
from segosight.features.ingestion import promotion, staging
from segosight.features.ingestion.raw.landing import TABLE as RAW
from segosight.features.review.curated.extraction import PENDING, TABLE as INSIGHTS

router = APIRouter(prefix="/api/ingest", tags=["ingest"])


def _snapshot(conn) -> dict[str, int]:
    return {
        "raw_records": conn.execute(f"SELECT count(*) FROM {RAW}").fetchone()[0],
        "alerts": conn.execute(f"SELECT count(*) FROM {ALERTS}").fetchone()[0],
        "pending_review": conn.execute(
            f"SELECT count(*) FROM {INSIGHTS} WHERE status = '{PENDING}'"
        ).fetchone()[0],
        "documents": conn.execute("SELECT count(*) FROM raw.documents").fetchone()[0],
    }


def _to_schema(result: profiling.Profile) -> IngestProfile:
    return IngestProfile(
        upload_id=result.upload_id,
        batch_root=result.batch_root,
        entities=[EntityPlan(**vars(e)) for e in result.entities],
        documents=[DocumentPlan(**vars(d)) for d in result.documents],
        unmatched=[UnmatchedItem(**vars(u)) for u in result.unmatched],
        absent_entities=result.absent_entities,
        findings=[IngestFinding(**vars(f)) for f in result.findings],
        total_rows=result.total_rows,
        total_documents=result.total_documents,
        can_confirm=result.can_confirm,
    )


@router.post("/upload", response_model=IngestProfile)
async def upload(
    files: list[UploadFile] = File(...),
    paths: list[str] = Form(default=[]),
) -> IngestProfile:
    """Stage an upload and return what ingesting it would do.

    `paths` carries the browser's `webkitRelativePath` for each file, in the
    same order, so a folder drop keeps its structure. It is client-supplied and
    sanitised in the staging layer before it reaches the filesystem.
    """
    payload: list[tuple[str, bytes]] = []
    for index, item in enumerate(files):
        content = await item.read()
        relative = (
            paths[index]
            if index < len(paths) and paths[index]
            else (item.filename or f"file-{index}")
        )
        payload.append((relative, content))

    try:
        staged = staging.create(payload)
    except staging.UploadRejected as error:
        raise HTTPException(status_code=400, detail=str(error)) from error

    try:
        return _to_schema(profiling.build(get_connection(), staged))
    except Exception as error:  # noqa: BLE001 - a bad drop must not leave litter
        staging.discard(staged.upload_id)
        raise HTTPException(
            status_code=400, detail=f"could not profile the upload: {error}"
        ) from error


@router.get("/{upload_id}", response_model=IngestProfile)
def reprofile(upload_id: str) -> IngestProfile:
    """Re-profile a staged upload, so a refresh mid-review costs nothing."""
    try:
        staged = staging.load(upload_id)
    except staging.UploadRejected as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return _to_schema(profiling.build(get_connection(), staged))


@router.delete("/{upload_id}")
def discard(upload_id: str) -> dict[str, str]:
    staging.discard(upload_id)
    return {"upload_id": upload_id, "status": "discarded"}


def _carry_decisions(source: duckdb.DuckDBPyConnection, target_path: Path) -> int:
    """Copy reviewer decisions into the freshly built warehouse.

    A rebuild derives every curated table from source. Review decisions are not
    derived -- they are a person's judgement, recorded with their name against
    it -- so they are read from the live warehouse and written into the new one
    before the swap. Losing them would mean an ingestion quietly reopened
    compliance findings a human had already closed.
    """
    decided = source.execute(
        f"""SELECT insight_id, status, review_decision, reviewed_by, reviewed_at
            FROM {INSIGHTS} WHERE status <> '{PENDING}'"""
    ).fetchall()
    if not decided:
        return 0
    fresh = duckdb.connect(str(target_path))
    try:
        for insight_id, status, decision, reviewer, reviewed_at in decided:
            fresh.execute(
                f"""UPDATE {INSIGHTS}
                    SET status = ?, review_decision = ?, reviewed_by = ?,
                        reviewed_at = ?
                    WHERE insight_id = ?""",
                [status, decision, reviewer, reviewed_at, insight_id],
            )
    finally:
        fresh.close()
    return len(decided)


@router.post("/{upload_id}/confirm", response_model=ConfirmResult)
def confirm(upload_id: str, request: ConfirmRequest) -> ConfirmResult:
    """Promote the drop into the corpus and rebuild the warehouse."""
    from segosight.app import pipeline

    try:
        staged = staging.load(upload_id)
    except staging.UploadRejected as error:
        raise HTTPException(status_code=404, detail=str(error)) from error

    started = time.perf_counter()
    buffer = io.StringIO()

    with write_lock():
        conn = get_connection()
        result = profiling.build(conn, staged)
        if result.blocking:
            raise HTTPException(
                status_code=409,
                detail="; ".join(f.message for f in result.blocking),
            )

        before = _snapshot(conn)
        live = dependencies.database_path()
        candidate = live.with_name("segosight.next.duckdb")
        promoted = None

        try:
            promoted = promotion.promote(
                staged,
                result,
                uploader=request.uploader,
                batch_name=request.batch_name,
                source_system=request.source_system,
                mappings=[
                    promotion.Mapping(m.path, m.kind, m.target) for m in request.mappings
                ],
            )

            if candidate.exists():
                candidate.unlink()
            with redirect_stdout(buffer):
                pipeline.run(candidate)
            _carry_decisions(conn, candidate)

            # Swap. The live connection must be closed first: DuckDB holds the
            # file open, and replacing it underneath a live handle leaves the
            # process reading a file that no longer exists at that path.
            dependencies.close_connection()
            os.replace(candidate, live)
            dependencies.get_database()
        except Exception as error:  # noqa: BLE001 - surfaced to the operator
            candidate.unlink(missing_ok=True)
            if promoted is not None:
                promotion.rollback(promoted.batch_root)
            dependencies.reopen()
            raise HTTPException(
                status_code=500,
                detail=(
                    f"ingestion failed and was rolled back; the warehouse is "
                    f"unchanged: {error}"
                ),
            ) from error

        after = _snapshot(get_connection())

    staging.discard(upload_id)
    staging.sweep()

    return ConfirmResult(
        batch_name=promoted.batch_name,
        sequence=promoted.sequence,
        files_promoted=promoted.files_promoted,
        aliases_added=promoted.aliases_added,
        excluded=promoted.excluded,
        duration_seconds=round(time.perf_counter() - started, 2),
        before=before,
        after=after,
        delta={key: after[key] - before[key] for key in after},
    )
