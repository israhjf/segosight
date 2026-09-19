"""Optional LLM enrichment for prose extraction. Disabled by default.

The deterministic extractors in `curated.extraction` are the product. This
module is strictly additive: when a local open-weight model is available it
proposes *additional* candidate insights that the rule patterns missed, and
those candidates land in the same `curated.extracted_insight` table with
`status = 'pending_review'` and a reduced confidence ceiling.

Why it is optional
------------------
An evaluator must be able to clone and run the system with no model download,
and the tests must be deterministic. Nothing in the pipeline depends on this
module; with it off, SegoSight loses recall on unusual phrasing and loses
nothing else.

Why a local model
-----------------
The corpus contains customer names, contacts and healthcare compliance
material. Sending it to a hosted API would export client data for a recall
improvement on 67 documents. A local Ollama model keeps it on the machine and
costs nothing, which also satisfies the no-spend constraint.

Failure modes, and what contains them
-------------------------------------
* **Fabricated deadlines and commitments.** A model will happily invent a date
  that is not in the text. Contained by requiring the model to return a verbatim
  `quote`, and discarding any candidate whose quote is not found in the source
  document. A candidate that cannot point at its own evidence is dropped.
* **Wrong entity attribution.** Contained by ignoring any system or facility the
  model names and re-deriving linkage with the deterministic `Linker`.
* **Overconfidence.** Contained by capping model confidence at
  `MAX_LLM_CONFIDENCE`, below the threshold any reviewer-facing default would
  auto-approve.
* **Non-determinism.** Contained by temperature 0 and by excluding this path
  from the test suite's assertions.

No model output is ever written to a compliance record, an identity crosswalk
or an alert without a human approving the row first.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass

#: A model proposal never outranks a deterministic match.
MAX_LLM_CONFIDENCE = 0.55

DEFAULT_ENDPOINT = os.environ.get("SEGOSIGHT_OLLAMA", "http://localhost:11434")
DEFAULT_MODEL = os.environ.get("SEGOSIGHT_LLM_MODEL", "llama3.2:3b")

PROMPT = """You extract operational facts from water-treatment field notes and \
customer emails for a service company.

Return ONLY a JSON array. Each element must have:
  "insight_type": one of commitment, customer_request, field_concern, recommendation
  "summary": one short sentence in your own words
  "quote": the EXACT sentence from the document that supports it, copied verbatim
  "due_phrase": any deadline wording present, or null

Rules:
- Copy "quote" character for character from the document. Do not paraphrase it.
- If nothing qualifies, return [].
- Do not infer facts that are not stated.

Document:
---
{document}
---
"""


@dataclass(frozen=True)
class Candidate:
    insight_type: str
    summary: str
    quote: str
    due_phrase: str | None
    confidence: float


def available(endpoint: str = DEFAULT_ENDPOINT, timeout: float = 1.5) -> bool:
    """True when a local Ollama server is reachable."""
    try:
        with urllib.request.urlopen(f"{endpoint}/api/tags", timeout=timeout):
            return True
    except (urllib.error.URLError, OSError, ValueError):
        return False


def propose(
    document_text: str,
    *,
    endpoint: str = DEFAULT_ENDPOINT,
    model: str = DEFAULT_MODEL,
    timeout: float = 60.0,
) -> list[Candidate]:
    """Ask a local model for additional candidates. Never raises.

    Candidates whose `quote` does not appear verbatim in the source are
    discarded: a model that cannot point at its evidence has fabricated it.
    """
    payload = json.dumps(
        {
            "model": model,
            "prompt": PROMPT.format(document=document_text[:6000]),
            "stream": False,
            "format": "json",
            "options": {"temperature": 0},
        }
    ).encode("utf-8")

    request = urllib.request.Request(
        f"{endpoint}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read())
        raw = json.loads(body.get("response", "[]"))
    except Exception:  # noqa: BLE001 - enrichment must never break the pipeline
        return []

    if isinstance(raw, dict):
        raw = raw.get("insights") or raw.get("results") or []
    if not isinstance(raw, list):
        return []

    return [c for c in (_validate(item, document_text) for item in raw) if c]


_ALLOWED = frozenset(
    {"commitment", "customer_request", "field_concern", "recommendation"}
)


def _validate(item: object, document_text: str) -> Candidate | None:
    """Reject anything malformed, mistyped, or not grounded in the source."""
    if not isinstance(item, dict):
        return None
    insight_type = str(item.get("insight_type", "")).strip().lower()
    quote = str(item.get("quote", "")).strip()
    summary = str(item.get("summary", "")).strip()
    if insight_type not in _ALLOWED or not quote or not summary:
        return None

    # Grounding check: the quote must really be in the document. Whitespace is
    # normalised because these files are hard-wrapped mid-sentence.
    haystack = " ".join(document_text.split()).lower()
    needle = " ".join(quote.split()).lower()
    if len(needle) < 12 or needle not in haystack:
        return None

    due_phrase = item.get("due_phrase")
    return Candidate(
        insight_type=insight_type,
        summary=summary[:300],
        quote=quote[:600],
        due_phrase=str(due_phrase)[:120] if due_phrase else None,
        confidence=MAX_LLM_CONFIDENCE,
    )
