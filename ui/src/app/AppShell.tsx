import AppBar from "@mui/material/AppBar";
import Avatar from "@mui/material/Avatar";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Container from "@mui/material/Container";
import Stack from "@mui/material/Stack";
import Toolbar from "@mui/material/Toolbar";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import WaterDropIcon from "@mui/icons-material/WaterDrop";
import { Link as RouterLink } from "react-router-dom";
import type { ReactNode } from "react";

import { PipelineAction } from "@/features/pipeline/PipelineAction";
import { useReviewer } from "@/features/review/ReviewerContext";
import { isoDate } from "@/shared/format";
import type { Overview } from "@/shared/types";
import { ThemeMenu } from "./ThemeMenu";

type Props = {
  overview: Overview | null;
  onRefresh: () => void;
  children: ReactNode;
};

export function AppShell({ overview, onRefresh, children }: Props) {
  const { reviewer } = useReviewer();
  const initials = reviewer
    .split(" ")
    .map((part) => part[0])
    .join("")
    .slice(0, 2);

  return (
    <Box sx={{ minHeight: "100dvh", bgcolor: "background.default" }}>
      <AppBar position="sticky">
        <Toolbar sx={{ gap: 2, flexWrap: "wrap", minHeight: { sm: 64 } }}>
          <Stack
            component={RouterLink}
            to="/"
            direction="row"
            spacing={1}
            alignItems="center"
            sx={{ textDecoration: "none", color: "inherit" }}
          >
            <WaterDropIcon color="primary" />
            <Typography variant="h3" sx={{ fontSize: "1.125rem", fontWeight: 600 }}>
              SegoSight
            </Typography>
          </Stack>

          <Typography variant="body2" color="text.secondary">
            Overview
          </Typography>

          <Box sx={{ flex: 1 }} />

          {/*
            The pending-review count lives in the stat tiles and the tab label
            now, so the app bar carries only the data-currency pill -- the one
            fact neither of those conveys.
          */}
          {overview && (
            <Tooltip title="Data current as of the latest observation in the warehouse">
              <Chip
                size="small"
                variant="outlined"
                label={`As of ${isoDate(overview.as_of_date)}`}
              />
            </Tooltip>
          )}

          <PipelineAction onComplete={onRefresh} />
          <ThemeMenu />

          <Tooltip title={`Signed in as ${reviewer}. Decisions are recorded under this name.`}>
            <Stack direction="row" spacing={1} alignItems="center">
              <Avatar sx={{ width: 30, height: 30, fontSize: "0.8rem" }}>{initials}</Avatar>
              <Typography variant="body2" sx={{ display: { xs: "none", md: "block" } }}>
                {reviewer.split(" ")[0]}
              </Typography>
            </Stack>
          </Tooltip>
        </Toolbar>
      </AppBar>

      <Container maxWidth="lg" sx={{ py: 3 }}>
        {children}
      </Container>
    </Box>
  );
}
