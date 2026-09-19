import { useState } from "react";
import Divider from "@mui/material/Divider";
import IconButton from "@mui/material/IconButton";
import ListItemIcon from "@mui/material/ListItemIcon";
import ListItemText from "@mui/material/ListItemText";
import Menu from "@mui/material/Menu";
import MenuItem from "@mui/material/MenuItem";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import CheckIcon from "@mui/icons-material/Check";
import DarkModeIcon from "@mui/icons-material/DarkMode";
import LightModeIcon from "@mui/icons-material/LightMode";
import SettingsBrightnessIcon from "@mui/icons-material/SettingsBrightness";

import { useThemeControls, type Contrast } from "@/design-system";

const CONTRASTS: Array<[Contrast, string]> = [
  ["normal", "Standard contrast"],
  ["medium", "Medium contrast"],
  ["high", "High contrast"],
];

export function ThemeMenu() {
  const { mode, contrast, followSystem, toggleMode, setContrast, useSystem } =
    useThemeControls();
  const [anchor, setAnchor] = useState<HTMLElement | null>(null);

  return (
    <>
      <Tooltip title={`Switch to ${mode === "dark" ? "light" : "dark"} mode`}>
        <IconButton onClick={toggleMode} size="small" aria-label="Toggle colour mode">
          {mode === "dark" ? <DarkModeIcon /> : <LightModeIcon />}
        </IconButton>
      </Tooltip>
      {/*
        Hidden for now to keep the app bar uncluttered. Deliberately not
        deleted: the contrast schemes it exposes (medium and high) are a real
        accessibility need, and `prefers-contrast: more` still selects the
        high-contrast palette automatically without this control. Remove the
        `display: none` to bring the menu back.
      */}
      <Tooltip title="Display settings">
        <IconButton
          onClick={(event) => setAnchor(event.currentTarget)}
          size="small"
          aria-label="Display settings"
          sx={{ display: "none" }}
        >
          <SettingsBrightnessIcon />
        </IconButton>
      </Tooltip>
      <Menu anchorEl={anchor} open={Boolean(anchor)} onClose={() => setAnchor(null)}>
        <Typography variant="overline" sx={{ px: 2, color: "text.secondary" }}>
          Contrast
        </Typography>
        {CONTRASTS.map(([value, label]) => (
          <MenuItem
            key={value}
            selected={contrast === value}
            onClick={() => {
              setContrast(value);
              setAnchor(null);
            }}
          >
            <ListItemIcon>{contrast === value && <CheckIcon fontSize="small" />}</ListItemIcon>
            <ListItemText>{label}</ListItemText>
          </MenuItem>
        ))}
        <Divider />
        <MenuItem
          onClick={() => {
            useSystem();
            setAnchor(null);
          }}
        >
          <ListItemIcon>{followSystem && <CheckIcon fontSize="small" />}</ListItemIcon>
          <ListItemText
            primary="Follow system"
            secondary="Match the operating system's appearance"
          />
        </MenuItem>
      </Menu>
    </>
  );
}
