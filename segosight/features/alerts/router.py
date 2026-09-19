"""Governed alert queue and alert detail."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from segosight.features.chemistry.canonical.series import TABLE as EVENTS
from segosight.features.alerts.curated.aggregation import EVIDENCE_TABLE, TABLE as ALERTS
from segosight.features.chemistry.curated.assessments import TABLE as ASSESSMENTS
from segosight.features.service.curated.coverage import TABLE as COVERAGE
from segosight.features.review.curated.extraction import PENDING
from segosight.features.compliance.curated.microbio import TABLE as MICROBIO
from segosight.app.dependencies import get_connection
from segosight.app.schemas import AlertDetail, AlertSummary, Evidence, SeriesPoint

router = APIRouter(prefix="/api/alerts", tags=["alerts"])

_SELECT = f"""
SELECT fingerprint, risk_class, severity, priority_score, title, why,
       consequence, customer_id, customer_name, account_tier, acv_usd,
       facility_id, facility_name, system_id, system_label, parameter_code,
       owner, coalesce(evidence_basis, 'structured'), first_observed,
       last_observed
FROM {ALERTS}
"""


def _evidence_for(conn, fingerprints: list[str]) -> dict[str, list[Evidence]]:
    if not fingerprints:
        return {}
    placeholders = ",".join("?" * len(fingerprints))
    rows = conn.execute(
        f"""SELECT alert_fingerprint, evidence_id, quote, summary, source_file,
                   authored_on, confidence_score, review_status
            FROM {EVIDENCE_TABLE}
            WHERE alert_fingerprint IN ({placeholders})
            ORDER BY review_status, authored_on DESC""",
        fingerprints,
    ).fetchall()
    grouped: dict[str, list[Evidence]] = {}
    for row in rows:
        grouped.setdefault(row[0], []).append(
            Evidence(
                evidence_id=row[1], quote=row[2], summary=row[3],
                source_file=row[4], authored_on=row[5], confidence_score=row[6],
                review_status=row[7],
            )
        )
    return grouped


def _to_summary(row, evidence: list[Evidence]) -> AlertSummary:
    return AlertSummary(
        alert_id=row[0], risk_class=row[1], severity=row[2],
        priority_score=row[3], title=row[4], why=row[5], consequence=row[6],
        customer_id=row[7], customer_name=row[8], account_tier=row[9],
        acv_usd=row[10], facility_id=row[11], facility_name=row[12],
        system_id=row[13], system_label=row[14], parameter_code=row[15],
        owner=row[16], evidence_basis=row[17],
        unreviewed_evidence=sum(1 for e in evidence if e.review_status == PENDING),
        evidence=evidence, first_observed=row[18], last_observed=row[19],
    )


@router.get("", response_model=list[AlertSummary])
def list_alerts(
    severity: str | None = None,
    risk_class: str | None = None,
    limit: int = Query(100, ge=1, le=500),
    evidence_limit: int = Query(3, ge=0, le=20),
) -> list[AlertSummary]:
    """Queue ordered by priority, with a few evidence lines per card."""
    conn = get_connection()
    clauses, params = [], []
    if severity:
        clauses.append("severity = ?")
        params.append(severity)
    if risk_class:
        clauses.append("risk_class = ?")
        params.append(risk_class)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    rows = conn.execute(
        f"""{_SELECT} {where}
            ORDER BY priority_score DESC, last_observed DESC NULLS LAST
            LIMIT ?""",
        params + [limit],
    ).fetchall()

    evidence = _evidence_for(conn, [r[0] for r in rows])
    return [
        _to_summary(row, evidence.get(row[0], [])[:evidence_limit]) for row in rows
    ]


@router.get("/{alert_id:path}", response_model=AlertDetail)
def get_alert(alert_id: str) -> AlertDetail:
    """One alert with the evidence chain behind it.

    Detail is where a finding has to survive scrutiny, so it carries the raw
    measurement series, every assessment against the governing band, escalation
    history and coverage state -- not a restatement of the card.
    """
    conn = get_connection()
    row = conn.execute(f"{_SELECT} WHERE fingerprint = ?", [alert_id]).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"no alert {alert_id!r}")

    evidence = _evidence_for(conn, [alert_id]).get(alert_id, [])
    summary = _to_summary(row, evidence)
    detail = AlertDetail(**summary.model_dump())

    system_id, parameter = row[13], row[15]
    if system_id and parameter:
        detail.series = [
            SeriesPoint(
                observed_at=point[0], value=point[1],
                collection_method=point[2], quality_status=point[3],
            )
            for point in conn.execute(
                f"""SELECT observed_at, normalized_value, collection_method,
                           quality_status
                    FROM {EVENTS}
                    WHERE system_id = ? AND parameter_code = ? AND is_current
                      AND normalized_value IS NOT NULL
                    ORDER BY observed_at""",
                [system_id, parameter],
            ).fetchall()
        ]
        band = conn.execute(
            f"""SELECT any_value(standard_unit), any_value(applied_lower),
                       any_value(applied_upper), any_value(governing_program)
                FROM {ASSESSMENTS}
                WHERE system_id = ? AND parameter_code = ?""",
            [system_id, parameter],
        ).fetchone()
        if band:
            (detail.standard_unit, detail.lower_limit,
             detail.upper_limit, detail.governing_program) = band

        detail.assessments = [
            dict(
                zip(
                    ("observed_at", "value", "status", "severity", "explanation"),
                    record,
                )
            )
            for record in conn.execute(
                f"""SELECT observed_at, normalized_value, status, severity,
                           explanation
                    FROM {ASSESSMENTS}
                    WHERE system_id = ? AND parameter_code = ? AND out_of_band
                    ORDER BY observed_at DESC LIMIT 25""",
                [system_id, parameter],
            ).fetchall()
        ]

    if system_id:
        detail.escalations = [
            dict(
                zip(
                    ("observed_at", "dipslide_log10", "escalation_type",
                     "documented", "days_undocumented", "required_action"),
                    record,
                )
            )
            for record in conn.execute(
                f"""SELECT observed_at, dipslide_log10, escalation_type,
                           documented, days_undocumented, required_action
                    FROM {MICROBIO} WHERE system_id = ?
                    ORDER BY observed_at DESC LIMIT 30""",
                [system_id],
            ).fetchall()
        ]

    if row[11]:
        coverage = conn.execute(
            f"""SELECT status, days_since_visit, cadence_ratio, service_frequency,
                       last_visit_date, last_technician, technician_departed,
                       explanation
                FROM {COVERAGE} WHERE facility_id = ?""",
            [row[11]],
        ).fetchone()
        if coverage:
            detail.coverage = dict(
                zip(
                    ("status", "days_since_visit", "cadence_ratio",
                     "service_frequency", "last_visit_date", "last_technician",
                     "technician_departed", "explanation"),
                    coverage,
                )
            )
    return detail
