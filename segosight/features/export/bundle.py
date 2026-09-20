"""Compliance export bundle: governed alerts and pending insights.

The two queues are exported as two CSVs inside one archive rather than one
merged table, because they are not the same kind of claim. An alert carries a
`rule_version` -- a judgement made under a published guideline revision. An
insight carries a `confidence_score` and a `provenance` of rule or ai -- a
machine's reading of someone's prose that no human has approved. They share
four columns out of roughly twenty; putting them in one table as sibling rows
would assert an equivalence that does not exist, in a file that may reach a
customer.

Each CSV carries its own provenance header, and a manifest names both so the
archive explains itself without the UI that produced it.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import zipfile

import duckdb

from segosight.features.alerts.curated.aggregation import (
    EVIDENCE_TABLE,
    TABLE as ALERTS,
)
from segosight.features.review.curated.extraction import PENDING, TABLE as INSIGHTS

ALERTS_FILENAME = "segosight_alerts.csv"
INSIGHTS_FILENAME = "segosight_pending_insights.csv"
MANIFEST_FILENAME = "manifest.txt"

ALERT_COLUMNS = [
    "alert_id", "severity", "priority_score", "risk_class", "title", "why",
    "consequence", "customer_name", "account_tier", "acv_usd", "facility_name",
    "system_id", "system_label", "parameter_code", "owner", "evidence_basis",
    "evidence_count", "pending_evidence", "first_observed", "last_observed",
    "rule_version",
]

INSIGHT_COLUMNS = [
    "insight_id", "insight_type", "status", "provenance", "extractor",
    "confidence_score", "summary", "quote", "author", "authored_on",
    "source_file", "customer_name", "facility_name", "system_id", "acv_usd",
    "due_on", "due_phrase", "days_overdue", "fulfilled", "commitment_subject",
]

_ALERT_SQL = f"""
SELECT a.fingerprint, a.severity, a.priority_score, a.risk_class, a.title,
       a.why, a.consequence, a.customer_name, a.account_tier, a.acv_usd,
       a.facility_name, a.system_id, a.system_label, a.parameter_code,
       a.owner, coalesce(a.evidence_basis, 'structured'),
       coalesce(e.total, 0), coalesce(e.pending, 0),
       a.first_observed, a.last_observed, a.rule_version
FROM {ALERTS} a
LEFT JOIN (
    SELECT alert_fingerprint,
           count(*) AS total,
           count(*) FILTER (WHERE review_status = '{PENDING}') AS pending
    FROM {EVIDENCE_TABLE}
    GROUP BY 1
) e ON e.alert_fingerprint = a.fingerprint
"""

_INSIGHT_SQL = f"""
SELECT i.insight_id, i.insight_type, i.status, i.extractor, i.confidence_score,
       i.summary, i.quote, i.author, i.authored_on, i.source_file,
       c.customer_name, f.facility_name, i.system_id, c.acv_usd,
       i.due_on, i.due_phrase, i.days_overdue, i.fulfilled,
       i.commitment_subject
FROM {INSIGHTS} i
LEFT JOIN canonical.facility f USING (facility_id)
LEFT JOIN canonical.customer c ON c.customer_id = i.customer_id
WHERE i.status = ?
ORDER BY i.confidence_score DESC, i.authored_on DESC NULLS LAST
"""


def _write(rows: list[list], columns: list[str], header: list[str]) -> str:
    buffer = io.StringIO(newline="")
    for line in header:
        buffer.write(f"{line}\r\n")
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(columns)
    writer.writerows(rows)
    return buffer.getvalue()


def _stamp(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def fetch_alerts(
    conn: duckdb.DuckDBPyConnection, severity: str | None = None
) -> list[list]:
    clause = "WHERE a.severity = ?" if severity and severity != "all" else ""
    params = [severity] if clause else []
    rows = conn.execute(
        f"""{_ALERT_SQL} {clause}
            ORDER BY a.priority_score DESC, a.last_observed DESC NULLS LAST""",
        params,
    ).fetchall()
    return [[_stamp(v) for v in row] for row in rows]


def fetch_insights(
    conn: duckdb.DuckDBPyConnection, status: str = PENDING
) -> list[list]:
    rows = conn.execute(_INSIGHT_SQL, [status]).fetchall()
    out = []
    for row in rows:
        extractor = row[3] or ""
        # Honest provenance, same rule the review queue applies: deterministic
        # unless the optional local model proposed it.
        provenance = "ai" if extractor.startswith("llm") else "rule"
        out.append(
            [
                _stamp(row[0]), _stamp(row[1]), _stamp(row[2]), provenance,
                _stamp(extractor), _stamp(row[4]), _stamp(row[5]), _stamp(row[6]),
                _stamp(row[7]), _stamp(row[8]), _stamp(row[9]), _stamp(row[10]),
                _stamp(row[11]), _stamp(row[12]), _stamp(row[13]), _stamp(row[14]),
                _stamp(row[15]), _stamp(row[16]), _stamp(row[17]), _stamp(row[18]),
            ]
        )
    return out


def build(
    conn: duckdb.DuckDBPyConnection,
    *,
    severity: str = "all",
    as_of: str | None = None,
    reviewer: str = "unknown",
) -> tuple[bytes, str]:
    """Return (zip bytes, filename)."""
    generated_at = dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()

    alerts = fetch_alerts(conn, severity)
    total_alerts = conn.execute(f"SELECT count(*) FROM {ALERTS}").fetchone()[0]
    insights = fetch_insights(conn)

    versions = sorted({row[20] for row in alerts if row[20]})
    pending_evidence = sum(int(row[17] or 0) for row in alerts)

    scope = (
        "complete governed queue"
        if len(alerts) == total_alerts
        else f"filtered view ({len(alerts)} of {total_alerts})"
    )

    alert_header = [
        "# SegoSight governed alerts",
        f"# generated_at,{generated_at}",
        f"# generated_by,{reviewer}",
        f"# data_as_of,{as_of or 'unknown'}",
        f"# rule_version,{' '.join(versions) or 'unknown'}",
        f"# severity_filter,{severity}",
        f"# rows_exported,{len(alerts)}",
        f"# rows_in_queue,{total_alerts}",
        f"# scope,{scope}",
        f"# pending_evidence_included,{pending_evidence}",
    ]

    # Deliberately says "not governed findings". Someone opening this file in
    # isolation must not read a confidence score as a compliance judgement.
    insight_header = [
        "# SegoSight pending insight review -- NOT GOVERNED FINDINGS",
        "# These rows are extracted from prose and awaiting human approval.",
        "# They carry a confidence_score, not a rule_version, and must not be",
        "# reported to a customer as findings.",
        f"# generated_at,{generated_at}",
        f"# generated_by,{reviewer}",
        f"# data_as_of,{as_of or 'unknown'}",
        "# status,pending_review",
        "# severity_filter,none -- the review queue has no severity",
        f"# rows_exported,{len(insights)}",
    ]

    manifest = "\n".join(
        [
            "SegoSight compliance export",
            f"generated_at      {generated_at}",
            f"generated_by      {reviewer}",
            f"data_as_of        {as_of or 'unknown'}",
            f"rule_version      {' '.join(versions) or 'unknown'}",
            "",
            f"{ALERTS_FILENAME}",
            f"  {len(alerts)} governed alert(s); severity filter: {severity}",
            f"  scope: {scope}",
            "  Judgements made under the rule version above.",
            "",
            f"{INSIGHTS_FILENAME}",
            f"  {len(insights)} pending insight(s); unfiltered.",
            "  Extracted from prose and awaiting human approval. These are NOT",
            "  governed findings and carry a confidence score rather than a",
            "  rule version. Do not report them to a customer as findings.",
            "",
        ]
    )

    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        # The BOM keeps Excel from mangling quotes and degree signs on Windows.
        bundle.writestr(
            ALERTS_FILENAME,
            "﻿" + _write(alerts, ALERT_COLUMNS, alert_header),
        )
        bundle.writestr(
            INSIGHTS_FILENAME,
            "﻿" + _write(insights, INSIGHT_COLUMNS, insight_header),
        )
        bundle.writestr(MANIFEST_FILENAME, manifest)

    scope_slug = "all" if severity == "all" else severity
    filename = f"segosight-export_{scope_slug}_{as_of or 'undated'}.zip"
    return archive.getvalue(), filename
