"""Record versioning: which version of a business key is current.

The sources carry no version column, so batch sequence is the only available
recency signal (registry `[[batches]].sequence`). When the same business key
appears in more than one batch the later one is current and the earlier is
retained as superseded evidence.

This is append-and-supersede, never overwrite. Guidelines section 2 requires
that a superseded or unrepresentative result "stays in the record and is
annotated rather than deleted", and a hospital documentation packet has to be
able to show that a correction happened, not merely show the corrected value.

Observed in the data: RD-00923 is re-issued in the September batch with
pH 9.1, correcting a transcription error that exported it as 91.2. SYS-0006 is
re-issued as decommissioned after its tube failure.
"""

from __future__ import annotations

import duckdb

from ..warehouse import CLEAN
from ..ingest.raw import TABLE as RAW_TABLE

TABLE = f"{CLEAN}.record_versions"

_DDL = f"""
CREATE OR REPLACE TABLE {TABLE} AS
WITH ranked AS (
    SELECT
        *,
        row_number() OVER (
            PARTITION BY entity, business_key
            ORDER BY batch_sequence DESC, source_row_number DESC
        ) AS recency_rank,
        count(*) OVER (PARTITION BY entity, business_key) AS version_count
    FROM {RAW_TABLE}
)
SELECT
    r.row_hash,
    r.entity,
    r.business_key,
    r.batch_name,
    r.batch_sequence,
    r.source_system,
    r.source_file,
    r.source_row_number,
    r.payload,
    r.ingested_at,
    r.version_count,
    (r.recency_rank = 1)                        AS is_current,
    (r.recency_rank > 1)                        AS is_superseded,
    -- The row_hash of the version in force. The ordering puts the current
    -- version first in the partition, so first_value resolves to it.
    first_value(r.row_hash) OVER (
        PARTITION BY r.entity, r.business_key
        ORDER BY r.batch_sequence DESC, r.source_row_number DESC
    )                                           AS current_row_hash
FROM ranked r
"""


def build(conn: duckdb.DuckDBPyConnection) -> int:
    """Materialize the version table. Returns the current-version row count."""
    conn.execute(_DDL)
    return conn.execute(
        f"SELECT count(*) FROM {TABLE} WHERE is_current"
    ).fetchone()[0]


def superseded(conn: duckdb.DuckDBPyConnection) -> list[tuple]:
    """Every business key that has more than one version, for review."""
    return conn.execute(
        f"""
        SELECT entity, business_key, version_count
        FROM {TABLE}
        WHERE version_count > 1 AND is_current
        ORDER BY entity, business_key
        """
    ).fetchall()
