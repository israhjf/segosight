export type Severity = "critical" | "high" | "medium" | "low";

export type Overview = {
  as_of_date: string | null;
  pending_review: number;
  active_alerts: number;
  critical_alerts: number;
  alerts_awaiting_prose_review: number;
  open_commitments: number;
};

export type ReviewItem = {
  insight_id: string;
  insight_type: string;
  summary: string;
  quote: string;
  author: string | null;
  authored_on: string | null;
  source_file: string;
  customer_id: string | null;
  customer_name: string | null;
  facility_id: string | null;
  facility_name: string | null;
  system_id: string | null;
  acv_usd: number | null;
  confidence_score: number;
  /** "rule" when a deterministic pattern produced it, "ai" when a model did. */
  provenance: "rule" | "ai";
  extractor: string;
  due_on: string | null;
  due_phrase: string | null;
  days_overdue: number | null;
  fulfilled: boolean | null;
  fulfillment_basis: string | null;
  commitment_subject: string | null;
  status: string;
  approve_verb: string;
  reject_verb: string;
};

export type Evidence = {
  evidence_id: string;
  quote: string | null;
  summary: string | null;
  source_file: string | null;
  authored_on: string | null;
  confidence_score: number | null;
  review_status: string;
};

export type Alert = {
  alert_id: string;
  risk_class: string;
  severity: Severity;
  priority_score: number;
  title: string;
  why: string;
  consequence: string;
  customer_id: string | null;
  customer_name: string | null;
  account_tier: string | null;
  acv_usd: number | null;
  facility_id: string | null;
  facility_name: string | null;
  system_id: string | null;
  system_label: string | null;
  parameter_code: string | null;
  owner: string | null;
  evidence_basis: string;
  unreviewed_evidence: number;
  evidence: Evidence[];
  first_observed: string | null;
  last_observed: string | null;
  /** Guideline revision that produced the judgement, e.g. treatment_guidelines_rev6. */
  rule_version: string | null;
};

export type SeriesPoint = {
  observed_at: string;
  value: number;
  collection_method: string;
  quality_status: string;
};

export type AlertDetail = Alert & {
  standard_unit: string | null;
  lower_limit: number | null;
  upper_limit: number | null;
  governing_program: string | null;
  series: SeriesPoint[];
  assessments: Array<Record<string, unknown>>;
  escalations: Array<Record<string, unknown>>;
  coverage: Record<string, unknown> | null;
};

export type DecisionResult = {
  insight_id: string;
  decision: string;
  reviewer: string;
  reviewed_at: string;
  commitment_created: string | null;
  evidence_links_updated: number;
  message: string;
};

export type PipelineResult = {
  ran_at: string;
  duration_seconds: number;
  before: Record<string, number>;
  after: Record<string, number>;
  delta: Record<string, number>;
  log: string[];
};

// --- Ingestion review --------------------------------------------------------

export type EntityPlan = {
  entity: string;
  file: string;
  rows: number;
  columns: string[];
  added_columns: string[];
  missing_columns: string[];
  new_keys: number;
  superseding_keys: number;
};

export type DocumentPlan = {
  document_class: string;
  directory: string;
  documents: number;
};

export type UnmatchedItem = {
  path: string;
  kind: "file" | "directory";
  suggestion: string | null;
  suggestion_target: string | null;
};

export type IngestFinding = {
  level: "blocking" | "advisory";
  code: string;
  message: string;
};

export type IngestProfile = {
  upload_id: string;
  batch_root: string;
  entities: EntityPlan[];
  documents: DocumentPlan[];
  unmatched: UnmatchedItem[];
  absent_entities: string[];
  findings: IngestFinding[];
  total_rows: number;
  total_documents: number;
  can_confirm: boolean;
};

export type MappingDecision = {
  path: string;
  kind: "document" | "entity" | "exclude";
  target?: string | null;
};

export type ConfirmResult = {
  batch_name: string;
  sequence: number;
  files_promoted: number;
  aliases_added: string[];
  excluded: string[];
  duration_seconds: number;
  before: Record<string, number>;
  after: Record<string, number>;
  delta: Record<string, number>;
};
