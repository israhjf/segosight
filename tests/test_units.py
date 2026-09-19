"""Unit resolution and conversion tests.

Literals are verbatim from water_readings.csv / water_readings_2026-09.csv.
"""

import pytest

from segosight.shared.normalize import codes
from segosight.features.chemistry.units import (
    PARAMETERS,
    convert,
    parse_units_declaration,
    resolve_parameter,
)


class TestParseUnitsDeclaration:
    def test_multi_key_declaration(self):
        got = parse_units_declaration("cond=uS/cm;hard=ppm CaCO3;cl=ppm;inhib=ppm")
        assert got == {
            "cond": "uS/cm",
            "hard": "ppm CaCO3",
            "cl": "ppm",
            "inhib": "ppm",
        }

    def test_single_key_declaration(self):
        assert parse_units_declaration("cond=mS/cm") == {"cond": "mS/cm"}

    def test_unit_value_may_contain_spaces(self):
        assert parse_units_declaration("hard=ppm CaCO3") == {"hard": "ppm CaCO3"}

    @pytest.mark.parametrize("empty", ["", None])
    def test_missing_declaration_is_empty_dict(self, empty):
        assert parse_units_declaration(empty) == {}

    def test_malformed_segment_is_skipped_not_fatal(self):
        # A broken segment must degrade one parameter, not lose the row.
        assert parse_units_declaration("cond=uS/cm;garbage;=ppm;hard=") == {
            "cond": "uS/cm"
        }


class TestPolymorphicInhibitorColumn:
    """`inhibitor_ppm` carries molybdate or inhibitor depending on declaration."""

    def test_moly_declaration_resolves_to_molybdate(self):
        # RB-0012: CL-M loop, inhibitor_ppm=234.0, units=cond=uS/cm;moly=ppm
        got = resolve_parameter(
            "inhibitor_ppm", parse_units_declaration("cond=uS/cm;moly=ppm")
        )
        assert got.parameter.code == "molybdate"
        assert got.issues == ()

    def test_inhib_declaration_resolves_to_inhibitor(self):
        # RB-0013: CT tower, inhibitor_ppm=13.9, units=...;inhib=ppm
        got = resolve_parameter(
            "inhibitor_ppm",
            parse_units_declaration("cond=uS/cm;hard=ppm CaCO3;cl=ppm;inhib=ppm"),
        )
        assert got.parameter.code == "inhibitor"

    def test_same_column_two_parameters_two_bands(self):
        """234 ppm is normal molybdate but absurd as a CT inhibitor residual."""
        moly = resolve_parameter("inhibitor_ppm", {"moly": "ppm"}).parameter.code
        inhib = resolve_parameter("inhibitor_ppm", {"inhib": "ppm"}).parameter.code
        assert moly != inhib

    def test_undeclared_falls_back_and_is_flagged_never_guessed(self):
        # 4 real rows populate inhibitor_ppm with no declaration. We must not
        # infer identity from magnitude or treatment program in this layer.
        got = resolve_parameter("inhibitor_ppm", {})
        assert got.raw_unit is None
        assert codes.UNIT_NOT_DECLARED in got.issues


class TestConductivityConversion:
    def test_millisiemens_scales_by_one_thousand(self):
        # RD-00001: conductivity=2.91, units=cond=mS/cm
        got = convert(PARAMETERS["conductivity"], 2.91, "mS/cm")
        assert got.value == pytest.approx(2910.0)
        assert got.detail["converted"] is True

    def test_microsiemens_passes_through_unscaled(self):
        # RB-0002: conductivity=2922, units=cond=uS/cm
        got = convert(PARAMETERS["conductivity"], 2922.0, "uS/cm")
        assert got.value == pytest.approx(2922.0)
        assert got.detail["converted"] is False

    def test_the_mid_file_unit_switch_is_not_a_step_change(self):
        """SYS-0014 BMS switches mS/cm -> uS/cm on 2026-07-14.

        Honouring the declaration, the readings either side are continuous.
        Ignoring it manufactures a 1000x excursion on a critical CT-HC2 tower.
        """
        before = convert(PARAMETERS["conductivity"], 2.93, "mS/cm").value
        after = convert(PARAMETERS["conductivity"], 2706.0, "uS/cm").value
        assert abs(before - after) / before < 0.15
        # And the trap we are avoiding:
        assert after / 2.93 > 900


class TestHardnessConversion:
    def test_grains_per_gallon_scales_by_17_1(self):
        # RB-0062: total_hardness=22.5, units=...;hard=gpg
        got = convert(PARAMETERS["total_hardness"], 22.5, "gpg")
        assert got.value == pytest.approx(384.75)

    def test_ppm_caco3_passes_through(self):
        got = convert(PARAMETERS["total_hardness"], 486.0, "ppm CaCO3")
        assert got.value == pytest.approx(486.0)

    def test_gpg_row_is_comparable_to_ppm_rows_after_conversion(self):
        # RB-0062 (gpg) vs RB-0060 (ppm CaCO3), both CT towers.
        gpg = convert(PARAMETERS["total_hardness"], 22.5, "gpg").value
        ppm = convert(PARAMETERS["total_hardness"], 380.0, "ppm CaCO3").value
        assert abs(gpg - ppm) < 100  # same order; unconverted it would be ~17x off


class TestConversionSafety:
    def test_unrecognized_unit_leaves_value_unconverted_and_flags_it(self):
        got = convert(PARAMETERS["conductivity"], 2.91, "S/m")
        assert got.value == 2.91
        assert codes.UNIT_UNRECOGNIZED in got.issues
        assert got.detail["converted"] is False

    def test_undeclared_unit_never_converts(self):
        """Guidelines: convert only when notation confirms the source unit."""
        got = convert(PARAMETERS["conductivity"], 2.91, None)
        assert got.value == 2.91
        assert codes.UNIT_NOT_DECLARED in got.issues

    def test_none_value_is_passthrough(self):
        assert convert(PARAMETERS["conductivity"], None, "mS/cm").value is None

    def test_unknown_column_raises(self):
        with pytest.raises(KeyError):
            resolve_parameter("not_a_column", {})


class TestFixedUnitColumns:
    @pytest.mark.parametrize(
        "column,expected", [("ph", "ph"), ("iron", "iron"), ("free_halogen", "free_halogen")]
    )
    def test_never_declared_columns_resolve_without_issues(self, column, expected):
        got = resolve_parameter(column, {})
        assert got.parameter.code == expected
        assert got.issues == ()
