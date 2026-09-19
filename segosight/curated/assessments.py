"""Curated tier: control-limit evaluation into ReadingAssessment.

Evaluation is program-aware, never generic. Guidelines section 6.2 warns that
readings "comfortably normal on a standard boiler are serious exceedances on an
HP unit", and section 6.1 that conductivity between 1,800 and 3,400 on a
formally enrolled CT-HC2 tower "is not an exceedance and must not be reported
to the customer as one".

The CT-HC2 conditional band is evaluated against system state, not against a
single row. The wide 2,400-3,400 band applies while chloride stays below
300 ppm and CT-785 inhibitor stays at or above 12 ppm. Those are established by
field tests; a BMS telemetry point measures conductivity alone and cannot
re-prove them. Conditions therefore carry forward from the most recent field
sample that measured them, within `condition_validity_days`.

The distinction between *failed* and *unconfirmed* matters. Section 6.1 says a
system "reverts to CT-STD limits" when a condition fails -- that means measured
and out of range. An unmeasured condition is not a failure, and section 6.1 is
explicit that conductivity between 1,800 and 3,400 on an HC2 tower "must not be
reported to the customer as one". Unconfirmed conditions therefore yield
`not_evaluated`, never an exceedance.

Assessment is kept separate from the raw reading, per the design: validity and
interpretation live here, evidence stays in canonical.reading_event.
"""

from __future__ import annotations

import bisect
import collections

import duckdb

from ..canonical.events import TABLE as EVENTS
from ..warehouse import CURATED, bulk_insert
from .programs import Config, Limit, load_config

TABLE = f"{CURATED}.reading_assessment"

IN_BAND = "in_band"
BELOW_BAND = "below_band"
ABOVE_BAND = "above_band"
ACTION_LEVEL = "action_level_exceeded"
BELOW_TARGET = "below_target"
NOT_EVALUATED = "not_evaluated"

_DDL = f"""
CREATE OR REPLACE TABLE {TABLE} (
    reading_event_id  VARCHAR NOT NULL,
    reading_id        VARCHAR NOT NULL,
    system_id         VARCHAR,
    facility_id       VARCHAR,
    observed_at       TIMESTAMP,
    parameter_code    VARCHAR NOT NULL,
    normalized_value  DOUBLE,
    standard_unit     VARCHAR,
    governing_program VARCHAR,
    applied_lower     DOUBLE,
    applied_upper     DOUBLE,
    limit_kind        VARCHAR,
    band_source       VARCHAR,
    status            VARCHAR NOT NULL,
    out_of_band       BOOLEAN NOT NULL,
    severity          VARCHAR NOT NULL,
    explanation       VARCHAR,
    rule_version      VARCHAR NOT NULL,
    collection_method VARCHAR,
    measurement_series_id VARCHAR
)
"""

_COLUMNS = [
    "reading_event_id", "reading_id", "system_id", "facility_id", "observed_at",
    "parameter_code", "normalized_value", "standard_unit", "governing_program",
    "applied_lower", "applied_upper", "limit_kind", "band_source", "status",
    "out_of_band", "severity", "explanation", "rule_version",
    "collection_method", "measurement_series_id",
]


#: Outcomes of checking a conditional band's prerequisites.
HOLDS = "holds"
FAILED = "failed"
UNCONFIRMED = "unconfirmed"


def _conditions_hold(limit: Limit, state: dict[str, tuple]) -> tuple[str, str]:
    """Check a conditional band's prerequisites against carried-forward state.

    `state` maps parameter -> (value, age_in_days). Returns one of HOLDS,
    FAILED or UNCONFIRMED with a human explanation. FAILED means a condition
    was measured and is out of range; UNCONFIRMED means it was never measured
    or is too stale to rely on, which is not the same thing.
    """
    unconfirmed = []
    for condition in limit.requires:
        parameter = condition["parameter"]
        entry = state.get(parameter)
        if entry is None:
            unconfirmed.append(f"{parameter} not measured")
            continue
        value, age = entry
        if "upper" in condition and value > condition["upper"]:
            return FAILED, (
                f"{parameter} {value:g} exceeds {condition['upper']:g} "
                f"(measured {age}d ago)"
            )
        if "lower" in condition and value < condition["lower"]:
            return FAILED, (
                f"{parameter} {value:g} below {condition['lower']:g} "
                f"(measured {age}d ago)"
            )
    if unconfirmed:
        return UNCONFIRMED, "; ".join(unconfirmed)
    return HOLDS, "chloride and inhibitor confirmed in range"


def _resolve_band(
    config: Config, program: str, parameter: str, system_id: str, state: dict
) -> tuple[Limit | None, str, str]:
    """Pick the governing band, honouring conditional programs and exceptions.

    Returns (limit, band_source, explanation_prefix).
    """
    prog = config.programs.get(program)

    if prog is not None:
        for conditional in prog.conditional:
            if conditional.parameter != parameter:
                continue
            outcome, why = _conditions_hold(conditional, state)
            if outcome == HOLDS:
                return (
                    conditional,
                    f"{program}:conditional",
                    f"{program} conditional band applies ({why})",
                )
            if outcome == FAILED and prog.fallback_program:
                fallback = config.limit_for(prog.fallback_program, parameter, system_id)
                return (
                    fallback,
                    f"{prog.fallback_program}:fallback",
                    f"{program} conditional band withdrawn ({why}); "
                    f"reverted to {prog.fallback_program}",
                )
            # Unconfirmed is not failure. Reporting an exceedance here would
            # breach section 6.1.
            return (
                None,
                f"{program}:unconfirmed",
                f"{program} conditional band cannot be confirmed ({why}); "
                f"not reported as an exceedance per section 6.1",
            )

    limit = config.limit_for(program, parameter, system_id)
    if limit is None:
        return None, "none", f"no {parameter} limit defined for {program}"
    if (system_id, parameter) in config.exceptions:
        exc = config.exceptions[(system_id, parameter)]
        return limit, f"{program}:exception", f"section 6.3 exception applies ({exc.reason})"
    return limit, program, ""


def _evaluate(limit: Limit, value: float, config: Config, system_id: str, parameter: str):
    """Classify a value against its band. Returns (status, severity, detail)."""
    if limit.kind == "trend_only":
        return NOT_EVALUATED, "none", "recorded for trend; no fixed limit"

    if limit.upper is not None and value > limit.upper:
        if limit.kind == "action_level":
            return ACTION_LEVEL, "high", f"{value:g} exceeds action level {limit.upper:g}"
        return ABOVE_BAND, "medium", f"{value:g} above upper limit {limit.upper:g}"

    if limit.lower is not None and value < limit.lower:
        return BELOW_BAND, "medium", f"{value:g} below lower limit {limit.lower:g}"

    # Section 6.3: between the contract floor and the tooling target is
    # compliant but earns a top-up, not an exceedance.
    exc = config.exceptions.get((system_id, parameter))
    if exc is not None and value < exc.target_lower:
        return (
            BELOW_TARGET,
            "low",
            f"{value:g} is compliant (floor {exc.contract_lower:g}) but below the "
            f"{exc.target_lower:g} tooling target; top up at this visit",
        )

    return IN_BAND, "none", "within band"


def build(conn: duckdb.DuckDBPyConnection, config: Config | None = None) -> int:
    """Assess every alert-eligible reading against its governing program."""
    cfg = config or load_config()
    conn.execute(_DDL)

    rows = conn.execute(
        f"""
        SELECT reading_event_id, reading_id, system_id, facility_id, observed_at,
               parameter_code, normalized_value, standard_unit, treatment_program,
               collection_method, measurement_series_id
        FROM {EVENTS}
        WHERE alert_eligible AND normalized_value IS NOT NULL
        ORDER BY observed_at
        """
    ).fetchall()

    # Conditional bands depend on parameters a telemetry row does not carry, so
    # build a per-system timeline of condition-bearing measurements and carry
    # the most recent one forward to each observation.
    condition_parameters = {
        condition["parameter"]
        for program in cfg.programs.values()
        for limit in program.conditional
        for condition in limit.requires
    }
    validity_days = int(cfg.thresholds.get("condition_validity_days", 45))

    timeline: dict[tuple[str, str], list[tuple]] = collections.defaultdict(list)
    for row in rows:
        system_id, observed_at, parameter, value = row[2], row[4], row[5], row[6]
        if parameter in condition_parameters and observed_at is not None:
            timeline[(system_id, parameter)].append((observed_at, value))
    for key in timeline:
        timeline[key].sort()

    def state_at(system_id: str, observed_at) -> dict[str, tuple]:
        """Condition parameters known for this system as of `observed_at`."""
        known: dict[str, tuple] = {}
        if observed_at is None:
            return known
        for parameter in condition_parameters:
            series = timeline.get((system_id, parameter))
            if not series:
                continue
            index = bisect.bisect_right(series, (observed_at, float("inf"))) - 1
            if index < 0:
                continue
            measured_at, value = series[index]
            age = (observed_at - measured_at).days
            if age <= validity_days:
                known[parameter] = (value, age)
        return known

    out = []
    for (
        event_id, reading_id, system_id, facility_id, observed_at, parameter,
        value, unit, program, method, series_id,
    ) in rows:
        limit, band_source, prefix = _resolve_band(
            cfg, program, parameter, system_id, state_at(system_id, observed_at)
        )

        if limit is None:
            status, severity, detail = NOT_EVALUATED, "none", prefix
            lower = upper = None
            kind = None
        else:
            status, severity, detail = _evaluate(
                limit, value, cfg, system_id, parameter
            )
            lower, upper, kind = limit.lower, limit.upper, limit.kind

        explanation = f"{prefix}; {detail}" if prefix else detail
        out.append(
            (
                event_id, reading_id, system_id, facility_id, observed_at,
                parameter, value, unit, program, lower, upper, kind, band_source,
                status, status in (BELOW_BAND, ABOVE_BAND, ACTION_LEVEL),
                severity, explanation, cfg.rule_version, method, series_id,
            )
        )

    bulk_insert(conn, TABLE, _COLUMNS, out)
    return len(out)
