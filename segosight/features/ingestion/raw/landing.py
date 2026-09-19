"""Raw tier: immutable landing of source rows.

Responsibilities, per the tiering convention: land payloads immutably with
source path, ingestion timestamp, batch sequence and a content hash, preserving
original timestamps, names, identifiers, units and malformed values exactly as
they arrived.

Explicitly NOT done here: no deduplication, no unit fixing, no dropping of
suspicious records, no correction resolution. A row that is wrong lands
verbatim and is judged downstream.

Values are preserved as text exactly as exported; the one normalization the
reader imposes is that an empty CSV field lands as JSON null rather than an
empty string, so absence is represented uniformly across payloads.

Rows are stored as JSON payloads rather than typed columns so that schema drift
-- the FieldFlow export adding `source_system` -- needs no migration. The load
runs inside DuckDB via `read_csv(all_varchar=true)` rather than row-by-row from
Python: per-statement round-trip overhead dominates otherwise (~1.3ms each,
turning a 2,200-row load into a 70-second one), and `all_varchar` guarantees no
type inference mangles a value on the way in.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from pathlib import Path

import duckdb

from segosight.shared.warehouse import RAW
from segosight.features.ingestion.registry import Registry, SourceFile, load_registry

TABLE = f"{RAW}.records"
SCHEMA_TABLE = f"{RAW}.schema_observations"

#: Field separator used when building the content hash. Unit Separator cannot
#: occur in the source text, so field boundaries stay unambiguous.
_SEP = "chr(31)"

_DDL = f"""
CREATE TABLE IF NOT EXISTS {TABLE} (
    row_hash          VARCHAR NOT NULL,
    entity            VARCHAR NOT NULL,
    batch_name        VARCHAR NOT NULL,
    batch_sequence    INTEGER NOT NULL,
    source_system     VARCHAR NOT NULL,
    source_file       VARCHAR NOT NULL,
    source_row_number BIGINT  NOT NULL,
    business_key      VARCHAR NOT NULL,
    payload           VARCHAR NOT NULL,
    ingested_at       TIMESTAMP NOT NULL
);
CREATE TABLE IF NOT EXISTS {SCHEMA_TABLE} (
    entity      VARCHAR NOT NULL,
    batch_name  VARCHAR NOT NULL,
    source_file VARCHAR NOT NULL,
    columns     VARCHAR NOT NULL,
    observed_at TIMESTAMP NOT NULL
);
"""


@dataclass(frozen=True)
class LoadResult:
    entity: str
    batch: str
    source_file: str
    rows_read: int
    rows_inserted: int
    #: Columns present here but not in this entity's first-seen file.
    added_columns: tuple[str, ...] = ()
    missing_columns: tuple[str, ...] = ()

    @property
    def rows_skipped(self) -> int:
        """Rows already present, i.e. an idempotent re-run."""
        return self.rows_read - self.rows_inserted


def ensure_schema(conn: duckdb.DuckDBPyConnection) -> None:
    for statement in _DDL.strip().split(";"):
        if statement.strip():
            conn.execute(statement)


def _quote(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _literal(text: str) -> str:
    return "'" + str(text).replace("'", "''") + "'"


def _columns_of(conn: duckdb.DuckDBPyConnection, path: Path) -> list[str]:
    return [
        row[0]
        for row in conn.execute(
            f"DESCRIBE SELECT * FROM read_csv({_literal(str(path))}, "
            f"all_varchar=true, header=true)"
        ).fetchall()
    ]


def _detect_drift(
    conn: duckdb.DuckDBPyConnection, source: SourceFile, columns: list[str]
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Compare this file's columns against the entity's first-seen shape."""
    baseline = conn.execute(
        f"""SELECT columns FROM {SCHEMA_TABLE}
            WHERE entity = ? ORDER BY observed_at LIMIT 1""",
        [source.entity.name],
    ).fetchone()
    if baseline is None:
        return (), ()
    known = set(baseline[0].split(","))
    return (
        tuple(sorted(set(columns) - known)),
        tuple(sorted(known - set(columns))),
    )


def land_file(
    conn: duckdb.DuckDBPyConnection,
    source: SourceFile,
    *,
    ingested_at: dt.datetime | None = None,
) -> LoadResult:
    """Land one source file into the raw tier. Safe to re-run."""
    ensure_schema(conn)
    stamp = ingested_at or dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)

    columns = _columns_of(conn, source.path)
    added, missing = _detect_drift(conn, source, columns)

    # Business key columns absent from this file yield empty segments rather
    # than failing the load; the resulting blank key is visible downstream.
    key_expr = ", ".join(
        f"coalesce(r.{_quote(col)}, '')" if col in columns else "''"
        for col in source.entity.business_key
    )
    key_sql = f"concat_ws('|', {key_expr})"

    read = (
        f"read_csv({_literal(str(source.path))}, all_varchar=true, header=true)"
    )
    # DuckDB returns the affected-row count as the INSERT's result.
    inserted = conn.execute(
        f"""
        INSERT INTO {TABLE}
        WITH scanned AS (
            SELECT
                {key_sql}                                   AS business_key,
                to_json(r)                                  AS payload,
                row_number() OVER ()                        AS source_row_number
            FROM {read} r
        ),
        hashed AS (
            SELECT
                sha256(concat_ws({_SEP},
                    {_literal(source.entity.name)},
                    {_literal(source.batch.name)},
                    business_key,
                    payload))                               AS row_hash,
                *
            FROM scanned
        )
        SELECT
            h.row_hash,
            {_literal(source.entity.name)},
            {_literal(source.batch.name)},
            {source.batch.sequence},
            {_literal(source.source_system)},
            {_literal(str(source.path))},
            h.source_row_number,
            h.business_key,
            h.payload,
            ?
        FROM hashed h
        WHERE NOT EXISTS (
            SELECT 1 FROM {TABLE} t WHERE t.row_hash = h.row_hash
        )
        """,
        [stamp],
    ).fetchone()[0]

    rows_read = conn.execute(f"SELECT count(*) FROM {read}").fetchone()[0]

    conn.execute(
        f"INSERT INTO {SCHEMA_TABLE} VALUES (?,?,?,?,?)",
        [
            source.entity.name,
            source.batch.name,
            str(source.path),
            ",".join(columns),
            stamp,
        ],
    )

    return LoadResult(
        entity=source.entity.name,
        batch=source.batch.name,
        source_file=source.path.name,
        rows_read=rows_read,
        rows_inserted=inserted,
        added_columns=added,
        missing_columns=missing,
    )


def land_all(
    conn: duckdb.DuckDBPyConnection,
    registry: Registry | None = None,
    root: Path | None = None,
) -> list[LoadResult]:
    """Land every file the registry resolves, in batch-sequence order."""
    reg = registry or load_registry()
    return [land_file(conn, source) for source in reg.all_files(root)]
