"""Raw landing and source-registry tests."""

from __future__ import annotations

import pytest

from segosight.features.ingestion.raw.landing import SCHEMA_TABLE
from segosight.features.ingestion.raw.landing import TABLE as RAW_TABLE
from segosight.features.ingestion.raw.landing import land_all
from segosight.features.ingestion.registry import load_registry


class TestRegistry:
    def test_resolves_both_batches_for_a_drifted_entity(self, registry):
        files = registry.files_for("service_visits")
        assert [f.batch.name for f in files] == ["legacy", "2026-09"]
        assert files[1].path.name == "service_visits_2026-09.csv"

    def test_renamed_new_batch_file_matches_the_existing_glob(self, registry):
        """systems_update_2026-09.csv is found without a new pattern."""
        names = [f.path.name for f in registry.files_for("systems")]
        assert names == ["systems.csv", "systems_update_2026-09.csv"]

    def test_files_are_ordered_by_batch_sequence(self, registry):
        for entity in registry.entities:
            seqs = [f.batch.sequence for f in registry.files_for(entity)]
            assert seqs == sorted(seqs)

    def test_source_system_is_attributed_per_batch(self, registry):
        systems = {f.batch.name: f.source_system for f in registry.files_for("water_readings")}
        assert systems == {"legacy": "ServiceTrak", "2026-09": "FieldFlow"}

    def test_parent_glob_does_not_swallow_the_nested_batch_directory(self, registry):
        """Non-recursive globs keep each batch's rows attributed to its batch."""
        legacy = [f for f in registry.files_for("water_readings") if f.batch.name == "legacy"]
        assert len(legacy) == 1

    def test_duplicate_batch_sequence_is_rejected(self, tmp_path):
        config = tmp_path / "bad.toml"
        config.write_text(
            """
[corpus]
start = 2026-03-01
end = 2026-09-30
[[batches]]
name = "a"
sequence = 1
root = "."
default_source_system = "X"
[[batches]]
name = "b"
sequence = 1
root = "n"
default_source_system = "Y"
[entities.x]
glob = "*.csv"
business_key = ["id"]
""",
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="unique"):
            load_registry(config)


class TestBusinessKey:
    """Business keys are built in SQL; assert against landed rows."""

    def test_single_column_key(self, warehouse):
        got = warehouse.execute(
            f"""SELECT count(*) FROM {RAW_TABLE}
                WHERE entity='water_readings' AND business_key='RD-00923'"""
        ).fetchone()[0]
        assert got == 2  # original plus corrected re-issue

    def test_composite_key_is_pipe_joined(self, warehouse):
        keys = [
            r[0]
            for r in warehouse.execute(
                f"""SELECT business_key FROM {RAW_TABLE}
                    WHERE entity='chemical_inventory' LIMIT 3"""
            ).fetchall()
        ]
        assert all("|" in k for k in keys)
        assert "Warehouse - SLC|CT-770" in [
            r[0]
            for r in warehouse.execute(
                f"SELECT business_key FROM {RAW_TABLE} WHERE entity='chemical_inventory'"
            ).fetchall()
        ]

    def test_every_landed_row_has_a_non_empty_key(self, warehouse):
        blank = warehouse.execute(
            f"SELECT count(*) FROM {RAW_TABLE} WHERE trim(business_key, '|') = ''"
        ).fetchone()[0]
        assert blank == 0


class TestRowHash:
    def test_a_corrected_reissue_gets_a_distinct_hash(self, warehouse):
        """Same key, changed payload must be a new version, not a collision."""
        hashes = [
            r[0]
            for r in warehouse.execute(
                f"""SELECT row_hash FROM {RAW_TABLE}
                    WHERE entity='water_readings' AND business_key='RD-00923'"""
            ).fetchall()
        ]
        assert len(hashes) == 2 and len(set(hashes)) == 2

    def test_hashes_are_unique_across_the_whole_raw_tier(self, warehouse):
        total, distinct = warehouse.execute(
            f"SELECT count(*), count(DISTINCT row_hash) FROM {RAW_TABLE}"
        ).fetchone()
        assert total == distinct


class TestSchemaDrift:
    def test_new_batch_column_is_detected_not_silently_absorbed(self, registry):
        from segosight.shared.warehouse import connect

        conn = connect(":memory:")
        results = land_all(conn, registry)
        drifted = [r for r in results if r.added_columns]
        assert len(drifted) == 1
        assert drifted[0].entity == "service_visits"
        assert drifted[0].added_columns == ("source_system",)
        conn.close()

    def test_drifted_column_still_lands_in_the_payload(self, warehouse):
        payload = warehouse.execute(
            f"""SELECT payload FROM {RAW_TABLE}
                WHERE entity='service_visits' AND business_key='FF-1001'"""
        ).fetchone()[0]
        assert "FieldFlow" in payload

    def test_every_file_records_its_observed_columns(self, warehouse):
        count = warehouse.execute(f"SELECT count(*) FROM {SCHEMA_TABLE}").fetchone()[0]
        assert count == 10


class TestLanding:
    def test_every_source_row_lands(self, warehouse):
        counts = dict(
            warehouse.execute(
                f"SELECT entity, count(*) FROM {RAW_TABLE} GROUP BY 1"
            ).fetchall()
        )
        assert counts["water_readings"] == 1618 + 84
        assert counts["service_visits"] == 305 + 19
        assert counts["systems"] == 54 + 2
        assert counts["work_orders"] == 51 + 4

    def test_raw_payload_preserves_the_original_value_uncorrected(self, warehouse):
        """Raw must not normalize: the impossible pH stays as exported."""
        import json

        payload = json.loads(
            warehouse.execute(
                f"""SELECT payload FROM {RAW_TABLE}
                    WHERE business_key = 'RD-00923' AND batch_name = 'legacy'"""
            ).fetchone()[0]
        )
        # Preserved as text, not coerced to a number and not repaired.
        assert payload["ph"] == "91.2"

    def test_empty_source_cells_land_as_json_null(self, warehouse):
        """read_csv maps an empty field to NULL; absence is uniform in payloads."""
        import json

        payload = json.loads(
            warehouse.execute(
                f"""SELECT payload FROM {RAW_TABLE}
                    WHERE business_key = 'RD-00923' AND batch_name = 'legacy'"""
            ).fetchone()[0]
        )
        assert payload["notes"] is None

    def test_raw_preserves_the_original_unit_notation(self, warehouse):
        payload = warehouse.execute(
            f"""SELECT payload FROM {RAW_TABLE}
                WHERE entity='water_readings' AND business_key='RD-00001'"""
        ).fetchone()[0]
        assert "mS/cm" in payload

    def test_re_landing_is_idempotent(self, registry):
        from segosight.shared.warehouse import connect

        conn = connect(":memory:")
        first = sum(r.rows_inserted for r in land_all(conn, registry))
        second = sum(r.rows_inserted for r in land_all(conn, registry))
        assert first > 0 and second == 0
        conn.close()
