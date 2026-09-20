import { useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Collapse from "@mui/material/Collapse";
import Divider from "@mui/material/Divider";
import IconButton from "@mui/material/IconButton";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import { useTheme } from "@mui/material/styles";
import ArrowForwardIcon from "@mui/icons-material/ArrowForward";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import { Link as RouterLink, useNavigate } from "react-router-dom";

import { SeverityChip } from "@/design-system/components/SeverityChip";
import { currency, humanize } from "@/shared/format";
import type { Alert as AlertType } from "@/shared/types";
import { EvidenceLine } from "./EvidenceLine";

/**
 * Lets the card's `:hover` reach the header title. A CSS descendant selector
 * beats lifting hover into React state: no re-render per pointer move, and the
 * colour change survives the pointer entering a child element.
 */
const TITLE_CLASS = "SegoSightAlertCard-title";

export function AlertCard({ alert }: { alert: AlertType }) {
  const theme = useTheme();
  const colors = theme.palette.severity[alert.severity] ?? theme.palette.severity.low;
  const unreviewed = alert.evidence_basis === "prose_pending_review";

  // Critical alerts open on load; everything else collapses so a long queue
  // stays scannable. Triage starts by comparing headers, not by reading every
  // evidence string.
  const [expanded, setExpanded] = useState(alert.severity === "critical");
  const navigate = useNavigate();
  const detailPath = `/alerts/${encodeURIComponent(alert.alert_id)}`;

  // The card is a click target, but the title stays a real anchor underneath
  // it: this handler is a convenience for pointer users, not the accessible
  // path to the page.
  const openDetail = () => {
    // Dragging across an evidence quote ends in a click. Navigating then would
    // throw away a selection the reviewer made on purpose -- those quotes are
    // verbatim source text people copy into tickets and customer email.
    if (window.getSelection()?.toString()) return;
    navigate(detailPath);
  };
  // alert_id carries colons ("corrosion_trend:SYS-0006:iron"), which are legal
  // in an id but awkward in a selector.
  const panelId = `alert-evidence-${alert.alert_id.replace(/[^a-zA-Z0-9]+/g, "-")}`;

  return (
    <Card
      onClick={openDetail}
      sx={{
        cursor: "pointer",
        // A severity rail reads faster than a coloured card and keeps the
        // surface neutral enough for long text to stay legible.
        borderLeft: 4,
        borderLeftColor: colors.main,
        // Hover steps the card up the Material 3 container ramp rather than
        // washing `action.hover` over it: MuiCard pins its own
        // `surfaceContainerLow` background, so a translucent overlay would let
        // the page surface through and shift the card's hue instead of just
        // deepening it.
        transition: theme.transitions.create(["background-color", "border-color"], {
          duration: theme.transitions.duration.shortest,
        }),
        "&:hover": {
          backgroundColor: theme.palette.material.surfaceContainerHigh,
          // In dark mode the container ramp is compressed almost flat
          // (surfaceContainerLow -> surfaceContainer is a 0.003 luminance
          // step), so the fill alone would not register. Firming the outline
          // carries the hover in every scheme. Named sides only -- the
          // shorthand would repaint the severity rail on the left.
          borderTopColor: theme.palette.material.outline,
          borderRightColor: theme.palette.material.outline,
          borderBottomColor: theme.palette.material.outline,
          [`& .${TITLE_CLASS}`]: { color: "primary.main" },
        },
      }}
    >
      <CardContent sx={{ pb: expanded ? 1.5 : 2 }}>
        <Stack
          direction={{ xs: "column", sm: "row" }}
          justifyContent="space-between"
          alignItems={{ sm: "center" }}
          spacing={1}
        >
          <Stack direction="row" spacing={1.25} alignItems="center" flexWrap="wrap">
            <SeverityChip severity={alert.severity} />
            <Typography
              variant="h3"
              className={TITLE_CLASS}
              sx={{
                fontSize: "1rem",
                transition: theme.transitions.create("color", {
                  duration: theme.transitions.duration.shortest,
                }),
              }}
            >
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
            <Tooltip title={expanded ? "Hide evidence" : "Show evidence"}>
              <IconButton
                size="small"
                onClick={(event) => {
                  event.stopPropagation();
                  setExpanded((open) => !open);
                }}
                aria-expanded={expanded}
                aria-controls={panelId}
                aria-label={`${expanded ? "Collapse" : "Expand"} ${alert.title}`}
                sx={{
                  transform: expanded ? "rotate(180deg)" : "none",
                  transition: theme.transitions.create("transform", {
                    duration: theme.transitions.duration.shortest,
                  }),
                }}
              >
                <ExpandMoreIcon />
              </IconButton>
            </Tooltip>
          </Stack>
        </Stack>

        {/*
          The title sits above the fold and carries the navigation: a collapsed
          card must still offer a way into the detail view, and this is a far
          larger target than the footer button.

          It reads as body text, not a hyperlink -- a queue of 41 blue
          underlined headings is noise. The affordance is the hover fill
          instead. Negative inline margin lets that fill reach the card's
          content edge so it looks like a row, not a boxed word.
        */}
        <Box
          component={RouterLink}
          to={detailPath}
          onClick={(event) => event.stopPropagation()}
          sx={{
            display: "block",
            mt: 0.75,
            mx: -1,
            px: 1,
            py: 0.5,
            borderRadius: 1,
            color: "text.primary",
            textDecoration: "none",
            cursor: "pointer",
            transition: theme.transitions.create("background-color", {
              duration: theme.transitions.duration.shortest,
            }),
            // No hover fill of its own any more: the whole card lights up and
            // navigates, so a second highlight here would just read as a
            // seam across the card. Focus styling stays -- keyboard users
            // reach this anchor, not the card.
            "&:focus-visible": {
              outline: `2px solid ${theme.palette.primary.main}`,
              outlineOffset: -2,
              backgroundColor: theme.palette.material.surfaceContainerHigh,
            },
          }}
        >
          <Typography variant="subtitle2" component="span" sx={{ display: "block" }}>
            {alert.title}
          </Typography>
        </Box>

        <Typography variant="caption" color="text.secondary" sx={{ mt: 0.25, display: "block" }}>
          {humanize(alert.risk_class)}
          {!expanded && alert.evidence.length > 0
            ? ` · ${alert.evidence.length} piece${alert.evidence.length === 1 ? "" : "s"} of evidence`
            : ""}
        </Typography>

        {/*
          Stays outside the collapse on purpose. "This alert rests on an
          extraction nobody has confirmed" is exactly the fact a reviewer must
          not be able to miss by leaving a card shut.
        */}
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

        <Collapse in={expanded} timeout="auto" unmountOnExit>
          <Box id={panelId}>
            <Divider sx={{ my: 1.5 }} />

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

            <Stack
              direction="row"
              justifyContent="space-between"
              alignItems="center"
              sx={{ mt: 2 }}
            >
              <Box sx={{ minWidth: 0 }}>
                {alert.owner && (
                  <Typography variant="caption" color="text.secondary">
                    Owner hint: {alert.owner}
                  </Typography>
                )}
              </Box>
              <Button
                component={RouterLink}
                to={detailPath}
                onClick={(event) => event.stopPropagation()}
                size="small"
                endIcon={<ArrowForwardIcon />}
              >
                View details
              </Button>
            </Stack>
          </Box>
        </Collapse>
      </CardContent>
    </Card>
  );
}
