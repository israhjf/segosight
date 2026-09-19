import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";

/**
 * Verbatim source text.
 *
 * Every extracted claim shows the sentence it came from. A reviewer approving
 * a compliance-adjacent item should never have to trust a paraphrase, and the
 * monospace face plus the rule on the left mark it as quoted evidence rather
 * than interface copy.
 */
export function QuoteBlock({
  quote,
  attribution,
}: {
  quote: string;
  attribution?: string;
}) {
  return (
    <Box
      component="figure"
      sx={{
        m: 0,
        pl: 1.75,
        borderLeft: 3,
        borderColor: "primary.main",
        py: 0.25,
      }}
    >
      <Typography
        component="blockquote"
        className="quote"
        sx={{ fontSize: "0.875rem", lineHeight: 1.55, color: "text.primary" }}
      >
        &ldquo;{quote}&rdquo;
      </Typography>
      {attribution && (
        <Typography
          component="figcaption"
          variant="caption"
          color="text.secondary"
          sx={{ mt: 0.5, display: "block" }}
        >
          {attribution}
        </Typography>
      )}
    </Box>
  );
}
