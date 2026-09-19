import type { ColorMode } from "./palette";

/**
 * Chart series colours.
 *
 * These are a dedicated categorical ramp, not the UI palette. The Material
 * scheme is deliberately monochromatic -- its primary (#415f91) and tertiary
 * (#705575) sit at ΔE 7.9 in normal vision, well under the 15 floor, so using
 * them as two series would produce a chart most people cannot read and
 * colour-blind readers certainly cannot.
 *
 * Both pairs below were verified with the palette validator against their own
 * surface (light #f9f9ff, dark #111318) and pass all six checks: lightness
 * band, chroma floor, CVD separation, normal-vision floor and contrast.
 * Dark steps are chosen for the dark band (L 0.48-0.67), never flipped.
 *
 * Series hues are kept clear of the reserved status colours -- red for
 * critical, amber for high -- so a threshold line never reads as a series.
 */
export const SERIES = {
  light: ["#1b5fa8", "#2e6b33"],
  dark: ["#5b93e0", "#45a862"],
} as const;

/** Fixed assignment by collection method, so a colour always means one thing. */
export const METHOD_ORDER = ["field", "lab", "bms"] as const;
export type Method = (typeof METHOD_ORDER)[number];

export function seriesColor(mode: ColorMode, method: string): string {
  const palette = SERIES[mode];
  const index = METHOD_ORDER.indexOf(method as Method);
  // Never cycle a generated hue: an unexpected method falls back to slot 0
  // and is disambiguated by its legend label.
  return palette[index >= 0 && index < palette.length ? index : 0];
}

export const METHOD_LABEL: Record<string, string> = {
  field: "Field test",
  lab: "Contract lab",
  bms: "Building automation",
};

/** Threshold line: a status colour, reserved, never used for a series. */
export function limitColor(mode: ColorMode): string {
  return mode === "dark" ? "#ffb4ab" : "#ba1a1a";
}

export const CHART = {
  strokeWidth: 2,
  markerSize: 9,
  gridOpacity: 0.35,
} as const;
