/**
 * Generates a typed token module from the Material Theme Builder CSS export.
 *
 * The .css files in src/design-system/tokens are the source of truth and are copied
 * verbatim from the design handoff. MUI needs real colour values rather than
 * `var(...)` strings so it can compute hover states, alpha overlays and
 * contrast text, so this script mirrors them into TypeScript.
 *
 * Re-run with `pnpm run tokens` whenever the palette is re-exported.
 */
import { readdirSync, readFileSync, writeFileSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const tokenDir = join(here, "..", "src", "design-system", "tokens");
const out = join(here, "..", "src", "design-system", "tokens.generated.ts");

const camel = (s) => s.replace(/-([a-z])/g, (_, c) => c.toUpperCase());

const schemes = {};
for (const file of readdirSync(tokenDir).filter((f) => f.endsWith(".css"))) {
  const css = readFileSync(join(tokenDir, file), "utf8");
  const selector = css.match(/^\.([a-z-]+)\s*\{/m)?.[1];
  if (!selector) continue;
  const tokens = {};
  for (const [, name, value] of css.matchAll(
    /--md-sys-color-([a-z-]+):\s*rgb\((\d+)\s+(\d+)\s+(\d+)\)/g
  )) {
    tokens[camel(name)] = null; // placeholder, filled below
  }
  for (const m of css.matchAll(
    /--md-sys-color-([a-z-]+):\s*rgb\((\d+)\s+(\d+)\s+(\d+)\)/g
  )) {
    const [, name, r, g, b] = m;
    tokens[camel(name)] = `#${[r, g, b]
      .map((n) => Number(n).toString(16).padStart(2, "0"))
      .join("")}`;
  }
  schemes[camel(selector)] = tokens;
}

const body = `// GENERATED FILE -- do not edit by hand.
// Source: src/design-system/tokens/*.css (Material Theme Builder export).
// Regenerate with: pnpm run tokens

export type MaterialScheme = {
${Object.keys(schemes.light)
  .map((k) => `  ${k}: string;`)
  .join("\n")}
};

export type SchemeName =
  | "light"
  | "lightMediumContrast"
  | "lightHighContrast"
  | "dark"
  | "darkMediumContrast"
  | "darkHighContrast";

export const schemes: Record<SchemeName, MaterialScheme> = ${JSON.stringify(
  schemes,
  null,
  2
)} as const;
`;

writeFileSync(out, body);
console.log(
  `wrote ${out} (${Object.keys(schemes).length} schemes, ${
    Object.keys(schemes.light).length
  } tokens each)`
);
