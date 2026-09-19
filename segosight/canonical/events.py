"""Canonical tier: reading events with resolved identity and series identity.

Lab uploads write the contract laboratory's own sample-point codes into the
`system_id` column (BONF-OGD-B2, MRMC-B1, ...). Without resolution those 36
readings orphan against systems.csv. Here they are mapped through the governed
crosswalk, and the confidence of that mapping travels with the row.

Measurement series identity is `system x parameter x collection_method`.
Separating by collection method is deliberate: on SYS-0006 the contract lab
reads iron at 0.14-0.51 ppm while the field reads 0.19-1.50 ppm on the same
equipment and the same days. Pooling them flattens the corrosion trend that
preceded a tube failure. Guidelines section 10 says to resolve units, sample
point and timing before concluding the water changed -- so the series keeps
them apart and lets an analyst compare them explicitly.

`alert_eligible` is false when a row only reaches its system through a
medium-confidence mapping, or when its own chemistry is not trustworthy.
"""

from __future__ import annotations

import duckdb

from ..clean.readings import TABLE as LONG
from ..warehouse import CANONICAL
from .entities import SYSTEM_TABLE
from .identity import confidence_sql, resolve_sql

TABLE = f"{CANONICAL}.reading_event"
SERIES_TABLE = f"{CANONICAL}.measurement_series"


def build(conn: duckdb.DuckDBPyConnection) -> int:
    """Materialize resolved reading events and their series metadata."""
    resolved = resolve_sql("sample_point", "l.source_system_ref")
    confidence = confidence_sql("sample_point", "l.source_system_ref")

    conn.execute(
        f"""
        CREATE OR REPLACE TABLE {TABLE} AS
        WITH resolved AS (
            SELECT
                l.*,
                {resolved}   AS system_id,
                {confidence} AS system_id_confidence,
                (l.source_system_ref <> {resolved}) AS system_id_was_aliased
            FROM {LONG} l
        )
        SELECT
            r.reading_event_id,
            r.reading_id,
            r.system_id,
            r.source_system_ref,
            r.system_id_was_aliased,
            r.system_id_confidence,
            s.facility_id,
            s.treatment_program,
            s.criticality,
            s.system_type,
            s.status AS system_status,
            r.observed_at,
            r.parameter_code,
            r.raw_value_text,
            r.raw_unit,
            r.normalized_value,
            r.standard_unit,
            r.was_converted,
            r.collection_method,
            r.collected_by_actor,
            concat_ws(':', r.system_id, r.parameter_code, r.collection_method)
                AS measurement_series_id,
            r.quality_status,
            r.quality_issues,
            -- A reading may drive an alert only when its chemistry is sound,
            -- it is the version in force, and its identity is not in doubt.
            (r.quality_status = 'valid'
             AND r.is_current
             AND r.system_id_confidence IN ('direct', 'high')
             AND s.system_id IS NOT NULL) AS alert_eligible,
            r.is_current,
            r.notes,
            r.batch_name,
            r.source_file,
            r.row_hash
        FROM resolved r
        LEFT JOIN {SYSTEM_TABLE} s ON s.system_id = r.system_id
        """
    )

    conn.execute(
        f"""
        CREATE OR REPLACE TABLE {SERIES_TABLE} AS
        SELECT
            measurement_series_id,
            any_value(system_id)        AS system_id,
            any_value(facility_id)      AS facility_id,
            any_value(parameter_code)   AS parameter_code,
            any_value(collection_method) AS collection_method,
            any_value(standard_unit)    AS standard_unit,
            any_value(treatment_program) AS treatment_program,
            count(*)                    AS observation_count,
            count(*) FILTER (WHERE alert_eligible) AS eligible_count,
            min(observed_at)            AS first_observed_at,
            max(observed_at)            AS last_observed_at,
            count(DISTINCT raw_unit)    AS distinct_raw_units
        FROM {TABLE}
        WHERE is_current
        GROUP BY measurement_series_id
        """
    )

    return conn.execute(f"SELECT count(*) FROM {TABLE}").fetchone()[0]
