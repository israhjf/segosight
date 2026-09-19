import { createTheme, type Theme } from "@mui/material/styles";

import { schemes, type MaterialScheme, type SchemeName } from "./tokens.generated";
import { severityColors, WARNING, type SeverityColors } from "./severity";

export type ColorMode = "light" | "dark";
export type Contrast = "normal" | "medium" | "high";

declare module "@mui/material/styles" {
  interface Palette {
    severity: Record<string, SeverityColors>;
    material: MaterialScheme;
  }
  interface PaletteOptions {
    severity?: Record<string, SeverityColors>;
    material?: MaterialScheme;
  }
}

export function schemeName(mode: ColorMode, contrast: Contrast): SchemeName {
  if (contrast === "normal") return mode;
  const suffix = contrast === "high" ? "HighContrast" : "MediumContrast";
  return `${mode}${suffix}` as SchemeName;
}

/**
 * Builds the MUI theme from a Material scheme.
 *
 * Every colour below traces to a `--md-sys-color-*` token, so the palette is
 * the single source of truth rather than something re-specified in component
 * styles. Surfaces use Material 3's container ramp: the page sits on
 * `surface`, cards on `surfaceContainerLow`, and raised elements step up from
 * there, which is what gives the layout depth without shadows.
 */
export function buildTheme(mode: ColorMode, contrast: Contrast): Theme {
  const s: MaterialScheme = schemes[schemeName(mode, contrast)];

  return createTheme({
    cssVariables: true,
    palette: {
      mode,
      material: s,
      severity: severityColors(s, mode),
      primary: {
        main: s.primary,
        contrastText: s.onPrimary,
        light: s.primaryContainer,
        dark: s.onPrimaryContainer,
      },
      secondary: {
        main: s.secondary,
        contrastText: s.onSecondary,
        light: s.secondaryContainer,
        dark: s.onSecondaryContainer,
      },
      error: { main: s.error, contrastText: s.onError, light: s.errorContainer },
      warning: { main: WARNING[mode].main, light: WARNING[mode].container },
      info: { main: s.tertiary, contrastText: s.onTertiary },
      success: { main: s.tertiary, contrastText: s.onTertiary },
      background: { default: s.surface, paper: s.surfaceContainerLow },
      text: {
        primary: s.onSurface,
        secondary: s.onSurfaceVariant,
        disabled: s.outline,
      },
      divider: s.outlineVariant,
    },
    shape: { borderRadius: 12 },
    typography: {
      fontFamily: '"Roboto", "Helvetica", "Arial", sans-serif',
      h1: { fontSize: "1.75rem", fontWeight: 500, letterSpacing: "-0.01em" },
      h2: { fontSize: "1.375rem", fontWeight: 500 },
      h3: { fontSize: "1.125rem", fontWeight: 500 },
      subtitle2: { fontWeight: 500, letterSpacing: "0.02em" },
      overline: { fontWeight: 600, letterSpacing: "0.08em", fontSize: "0.6875rem" },
      button: { textTransform: "none", fontWeight: 500 },
    },
    components: {
      MuiCssBaseline: {
        styleOverrides: {
          body: { backgroundColor: s.surface, color: s.onSurface },
          // The evidence quotes are verbatim source text; a monospace face
          // signals "this is what the document says" rather than UI copy.
          "code, .quote": { fontFamily: '"Roboto Mono", ui-monospace, monospace' },
        },
      },
      MuiPaper: {
        styleOverrides: {
          root: { backgroundImage: "none", borderColor: s.outlineVariant },
        },
      },
      MuiCard: {
        defaultProps: { variant: "outlined" },
        styleOverrides: {
          root: {
            backgroundColor: s.surfaceContainerLow,
            borderColor: s.outlineVariant,
          },
        },
      },
      MuiChip: { styleOverrides: { root: { fontWeight: 500 } } },
      MuiAppBar: {
        defaultProps: { elevation: 0, color: "transparent" },
        styleOverrides: {
          root: {
            backgroundColor: s.surfaceContainer,
            color: s.onSurface,
            borderBottom: `1px solid ${s.outlineVariant}`,
          },
        },
      },
      MuiButton: { defaultProps: { disableElevation: true } },
      MuiTooltip: {
        defaultProps: { arrow: true },
        styleOverrides: {
          tooltip: {
            backgroundColor: s.inverseSurface,
            color: s.inverseOnSurface,
            fontSize: "0.75rem",
          },
        },
      },
    },
  });
}
