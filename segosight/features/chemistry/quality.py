"""Physical-plausibility assessment for normalized readings.

Guidelines section 4.1: values that are physically impossible -- a pH outside
the 0-14 scale, a negative concentration -- "are recording or instrument errors
by definition and must be corrected in the record, not acted on". Such readings
are quarantined as `invalid` so no treatment response is ever triggered from
them, while the row itself is retained as evidence (section 2: an
unrepresentative result "stays in the record and is annotated rather than
deleted").

Zero deserves care. Zero conductivity is a BMS dropout (3 rows) and is
implausible for treated water. Zero total hardness is the *target* on boiler
feedwater ("below 2 ppm", section 3.1) and appears in 22 healthy rows; zero
sulfite is a real depletion finding, not a defect. So only conductivity is
zero-checked, and the rest are left for the control-limit rules to judge.
"""

from __future__ import annotations

import re

from segosight.shared.normalize import codes
from segosight.shared.normalize.result import Normalized

PH_MIN, PH_MAX = 0.0, 14.0

#: Parameters for which a negative value is physically impossible.
_CONCENTRATION_PARAMETERS = frozenset(
    {
        "conductivity",
        "total_hardness",
        "m_alkalinity",
        "chloride",
        "inhibitor",
        "molybdate",
        "sulfite",
        "nitrite",
        "iron",
        "free_halogen",
        "dipslide",
    }
)

_DIPSLIDE_RE = re.compile(r"^\s*10\^(\d+)\s*$")


def parse_dipslide(raw: str | None) -> Normalized[float]:
    """Parse a `10^x` dipslide culture result into its base-10 exponent.

    Storing the exponent (not the CFU count) keeps the semi-quantitative ladder
    in guidelines section 5 directly comparable: the healthcare escalation
    thresholds are expressed as 10^4 and 10^5, which become 4.0 and 5.0.
    """
    if raw is None:
        return Normalized(value=None, raw=raw)
    text = str(raw).strip()
    if not text:
        return Normalized(value=None, raw=raw)

    match = _DIPSLIDE_RE.match(text)
    if match is None:
        return Normalized(value=None, raw=raw).with_issue(codes.MALFORMED_DIPSLIDE)
    return Normalized(
        value=float(match.group(1)), raw=raw, detail={"standard_unit": "log10 CFU/ml"}
    )


def assess(parameter_code: str, value: float | None) -> tuple[str, tuple[str, ...]]:
    """Judge one normalized value's physical plausibility.

    Returns `(quality_status, issues)`. The status is independent of whether a
    correction later supersedes the row -- an impossible value is quarantined
    on its own merits, so an *uncorrected* typo is caught too.
    """
    if value is None:
        return codes.VALID, ()

    if parameter_code == "ph" and not (PH_MIN <= value <= PH_MAX):
        return codes.INVALID, (codes.PH_OUT_OF_SCALE,)

    if parameter_code in _CONCENTRATION_PARAMETERS and value < 0:
        return codes.INVALID, (codes.NEGATIVE_CONCENTRATION,)

    # Treated water always conducts; zero is a telemetry dropout, not a result.
    # Suspect rather than invalid: it is excluded from trends but stays visible
    # as a signal that the BMS feed is unhealthy.
    if parameter_code == "conductivity" and value == 0:
        return codes.SUSPECT, (codes.ZERO_CONDUCTIVITY,)

    return codes.VALID, ()
