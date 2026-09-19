import Box from "@mui/material/Box";
import LinearProgress from "@mui/material/LinearProgress";
import Typography from "@mui/material/Typography";
import { useTheme } from "@mui/material/styles";

/**
 * Extraction confidence.
 *
 * Deliberately not called a probability. It reflects how literal the evidence
 * was -- an explicit date scores above "by Monday", which scores above "a
 * couple of weeks" -- so it ranks a queue rather than predicting correctness.
 */
export function ConfidenceMeter({ value }: { value: number }) {
  const theme = useTheme();
  const pct = Math.round(value * 100);
  const tone =
    value >= 0.75
      ? theme.palette.primary.main
      : value >= 0.55
        ? theme.palette.severity.high.main
        : theme.palette.severity.medium.main;

  return (
    <Box sx={{ minWidth: 132 }}>
      <Box sx={{ display: "flex", justifyContent: "space-between", mb: 0.25 }}>
        <Typography variant="caption" color="text.secondary">
          Confidence
        </Typography>
        <Typography variant="caption" sx={{ fontWeight: 700 }}>
          {pct}%
        </Typography>
      </Box>
      <LinearProgress
        variant="determinate"
        value={pct}
        aria-label={`Extraction confidence ${pct} percent`}
        sx={{
          height: 6,
          borderRadius: 3,
          bgcolor: theme.palette.action.hover,
          "& .MuiLinearProgress-bar": { bgcolor: tone, borderRadius: 3 },
        }}
      />
    </Box>
  );
}
