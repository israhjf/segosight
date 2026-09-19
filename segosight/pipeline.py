"""SegoSight pipeline runner.

    python -m segosight.pipeline [--warehouse PATH] [--materials PATH]

Re-running is safe: the raw tier is content-addressed, so re-ingesting a batch
inserts nothing. Incorporating a new drop is a config change in
`config/sources.toml`, not a code change.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from .canonical import entities, events, identity, visits
from .clean import readings, versioning
from .curated import alerts, assessments, coverage, microbio, trends
from .curated.programs import load_config
from .ingest.raw import land_all
from .ingest.registry import load_registry
from .warehouse import connect


def run(warehouse_path: Path | str | None = None, materials: Path | None = None):
    registry = load_registry()
    conn = connect(warehouse_path)
    started = time.perf_counter()

    print("Raw tier")
    results = land_all(conn, registry, materials)
    for result in results:
        drift = ""
        if result.added_columns:
            drift = f"  [+{', '.join(result.added_columns)}]"
        if result.missing_columns:
            drift += f"  [-{', '.join(result.missing_columns)}]"
        print(
            f"  {result.entity:<20} {result.batch:<9} "
            f"read={result.rows_read:<5} new={result.rows_inserted:<5}"
            f"skipped={result.rows_skipped:<5}{drift}"
        )

    current = versioning.build(conn)
    multi = versioning.superseded(conn)
    print(f"\nClean tier\n  current record versions: {current}")
    for entity, key, count in multi:
        print(f"  superseded: {entity} {key} ({count} versions)")

    total = readings.build(conn, corpus=registry.corpus)
    print(f"  long-form reading events: {total}")
    for status, count in conn.execute(
        f"""SELECT quality_status, count(*) FROM {readings.TABLE}
            GROUP BY 1 ORDER BY 2 DESC"""
    ).fetchall():
        print(f"    {status:<12} {count}")

    print("\nCanonical tier")
    print(f"  identity mappings: {identity.build(conn)}")
    counts = entities.build(conn)
    print(
        f"  customers={counts['customers']} facilities={counts['facilities']} "
        f"systems={counts['systems']}"
    )
    for entity, key, canonical in conn.execute(
        f"""SELECT domain, source_id, canonical_id FROM {identity.TABLE}
            WHERE relationship = 'duplicate_merge' ORDER BY domain, source_id"""
    ).fetchall():
        print(f"    merged {entity}: {key} -> {canonical}")

    print(f"  reading events: {events.build(conn)}")
    aliased, eligible = conn.execute(
        f"""SELECT count(*) FILTER (WHERE system_id_was_aliased),
                   count(*) FILTER (WHERE system_id_was_aliased AND alert_eligible)
            FROM {events.TABLE}"""
    ).fetchone()
    print(f"    lab-aliased events resolved: {aliased} ({eligible} alert-eligible)")
    orphans = conn.execute(
        f"SELECT count(*) FROM {events.TABLE} WHERE facility_id IS NULL"
    ).fetchone()[0]
    print(f"    unresolved (orphaned) events: {orphans}")

    counts = visits.build(conn, corpus=registry.corpus)
    print(
        f"  visits={counts['visits']} "
        f"system_services={counts['system_services']} "
        f"chemical_applications={counts['chemical_applications']}"
    )

    print("\nCurated tier")
    programs = load_config()
    print(f"  rule version: {programs.rule_version}")
    print(f"  reading assessments: {assessments.build(conn, programs)}")
    for status, count in conn.execute(
        f"""SELECT status, count(*) FROM {assessments.TABLE}
            WHERE status <> 'in_band' GROUP BY 1 ORDER BY 2 DESC"""
    ).fetchall():
        print(f"    {status:<24} {count}")

    print(f"  trend signals: {trends.build(conn, programs)}")
    print(f"  coverage evaluated: {coverage.build(conn, programs)} facilities")
    for status, count in conn.execute(
        f"""SELECT status, count(*) FROM {coverage.TABLE}
            WHERE status <> 'on_schedule' GROUP BY 1 ORDER BY 2 DESC"""
    ).fetchall():
        print(f"    {status:<24} {count}")

    escalations = microbio.build(conn, programs)
    undocumented = conn.execute(
        f"SELECT count(*) FROM {microbio.TABLE} WHERE NOT documented"
    ).fetchone()[0]
    print(f"  microbio escalations: {escalations} ({undocumented} undocumented)")

    total = alerts.build(conn, programs)
    print(f"\nOperational alerts: {total}")
    for row in conn.execute(
        f"""SELECT severity, risk_class, count(*) FROM {alerts.TABLE}
            GROUP BY 1,2 ORDER BY count(*) DESC"""
    ).fetchall():
        print(f"    {row[0]:<9} {row[1]:<22} {row[2]}")

    print("\nTop 5 by priority")
    for row in conn.execute(
        f"""SELECT priority_score, severity, customer_name, title
            FROM {alerts.TABLE} ORDER BY priority_score DESC, last_observed DESC
            LIMIT 5"""
    ).fetchall():
        print(f"  [{row[0]:.2f}] {row[1]:<8} {(row[2] or '-')[:26]:<26} {row[3]}")

    print(f"\nCompleted in {time.perf_counter() - started:.2f}s")
    return conn


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="segosight.pipeline")
    parser.add_argument("--warehouse", type=Path, default=None)
    parser.add_argument("--materials", type=Path, default=None)
    args = parser.parse_args(argv)
    run(args.warehouse, args.materials)
    return 0


if __name__ == "__main__":
    sys.exit(main())
