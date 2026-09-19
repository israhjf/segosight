"""Timestamp parsing across the export conventions present in the sources.

The supplied data dictionary claims legacy files are ISO and only the FieldFlow
batch is American-format. That is not what the data does: `water_readings.csv`
carries BOTH conventions in the same file -- BMS rows use `M/D/YY H:MM` while
field and lab rows use `YYYY-MM-DD HH:MM`. Format is therefore detected per
value, never assumed per file.

Month-first is the declared convention for the American-format exports (Rosa
Camacho, "FieldFlow go-live notes", 2026-09-05). Values where both components
are <= 12 are genuinely ambiguous under any other convention, so they are
marked as such in `detail` for auditability even though we resolve them
month-first.
"""

from __future__ import annotations

import datetime as dt
import re

from segosight.shared.normalize import codes
from segosight.shared.normalize.result import Normalized

#: Candidate formats, most specific first. Order matters: a value matching an
#: earlier entry never falls through to a later one.
DEFAULT_FORMATS: tuple[str, ...] = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d",
    "%m/%d/%Y %H:%M",
    "%m/%d/%y %H:%M",
    "%m/%d/%Y",
    "%m/%d/%y",
)

#: Formats whose month/day order is convention-dependent.
_SLASH_FORMATS = frozenset(f for f in DEFAULT_FORMATS if "/" in f)

_SLASH_RE = re.compile(r"^\s*(\d{1,2})/(\d{1,2})/(\d{2,4})")


def _is_ambiguous(raw: str) -> bool:
    """True when a slash date could be read either month-first or day-first."""
    m = _SLASH_RE.match(raw)
    if not m:
        return False
    first, second = int(m.group(1)), int(m.group(2))
    return first <= 12 and second <= 12


def parse_timestamp(
    raw: str | None,
    *,
    formats: tuple[str, ...] = DEFAULT_FORMATS,
    corpus: tuple[dt.date, dt.date] | None = None,
) -> Normalized[dt.datetime]:
    """Parse a timestamp, reporting which convention matched.

    Args:
        raw: The source string. Empty/None yields a null value with no issue,
            because a missing optional timestamp is not a defect.
        formats: Ordered candidate formats. Callers restrict this when a source
            is known to emit exactly one convention.
        corpus: Optional (start, end) window. Values outside it are flagged
            rather than dropped -- a date typo is a finding, not a reason to
            discard the record.
    """
    if raw is None:
        return Normalized(value=None, raw=raw)
    text = raw.strip()
    if not text:
        return Normalized(value=None, raw=raw)

    for fmt in formats:
        try:
            parsed = dt.datetime.strptime(text, fmt)
        except ValueError:
            continue

        detail: dict[str, object] = {"format": fmt}
        if fmt in _SLASH_FORMATS:
            detail["convention"] = "month_first"
            detail["ambiguous"] = _is_ambiguous(text)
        result: Normalized[dt.datetime] = Normalized(
            value=parsed, raw=raw, detail=detail
        )
        if corpus is not None and not (corpus[0] <= parsed.date() <= corpus[1]):
            result = result.with_issue(
                codes.TIMESTAMP_OUT_OF_CORPUS,
                corpus_start=corpus[0].isoformat(),
                corpus_end=corpus[1].isoformat(),
            )
        return result

    return Normalized(value=None, raw=raw).with_issue(
        codes.UNPARSEABLE_TIMESTAMP, tried=list(formats)
    )


def parse_date(
    raw: str | None,
    *,
    formats: tuple[str, ...] = DEFAULT_FORMATS,
    corpus: tuple[dt.date, dt.date] | None = None,
) -> Normalized[dt.date]:
    """Parse a date-only field, discarding any time component."""
    ts = parse_timestamp(raw, formats=formats, corpus=corpus)
    return Normalized(
        value=ts.value.date() if ts.value is not None else None,
        raw=ts.raw,
        issues=ts.issues,
        detail=ts.detail,
    )
