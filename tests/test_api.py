"""API contract tests.

These run against the same warehouse fixture the pipeline tests use, so the
shapes the UI consumes are checked against real data rather than stubs.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from segosight.api import dependencies
from segosight.api.app import create_app
from segosight.curated.extraction import PENDING


@pytest.fixture()
def client(writable_warehouse, monkeypatch):
    """API bound to the session warehouse.

    The app's lifespan closes its connection on shutdown, which would close
    the shared fixture out from under every later test, so the teardown is
    neutralised here. The connection's real lifecycle is exercised by the
    server itself, not by this fixture.
    """
    monkeypatch.setattr(dependencies, "_connection", writable_warehouse)
    monkeypatch.setattr(dependencies, "close_connection", lambda: None)
    monkeypatch.setattr("segosight.api.app.close_connection", lambda: None)
    app = create_app()
    with TestClient(app) as test_client:
        yield test_client


class TestOverview:
    def test_health(self, client):
        body = client.get("/api/health").json()
        assert body["status"] == "ok" and body["tables"] > 20

    def test_counters_match_the_warehouse(self, client, writable_warehouse):
        body = client.get("/api/overview").json()
        assert body["active_alerts"] == writable_warehouse.execute(
            "SELECT count(*) FROM curated.operational_alert"
        ).fetchone()[0]
        assert body["pending_review"] > 0

    def test_prose_banner_count_is_not_silently_zero(self, client):
        """Regression: a fingerprint-substring bug once cleared every banner."""
        body = client.get("/api/overview").json()
        assert body["alerts_awaiting_prose_review"] == 9

    def test_as_of_is_data_derived(self, client):
        assert client.get("/api/overview").json()["as_of_date"] == "2026-09-11"


class TestReviewQueue:
    def test_returns_pending_items(self, client):
        items = client.get("/api/review").json()
        assert items
        assert {item["status"] for item in items} == {PENDING}

    def test_every_item_states_its_provenance(self, client):
        items = client.get("/api/review").json()
        assert all(item["provenance"] in ("rule", "ai") for item in items)
        # With the LLM path off, nothing should claim to be AI-produced.
        assert all(item["provenance"] == "rule" for item in items)

    def test_every_item_carries_a_quote_and_confidence(self, client):
        for item in client.get("/api/review").json():
            assert item["quote"].strip()
            assert 0 < item["confidence_score"] <= 1

    def test_button_verbs_match_the_insight_type(self, client):
        verbs = {
            item["insight_type"]: (item["approve_verb"], item["reject_verb"])
            for item in client.get("/api/review").json()
        }
        assert verbs.get("commitment", ("Merge",))[0] == "Merge"
        assert verbs.get("field_concern", ("Attach",))[0] == "Attach"

    def test_ordering_puts_unresolved_first(self, client):
        items = client.get("/api/review").json()
        assert items[0]["fulfilled"] is False

    def test_unknown_insight_is_404(self, client):
        assert client.get("/api/review/does-not-exist").status_code == 404


class TestDecisions:
    def test_approving_a_commitment_promotes_it(self, client, writable_warehouse):
        item = next(
            i
            for i in client.get("/api/review").json()
            if i["insight_type"] in ("commitment", "customer_request")
        )
        response = client.post(
            f"/api/review/{item['insight_id']}/decision",
            json={"decision": "approved", "reviewer": "D. Whitlock"},
        )
        assert response.status_code == 200
        assert response.json()["commitment_created"]
        assert writable_warehouse.execute(
            "SELECT count(*) FROM curated.customer_commitment WHERE source_insight_id = ?",
            [item["insight_id"]],
        ).fetchone()[0] == 1

    def test_the_decision_is_attributed_and_timestamped(self, client, writable_warehouse):
        item = client.get("/api/review").json()[0]
        client.post(
            f"/api/review/{item['insight_id']}/decision",
            json={"decision": "approved", "reviewer": "R. Camacho", "note": "checked"},
        )
        row = writable_warehouse.execute(
            """SELECT status, reviewed_by, review_decision, reviewed_at
               FROM curated.extracted_insight WHERE insight_id = ?""",
            [item["insight_id"]],
        ).fetchone()
        assert row[0] == "approved" and row[1] == "R. Camacho"
        assert row[2] == "checked" and row[3] is not None

    def test_approval_does_not_inflate_confidence(self, client, writable_warehouse):
        """An approved row keeps the score it was extracted with."""
        item = client.get("/api/review").json()[0]
        before = item["confidence_score"]
        client.post(
            f"/api/review/{item['insight_id']}/decision",
            json={"decision": "approved", "reviewer": "D. Whitlock"},
        )
        after = writable_warehouse.execute(
            "SELECT confidence_score FROM curated.extracted_insight WHERE insight_id = ?",
            [item["insight_id"]],
        ).fetchone()[0]
        assert after == before

    def test_a_second_decision_is_refused(self, client):
        item = client.get("/api/review").json()[0]
        payload = {"decision": "approved", "reviewer": "D. Whitlock"}
        assert client.post(f"/api/review/{item['insight_id']}/decision", json=payload).status_code == 200
        assert client.post(f"/api/review/{item['insight_id']}/decision", json=payload).status_code == 409

    def test_anonymous_decisions_are_rejected(self, client):
        item = client.get("/api/review").json()[0]
        response = client.post(
            f"/api/review/{item['insight_id']}/decision",
            json={"decision": "approved", "reviewer": ""},
        )
        assert response.status_code == 422

    def test_an_invalid_decision_value_is_rejected(self, client):
        item = client.get("/api/review").json()[0]
        response = client.post(
            f"/api/review/{item['insight_id']}/decision",
            json={"decision": "maybe", "reviewer": "D. Whitlock"},
        )
        assert response.status_code == 422

    def test_rejecting_detaches_evidence_without_deleting_it(self, client, writable_warehouse):
        item = next(
            i for i in client.get("/api/review").json() if i["insight_type"] == "field_concern"
        )
        client.post(
            f"/api/review/{item['insight_id']}/decision",
            json={"decision": "rejected", "reviewer": "D. Whitlock", "note": "not a concern"},
        )
        status, kept = writable_warehouse.execute(
            """SELECT any_value(review_status), count(*) FROM curated.alert_evidence
               WHERE evidence_id = ?""",
            [item["insight_id"]],
        ).fetchone()
        assert status == "rejected" and kept > 0


class TestAlerts:
    def test_queue_is_priority_ordered(self, client):
        alerts = client.get("/api/alerts").json()
        scores = [a["priority_score"] for a in alerts]
        assert scores == sorted(scores, reverse=True)

    def test_every_alert_answers_the_four_questions(self, client):
        for alert in client.get("/api/alerts").json():
            assert alert["title"] and alert["why"] and alert["consequence"]
            assert alert["severity"] in ("critical", "high", "medium", "low")

    def test_evidence_carries_review_status(self, client):
        alerts = client.get("/api/alerts").json()
        with_evidence = [a for a in alerts if a["evidence"]]
        assert with_evidence
        for alert in with_evidence:
            assert all(e["review_status"] for e in alert["evidence"])

    def test_severity_filter(self, client):
        critical = client.get("/api/alerts?severity=critical").json()
        assert critical and all(a["severity"] == "critical" for a in critical)

    def test_detail_returns_the_measurement_series(self, client):
        detail = client.get("/api/alerts/corrosion_trend:SYS-0006:iron").json()
        assert detail["upper_limit"] == 2.0
        assert detail["governing_program"] == "BP-STD"
        assert len(detail["series"]) > 20
        assert {p["collection_method"] for p in detail["series"]} == {"field", "lab"}

    def test_detail_keeps_lab_and_field_distinguishable(self, client):
        """The chart must be able to draw them apart; pooling hides the trend."""
        detail = client.get("/api/alerts/corrosion_trend:SYS-0006:iron").json()
        field = [p["value"] for p in detail["series"] if p["collection_method"] == "field"]
        lab = [p["value"] for p in detail["series"] if p["collection_method"] == "lab"]
        assert max(field) > max(lab) * 2

    def test_detail_includes_escalation_history(self, client):
        detail = client.get("/api/alerts/microbio_escalation:SYS-0004:dipslide").json()
        assert len(detail["escalations"]) > 10
        assert any(row["documented"] is False for row in detail["escalations"])

    def test_unknown_alert_is_404(self, client):
        assert client.get("/api/alerts/no:such:alert").status_code == 404


class TestConcurrency:
    """Regression: concurrent requests must not read each other's result sets.

    The Overview screen fires /api/overview, /api/review and /api/alerts at
    once. FastAPI runs sync endpoints in a threadpool, and a DuckDB connection
    holds its result set on the connection itself -- so sharing one across
    threads made /api/overview deserialise rows belonging to /api/review and
    fail validation with a 500. Every request now gets its own cursor.

    TestClient issues requests serially, which is exactly why the original bug
    survived the suite; these tests drive the app from real threads.
    """

    def test_each_request_gets_an_independent_handle(self, writable_warehouse, monkeypatch):
        monkeypatch.setattr(dependencies, "_connection", writable_warehouse)
        first = dependencies.get_connection()
        second = dependencies.get_connection()
        assert first is not second
        assert first is not writable_warehouse

    def test_parallel_endpoints_return_their_own_rows(self, client):
        import concurrent.futures as futures

        def call(path: str):
            return client.get(path)

        paths = ["/api/overview", "/api/review?limit=50", "/api/alerts?limit=100"] * 8
        with futures.ThreadPoolExecutor(max_workers=12) as pool:
            responses = list(pool.map(call, paths))

        assert all(response.status_code == 200 for response in responses)

        for path, response in zip(paths, responses):
            body = response.json()
            if path.startswith("/api/overview"):
                # The symptom of the bug: strings where integers belong.
                assert isinstance(body["active_alerts"], int)
                assert isinstance(body["pending_review"], int)
                assert body["as_of_date"] == "2026-09-11"
            else:
                assert isinstance(body, list) and body
                assert "insight_id" in body[0] or "alert_id" in body[0]

    def test_parallel_detail_requests_stay_distinct(self, client):
        import concurrent.futures as futures

        ids = [
            "corrosion_trend:SYS-0006:iron",
            "microbio_escalation:SYS-0004:dipslide",
        ] * 6
        with futures.ThreadPoolExecutor(max_workers=8) as pool:
            responses = list(pool.map(lambda i: client.get(f"/api/alerts/{i}"), ids))

        for alert_id, response in zip(ids, responses):
            assert response.status_code == 200
            assert response.json()["alert_id"] == alert_id
