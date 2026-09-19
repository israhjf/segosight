"""Corpus-wide validation: the primitives must survive every real row.

These tests read the supplied CSVs in place. They guard the hard requirement
that the system works against the data as it actually is, and they would catch
a regression that unit tests on hand-picked literals would miss.
"""

from __future__ import annotations

import csv

import pytest

from segosight.normalize import codes
from segosight.normalize.delimited import parse_chemicals_added, parse_systems_serviced
from segosight.normalize.identity import resolve_actor
from segosight.normalize.numeric import parse_number
from segosight.normalize.quality import parse_dipslide
from segosight.normalize.temporal import parse_timestamp
from segosight.normalize.units import (
    COLUMN_SPECS,
    convert,
    parse_units_declaration,
    resolve_parameter,
)
from segosight.paths import materials_root, new_batch_root


def _read(path):
    if not path.exists():
        pytest.skip(f"source material not present: {path}")
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


@pytest.fixture(scope="module")
def readings():
    return _read(materials_root() / "water_readings.csv") + _read(
        new_batch_root() / "water_readings_2026-09.csv"
    )


@pytest.fixture(scope="module")
def visits():
    return _read(materials_root() / "service_visits.csv") + _read(
        new_batch_root() / "service_visits_2026-09.csv"
    )


class TestTimestampCoverage:
    def test_every_reading_timestamp_parses(self, readings):
        failed = [
            r["reading_id"]
            for r in readings
            if codes.UNPARSEABLE_TIMESTAMP in parse_timestamp(r["timestamp"]).issues
        ]
        assert failed == []

    def test_both_conventions_are_actually_present_in_the_legacy_file(self):
        """Guards the dictionary's incorrect claim that legacy is ISO-only."""
        legacy = _read(materials_root() / "water_readings.csv")
        formats = {
            parse_timestamp(r["timestamp"]).detail.get("format") for r in legacy
        }
        assert "%Y-%m-%d %H:%M" in formats
        assert "%m/%d/%y %H:%M" in formats

    def test_every_visit_date_parses(self, visits):
        failed = [
            v["visit_id"]
            for v in visits
            if codes.UNPARSEABLE_TIMESTAMP in parse_timestamp(v["visit_date"]).issues
        ]
        assert failed == []


class TestUnitCoverage:
    def test_every_declared_unit_is_recognized(self, readings):
        unrecognized = set()
        for row in readings:
            declaration = parse_units_declaration(row["units"])
            for spec in COLUMN_SPECS:
                raw = row.get(spec.column)
                if not raw:
                    continue
                res = resolve_parameter(spec.column, declaration)
                got = convert(res.parameter, parse_number(raw).value, res.raw_unit)
                if codes.UNIT_UNRECOGNIZED in got.issues:
                    unrecognized.add((res.parameter.code, res.raw_unit))
        assert unrecognized == set()

    def test_every_numeric_cell_parses(self, readings):
        bad = []
        for row in readings:
            for spec in COLUMN_SPECS:
                raw = row.get(spec.column)
                if raw and codes.UNPARSEABLE_NUMBER in parse_number(raw).issues:
                    bad.append((row["reading_id"], spec.column, raw))
        assert bad == []

    def test_undeclared_units_are_confined_to_the_known_handful(self, readings):
        """4 rows populate inhibitor_ppm with no declaration; alert on growth."""
        undeclared = sum(
            1
            for row in readings
            for spec in COLUMN_SPECS
            if row.get(spec.column)
            and codes.UNIT_NOT_DECLARED
            in resolve_parameter(
                spec.column, parse_units_declaration(row["units"])
            ).issues
        )
        assert undeclared <= 15

    def test_conductivity_normalizes_into_one_comparable_range(self, readings):
        """After conversion, mS/cm and uS/cm rows must be mutually comparable."""
        values = []
        for row in readings:
            if not row["conductivity"]:
                continue
            declaration = parse_units_declaration(row["units"])
            res = resolve_parameter("conductivity", declaration)
            got = convert(res.parameter, parse_number(row["conductivity"]).value, res.raw_unit)
            if got.value:
                values.append(got.value)
        # No treated system reads below 100 uS/cm; an unconverted mS/cm row
        # would land near 3.0 and fail this.
        assert min(values) > 100
        assert max(values) < 10_000


class TestDipslideCoverage:
    def test_every_dipslide_value_parses(self, readings):
        bad = [
            r["reading_id"]
            for r in readings
            if r["microbio_dipslide"]
            and codes.MALFORMED_DIPSLIDE in parse_dipslide(r["microbio_dipslide"]).issues
        ]
        assert bad == []


class TestIdentityCoverage:
    def test_every_technician_token_resolves(self, visits):
        unresolved = {
            v["technician"]
            for v in visits
            if v["technician"] and resolve_actor(v["technician"]).value is None
        }
        assert unresolved == set()

    def test_every_collected_by_token_resolves(self, readings):
        unresolved = {
            r["collected_by"]
            for r in readings
            if r["collected_by"] and resolve_actor(r["collected_by"]).value is None
        }
        assert unresolved == set()


class TestDelimitedCoverage:
    def test_every_dose_segment_parses(self, visits):
        bad = []
        for visit in visits:
            got = parse_chemicals_added(visit["chemicals_added"])
            bad += [(visit["visit_id"], d.raw) for d in got.value if d.issues]
        assert bad == []

    def test_every_system_reference_is_well_formed(self, visits):
        malformed = [
            (v["visit_id"], s)
            for v in visits
            for s in parse_systems_serviced(v["systems_serviced"]).value
            if not s.startswith("SYS-")
        ]
        assert malformed == []

    def test_dose_attribution_is_impossible_for_most_visits(self, visits):
        """Documents the modelling constraint rather than hiding it."""
        with_chem = [v for v in visits if v["chemicals_added"]]
        multi = [
            v
            for v in with_chem
            if len(parse_systems_serviced(v["systems_serviced"]).value) > 1
        ]
        assert len(multi) / len(with_chem) > 0.8
