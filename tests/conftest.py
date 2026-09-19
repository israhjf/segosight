"""Shared fixtures.

The warehouse is built once per session from the real source material, so the
pipeline tests assert against the actual corpus rather than synthetic rows.

It is built to a file rather than held in memory so that tests which *write*
(review decisions, promotion) can take a cheap copy and mutate it in isolation.
Without that, a decision recorded by one test changes what a later test sees,
and the suite silently becomes order-dependent.
"""

from __future__ import annotations

import shutil

import duckdb
import pytest

from segosight.features.chemistry.canonical import series as events
from segosight.features.identity.canonical import crosswalk as identity, entities
from segosight.features.service.canonical import visits
from segosight.features.chemistry.clean import readings
from segosight.features.ingestion.clean import versioning
from segosight.features.alerts.curated import aggregation as alerts
from segosight.features.chemistry.curated import assessments, trends
from segosight.features.compliance.curated import microbio
from segosight.features.review.curated import extraction
from segosight.features.service.curated import coverage
from segosight.features.chemistry.programs import load_config
from segosight.features.review.raw import documents
from segosight.features.ingestion.raw.landing import land_all
from segosight.features.ingestion.registry import load_registry
from segosight.shared.paths import materials_root
from segosight.shared.warehouse import connect


@pytest.fixture(scope="session")
def registry():
    return load_registry()


@pytest.fixture(scope="session")
def programs():
    return load_config()


@pytest.fixture(scope="session")
def warehouse_path(tmp_path_factory, registry):
    """Build every tier once, then close so the file can be copied safely."""
    if not materials_root().is_dir():
        pytest.skip("source material not present")

    path = tmp_path_factory.mktemp("warehouse") / "segosight.duckdb"
    conn = connect(path)
    programs_config = load_config()

    land_all(conn, registry)
    versioning.build(conn)
    readings.build(conn, corpus=registry.corpus)
    identity.build(conn)
    entities.build(conn)
    events.build(conn)
    visits.build(conn, corpus=registry.corpus)
    assessments.build(conn, programs_config)
    trends.build(conn, programs_config)
    coverage.build(conn, programs_config)
    microbio.build(conn, programs_config)
    alerts.build(conn, programs_config)
    documents.build(conn)
    extraction.build(conn)
    alerts.attach_prose(conn, programs_config)

    conn.close()
    return path


@pytest.fixture(scope="session")
def warehouse(warehouse_path):
    """Read-only view of the built warehouse, shared by the read-only tests."""
    conn = duckdb.connect(str(warehouse_path), read_only=True)
    yield conn
    conn.close()


@pytest.fixture()
def writable_warehouse(warehouse_path, tmp_path):
    """An isolated copy, for tests that record decisions."""
    copy = tmp_path / "segosight.duckdb"
    shutil.copy(warehouse_path, copy)
    conn = connect(copy)
    yield conn
    conn.close()
