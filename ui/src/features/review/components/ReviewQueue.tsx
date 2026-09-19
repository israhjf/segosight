import { useCallback, useState } from "react";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import EditNoteIcon from "@mui/icons-material/EditNote";
import TaskAltIcon from "@mui/icons-material/TaskAlt";

import { api, ApiError } from "@/shared/api/client";
import type { ReviewItem } from "@/shared/types";
import { ReviewCard } from "./ReviewCard";
import { useReviewer } from "@/features/review/ReviewerContext";

const PAGE = 4;

type Props = {
  items: ReviewItem[];
  loading: boolean;
  onChanged: (message: string) => void;
  /** False when a tab label already names the section, to avoid repeating it. */
  showHeading?: boolean;
};

export function ReviewQueue({ items, loading, onChanged, showHeading = true }: Props) {
  const { reviewer } = useReviewer();
  const [visible, setVisible] = useState(PAGE);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const decide = useCallback(
    async (item: ReviewItem, decision: "approved" | "rejected") => {
      setBusyId(item.insight_id);
      setError(null);
      try {
        const result = await api.decide(item.insight_id, decision, reviewer);
        onChanged(result.message);
      } catch (caught) {
        setError(
          caught instanceof ApiError
            ? caught.message
            : "Could not record the decision."
        );
      } finally {
        setBusyId(null);
      }
    },
    [reviewer, onChanged]
  );

  return (
    <Box component="section" aria-labelledby="review-heading">
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
            <EditNoteIcon color="primary" />
            <Typography id="review-heading" variant="h2">
              Pending insight review
            </Typography>
            <Chip size="small" label={items.length} color="primary" variant="outlined" />
          </Stack>
        ) : (
          <span />
        )}
        <Typography variant="caption" color="text.secondary">
          Sorted: unresolved and overdue first, then least certain
        </Typography>
      </Stack>

      {error && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      {loading && items.length === 0 && (
        <Stack alignItems="center" sx={{ py: 6 }}>
          <CircularProgress size={28} />
        </Stack>
      )}

      {!loading && items.length === 0 && (
        <Paper variant="outlined" sx={{ p: 4, textAlign: "center" }}>
          <TaskAltIcon sx={{ fontSize: 32, color: "text.secondary", mb: 1 }} />
          <Typography variant="body2" color="text.secondary">
            Nothing waiting. Every extracted insight has been reviewed.
          </Typography>
        </Paper>
      )}

      <Stack spacing={2}>
        {items.slice(0, visible).map((item) => (
          <ReviewCard
            key={item.insight_id}
            item={item}
            busy={busyId === item.insight_id}
            onDecide={decide}
          />
        ))}
      </Stack>

      {items.length > visible && (
        <Stack alignItems="center" sx={{ mt: 2 }}>
          <Button onClick={() => setVisible((n) => n + PAGE)} size="small">
            Show {Math.min(PAGE, items.length - visible)} more of {items.length}
          </Button>
        </Stack>
      )}
    </Box>
  );
}
