import Chip from "@mui/material/Chip";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import SubdirectoryArrowRightIcon from "@mui/icons-material/SubdirectoryArrowRight";

import { fileName } from "@/shared/format";
import type { Evidence } from "@/shared/types";

const STATUS_LABEL: Record<string, string> = {
  pending_review: "PENDING",
  approved: "APPROVED",
  rejected: "REJECTED",
};

/**
 * One quote supporting an alert, with its review state.
 *
 * The state is on every line because an alert can cite several documents at
 * different stages, and a reviewer needs to know which parts of the case have
 * been accepted and which are still someone's unverified reading of a note.
 */
export function EvidenceLine({ evidence }: { evidence: Evidence }) {
  const status = evidence.review_status;
  const approved = status === "approved";
  const rejected = status === "rejected";

  return (
    <Stack
      direction="row"
      spacing={1}
      alignItems="flex-start"
      sx={{ opacity: rejected ? 0.55 : 1 }}
    >
      <SubdirectoryArrowRightIcon sx={{ fontSize: 16, color: "text.disabled", mt: 0.25 }} />
      <Typography
        variant="body2"
        className="quote"
        sx={{
          flex: 1,
          minWidth: 0,
          color: "text.secondary",
          textDecoration: rejected ? "line-through" : "none",
        }}
      >
        &ldquo;{evidence.quote}&rdquo;
        {evidence.source_file && (
          <Tooltip title={evidence.source_file}>
            <Typography component="span" variant="caption" sx={{ ml: 1 }}>
              ({fileName(evidence.source_file)})
            </Typography>
          </Tooltip>
        )}
      </Typography>
      <Chip
        size="small"
        variant={approved ? "filled" : "outlined"}
        color={approved ? "primary" : "default"}
        label={STATUS_LABEL[status] ?? status.toUpperCase()}
        sx={{ fontSize: "0.625rem", height: 20, fontWeight: 700 }}
      />
    </Stack>
  );
}
