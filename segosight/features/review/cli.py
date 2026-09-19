"""Command-line access to the pending-review queue.

    python -m segosight.features.review.cli list [--type TYPE] [--limit N]
    python -m segosight.features.review.cli show INSIGHT_ID
    python -m segosight.features.review.cli approve INSIGHT_ID --reviewer NAME [--note TEXT]
    python -m segosight.features.review.cli reject  INSIGHT_ID --reviewer NAME [--note TEXT]

This is the human gate, not a convenience. Prose extraction proposes; a named
reviewer disposes. Approval is recorded with the reviewer and a timestamp so
that a decision about a compliance record is itself auditable, and an approved
row keeps its original confidence score rather than being rewritten to 1.0.

Rejection never deletes. The row stays with `status = 'rejected'`, which is
what stops the same false positive being re-proposed as though it were new.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sys

from segosight.features.review.curated.extraction import PENDING, TABLE
from segosight.shared.warehouse import connect

APPROVED = "approved"
REJECTED = "rejected"


def _rows(conn, sql, params=()):
    return conn.execute(sql, list(params)).fetchall()


def cmd_list(conn, args) -> int:
    clause = "WHERE status = ?"
    params = [args.status]
    if args.type:
        clause += " AND insight_type = ?"
        params.append(args.type)
    rows = _rows(
        conn,
        f"""SELECT insight_id, insight_type, confidence_score, facility_id,
                   days_overdue, fulfilled, substr(quote, 1, 88)
            FROM {TABLE} {clause}
            ORDER BY coalesce(fulfilled, true) ASC,
                     coalesce(days_overdue, 0) DESC,
                     confidence_score ASC
            LIMIT ?""",
        params + [args.limit],
    )
    if not rows:
        print(f"No insights with status {args.status!r}.")
        return 0
    print(f"{len(rows)} insight(s), status={args.status}\n")
    for insight_id, kind, confidence, facility, overdue, fulfilled, quote in rows:
        flag = "UNRESOLVED" if fulfilled is False else ("n/a" if fulfilled is None else "ok")
        age = f"{overdue}d" if overdue is not None else "-"
        print(f"  {insight_id}")
        print(
            f"    {kind:<18} conf={confidence:<5} {facility or '------':<7} "
            f"open={age:<6} {flag}"
        )
        print(f'    "{quote}"')
    return 0


def cmd_show(conn, args) -> int:
    row = _rows(
        conn,
        f"""SELECT insight_id, insight_type, summary, quote, source_file,
                   authored_on, author, customer_id, facility_id, system_id,
                   link_confidence, link_basis, due_on, due_phrase,
                   confidence_score, status, review_decision, reviewed_by,
                   fulfilled, fulfillment_basis, days_overdue, extractor
            FROM {TABLE} WHERE insight_id = ?""",
        [args.insight_id],
    )
    if not row:
        print(f"No insight {args.insight_id!r}", file=sys.stderr)
        return 1
    labels = [
        "insight_id", "type", "summary", "quote", "source", "authored",
        "author", "customer", "facility", "system", "link_confidence",
        "link_basis", "due_on", "due_phrase", "confidence", "status",
        "decision", "reviewed_by", "fulfilled", "fulfillment", "days_open",
        "extractor",
    ]
    for label, value in zip(labels, row[0]):
        print(f"  {label:<16} {value}")
    return 0


def _decide(conn, args, decision: str) -> int:
    updated = conn.execute(
        f"""UPDATE {TABLE}
            SET status = ?, review_decision = ?, reviewed_by = ?, reviewed_at = ?
            WHERE insight_id = ? AND status = ?""",
        [
            decision,
            args.note or decision,
            args.reviewer,
            dt.datetime.now().replace(microsecond=0),
            args.insight_id,
            PENDING,
        ],
    ).fetchone()[0]
    if not updated:
        print(
            f"{args.insight_id!r} is not pending review (already decided, or unknown).",
            file=sys.stderr,
        )
        return 1
    print(f"{args.insight_id} -> {decision} by {args.reviewer}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="segosight.features.review.cli")
    parser.add_argument("--warehouse", default=None)
    sub = parser.add_subparsers(dest="command", required=True)

    listing = sub.add_parser("list", help="show queued insights")
    listing.add_argument("--type")
    listing.add_argument("--status", default=PENDING)
    listing.add_argument("--limit", type=int, default=20)
    listing.set_defaults(func=cmd_list)

    show = sub.add_parser("show", help="show one insight in full")
    show.add_argument("insight_id")
    show.set_defaults(func=cmd_show)

    for name, decision in (("approve", APPROVED), ("reject", REJECTED)):
        command = sub.add_parser(name, help=f"mark an insight {decision}")
        command.add_argument("insight_id")
        command.add_argument("--reviewer", required=True)
        command.add_argument("--note")
        command.set_defaults(func=lambda c, a, d=decision: _decide(c, a, d))

    args = parser.parse_args(argv)
    conn = connect(args.warehouse)
    try:
        return args.func(conn, args)
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
