import { createContext, useContext, useMemo, useState, type ReactNode } from "react";

import type { Alert } from "@/shared/types";

/**
 * What an export would currently cover.
 *
 * The severity filter is local state inside the queue, but the Export button
 * lives in the app bar, two components away. Rather than thread the filter
 * through AppShell, the queue publishes its scope here and the menu reads it.
 * Exporting "the current view" is only honest if the exporter knows what the
 * view actually is.
 */
export type ExportScope = {
  /** The severity filter in force, or "all". */
  severity: string;
  /** The alerts on screen, in the order shown. */
  alerts: Alert[];
};

type ScopeContext = ExportScope & { setScope: (scope: ExportScope) => void };

const Context = createContext<ScopeContext>({
  severity: "all",
  alerts: [],
  setScope: () => {},
});

export function ExportScopeProvider({ children }: { children: ReactNode }) {
  const [scope, setScope] = useState<ExportScope>({ severity: "all", alerts: [] });
  const value = useMemo(() => ({ ...scope, setScope }), [scope]);
  return <Context.Provider value={value}>{children}</Context.Provider>;
}

export const useExportScope = () => useContext(Context);
