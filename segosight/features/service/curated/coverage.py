"""Curated tier: service-coverage gaps against contracted cadence.

Coverage failures are invisible as records. `visit_status` is 'completed' on
321 of 324 visits; a site that was never serviced produces no row at all. A gap
is therefore detected as an absence -- days since the last visit measured
against the contracted interval -- not by reading a flag.

Seasonal closure is the critical false-positive guard. Guidelines section 7:
"A seasonal site showing no visits during its documented closure window is on
schedule, not neglected; the distinction lives in the contract terms, and
coverage reviews should read them before raising an alarm." Powder Basin Lodge
is 130 days past its last visit on a monthly contract and is entirely on
schedule. Jenn Fowler's April note says so directly: "That is the contract, not
us forgetting them. It trips people up every summer."

The system also records who last served the site. When that technician has
left the company, the gap has an explanation and a named owner problem --
which is exactly how Kestrel Aerospace went 70 days without a visit on a
weekly contract after Kyle Bishop's departure.
"""

from __future__ import annotations

import datetime as dt

import duckdb

from segosight.features.identity.canonical.entities import CUSTOMER_TABLE, FACILITY_TABLE
from segosight.features.identity.canonical.crosswalk import EMPLOYEE_TABLE
from segosight.features.service.canonical.visits import VISIT_TABLE
from segosight.shared.warehouse import CURATED, bulk_insert
from segosight.features.chemistry.programs import Config, SeasonalClosure, load_config

TABLE = f"{CURATED}.coverage_status"

ON_SCHEDULE = "on_schedule"
DUE = "due"
OVERDUE = "overdue"
CRITICAL = "critically_overdue"
SEASONAL_CLOSED = "seasonally_closed"
NEVER_SERVICED = "never_serviced"

_DDL = f"""
CREATE OR REPLACE TABLE {TABLE} (
    facility_id        VARCHAR NOT NULL,
    customer_id        VARCHAR,
    facility_name      VARCHAR,
    customer_name      VARCHAR,
    account_tier       VARCHAR,
    acv_usd            DOUBLE,
    service_frequency  VARCHAR,
    cadence_days       INTEGER,
    last_visit_date    DATE,
    last_visit_id      VARCHAR,
    last_technician_id VARCHAR,
    last_technician    VARCHAR,
    technician_departed BOOLEAN,
    days_since_visit   INTEGER,
    cadence_ratio      DOUBLE,
    visit_count        INTEGER,
    status             VARCHAR NOT NULL,
    seasonally_closed  BOOLEAN NOT NULL,
    as_of_date         DATE NOT NULL,
    rule_version       VARCHAR NOT NULL,
    explanation        VARCHAR
)
"""

_COLUMNS = [
    "facility_id", "customer_id", "facility_name", "customer_name",
    "account_tier", "acv_usd", "service_frequency", "cadence_days",
    "last_visit_date", "last_visit_id", "last_technician_id", "last_technician",
    "technician_departed", "days_since_visit", "cadence_ratio", "visit_count",
    "status", "seasonally_closed", "as_of_date", "rule_version", "explanation",
]


def _within_window(closure: SeasonalClosure, date: dt.date) -> bool:
    """Is `date` inside the closure window? Handles windows crossing New Year."""
    start_month, start_day = (int(p) for p in closure.closed_from.split("-"))
    end_month, end_day = (int(p) for p in closure.closed_to.split("-"))
    start = (start_month, start_day)
    end = (end_month, end_day)
    today = (date.month, date.day)
    if start <= end:
        return start <= today <= end
    return today >= start or today <= end


def as_of_default(conn: duckdb.DuckDBPyConnection) -> dt.date:
    """Latest observation in the loaded data.

    Deliberately not the system clock: results stay reproducible, and the
    system cannot know about service that happened after its data ends.
    """
    row = conn.execute(
        f"SELECT max(visit_date) FROM {VISIT_TABLE}"
    ).fetchone()
    return row[0] if row and row[0] else dt.date.today()


def build(
    conn: duckdb.DuckDBPyConnection,
    config: Config | None = None,
    as_of: dt.date | None = None,
) -> int:
    """Evaluate coverage for every facility as of a reference date."""
    cfg = config or load_config()
    reference = as_of or as_of_default(conn)
    conn.execute(_DDL)

    rows = conn.execute(
        f"""
        WITH last_visit AS (
            SELECT facility_id,
                   max(visit_date) AS last_visit_date,
                   count(*)        AS visit_count,
                   arg_max(visit_id, visit_date)     AS last_visit_id,
                   arg_max(technician_id, visit_date) AS last_technician_id
            FROM {VISIT_TABLE}
            WHERE visit_date IS NOT NULL
            GROUP BY facility_id
        )
        SELECT f.facility_id, f.customer_id, f.facility_name, c.customer_name,
               c.account_tier, c.acv_usd, f.service_frequency,
               v.last_visit_date, v.last_visit_id, v.last_technician_id,
               e.display_name, e.departed_on, v.visit_count
        FROM {FACILITY_TABLE} f
        LEFT JOIN {CUSTOMER_TABLE} c USING (customer_id)
        LEFT JOIN last_visit v ON v.facility_id = f.facility_id
        LEFT JOIN {EMPLOYEE_TABLE} e ON e.employee_id = v.last_technician_id
        ORDER BY f.facility_id
        """
    ).fetchall()

    overdue_factor = float(cfg.thresholds["overdue_factor"])
    critical_factor = float(cfg.thresholds["critical_factor"])

    out = []
    for (
        facility_id, customer_id, facility_name, customer_name, tier, acv,
        frequency, last_date, last_visit_id, technician_id, technician_name,
        departed_on, visit_count,
    ) in rows:
        cadence = cfg.cadence_for(frequency)
        closure = cfg.seasonal.get(facility_id)
        closed_now = closure is not None and _within_window(closure, reference)

        days = (reference - last_date).days if last_date else None
        ratio = (days / cadence) if (days is not None and cadence) else None

        departed = bool(departed_on) and (
            last_date is not None and last_date >= dt.date.fromisoformat(str(departed_on))
            or bool(departed_on)
        )

        if last_date is None:
            status = NEVER_SERVICED
            explanation = "no visit recorded in the loaded data"
        elif closed_now:
            status = SEASONAL_CLOSED
            explanation = (
                f"{days} days since last visit, but the site is within its "
                f"documented closure window ({closure.closed_from} to "
                f"{closure.closed_to}); on schedule, not neglected"
            )
        elif ratio is None:
            status = ON_SCHEDULE
            explanation = f"cadence not recognised from {frequency!r}"
        elif ratio >= critical_factor:
            status = CRITICAL
            explanation = (
                f"{days} days since last visit on a {frequency} contract "
                f"({ratio:.1f}x the {cadence}-day cadence)"
            )
        elif ratio >= overdue_factor:
            status = OVERDUE
            explanation = (
                f"{days} days since last visit on a {frequency} contract "
                f"({ratio:.1f}x the {cadence}-day cadence)"
            )
        elif ratio >= 1.0:
            status = DUE
            explanation = f"{days} days since last visit; next service due"
        else:
            status = ON_SCHEDULE
            explanation = f"{days} days since last visit, within cadence"

        if status in (OVERDUE, CRITICAL) and departed_on:
            explanation += (
                f"; last served by {technician_name}, who left on {departed_on}"
            )

        out.append(
            (
                facility_id, customer_id, facility_name, customer_name, tier,
                acv, frequency, cadence, last_date, last_visit_id, technician_id,
                technician_name, bool(departed_on), days, ratio,
                visit_count or 0, status, closed_now, reference,
                cfg.rule_version, explanation,
            )
        )

    bulk_insert(conn, TABLE, _COLUMNS, out)
    return len(out)
