import { useState } from "react";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Divider from "@mui/material/Divider";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import CheckIcon from "@mui/icons-material/Check";
import CloseIcon from "@mui/icons-material/Close";
import DescriptionOutlinedIcon from "@mui/icons-material/DescriptionOutlined";
import ScheduleIcon from "@mui/icons-material/Schedule";

import { ConfidenceMeter } from "./ConfidenceMeter";
import { ProvenanceChip } from "./ProvenanceChip";
import { QuoteBlock } from "@/design-system/components/QuoteBlock";
import { currency, dueLabel, fileName, humanize, isoDate } from "@/shared/format";
import type { ReviewItem } from "@/shared/types";

type Props = {
  item: ReviewItem;
  busy: boolean;
  onDecide: (item: ReviewItem, decision: "approved" | "rejected") => void;
};

export function ReviewCard({ item, busy, onDecide }: Props) {
  const [hovered, setHovered] = useState(false);
  const overdue = (item.days_overdue ?? 0) > 0;

  return (
    <Card
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      sx={{
        borderColor: overdue ? "severity.high.main" : "divider",
        transition: "border-color 120ms, box-shadow 120ms",
        boxShadow: hovered ? 2 : 0,
      }}
    >
      <CardContent sx={{ pb: 1.5 }}>
        <Stack
          direction={{ xs: "column", sm: "row" }}
          justifyContent="space-between"
          alignItems={{ sm: "center" }}
          spacing={1}
          sx={{ mb: 1.5 }}
        >
          <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
            <Typography variant="overline" color="text.secondary">
              Type
            </Typography>
            <Typography variant="subtitle2">{humanize(item.insight_type)}</Typography>
          </Stack>

          <Stack direction="row" spacing={1} alignItems="center">
            <ScheduleIcon
              fontSize="small"
              sx={{ color: overdue ? "severity.high.main" : "text.secondary" }}
            />
            <Typography
              variant="body2"
              sx={{
                fontWeight: overdue ? 700 : 500,
                color: overdue ? "severity.high.main" : "text.secondary",
              }}
            >
              {item.due_on ? "Due " : "Raised "}
              {dueLabel(item.due_on, item.days_overdue)}
              {item.due_on && ` (${isoDate(item.due_on)})`}
            </Typography>
          </Stack>
        </Stack>

        <Divider sx={{ mb: 1.5 }} />

        <QuoteBlock
          quote={item.quote}
          attribution={
            item.due_phrase ? `Deadline read from “${item.due_phrase}”` : undefined
          }
        />

        <Divider sx={{ my: 1.5 }} />

        <Stack
          direction={{ xs: "column", md: "row" }}
          spacing={2}
          alignItems={{ md: "center" }}
          justifyContent="space-between"
        >
          <Stack spacing={0.5} sx={{ minWidth: 0 }}>
            <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
              <Typography variant="body2" sx={{ fontWeight: 600 }}>
                {item.customer_name ?? item.facility_id ?? "Unlinked"}
              </Typography>
              {item.acv_usd != null && (
                <Typography variant="body2" color="text.secondary">
                  {currency(item.acv_usd)}/yr
                </Typography>
              )}
              {item.system_id && (
                <Typography variant="body2" color="text.secondary">
                  · {item.system_id}
                </Typography>
              )}
            </Stack>
            <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
              <Typography variant="caption" color="text.secondary">
                {item.author ?? "unattributed"}
              </Typography>
              <Tooltip title={item.source_file}>
                <Stack direction="row" spacing={0.5} alignItems="center">
                  <DescriptionOutlinedIcon sx={{ fontSize: 14, color: "text.secondary" }} />
                  <Typography variant="caption" color="text.secondary">
                    {fileName(item.source_file)}
                  </Typography>
                </Stack>
              </Tooltip>
            </Stack>
          </Stack>

          <Stack direction="row" spacing={2} alignItems="center">
            <ProvenanceChip provenance={item.provenance} extractor={item.extractor} />
            <ConfidenceMeter value={item.confidence_score} />
          </Stack>
        </Stack>

        {item.fulfillment_basis && (
          <Typography
            variant="caption"
            color="text.secondary"
            sx={{ display: "block", mt: 1.25, fontStyle: "italic" }}
          >
            {item.fulfillment_basis}
          </Typography>
        )}

        <Stack direction="row" spacing={1} justifyContent="flex-end" sx={{ mt: 2 }}>
          <Button
            size="small"
            color="inherit"
            startIcon={<CloseIcon />}
            disabled={busy}
            onClick={() => onDecide(item, "rejected")}
          >
            {item.reject_verb}
          </Button>
          <Button
            size="small"
            variant="contained"
            startIcon={<CheckIcon />}
            disabled={busy}
            onClick={() => onDecide(item, "approved")}
          >
            Approve ({item.approve_verb})
          </Button>
        </Stack>
      </CardContent>
    </Card>
  );
}
