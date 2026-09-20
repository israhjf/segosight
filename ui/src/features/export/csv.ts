import type { Alert } from "@/shared/types";

/**
 * CSV export of the governed alert queue.
 *
 * Two rules govern the shape of this file:
 *
 * 1. It exports what is on screen, because that is what "export" means to the
 *    person clicking it -- but it writes its own scope into the file. A
 *    six-row export of a forty-one-row queue, forwarded to a hospital, must
 *    not be readable as the complete record.
 * 2. It is the *internal* artefact, so it carries pending prose extractions
 *    with their review state visible. The customer-facing packet is the print
 *    report, which withholds them.
 */

const COLUMNS = [
  "alert_id",
  "severity",
  "priority_score",
  "risk_class",
  "title",
  "why",
  "consequence",
  "customer_name",
  "account_tier",
  "acv_usd",
  "facility_name",
  "system_id",
  "system_label",
  "parameter_code",
  "owner",
  "evidence_basis",
  "evidence_count",
  "pending_evidence",
  "first_observed",
  "last_observed",
  "rule_version",
] as const;

function cell(value: unknown): string {
  if (value === null || value === undefined) return "";
  const text = String(value);
  // Quote anything that could break the row, and double embedded quotes.
  return /[",\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

function row(alert: Alert): string {
  const pending = alert.evidence.filter((e) => e.review_status === "pending_review").length;
  return [
    alert.alert_id,
    alert.severity,
    alert.priority_score.toFixed(2),
    alert.risk_class,
    alert.title,
    alert.why,
    alert.consequence,
    alert.customer_name,
    alert.account_tier,
    alert.acv_usd,
    alert.facility_name,
    alert.system_id,
    alert.system_label,
    alert.parameter_code,
    alert.owner,
    alert.evidence_basis,
    alert.evidence.length,
    pending,
    alert.first_observed,
    alert.last_observed,
    alert.rule_version,
  ]
    .map(cell)
    .join(",");
}

export type CsvContext = {
  alerts: Alert[];
  /** The filter in force: "all", or a severity. */
  severity: string;
  /** Latest observation in the warehouse. */
  asOf: string | null;
  /** Total alerts in the queue before filtering. */
  totalAlerts: number;
  reviewer: string;
};

export function buildCsv({
  alerts,
  severity,
  asOf,
  totalAlerts,
  reviewer,
}: CsvContext): string {
  const generatedAt = new Date().toISOString();
  const versions = Array.from(
    new Set(alerts.map((a) => a.rule_version).filter(Boolean))
  );
  const pending = alerts.reduce(
    (sum, a) => sum + a.evidence.filter((e) => e.review_status === "pending_review").length,
    0
  );

  // Provenance rows first. Commented so a parser can skip them, present so a
  // human opening the file in Excel cannot mistake a filtered slice for the
  // whole governed table.
  const header = [
    `# SegoSight governed alerts`,
    `# generated_at,${generatedAt}`,
    `# generated_by,${cell(reviewer)}`,
    `# data_as_of,${asOf ?? "unknown"}`,
    `# rule_version,${versions.join(" ") || "unknown"}`,
    `# severity_filter,${severity}`,
    `# rows_exported,${alerts.length}`,
    `# rows_in_queue,${totalAlerts}`,
    `# scope,${
      alerts.length === totalAlerts
        ? "complete governed queue"
        : `filtered view (${alerts.length} of ${totalAlerts})`
    }`,
    `# pending_evidence_included,${pending}`,
  ];

  return [...header, COLUMNS.join(","), ...alerts.map(row)].join("\r\n");
}

export function csvFilename(severity: string, asOf: string | null): string {
  const scope = severity === "all" ? "all" : severity;
  return `segosight-alerts_${scope}_${asOf ?? "undated"}.csv`;
}

/** Hands the file to the browser. */
export function downloadCsv(filename: string, body: string): void {
  // The BOM keeps Excel from mangling the degree signs and quotes in the
  // finding text when it opens the file on a Windows machine.
  const blob = new Blob(["﻿", body], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}
