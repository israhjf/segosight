"""Curated tier: operational facts extracted from prose, pending human review.

Every row this module writes is a *proposal*. It lands with an explicit
`confidence_score` and `status = 'pending_review'`, and nothing downstream
treats it as fact until a reviewer approves it. That constraint is deliberate
and absolute: several of these documents concern a hospital's accreditation
documentation, and a compliance record must never be altered on the strength of
a pattern match or a model's guess.

The guidelines make the same point from the operational side -- section 9 says
verbal notification is a courtesy and the work order is the record, and section
5.3 says the escalation exists on paper or it did not happen. So extraction
surfaces what was said; only a human can promote it to what was done.

What is extracted:

* commitments -- promises Sego made, with the deadline they implied;
* customer requests -- inbound asks carrying a deadline;
* field concerns -- technician-raised issues, checked against work orders;
* recommendations -- proposed actions awaiting a decision;
* identity candidates -- crosswalk or merge proposals stated in prose.
"""

from __future__ import annotations

import datetime as dt
import re

import duckdb

from ..ingest.documents import TABLE as DOCUMENTS
from ..normalize.prose import (
    find_commitments,
    find_due_date,
    parse_email_headers,
    split_sentences,
    strip_headers,
)
from ..warehouse import CURATED, bulk_insert
from .linking import Linker

TABLE = f"{CURATED}.extracted_insight"
REVIEW_QUEUE_VIEW = f"{CURATED}.review_queue"

PENDING = "pending_review"
EXTRACTOR = "deterministic/v1"

#: Days a technician's written concern has to become a work order before it
#: counts as undocumented (guidelines section 9 says one business day for
#: safety, compliance or equipment-integrity risks; 14 days is deliberately
#: generous so only genuinely dropped flags surface).
_CONCERN_WINDOW_DAYS = 14

COMMITMENT = "commitment"
CUSTOMER_REQUEST = "customer_request"
FIELD_CONCERN = "field_concern"
RECOMMENDATION = "recommendation"
IDENTITY_CANDIDATE = "identity_candidate"

#: Language a technician uses when flagging something the office should act on.
_CONCERN_PATTERNS = (
    (r"\bneeds? a decision\b", 0.85),
    (r"\braised (?:this |it )?(?:with|to)\b", 0.8),
    (r"\btold the office\b|\bflagged\b|\breported to the office\b", 0.8),
    (r"\bneeds? (?:to be |a )?(?:looked at|work order|follow ?up|attention)\b", 0.8),
    (r"\bstill waiting\b|\bstill (?:no|not)\b|\bnever (?:got|happened)\b", 0.75),
    (r"\bwe should\b|\bsomebody should\b|\bsomeone should\b", 0.7),
    (r"\bconcern(?:ed|s)?\b|\bworried\b|\bnot happy\b", 0.6),
)

#: Idioms that contain concern vocabulary but assert the opposite. "Done as far
#: as I'm concerned" is a technician closing something out, not raising it.
_CONCERN_EXCLUSIONS = (
    r"as far as (?:i|im|i'm) concerned",
    r"\bno concerns?\b",
    r"\bnothing to (?:worry|report)\b",
)

_RECOMMENDATION_PATTERNS = (
    (r"\brecommend(?:ed|ing|s)?\b", 0.8),
    (r"\bshould (?:consider|move|firm up|convert|replace|upgrade)\b", 0.7),
    (r"\bconsider (?:moving|offline|converting|replacing)\b", 0.7),
    (r"\bproposal\b|\bproposed\b", 0.65),
)

#: What a commitment is actually *for*. Fulfilment evidence has to match the
#: deliverable: a routine service visit does not hand over an accreditation
#: documentation packet, and treating it as though it does is how "we sent
#: someone" gets mistaken for "we sent the report".
_SUBJECT_PATTERNS = (
    (r"\bdocument(?:ation|s)?\b|\breport\b|\bpacket\b|\brecords?\b|\bsds\b|"
     r"\bcertificate\b|\bcoi\b|\bsummary\b|\bhistory\b", "documentation"),
    (r"\bremediation plan\b|\bplan\b|\bproposal\b|\bquote\b|\bprice\b", "plan"),
    (r"\bvisit\b|\btechnician\b|\bcoverage\b|\bservice\b|\bschedul\w+\b|"
     r"\bonsite\b|\bon site\b|\bcallout\b", "visit"),
)

_IDENTITY_PATTERNS = (
    (r"\b=\s*(?:SYS-\d{4}|the\b)", 0.7),
    (r"\bcrosswalk\b|\bmaps? to\b|\bsame as\b|\bduplicate\b|\bretired\b|\bmerged?\b", 0.7),
)

_DDL = f"""
CREATE OR REPLACE TABLE {TABLE} (
    insight_id        VARCHAR NOT NULL,
    document_id       VARCHAR NOT NULL,
    source_file       VARCHAR NOT NULL,
    document_class    VARCHAR NOT NULL,
    authored_on       DATE,
    insight_type      VARCHAR NOT NULL,
    summary           VARCHAR NOT NULL,
    quote             VARCHAR NOT NULL,
    author            VARCHAR,
    counterparty      VARCHAR,
    customer_id       VARCHAR,
    facility_id       VARCHAR,
    system_id         VARCHAR,
    commitment_subject VARCHAR,
    link_confidence   DOUBLE,
    link_basis        VARCHAR,
    due_on            DATE,
    due_phrase        VARCHAR,
    due_confidence    DOUBLE,
    confidence_score  DOUBLE NOT NULL,
    status            VARCHAR NOT NULL,
    review_decision   VARCHAR,
    reviewed_by       VARCHAR,
    reviewed_at       TIMESTAMP,
    fulfilled         BOOLEAN,
    fulfillment_basis VARCHAR,
    days_overdue      INTEGER,
    extractor         VARCHAR NOT NULL,
    extracted_at      TIMESTAMP NOT NULL
)
"""

_COLUMNS = [
    "insight_id", "document_id", "source_file", "document_class", "authored_on",
    "insight_type", "summary", "quote", "author", "counterparty", "customer_id",
    "facility_id", "system_id", "commitment_subject", "link_confidence",
    "link_basis", "due_on",
    "due_phrase", "due_confidence", "confidence_score", "status",
    "review_decision", "reviewed_by", "reviewed_at", "fulfilled",
    "fulfillment_basis", "days_overdue", "extractor", "extracted_at",
]

_REVIEW_VIEW = f"""
CREATE OR REPLACE VIEW {REVIEW_QUEUE_VIEW} AS
SELECT insight_id, insight_type, summary, quote, source_file, authored_on,
       customer_id, facility_id, system_id, commitment_subject,
       link_confidence, due_on, confidence_score, fulfilled, days_overdue,
       fulfillment_basis, extractor, status
FROM {TABLE}
WHERE status = '{PENDING}'
ORDER BY
    -- Overdue and unfulfilled first, then least certain, so a reviewer sees
    -- the consequential and the doubtful before the routine.
    coalesce(fulfilled, true) ASC,
    coalesce(days_overdue, 0) DESC,
    confidence_score ASC
"""


def _match(patterns, text: str, exclusions: tuple[str, ...] = ()) -> float | None:
    lowered = text.lower()
    if any(re.search(pattern, lowered) for pattern in exclusions):
        return None
    for pattern, confidence in patterns:
        if re.search(pattern, lowered):
            return confidence
    return None


def _score(*components: float) -> float:
    """Combine signal confidences conservatively: the weakest link governs."""
    values = [c for c in components if c is not None]
    if not values:
        return 0.0
    return round(min(values) * (0.9 + 0.1 * (len(values) > 1)), 3)


def build(
    conn: duckdb.DuckDBPyConnection,
    as_of: dt.date | None = None,
    extracted_at: dt.datetime | None = None,
) -> dict[str, int]:
    """Extract candidate insights from every landed document."""
    conn.execute(_DDL)
    linker = Linker(conn)
    stamp = extracted_at or dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)

    reference = as_of or conn.execute(
        "SELECT max(visit_date) FROM canonical.service_visit"
    ).fetchone()[0]

    documents = conn.execute(
        f"""SELECT document_id, source_file, file_name, document_class,
                   filename_date, filename_slug, filename_topic, body
            FROM {DOCUMENTS}
            WHERE extraction_status = 'ok'
            ORDER BY file_name"""
    ).fetchall()

    rows: list[tuple] = []

    def add(
        document, insight_type, summary, quote, author, counterparty, mentions,
        confidence, due=None, index=0,
    ):
        subject = None
        if insight_type in (COMMITMENT, CUSTOMER_REQUEST):
            lowered = quote.lower()
            subject = next(
                (name for pattern, name in _SUBJECT_PATTERNS if re.search(pattern, lowered)),
                "other",
            )
        document_id, source_file, _, document_class, authored, *_ = document
        facility_id, link_confidence, link_basis = mentions.best_facility
        system_id = mentions.system_ids[0] if mentions.system_ids else None
        rows.append(
            (
                f"{document_id}:{insight_type}:{index}",
                document_id, source_file, document_class, authored, insight_type,
                summary, quote[:600], author, counterparty,
                linker.customer_for(facility_id), facility_id, system_id,
                subject, link_confidence, link_basis,
                due.due_on if due else None,
                due.phrase if due else None,
                due.confidence if due else None,
                _score(confidence, link_confidence or None, due.confidence if due else None),
                PENDING, None, None, None, None, None, None, EXTRACTOR, stamp,
            )
        )

    for document in documents:
        (document_id, source_file, file_name, document_class, authored,
         slug, topic, body) = document

        headers = parse_email_headers(body)
        text = strip_headers(body) if headers.is_email else body
        mentions = linker.find(body, f"{slug} {topic}")
        authored_on = headers.sent_at.date() if headers.sent_at else authored
        author = headers.sender if headers.is_email else (slug or "").title()
        counterparty = headers.recipients[0] if headers.recipients else None
        is_from_sego = bool(
            headers.sender_address and "segoindustrialwater" in headers.sender_address
        )

        # --- commitments and inbound requests ---------------------------
        for index, signal in enumerate(find_commitments(text)):
            due = find_due_date(signal.sentence, authored_on) or find_due_date(
                text, authored_on
            )
            if signal.kind == "customer_request":
                insight_type = CUSTOMER_REQUEST
                summary = "Customer asked Sego for something with a deadline"
            elif is_from_sego or not headers.is_email:
                insight_type = COMMITMENT
                summary = "Sego promised the customer an action"
            else:
                continue
            add(
                document, insight_type, summary, signal.sentence, author,
                counterparty, mentions, signal.confidence, due, index,
            )

        # --- field concerns and recommendations --------------------------
        if document_class == "technician_note":
            for index, sentence in enumerate(split_sentences(text)):
                concern = _match(_CONCERN_PATTERNS, sentence, _CONCERN_EXCLUSIONS)
                recommendation = _match(_RECOMMENDATION_PATTERNS, sentence)
                if recommendation is not None:
                    add(
                        document, RECOMMENDATION,
                        "Technician recommended an action awaiting a decision",
                        sentence, author, None, mentions, recommendation,
                        None, index,
                    )
                elif concern is not None:
                    add(
                        document, FIELD_CONCERN,
                        "Technician raised a concern in a note",
                        sentence, author, None, mentions, concern, None, index,
                    )

        # --- identity and crosswalk proposals ----------------------------
        if _match(_IDENTITY_PATTERNS, text) and (
            mentions.system_ids or "CUST-" in text
        ):
            confidence = _match(_IDENTITY_PATTERNS, text)
            add(
                document, IDENTITY_CANDIDATE,
                "Prose proposes an identifier mapping or account merge",
                next(
                    (s for s in split_sentences(text) if _match(_IDENTITY_PATTERNS, s)),
                    text[:300],
                ),
                author, None, mentions, confidence, None, 0,
            )

    bulk_insert(conn, TABLE, _COLUMNS, rows)
    _assess_fulfilment(conn, reference)
    _assess_concern_documentation(conn, reference)
    conn.execute(_REVIEW_VIEW)

    return {
        "insights": len(rows),
        "pending": conn.execute(
            f"SELECT count(*) FROM {TABLE} WHERE status = '{PENDING}'"
        ).fetchone()[0],
    }


def _assess_fulfilment(conn: duckdb.DuckDBPyConnection, reference: dt.date) -> None:
    """Annotate commitments with whatever evidence of delivery exists.

    Evidence must match the deliverable. A service visit evidences a promised
    visit; it evidences nothing about a promised documentation packet, and the
    system says so rather than guessing. Where the deliverable is a document or
    a plan, the pipeline has no structured record of it at all -- there is no
    outbound-document store -- so fulfilment is left NULL and the reviewer is
    told why.

    This annotates a row that still requires review. It closes nothing.
    """
    conn.execute(
        f"""
        WITH evidence AS (
            SELECT i.insight_id,
                   max(v.visit_id)   AS visit_id,
                   count(v.visit_id) AS visits
            FROM {TABLE} i
            LEFT JOIN canonical.service_visit v
              ON v.facility_id = i.facility_id
             AND v.visit_date > i.authored_on
             AND v.visit_date <= coalesce(i.due_on, i.authored_on + 30)
            WHERE i.insight_type IN ('{COMMITMENT}', '{CUSTOMER_REQUEST}')
            GROUP BY i.insight_id
        )
        UPDATE {TABLE} AS t
        SET fulfilled = CASE
                WHEN t.commitment_subject = 'visit' THEN (e.visits > 0)
                ELSE NULL
            END,
            fulfillment_basis = CASE
                WHEN t.commitment_subject = 'visit' AND e.visits > 0
                    THEN 'service visit ' || e.visit_id || ' before the deadline'
                WHEN t.commitment_subject = 'visit'
                    THEN 'no service visit at this facility before the deadline'
                ELSE 'deliverable is a ' || coalesce(t.commitment_subject, 'document')
                     || '; no structured record exists to evidence delivery'
            END,
            days_overdue = CASE
                WHEN t.due_on IS NOT NULL AND t.due_on <= DATE '{reference}'
                     AND NOT (t.commitment_subject = 'visit' AND e.visits > 0)
                THEN date_diff('day', t.due_on, DATE '{reference}')
                ELSE NULL
            END
        FROM evidence e
        WHERE e.insight_id = t.insight_id
        """
    )


def _assess_concern_documentation(
    conn: duckdb.DuckDBPyConnection, reference: dt.date
) -> None:
    """Check whether a technician's written concern ever became a work order.

    This is the company's stated pain in their own words: "Technicians flag
    things in notes and verbally on site, and some of those flags deserve work
    orders and customer conversations that never happen." Guidelines section 9
    settles what counts -- verbal notification is a courtesy, the work order is
    the record.

    A concern is treated as documented when a work order was raised at the same
    facility within `_CONCERN_WINDOW_DAYS` of the note. The window matters for
    the same reason it does in the microbiological ladder: a work order raised
    months later is real remediation but is not evidence that the flag was
    acted on when it was made.
    """
    conn.execute(
        f"""
        WITH orders AS (
            SELECT json_extract_string(payload, '$.facility_id') AS facility_id,
                   try_cast(json_extract_string(payload, '$.created_date') AS DATE) AS created,
                   json_extract_string(payload, '$.wo_id') AS wo_id
            FROM clean.record_versions
            WHERE entity = 'work_orders' AND is_current
        ),
        matched AS (
            SELECT i.insight_id,
                   count(o.wo_id) AS orders,
                   min(o.wo_id)   AS wo_id
            FROM {TABLE} i
            LEFT JOIN orders o
              ON o.facility_id = i.facility_id
             AND o.created >= i.authored_on
             AND o.created <= i.authored_on + {_CONCERN_WINDOW_DAYS}
            WHERE i.insight_type IN ('{FIELD_CONCERN}', '{RECOMMENDATION}')
            GROUP BY i.insight_id
        )
        UPDATE {TABLE} AS t
        SET fulfilled = (m.orders > 0),
            fulfillment_basis = CASE
                WHEN m.orders > 0
                    THEN 'work order ' || m.wo_id || ' raised within '
                         || {_CONCERN_WINDOW_DAYS} || ' days'
                ELSE 'no work order raised at this facility within '
                     || {_CONCERN_WINDOW_DAYS} || ' days of the note'
            END,
            days_overdue = CASE
                WHEN m.orders = 0
                THEN date_diff('day', t.authored_on, DATE '{reference}')
                ELSE NULL
            END
        FROM matched m
        WHERE m.insight_id = t.insight_id
        """
    )
