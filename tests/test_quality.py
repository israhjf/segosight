"""Physical-plausibility and dipslide tests."""

import pytest

from segosight.shared.normalize import codes
from segosight.shared.normalize.numeric import parse_number
from segosight.features.chemistry.quality import assess, parse_dipslide


class TestParseNumber:
    def test_plain_value(self):
        assert parse_number("2675.0").value == pytest.approx(2675.0)

    def test_integer_style_value(self):
        assert parse_number("2922").value == pytest.approx(2922.0)

    @pytest.mark.parametrize("empty", ["", "  ", None])
    def test_empty_cell_is_absence_not_error(self, empty):
        got = parse_number(empty)
        assert got.value is None and got.issues == ()

    def test_thousands_separator_tolerated(self):
        assert parse_number("53,900").value == pytest.approx(53900.0)

    def test_garbage_is_flagged_not_dropped(self):
        got = parse_number("n/a")
        assert got.value is None
        assert codes.UNPARSEABLE_NUMBER in got.issues
        assert got.raw == "n/a"


class TestDipslide:
    @pytest.mark.parametrize(
        "raw,expected", [("10^2", 2.0), ("10^3", 3.0), ("10^4", 4.0), ("10^5", 5.0)]
    )
    def test_observed_ladder_parses_to_exponent(self, raw, expected):
        assert parse_dipslide(raw).value == pytest.approx(expected)

    def test_exponent_ordering_matches_escalation_ladder(self):
        """10^5 must sort above 10^4 numerically for threshold logic."""
        assert parse_dipslide("10^5").value > parse_dipslide("10^4").value

    def test_empty_is_absence(self):
        assert parse_dipslide("").value is None
        assert parse_dipslide("").issues == ()

    def test_malformed_is_flagged(self):
        got = parse_dipslide("high")
        assert got.value is None
        assert codes.MALFORMED_DIPSLIDE in got.issues


class TestPhysicalImpossibility:
    def test_ph_above_scale_is_quarantined(self):
        # RD-00923 as originally exported: ph=91.2 (later corrected to 9.1).
        status, issues = assess("ph", 91.2)
        assert status == codes.INVALID
        assert codes.PH_OUT_OF_SCALE in issues

    def test_ph_below_scale_is_quarantined(self):
        status, _ = assess("ph", -1.0)
        assert status == codes.INVALID

    @pytest.mark.parametrize("ph", [0.0, 7.0, 11.4, 14.0])
    def test_in_scale_ph_is_valid(self, ph):
        assert assess("ph", ph)[0] == codes.VALID

    def test_impossible_value_is_quarantined_without_needing_a_correction(self):
        """The strict variant: uncorrected typos are caught on their own."""
        status, _ = assess("ph", 91.2)
        assert status == codes.INVALID

    def test_negative_concentration_is_quarantined(self):
        status, issues = assess("iron", -0.3)
        assert status == codes.INVALID
        assert codes.NEGATIVE_CONCENTRATION in issues


class TestZeroHandling:
    def test_zero_conductivity_is_suspect_bms_dropout(self):
        # RD-00439, RD-00874, RD-01486
        status, issues = assess("conductivity", 0.0)
        assert status == codes.SUSPECT
        assert codes.ZERO_CONDUCTIVITY in issues

    def test_zero_hardness_is_valid_because_it_is_the_boiler_target(self):
        """22 rows read 0.0 hardness; guidelines want feedwater below 2 ppm."""
        assert assess("total_hardness", 0.0) == (codes.VALID, ())

    def test_zero_sulfite_is_valid_data_and_a_finding_for_the_rules_layer(self):
        """RD-01378: depletion is a real result, not a parse defect."""
        assert assess("sulfite", 0.0) == (codes.VALID, ())

    def test_null_is_valid(self):
        assert assess("iron", None) == (codes.VALID, ())
