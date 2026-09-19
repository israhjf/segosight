import { useState, type ReactNode, type SyntheticEvent } from "react";
import Box from "@mui/material/Box";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Tab from "@mui/material/Tab";
import Tabs from "@mui/material/Tabs";
import Typography from "@mui/material/Typography";
import { alpha } from "@mui/material/styles";
import CrisisAlertIcon from "@mui/icons-material/CrisisAlert";
import EditNoteIcon from "@mui/icons-material/EditNote";

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

const REVIEW_TAB = "review";
const ALERTS_TAB = "alerts";
type TabId = typeof REVIEW_TAB | typeof ALERTS_TAB;

function TabPanel({
  id,
  active,
  children,
}: {
  id: TabId;
  active: TabId;
  children: ReactNode;
}) {
  const selected = id === active;
  return (
    <Box
      role="tabpanel"
      id={`panel-${id}`}
      aria-labelledby={`tab-${id}`}
      // Both panels stay mounted and the inactive one is hidden, so switching
      // tabs preserves scroll position, the severity filter and how many cards
      // have been paged in. Unmounting would reset all three, which is the
      // "losing context" the tabs are meant to prevent.
      hidden={!selected}
      sx={{ pt: 3 }}
    >
      {children}
    </Box>
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
  // Review first by default: an unreviewed extraction can still change the
  // governed state, so clearing the queue is the prerequisite for trusting
  // what the alerts say.
  const [active, setActive] = useState<TabId>(REVIEW_TAB);
  const change = (_: SyntheticEvent, value: TabId) => setActive(value);

  return (
    <Stack spacing={3}>
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

      <Box>
        <Box
          sx={{
            borderBottom: 1,
            borderColor: "divider",
            // The tab bar sticks under the app bar so switching queues stays
            // one click away deep inside a long list -- the scroll fatigue
            // these tabs exist to solve.
            position: "sticky",
            top: 64,
            zIndex: (theme) => theme.zIndex.appBar - 1,
            bgcolor: "background.default",
          }}
        >
          <Tabs
            value={active}
            onChange={change}
            aria-label="Dashboard queues"
            textColor="primary"
            indicatorColor="primary"
            sx={{
              minHeight: 48,
              "& .MuiTab-root": {
                textTransform: "none",
                fontWeight: 500,
                fontSize: "0.9375rem",
                minHeight: 48,
                color: "text.secondary",
              },
              "& .MuiTab-root.Mui-selected": {
                color: "primary.main",
                fontWeight: 600,
                // A tint of the brand blue rather than a fixed grey, so the
                // selected tab keeps a recognisable footprint in both colour
                // modes. alpha() re-derives it from whichever primary is in
                // force, which a hard-coded light blue would not.
                bgcolor: (theme) => alpha(theme.palette.primary.main, 0.1),
                borderRadius: "8px 8px 0 0",
              },
              "& .MuiTab-root:hover:not(.Mui-selected)": {
                bgcolor: (theme) => alpha(theme.palette.primary.main, 0.04),
                borderRadius: "8px 8px 0 0",
              },
              "& .MuiTabs-indicator": { height: 3, borderRadius: "3px 3px 0 0" },
            }}
          >
            <Tab
              value={REVIEW_TAB}
              id={`tab-${REVIEW_TAB}`}
              aria-controls={`panel-${REVIEW_TAB}`}
              iconPosition="start"
              icon={<EditNoteIcon fontSize="small" />}
              label={`Pending insight review (${reviewItems.length})`}
            />
            <Tab
              value={ALERTS_TAB}
              id={`tab-${ALERTS_TAB}`}
              aria-controls={`panel-${ALERTS_TAB}`}
              iconPosition="start"
              icon={<CrisisAlertIcon fontSize="small" />}
              label={`Governed alerts (${alerts.length} active)`}
            />
          </Tabs>
        </Box>

        <TabPanel id={REVIEW_TAB} active={active}>
          <ReviewQueue
            items={reviewItems}
            loading={loading}
            onChanged={onChanged}
            showHeading={false}
          />
        </TabPanel>

        <TabPanel id={ALERTS_TAB} active={active}>
          <AlertQueue alerts={alerts} loading={loading} showHeading={false} />
        </TabPanel>
      </Box>
    </Stack>
  );
}
