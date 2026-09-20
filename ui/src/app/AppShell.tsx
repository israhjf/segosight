import AppBar from "@mui/material/AppBar";
import Avatar from "@mui/material/Avatar";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import Container from "@mui/material/Container";
import Stack from "@mui/material/Stack";
import Toolbar from "@mui/material/Toolbar";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import WaterDropIcon from "@mui/icons-material/WaterDrop";
import IconButton from "@mui/material/IconButton";
import Menu from "@mui/material/Menu";
import CloudUploadOutlinedIcon from "@mui/icons-material/CloudUploadOutlined";
import MoreVertIcon from "@mui/icons-material/MoreVert";
import { Link as RouterLink } from "react-router-dom";
import { useState, type MouseEvent, type ReactNode } from "react";

import { ExportMenu } from "@/features/export";
import { PipelineAction } from "@/features/pipeline/PipelineAction";
import { useReviewer } from "@/features/review/ReviewerContext";
import { isoDate } from "@/shared/format";
import type { Overview } from "@/shared/types";
import { ThemeMenu } from "@/design-system/ThemeMenu";

type Props = {
  overview: Overview | null;
  onRefresh: () => void;
  children: ReactNode;
};

export function AppShell({ overview, onRefresh, children }: Props) {
  const { reviewer } = useReviewer();
  const [dataMenu, setDataMenu] = useState<HTMLElement | null>(null);
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

          <ExportMenu overview={overview} />

          {/*
            Upload is the weekly action and gets the prominence; rebuilding
            from existing sources is the occasional one and sits behind the
            overflow. Both stay reachable -- a guideline revision needs a
            rebuild with no new data involved.
          */}
          <Button
            component={RouterLink}
            to="/ingest"
            size="small"
            variant="contained"
            startIcon={<CloudUploadOutlinedIcon />}
          >
            Upload data
          </Button>

          <Tooltip title="More data actions">
            <IconButton
              size="small"
              onClick={(event: MouseEvent<HTMLElement>) =>
                setDataMenu(event.currentTarget)
              }
              aria-haspopup="menu"
              aria-expanded={Boolean(dataMenu)}
              aria-label="More data actions"
            >
              <MoreVertIcon fontSize="small" />
            </IconButton>
          </Tooltip>
          <Menu
            anchorEl={dataMenu}
            open={Boolean(dataMenu)}
            onClose={() => setDataMenu(null)}
            anchorOrigin={{ vertical: "bottom", horizontal: "right" }}
            transformOrigin={{ vertical: "top", horizontal: "right" }}
            slotProps={{
              paper: { variant: "outlined", sx: { mt: 0.5, minWidth: 280 } },
            }}
          >
            <PipelineAction
              onComplete={onRefresh}
              asMenuItem
              onInvoke={() => setDataMenu(null)}
            />
          </Menu>

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
