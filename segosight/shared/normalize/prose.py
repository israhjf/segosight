"""Primitives for reading operational meaning out of free text.

Deterministic and unit-testable by design. Everything here produces a
*candidate* with an explicit confidence score; nothing it returns is treated as
fact until a human approves it. The optional LLM path (see
`curated.llm_extract`) proposes additional candidates through the same gate and
never bypasses it.

Confidence reflects how literal the evidence is, not how plausible the guess:
an explicit ISO date scores higher than "by Monday", which scores higher than
"a couple of weeks".
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass

_HEADER_RE = re.compile(
    r"^(?P<key>From|To|Cc|Date|Subject)\s*:\s*(?P<value>.*)$",
    re.IGNORECASE | re.MULTILINE,
)
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")

_WEEKDAYS = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}

_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11,
    "december": 12, "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7,
    "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}


@dataclass(frozen=True)
class EmailHeaders:
    sender: str | None = None
    sender_address: str | None = None
    recipients: tuple[str, ...] = ()
    cc: tuple[str, ...] = ()
    sent_at: dt.datetime | None = None
    subject: str | None = None
    is_email: bool = False


def parse_email_headers(text: str) -> EmailHeaders:
    """Pull RFC-ish headers off a service-inbox export.

    Technician notes have no headers and come back with `is_email=False`, which
    is the signal to treat the document as a field note instead.
    """
    found: dict[str, str] = {}
    for match in _HEADER_RE.finditer(text[:1200]):
        found.setdefault(match.group("key").lower(), match.group("value").strip())

    if "from" not in found or "subject" not in found:
        return EmailHeaders()

    sender = found.get("from", "")
    addresses = _EMAIL_RE.findall(sender)
    sent_at = None
    if raw_date := found.get("date"):
        for fmt in (
            "%a, %d %b %Y %H:%M:%S %z",
            "%d %b %Y %H:%M:%S %z",
            "%a, %d %b %Y %H:%M:%S",
        ):
            try:
                sent_at = dt.datetime.strptime(raw_date.strip(), fmt).replace(tzinfo=None)
                break
            except ValueError:
                continue

    return EmailHeaders(
        sender=re.sub(r"<[^>]*>", "", sender).strip() or None,
        sender_address=addresses[0] if addresses else None,
        recipients=tuple(_EMAIL_RE.findall(found.get("to", ""))),
        cc=tuple(_EMAIL_RE.findall(found.get("cc", ""))),
        sent_at=sent_at,
        subject=found.get("subject"),
        is_email=True,
    )


def strip_headers(text: str) -> str:
    """Return the message body with the header block removed."""
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if not line.strip() and index:
            preceding = "\n".join(lines[:index])
            if _HEADER_RE.search(preceding):
                return "\n".join(lines[index + 1 :]).strip()
    return text.strip()


@dataclass(frozen=True)
class DueDate:
    """A deadline inferred from a phrase, with the phrase preserved."""

    due_on: dt.date
    phrase: str
    confidence: float
    basis: str


#: Ordered patterns. Earlier entries are more literal, hence more confident.
def find_due_date(text: str, reference: dt.date | None) -> DueDate | None:
    """Infer the deadline a piece of prose commits to.

    `reference` is the date the message was sent; relative phrases are
    meaningless without it, so they are skipped when it is unknown.
    """
    lowered = text.lower()

    iso = re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", text)
    if iso:
        try:
            return DueDate(dt.date.fromisoformat(iso.group(1)), iso.group(1), 0.95, "explicit_iso_date")
        except ValueError:
            pass

    if reference is None:
        return None

    # "by Monday", "on Friday"
    weekday = re.search(r"\b(?:by|on|before)\s+(" + "|".join(_WEEKDAYS) + r")\b", lowered)
    if weekday:
        target = _WEEKDAYS[weekday.group(1)]
        ahead = (target - reference.weekday()) % 7 or 7
        return DueDate(
            reference + dt.timedelta(days=ahead), weekday.group(0), 0.8, "relative_weekday"
        )

    # "within a couple of weeks", "within two weeks", "in 10 days"
    window = re.search(
        r"\b(?:within|in)\s+(?:a\s+)?(couple\s+of\s+|few\s+)?(\d+|one|two|three|four)?\s*"
        r"(day|days|week|weeks|month|months)\b",
        lowered,
    )
    if window:
        words = {"one": 1, "two": 2, "three": 3, "four": 4}
        vague, count, unit = window.groups()
        if count and count.isdigit():
            quantity = int(count)
        elif count in words:
            quantity = words[count]
        elif vague and "couple" in vague:
            quantity = 2
        elif vague and "few" in vague:
            quantity = 3
        else:
            quantity = 1
        days = {"day": 1, "days": 1, "week": 7, "weeks": 7, "month": 30, "months": 30}[unit]
        # A vague quantifier is a softer commitment than a counted one.
        confidence = 0.5 if vague else 0.75
        return DueDate(
            reference + dt.timedelta(days=quantity * days),
            window.group(0),
            confidence,
            "relative_window",
        )

    # "this week", "this coming week", "next week"
    soon = re.search(r"\b(this\s+(?:coming\s+)?week|next\s+week|end\s+of\s+the\s+week)\b", lowered)
    if soon:
        offset = 14 if soon.group(1).startswith("next") else 7
        return DueDate(reference + dt.timedelta(days=offset), soon.group(1), 0.6, "relative_week")

    # "mid-October", "early September"
    named = re.search(
        r"\b(early|mid|late)[-\s]+(" + "|".join(_MONTHS) + r")\b", lowered
    )
    if named:
        part, month_name = named.groups()
        month = _MONTHS[month_name]
        day = {"early": 5, "mid": 15, "late": 25}[part]
        year = reference.year + (1 if month < reference.month else 0)
        return DueDate(dt.date(year, month, day), named.group(0), 0.45, "named_month_part")

    return None


#: Verbs that signal an outbound promise rather than a description of work.
COMMITMENT_PATTERNS: tuple[tuple[str, str, float], ...] = (
    (r"\bi will\b|\bwe will\b|\bi'll\b|\bwe'll\b", "explicit_promise", 0.85),
    (r"\bi am arranging\b|\bwe are arranging\b|\bam arranging\b", "explicit_promise", 0.8),
    (r"\bwill (?:confirm|send|provide|get|have|schedule|arrange|follow up)\b", "explicit_promise", 0.85),
    (r"\bwe can have\b|\bi can have\b", "soft_promise", 0.6),
    (r"\b(?:can you|could you|please)\s+(?:have|send|provide|get)\b", "customer_request", 0.7),
    (r"\basked (?:for|us for)\b|\brequest(?:ing|ed)?\b", "customer_request", 0.55),
)


@dataclass(frozen=True)
class CommitmentSignal:
    sentence: str
    kind: str
    confidence: float


def find_commitments(body: str) -> list[CommitmentSignal]:
    """Sentences that promise something to a customer, or ask Sego for it."""
    signals: list[CommitmentSignal] = []
    for sentence in split_sentences(body):
        lowered = sentence.lower()
        for pattern, kind, confidence in COMMITMENT_PATTERNS:
            if re.search(pattern, lowered):
                signals.append(CommitmentSignal(sentence.strip(), kind, confidence))
                break
    return signals


_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")


def split_sentences(text: str) -> list[str]:
    """Split prose into sentences, tolerating the hard line wraps in these files."""
    unwrapped = re.sub(r"(?<![.!?:])\n(?!\n)", " ", text)
    out: list[str] = []
    for block in unwrapped.split("\n"):
        block = block.strip()
        if not block:
            continue
        out.extend(part.strip() for part in _SENTENCE_RE.split(block) if part.strip())
    return out
