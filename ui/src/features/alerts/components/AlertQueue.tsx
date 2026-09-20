import { useEffect, useMemo, useState } from "react";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Stack from "@mui/material/Stack";
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import Typography from "@mui/material/Typography";
import CrisisAlertIcon from "@mui/icons-material/CrisisAlert";

import { SEVERITY_ORDER } from "@/design-system";
import { useExportScope } from "@/features/export";
import type { Alert } from "@/shared/types";
import { AlertCard } from "./AlertCard";

type Props = {
  alerts: Alert[];
  loading: boolean;
  /** False when a tab label already names the section, to avoid repeating it. */
  showHeading?: boolean;
};

export function AlertQueue({ alerts, loading, showHeading = true }: Props) {
  const [severity, setSeverity] = useState<string>("all");

  const filtered = useMemo(
    () => (severity === "all" ? alerts : alerts.filter((a) => a.severity === severity)),
    [alerts, severity]
  );

  // The Export button sits in the app bar and cannot see this filter, so
  // publish it. "Export the current view" is only truthful if the exporter
  // knows what the current view is.
  const { setScope } = useExportScope();
  useEffect(() => {
    setScope({ severity, alerts: filtered });
  }, [severity, filtered, setScope]);

  const counts = useMemo(() => {
    const tally: Record<string, number> = {};
    for (const alert of alerts) tally[alert.severity] = (tally[alert.severity] ?? 0) + 1;
    return tally;
  }, [alerts]);

  return (
    <Box component="section" aria-labelledby="alerts-heading">
      <Stack
        direction="row"
        alignItems="center"
        justifyContent="space-between"
        sx={{ mb: 2 }}
        flexWrap="wrap"
        gap={1}
      >
        {showHeading ? (
          <Stack direction="row" spacing={1.5} alignItems="center">
            <CrisisAlertIcon color="error" />
            <Typography id="alerts-heading" variant="h2">
              Governed alerts
            </Typography>
            <Chip size="small" label={`${alerts.length} active`} variant="outlined" />
          </Stack>
        ) : (
          <Typography variant="caption" color="text.secondary">
            Ranked by severity, weighted by account tier and equipment criticality
          </Typography>
        )}

        {/* Filters sit in one row above the list, never inside the cards. */}
        <ToggleButtonGroup
          size="small"
          exclusive
          value={severity}
          onChange={(_, value) => value && setSeverity(value)}
          aria-label="Filter by severity"
        >
          <ToggleButton value="all">All</ToggleButton>
          {SEVERITY_ORDER.filter((level) => counts[level]).map((level) => (
            <ToggleButton key={level} value={level}>
              {level} ({counts[level]})
            </ToggleButton>
          ))}
        </ToggleButtonGroup>
      </Stack>

      {loading && alerts.length === 0 && (
        <Stack alignItems="center" sx={{ py: 6 }}>
          <CircularProgress size={28} />
        </Stack>
      )}

      <Stack spacing={2}>
        {filtered.map((alert) => (
          <AlertCard key={alert.alert_id} alert={alert} />
        ))}
      </Stack>
    </Box>
  );
}
