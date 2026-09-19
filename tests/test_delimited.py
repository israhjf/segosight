"""Tests for exploding the semicolon-delimited visit fields."""

import pytest

from segosight.shared.normalize import codes
from segosight.shared.normalize.delimited import (
    Dose,
    doses_are_attributable,
    parse_chemicals_added,
    parse_systems_serviced,
)


class TestSystemsServiced:
    def test_multi_system_visit_explodes_in_order(self):
        # V-0001
        got = parse_systems_serviced("SYS-0001;SYS-0002;SYS-0003;SYS-0004;SYS-0005")
        assert got.value == [
            "SYS-0001",
            "SYS-0002",
            "SYS-0003",
            "SYS-0004",
            "SYS-0005",
        ]

    def test_single_system_visit(self):
        assert parse_systems_serviced("SYS-0022").value == ["SYS-0022"]

    def test_fieldflow_visit_referencing_the_rental_unit(self):
        # FF-1007, after the SYS-0006 -> SYS-0101 replacement
        assert parse_systems_serviced("SYS-0101;SYS-0007;SYS-0008").value == [
            "SYS-0101",
            "SYS-0007",
            "SYS-0008",
        ]

    @pytest.mark.parametrize("empty", ["", None])
    def test_empty_yields_empty_list(self, empty):
        assert parse_systems_serviced(empty).value == []


class TestChemicalsAdded:
    def test_parses_product_quantity_and_unit(self):
        got = parse_chemicals_added("BW-210 3 gal; BW-305 1 gal; AM-115 1 qt")
        assert [(d.product_code, d.quantity, d.unit) for d in got.value] == [
            ("BW-210", 3.0, "gal"),
            ("BW-305", 1.0, "gal"),
            ("AM-115", 1.0, "qt"),
        ]

    def test_hyphenated_product_with_letter_suffix(self):
        # CL-M40 must not be truncated to CL-M or misread as CL-40.
        got = parse_chemicals_added("CL-M40 1 gal")
        assert got.value[0].product_code == "CL-M40"

    def test_solid_biocide_in_pounds(self):
        got = parse_chemicals_added("BRM-40 5 lb")
        assert (got.value[0].product_code, got.value[0].unit) == ("BRM-40", "lb")

    def test_repeated_segments_are_distinct_doses_not_duplicates(self):
        """V-0001 doses two towers identically; collapsing halves consumption."""
        got = parse_chemicals_added(
            "CT-770 6 gal; BIO-12 1 gal; CT-770 6 gal; BIO-12 1 gal"
        )
        assert len(got.value) == 4
        ct770 = [d for d in got.value if d.product_code == "CT-770"]
        assert sum(d.quantity for d in ct770) == pytest.approx(12.0)
        assert [d.ordinal for d in got.value] == [0, 1, 2, 3]

    def test_decimal_quantity(self):
        assert parse_chemicals_added("CT-770 2.5 gal").value[0].quantity == 2.5

    @pytest.mark.parametrize("empty", ["", None])
    def test_visit_with_no_chemicals(self, empty):
        # FF-1002, the emergency callout: no dosing recorded.
        assert parse_chemicals_added(empty).value == []

    def test_unparseable_segment_is_retained_and_flagged(self):
        got = parse_chemicals_added("BW-210 3 gal; something odd here")
        assert len(got.value) == 2
        assert codes.UNPARSEABLE_DOSE in got.issues
        assert got.value[1].quantity is None
        assert got.value[1].raw == "something odd here"

    def test_unknown_dose_unit_is_flagged_but_quantity_kept(self):
        got = parse_chemicals_added("BW-210 3 drums")
        assert got.value[0].quantity == 3.0
        assert codes.UNKNOWN_DOSE_UNIT in got.issues


class TestDoseAttribution:
    def test_single_system_visit_is_attributable(self):
        assert doses_are_attributable(1) is True

    @pytest.mark.parametrize("count", [0, 2, 5])
    def test_multi_or_zero_system_visit_is_not_attributable(self, count):
        """85% of chemical-bearing visits; attribution here would be invention."""
        assert doses_are_attributable(count) is False
