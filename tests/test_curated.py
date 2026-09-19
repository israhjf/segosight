"""Curated tier: control limits, trends, coverage, escalation and alerting.

These tests encode the operational conclusions the product is built to reach,
so a regression that quietly loses a finding fails the suite.
"""

from __future__ import annotations

import datetime as dt

import pytest

from segosight.curated.alerts import TABLE as ALERTS
from segosight.curated.assessments import TABLE as ASSESSMENTS
from segosight.curated.coverage import TABLE as COVERAGE
from segosight.curated.coverage import _within_window
from segosight.curated.microbio import TABLE as MICROBIO
from segosight.curated.programs import SeasonalClosure
from segosight.curated.trends import TABLE as TRENDS
from segosight.curated.trends import find_runs, resample_weekly


class TestProgramConfig:
    def test_thresholds_are_not_hard_coded(self, programs):
        assert programs.rule_version == "treatment_guidelines_rev6"
        assert programs.limit_for("CT-STD", "conductivity").upper == 1800
        assert programs.limit_for("BP-HP", "conductivity").upper == 1500

    def test_hp_boiler_is_tighter_than_standard(self, programs):
        """Section 6.2: normal on BP-STD is a serious exceedance on BP-HP."""
        std = programs.limit_for("BP-STD", "conductivity")
        hp = programs.limit_for("BP-HP", "conductivity")
        assert hp.upper < std.lower

    def test_cadence_ignores_contract_terms_in_the_frequency_cell(self, programs):
        assert programs.cadence_for("monthly (seasonal: closed mid-May to mid-Oct)") == 30
        assert programs.cadence_for("weekly") == 7

    def test_section_6_3_exception_overrides_the_generic_band(self, programs):
        generic = programs.limit_for("CL-M", "molybdate")
        tooling = programs.limit_for("CL-M", "molybdate", "SYS-0044")
        assert generic.kind == "band"
        assert tooling.kind == "band_with_target"


class TestProgramAwareAssessment:
    def test_hc2_wide_band_is_honoured(self, warehouse):
        """Section 6.1: 1800-3400 on an enrolled HC2 tower is not an exceedance."""
        false_positives = warehouse.execute(
            f"""SELECT count(*) FROM {ASSESSMENTS}
                WHERE governing_program = 'CT-HC2' AND parameter_code = 'conductivity'
                  AND out_of_band AND band_source = 'CT-HC2:conditional'"""
        ).fetchone()[0]
        assert false_positives == 0

    def test_hc2_reverts_to_ct_std_when_a_condition_actually_fails(self, warehouse):
        """SYS-0016 inhibitor fell to 11 ppm on 2026-07-02, below the 12 required."""
        row = warehouse.execute(
            f"""SELECT count(*), any_value(explanation) FROM {ASSESSMENTS}
                WHERE band_source = 'CT-STD:fallback' AND system_id = 'SYS-0016'"""
        ).fetchone()
        assert row[0] > 0
        assert "inhibitor" in row[1] and "reverted to CT-STD" in row[1]

    def test_unconfirmed_conditions_never_produce_an_exceedance(self, warehouse):
        """A BMS row measures conductivity alone; that is not a condition failure."""
        bad = warehouse.execute(
            f"""SELECT count(*) FROM {ASSESSMENTS}
                WHERE band_source = 'CT-HC2:unconfirmed' AND out_of_band"""
        ).fetchone()[0]
        assert bad == 0

    def test_section_6_3_reading_is_compliant_but_below_target(self, warehouse):
        """Answers the question Aaron Silva wrote down: is 210 a problem?"""
        row = warehouse.execute(
            f"""SELECT status, explanation FROM {ASSESSMENTS}
                WHERE system_id = 'SYS-0044' AND parameter_code = 'molybdate'
                  AND normalized_value = 210 LIMIT 1"""
        ).fetchone()
        assert row[0] == "below_target"
        assert "compliant" in row[1] and "225" in row[1]

    def test_every_assessment_records_its_rule_version(self, warehouse):
        missing = warehouse.execute(
            f"SELECT count(*) FROM {ASSESSMENTS} WHERE rule_version IS NULL"
        ).fetchone()[0]
        assert missing == 0

    def test_trend_only_parameters_are_not_judged(self, warehouse):
        """Closed-loop conductivity: 'record for trend; no fixed limit'."""
        statuses = {
            r[0]
            for r in warehouse.execute(
                f"""SELECT DISTINCT status FROM {ASSESSMENTS}
                    WHERE limit_kind = 'trend_only'"""
            ).fetchall()
        }
        assert statuses <= {"not_evaluated"}


class TestTrendDetection:
    def test_finds_a_minimal_run(self):
        points = [(dt.datetime(2026, 3, d), v) for d, v in enumerate([1, 2, 3], start=1)]
        assert find_runs(points, 3) == [("rising", 0, 2)]

    def test_ignores_a_run_that_is_too_short(self):
        points = [(dt.datetime(2026, 3, d), v) for d, v in enumerate([1, 2], start=1)]
        assert find_runs(points, 3) == []

    def test_a_flat_series_has_no_trend(self):
        points = [(dt.datetime(2026, 3, d), 1.0) for d in range(1, 6)]
        assert find_runs(points, 3) == []

    def test_direction_change_closes_a_run(self):
        points = [
            (dt.datetime(2026, 3, d), v) for d, v in enumerate([1, 2, 3, 4, 3, 2, 1], start=1)
        ]
        assert find_runs(points, 3) == [("rising", 0, 3), ("falling", 3, 6)]

    def test_weekly_resampling_uses_the_median(self):
        points = [
            (dt.datetime(2026, 3, 2), 10.0),
            (dt.datetime(2026, 3, 3), 1000.0),  # spike
            (dt.datetime(2026, 3, 4), 12.0),
        ]
        assert resample_weekly(points) == [(dt.datetime(2026, 3, 2), 12.0)]

    def test_bms_series_are_resampled_not_evaluated_raw(self, warehouse):
        grains = {
            r[0]
            for r in warehouse.execute(
                f"""SELECT DISTINCT sample_grain FROM {TRENDS}
                    WHERE collection_method = 'bms'"""
            ).fetchall()
        }
        assert grains == {"weekly_median"}

    def test_the_corrosion_trend_is_detected_within_band(self, warehouse):
        """The whole thesis: SYS-0006 iron, never breaching 2.0 ppm."""
        rows = warehouse.execute(
            f"""SELECT min(started_at), max(last_value), bool_and(all_within_band)
                FROM {TRENDS}
                WHERE measurement_series_id = 'SYS-0006:iron:field'
                  AND direction = 'rising'"""
        ).fetchone()
        assert rows[0].date() <= dt.date(2026, 4, 14)
        assert rows[1] == pytest.approx(1.50)
        assert rows[2] is True

    def test_it_fires_months_before_the_failure(self, warehouse):
        first = warehouse.execute(
            f"""SELECT min(ended_at) FROM {TRENDS}
                WHERE measurement_series_id = 'SYS-0006:iron:field'
                  AND direction = 'rising' AND run_length >= 3"""
        ).fetchone()[0]
        failure = dt.date(2026, 9, 2)
        assert (failure - first.date()).days > 120


class TestSeasonalWindow:
    @pytest.fixture
    def summer(self):
        return SeasonalClosure("F-0008", "05-15", "10-15", "")

    @pytest.mark.parametrize("day", [dt.date(2026, 5, 20), dt.date(2026, 9, 11)])
    def test_inside_window(self, summer, day):
        assert _within_window(summer, day) is True

    @pytest.mark.parametrize("day", [dt.date(2026, 5, 1), dt.date(2026, 11, 1)])
    def test_outside_window(self, summer, day):
        assert _within_window(summer, day) is False

    def test_window_crossing_new_year(self):
        winter = SeasonalClosure("F-X", "11-01", "03-01", "")
        assert _within_window(winter, dt.date(2026, 12, 25)) is True
        assert _within_window(winter, dt.date(2026, 1, 15)) is True
        assert _within_window(winter, dt.date(2026, 6, 1)) is False


class TestCoverage:
    def test_the_unserviced_a_tier_account_is_critical(self, warehouse):
        row = warehouse.execute(
            f"""SELECT status, days_since_visit, round(cadence_ratio, 1),
                       account_tier, technician_departed
                FROM {COVERAGE} WHERE facility_id = 'F-0004'"""
        ).fetchone()
        assert row[0] == "critically_overdue"
        assert row[1] >= 60 and row[2] >= 8.0
        assert row[3] == "A" and row[4] is True

    def test_the_departed_technician_is_named_in_the_explanation(self, warehouse):
        explanation = warehouse.execute(
            f"SELECT explanation FROM {COVERAGE} WHERE facility_id = 'F-0004'"
        ).fetchone()[0]
        assert "Kyle Bishop" in explanation

    def test_the_seasonal_site_is_not_reported_as_neglected(self, warehouse):
        """123 days without a visit and entirely on schedule."""
        row = warehouse.execute(
            f"""SELECT status, seasonally_closed, days_since_visit
                FROM {COVERAGE} WHERE facility_id = 'F-0008'"""
        ).fetchone()
        assert row[0] == "seasonally_closed"
        assert row[1] is True
        assert row[2] > 100  # would be the worst gap in the corpus otherwise

    def test_no_seasonal_site_raises_a_coverage_alert(self, warehouse):
        leaked = warehouse.execute(
            f"""SELECT count(*) FROM {ALERTS} a
                JOIN {COVERAGE} c USING (facility_id)
                WHERE a.risk_class = 'coverage_gap' AND c.seasonally_closed"""
        ).fetchone()[0]
        assert leaked == 0

    def test_as_of_date_is_data_derived_not_the_system_clock(self, warehouse):
        as_of = warehouse.execute(
            f"SELECT DISTINCT as_of_date FROM {COVERAGE}"
        ).fetchone()[0]
        assert as_of == dt.date(2026, 9, 11)


class TestMicrobiologicalLadder:
    def test_healthcare_sites_use_the_tighter_ladder(self, warehouse):
        ladders = dict(
            warehouse.execute(
                f"SELECT DISTINCT facility_id, ladder FROM {MICROBIO}"
            ).fetchall()
        )
        assert ladders.get("F-0001") == "healthcare"

    def test_two_consecutive_10_4_triggers_director_notification(self, warehouse):
        row = warehouse.execute(
            f"""SELECT observed_at::DATE FROM {MICROBIO}
                WHERE system_id = 'SYS-0004'
                  AND escalation_type = 'director_notification'
                ORDER BY observed_at LIMIT 1"""
        ).fetchone()
        assert row[0] == dt.date(2026, 6, 15)

    def test_a_single_10_5_triggers_urgent_cleaning(self, warehouse):
        count = warehouse.execute(
            f"""SELECT count(*) FROM {MICROBIO}
                WHERE system_id = 'SYS-0004'
                  AND escalation_type = 'urgent_offline_clean'"""
        ).fetchone()[0]
        assert count >= 4

    def test_a_late_work_order_does_not_retroactively_document(self, warehouse):
        """WO-0160 was raised 2026-09-09; it cannot close a June escalation."""
        row = warehouse.execute(
            f"""SELECT documented, days_undocumented FROM {MICROBIO}
                WHERE system_id = 'SYS-0004'
                  AND escalation_type = 'director_notification'
                ORDER BY observed_at LIMIT 1"""
        ).fetchone()
        assert row[0] is False
        assert row[1] > 80

    def test_the_compliance_gap_is_surfaced_in_full(self, warehouse):
        undocumented = warehouse.execute(
            f"SELECT count(*) FROM {MICROBIO} WHERE NOT documented"
        ).fetchone()[0]
        assert undocumented >= 15


class TestAlertQueue:
    def test_the_queue_is_small_enough_to_read(self, warehouse):
        total = warehouse.execute(f"SELECT count(*) FROM {ALERTS}").fetchone()[0]
        assert 10 <= total <= 45

    def test_alerts_are_deduplicated_by_fingerprint(self, warehouse):
        """SYS-0006's five iron runs must become one alert, not five."""
        duplicates = warehouse.execute(
            f"""SELECT fingerprint FROM {ALERTS}
                GROUP BY 1 HAVING count(*) > 1"""
        ).fetchall()
        assert duplicates == []

        iron = warehouse.execute(
            f"""SELECT count(*), any_value(evidence_count) FROM {ALERTS}
                WHERE system_id = 'SYS-0006' AND risk_class = 'corrosion_trend'"""
        ).fetchone()
        assert iron[0] == 1 and iron[1] > 1

    def test_the_healthcare_escalation_ranks_first(self, warehouse):
        top = warehouse.execute(
            f"""SELECT risk_class, facility_id, severity FROM {ALERTS}
                ORDER BY priority_score DESC LIMIT 1"""
        ).fetchone()
        assert top == ("microbio_escalation", "F-0001", "critical")

    def test_every_alert_answers_dana_s_four_questions(self, warehouse):
        gaps = warehouse.execute(
            f"""SELECT count(*) FROM {ALERTS}
                WHERE title IS NULL OR why IS NULL OR consequence IS NULL
                   OR trim(why) = '' OR trim(consequence) = ''"""
        ).fetchone()[0]
        assert gaps == 0

    def test_priority_weights_account_tier_and_criticality(self, warehouse):
        """An A-tier critical system outranks a C-tier standard one at equal severity."""
        rows = warehouse.execute(
            f"""SELECT account_tier, priority_score FROM {ALERTS}
                WHERE severity = 'high' AND account_tier IS NOT NULL"""
        ).fetchall()
        by_tier = {}
        for tier, score in rows:
            by_tier.setdefault(tier, []).append(score)
        if "A" in by_tier and "C" in by_tier:
            assert max(by_tier["A"]) > max(by_tier["C"])

    def test_the_boiler_corrosion_alert_exists_and_explains_itself(self, warehouse):
        row = warehouse.execute(
            f"""SELECT severity, why, consequence FROM {ALERTS}
                WHERE system_id = 'SYS-0006' AND risk_class = 'corrosion_trend'"""
        ).fetchone()
        assert row[0] in ("high", "critical")
        assert "inside its band" in row[1]
        assert "action level" in row[2]

    def test_the_closed_loop_collapse_is_surfaced(self, warehouse):
        """Pintura SYS-0019: nitrite 1050 -> 410 with no recovery."""
        row = warehouse.execute(
            f"""SELECT severity, why FROM {ALERTS}
                WHERE system_id = 'SYS-0019' AND risk_class = 'residual_loss'"""
        ).fetchone()
        assert row is not None
        assert "410" in row[1] and "not recovering" in row[1]

    def test_normal_sawtooth_consumption_does_not_alert(self, warehouse):
        """Residual decay that recovers after dosing is operation, not a finding."""
        residual = warehouse.execute(
            f"SELECT count(*) FROM {ALERTS} WHERE risk_class = 'residual_loss'"
        ).fetchone()[0]
        assert residual <= 15

    def test_boiler_conductivity_cycling_is_not_a_scaling_alert(self, warehouse):
        """Blowdown cycles a boiler by design; the guideline example is towers."""
        boilers = warehouse.execute(
            f"""SELECT count(*) FROM {ALERTS} a
                JOIN canonical.system s USING (system_id)
                WHERE a.risk_class = 'scaling_risk' AND s.system_type = 'steam_boiler'"""
        ).fetchone()[0]
        assert boilers == 0
