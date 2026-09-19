import type { MaterialScheme } from "./tokens.generated";

/**
 * Severity colour roles.
 *
 * The Material Theme Builder export defines primary, secondary, tertiary and
 * error. It has no "warning" role, but SegoSight has four severities and
 * collapsing high into error would flatten the distinction Dana relies on
 * between "act today" and "act this week".
 *
 * So `high` is an explicit extension rather than a token from the export, and
 * it is the only colour in the app not taken from the handoff. It is tuned per
 * mode to clear 4.5:1 against that mode's surface.
 */
export type Severity = "critical" | "high" | "medium" | "low";

export const WARNING = {
  light: { main: "#8a5100", container: "#ffddb3", onContainer: "#2b1700" },
  dark: { main: "#ffb95c", container: "#6a3d00", onContainer: "#ffddb3" },
} as const;

export type SeverityColors = {
  main: string;
  container: string;
  onContainer: string;
};

/** Maps a severity onto the scheme in force. */
export function severityColors(
  scheme: MaterialScheme,
  mode: "light" | "dark"
): Record<Severity, SeverityColors> {
  return {
    critical: {
      main: scheme.error,
      container: scheme.errorContainer,
      onContainer: scheme.onErrorContainer,
    },
    high: {
      main: WARNING[mode].main,
      container: WARNING[mode].container,
      onContainer: WARNING[mode].onContainer,
    },
    medium: {
      main: scheme.tertiary,
      container: scheme.tertiaryContainer,
      onContainer: scheme.onTertiaryContainer,
    },
    low: {
      main: scheme.onSurfaceVariant,
      container: scheme.surfaceContainerHigh,
      onContainer: scheme.onSurfaceVariant,
    },
  };
}

export const SEVERITY_ORDER: Severity[] = ["critical", "high", "medium", "low"];
