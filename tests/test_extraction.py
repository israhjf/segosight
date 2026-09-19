"""Prose extraction, the human-review gate, and prose-derived alerting."""

from __future__ import annotations

import datetime as dt

import pytest

from segosight.features.alerts.curated.aggregation import EVIDENCE_TABLE
from segosight.features.alerts.curated.aggregation import TABLE as ALERTS
from segosight.features.review.curated.extraction import PENDING, REVIEW_QUEUE_VIEW
from segosight.features.review.curated.extraction import TABLE as INSIGHTS
from segosight.features.review.linking import Linker, slugify
from segosight.features.review.llm import MAX_LLM_CONFIDENCE, _validate
from segosight.features.review.raw.documents import TABLE as DOCUMENTS
from segosight.features.review.raw.documents import parse_filename


class TestDocumentIngestion:
    def test_every_document_lands(self, warehouse):
        total = warehouse.execute(f"SELECT count(*) FROM {DOCUMENTS}").fetchone()[0]
        assert total == 67

    def test_all_three_formats_are_extracted(self, warehouse):
        rows = dict(
            warehouse.execute(
                f"""SELECT file_suffix, count(*) FROM {DOCUMENTS}
                    WHERE extraction_status = 'ok' GROUP BY 1"""
            ).fetchall()
        )
        assert rows == {".txt": 63, ".docx": 3, ".pdf": 1}

    def test_the_pdf_field_record_yields_text(self, warehouse):
        body = warehouse.execute(
            f"""SELECT body FROM {DOCUMENTS} WHERE file_suffix = '.pdf'"""
        ).fetchone()[0]
        assert "SYS-0030" in body and "NITRITE" in body

    def test_extraction_failures_would_be_visible_not_skipped(self, warehouse):
        """Nothing failed here, but a failure must land as a review item."""
        failed = warehouse.execute(
            f"""SELECT count(*) FROM {DOCUMENTS} WHERE extraction_status <> 'ok'"""
        ).fetchone()[0]
        assert failed == 0

    def test_filename_convention_parses(self):
        date, slug, topic = parse_filename("2026-08-22_kestrel_reply")
        assert date == dt.date(2026, 8, 22)
        assert slug == "kestrel" and topic == "reply"

    def test_unconventional_filename_degrades_gracefully(self):
        assert parse_filename("notes") == (None, None, None)


class TestLinking:
    def test_slugify(self):
        assert slugify("Maeser Ridge Regional Medical Center") == (
            "maeser-ridge-regional-medical-center"
        )

    def test_a_system_reference_pins_the_facility(self, warehouse):
        linker = Linker(warehouse)
        found = linker.find("The reuse-water tower (SYS-0042) keeps creeping up")
        assert found.system_ids == ("SYS-0042",)
        assert found.best_facility[0] == "F-0016"

    def test_a_distinctive_token_resolves_a_short_name(self, warehouse):
        """A reply signed only 'Kestrel' must still reach F-0004."""
        linker = Linker(warehouse)
        facility, confidence, basis = linker.find("Kestrel", "kestrel reply").best_facility
        assert facility == "F-0004"
        assert confidence >= 0.8 and "distinctive_token" in basis

    def test_internal_and_supplier_mail_stays_unlinked(self, warehouse):
        """Not every document is about a customer site; guessing would be worse."""
        unlinked = warehouse.execute(
            f"""SELECT count(*) FROM {DOCUMENTS} d
                WHERE NOT EXISTS (
                    SELECT 1 FROM {INSIGHTS} i
                    WHERE i.document_id = d.document_id AND i.facility_id IS NOT NULL
                )"""
        ).fetchone()[0]
        assert unlinked >= 2


class TestHumanInTheLoopGate:
    def test_every_extraction_lands_pending_review(self, warehouse):
        statuses = {
            r[0] for r in warehouse.execute(f"SELECT DISTINCT status FROM {INSIGHTS}").fetchall()
        }
        assert statuses == {PENDING}

    def test_every_extraction_carries_a_confidence_score(self, warehouse):
        bad = warehouse.execute(
            f"""SELECT count(*) FROM {INSIGHTS}
                WHERE confidence_score IS NULL OR confidence_score <= 0
                   OR confidence_score > 1"""
        ).fetchone()[0]
        assert bad == 0

    def test_nothing_is_auto_approved(self, warehouse):
        decided = warehouse.execute(
            f"""SELECT count(*) FROM {INSIGHTS}
                WHERE reviewed_by IS NOT NULL OR review_decision IS NOT NULL"""
        ).fetchone()[0]
        assert decided == 0

    def test_extraction_never_writes_to_the_governed_crosswalk(self, warehouse):
        """Identity candidates are proposals; the crosswalk stays curated."""
        candidates = warehouse.execute(
            f"""SELECT count(*) FROM {INSIGHTS}
                WHERE insight_type = 'identity_candidate'"""
        ).fetchone()[0]
        crosswalk = warehouse.execute(
            "SELECT count(*) FROM canonical.identity_resolution"
        ).fetchone()[0]
        assert candidates > 0
        # Unchanged from the 9 governed mappings seeded in Module 3.
        assert crosswalk == 9

    def test_every_insight_quotes_its_source(self, warehouse):
        """A claim that cannot point at its evidence is not reviewable."""
        unquoted = warehouse.execute(
            f"""SELECT count(*) FROM {INSIGHTS}
                WHERE quote IS NULL OR trim(quote) = '' OR source_file IS NULL"""
        ).fetchone()[0]
        assert unquoted == 0

    def test_review_queue_orders_unresolved_and_uncertain_first(self, warehouse):
        rows = warehouse.execute(
            f"SELECT fulfilled FROM {REVIEW_QUEUE_VIEW} LIMIT 5"
        ).fetchall()
        assert rows[0][0] is False


class TestCommitments:
    def test_the_broken_kestrel_promise_is_found(self, warehouse):
        row = warehouse.execute(
            f"""SELECT due_on, days_overdue, fulfilled, commitment_subject
                FROM {INSIGHTS}
                WHERE insight_type = 'commitment' AND facility_id = 'F-0004'"""
        ).fetchone()
        assert row[0] == dt.date(2026, 8, 24)
        assert row[1] >= 14
        assert row[2] is False
        assert row[3] == "visit"

    def test_a_visit_does_not_evidence_a_documentation_deliverable(self, warehouse):
        """Maeser Ridge asked for an accreditation packet, not a service call."""
        rows = warehouse.execute(
            f"""SELECT fulfilled, fulfillment_basis FROM {INSIGHTS}
                WHERE facility_id = 'F-0001'
                  AND commitment_subject = 'documentation'"""
        ).fetchall()
        assert rows
        for fulfilled, basis in rows:
            assert fulfilled is None
            assert "no structured record" in basis

    def test_deliverable_type_is_classified(self, warehouse):
        subjects = {
            r[0]
            for r in warehouse.execute(
                f"""SELECT DISTINCT commitment_subject FROM {INSIGHTS}
                    WHERE commitment_subject IS NOT NULL"""
            ).fetchall()
        }
        assert {"visit", "documentation"} <= subjects


class TestFieldConcerns:
    def test_the_boiler_inspection_recommendation_is_surfaced(self, warehouse):
        """Webb recommended inspecting SYS-0006 45 days before it failed."""
        row = warehouse.execute(
            f"""SELECT quote, days_overdue, fulfilled FROM {INSIGHTS}
                WHERE source_file LIKE '%2026-07-28_webb_bonneville-ogden%'
                  AND insight_type IN ('field_concern', 'recommendation')"""
        ).fetchone()
        assert "internal inspection" in row[0]
        assert row[2] is False

    def test_a_concern_backed_by_a_work_order_is_marked_documented(self, warehouse):
        documented = warehouse.execute(
            f"""SELECT count(*) FROM {INSIGHTS}
                WHERE insight_type IN ('field_concern', 'recommendation')
                  AND fulfilled IS TRUE"""
        ).fetchone()[0]
        assert documented >= 1

    def test_closing_language_is_not_read_as_a_concern(self, warehouse):
        """'DONE AS FAR AS IM CONCERNED' asserts the opposite of a concern."""
        false_positive = warehouse.execute(
            f"""SELECT count(*) FROM {INSIGHTS}
                WHERE insight_type = 'field_concern'
                  AND lower(quote) LIKE '%as far as im concerned%'"""
        ).fetchone()[0]
        assert false_positive == 0


class TestProseAlerting:
    def test_prose_alerts_are_marked_as_unreviewed(self, warehouse):
        bases = dict(
            warehouse.execute(
                f"SELECT evidence_basis, count(*) FROM {ALERTS} GROUP BY 1"
            ).fetchall()
        )
        assert bases["prose_pending_review"] > 0
        assert bases["structured"] > 0

    def test_the_broken_promise_becomes_its_own_alert(self, warehouse):
        row = warehouse.execute(
            f"""SELECT severity, evidence_basis FROM {ALERTS}
                WHERE risk_class = 'unfulfilled_commitment'
                  AND facility_id = 'F-0004'"""
        ).fetchone()
        assert row == ("high", "prose_pending_review")

    def test_corroborating_prose_attaches_as_evidence_not_a_new_alert(self, warehouse):
        """Webb's inspection note strengthens the existing corrosion alert."""
        evidence = warehouse.execute(
            f"""SELECT count(*) FROM {EVIDENCE_TABLE} e
                JOIN {ALERTS} a ON a.fingerprint = e.alert_fingerprint
                WHERE a.system_id = 'SYS-0006'
                  AND a.risk_class = 'corrosion_trend'"""
        ).fetchone()[0]
        assert evidence > 0

    def test_all_attached_evidence_shows_its_review_status(self, warehouse):
        statuses = {
            r[0]
            for r in warehouse.execute(
                f"SELECT DISTINCT review_status FROM {EVIDENCE_TABLE}"
            ).fetchall()
        }
        assert statuses == {PENDING}

    def test_structured_alerts_survive_prose_integration(self, warehouse):
        """Module 4's findings must not be displaced by Module 5."""
        structured = warehouse.execute(
            f"SELECT count(*) FROM {ALERTS} WHERE evidence_basis = 'structured'"
        ).fetchone()[0]
        assert structured == 32


class TestLLMGuards:
    def test_a_grounded_quote_is_accepted(self):
        document = "The bleed valve sticks, I cleaned the stem again."
        candidate = _validate(
            {"insight_type": "field_concern", "summary": "valve sticking",
             "quote": "The bleed valve sticks"},
            document,
        )
        assert candidate is not None
        assert candidate.confidence == MAX_LLM_CONFIDENCE

    def test_a_fabricated_quote_is_rejected(self):
        """The central guard: a model that cannot cite its evidence is dropped."""
        assert _validate(
            {"insight_type": "commitment", "summary": "refund",
             "quote": "I promised a refund on Friday"},
            "The bleed valve sticks, I cleaned the stem again.",
        ) is None

    def test_an_unknown_insight_type_is_rejected(self):
        assert _validate(
            {"insight_type": "invented", "summary": "x", "quote": "The bleed valve sticks"},
            "The bleed valve sticks, I cleaned the stem again.",
        ) is None

    def test_model_confidence_cannot_outrank_deterministic_matches(self):
        assert MAX_LLM_CONFIDENCE < 0.6

    @pytest.mark.parametrize("payload", [None, "text", 42, {"quote": "x"}])
    def test_malformed_payloads_are_rejected(self, payload):
        assert _validate(payload, "some document text here") is None
