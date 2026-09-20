import { useState, type MouseEvent } from "react";
import Alert from "@mui/material/Alert";
import Button from "@mui/material/Button";
import ListItemIcon from "@mui/material/ListItemIcon";
import ListItemText from "@mui/material/ListItemText";
import Menu from "@mui/material/Menu";
import MenuItem from "@mui/material/MenuItem";
import Snackbar from "@mui/material/Snackbar";
import FileDownloadOutlinedIcon from "@mui/icons-material/FileDownloadOutlined";
import PictureAsPdfOutlinedIcon from "@mui/icons-material/PictureAsPdfOutlined";
import PrintOutlinedIcon from "@mui/icons-material/PrintOutlined";
import TableChartOutlinedIcon from "@mui/icons-material/TableChartOutlined";

/**
 * Export actions for the dashboard.
 *
 * Several of Sego's accounts are healthcare facilities where water-safety
 * documentation is a compliance matter, and the client's stated pain includes a
 * hospital asking for records they "should be able to produce in an afternoon
 * and currently cannot". So export is a first-class surface, not a convenience.
 *
 * The three actions are placeholders pending the generation backend. They are
 * deliberately left enabled rather than disabled: a disabled control tells a
 * user nothing, while a toast tells them the capability is coming and that
 * their click registered.
 */

type ExportFormat = "print" | "pdf" | "csv";

const ACTIONS: Array<{
  id: ExportFormat;
  label: string;
  icon: typeof PrintOutlinedIcon;
}> = [
  { id: "print", label: "Print report", icon: PrintOutlinedIcon },
  { id: "pdf", label: "Download as PDF", icon: PictureAsPdfOutlinedIcon },
  { id: "csv", label: "Download as CSV", icon: TableChartOutlinedIcon },
];

export function ExportMenu() {
  const [anchor, setAnchor] = useState<HTMLElement | null>(null);
  const [toast, setToast] = useState<string | null>(null);

  const open = (event: MouseEvent<HTMLElement>) => setAnchor(event.currentTarget);
  const close = () => setAnchor(null);

  const choose = (format: ExportFormat) => {
    close();
    // eslint-disable-next-line no-console -- placeholder until the generator lands
    console.log(`[export] requested format: ${format}`);
    setToast("Export feature coming soon.");
  };

  return (
    <>
      <Button
        size="small"
        variant="outlined"
        startIcon={<FileDownloadOutlinedIcon />}
        onClick={open}
        aria-haspopup="menu"
        aria-expanded={Boolean(anchor)}
        aria-controls={anchor ? "export-menu" : undefined}
      >
        Export
      </Button>

      <Menu
        id="export-menu"
        anchorEl={anchor}
        open={Boolean(anchor)}
        onClose={close}
        anchorOrigin={{ vertical: "bottom", horizontal: "right" }}
        transformOrigin={{ vertical: "top", horizontal: "right" }}
        slotProps={{
          paper: {
            variant: "outlined",
            sx: { mt: 0.5, minWidth: 210, borderColor: "divider" },
          },
        }}
      >
        {ACTIONS.map(({ id, label, icon: Icon }) => (
          <MenuItem key={id} onClick={() => choose(id)}>
            <ListItemIcon>
              <Icon fontSize="small" sx={{ color: "text.secondary" }} />
            </ListItemIcon>
            <ListItemText
              primary={label}
              primaryTypographyProps={{ variant: "body2" }}
            />
          </MenuItem>
        ))}
      </Menu>

      <Snackbar
        open={Boolean(toast)}
        autoHideDuration={4000}
        onClose={() => setToast(null)}
        anchorOrigin={{ vertical: "bottom", horizontal: "center" }}
      >
        <Alert severity="info" variant="filled" onClose={() => setToast(null)}>
          {toast}
        </Alert>
      </Snackbar>
    </>
  );
}
