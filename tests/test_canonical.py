"""Canonical tier: identity resolution, merges, lineage and series identity."""

from __future__ import annotations

import pytest

from segosight.features.identity.canonical.entities import CUSTOMER_TABLE, FACILITY_TABLE, SYSTEM_TABLE
from segosight.features.chemistry.canonical.series import SERIES_TABLE
from segosight.features.chemistry.canonical.series import TABLE as EVENTS
from segosight.features.identity.canonical.crosswalk import EMPLOYEE_TABLE, LINEAGE_TABLE
from segosight.features.identity.canonical.crosswalk import TABLE as CROSSWALK


class TestCrosswalk:
    def test_every_mapping_carries_evidence_and_rationale(self, warehouse):
        gaps = warehouse.execute(
            f"""SELECT source_id FROM {CROSSWALK}
                WHERE evidence IS NULL OR rationale IS NULL OR rationale = ''"""
        ).fetchall()
        assert gaps == []

    def test_confidence_gates_alert_eligibility(self, warehouse):
        rows = warehouse.execute(
            f"SELECT DISTINCT confidence, alert_eligible FROM {CROSSWALK} ORDER BY 1"
        ).fetchall()
        assert rows == [("high", True), ("medium", False)]

    def test_webbs_hedge_is_preserved_as_medium_confidence(self, warehouse):
        """The note separates "sure of" from "mostly sure of"; keep the split."""
        medium = {
            r[0]
            for r in warehouse.execute(
                f"""SELECT source_id FROM {CROSSWALK}
                    WHERE domain='sample_point' AND confidence='medium'"""
            ).fetchall()
        }
        assert medium == {"CLPK-B1", "MRMC-B1"}

    def test_all_six_lab_codes_are_mapped(self, warehouse):
        count = warehouse.execute(
            f"SELECT count(*) FROM {CROSSWALK} WHERE domain='sample_point'"
        ).fetchone()[0]
        assert count == 6


class TestCustomerMerge:
    def test_retired_customer_id_does_not_survive(self, warehouse):
        gone = warehouse.execute(
            f"SELECT count(*) FROM {CUSTOMER_TABLE} WHERE customer_id='CUST-0019'"
        ).fetchone()[0]
        assert gone == 0

    def test_surviving_account_keeps_its_own_attributes(self, warehouse):
        """The retired tier C / null-ACV row must not overwrite tier B / 24000."""
        row = warehouse.execute(
            f"""SELECT account_tier, acv_usd, merged_source_count
                FROM {CUSTOMER_TABLE} WHERE customer_id='CUST-0007'"""
        ).fetchone()
        assert row == ("B", 24000.0, 2)

    def test_exactly_one_customer_was_merged(self, warehouse):
        rows = warehouse.execute(
            f"""SELECT customer_id FROM {CUSTOMER_TABLE} WHERE merged_source_count > 1"""
        ).fetchall()
        assert rows == [("CUST-0007",)]


class TestFacilityMerge:
    @pytest.mark.parametrize("retired", ["F-0021", "F-0022"])
    def test_duplicate_facility_ids_do_not_survive(self, warehouse, retired):
        gone = warehouse.execute(
            f"SELECT count(*) FROM {FACILITY_TABLE} WHERE facility_id=?", [retired]
        ).fetchone()[0]
        assert gone == 0

    def test_surviving_facilities_keep_their_own_names(self, warehouse):
        rows = dict(
            warehouse.execute(
                f"""SELECT facility_id, facility_name FROM {FACILITY_TABLE}
                    WHERE facility_id IN ('F-0003','F-0009')"""
            ).fetchall()
        )
        assert rows == {"F-0003": "Clearfield Plant", "F-0009": "Bottling Plant"}

    def test_merged_facilities_own_the_equipment_their_visits_referenced(self, warehouse):
        """The duplicates owned zero systems; the survivors own the real ones."""
        counts = dict(
            warehouse.execute(
                f"""SELECT facility_id, count(*) FROM {SYSTEM_TABLE}
                    WHERE facility_id IN ('F-0003','F-0009') GROUP BY 1"""
            ).fetchall()
        )
        assert counts == {"F-0003": 2, "F-0009": 2}

    def test_every_facility_belongs_to_a_canonical_customer(self, warehouse):
        orphans = warehouse.execute(
            f"""SELECT f.facility_id FROM {FACILITY_TABLE} f
                LEFT JOIN {CUSTOMER_TABLE} c USING (customer_id)
                WHERE c.customer_id IS NULL"""
        ).fetchall()
        assert orphans == []


class TestAssetLineage:
    @pytest.mark.september
    def test_replacement_is_lineage_not_a_merge(self, warehouse):
        """Both IDs must remain real, distinct systems."""
        merged = warehouse.execute(
            f"""SELECT count(*) FROM {CROSSWALK}
                WHERE domain='system' AND source_id IN ('SYS-0006','SYS-0101')"""
        ).fetchone()[0]
        assert merged == 0

        both = warehouse.execute(
            f"""SELECT count(*) FROM {SYSTEM_TABLE}
                WHERE system_id IN ('SYS-0006','SYS-0101')"""
        ).fetchone()[0]
        assert both == 2

    def test_lineage_link_records_the_replacement(self, warehouse):
        row = warehouse.execute(
            f"""SELECT predecessor_id, successor_id, relationship
                FROM {LINEAGE_TABLE}"""
        ).fetchone()
        assert row == ("SYS-0006", "SYS-0101", "replacement_rental")

    @pytest.mark.september
    def test_the_failed_unit_is_decommissioned_and_the_rental_active(self, warehouse):
        rows = dict(
            warehouse.execute(
                f"""SELECT system_id, status FROM {SYSTEM_TABLE}
                    WHERE system_id IN ('SYS-0006','SYS-0101')"""
            ).fetchall()
        )
        assert rows == {"SYS-0006": "decommissioned", "SYS-0101": "active"}


class TestLabSamplePointResolution:
    def test_no_reading_event_is_orphaned(self, warehouse):
        orphans = warehouse.execute(
            f"SELECT count(*) FROM {EVENTS} WHERE facility_id IS NULL"
        ).fetchone()[0]
        assert orphans == 0

    def test_lab_codes_resolve_to_systems(self, warehouse):
        mapped = dict(
            warehouse.execute(
                f"""SELECT source_system_ref, any_value(system_id) FROM {EVENTS}
                    WHERE system_id_was_aliased GROUP BY 1"""
            ).fetchall()
        )
        assert mapped == {
            "BONF-OGD-B2": "SYS-0006",
            "BONF-CLF-B1": "SYS-0009",
            "SALT-HP1": "SYS-0032",
            "SALT-HP2": "SYS-0033",
            "CLPK-B1": "SYS-0041",
            "MRMC-B1": "SYS-0001",
        }

    def test_medium_confidence_readings_resolve_but_cannot_alert(self, warehouse):
        """The healthcare case: MRMC-B1 is ambiguous between two boilers."""
        rows = dict(
            (r[0], (r[1], r[2]))
            for r in warehouse.execute(
                f"""SELECT source_system_ref, count(*),
                           count(*) FILTER (WHERE alert_eligible)
                    FROM {EVENTS} WHERE system_id_was_aliased
                      AND system_id_confidence='medium' GROUP BY 1"""
            ).fetchall()
        )
        assert rows["MRMC-B1"][1] == 0
        assert rows["CLPK-B1"][1] == 0
        assert rows["MRMC-B1"][0] > 0  # resolved and visible, just not alerting

    def test_high_confidence_lab_readings_are_alert_eligible(self, warehouse):
        eligible = warehouse.execute(
            f"""SELECT count(*) FROM {EVENTS}
                WHERE source_system_ref='BONF-OGD-B2' AND alert_eligible"""
        ).fetchone()[0]
        assert eligible > 0

    def test_the_original_lab_code_is_retained(self, warehouse):
        """Provenance: an analyst must see which code the lab actually sent."""
        nulls = warehouse.execute(
            f"""SELECT count(*) FROM {EVENTS}
                WHERE system_id_was_aliased AND source_system_ref IS NULL"""
        ).fetchone()[0]
        assert nulls == 0


class TestMeasurementSeries:
    def test_series_separates_lab_from_field(self, warehouse):
        rows = dict(
            warehouse.execute(
                f"""SELECT measurement_series_id, observation_count
                    FROM {SERIES_TABLE}
                    WHERE system_id='SYS-0006' AND parameter_code='iron'"""
            ).fetchall()
        )
        assert rows == {"SYS-0006:iron:field": 26, "SYS-0006:iron:lab": 6}

    def test_series_id_is_built_from_canonical_system_not_lab_code(self, warehouse):
        bad = warehouse.execute(
            f"""SELECT count(*) FROM {SERIES_TABLE}
                WHERE measurement_series_id LIKE '%BONF%'
                   OR measurement_series_id LIKE '%MRMC%'"""
        ).fetchone()[0]
        assert bad == 0

    def test_mixed_unit_series_are_surfaced_for_review(self, warehouse):
        """The four BMS towers switched mS/cm -> uS/cm mid-series."""
        rows = {
            r[0]
            for r in warehouse.execute(
                f"SELECT measurement_series_id FROM {SERIES_TABLE} WHERE distinct_raw_units > 1"
            ).fetchall()
        }
        assert rows == {
            f"SYS-{n}:conductivity:bms" for n in ("0014", "0015", "0016", "0017")
        }

    def test_every_event_has_a_series(self, warehouse):
        nulls = warehouse.execute(
            f"SELECT count(*) FROM {EVENTS} WHERE measurement_series_id IS NULL"
        ).fetchone()[0]
        assert nulls == 0


class TestEmployeeMaster:
    def test_roster_is_materialized_with_initials(self, warehouse):
        row = warehouse.execute(
            f"""SELECT employee_id, initials, departed_on FROM {EMPLOYEE_TABLE}
                WHERE display_name='Kyle Bishop'"""
        ).fetchone()
        assert row[0] == "EMP-KB" and row[1] == "KB"
        assert row[2] is not None  # departed staff retained, not deleted

    def test_initials_are_unique_so_fieldflow_tokens_are_unambiguous(self, warehouse):
        dupes = warehouse.execute(
            f"SELECT initials FROM {EMPLOYEE_TABLE} GROUP BY 1 HAVING count(*) > 1"
        ).fetchall()
        assert dupes == []
