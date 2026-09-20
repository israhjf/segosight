"""The compliance export bundle.

The governing concern here is not formatting but conflation: a pending
extraction must never be readable as a governed finding. These tests pin the
separation in the archive, in each file's header, and in the manifest.
"""

from __future__ import annotations

import csv
import io
import zipfile

import pytest
from fastapi.testclient import TestClient

from segosight.app import dependencies
from segosight.app.api import create_app
from segosight.features.export import bundle


@pytest.fixture()
def client(writable_warehouse, monkeypatch):
    monkeypatch.setattr(dependencies, "_connection", writable_warehouse)
    monkeypatch.setattr(dependencies, "close_connection", lambda: None)
    monkeypatch.setattr("segosight.app.api.close_connection", lambda: None)
    with TestClient(create_app()) as test_client:
        yield test_client


def read_csv(archive: zipfile.ZipFile, name: str):
    """Return (comment header lines, column row, data rows)."""
    text = archive.read(name).decode("utf-8-sig")
    rows = list(csv.reader(io.StringIO(text)))
    # Header lines contain commas, so the reader splits them; rejoin to
    # recover the original "# key,value" line.
    header = [",".join(r) for r in rows if r and r[0].startswith("#")]
    body = [r for r in rows if r and not r[0].startswith("#")]
    return header, body[0], body[1:]


@pytest.fixture()
def archive(warehouse):
    payload, _ = bundle.build(
        warehouse, severity="all", as_of="2026-09-11", reviewer="Dana Whitlock"
    )
    return zipfile.ZipFile(io.BytesIO(payload))


class TestBundleShape:
    def test_archive_holds_two_csvs_and_a_manifest(self, archive):
        assert sorted(archive.namelist()) == sorted(
            [bundle.ALERTS_FILENAME, bundle.INSIGHTS_FILENAME, bundle.MANIFEST_FILENAME]
        )

    def test_alert_schema_is_unchanged(self, archive):
        """The existing CSV contract must not regress when insights are added."""
        _, columns, _ = read_csv(archive, bundle.ALERTS_FILENAME)
        assert columns == bundle.ALERT_COLUMNS

    def test_both_queues_are_complete(self, archive, warehouse):
        _, _, alerts = read_csv(archive, bundle.ALERTS_FILENAME)
        _, _, insights = read_csv(archive, bundle.INSIGHTS_FILENAME)
        assert len(alerts) == warehouse.execute(
            "SELECT count(*) FROM curated.operational_alert"
        ).fetchone()[0]
        assert len(insights) == warehouse.execute(
            "SELECT count(*) FROM curated.extracted_insight WHERE status='pending_review'"
        ).fetchone()[0]

    def test_the_two_schemas_stay_separate(self, archive):
        """Merging them would assert an equivalence that does not exist."""
        _, alert_columns, _ = read_csv(archive, bundle.ALERTS_FILENAME)
        _, insight_columns, _ = read_csv(archive, bundle.INSIGHTS_FILENAME)
        assert "rule_version" in alert_columns
        assert "rule_version" not in insight_columns
        assert "confidence_score" in insight_columns
        assert "confidence_score" not in alert_columns
        assert "severity" not in insight_columns


class TestProvenance:
    def test_alerts_carry_their_rule_version(self, archive):
        header, columns, rows = read_csv(archive, bundle.ALERTS_FILENAME)
        assert any("rule_version,treatment_guidelines_rev6" in h for h in header)
        index = columns.index("rule_version")
        assert all(row[index] == "treatment_guidelines_rev6" for row in rows)

    def test_insight_file_disclaims_itself(self, archive):
        """A file opened away from the UI must still say what it is."""
        header, _, _ = read_csv(archive, bundle.INSIGHTS_FILENAME)
        joined = " ".join(header).lower()
        assert "not governed findings" in joined
        assert "awaiting human approval" in joined
        assert "confidence_score, not a rule_version" in joined

    def test_every_insight_declares_rule_or_ai(self, archive):
        _, columns, rows = read_csv(archive, bundle.INSIGHTS_FILENAME)
        index = columns.index("provenance")
        assert rows
        assert {row[index] for row in rows} <= {"rule", "ai"}

    def test_manifest_explains_both_files(self, archive):
        manifest = archive.read(bundle.MANIFEST_FILENAME).decode()
        assert bundle.ALERTS_FILENAME in manifest
        assert bundle.INSIGHTS_FILENAME in manifest
        assert "NOT" in manifest and "governed findings" in manifest
        assert "Dana Whitlock" in manifest

    def test_scope_is_stated_when_filtered(self, warehouse):
        payload, filename = bundle.build(
            warehouse, severity="critical", as_of="2026-09-11", reviewer="Dana"
        )
        archive = zipfile.ZipFile(io.BytesIO(payload))
        header, _, rows = read_csv(archive, bundle.ALERTS_FILENAME)
        joined = " ".join(header)
        assert "severity_filter,critical" in joined
        assert "filtered view" in joined
        assert len(rows) == 2
        assert "critical" in filename

    def test_insights_are_never_filtered_by_alert_severity(self, warehouse):
        """The review queue has no severity; applying one would invent a link."""
        unfiltered = bundle.build(warehouse, severity="all", reviewer="Dana")[0]
        filtered = bundle.build(warehouse, severity="critical", reviewer="Dana")[0]
        counts = []
        for payload in (unfiltered, filtered):
            _, _, rows = read_csv(
                zipfile.ZipFile(io.BytesIO(payload)), bundle.INSIGHTS_FILENAME
            )
            counts.append(len(rows))
        assert counts[0] == counts[1]

        header, _, _ = read_csv(
            zipfile.ZipFile(io.BytesIO(filtered)), bundle.INSIGHTS_FILENAME
        )
        assert any("severity_filter,none" in h for h in header)


class TestExportEndpoint:
    def test_download_is_a_zip_attachment(self, client):
        response = client.get("/api/export/bundle.zip?severity=all&reviewer=Dana")
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/zip"
        assert "attachment" in response.headers["content-disposition"]
        assert ".zip" in response.headers["content-disposition"]

    def test_downloaded_archive_opens(self, client):
        response = client.get("/api/export/bundle.zip?reviewer=Dana%20Whitlock")
        archive = zipfile.ZipFile(io.BytesIO(response.content))
        assert archive.testzip() is None
        assert bundle.INSIGHTS_FILENAME in archive.namelist()

    def test_reviewer_is_recorded(self, client):
        response = client.get("/api/export/bundle.zip?reviewer=Dana%20Whitlock")
        archive = zipfile.ZipFile(io.BytesIO(response.content))
        assert "Dana Whitlock" in archive.read(bundle.MANIFEST_FILENAME).decode()
