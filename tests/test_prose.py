"""Prose primitives: email headers, deadline phrases, commitment language."""

from __future__ import annotations

import datetime as dt

import pytest

from segosight.normalize.prose import (
    find_commitments,
    find_due_date,
    parse_email_headers,
    split_sentences,
    strip_headers,
)

KESTREL_REPLY = """From: Rosa Camacho <rosa.camacho@segoindustrialwater.example>
To: Dave Pulsipher <d.pulsipher@kestrelaero.example>
Cc: Dana Whitlock <dana.whitlock@segoindustrialwater.example>
Date: Sat, 22 Aug 2026 10:05:00 -0600
Subject: RE: No service visits since early July

Dave,

I am arranging coverage and will confirm a technician and a day for this
coming week by Monday.

Rosa Camacho
"""


class TestEmailHeaders:
    def test_parses_a_service_inbox_export(self):
        headers = parse_email_headers(KESTREL_REPLY)
        assert headers.is_email is True
        assert headers.sender == "Rosa Camacho"
        assert headers.sender_address == "rosa.camacho@segoindustrialwater.example"
        assert headers.sent_at == dt.datetime(2026, 8, 22, 10, 5)
        assert headers.subject.startswith("RE: No service visits")

    def test_cc_is_captured_so_escalation_is_visible(self):
        headers = parse_email_headers(KESTREL_REPLY)
        assert "dana.whitlock@segoindustrialwater.example" in headers.cc

    def test_a_technician_note_is_not_an_email(self):
        note = "CleanPeak weekly. Jenn F. 8/14/26\n\nThe reuse-water tower..."
        assert parse_email_headers(note).is_email is False

    def test_headers_are_stripped_from_the_body(self):
        body = strip_headers(KESTREL_REPLY)
        assert "Subject:" not in body
        assert body.startswith("Dave,")


class TestDueDates:
    @pytest.fixture
    def saturday(self):
        return dt.date(2026, 8, 22)

    def test_by_monday_resolves_forward(self, saturday):
        due = find_due_date("will confirm ... by Monday.", saturday)
        assert due.due_on == dt.date(2026, 8, 24)
        assert due.basis == "relative_weekday"

    def test_a_couple_of_weeks_is_lower_confidence_than_a_weekday(self, saturday):
        vague = find_due_date("Can you have this to me within a couple of weeks?", saturday)
        precise = find_due_date("by Monday", saturday)
        assert vague.due_on == dt.date(2026, 9, 5)
        assert vague.confidence < precise.confidence

    def test_explicit_iso_date_scores_highest(self):
        due = find_due_date("Please deliver by 2026-09-30.", dt.date(2026, 9, 1))
        assert due.due_on == dt.date(2026, 9, 30)
        assert due.confidence >= 0.9

    def test_counted_window(self, saturday):
        assert find_due_date("within two weeks", saturday).due_on == dt.date(2026, 9, 5)

    def test_named_month_part(self, saturday):
        due = find_due_date("reopening roughly mid-October", saturday)
        assert due.due_on == dt.date(2026, 10, 15)
        assert due.confidence < 0.5  # softest signal we accept

    def test_relative_phrases_need_a_reference_date(self):
        assert find_due_date("by Monday", None) is None

    def test_no_deadline_language_yields_nothing(self, saturday):
        assert find_due_date("Boiler side normal.", saturday) is None


class TestCommitmentLanguage:
    def test_detects_an_outbound_promise(self):
        signals = find_commitments(strip_headers(KESTREL_REPLY))
        assert any(s.kind == "explicit_promise" for s in signals)

    def test_detects_an_inbound_request(self):
        signals = find_commitments("Can you have this to me within a couple of weeks?")
        assert signals and signals[0].kind == "customer_request"

    def test_descriptive_text_is_not_a_commitment(self):
        assert find_commitments("Tested boiler and feedwater, adjusted feed.") == []


class TestSentenceSplitting:
    def test_hard_wrapped_sentences_are_rejoined(self):
        text = "I am arranging coverage and will confirm a technician\nand a day by Monday. Thanks."
        sentences = split_sentences(text)
        assert sentences[0].endswith("by Monday.")
        assert "\n" not in sentences[0]

    def test_blank_lines_separate_blocks(self):
        assert len(split_sentences("One thing.\n\nAnother thing.")) == 2
