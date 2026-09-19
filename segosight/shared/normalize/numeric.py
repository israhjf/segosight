"""Numeric coercion that never silently invents or discards a value."""

from __future__ import annotations

from segosight.shared.normalize import codes
from segosight.shared.normalize.result import Normalized


def parse_number(raw: str | None) -> Normalized[float]:
    """Coerce a source cell to float.

    An empty cell is a legitimate absence (the wide reading rows are sparse by
    design) and yields a null with no issue. A non-empty cell that will not
    parse is flagged, so it reaches the DQ queue instead of vanishing.
    """
    if raw is None:
        return Normalized(value=None, raw=raw)
    if isinstance(raw, (int, float)):
        return Normalized(value=float(raw), raw=raw)

    text = raw.strip()
    if not text:
        return Normalized(value=None, raw=raw)

    # Thousands separators appear in free text ("Makeup meter 53,900") and are
    # tolerated here so an operator-entered value does not fail on a comma.
    candidate = text.replace(",", "")
    try:
        return Normalized(value=float(candidate), raw=raw)
    except ValueError:
        return Normalized(value=None, raw=raw).with_issue(codes.UNPARSEABLE_NUMBER)
