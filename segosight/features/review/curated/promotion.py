"""Promotion of a reviewed insight into governed operational record.

This is what makes the human gate mean something. Extraction proposes; a named
reviewer promotes. Until someone approves, a prose-derived fact is a candidate
and nothing downstream treats it as true.

On approval:

* a commitment or customer request becomes a row in
  `curated.customer_commitment` -- the object the guidelines call for when they
  say customer-facing commitments are tracked to completion by the service
  coordinator, and that a commitment made in email and not scheduled is a miss
  waiting to be discovered by the customer;
* a field concern or recommendation has its `alert_evidence` link approved,
  which clears the "rests on unreviewed extractions" banner on the alert it
  supports.

On rejection the insight is marked rejected and its evidence links are detached,
so a false positive stops colouring an alert without being deleted -- the row
survives as the record of a decision.

Both the API and the CLI route through here, so a decision made in the UI and
one made in a terminal produce identical state.
"""

from __future__ import annotations

import datetime as dt

import duckdb

from segosight.shared.warehouse import CURATED
from segosight.features.alerts.curated.aggregation import EVIDENCE_TABLE
from segosight.features.review.curated.extraction import PENDING, TABLE as INSIGHTS

COMMITMENT_TABLE = f"{CURATED}.customer_commitment"

APPROVED = "approved"
REJECTED = "rejected"

#: Insight types that become tracked commitments when approved.
_COMMITMENT_TYPES = ("commitment", "customer_request")

_DDL = f"""
CREATE TABLE IF NOT EXISTS {COMMITMENT_TABLE} (
    commitment_id     VARCHAR PRIMARY KEY,
    source_insight_id VARCHAR NOT NULL,
    customer_id       VARCHAR,
    facility_id       VARCHAR,
    system_id         VARCHAR,
    commitment_type   VARCHAR NOT NULL,
    deliverable       VARCHAR,
    promise           VARCHAR NOT NULL,
    promised_by       VARCHAR,
    promised_on       DATE,
    due_on            DATE,
    status            VARCHAR NOT NULL,
    fulfilled         BOOLEAN,
    fulfillment_basis VARCHAR,
    days_overdue      INTEGER,
    source_file       VARCHAR,
    approved_by       VARCHAR NOT NULL,
    approved_at       TIMESTAMP NOT NULL
)
"""


def ensure_schema(conn: duckdb.DuckDBPyConnection) -> None:
    conn.execute(_DDL)


def _fetch(conn: duckdb.DuckDBPyConnection, insight_id: str):
    return conn.execute(
        f"""SELECT insight_id, insight_type, customer_id, facility_id, system_id,
                   commitment_subject, quote, author, authored_on, due_on,
                   fulfilled, fulfillment_basis, days_overdue, source_file, status
            FROM {INSIGHTS} WHERE insight_id = ?""",
        [insight_id],
    ).fetchone()


class ReviewError(RuntimeError):
    """Raised when a decision cannot be applied."""


def decide(
    conn: duckdb.DuckDBPyConnection,
    insight_id: str,
    decision: str,
    reviewer: str,
    note: str | None = None,
    reviewed_at: dt.datetime | None = None,
) -> dict:
    """Apply a review decision and promote or detach accordingly.

    Returns a summary of what the decision changed, so the caller can tell the
    reviewer what their click actually did rather than just confirming it.
    """
    if decision not in (APPROVED, REJECTED):
        raise ReviewError(f"unknown decision {decision!r}")
    if not reviewer or not reviewer.strip():
        raise ReviewError("a reviewer name is required: decisions are attributable")

    ensure_schema(conn)
    row = _fetch(conn, insight_id)
    if row is None:
        raise ReviewError(f"no insight {insight_id!r}")
    if row[14] != PENDING:
        raise ReviewError(
            f"{insight_id!r} is already {row[14]}; decisions are not re-made silently"
        )

    stamp = reviewed_at or dt.datetime.now().replace(microsecond=0)
    conn.execute(
        f"""UPDATE {INSIGHTS}
            SET status = ?, review_decision = ?, reviewed_by = ?, reviewed_at = ?
            WHERE insight_id = ?""",
        [decision, note or decision, reviewer, stamp, insight_id],
    )

    effects: dict = {
        "insight_id": insight_id,
        "decision": decision,
        "reviewer": reviewer,
        "reviewed_at": stamp.isoformat(),
        "commitment_created": None,
        "evidence_links_updated": 0,
    }

    if decision == REJECTED:
        # Detach rather than delete: the alert stops citing it, the decision
        # survives as the reason it stopped.
        effects["evidence_links_updated"] = conn.execute(
            f"""UPDATE {EVIDENCE_TABLE} SET review_status = ?
                WHERE evidence_id = ?""",
            [REJECTED, insight_id],
        ).fetchone()[0]
        _refresh_alert_basis(conn)
        return effects

    (_, insight_type, customer_id, facility_id, system_id, subject, quote,
     author, authored_on, due_on, fulfilled, basis, days_overdue, source_file,
     _status) = row

    if insight_type in _COMMITMENT_TYPES:
        commitment_id = f"COMMIT:{insight_id}"
        conn.execute(
            f"""INSERT OR REPLACE INTO {COMMITMENT_TABLE} VALUES
                (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            [
                commitment_id, insight_id, customer_id, facility_id, system_id,
                insight_type, subject, quote, author, authored_on, due_on,
                "open" if fulfilled is not True else "met",
                fulfilled, basis, days_overdue, source_file, reviewer, stamp,
            ],
        )
        effects["commitment_created"] = commitment_id

    effects["evidence_links_updated"] = conn.execute(
        f"""UPDATE {EVIDENCE_TABLE} SET review_status = ? WHERE evidence_id = ?""",
        [APPROVED, insight_id],
    ).fetchone()[0]
    _refresh_alert_basis(conn)
    return effects


def _refresh_alert_basis(conn: duckdb.DuckDBPyConnection) -> None:
    """Recompute whether each alert still rests on unreviewed extractions.

    An alert is only flagged once *every* piece of prose it cites has been
    reviewed; one approved quote does not clear a card that also cites two
    pending ones.
    """
    from segosight.features.alerts.curated.aggregation import TABLE as ALERTS

    conn.execute(
        f"""
        UPDATE {ALERTS} AS a
        SET evidence_basis = CASE
            WHEN EXISTS (
                SELECT 1 FROM {EVIDENCE_TABLE} e
                WHERE e.alert_fingerprint = a.fingerprint
                  AND e.evidence_role = 'primary'
                  AND e.review_status = '{PENDING}'
            ) THEN 'prose_pending_review'
            ELSE 'prose_reviewed'
        END
        WHERE a.evidence_basis LIKE 'prose%'
        """
    )


def unreviewed_evidence_counts(conn: duckdb.DuckDBPyConnection) -> dict[str, int]:
    """Pending prose citations per alert fingerprint, for the UI banner."""
    ensure_schema(conn)
    return {
        row[0]: row[1]
        for row in conn.execute(
            f"""SELECT alert_fingerprint, count(*)
                FROM {EVIDENCE_TABLE}
                WHERE review_status = '{PENDING}'
                GROUP BY 1"""
        ).fetchall()
    }
