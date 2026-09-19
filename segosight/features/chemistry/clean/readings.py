"""Clean tier: water readings exploded into long/narrow measurement events.

One source row becomes one row per populated parameter. This is the grain the
Ontology design calls for, and the source forces it: the `units` column carries
a unit *per parameter*, so a wide row cannot hold the correct `raw_unit` for
each of its columns.

Both raw and normalized values are preserved on every row. Conversion happens
only where the source declared a unit, so an undeclared value is carried
through unconverted and flagged rather than silently rescaled.

Superseded versions are retained with `is_current = false`. Trend and
control-limit queries filter on `is_current AND quality_status = 'valid'`;
audit and compliance views read everything.
"""

from __future__ import annotations

import json

import duckdb

from segosight.shared.normalize import codes
from segosight.shared.normalize.actors import resolve_actor
from segosight.shared.normalize.numeric import parse_number
from segosight.features.chemistry.quality import assess, parse_dipslide
from segosight.shared.normalize.temporal import parse_timestamp
from segosight.features.chemistry.units import (
    COLUMN_SPECS,
    PARAMETERS,
    convert,
    parse_units_declaration,
    resolve_parameter,
)
from segosight.shared.warehouse import CLEAN, bulk_insert
from segosight.features.ingestion.clean.versioning import TABLE as VERSIONS

TABLE = f"{CLEAN}.water_readings_long"

#: Column order, matching the tuple produced by `_emit`.
_COLUMNS = [
    "reading_event_id", "reading_id", "source_system_ref", "observed_at",
    "observed_at_raw", "date_format", "parameter_code", "raw_value",
    "raw_value_text", "raw_unit", "normalized_value", "standard_unit",
    "was_converted", "collection_method", "collected_by_raw",
    "collected_by_actor", "quality_status", "quality_issues", "notes",
    "is_current", "batch_name", "batch_sequence", "source_file",
    "source_row_number", "row_hash",
]

_DDL = f"""
CREATE OR REPLACE TABLE {TABLE} (
    reading_event_id   VARCHAR PRIMARY KEY,
    reading_id         VARCHAR NOT NULL,
    source_system_ref  VARCHAR,
    observed_at        TIMESTAMP,
    observed_at_raw    VARCHAR,
    date_format        VARCHAR,
    parameter_code     VARCHAR NOT NULL,
    raw_value          DOUBLE,
    raw_value_text     VARCHAR,
    raw_unit           VARCHAR,
    normalized_value   DOUBLE,
    standard_unit      VARCHAR,
    was_converted      BOOLEAN,
    collection_method  VARCHAR,
    collected_by_raw   VARCHAR,
    collected_by_actor VARCHAR,
    quality_status     VARCHAR NOT NULL,
    quality_issues     VARCHAR NOT NULL,
    notes              VARCHAR,
    is_current         BOOLEAN NOT NULL,
    batch_name         VARCHAR NOT NULL,
    batch_sequence     INTEGER NOT NULL,
    source_file        VARCHAR NOT NULL,
    source_row_number  INTEGER NOT NULL,
    row_hash           VARCHAR NOT NULL
)
"""


def _emit(row: dict, meta: dict, parameter, raw_text, raw_unit, value, extra_issues):
    """Build one long-form row for a single parameter."""
    converted = convert(parameter, value, raw_unit)
    status, quality_issues = assess(parameter.code, converted.value)

    issues = tuple(
        dict.fromkeys(tuple(extra_issues) + converted.issues + quality_issues)
    )
    # An unresolved unit means the number is not comparable to its peers, so it
    # must not silently join a trend series.
    if status == codes.VALID and (
        codes.UNIT_NOT_DECLARED in issues or codes.UNIT_UNRECOGNIZED in issues
    ):
        status = codes.UNRESOLVED

    return (
        f"{row['reading_id']}:{parameter.code}:{meta['row_hash'][:12]}",
        row["reading_id"],
        row.get("system_id"),
        meta["observed_at"],
        row.get("timestamp"),
        meta["date_format"],
        parameter.code,
        converted.value if converted.value is not None else None,
        raw_text,
        raw_unit,
        converted.value,
        parameter.standard_unit,
        bool(converted.detail.get("converted", False)),
        row.get("collection_method"),
        row.get("collected_by"),
        meta["actor"],
        status,
        json.dumps(list(issues)),
        row.get("notes") or None,
        meta["is_current"],
        meta["batch_name"],
        meta["batch_sequence"],
        meta["source_file"],
        meta["source_row_number"],
        meta["row_hash"],
    )


def build(conn: duckdb.DuckDBPyConnection, corpus=None) -> int:
    """Explode current and superseded reading rows into the long table."""
    conn.execute(_DDL)

    versions = conn.execute(
        f"""
        SELECT payload, is_current, batch_name, batch_sequence,
               source_file, source_row_number, row_hash
        FROM {VERSIONS}
        WHERE entity = 'water_readings'
        ORDER BY batch_sequence, source_row_number
        """
    ).fetchall()

    out = []
    for payload, is_current, batch, seq, src_file, src_row, row_hash in versions:
        row = json.loads(payload)
        stamp = parse_timestamp(row.get("timestamp"), corpus=corpus)
        actor = resolve_actor(row.get("collected_by"))
        declaration = parse_units_declaration(row.get("units"))

        meta = {
            "observed_at": stamp.value,
            "date_format": stamp.detail.get("format"),
            "actor": actor.value.actor_id if actor.value else None,
            "is_current": bool(is_current),
            "batch_name": batch,
            "batch_sequence": seq,
            "source_file": src_file,
            "source_row_number": src_row,
            "row_hash": row_hash,
        }

        for spec in COLUMN_SPECS:
            raw_text = row.get(spec.column)
            if raw_text is None or str(raw_text).strip() == "":
                continue
            number = parse_number(raw_text)
            resolution = resolve_parameter(spec.column, declaration)
            out.append(
                _emit(
                    row, meta, resolution.parameter, raw_text,
                    resolution.raw_unit, number.value,
                    resolution.issues + number.issues + stamp.issues,
                )
            )

        # Dipslide is semi-quantitative and never unit-declared; it is stored
        # as its base-10 exponent so the 10^4 / 10^5 ladder compares numerically.
        dip_raw = row.get("microbio_dipslide")
        if dip_raw and str(dip_raw).strip():
            dip = parse_dipslide(dip_raw)
            out.append(
                _emit(
                    row, meta, PARAMETERS["dipslide"], dip_raw,
                    "log10 CFU/ml" if dip.value is not None else None,
                    dip.value, dip.issues + stamp.issues,
                )
            )

    bulk_insert(conn, TABLE, _COLUMNS, out)
    return conn.execute(f"SELECT count(*) FROM {TABLE}").fetchone()[0]
