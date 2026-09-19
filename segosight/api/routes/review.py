"""Pending-review queue and the decision endpoint."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from ...curated import promotion
from ...curated.extraction import PENDING, TABLE as INSIGHTS
from ...curated.llm import MAX_LLM_CONFIDENCE  # noqa: F401  (documents the cap)
from ..dependencies import get_connection, write_lock
from ..schemas import Decision, DecisionResult, ReviewItem

router = APIRouter(prefix="/api/review", tags=["review"])

#: Button verbs per insight type. Approving a commitment merges it into the
#: tracked-commitment register; approving a concern attaches it to the alert it
#: supports. The wireframe's Merge/Attach wording comes from here.
_VERBS = {
    "commitment": ("Merge", "Mark invalid"),
    "customer_request": ("Merge", "Mark invalid"),
    "field_concern": ("Attach", "Discard"),
    "recommendation": ("Attach", "Discard"),
    "identity_candidate": ("Attach", "Discard"),
}

_SELECT = f"""
SELECT i.insight_id, i.insight_type, i.summary, i.quote, i.author,
       i.authored_on, i.source_file, i.customer_id, c.customer_name,
       i.facility_id, f.facility_name, i.system_id, c.acv_usd,
       i.confidence_score, i.extractor, i.due_on, i.due_phrase,
       i.days_overdue, i.fulfilled, i.fulfillment_basis,
       i.commitment_subject, i.status
FROM {INSIGHTS} i
LEFT JOIN canonical.facility f USING (facility_id)
LEFT JOIN canonical.customer c ON c.customer_id = i.customer_id
"""


def _to_item(row) -> ReviewItem:
    extractor = row[14] or ""
    approve, reject = _VERBS.get(row[1], ("Approve", "Reject"))
    return ReviewItem(
        insight_id=row[0], insight_type=row[1], summary=row[2], quote=row[3],
        author=row[4], authored_on=row[5], source_file=row[6],
        customer_id=row[7], customer_name=row[8], facility_id=row[9],
        facility_name=row[10], system_id=row[11], acv_usd=row[12],
        confidence_score=row[13],
        # Honest provenance: these rows are produced by deterministic patterns
        # unless the optional local model proposed them.
        provenance="ai" if extractor.startswith("llm") else "rule",
        extractor=extractor, due_on=row[15], due_phrase=row[16],
        days_overdue=row[17], fulfilled=row[18], fulfillment_basis=row[19],
        commitment_subject=row[20], status=row[21],
        approve_verb=approve, reject_verb=reject,
    )


@router.get("", response_model=list[ReviewItem])
def list_review(
    status: str = Query(PENDING),
    insight_type: str | None = None,
    limit: int = Query(50, ge=1, le=500),
) -> list[ReviewItem]:
    """Queue ordered as the wireframe specifies: overdue and consequential first."""
    clause = "WHERE i.status = ?"
    params: list = [status]
    if insight_type:
        clause += " AND i.insight_type = ?"
        params.append(insight_type)
    rows = get_connection().execute(
        f"""{_SELECT} {clause}
            ORDER BY coalesce(i.fulfilled, true) ASC,
                     coalesce(i.days_overdue, 0) DESC,
                     coalesce(c.acv_usd, 0) DESC,
                     i.confidence_score ASC
            LIMIT ?""",
        params + [limit],
    ).fetchall()
    return [_to_item(row) for row in rows]


@router.get("/{insight_id:path}", response_model=ReviewItem)
def get_review(insight_id: str) -> ReviewItem:
    row = get_connection().execute(
        f"{_SELECT} WHERE i.insight_id = ?", [insight_id]
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"no insight {insight_id!r}")
    return _to_item(row)


@router.post("/{insight_id:path}/decision", response_model=DecisionResult)
def decide(insight_id: str, body: Decision) -> DecisionResult:
    """Record a reviewer's decision and promote or detach accordingly."""
    conn = get_connection()
    with write_lock():
        try:
            effects = promotion.decide(
                conn, insight_id, body.decision, body.reviewer, body.note
            )
        except promotion.ReviewError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error

    if effects["commitment_created"]:
        message = "Approved and merged into tracked commitments."
    elif body.decision == promotion.APPROVED:
        message = (
            f"Approved and attached to {effects['evidence_links_updated']} alert(s)."
        )
    else:
        message = (
            f"Rejected; detached from {effects['evidence_links_updated']} alert(s). "
            "The record is kept."
        )
    return DecisionResult(**effects, message=message)
