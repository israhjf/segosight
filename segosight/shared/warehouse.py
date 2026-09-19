"""DuckDB warehouse connection and tier schema.

Tiers follow the layered convention in the Ontology design: immutable source
evidence (raw), standardized/reconciled data (clean), and consumer-ready
serving tables. Each tier is a DuckDB schema so a query makes its provenance
obvious.
"""

from __future__ import annotations

import os
from pathlib import Path

import duckdb

from segosight.shared.paths import REPO_ROOT

RAW = "raw"
CLEAN = "clean"
CANONICAL = "canonical"
CURATED = "curated"
TIERS = (RAW, CLEAN, CANONICAL, CURATED)


def warehouse_path() -> Path:
    override = os.environ.get("SEGOSIGHT_WAREHOUSE")
    if override:
        return Path(override)
    return REPO_ROOT / "warehouse" / "segosight.duckdb"


def connect(path: Path | str | None = None) -> duckdb.DuckDBPyConnection:
    """Open the warehouse, creating tier schemas if absent.

    Pass ':memory:' for tests.
    """
    target = path if path is not None else warehouse_path()
    if target != ":memory:":
        target = Path(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        target = str(target)
    conn = duckdb.connect(target)
    for tier in TIERS:
        conn.execute(f"CREATE SCHEMA IF NOT EXISTS {tier}")
    return conn


def bulk_insert(
    conn: "duckdb.DuckDBPyConnection",
    table: str,
    columns: "list[str]",
    rows: "list[tuple]",
) -> int:
    """Insert Python-built rows efficiently.

    Row-by-row `executemany` costs ~1.3ms per statement in DuckDB, which
    dominates any load above a few hundred rows. Staging through a temporary
    CSV lets the native reader do the work in one statement.

    NULLs are written as a sentinel because an empty CSV field is an empty
    string, not a NULL, for VARCHAR columns.
    """
    import csv as _csv
    import tempfile

    if not rows:
        return 0

    sentinel = "\\N"
    with tempfile.TemporaryDirectory() as tmp:
        staging = Path(tmp) / "staging.csv"
        with staging.open("w", newline="", encoding="utf-8") as handle:
            writer = _csv.writer(handle)
            writer.writerow(columns)
            for row in rows:
                writer.writerow(
                    [sentinel if value is None else value for value in row]
                )
        quoted = str(staging).replace("'", "''")
        column_list = ", ".join(f'"{c}"' for c in columns)
        return conn.execute(
            f"""
            INSERT INTO {table} ({column_list})
            SELECT {column_list}
            FROM read_csv('{quoted}', header=true, all_varchar=true,
                          nullstr='{sentinel}')
            """
        ).fetchone()[0]
