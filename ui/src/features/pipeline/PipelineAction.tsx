import { useState } from "react";
import Button from "@mui/material/Button";
import Dialog from "@mui/material/Dialog";
import DialogActions from "@mui/material/DialogActions";
import DialogContent from "@mui/material/DialogContent";
import DialogTitle from "@mui/material/DialogTitle";
import Stack from "@mui/material/Stack";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Typography from "@mui/material/Typography";
import CircularProgress from "@mui/material/CircularProgress";
import SyncIcon from "@mui/icons-material/Sync";

import { api } from "@/shared/api";
import { humanize } from "@/shared/format";
import type { PipelineResult } from "@/shared/types";

/**
 * Runs the ingestion pipeline from inside the product.
 *
 * DuckDB allows one writer, and the API holds it, so the rebuild belongs here
 * rather than in a terminal. That turns "incorporate the next data batch" into
 * something the operations director can do herself, and the before/after
 * counts show exactly what the new batch changed.
 *
 * Safe to press twice: the raw tier is content-addressed, so re-running over
 * unchanged files inserts nothing, and reviewer decisions are re-applied after
 * the rebuild rather than reset.
 */
export function PipelineAction({ onComplete }: { onComplete: () => void }) {
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<PipelineResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const run = async () => {
    setRunning(true);
    setError(null);
    try {
      const outcome = await api.runPipeline();
      setResult(outcome);
      onComplete();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Pipeline failed.");
    } finally {
      setRunning(false);
    }
  };

  const rows = result
    ? Object.keys(result.after).map((key) => ({
        key,
        before: result.before[key],
        after: result.after[key],
        delta: result.delta[key],
      }))
    : [];

  return (
    <>
      <Button
        size="small"
        variant="outlined"
        startIcon={running ? <CircularProgress size={14} /> : <SyncIcon />}
        onClick={run}
        disabled={running}
      >
        {running ? "Ingesting…" : "Ingest data"}
      </Button>

      <Dialog
        open={Boolean(result || error)}
        onClose={() => {
          setResult(null);
          setError(null);
        }}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>{error ? "Ingestion failed" : "Ingestion complete"}</DialogTitle>
        <DialogContent>
          {error && <Typography color="error">{error}</Typography>}
          {result && (
            <Stack spacing={2}>
              <Typography variant="body2" color="text.secondary">
                Rebuilt every tier from source in {result.duration_seconds}s.
                Reviewer decisions were preserved.
              </Typography>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Measure</TableCell>
                    <TableCell align="right">Before</TableCell>
                    <TableCell align="right">After</TableCell>
                    <TableCell align="right">Change</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {rows.map((row) => (
                    <TableRow key={row.key}>
                      <TableCell>{humanize(row.key)}</TableCell>
                      <TableCell align="right">{row.before}</TableCell>
                      <TableCell align="right">{row.after}</TableCell>
                      <TableCell
                        align="right"
                        sx={{
                          fontWeight: row.delta !== 0 ? 700 : 400,
                          color: row.delta !== 0 ? "primary.main" : "text.secondary",
                        }}
                      >
                        {row.delta > 0 ? `+${row.delta}` : row.delta}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </Stack>
          )}
        </DialogContent>
        <DialogActions>
          <Button
            onClick={() => {
              setResult(null);
              setError(null);
            }}
          >
            Close
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
}
