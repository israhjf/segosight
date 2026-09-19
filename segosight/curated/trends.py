"""Curated tier: sustained-trend detection (guidelines section 4.2).

"A parameter moving steadily in one direction across three or more consecutive
services indicates an active mechanism, and the time to investigate is at the
trend stage, not at the limit. This applies even when every individual reading
is inside its band."

That sentence is the product. On SYS-0006 the field iron series climbs from
0.19 to 1.50 ppm over six months and never reaches the 2.0 ppm action level;
the boiler failed on 2026-09-02 with oxygen pitting, at a cost of $41,800. A
strict three-consecutive-services rule fires on 2026-04-07, 148 days earlier.

Two deliberate constraints:

* Trends run *within* a measurement series, which is system x parameter x
  collection method. The contract lab reads iron on SYS-0006 at 0.14-0.51 ppm
  while the field reads 0.19-1.50 on the same equipment; pooling them flattens
  the signal.
* BMS feeds are resampled to a weekly median before evaluation. Section 4.2
  counts "consecutive services", and three consecutive rising days on a tower
  is noise -- evaluating raw daily samples would bury the real findings.

A run is emitted as evidence, not as an alert. Alert lifecycle and dedup are
handled downstream so a sawtooth series does not open and close an alert
repeatedly.
"""

from __future__ import annotations

import collections
import datetime as dt
import statistics

import duckdb

from ..canonical.events import TABLE as EVENTS
from ..warehouse import CURATED, bulk_insert
from .assessments import TABLE as ASSESSMENTS
from .programs import Config, load_config

TABLE = f"{CURATED}.trend_signal"

#: Collection methods delivering high-frequency telemetry rather than services.
HIGH_FREQUENCY_METHODS = frozenset({"bms"})

#: Parameters where a sustained move is operationally meaningful. Restricting
#: the set keeps the alert queue honest: a drifting pH on a boiler is noise,
#: a climbing iron is corrosion.
TRENDED_PARAMETERS = frozenset(
    {"iron", "conductivity", "free_halogen", "inhibitor", "molybdate", "nitrite", "sulfite"}
)

#: Direction that constitutes a concern, per parameter.
#: "rising" -- accumulation or fouling; "falling" -- residual being consumed.
CONCERNING_DIRECTION = {
    "iron": "rising",
    "conductivity": "rising",
    "free_halogen": "falling",
    "inhibitor": "falling",
    "molybdate": "falling",
    "nitrite": "falling",
    "sulfite": "falling",
}

_DDL = f"""
CREATE OR REPLACE TABLE {TABLE} (
    trend_id           VARCHAR NOT NULL,
    measurement_series_id VARCHAR NOT NULL,
    system_id          VARCHAR,
    facility_id        VARCHAR,
    parameter_code     VARCHAR NOT NULL,
    collection_method  VARCHAR,
    treatment_program  VARCHAR,
    direction          VARCHAR NOT NULL,
    is_concerning      BOOLEAN NOT NULL,
    run_length         INTEGER NOT NULL,
    started_at         TIMESTAMP,
    ended_at           TIMESTAMP,
    first_value        DOUBLE,
    last_value         DOUBLE,
    net_change         DOUBLE,
    pct_change         DOUBLE,
    standard_unit      VARCHAR,
    all_within_band    BOOLEAN,
    sample_grain       VARCHAR NOT NULL,
    rule_version       VARCHAR NOT NULL,
    explanation        VARCHAR
)
"""

_COLUMNS = [
    "trend_id", "measurement_series_id", "system_id", "facility_id",
    "parameter_code", "collection_method", "treatment_program", "direction",
    "is_concerning", "run_length", "started_at", "ended_at", "first_value",
    "last_value", "net_change", "pct_change", "standard_unit",
    "all_within_band", "sample_grain", "rule_version", "explanation",
]


def _week_start(moment: dt.datetime) -> dt.datetime:
    date = moment.date()
    return dt.datetime.combine(date - dt.timedelta(days=date.weekday()), dt.time())


def resample_weekly(points: list[tuple]) -> list[tuple]:
    """Collapse high-frequency points to one median value per ISO week.

    The median, not the mean, so a single dropout or spike cannot drag a week.
    """
    buckets: dict[dt.datetime, list[float]] = collections.defaultdict(list)
    for moment, value in points:
        buckets[_week_start(moment)].append(value)
    return [(week, statistics.median(values)) for week, values in sorted(buckets.items())]


def find_runs(points: list[tuple], minimum: int) -> list[tuple]:
    """Maximal runs of strictly monotonic values of at least `minimum` length.

    Returns (direction, start_index, end_index) with indices inclusive.
    """
    runs = []
    if len(points) < minimum:
        return runs

    start = 0
    direction = None
    for index in range(1, len(points)):
        previous, current = points[index - 1][1], points[index][1]
        step = "rising" if current > previous else "falling" if current < previous else None
        if step is not None and step == direction:
            continue
        # Direction changed or flattened: close the open run.
        if direction is not None and index - start >= minimum:
            runs.append((direction, start, index - 1))
        direction = step
        start = index - 1 if step is not None else index

    if direction is not None and len(points) - start >= minimum:
        runs.append((direction, start, len(points) - 1))
    return runs


def build(conn: duckdb.DuckDBPyConnection, config: Config | None = None) -> int:
    """Detect sustained trends across every eligible measurement series."""
    cfg = config or load_config()
    minimum = int(cfg.thresholds.get("trend_min_run", 3))
    conn.execute(_DDL)

    rows = conn.execute(
        f"""
        SELECT e.measurement_series_id, e.system_id, e.facility_id,
               e.parameter_code, e.collection_method, e.treatment_program,
               e.observed_at, e.normalized_value, e.standard_unit,
               coalesce(a.out_of_band, false) AS out_of_band
        FROM {EVENTS} e
        LEFT JOIN {ASSESSMENTS} a USING (reading_event_id)
        WHERE e.alert_eligible AND e.normalized_value IS NOT NULL
          AND e.observed_at IS NOT NULL
          AND e.parameter_code IN ({','.join(f"'{p}'" for p in sorted(TRENDED_PARAMETERS))})
        ORDER BY e.measurement_series_id, e.observed_at
        """
    ).fetchall()

    series: dict[str, dict] = {}
    for row in rows:
        entry = series.setdefault(
            row[0],
            {
                "system_id": row[1], "facility_id": row[2], "parameter": row[3],
                "method": row[4], "program": row[5], "unit": row[8],
                "points": [], "out_of_band": {},
            },
        )
        entry["points"].append((row[6], row[7]))
        entry["out_of_band"][row[6]] = row[9]

    out = []
    for series_id, entry in series.items():
        grain = "service"
        points = entry["points"]
        if entry["method"] in HIGH_FREQUENCY_METHODS:
            points = resample_weekly(points)
            grain = "weekly_median"

        concerning_direction = CONCERNING_DIRECTION.get(entry["parameter"])
        for direction, start, end in find_runs(points, minimum):
            first_value, last_value = points[start][1], points[end][1]
            net = last_value - first_value
            pct = (net / first_value * 100) if first_value else None
            within = (
                all(
                    not entry["out_of_band"].get(moment, False)
                    for moment, _ in points[start : end + 1]
                )
                if grain == "service"
                else None
            )
            run_length = end - start + 1
            is_concerning = direction == concerning_direction

            explanation = (
                f"{entry['parameter']} {direction} across {run_length} consecutive "
                f"{'services' if grain == 'service' else 'weeks'}: "
                f"{first_value:g} to {last_value:g} {entry['unit']}"
            )
            if within:
                explanation += " (every reading inside its band)"

            out.append(
                (
                    f"{series_id}:{points[start][0]:%Y%m%d}:{direction}",
                    series_id, entry["system_id"], entry["facility_id"],
                    entry["parameter"], entry["method"], entry["program"],
                    direction, is_concerning, run_length,
                    points[start][0], points[end][0], first_value, last_value,
                    net, pct, entry["unit"], within, grain, cfg.rule_version,
                    explanation,
                )
            )

    bulk_insert(conn, TABLE, _COLUMNS, out)
    return len(out)
