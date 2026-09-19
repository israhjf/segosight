"""Canonical tier: the governed identity crosswalk.

Loads `config/identity.toml` into `canonical.identity_resolution`, one row per
source-identifier-to-canonical-identifier decision, carrying confidence,
evidence, authorization and rationale.

Confidence gates alerting. A `medium` mapping resolves for display and review
but is not `alert_eligible`, so a reading that only reaches a system through an
uncertain lab-code mapping cannot by itself raise a customer-facing or
compliance alert. That matters most for MRMC-B1: Maeser Ridge has two
fire-tube boilers, so "boiler 1" is ambiguous, and it is a healthcare account
where a wrong join would put another unit's chemistry into a compliance record.

Asset lineage is deliberately NOT a merge. SYS-0006 and SYS-0101 are distinct
physical units; the lineage link records continuity without rewriting history,
exactly as Rosa's go-live note requires.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import duckdb

from segosight.shared.normalize.actors import ROSTER
from segosight.shared.paths import config_dir
from segosight.shared.warehouse import CANONICAL, bulk_insert

DEFAULT_CONFIG = config_dir() / "identity.toml"

TABLE = f"{CANONICAL}.identity_resolution"
LINEAGE_TABLE = f"{CANONICAL}.asset_lineage"
EMPLOYEE_TABLE = f"{CANONICAL}.employee"

#: Confidence levels that may drive customer-facing or compliance alerts.
ALERT_ELIGIBLE_CONFIDENCE = frozenset({"high"})

#: Config table name -> identity domain.
_DOMAINS = {
    "customer": "customer",
    "facility": "facility",
    "system": "system",
    "sample_point": "sample_point",
}

_COLUMNS = [
    "domain", "source_id", "canonical_id", "relationship", "confidence",
    "alert_eligible", "effective_from", "evidence", "authorized_by", "rationale",
]

_LINEAGE_COLUMNS = [
    "predecessor_id", "successor_id", "relationship", "confidence",
    "effective_from", "evidence", "authorized_by", "rationale",
]

_DDL = f"""
CREATE OR REPLACE TABLE {TABLE} (
    domain         VARCHAR NOT NULL,
    source_id      VARCHAR NOT NULL,
    canonical_id   VARCHAR NOT NULL,
    relationship   VARCHAR NOT NULL,
    confidence     VARCHAR NOT NULL,
    alert_eligible BOOLEAN NOT NULL,
    effective_from DATE,
    evidence       VARCHAR,
    authorized_by  VARCHAR,
    rationale      VARCHAR
);
CREATE OR REPLACE TABLE {LINEAGE_TABLE} (
    predecessor_id VARCHAR NOT NULL,
    successor_id   VARCHAR NOT NULL,
    relationship   VARCHAR NOT NULL,
    confidence     VARCHAR NOT NULL,
    effective_from DATE,
    evidence       VARCHAR,
    authorized_by  VARCHAR,
    rationale      VARCHAR
);
CREATE OR REPLACE TABLE {EMPLOYEE_TABLE} (
    employee_id  VARCHAR NOT NULL,
    display_name VARCHAR NOT NULL,
    initials     VARCHAR NOT NULL,
    actor_type   VARCHAR NOT NULL,
    departed_on  DATE
);
"""


def load_config(path: Path | None = None) -> dict:
    return tomllib.loads((path or DEFAULT_CONFIG).read_text(encoding="utf-8"))


def build(conn: duckdb.DuckDBPyConnection, path: Path | None = None) -> int:
    """Materialize the crosswalk, lineage and employee master."""
    config = load_config(path)
    for statement in _DDL.strip().split(";"):
        if statement.strip():
            conn.execute(statement)

    rows = []
    for table_name, domain in _DOMAINS.items():
        for entry in config.get(table_name, []):
            confidence = entry["confidence"]
            rows.append(
                (
                    domain,
                    entry["source_id"],
                    entry["canonical_id"],
                    entry.get("relationship", "alias"),
                    confidence,
                    confidence in ALERT_ELIGIBLE_CONFIDENCE,
                    entry.get("effective_from"),
                    entry.get("evidence"),
                    entry.get("authorized_by"),
                    " ".join(entry.get("rationale", "").split()),
                )
            )
    bulk_insert(conn, TABLE, _COLUMNS, rows)

    lineage = [
        (
            e["predecessor_id"], e["successor_id"], e["relationship"],
            e["confidence"], e.get("effective_from"), e.get("evidence"),
            e.get("authorized_by"), " ".join(e.get("rationale", "").split()),
        )
        for e in config.get("asset_lineage", [])
    ]
    bulk_insert(conn, LINEAGE_TABLE, _LINEAGE_COLUMNS, lineage)

    employees = [
        (
            actor.actor_id,
            actor.display_name,
            "".join(p[0] for p in actor.display_name.split()).upper(),
            actor.actor_type,
            actor.departed,
        )
        for actor in ROSTER
    ]
    bulk_insert(
        conn, EMPLOYEE_TABLE,
        ["employee_id", "display_name", "initials", "actor_type", "departed_on"],
        employees,
    )

    return len(rows)


def resolve_sql(domain: str, column: str) -> str:
    """SQL fragment resolving `column` to its canonical identifier.

    Unmapped identifiers pass through unchanged, so an identifier that needs no
    resolution behaves identically to one that does.
    """
    return (
        f"coalesce((SELECT r.canonical_id FROM {TABLE} r "
        f"WHERE r.domain = '{domain}' AND r.source_id = {column}), {column})"
    )


def confidence_sql(domain: str, column: str) -> str:
    """SQL fragment giving the confidence with which `column` was resolved."""
    return (
        f"coalesce((SELECT r.confidence FROM {TABLE} r "
        f"WHERE r.domain = '{domain}' AND r.source_id = {column}), 'direct')"
    )
