import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Divider from "@mui/material/Divider";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import { useTheme } from "@mui/material/styles";
import ArrowForwardIcon from "@mui/icons-material/ArrowForward";
import { Link as RouterLink } from "react-router-dom";

import { SeverityChip } from "@/design-system/components/SeverityChip";
import { currency, humanize } from "@/shared/format";
import type { Alert as AlertType } from "@/shared/types";
import { EvidenceLine } from "./EvidenceLine";

export function AlertCard({ alert }: { alert: AlertType }) {
  const theme = useTheme();
  const colors = theme.palette.severity[alert.severity] ?? theme.palette.severity.low;
  const unreviewed = alert.evidence_basis === "prose_pending_review";

  return (
    <Card
      sx={{
        // A severity rail reads faster than a coloured card and keeps the
        // surface neutral enough for long text to stay legible.
        borderLeft: 4,
        borderLeftColor: colors.main,
      }}
    >
      <CardContent sx={{ pb: 1.5 }}>
        <Stack
          direction={{ xs: "column", sm: "row" }}
          justifyContent="space-between"
          alignItems={{ sm: "center" }}
          spacing={1}
        >
          <Stack direction="row" spacing={1.25} alignItems="center" flexWrap="wrap">
            <SeverityChip severity={alert.severity} />
            <Typography variant="h3" sx={{ fontSize: "1rem" }}>
              {alert.customer_name ?? alert.facility_id}
              {alert.system_id ? ` · ${alert.system_id}` : ""}
            </Typography>
          </Stack>
          <Stack direction="row" spacing={2} alignItems="center">
            {alert.acv_usd != null && (
              <Typography variant="body2" color="text.secondary">
                {currency(alert.acv_usd)}/yr
              </Typography>
            )}
            <Typography variant="body2" sx={{ fontWeight: 700 }}>
              Score {alert.priority_score.toFixed(2)}
            </Typography>
          </Stack>
        </Stack>

        <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, display: "block" }}>
          {humanize(alert.risk_class)}
        </Typography>

        {unreviewed && (
          <Alert
            severity="warning"
            variant="outlined"
            sx={{ mt: 1.5, py: 0, "& .MuiAlert-message": { py: 0.75 } }}
          >
            <Typography variant="caption" sx={{ fontWeight: 600 }}>
              Prose unreviewed — this alert rests on an extraction nobody has
              confirmed yet.
            </Typography>
          </Alert>
        )}

        <Divider sx={{ my: 1.5 }} />

        <Typography variant="subtitle2" sx={{ mb: 0.5 }}>
          {alert.title}
        </Typography>
        <Typography variant="body2" color="text.secondary">
          {alert.why}
        </Typography>

        {alert.evidence.length > 0 && (
          <Stack spacing={0.75} sx={{ mt: 1.5 }}>
            {alert.evidence.map((evidence) => (
              <EvidenceLine key={evidence.evidence_id} evidence={evidence} />
            ))}
          </Stack>
        )}

        <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mt: 2 }}>
          <Box sx={{ minWidth: 0 }}>
            {alert.owner && (
              <Typography variant="caption" color="text.secondary">
                Owner hint: {alert.owner}
              </Typography>
            )}
          </Box>
          <Button
            component={RouterLink}
            to={`/alerts/${encodeURIComponent(alert.alert_id)}`}
            size="small"
            endIcon={<ArrowForwardIcon />}
          >
            View details
          </Button>
        </Stack>
      </CardContent>
    </Card>
  );
}
