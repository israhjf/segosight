"""Resolution of technician tokens to a canonical Employee identity.

Legacy ServiceTrak exports carry full names ("Jenn Fowler"); FieldFlow exports
carry initials ("JF"), confirmed by Rosa Camacho's go-live note of 2026-09-05.
Readings additionally carry non-person actors in `collected_by` -- "BMS export"
and "Central Analytical" -- which must not be coerced into employees.

Initials are resolved against the known roster and only when unambiguous. The
Ontology design is explicit that ambiguous initials are flagged for review
rather than auto-guessed, so a future hire colliding on initials raises an
exception instead of silently reassigning another technician's work.
"""

from __future__ import annotations

from dataclasses import dataclass

from segosight.shared.normalize import codes
from segosight.shared.normalize.result import Normalized


@dataclass(frozen=True)
class Actor:
    """A canonical actor: an employee, or a non-person data source."""

    actor_id: str
    display_name: str
    #: "employee" | "system" | "external_org"
    actor_type: str
    #: Set for employees who have left; their historical records remain valid.
    departed: str | None = None


#: Roster from organization_context.pdf section 2. Kyle Bishop left mid-July
#: 2026; his visits before that date are legitimate history, not defects.
ROSTER: tuple[Actor, ...] = (
    Actor("EMP-WN", "Walt Neilsen", "employee"),
    Actor("EMP-DW", "Dana Whitlock", "employee"),
    Actor("EMP-RC", "Rosa Camacho", "employee"),
    Actor("EMP-DH", "Dale Hardy", "employee"),
    Actor("EMP-MW", "Marcus Webb", "employee"),
    Actor("EMP-JF", "Jenn Fowler", "employee"),
    Actor("EMP-TR", "Tomas Rivera", "employee"),
    Actor("EMP-AS", "Aaron Silva", "employee"),
    Actor("EMP-KB", "Kyle Bishop", "employee", departed="2026-07-15"),
)

#: Non-person actors appearing in `collected_by`.
NON_PERSON_ACTORS: tuple[Actor, ...] = (
    Actor("SRC-BMS", "BMS export", "system"),
    Actor("ORG-CENTRAL-ANALYTICAL", "Central Analytical", "external_org"),
)

_ALL_ACTORS = ROSTER + NON_PERSON_ACTORS


def _initials(full_name: str) -> str:
    return "".join(part[0] for part in full_name.split() if part).upper()


def _build_index() -> tuple[dict[str, Actor], dict[str, list[Actor]]]:
    """Index actors by exact display name and by initials."""
    by_name = {a.display_name.casefold(): a for a in _ALL_ACTORS}
    by_initials: dict[str, list[Actor]] = {}
    for actor in ROSTER:
        by_initials.setdefault(_initials(actor.display_name), []).append(actor)
    return by_name, by_initials


_BY_NAME, _BY_INITIALS = _build_index()


def resolve_actor(raw: str | None) -> Normalized[Actor]:
    """Resolve a technician name, initials, or data-source label to an Actor.

    Ambiguous initials return no value and flag `AMBIGUOUS_ACTOR`; unknown
    tokens flag `UNKNOWN_ACTOR`. Both land in the identity review queue.
    """
    if raw is None:
        return Normalized(value=None, raw=raw)
    text = raw.strip()
    if not text:
        return Normalized(value=None, raw=raw)

    exact = _BY_NAME.get(text.casefold())
    if exact is not None:
        return Normalized(value=exact, raw=raw, detail={"matched_on": "display_name"})

    candidates = _BY_INITIALS.get(text.upper(), [])
    if len(candidates) == 1:
        return Normalized(
            value=candidates[0], raw=raw, detail={"matched_on": "initials"}
        )
    if len(candidates) > 1:
        return Normalized(value=None, raw=raw).with_issue(
            codes.AMBIGUOUS_ACTOR,
            candidates=[a.actor_id for a in candidates],
        )

    return Normalized(value=None, raw=raw).with_issue(codes.UNKNOWN_ACTOR)
