"""Explosion of the semicolon-delimited multi-value fields in service visits.

`systems_serviced` and `chemicals_added` are 1NF violations that trap the two
N:M relationships the Ontology needs as first-class events (SystemService and
ChemicalApplication).

A hard limit discovered in the data: 269 of the 316 chemical-bearing visits
serve more than one system, and `chemicals_added` is a flat concatenation
across all of them with no per-system boundary. Dose-to-system attribution is
therefore *not recoverable* from this source for ~85% of doses. We preserve
each dose with its ordinal and leave the system unattributed rather than
inventing an assignment; ApplicationTargetsSystem must stay nullable.

Repeated identical segments are real. Visit V-0001 lists
`CT-770 6 gal; BIO-12 1 gal; CT-770 6 gal; BIO-12 1 gal` because two towers
were each dosed. Deduplicating would halve recorded consumption.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from segosight.shared.normalize import codes
from segosight.shared.normalize.result import Normalized

#: Product codes observed across both batches: AM-115, BIO-12, BRM-40, BW-210,
#: BW-305, CL-40, CL-M40, CT-770, CT-785.
_DOSE_RE = re.compile(
    r"^(?P<product>[A-Z]{2,3}-[A-Z]?\d{2,3})\s+"
    r"(?P<quantity>\d+(?:\.\d+)?)\s+"
    r"(?P<unit>[A-Za-z]+)$"
)

#: Dose units observed in the corpus.
KNOWN_DOSE_UNITS = frozenset({"gal", "qt", "lb"})


def split_list(raw: str | None) -> list[str]:
    """Split a semicolon-delimited cell, dropping empty segments."""
    if not raw:
        return []
    return [seg.strip() for seg in raw.split(";") if seg.strip()]


def parse_systems_serviced(raw: str | None) -> Normalized[list[str]]:
    """Explode `systems_serviced` into system identifiers.

    Order is preserved and duplicates are kept; validation that each identifier
    resolves to a real system happens in the reconciliation layer, not here.
    """
    return Normalized(value=split_list(raw), raw=raw)


@dataclass(frozen=True)
class Dose:
    """One chemical application recorded on a visit."""

    product_code: str
    quantity: float | None
    unit: str | None
    #: Position within the visit's `chemicals_added` list, 0-based. Preserved
    #: because repeated segments are distinct real doses.
    ordinal: int
    raw: str
    issues: tuple[str, ...] = ()


def parse_chemicals_added(raw: str | None) -> Normalized[list[Dose]]:
    """Explode `chemicals_added` into individual doses.

    A segment that does not parse becomes a Dose carrying only its raw text and
    an issue code, so the dose is still counted as having happened and lands in
    the DQ queue rather than disappearing from consumption totals.
    """
    doses: list[Dose] = []
    issues: list[str] = []

    for ordinal, segment in enumerate(split_list(raw)):
        match = _DOSE_RE.match(segment)
        if match is None:
            doses.append(
                Dose(
                    product_code=segment.split()[0] if segment.split() else segment,
                    quantity=None,
                    unit=None,
                    ordinal=ordinal,
                    raw=segment,
                    issues=(codes.UNPARSEABLE_DOSE,),
                )
            )
            issues.append(codes.UNPARSEABLE_DOSE)
            continue

        unit = match.group("unit")
        dose_issues: tuple[str, ...] = ()
        if unit not in KNOWN_DOSE_UNITS:
            dose_issues = (codes.UNKNOWN_DOSE_UNIT,)
            issues.append(codes.UNKNOWN_DOSE_UNIT)

        doses.append(
            Dose(
                product_code=match.group("product"),
                quantity=float(match.group("quantity")),
                unit=unit,
                ordinal=ordinal,
                raw=segment,
                issues=dose_issues,
            )
        )

    return Normalized(value=doses, raw=raw, issues=tuple(dict.fromkeys(issues)))


def doses_are_attributable(system_count: int) -> bool:
    """True only when a visit's doses can be tied to a single system.

    With one system serviced, every dose on the visit belongs to it. With more
    than one, the flat list carries no per-system boundary and attribution
    would be fabrication.
    """
    return system_count == 1
