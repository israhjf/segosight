"""Curated tier: microbiological escalation ladder (guidelines section 5).

Healthcare and assisted-living sites run the tighter section 5.3 ladder because
of aerosol exposure risk:

* a single 10^4 requires same-visit corrective action and a re-test within one
  week;
* two consecutive results at or above 10^4 require notification of the
  operations director within one business day, a documented remediation plan
  communicated to the customer in writing, and continued weekly re-tests until
  two consecutive results return to 10^3 or below;
* any single 10^5 requires an urgent recommendation for offline cleaning and
  disinfection.

The addendum closes with the sentence this module exists to enforce: "Verbal
mentions to site staff do not satisfy the notification requirement in this
addendum. The escalation exists on paper or it did not happen."

So each escalation records both the required action and whether documentary
evidence of it exists. Guidelines section 9 makes the work order the record,
with verbal notification an explicit courtesy rather than compliance -- and it
requires that work order "within one business day of identification".

The window matters. Maeser Ridge's CT-2 has exactly one work order, WO-0160,
raised on 2026-09-09. Accepting any later work order as evidence would let it
retroactively satisfy escalations going back to 2026-05-25 and report a
three-month compliance gap as fully documented. Evidence must therefore land
inside `documentation_window_days` of the trigger; a later work order is
recorded as remediation but does not close the notification requirement.
"""

from __future__ import annotations

import datetime as dt

import duckdb

from ..canonical.events import TABLE as EVENTS
from ..clean.versioning import TABLE as VERSIONS
from ..warehouse import CURATED, bulk_insert
from .programs import Config, load_config

TABLE = f"{CURATED}.microbio_escalation"

CORRECTIVE = "corrective_action"
ESCALATION = "director_notification"
URGENT = "urgent_offline_clean"

_DDL = f"""
CREATE OR REPLACE TABLE {TABLE} (
    escalation_id     VARCHAR NOT NULL,
    system_id         VARCHAR NOT NULL,
    facility_id       VARCHAR,
    observed_at       TIMESTAMP,
    dipslide_log10    DOUBLE,
    previous_log10    DOUBLE,
    ladder            VARCHAR NOT NULL,
    escalation_type   VARCHAR NOT NULL,
    severity          VARCHAR NOT NULL,
    required_action   VARCHAR NOT NULL,
    retest_due_by     DATE,
    documented        BOOLEAN NOT NULL,
    documented_by     VARCHAR,
    days_undocumented INTEGER,
    rule_version      VARCHAR NOT NULL,
    explanation       VARCHAR
)
"""

_COLUMNS = [
    "escalation_id", "system_id", "facility_id", "observed_at",
    "dipslide_log10", "previous_log10", "ladder", "escalation_type", "severity",
    "required_action", "retest_due_by", "documented", "documented_by",
    "days_undocumented", "rule_version", "explanation",
]


def build(
    conn: duckdb.DuckDBPyConnection,
    config: Config | None = None,
    as_of: dt.date | None = None,
) -> int:
    """Walk each system's dipslide history and apply the governing ladder."""
    cfg = config or load_config()
    conn.execute(_DDL)

    rows = conn.execute(
        f"""
        SELECT system_id, facility_id, observed_at, normalized_value
        FROM {EVENTS}
        WHERE parameter_code = 'dipslide' AND alert_eligible
          AND normalized_value IS NOT NULL
        ORDER BY system_id, observed_at
        """
    ).fetchall()

    # Work orders are the documentary record. Index them by system and date.
    work_orders = conn.execute(
        f"""
        SELECT json_extract_string(payload, '$.system_id') AS system_id,
               try_cast(json_extract_string(payload, '$.created_date') AS DATE) AS created,
               json_extract_string(payload, '$.wo_id') AS wo_id
        FROM {VERSIONS}
        WHERE entity = 'work_orders' AND is_current
        """
    ).fetchall()
    orders_by_system: dict[str, list[tuple]] = {}
    for system_id, created, wo_id in work_orders:
        if system_id and created:
            orders_by_system.setdefault(system_id, []).append((created, wo_id))
    for key in orders_by_system:
        orders_by_system[key].sort()

    healthcare_cfg = cfg.microbio["healthcare"]
    general_cfg = cfg.microbio["general"]
    retest_days = int(healthcare_cfg["retest_within_days"])
    documentation_window = int(cfg.thresholds.get("documentation_window_days", 3))

    history: dict[str, list[tuple]] = {}
    for system_id, facility_id, observed_at, value in rows:
        history.setdefault(system_id, []).append((observed_at, value, facility_id))

    reference = as_of or max((r[2].date() for r in rows if r[2]), default=dt.date.today())

    out = []
    for system_id, series in history.items():
        facility_id = series[0][2]
        healthcare = cfg.is_healthcare(facility_id)
        ladder = "healthcare" if healthcare else "general"
        settings = healthcare_cfg if healthcare else general_cfg
        corrective_at = float(settings["corrective_at"])
        urgent_at = float(
            settings.get("urgent_single_result", settings.get("elevated_at"))
        )

        for index, (observed_at, value, _) in enumerate(series):
            previous = series[index - 1][1] if index else None
            triggers = []

            if value >= urgent_at:
                triggers.append(
                    (
                        URGENT, "critical",
                        "urgent recommendation for offline cleaning and "
                        "disinfection of the affected tower",
                    )
                )
            if (
                healthcare
                and previous is not None
                and previous >= corrective_at
                and value >= corrective_at
            ):
                triggers.append(
                    (
                        ESCALATION, "critical",
                        "notify the operations director within one business day, "
                        "communicate a documented remediation plan to the customer "
                        "in writing, and re-test weekly until two consecutive "
                        "results return to 10^3 or below",
                    )
                )
            if value >= corrective_at and not triggers:
                triggers.append(
                    (
                        CORRECTIVE, "high",
                        "same-visit corrective action: verify oxidant residual and "
                        "feed equipment, supplemental biocide, re-test",
                    )
                )

            for escalation_type, severity, action in triggers:
                trigger_date = observed_at.date()
                deadline = trigger_date + dt.timedelta(days=documentation_window)
                documented_by = next(
                    (
                        wo_id
                        for created, wo_id in orders_by_system.get(system_id, [])
                        if trigger_date <= created <= deadline
                    ),
                    None,
                )
                # A work order raised outside the window is real remediation but
                # does not satisfy the notification requirement; record it so the
                # operator sees the action that eventually happened.
                late_evidence = next(
                    (
                        wo_id
                        for created, wo_id in orders_by_system.get(system_id, [])
                        if created > deadline
                    ),
                    None,
                )
                undocumented_days = (
                    None if documented_by else (reference - trigger_date).days
                )
                explanation = (
                    f"dipslide 10^{value:.0f}"
                    + (f" following 10^{previous:.0f}" if previous is not None else "")
                    + f" on a {ladder} site"
                )
                if not documented_by:
                    explanation += (
                        "; no work order within "
                        f"{documentation_window} days - guidelines section 5.3 "
                        "states the escalation exists on paper or it did not happen"
                    )
                    if late_evidence:
                        explanation += f" (later remediation: {late_evidence})"

                out.append(
                    (
                        f"{system_id}:{trigger_date:%Y%m%d}:{escalation_type}",
                        system_id, facility_id, observed_at, value, previous,
                        ladder, escalation_type, severity, action,
                        trigger_date + dt.timedelta(days=retest_days),
                        documented_by is not None, documented_by,
                        undocumented_days, cfg.rule_version, explanation,
                    )
                )

    bulk_insert(conn, TABLE, _COLUMNS, out)
    return len(out)
