"""Canonical tier: service visits and the events trapped inside them.

`systems_serviced` and `chemicals_added` are semicolon-delimited strings in the
source. They are exploded here into first-class SystemService and
ChemicalApplication events, which is what lets coverage and consumption
analytics traverse them.

Dose attribution is deliberately partial. 269 of the 316 chemical-bearing
visits serve more than one system, and the dose list is a flat concatenation
across all of them with no per-system boundary. Those doses record a null
system and `attribution = 'facility'`; only single-system visits attribute a
dose to equipment. Inventing an assignment would corrupt the very consumption
analytics the guidelines rely on to spot a leaking closed loop.
"""

from __future__ import annotations

import json

import duckdb

from ..clean.versioning import TABLE as VERSIONS
from ..normalize.delimited import (
    doses_are_attributable,
    parse_chemicals_added,
    parse_systems_serviced,
)
from ..normalize.identity import resolve_actor
from ..normalize.temporal import parse_date
from ..warehouse import CANONICAL, bulk_insert
from .identity import resolve_sql

VISIT_TABLE = f"{CANONICAL}.service_visit"
SYSTEM_SERVICE_TABLE = f"{CANONICAL}.system_service"
APPLICATION_TABLE = f"{CANONICAL}.chemical_application"

_DDL = f"""
CREATE OR REPLACE TABLE {VISIT_TABLE} (
    visit_id          VARCHAR NOT NULL,
    visit_date        DATE,
    visit_date_raw    VARCHAR,
    customer_id       VARCHAR,
    facility_id       VARCHAR,
    source_facility_id VARCHAR,
    technician_raw    VARCHAR,
    technician_id     VARCHAR,
    visit_status      VARCHAR,
    work_performed    VARCHAR,
    observations      VARCHAR,
    follow_up_date    DATE,
    system_count      INTEGER,
    dose_count        INTEGER,
    source_system     VARCHAR,
    batch_name        VARCHAR
);
CREATE OR REPLACE TABLE {SYSTEM_SERVICE_TABLE} (
    system_service_id VARCHAR NOT NULL,
    visit_id          VARCHAR NOT NULL,
    system_id         VARCHAR NOT NULL,
    facility_id       VARCHAR,
    visit_date        DATE,
    technician_id     VARCHAR,
    visit_status      VARCHAR,
    ordinal           INTEGER
);
CREATE OR REPLACE TABLE {APPLICATION_TABLE} (
    application_id VARCHAR NOT NULL,
    visit_id       VARCHAR NOT NULL,
    facility_id    VARCHAR,
    system_id      VARCHAR,
    attribution    VARCHAR NOT NULL,
    product_code   VARCHAR NOT NULL,
    quantity       DOUBLE,
    unit           VARCHAR,
    visit_date     DATE,
    ordinal        INTEGER NOT NULL,
    raw_segment    VARCHAR
);
"""

_VISIT_COLUMNS = [
    "visit_id", "visit_date", "visit_date_raw", "customer_id", "facility_id",
    "source_facility_id", "technician_raw", "technician_id", "visit_status",
    "work_performed", "observations", "follow_up_date", "system_count",
    "dose_count", "source_system", "batch_name",
]
_SERVICE_COLUMNS = [
    "system_service_id", "visit_id", "system_id", "facility_id", "visit_date",
    "technician_id", "visit_status", "ordinal",
]
_APPLICATION_COLUMNS = [
    "application_id", "visit_id", "facility_id", "system_id", "attribution",
    "product_code", "quantity", "unit", "visit_date", "ordinal", "raw_segment",
]


def build(conn: duckdb.DuckDBPyConnection, corpus=None) -> dict[str, int]:
    """Explode current service-visit records into visits, services and doses."""
    for statement in _DDL.strip().split(";"):
        if statement.strip():
            conn.execute(statement)

    rows = conn.execute(
        f"""
        SELECT payload, batch_name,
               json_extract_string(payload, '$.facility_id') AS raw_facility,
               {resolve_sql('facility', "json_extract_string(payload, '$.facility_id')")}
                   AS facility_id,
               {resolve_sql('customer', "json_extract_string(payload, '$.customer_id')")}
                   AS customer_id
        FROM {VERSIONS}
        WHERE entity = 'service_visits' AND is_current
        ORDER BY batch_sequence, source_row_number
        """
    ).fetchall()

    visits, services, applications = [], [], []
    for payload, batch, raw_facility, facility_id, customer_id in rows:
        row = json.loads(payload)
        visit_id = row["visit_id"]
        date = parse_date(row.get("visit_date"), corpus=corpus)
        follow_up = parse_date(row.get("follow_up_date"), corpus=corpus)
        actor = resolve_actor(row.get("technician"))
        technician_id = actor.value.actor_id if actor.value else None

        systems = parse_systems_serviced(row.get("systems_serviced")).value
        doses = parse_chemicals_added(row.get("chemicals_added")).value
        attributable = doses_are_attributable(len(systems))

        visits.append(
            (
                visit_id, date.value, row.get("visit_date"), customer_id,
                facility_id, raw_facility, row.get("technician"), technician_id,
                row.get("visit_status"), row.get("work_performed"),
                row.get("observations"), follow_up.value, len(systems),
                len(doses), row.get("source_system") or "ServiceTrak", batch,
            )
        )

        for ordinal, system_id in enumerate(systems):
            services.append(
                (
                    f"{visit_id}:{system_id}", visit_id, system_id, facility_id,
                    date.value, technician_id, row.get("visit_status"), ordinal,
                )
            )

        for dose in doses:
            applications.append(
                (
                    f"{visit_id}:{dose.ordinal}", visit_id, facility_id,
                    systems[0] if attributable else None,
                    "system" if attributable else "facility",
                    dose.product_code, dose.quantity, dose.unit, date.value,
                    dose.ordinal, dose.raw,
                )
            )

    bulk_insert(conn, VISIT_TABLE, _VISIT_COLUMNS, visits)
    bulk_insert(conn, SYSTEM_SERVICE_TABLE, _SERVICE_COLUMNS, services)
    bulk_insert(conn, APPLICATION_TABLE, _APPLICATION_COLUMNS, applications)

    return {
        "visits": len(visits),
        "system_services": len(services),
        "chemical_applications": len(applications),
    }
