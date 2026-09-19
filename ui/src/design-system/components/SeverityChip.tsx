import Chip from "@mui/material/Chip";
import { useTheme } from "@mui/material/styles";

import type { Severity } from "@/shared/types";

/**
 * Severity never travels as colour alone: the chip always carries its label,
 * so the state survives greyscale printing and colour-blind readers.
 */
export function SeverityChip({ severity, size = "small" }: { severity: Severity; size?: "small" | "medium" }) {
  const theme = useTheme();
  const colors = theme.palette.severity[severity] ?? theme.palette.severity.low;
  return (
    <Chip
      size={size}
      label={severity.toUpperCase()}
      sx={{
        bgcolor: colors.container,
        color: colors.onContainer,
        fontWeight: 700,
        letterSpacing: "0.06em",
        fontSize: size === "small" ? "0.6875rem" : "0.75rem",
        borderRadius: 1,
      }}
    />
  );
}
