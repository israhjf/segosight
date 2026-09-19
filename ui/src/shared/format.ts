/** Formatting shared across features, so one finding reads the same everywhere. */

export const currency = (value: number | null | undefined): string =>
  value == null
    ? "—"
    : new Intl.NumberFormat("en-US", {
        style: "currency",
        currency: "USD",
        maximumFractionDigits: 0,
      }).format(value);

export const shortDate = (value: string | null | undefined): string =>
  value ? new Date(value).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" }) : "—";

export const isoDate = (value: string | null | undefined): string =>
  value ? value.slice(0, 10) : "—";

export const percent = (value: number | null | undefined): string =>
  value == null ? "—" : `${Math.round(value * 100)}%`;

/** "18 days ago", "due in 3 days", "due today". */
export function dueLabel(dueOn: string | null, daysOverdue: number | null): string {
  if (daysOverdue != null && daysOverdue > 0) {
    return `${daysOverdue} day${daysOverdue === 1 ? "" : "s"} ago`;
  }
  if (!dueOn) return "no date";
  if (daysOverdue === 0) return "today";
  return `due ${isoDate(dueOn)}`;
}

/** risk_class / insight_type slugs into readable labels. */
export const humanize = (slug: string): string =>
  slug
    .split("_")
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");

export const fileName = (path: string | null | undefined): string =>
  path ? path.split("/").pop() ?? path : "—";
