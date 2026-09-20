"""Response and request models for the SegoSight API."""

from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, Field


class Overview(BaseModel):
    as_of_date: dt.date | None
    pending_review: int
    active_alerts: int
    critical_alerts: int
    alerts_awaiting_prose_review: int
    open_commitments: int
    last_pipeline_run: dt.datetime | None = None


class ReviewItem(BaseModel):
    insight_id: str
    insight_type: str
    summary: str
    quote: str
    author: str | None
    authored_on: dt.date | None
    source_file: str
    customer_id: str | None
    customer_name: str | None
    facility_id: str | None
    facility_name: str | None
    system_id: str | None
    acv_usd: float | None
    confidence_score: float
    #: "rule" | "ai" -- drives the provenance chip.
    provenance: str
    extractor: str
    due_on: dt.date | None
    due_phrase: str | None
    days_overdue: int | None
    fulfilled: bool | None
    fulfillment_basis: str | None
    commitment_subject: str | None
    status: str
    #: Verb shown on the approve button, e.g. "Merge" or "Attach".
    approve_verb: str
    reject_verb: str


class Decision(BaseModel):
    decision: str = Field(pattern="^(approved|rejected)$")
    reviewer: str = Field(min_length=1, max_length=120)
    note: str | None = Field(default=None, max_length=600)


class DecisionResult(BaseModel):
    insight_id: str
    decision: str
    reviewer: str
    reviewed_at: str
    commitment_created: str | None
    evidence_links_updated: int
    message: str


class Evidence(BaseModel):
    evidence_id: str
    quote: str | None
    summary: str | None
    source_file: str | None
    authored_on: dt.date | None
    confidence_score: float | None
    review_status: str


class AlertSummary(BaseModel):
    alert_id: str
    risk_class: str
    severity: str
    priority_score: float
    title: str
    why: str
    consequence: str
    customer_id: str | None
    customer_name: str | None
    account_tier: str | None
    acv_usd: float | None
    facility_id: str | None
    facility_name: str | None
    system_id: str | None
    system_label: str | None
    parameter_code: str | None
    owner: str | None
    evidence_basis: str
    unreviewed_evidence: int
    evidence: list[Evidence] = []
    first_observed: dt.datetime | None
    last_observed: dt.datetime | None
    # The guideline revision that produced this judgement. Stamped on every
    # curated row; exposed here because an exported finding without its rule
    # version is an opinion, not evidence.
    rule_version: str | None = None


class SeriesPoint(BaseModel):
    observed_at: dt.datetime
    value: float
    collection_method: str
    quality_status: str


class AlertDetail(AlertSummary):
    standard_unit: str | None = None
    lower_limit: float | None = None
    upper_limit: float | None = None
    governing_program: str | None = None
    series: list[SeriesPoint] = []
    assessments: list[dict] = []
    escalations: list[dict] = []
    coverage: dict | None = None


class PipelineResult(BaseModel):
    ran_at: dt.datetime
    duration_seconds: float
    before: dict
    after: dict
    delta: dict
    log: list[str]


# --- Ingestion review --------------------------------------------------------


class EntityPlan(BaseModel):
    """What one staged file would do to one entity."""

    entity: str
    file: str
    rows: int
    columns: list[str]
    added_columns: list[str]
    missing_columns: list[str]
    new_keys: int
    superseding_keys: int


class DocumentPlan(BaseModel):
    document_class: str
    directory: str
    documents: int


class UnmatchedItem(BaseModel):
    path: str
    kind: str
    suggestion: str | None = None
    suggestion_target: str | None = None


class IngestFinding(BaseModel):
    level: str
    code: str
    message: str


class IngestProfile(BaseModel):
    upload_id: str
    batch_root: str
    entities: list[EntityPlan] = []
    documents: list[DocumentPlan] = []
    unmatched: list[UnmatchedItem] = []
    absent_entities: list[str] = []
    findings: list[IngestFinding] = []
    total_rows: int
    total_documents: int
    can_confirm: bool


class MappingDecision(BaseModel):
    path: str
    kind: str
    target: str | None = None


class ConfirmRequest(BaseModel):
    uploader: str
    #: What to call this batch. Defaults to the uploaded folder's name.
    batch_name: str | None = None
    #: The system this export came from. Not cosmetic: it is how downstream
    #: logic knows to expect FieldFlow's M/D/YYYY dates and technician initials
    #: rather than ServiceTrak's full names.
    source_system: str = "Upload"
    mappings: list[MappingDecision] = []


class ConfirmResult(BaseModel):
    batch_name: str
    sequence: int
    files_promoted: int
    aliases_added: list[str] = []
    excluded: list[str] = []
    duration_seconds: float
    before: dict[str, int]
    after: dict[str, int]
    delta: dict[str, int]
