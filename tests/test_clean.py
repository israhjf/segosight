"""Clean-tier tests: versioning, long-form explosion, and evidence integrity.

The final class asserts that the operationally important signals survive
normalization. Those are regression guards on the product's core claims, not
just on the plumbing.
"""

from __future__ import annotations

import pytest

from segosight.features.chemistry.clean.readings import TABLE as LONG
from segosight.features.ingestion.clean.versioning import TABLE as VERSIONS
from segosight.features.ingestion.clean.versioning import superseded


class TestVersioning:
    @pytest.mark.september
    def test_only_the_two_known_keys_have_multiple_versions(self, warehouse):
        assert {(e, k) for e, k, _ in superseded(warehouse)} == {
            ("water_readings", "RD-00923"),
            ("systems", "SYS-0006"),
        }

    @pytest.mark.september
    def test_corrected_reading_supersedes_the_original(self, warehouse):
        rows = warehouse.execute(
            f"""SELECT batch_name, is_current, is_superseded
                FROM {VERSIONS} WHERE business_key='RD-00923'
                ORDER BY batch_sequence"""
        ).fetchall()
        assert rows == [("legacy", False, True), ("2026-09", True, False)]

    @pytest.mark.september
    def test_the_superseded_version_is_retained_not_deleted(self, warehouse):
        """Guidelines section 2: annotate rather than delete."""
        count = warehouse.execute(
            f"SELECT count(*) FROM {VERSIONS} WHERE business_key='RD-00923'"
        ).fetchone()[0]
        assert count == 2

    @pytest.mark.september
    def test_decommissioned_system_supersedes_its_active_record(self, warehouse):
        current = warehouse.execute(
            f"""SELECT payload FROM {VERSIONS}
                WHERE entity='systems' AND business_key='SYS-0006' AND is_current"""
        ).fetchone()[0]
        assert '"status":"decommissioned"' in current.replace(" ", "")

    @pytest.mark.september
    def test_replacement_asset_is_a_separate_identity(self, warehouse):
        """SYS-0101 is a different physical unit, not a rename of SYS-0006."""
        rows = warehouse.execute(
            f"""SELECT business_key, count(*) FROM {VERSIONS}
                WHERE entity='systems' AND business_key IN ('SYS-0006','SYS-0101')
                GROUP BY 1 ORDER BY 1"""
        ).fetchall()
        assert rows == [("SYS-0006", 2), ("SYS-0101", 1)]

    def test_every_business_key_has_exactly_one_current_version(self, warehouse):
        bad = warehouse.execute(
            f"""SELECT entity, business_key FROM {VERSIONS} WHERE is_current
                GROUP BY 1,2 HAVING count(*) <> 1"""
        ).fetchall()
        assert bad == []


class TestLongFormExplosion:
    @pytest.mark.september
    def test_one_row_per_populated_parameter(self, warehouse):
        total = warehouse.execute(f"SELECT count(*) FROM {LONG}").fetchone()[0]
        assert total == 6502

    def test_each_parameter_has_exactly_one_standard_unit(self, warehouse):
        bad = warehouse.execute(
            f"""SELECT parameter_code FROM {LONG}
                GROUP BY 1 HAVING count(DISTINCT standard_unit) > 1"""
        ).fetchall()
        assert bad == []

    @pytest.mark.september
    def test_molybdate_is_split_out_from_inhibitor(self, warehouse):
        """Same source column, two parameters, two control bands."""
        counts = dict(
            warehouse.execute(
                f"""SELECT parameter_code, count(*) FROM {LONG}
                    WHERE parameter_code IN ('molybdate','inhibitor') GROUP BY 1"""
            ).fetchall()
        )
        assert counts == {"inhibitor": 374, "molybdate": 91}

    def test_molybdate_and_inhibitor_occupy_disjoint_ranges(self, warehouse):
        moly_min, inhib_max = warehouse.execute(
            f"""SELECT
                  min(normalized_value) FILTER (WHERE parameter_code='molybdate'),
                  max(normalized_value) FILTER (WHERE parameter_code='inhibitor')
                FROM {LONG} WHERE quality_status='valid'"""
        ).fetchone()
        assert moly_min > inhib_max

    def test_raw_and_normalized_values_are_both_retained(self, warehouse):
        row = warehouse.execute(
            f"""SELECT raw_value_text, raw_unit, normalized_value, standard_unit
                FROM {LONG} WHERE reading_id='RD-00001'
                AND parameter_code='conductivity'"""
        ).fetchone()
        assert row == ("2.91", "mS/cm", 2910.0, "uS/cm")

    def test_dipslide_is_stored_as_its_exponent(self, warehouse):
        rows = warehouse.execute(
            f"""SELECT DISTINCT raw_value_text, normalized_value FROM {LONG}
                WHERE parameter_code='dipslide' ORDER BY normalized_value"""
        ).fetchall()
        assert rows == [("10^2", 2.0), ("10^3", 3.0), ("10^4", 4.0), ("10^5", 5.0)]


class TestQuarantine:
    @pytest.mark.september
    def test_impossible_ph_is_invalid_and_not_current(self, warehouse):
        row = warehouse.execute(
            f"""SELECT quality_status, is_current FROM {LONG}
                WHERE reading_id='RD-00923' AND parameter_code='ph'
                AND raw_value_text='91.2'"""
        ).fetchone()
        assert row == ("invalid", False)

    @pytest.mark.september
    def test_the_correction_is_current_and_valid(self, warehouse):
        row = warehouse.execute(
            f"""SELECT normalized_value, quality_status, is_current FROM {LONG}
                WHERE reading_id='RD-00923' AND parameter_code='ph'
                AND raw_value_text='9.1'"""
        ).fetchone()
        assert row == (9.1, "valid", True)

    def test_zero_conductivity_rows_are_suspect(self, warehouse):
        ids = {
            r[0]
            for r in warehouse.execute(
                f"""SELECT reading_id FROM {LONG}
                    WHERE parameter_code='conductivity' AND quality_status='suspect'"""
            ).fetchall()
        }
        assert ids == {"RD-00439", "RD-00874", "RD-01486"}

    @pytest.mark.september
    def test_undeclared_units_are_unresolved_not_silently_valid(self, warehouse):
        count = warehouse.execute(
            f"SELECT count(*) FROM {LONG} WHERE quality_status='unresolved'"
        ).fetchone()[0]
        assert count == 14

    def test_quarantined_rows_keep_their_raw_evidence(self, warehouse):
        nulls = warehouse.execute(
            f"""SELECT count(*) FROM {LONG}
                WHERE quality_status <> 'valid' AND raw_value_text IS NULL"""
        ).fetchone()[0]
        assert nulls == 0


class TestEvidenceIntegrity:
    """The signals the product exists to surface must survive normalization."""

    def test_unit_switch_does_not_create_a_step_change(self, warehouse):
        """SYS-0014 BMS switches mS/cm -> uS/cm on 2026-07-14."""
        before, after = warehouse.execute(
            f"""SELECT
                  avg(normalized_value) FILTER (WHERE observed_at < '2026-07-14'),
                  avg(normalized_value) FILTER (WHERE observed_at >= '2026-07-14')
                FROM {LONG}
                WHERE source_system_ref='SYS-0014' AND parameter_code='conductivity'
                  AND collection_method='bms' AND quality_status='valid'"""
        ).fetchone()
        assert abs(before - after) / before < 0.05

    @pytest.mark.september
    def test_gpg_hardness_becomes_comparable_to_ppm_hardness(self, warehouse):
        value = warehouse.execute(
            f"""SELECT normalized_value FROM {LONG}
                WHERE reading_id='RB-0062' AND parameter_code='total_hardness'"""
        ).fetchone()[0]
        assert value == pytest.approx(22.5 * 17.1)

    def test_the_corrosion_trend_survives_normalization(self, warehouse):
        """SYS-0006 field iron climbs 0.19 -> 1.50 before the boiler failed."""
        rows = warehouse.execute(
            f"""SELECT normalized_value FROM {LONG}
                WHERE source_system_ref='SYS-0006' AND parameter_code='iron'
                  AND collection_method='field' AND is_current
                  AND quality_status='valid' ORDER BY observed_at"""
        ).fetchall()
        values = [r[0] for r in rows]
        assert len(values) == 26
        assert values[0] == pytest.approx(0.19)
        assert values[-1] == pytest.approx(1.50)

    def test_the_trend_never_breaches_the_action_level(self, warehouse):
        """Guidelines 4.2: waiting for the 2.0 ppm limit means acting too late."""
        peak = warehouse.execute(
            f"""SELECT max(normalized_value) FROM {LONG}
                WHERE source_system_ref='SYS-0006' AND parameter_code='iron'
                  AND collection_method='field' AND quality_status='valid'"""
        ).fetchone()[0]
        assert peak < 2.0

    def test_lab_and_field_series_stay_separable(self, warehouse):
        """Pooling them would flatten the signal; the grain must allow a split."""
        stats = dict(
            (r[0], (r[1], r[2]))
            for r in warehouse.execute(
                f"""SELECT collection_method, count(*), max(normalized_value)
                    FROM {LONG}
                    WHERE source_system_ref IN ('SYS-0006','BONF-OGD-B2')
                      AND parameter_code='iron' GROUP BY 1"""
            ).fetchall()
        )
        assert stats["field"][1] == pytest.approx(1.50)
        assert stats["lab"][1] == pytest.approx(0.51)
        # The lab peak is a third of the field peak on the same equipment.
        assert stats["lab"][1] < stats["field"][1] / 2

    def test_healthcare_dipslide_escalation_is_visible(self, warehouse):
        """SYS-0004 at a hospital: sustained 10^4+, repeated 10^5."""
        rows = warehouse.execute(
            f"""SELECT count(*) FILTER (WHERE normalized_value >= 4),
                       count(*) FILTER (WHERE normalized_value >= 5)
                FROM {LONG}
                WHERE source_system_ref='SYS-0004' AND parameter_code='dipslide'
                  AND is_current"""
        ).fetchone()
        assert rows[0] >= 10 and rows[1] >= 4
