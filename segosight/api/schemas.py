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
