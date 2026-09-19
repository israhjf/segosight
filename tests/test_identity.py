"""Technician identity resolution tests."""

import pytest

from segosight.normalize import codes
from segosight.normalize.identity import resolve_actor


class TestFullNames:
    @pytest.mark.parametrize(
        "name,actor_id",
        [
            ("Jenn Fowler", "EMP-JF"),
            ("Marcus Webb", "EMP-MW"),
            ("Dale Hardy", "EMP-DH"),
            ("Tomas Rivera", "EMP-TR"),
            ("Aaron Silva", "EMP-AS"),
            ("Kyle Bishop", "EMP-KB"),
        ],
    )
    def test_legacy_servicetrak_names(self, name, actor_id):
        assert resolve_actor(name).value.actor_id == actor_id

    def test_match_is_case_insensitive(self):
        assert resolve_actor("jenn fowler").value.actor_id == "EMP-JF"


class TestFieldFlowInitials:
    @pytest.mark.parametrize(
        "initials,actor_id",
        [("JF", "EMP-JF"), ("MW", "EMP-MW"), ("DH", "EMP-DH"),
         ("TR", "EMP-TR"), ("AS", "EMP-AS")],
    )
    def test_all_initials_present_in_the_new_batch(self, initials, actor_id):
        got = resolve_actor(initials)
        assert got.value.actor_id == actor_id
        assert got.detail["matched_on"] == "initials"

    def test_initials_and_full_name_collapse_to_one_identity(self):
        """The core migration requirement: MW and Marcus Webb are one person."""
        assert resolve_actor("MW").value == resolve_actor("Marcus Webb").value


class TestNonPersonActors:
    def test_bms_export_is_a_system_not_an_employee(self):
        got = resolve_actor("BMS export")
        assert got.value.actor_type == "system"

    def test_contract_lab_is_an_external_org(self):
        got = resolve_actor("Central Analytical")
        assert got.value.actor_type == "external_org"

    def test_non_person_actors_are_excluded_from_initials_matching(self):
        # "CA" must not resolve to Central Analytical by accident.
        assert resolve_actor("CA").value is None


class TestDepartedStaff:
    def test_departed_technician_still_resolves(self):
        """Kyle Bishop left mid-July; his March-July visits are real history."""
        got = resolve_actor("Kyle Bishop")
        assert got.value.actor_id == "EMP-KB"
        assert got.value.departed == "2026-07-15"


class TestUnresolved:
    def test_unknown_token_is_flagged(self):
        got = resolve_actor("ZZ")
        assert got.value is None
        assert codes.UNKNOWN_ACTOR in got.issues

    @pytest.mark.parametrize("empty", ["", "   ", None])
    def test_empty_is_absence_not_error(self, empty):
        got = resolve_actor(empty)
        assert got.value is None and got.issues == ()

    def test_ambiguous_initials_are_flagged_rather_than_guessed(self, monkeypatch):
        import segosight.normalize.identity as ident

        twin = ident.Actor("EMP-XX", "Jane Fowler", "employee")
        monkeypatch.setitem(ident._BY_INITIALS, "JF", [ident.ROSTER[5], twin])
        got = resolve_actor("JF")
        assert got.value is None
        assert codes.AMBIGUOUS_ACTOR in got.issues
        assert set(got.detail["candidates"]) == {"EMP-JF", "EMP-XX"}
