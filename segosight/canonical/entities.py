"""Canonical tier: master data with source identifiers resolved.

customers.csv is denormalized -- one row per customer x facility -- so the
customer and facility entities are projected out of it separately, which the
Ontology design requires: a corporate account can own several plants, while
service, chemistry and coverage failures happen at a physical site.

Merge precedence: where several source records collapse onto one canonical
identifier, the record whose own identifier survives wins. Otherwise the
retired CUST-0019 row (tier C, no contract value) would overwrite the surviving
CUST-0007 account's tier B and $24,000 ACV.
"""

from __future__ import annotations

import duckdb

from ..clean.versioning import TABLE as VERSIONS
from ..warehouse import CANONICAL
from .identity import confidence_sql, resolve_sql

CUSTOMER_TABLE = f"{CANONICAL}.customer"
FACILITY_TABLE = f"{CANONICAL}.facility"
SYSTEM_TABLE = f"{CANONICAL}.system"


def _field(column: str) -> str:
    return f"json_extract_string(payload, '$.{column}')"


def _customers_cte() -> str:
    return f"""
    SELECT
        {_field('customer_id')}   AS source_customer_id,
        {_field('facility_id')}   AS source_facility_id,
        {_field('customer_name')} AS customer_name,
        {_field('facility_name')} AS facility_name,
        {_field('address')}       AS address,
        {_field('city')}          AS city,
        {_field('state')}         AS state,
        {_field('account_tier')}  AS account_tier,
        try_cast({_field('annual_contract_value_usd')} AS DOUBLE) AS acv_usd,
        {_field('primary_contact_name')}  AS contact_name,
        {_field('primary_contact_email')} AS contact_email,
        {_field('primary_contact_phone')} AS contact_phone,
        {_field('service_frequency')}     AS service_frequency,
        try_cast({_field('contract_start')} AS DATE) AS contract_start,
        try_cast({_field('contract_end')}   AS DATE) AS contract_end,
        try_cast({_field('sla_response_hours')} AS INTEGER) AS sla_response_hours,
        {_field('notes')} AS notes
    FROM {VERSIONS}
    WHERE entity = 'customers' AND is_current
    """


def build(conn: duckdb.DuckDBPyConnection) -> dict[str, int]:
    """Materialize canonical customer, facility and system tables."""
    cust_id = resolve_sql("customer", "source_customer_id")
    fac_id = resolve_sql("facility", "source_facility_id")

    conn.execute(
        f"""
        CREATE OR REPLACE TABLE {CUSTOMER_TABLE} AS
        WITH src AS ({_customers_cte()}),
        resolved AS (
            SELECT *, {cust_id} AS customer_id,
                   {confidence_sql('customer', 'source_customer_id')} AS id_confidence
            FROM src
        ),
        ranked AS (
            SELECT *, row_number() OVER (
                PARTITION BY customer_id
                -- The surviving record's own row wins over a merged-in one.
                ORDER BY (source_customer_id = customer_id) DESC,
                         acv_usd DESC NULLS LAST
            ) AS rank
            FROM resolved
        )
        SELECT customer_id, customer_name, account_tier, acv_usd,
               contact_name, contact_email, contact_phone,
               contract_start, contract_end, sla_response_hours, id_confidence,
               (SELECT count(DISTINCT source_customer_id) FROM resolved r2
                WHERE r2.customer_id = ranked.customer_id) AS merged_source_count
        FROM ranked WHERE rank = 1
        """
    )

    conn.execute(
        f"""
        CREATE OR REPLACE TABLE {FACILITY_TABLE} AS
        WITH src AS ({_customers_cte()}),
        resolved AS (
            SELECT *, {cust_id} AS customer_id, {fac_id} AS facility_id,
                   {confidence_sql('facility', 'source_facility_id')} AS id_confidence
            FROM src
        ),
        ranked AS (
            SELECT *, row_number() OVER (
                PARTITION BY facility_id
                ORDER BY (source_facility_id = facility_id) DESC
            ) AS rank
            FROM resolved
        )
        SELECT facility_id, customer_id, facility_name, address, city, state,
               service_frequency, contract_start, contract_end,
               sla_response_hours, notes, id_confidence,
               (SELECT count(DISTINCT source_facility_id) FROM resolved r2
                WHERE r2.facility_id = ranked.facility_id) AS merged_source_count
        FROM ranked WHERE rank = 1
        """
    )

    conn.execute(
        f"""
        CREATE OR REPLACE TABLE {SYSTEM_TABLE} AS
        SELECT
            {_field('system_id')} AS system_id,
            {resolve_sql('facility', _field('facility_id'))} AS facility_id,
            {_field('system_type')}           AS system_type,
            {_field('description')}           AS description,
            {_field('capacity')}              AS capacity,
            {_field('operating_parameters')}  AS operating_parameters,
            try_cast({_field('install_date')} AS DATE) AS install_date,
            {_field('treatment_program')}     AS treatment_program,
            {_field('criticality')}           AS criticality,
            {_field('status')}                AS status,
            {_field('notes')}                 AS notes
        FROM {VERSIONS}
        WHERE entity = 'systems' AND is_current
        """
    )

    return {
        "customers": conn.execute(f"SELECT count(*) FROM {CUSTOMER_TABLE}").fetchone()[0],
        "facilities": conn.execute(f"SELECT count(*) FROM {FACILITY_TABLE}").fetchone()[0],
        "systems": conn.execute(f"SELECT count(*) FROM {SYSTEM_TABLE}").fetchone()[0],
    }
