"""Temporal parsing tests.

Every literal here is a verbatim value taken from the supplied CSVs.
"""

import datetime as dt

import pytest

from segosight.shared.normalize import codes
from segosight.shared.normalize.temporal import parse_date, parse_timestamp

CORPUS = (dt.date(2026, 3, 1), dt.date(2026, 9, 30))


class TestMixedFormatsWithinOneFile:
    """water_readings.csv carries both conventions; the dictionary says otherwise."""

    def test_iso_field_reading(self):
        # RD-00923, collection_method=field
        got = parse_timestamp("2026-06-11 09:50")
        assert got.value == dt.datetime(2026, 6, 11, 9, 50)
        assert got.detail["format"] == "%Y-%m-%d %H:%M"
        assert got.ok

    def test_american_bms_reading_in_the_same_legacy_file(self):
        # RD-00001, collection_method=bms -- same file as the ISO row above
        got = parse_timestamp("3/2/26 0:00")
        assert got.value == dt.datetime(2026, 3, 2, 0, 0)
        assert got.detail["convention"] == "month_first"
        assert got.ok

    def test_both_conventions_resolve_to_the_same_march_day(self):
        iso = parse_timestamp("2026-03-02 08:30").value.date()
        american = parse_timestamp("3/2/26 0:00").value.date()
        assert iso == american == dt.date(2026, 3, 2)


class TestFieldFlowBatch:
    def test_four_digit_year_date_only(self):
        # FF-1001 visit_date
        got = parse_date("9/1/2026")
        assert got.value == dt.date(2026, 9, 1)
        assert got.detail["format"] == "%m/%d/%Y"

    def test_two_digit_year_expands_to_2026_not_1926(self):
        assert parse_date("9/12/26").value == dt.date(2026, 9, 12)


class TestMonthFirstConvention:
    def test_day_over_twelve_is_unambiguous(self):
        # 8/31/26 can only be August 31st
        got = parse_timestamp("8/31/26 0:00")
        assert got.value == dt.datetime(2026, 8, 31, 0, 0)
        assert got.detail["ambiguous"] is False

    def test_ambiguous_value_is_resolved_month_first_but_flagged(self):
        got = parse_timestamp("3/2/26 0:00")
        assert got.value.month == 3 and got.value.day == 2
        assert got.detail["ambiguous"] is True

    def test_ambiguity_is_recorded_not_treated_as_an_error(self):
        # Ambiguity is metadata for audit, not a defect that blocks the row.
        assert parse_timestamp("3/2/26 0:00").ok


class TestDefects:
    def test_unparseable_value_is_flagged_and_yields_no_value(self):
        got = parse_timestamp("not a date")
        assert got.value is None
        assert codes.UNPARSEABLE_TIMESTAMP in got.issues

    @pytest.mark.parametrize("empty", ["", "   ", None])
    def test_missing_is_null_without_an_issue(self, empty):
        got = parse_timestamp(empty)
        assert got.value is None and got.issues == ()

    def test_out_of_corpus_is_flagged_but_value_is_retained(self):
        # A date typo must be surfaced, never silently dropped.
        got = parse_timestamp("2019-01-01 10:00", corpus=CORPUS)
        assert got.value == dt.datetime(2019, 1, 1, 10, 0)
        assert codes.TIMESTAMP_OUT_OF_CORPUS in got.issues

    def test_restricting_formats_rejects_the_other_convention(self):
        got = parse_timestamp("3/2/26 0:00", formats=("%Y-%m-%d %H:%M",))
        assert codes.UNPARSEABLE_TIMESTAMP in got.issues
