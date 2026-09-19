import Box from "@mui/material/Box";
import Divider from "@mui/material/Divider";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

import { AlertQueue } from "@/features/alerts/AlertQueue";
import { ReviewQueue } from "@/features/review/ReviewQueue";
import type { Alert, Overview, ReviewItem } from "@/shared/types";

function StatTile({
  label,
  value,
  tone,
}: {
  label: string;
  value: number | string;
  tone?: "critical" | "high" | "default";
}) {
  return (
    <Paper variant="outlined" sx={{ p: 2, flex: 1, minWidth: 148 }}>
      <Typography
        variant="h1"
        sx={{
          fontSize: "2rem",
          lineHeight: 1.1,
          color:
            tone === "critical"
              ? "severity.critical.main"
              : tone === "high"
                ? "severity.high.main"
                : "text.primary",
        }}
      >
        {value}
      </Typography>
      <Typography variant="caption" color="text.secondary">
        {label}
      </Typography>
    </Paper>
  );
}

type Props = {
  overview: Overview | null;
  reviewItems: ReviewItem[];
  alerts: Alert[];
  loading: boolean;
  onChanged: (message: string) => void;
};

export function OverviewPage({ overview, reviewItems, alerts, loading, onChanged }: Props) {
  return (
    <Stack spacing={4}>
      {overview && (
        <Stack direction="row" spacing={2} flexWrap="wrap" useFlexGap>
          <StatTile label="Critical alerts" value={overview.critical_alerts} tone="critical" />
          <StatTile label="Active alerts" value={overview.active_alerts} />
          <StatTile label="Awaiting review" value={overview.pending_review} tone="high" />
          <StatTile
            label="Alerts on unreviewed prose"
            value={overview.alerts_awaiting_prose_review}
            tone={overview.alerts_awaiting_prose_review > 0 ? "high" : "default"}
          />
          <StatTile label="Open commitments" value={overview.open_commitments} />
        </Stack>
      )}

      <ReviewQueue items={reviewItems} loading={loading} onChanged={onChanged} />

      <Box>
        <Divider sx={{ mb: 3 }} />
        <AlertQueue alerts={alerts} loading={loading} />
      </Box>
    </Stack>
  );
}
