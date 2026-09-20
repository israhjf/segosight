import { useState, type MouseEvent } from "react";
import { useNavigate } from "react-router-dom";
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

import { useReviewer } from "@/features/review/ReviewerContext";
import { useExportScope } from "./ExportScopeContext";

/**
 * Export actions for the dashboard.
 *
 * Several of Sego's accounts are healthcare facilities where water-safety
 * documentation is a compliance matter, and the client's stated pain includes a
 * hospital asking for records they "should be able to produce in an afternoon
 * and currently cannot". So export is a first-class surface, not a convenience.
 *
 * Print and PDF are the same surface: both open the /report route, which
 * renders the queue flat and expanded with its provenance stamp, and hand it
 * to the browser's print dialog. PDF is what you get by choosing "Save as
 * PDF" there.
 *
 * CSV is an archive of two files, built server-side. Governed alerts and
 * pending insights share four columns out of twenty and are not the same kind
 * of claim -- one carries a rule version, the other a confidence score -- so
 * they stay in separate CSVs with a manifest explaining which is which.
 */

type ExportFormat = "print" | "pdf" | "csv";

const ACTIONS: Array<{
  id: ExportFormat;
  label: string;
  icon: typeof PrintOutlinedIcon;
}> = [
  { id: "print", label: "Print report", icon: PrintOutlinedIcon },
  { id: "pdf", label: "Download as PDF", icon: PictureAsPdfOutlinedIcon },
  { id: "csv", label: "Download CSVs", icon: TableChartOutlinedIcon },
];

export function ExportMenu() {
  const [anchor, setAnchor] = useState<HTMLElement | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const navigate = useNavigate();
  const { reviewer } = useReviewer();
  const { severity } = useExportScope();

  const open = (event: MouseEvent<HTMLElement>) => setAnchor(event.currentTarget);
  const close = () => setAnchor(null);

  const query = severity === "all" ? "" : `?severity=${encodeURIComponent(severity)}`;

  const choose = (format: ExportFormat) => {
    close();

    if (format === "print" || format === "pdf") {
      // Both land on the same document. The report page opens the print
      // dialog itself, where "Save as PDF" is the destination.
      navigate(`/report${query}${query ? "&" : "?"}print=1`);
      return;
    }

    // A plain GET with Content-Disposition: the browser saves it without the
    // page needing to hold the bytes. The archive is built from the same
    // queries the dashboard uses, so it cannot drift from what is on screen.
    const params = new URLSearchParams({ severity, reviewer });
    const link = document.createElement("a");
    link.href = `/api/export/bundle.zip?${params.toString()}`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);

    const scope = severity === "all" ? "all alerts" : `${severity} alerts`;
    setToast(
      `Preparing ${scope} plus the pending review queue — two CSVs in one archive.`
    );
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
        <Alert severity="success" variant="filled" onClose={() => setToast(null)}>
          {toast}
        </Alert>
      </Snackbar>
    </>
  );
}
