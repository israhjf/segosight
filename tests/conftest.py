"""Shared fixtures.

The warehouse is built once per session from the real source material, so the
pipeline tests assert against the actual corpus rather than synthetic rows.
"""

from __future__ import annotations

import pytest

from segosight.canonical import entities, events, identity, visits
from segosight.curated import alerts, assessments, coverage, extraction, microbio, trends
from segosight.ingest import documents
from segosight.curated.programs import load_config
from segosight.clean import readings, versioning
from segosight.ingest.raw import land_all
from segosight.ingest.registry import load_registry
from segosight.paths import materials_root
from segosight.warehouse import connect


@pytest.fixture(scope="session")
def registry():
    return load_registry()


@pytest.fixture(scope="session")
def programs():
    return load_config()


@pytest.fixture(scope="session")
def warehouse(registry):
    if not materials_root().is_dir():
        pytest.skip("source material not present")
    conn = connect(":memory:")
    land_all(conn, registry)
    versioning.build(conn)
    readings.build(conn, corpus=registry.corpus)
    identity.build(conn)
    entities.build(conn)
    events.build(conn)
    visits.build(conn, corpus=registry.corpus)
    programs = load_config()
    assessments.build(conn, programs)
    trends.build(conn, programs)
    coverage.build(conn, programs)
    microbio.build(conn, programs)
    alerts.build(conn, programs)
    documents.build(conn)
    extraction.build(conn)
    alerts.attach_prose(conn, programs)
    yield conn
    conn.close()
