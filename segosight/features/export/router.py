"""Compliance export download."""

from __future__ import annotations

from fastapi import APIRouter, Query
from fastapi.responses import Response

from segosight.app.dependencies import get_connection
from segosight.features.export import bundle

router = APIRouter(prefix="/api/export", tags=["export"])


@router.get("/bundle.zip")
def export_bundle(
    severity: str = Query("all"),
    reviewer: str = Query("unknown"),
) -> Response:
    """Governed alerts and pending insights, as two CSVs in one archive.

    Generated server-side rather than in the browser so both queues come from
    the same query path the dashboard uses, and so the archive carries a
    manifest that explains what each file is without the UI around it.
    """
    conn = get_connection()
    as_of = conn.execute(
        "SELECT max(observed_at)::DATE FROM canonical.reading_event"
    ).fetchone()[0]

    payload, filename = bundle.build(
        conn,
        severity=severity,
        as_of=str(as_of) if as_of else None,
        reviewer=reviewer,
    )
    return Response(
        content=payload,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
