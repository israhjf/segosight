"""Resolve prose mentions to canonical customers, facilities and systems.

Two signals, deliberately kept separate because they carry different weight:

* explicit identifiers in the text (SYS-0042, F-0008, WO-0158) are near-certain;
* site name and filename-slug matches are strong but not proof, because several
  facilities share a customer and the filename slug on a technician note is the
  technician's surname, not the site.

Nothing here decides anything. It produces linkage candidates with confidence,
which the extraction layer attaches to an insight that a human then approves.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import duckdb

from segosight.features.identity.canonical.entities import CUSTOMER_TABLE, FACILITY_TABLE, SYSTEM_TABLE

SYSTEM_ID_RE = re.compile(r"\bSYS-\d{4}\b")
FACILITY_ID_RE = re.compile(r"\bF-\d{4}\b")
CUSTOMER_ID_RE = re.compile(r"\bCUST-\d{4}\b")
WORK_ORDER_RE = re.compile(r"\bWO-\d{4}\b")
VISIT_RE = re.compile(r"\b(?:V-\d{4}|FF-\d{4})\b")

_NON_WORD = re.compile(r"[^a-z0-9]+")

#: Words that carry no discriminating power in a site name.
_STOPWORDS = frozenset(
    {
        "the", "co", "inc", "llc", "group", "company", "services", "service",
        "plant", "building", "main", "campus", "center", "centre", "regional",
        "of", "and", "1", "yard", "shop", "complex",
    }
)


def slugify(text: str) -> str:
    return _NON_WORD.sub("-", text.lower()).strip("-")


def _tokens(text: str) -> frozenset[str]:
    return frozenset(t for t in slugify(text).split("-") if t and t not in _STOPWORDS)


@dataclass(frozen=True)
class Mentions:
    """Everything a document appears to refer to."""

    system_ids: tuple[str, ...] = ()
    facility_ids: tuple[str, ...] = ()
    customer_ids: tuple[str, ...] = ()
    work_order_ids: tuple[str, ...] = ()
    visit_ids: tuple[str, ...] = ()
    #: facility_id -> (confidence, how it was matched)
    facility_candidates: dict[str, tuple[float, str]] = field(default_factory=dict)

    @property
    def best_facility(self) -> tuple[str | None, float, str]:
        if self.facility_ids:
            return self.facility_ids[0], 0.98, "explicit_facility_id"
        if not self.facility_candidates:
            return None, 0.0, "unresolved"
        facility_id, (confidence, basis) = max(
            self.facility_candidates.items(), key=lambda item: item[1][0]
        )
        return facility_id, confidence, basis


class Linker:
    """Matches prose against canonical master data."""

    def __init__(self, conn: duckdb.DuckDBPyConnection):
        self._systems = {
            row[0]: row[1]
            for row in conn.execute(
                f"SELECT system_id, facility_id FROM {SYSTEM_TABLE}"
            ).fetchall()
        }
        self._facility_names: list[tuple[str, frozenset[str], str]] = []
        for facility_id, facility_name, customer_name in conn.execute(
            f"""SELECT f.facility_id, f.facility_name, c.customer_name
                FROM {FACILITY_TABLE} f
                LEFT JOIN {CUSTOMER_TABLE} c USING (customer_id)"""
        ).fetchall():
            for label in filter(None, (customer_name, facility_name)):
                self._facility_names.append((facility_id, _tokens(label), label))
        # A token belonging to exactly one facility identifies it on its own.
        # "Kestrel" is only ever Kestrel Aerospace, so a reply signed just
        # "Kestrel" should still resolve even though it shares one token in
        # three with the full registered name.
        occurrences: dict[str, set[str]] = {}
        for facility_id, tokens, _ in self._facility_names:
            for token in tokens:
                occurrences.setdefault(token, set()).add(facility_id)
        self._distinctive = {
            token: next(iter(ids))
            for token, ids in occurrences.items()
            if len(ids) == 1 and len(token) > 3
        }
        self._facility_customer = {
            row[0]: row[1]
            for row in conn.execute(
                f"SELECT facility_id, customer_id FROM {FACILITY_TABLE}"
            ).fetchall()
        }

    def customer_for(self, facility_id: str | None) -> str | None:
        return self._facility_customer.get(facility_id) if facility_id else None

    def facility_for_system(self, system_id: str) -> str | None:
        return self._systems.get(system_id)

    def find(self, text: str, filename_hint: str = "") -> Mentions:
        """Locate every entity a document refers to."""
        system_ids = tuple(dict.fromkeys(SYSTEM_ID_RE.findall(text)))
        facility_ids = tuple(dict.fromkeys(FACILITY_ID_RE.findall(text)))

        candidates: dict[str, tuple[float, str]] = {}

        # A system reference pins the facility that owns it.
        for system_id in system_ids:
            owner = self._systems.get(system_id)
            if owner:
                candidates[owner] = (0.9, f"system_reference:{system_id}")

        haystack = _tokens(f"{filename_hint} {text}")
        for facility_id, tokens, label in self._facility_names:
            if not tokens:
                continue
            overlap = tokens & haystack
            if not overlap:
                continue
            score = len(overlap) / len(tokens)
            if score < 0.5:
                continue
            # Full name match is stronger than a single shared token.
            confidence = 0.85 if score == 1.0 else 0.6
            existing = candidates.get(facility_id)
            if existing is None or confidence > existing[0]:
                candidates[facility_id] = (confidence, f"name_match:{label}")

        for token in haystack:
            facility_id = self._distinctive.get(token)
            if facility_id is None:
                continue
            existing = candidates.get(facility_id)
            if existing is None or existing[0] < 0.8:
                candidates[facility_id] = (0.8, f"distinctive_token:{token}")

        return Mentions(
            system_ids=system_ids,
            facility_ids=facility_ids,
            customer_ids=tuple(dict.fromkeys(CUSTOMER_ID_RE.findall(text))),
            work_order_ids=tuple(dict.fromkeys(WORK_ORDER_RE.findall(text))),
            visit_ids=tuple(dict.fromkeys(VISIT_RE.findall(text))),
            facility_candidates=candidates,
        )
