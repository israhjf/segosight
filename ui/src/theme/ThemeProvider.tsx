import CssBaseline from "@mui/material/CssBaseline";
import { ThemeProvider as MuiThemeProvider } from "@mui/material/styles";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { buildTheme, schemeName, type ColorMode, type Contrast } from "./palette";
import "./tokens/light.css";
import "./tokens/light-mc.css";
import "./tokens/light-hc.css";
import "./tokens/dark.css";
import "./tokens/dark-mc.css";
import "./tokens/dark-hc.css";

type ThemeControls = {
  mode: ColorMode;
  contrast: Contrast;
  followSystem: boolean;
  toggleMode: () => void;
  setContrast: (contrast: Contrast) => void;
  useSystem: () => void;
};

const ThemeControlsContext = createContext<ThemeControls | null>(null);

const MODE_KEY = "segosight.color-mode";
const CONTRAST_KEY = "segosight.contrast";

function prefersDark() {
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ?? false;
}

function prefersMoreContrast() {
  return window.matchMedia?.("(prefers-contrast: more)").matches ?? false;
}

function read<T extends string>(key: string, allowed: readonly T[]): T | null {
  try {
    const value = localStorage.getItem(key) as T | null;
    return value && allowed.includes(value) ? value : null;
  } catch {
    // Private browsing and blocked storage both land here; the UI must still
    // render, it just will not remember the choice.
    return null;
  }
}

function persist(key: string, value: string) {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* preference is a convenience, never a requirement */
  }
}

/**
 * Colour mode and contrast.
 *
 * Mode follows the operating system until the user overrides it, which is the
 * behaviour people expect and the reason the toggle does not default to light.
 * Contrast is an accessibility preference the OS already knows, so
 * `prefers-contrast: more` selects the high-contrast scheme automatically; the
 * settings menu exists for the case where someone wants it without changing a
 * system setting.
 */
export function ThemeProvider({ children }: { children: ReactNode }) {
  const stored = read(MODE_KEY, ["light", "dark"] as const);
  const [followSystem, setFollowSystem] = useState(stored === null);
  const [mode, setMode] = useState<ColorMode>(stored ?? (prefersDark() ? "dark" : "light"));
  const [contrast, setContrastState] = useState<Contrast>(
    read(CONTRAST_KEY, ["normal", "medium", "high"] as const) ??
      (prefersMoreContrast() ? "high" : "normal")
  );

  useEffect(() => {
    if (!followSystem) return;
    const query = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = (event: MediaQueryListEvent) =>
      setMode(event.matches ? "dark" : "light");
    query.addEventListener("change", onChange);
    return () => query.removeEventListener("change", onChange);
  }, [followSystem]);

  // Keep the document class in sync so raw CSS can read the same tokens MUI does.
  useEffect(() => {
    const name = schemeName(mode, contrast)
      .replace(/([A-Z])/g, "-$1")
      .toLowerCase();
    document.documentElement.className = name;
    document.documentElement.style.colorScheme = mode;
  }, [mode, contrast]);

  const toggleMode = useCallback(() => {
    setMode((current) => {
      const next = current === "dark" ? "light" : "dark";
      persist(MODE_KEY, next);
      return next;
    });
    setFollowSystem(false);
  }, []);

  const setContrast = useCallback((next: Contrast) => {
    setContrastState(next);
    persist(CONTRAST_KEY, next);
  }, []);

  const useSystem = useCallback(() => {
    try {
      localStorage.removeItem(MODE_KEY);
    } catch {
      /* ignore */
    }
    setFollowSystem(true);
    setMode(prefersDark() ? "dark" : "light");
  }, []);

  const theme = useMemo(() => buildTheme(mode, contrast), [mode, contrast]);
  const controls = useMemo(
    () => ({ mode, contrast, followSystem, toggleMode, setContrast, useSystem }),
    [mode, contrast, followSystem, toggleMode, setContrast, useSystem]
  );

  return (
    <ThemeControlsContext.Provider value={controls}>
      <MuiThemeProvider theme={theme}>
        <CssBaseline />
        {children}
      </MuiThemeProvider>
    </ThemeControlsContext.Provider>
  );
}

export function useThemeControls(): ThemeControls {
  const value = useContext(ThemeControlsContext);
  if (!value) throw new Error("useThemeControls must be used inside ThemeProvider");
  return value;
}
