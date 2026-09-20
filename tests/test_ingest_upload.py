"""The upload → profile → review → confirm pipeline.

These tests exercise the parts that can quietly do damage: a client-supplied
path escaping the staging directory, a profile that under-reports what an
ingestion would change, a promotion that half-applies, and a rebuild that
discards reviewer decisions.

Nothing here touches the real `sources.toml` or the real materials tree. Every
test that promotes works against copies in tmp_path, because a test that
appends a batch entry to the governed config would corrupt the corpus for every
later test and for the developer running it.
"""

from __future__ import annotations

import datetime as dt
import shutil
from pathlib import Path

import pytest

from segosight.features.ingestion import profile as profiling
from segosight.features.ingestion import promotion, staging
from segosight.features.ingestion.registry import DEFAULT_CONFIG, load_registry
from segosight.shared.paths import materials_root


# --------------------------------------------------------------------------
# fixtures
# --------------------------------------------------------------------------


@pytest.fixture()
def staging_area(tmp_path, monkeypatch):
    """Redirect the staging root into tmp_path."""
    root = tmp_path / "staging"
    monkeypatch.setattr(staging, "staging_root", lambda: root)
    return root


@pytest.fixture()
def new_batch_files():
    """The real 2026-09 drop, as a browser would upload the folder."""
    source = materials_root() / "new_data_batch"
    if not source.is_dir():
        pytest.skip("source material not present")
    return [
        (str(p.relative_to(source.parent)), p.read_bytes())
        for p in sorted(source.rglob("*"))
        if p.is_file()
    ]


@pytest.fixture()
def sandbox_config(tmp_path):
    """A copy of sources.toml that a test may safely rewrite."""
    copy = tmp_path / "sources.toml"
    shutil.copy(DEFAULT_CONFIG, copy)
    return copy


# --------------------------------------------------------------------------
# staging: everything from the browser is untrusted
# --------------------------------------------------------------------------


class TestStagingSafety:
    @pytest.mark.parametrize(
        "hostile",
        [
            "../../etc/passwd",
            "..\\..\\windows\\system32\\config.csv",
            "/etc/shadow",
            "notes/../../../../../../tmp/escape.csv",
        ],
    )
    def test_path_traversal_cannot_escape(self, hostile):
        """webkitRelativePath is client-controlled and must never escape."""
        safe = staging.safe_relative_path(hostile)
        assert not safe.is_absolute()
        assert ".." not in safe.parts

    def test_traversal_attempt_writes_inside_the_upload(self, staging_area):
        upload = staging.create([("../../../evil.csv", b"a,b\n1,2\n")])
        written = list(upload.root.rglob("*.csv"))
        assert len(written) == 1
        assert written[0].resolve().is_relative_to(upload.root.resolve())

    def test_folder_structure_survives(self, staging_area, new_batch_files):
        upload = staging.create(new_batch_files)
        relative = {str(f.relative_path) for f in upload.files}
        assert "new_data_batch/water_readings_2026-09.csv" in relative
        assert any(r.startswith("new_data_batch/communications/") for r in relative)

    def test_unknown_suffix_is_refused_by_name(self, staging_area):
        with pytest.raises(staging.UploadRejected, match=r"\.exe"):
            staging.create([("payload.exe", b"MZ")])

    def test_oversized_file_is_refused(self, staging_area, monkeypatch):
        monkeypatch.setattr(staging, "MAX_FILE_BYTES", 16)
        with pytest.raises(staging.UploadRejected, match="per-file limit"):
            staging.create([("big.csv", b"x" * 64)])

    def test_empty_upload_is_refused(self, staging_area):
        with pytest.raises(staging.UploadRejected, match="no files"):
            staging.create([])

    def test_discard_removes_everything(self, staging_area, new_batch_files):
        upload = staging.create(new_batch_files)
        assert upload.root.is_dir()
        staging.discard(upload.upload_id)
        assert not upload.root.exists()

    def test_sweep_only_takes_expired_uploads(self, staging_area, monkeypatch):
        fresh = staging.create([("a.csv", b"x,y\n1,2\n")])
        stale = staging.create([("b.csv", b"x,y\n1,2\n")])
        stale.created_at = stale.created_at - dt.timedelta(days=3)
        stale.save()

        assert staging.sweep() == 1
        assert fresh.root.is_dir()
        assert not stale.root.exists()

    def test_reload_round_trips(self, staging_area, new_batch_files):
        upload = staging.create(new_batch_files)
        reopened = staging.load(upload.upload_id)
        assert reopened.upload_id == upload.upload_id
        assert len(reopened.files) == len(upload.files)


# --------------------------------------------------------------------------
# folder-name drift: the thing that used to require a code change
# --------------------------------------------------------------------------


class TestDirectoryAliases:
    def test_renamed_folder_resolves_through_config(self, registry):
        """`communications` is the 2026-09 rename of `customer_communications`.

        It used to be absorbed by editing a tuple in documents.py. The registry
        contract says a new drop is a config change, so it is an alias now.
        """
        resolved = {(d.path.name, d.document_class) for d in registry.document_dirs()}
        assert ("communications", "customer_communication") in resolved
        assert ("customer_communications", "customer_communication") in resolved
        assert ("technician_notes", "technician_note") in resolved

    def test_every_document_lands_exactly_once(self, warehouse):
        """Aliases must not double-land a directory matched twice."""
        duplicated = warehouse.execute(
            """SELECT source_file, count(*) AS n FROM raw.documents
               GROUP BY 1 HAVING count(*) > 1"""
        ).fetchall()
        assert duplicated == []

    def test_corpus_document_count_is_unchanged(self, warehouse):
        """Moving directories into config must not change what is ingested."""
        counts = dict(
            warehouse.execute(
                "SELECT batch_name, count(*) FROM raw.documents GROUP BY 1"
            ).fetchall()
        )
        assert counts == {"legacy": 59, "2026-09": 8}

    def test_alias_can_be_added_to_config_text(self, sandbox_config):
        text = sandbox_config.read_text(encoding="utf-8")
        updated = promotion.add_document_alias(text, "technician_note", "site_notes")
        assert '"site_notes"' in updated
        # The surrounding comments are what make the file a governed artefact.
        assert "# --- Prose directories" in updated

    def test_adding_an_existing_alias_is_a_no_op(self, sandbox_config):
        text = sandbox_config.read_text(encoding="utf-8")
        assert promotion.add_document_alias(text, "technician_note", "tech_notes") == text


# --------------------------------------------------------------------------
# profiling: the review screen must not under-report
# --------------------------------------------------------------------------


class TestProfile:
    def test_folder_upload_finds_the_batch_root(self, staging_area, new_batch_files):
        upload = staging.create(new_batch_files)
        assert profiling.resolve_batch_root(upload.root).name == "new_data_batch"

    def test_loose_files_keep_the_upload_root(self, staging_area):
        upload = staging.create([("customers.csv", b"customer_id\nCUST-0001\n")])
        assert profiling.resolve_batch_root(upload.root) == upload.root

    def test_known_drop_matches_every_entity(
        self, staging_area, new_batch_files, writable_warehouse
    ):
        upload = staging.create(new_batch_files)
        result = profiling.build(writable_warehouse, upload)
        assert {e.entity for e in result.entities} == {
            "systems",
            "service_visits",
            "water_readings",
            "work_orders",
        }
        assert result.total_rows == 109

    def test_reuploading_a_landed_batch_shows_no_new_keys(
        self, staging_area, new_batch_files, writable_warehouse
    ):
        """Idempotency has to be *visible* before Dana confirms, not after."""
        upload = staging.create(new_batch_files)
        result = profiling.build(writable_warehouse, upload)
        assert sum(e.new_keys for e in result.entities) == 0
        assert sum(e.superseding_keys for e in result.entities) == 109

    def test_genuinely_new_rows_count_as_new(self, staging_area, writable_warehouse):
        upload = staging.create(
            [
                (
                    "work_orders_2099.csv",
                    b"wo_id,customer_id,facility_id,system_id,created_date,priority,"
                    b"status,owner,title,description\n"
                    b"WO-9001,CUST-0001,F-0001,SYS-0001,2099-01-01,P3,open,"
                    b"Marcus Webb,Test,Synthetic row\n",
                )
            ]
        )
        result = profiling.build(writable_warehouse, upload)
        work_orders = next(e for e in result.entities if e.entity == "work_orders")
        assert work_orders.new_keys == 1
        assert work_orders.superseding_keys == 0

    def test_missing_master_files_are_a_delta_not_an_error(
        self, staging_area, new_batch_files, writable_warehouse
    ):
        """The 2026-09 drop has no customers.csv. That is normal."""
        upload = staging.create(new_batch_files)
        result = profiling.build(writable_warehouse, upload)
        assert set(result.absent_entities) == {"customers", "chemical_inventory"}
        assert not result.blocking
        assert result.can_confirm

    def test_prose_directory_is_profiled(
        self, staging_area, new_batch_files, writable_warehouse
    ):
        upload = staging.create(new_batch_files)
        result = profiling.build(writable_warehouse, upload)
        comms = next(d for d in result.documents if d.directory == "communications")
        assert comms.document_class == "customer_communication"
        assert comms.documents == 8

    def test_unrecognised_directory_blocks_and_suggests(
        self, staging_area, writable_warehouse
    ):
        """An unknown folder is never guessed at -- it is escalated to Dana."""
        upload = staging.create(
            [
                ("drop/water_readings_x.csv", b"reading_id,system_id\nRD-1,SYS-0001\n"),
                ("drop/technician_note/2026-09-01_site_note.txt", b"a note"),
            ]
        )
        result = profiling.build(writable_warehouse, upload)
        unmatched = {u.path for u in result.unmatched}
        assert any("technician_note" in p for p in unmatched)
        assert any(f.code == "unmapped" for f in result.blocking)
        assert not result.can_confirm
        # It should propose the near-match without applying it.
        suggested = next(u for u in result.unmatched if "technician_note" in u.path)
        assert suggested.suggestion == "technician_notes"

    def test_schema_drift_is_reported_not_rejected(
        self, staging_area, writable_warehouse
    ):
        upload = staging.create(
            [
                (
                    "work_orders_drift.csv",
                    b"wo_id,customer_id,facility_id,system_id,created_date,priority,"
                    b"status,owner,title,description,new_field\n"
                    b"WO-9100,CUST-0001,F-0001,SYS-0001,2099-01-01,P3,open,"
                    b"Marcus Webb,Test,Row,extra\n",
                )
            ]
        )
        result = profiling.build(writable_warehouse, upload)
        work_orders = next(e for e in result.entities if e.entity == "work_orders")
        assert "new_field" in work_orders.added_columns
        assert any(f.code == "schema_added" for f in result.findings)
        # Drift is informational: it must not block a load.
        assert not any(f.code == "schema_added" for f in result.blocking)

    def test_orphan_reference_blocks(self, staging_area, writable_warehouse):
        """A visit citing a facility nobody has ever seen is a broken drop."""
        upload = staging.create(
            [
                (
                    "service_visits_orphan.csv",
                    b"visit_id,visit_date,technician,customer_id,facility_id,"
                    b"systems_serviced,work_performed,chemicals_added,visit_status,"
                    b"follow_up_date,observations\n"
                    b"V-9999,2099-01-01,Jenn Fowler,CUST-0001,F-9999,SYS-0001,"
                    b"Check,,completed,,\n",
                )
            ]
        )
        result = profiling.build(writable_warehouse, upload)
        assert any(f.code == "orphan_reference" for f in result.blocking)
        assert not result.can_confirm

    def test_lab_sample_codes_do_not_count_as_orphans(
        self, staging_area, writable_warehouse
    ):
        """BONF-OGD-B2 resolves through the crosswalk, not against systems.

        Treating lab sample points as orphans would block every drop that
        contains a lab report -- a documented quirk, not a broken upload.
        """
        upload = staging.create(
            [
                (
                    "water_readings_lab.csv",
                    b"reading_id,timestamp,system_id,collected_by,collection_method,"
                    b"conductivity,units\n"
                    b"RD-99001,2099-01-01 08:00,BONF-OGD-B2,Central Analytical,lab,"
                    b"2.4,cond=mS/cm\n",
                )
            ]
        )
        result = profiling.build(writable_warehouse, upload)
        assert not any(f.code == "orphan_reference" for f in result.blocking)

    def test_empty_drop_cannot_be_confirmed(self, staging_area, writable_warehouse):
        upload = staging.create([("readme.md", b"# nothing to ingest")])
        result = profiling.build(writable_warehouse, upload)
        assert not result.can_confirm
        assert any(f.code in {"empty", "unmapped"} for f in result.blocking)


# --------------------------------------------------------------------------
# promotion: config is a governed artefact
# --------------------------------------------------------------------------


class TestPromotion:
    @pytest.fixture()
    def sandbox_materials(self, tmp_path):
        root = tmp_path / "materials"
        root.mkdir()
        return root

    def test_promote_registers_a_batch_and_copies_files(
        self, staging_area, new_batch_files, writable_warehouse,
        sandbox_config, sandbox_materials, monkeypatch,
    ):
        monkeypatch.setattr(promotion, "materials_root", lambda: sandbox_materials)
        upload = staging.create(new_batch_files)
        result = profiling.build(writable_warehouse, upload)

        promoted = promotion.promote(
            upload, result, uploader="Dana Whitlock",
            config_path=sandbox_config, materials=sandbox_materials,
        )

        assert promoted.files_promoted == len(new_batch_files)
        assert (sandbox_materials / promoted.batch_root).is_dir()

        text = sandbox_config.read_text(encoding="utf-8")
        assert f'root                  = "{promoted.batch_root}"' in text
        assert "Dana Whitlock" in text, "a batch must be traceable to a person"

        # The new batch must take the highest sequence: supersede precedence
        # is decided by batch order and a later drop has to win.
        registry = load_registry(sandbox_config)
        assert max(b.sequence for b in registry.batches) == promoted.sequence
        assert promoted.sequence > 2

    def test_rollback_leaves_no_trace(
        self, staging_area, new_batch_files, writable_warehouse,
        sandbox_config, sandbox_materials, monkeypatch,
    ):
        """A failed rebuild must not leave a half-registered batch behind."""
        monkeypatch.setattr(promotion, "materials_root", lambda: sandbox_materials)
        before = sandbox_config.read_text(encoding="utf-8")

        upload = staging.create(new_batch_files)
        result = profiling.build(writable_warehouse, upload)
        promoted = promotion.promote(
            upload, result, uploader="Dana Whitlock",
            config_path=sandbox_config, materials=sandbox_materials,
        )
        assert sandbox_config.read_text(encoding="utf-8") != before

        promotion.rollback(
            promoted.batch_root, config_path=sandbox_config, materials=sandbox_materials
        )

        after = sandbox_config.read_text(encoding="utf-8")
        assert not (sandbox_materials / promoted.batch_root).exists()
        assert promoted.batch_root not in after
        registry = load_registry(sandbox_config)
        assert len(registry.batches) == 2

    def test_excluded_items_are_not_copied(
        self, staging_area, writable_warehouse, sandbox_config,
        sandbox_materials, monkeypatch,
    ):
        monkeypatch.setattr(promotion, "materials_root", lambda: sandbox_materials)
        upload = staging.create(
            [
                ("drop/work_orders_x.csv", b"wo_id\nWO-1\n"),
                ("drop/scratch.csv", b"junk\n1\n"),
            ]
        )
        result = profiling.build(writable_warehouse, upload)
        promoted = promotion.promote(
            upload, result, uploader="Dana Whitlock",
            mappings=[promotion.Mapping(path="drop/scratch.csv", kind="exclude")],
            config_path=sandbox_config, materials=sandbox_materials,
        )
        copied = {p.name for p in (sandbox_materials / promoted.batch_root).rglob("*")}
        assert "work_orders_x.csv" in copied
        assert "scratch.csv" not in copied
        assert promoted.excluded == ["drop/scratch.csv"]

    def test_mapped_directory_becomes_a_permanent_alias(
        self, staging_area, writable_warehouse, sandbox_config,
        sandbox_materials, monkeypatch,
    ):
        """Dana's mapping is saved, so the next drop resolves automatically."""
        monkeypatch.setattr(promotion, "materials_root", lambda: sandbox_materials)
        upload = staging.create(
            [
                ("drop/work_orders_x.csv", b"wo_id\nWO-1\n"),
                ("drop/site_notes/2026-09-01_site_note.txt", b"a note"),
            ]
        )
        result = profiling.build(writable_warehouse, upload)
        promoted = promotion.promote(
            upload, result, uploader="Dana Whitlock",
            mappings=[
                promotion.Mapping(
                    path="drop/site_notes", kind="document", target="technician_note"
                )
            ],
            config_path=sandbox_config, materials=sandbox_materials,
        )
        assert promoted.aliases_added == ["site_notes -> technician_note"]
        registry = load_registry(sandbox_config)
        assert "site_notes" in registry.documents["technician_note"]

    def test_batch_directory_name_never_collides(
        self, staging_area, new_batch_files, writable_warehouse,
        sandbox_materials, monkeypatch,
    ):
        monkeypatch.setattr(promotion, "materials_root", lambda: sandbox_materials)
        upload = staging.create(new_batch_files)
        result = profiling.build(writable_warehouse, upload)
        # `new_data_batch` is already a batch ROOT in config, even though the
        # sandbox materials directory is empty. Reusing it would give two
        # entries the same root.
        assert promotion.batch_directory_name(
            result, upload, materials=sandbox_materials
        ) == "new_data_batch-2"


# --------------------------------------------------------------------------
# the governed config itself
# --------------------------------------------------------------------------


class TestConfigIntegrity:
    def test_real_config_is_untouched_by_this_module(self):
        """Guard rail: these tests must never write to the shipped config."""
        registry = load_registry()
        assert [b.name for b in registry.batches] == ["legacy", "2026-09"]
        assert set(registry.documents) == {
            "technician_note",
            "customer_communication",
        }

    def test_batch_sequences_stay_unique(self):
        registry = load_registry()
        sequences = [b.sequence for b in registry.batches]
        assert len(set(sequences)) == len(sequences)


# --------------------------------------------------------------------------
# the HTTP surface
# --------------------------------------------------------------------------


class TestIngestApi:
    """Upload and profile over HTTP.

    Confirm is deliberately not exercised end to end here: it promotes into
    the real materials tree and appends to the shipped `sources.toml`, so a
    test that ran it would mutate the corpus for everything after it. Its
    parts -- promote, rollback and the decision carry-over -- are covered
    directly above.
    """

    @pytest.fixture()
    def client(self, writable_warehouse, staging_area, monkeypatch):
        from fastapi.testclient import TestClient

        from segosight.app import dependencies
        from segosight.app.api import create_app

        monkeypatch.setattr(dependencies, "_connection", writable_warehouse)
        monkeypatch.setattr(dependencies, "close_connection", lambda: None)
        monkeypatch.setattr("segosight.app.api.close_connection", lambda: None)
        with TestClient(create_app()) as test_client:
            yield test_client

    @staticmethod
    def _post(client, files):
        """Post as a browser would: each file paired with its relative path."""
        payload = [("files", (Path(name).name, blob, "text/csv")) for name, blob in files]
        payload += [("paths", (None, name)) for name, _ in files]
        return client.post("/api/ingest/upload", files=payload)

    def test_upload_returns_a_profile(self, client, new_batch_files):
        response = self._post(client, new_batch_files)
        assert response.status_code == 200, response.text
        body = response.json()
        assert body["batch_root"] == "new_data_batch"
        assert body["total_rows"] == 109
        assert body["total_documents"] == 8
        assert sorted(body["absent_entities"]) == ["chemical_inventory", "customers"]
        assert body["can_confirm"] is True

    def test_profile_survives_a_refresh(self, client, new_batch_files):
        upload_id = self._post(client, new_batch_files).json()["upload_id"]
        again = client.get(f"/api/ingest/{upload_id}")
        assert again.status_code == 200
        assert again.json()["total_rows"] == 109

    def test_rejected_upload_leaves_nothing_staged(self, client, staging_area):
        response = self._post(client, [("payload.exe", b"MZ")])
        assert response.status_code == 400
        assert "not an accepted file type" in response.json()["detail"]
        assert not list(staging_area.glob("*")) or all(
            not p.is_dir() for p in staging_area.glob("*")
        )

    def test_discard_removes_the_upload(self, client, new_batch_files):
        upload_id = self._post(client, new_batch_files).json()["upload_id"]
        assert client.delete(f"/api/ingest/{upload_id}").status_code == 200
        assert client.get(f"/api/ingest/{upload_id}").status_code == 404

    def test_confirming_a_blocked_upload_is_refused(self, client, staging_area):
        """A drop with unmapped items must not be confirmable over the wire.

        The UI disables the button, but the guard has to live on the server:
        a disabled button is not a control.
        """
        files = [
            ("drop/water_readings_x.csv", b"reading_id,system_id\nRD-1,SYS-0001\n"),
            ("drop/mystery_folder/2026-09-01_site_note.txt", b"note"),
        ]
        upload_id = self._post(client, files).json()["upload_id"]
        response = client.post(
            f"/api/ingest/{upload_id}/confirm",
            json={"uploader": "Dana Whitlock", "mappings": []},
        )
        assert response.status_code == 409
        assert "not recognised" in response.json()["detail"]

    def test_unknown_upload_is_404(self, client):
        assert client.get("/api/ingest/does-not-exist").status_code == 404
