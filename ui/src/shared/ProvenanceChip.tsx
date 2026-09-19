import Chip from "@mui/material/Chip";
import Tooltip from "@mui/material/Tooltip";
import PsychologyIcon from "@mui/icons-material/Psychology";
import RuleIcon from "@mui/icons-material/Rule";

/**
 * States what produced an extraction.
 *
 * The distinction is not cosmetic. Most of these rows come from deterministic
 * patterns over the source text; only rows proposed by the optional local
 * model are AI-assisted. Labelling regex output as AI would overstate what the
 * system does, and would hide the rows that genuinely warrant more scepticism.
 */
export function ProvenanceChip({
  provenance,
  extractor,
}: {
  provenance: "rule" | "ai";
  extractor: string;
}) {
  const isAi = provenance === "ai";
  return (
    <Tooltip
      title={
        isAi
          ? `Proposed by a local model (${extractor}). Its quote was verified against the source document before being shown.`
          : `Matched by a deterministic pattern (${extractor}). No model involved.`
      }
    >
      <Chip
        size="small"
        variant="outlined"
        icon={isAi ? <PsychologyIcon /> : <RuleIcon />}
        label={isAi ? "AI-assisted" : "Rule-based"}
        sx={{ fontSize: "0.6875rem", "& .MuiChip-icon": { fontSize: 15 } }}
      />
    </Tooltip>
  );
}
