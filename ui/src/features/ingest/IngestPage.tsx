import { useCallback, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import Alert from "@mui/material/Alert";
import AlertTitle from "@mui/material/AlertTitle";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Divider from "@mui/material/Divider";
import LinearProgress from "@mui/material/LinearProgress";
import MenuItem from "@mui/material/MenuItem";
import Select from "@mui/material/Select";
import Stack from "@mui/material/Stack";
import Step from "@mui/material/Step";
import StepLabel from "@mui/material/StepLabel";
import Stepper from "@mui/material/Stepper";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Typography from "@mui/material/Typography";
import { alpha } from "@mui/material/styles";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import CheckCircleOutlineIcon from "@mui/icons-material/CheckCircleOutline";
import DescriptionOutlinedIcon from "@mui/icons-material/DescriptionOutlined";
import FolderOpenOutlinedIcon from "@mui/icons-material/FolderOpenOutlined";
import UploadFileOutlinedIcon from "@mui/icons-material/UploadFileOutlined";

import { useReviewer } from "@/features/review/ReviewerContext";
import { api } from "@/shared/api/client";
import { humanize } from "@/shared/format";
import type {
  ConfirmResult,
  IngestProfile,
  MappingDecision,
  UnmatchedItem,
} from "@/shared/types";

const STEPS = ["Select files", "Review what will change", "Confirm"];

const DOCUMENT_CLASSES = ["technician_note", "customer_communication"] as const;

/** Every entity the registry knows, for mapping an unrecognised file. */
const ENTITIES = [
  "customers",
  "systems",
  "service_visits",
  "water_readings",
  "work_orders",
  "chemical_inventory",
] as const;

function Dropzone({
  onFiles,
  busy,
}: {
  onFiles: (files: File[]) => void;
  busy: boolean;
}) {
  const fileInput = useRef<HTMLInputElement>(null);
  const folderInput = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);

  const handleDrop = useCallback(
    (event: React.DragEvent) => {
      event.preventDefault();
      setOver(false);
      const dropped = Array.from(event.dataTransfer.files);
      if (dropped.length) onFiles(dropped);
    },
    [onFiles]
  );

  return (
    <Box
      onDragOver={(event) => {
        event.preventDefault();
        setOver(true);
      }}
      onDragLeave={() => setOver(false)}
      onDrop={handleDrop}
      sx={{
        border: 2,
        borderStyle: "dashed",
        borderColor: over ? "primary.main" : "divider",
        borderRadius: 2,
        bgcolor: (theme) =>
          over ? alpha(theme.palette.primary.main, 0.06) : "transparent",
        p: 5,
        textAlign: "center",
        transition: "border-color 150ms, background-color 150ms",
      }}
    >
      <FolderOpenOutlinedIcon sx={{ fontSize: 40, color: "text.secondary" }} />
      <Typography variant="h3" sx={{ fontSize: "1.05rem", mt: 1 }}>
        Drop a data export here
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5, mb: 2.5 }}>
        A whole batch folder, or individual CSV and note files. Nothing is
        ingested until you have reviewed it.
      </Typography>

      <Stack direction="row" spacing={1.5} justifyContent="center" flexWrap="wrap" useFlexGap>
        <Button
          variant="contained"
          startIcon={<UploadFileOutlinedIcon />}
          onClick={() => fileInput.current?.click()}
          disabled={busy}
        >
          Choose files
        </Button>
        <Button
          variant="outlined"
          startIcon={<FolderOpenOutlinedIcon />}
          onClick={() => folderInput.current?.click()}
          disabled={busy}
        >
          Choose a folder
        </Button>
      </Stack>

      <input
        ref={fileInput}
        type="file"
        multiple
        hidden
        accept=".csv,.txt,.md,.pdf,.docx"
        onChange={(event) => onFiles(Array.from(event.target.files ?? []))}
      />
      {/*
        webkitdirectory is non-standard but supported everywhere that matters,
        and it is the only way the browser will hand over a folder's relative
        paths -- which is exactly what distinguishes `communications/` from a
        loose file. React does not type it, hence the spread.
      */}
      <input
        ref={folderInput}
        type="file"
        multiple
        hidden
        {...{ webkitdirectory: "", directory: "" }}
        onChange={(event) => onFiles(Array.from(event.target.files ?? []))}
      />
    </Box>
  );
}

function MappingRow({
  item,
  value,
  onChange,
}: {
  item: UnmatchedItem;
  value: MappingDecision;
  onChange: (next: MappingDecision) => void;
}) {
  const options = item.kind === "directory" ? DOCUMENT_CLASSES : ENTITIES;
  const kind = item.kind === "directory" ? "document" : "entity";

  return (
    <Stack
      direction={{ xs: "column", sm: "row" }}
      spacing={1.5}
      alignItems={{ sm: "center" }}
      sx={{ py: 1.25 }}
    >
      <Box sx={{ flex: 1, minWidth: 0 }}>
        <Typography variant="body2" sx={{ fontWeight: 600 }}>
          {item.path}
        </Typography>
        <Typography variant="caption" color="text.secondary">
          {item.kind === "directory" ? "Folder" : "File"} not recognised
          {item.suggestion ? ` · closest known name is ${item.suggestion}` : ""}
        </Typography>
      </Box>
      <Select
        size="small"
        value={value.kind === "exclude" ? "exclude" : (value.target ?? "")}
        displayEmpty
        onChange={(event) => {
          const chosen = event.target.value;
          onChange(
            chosen === "exclude"
              ? { path: item.path, kind: "exclude" }
              : { path: item.path, kind, target: chosen }
          );
        }}
        sx={{ minWidth: 240 }}
      >
        <MenuItem value="" disabled>
          Choose what this is
        </MenuItem>
        {options.map((option) => (
          <MenuItem key={option} value={option}>
            {humanize(option)}
          </MenuItem>
        ))}
        <Divider />
        <MenuItem value="exclude">Leave it out of this batch</MenuItem>
      </Select>
    </Stack>
  );
}

function Review({
  profile,
  mappings,
  setMapping,
}: {
  profile: IngestProfile;
  mappings: Record<string, MappingDecision>;
  setMapping: (path: string, next: MappingDecision) => void;
}) {
  const blocking = profile.findings.filter((f) => f.level === "blocking");
  const advisory = profile.findings.filter((f) => f.level === "advisory");
  const unresolved = profile.unmatched.filter((u) => !mappings[u.path]);

  return (
    <Stack spacing={2.5}>
      <Stack direction="row" spacing={2} flexWrap="wrap" useFlexGap>
        <Chip label={`Batch: ${profile.batch_root}`} />
        <Chip variant="outlined" label={`${profile.total_rows} rows`} />
        <Chip variant="outlined" label={`${profile.total_documents} documents`} />
      </Stack>

      {profile.unmatched.length > 0 && (
        <Card variant="outlined">
          <CardContent>
            <Typography variant="h3" sx={{ fontSize: "1rem" }}>
              Needs your decision
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5, mb: 1 }}>
              These names are not in the registry. Nothing is guessed — tell the
              system what each one is, and the choice is saved so the next drop
              using that name resolves on its own.
            </Typography>
            <Divider />
            {profile.unmatched.map((item) => (
              <MappingRow
                key={item.path}
                item={item}
                value={mappings[item.path] ?? { path: item.path, kind: "exclude" }}
                onChange={(next) => setMapping(item.path, next)}
              />
            ))}
          </CardContent>
        </Card>
      )}

      {blocking.length > 0 && unresolved.length === 0 && (
        <Alert severity="error" variant="outlined">
          <AlertTitle>Cannot ingest yet</AlertTitle>
          <ul style={{ margin: 0, paddingLeft: "1.1rem" }}>
            {blocking
              .filter((f) => f.code !== "unmapped")
              .map((finding) => (
                <li key={finding.message}>{finding.message}</li>
              ))}
          </ul>
        </Alert>
      )}

      {profile.entities.length > 0 && (
        <Card variant="outlined">
          <CardContent sx={{ pb: 1 }}>
            <Typography variant="h3" sx={{ fontSize: "1rem", mb: 1 }}>
              Tabular data
            </Typography>
            <Box sx={{ overflowX: "auto" }}>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>File</TableCell>
                    <TableCell>Matches</TableCell>
                    <TableCell align="right">Rows</TableCell>
                    <TableCell align="right">New</TableCell>
                    <TableCell align="right">Supersedes</TableCell>
                    <TableCell>Schema</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {profile.entities.map((entity) => (
                    <TableRow key={entity.file}>
                      <TableCell sx={{ fontFamily: "monospace", fontSize: "0.75rem" }}>
                        {entity.file}
                      </TableCell>
                      <TableCell>{humanize(entity.entity)}</TableCell>
                      <TableCell align="right">{entity.rows}</TableCell>
                      <TableCell align="right" sx={{ fontWeight: 600 }}>
                        {entity.new_keys}
                      </TableCell>
                      <TableCell align="right">{entity.superseding_keys}</TableCell>
                      <TableCell>
                        {entity.added_columns.length === 0 &&
                        entity.missing_columns.length === 0 ? (
                          <Typography variant="caption" color="text.secondary">
                            unchanged
                          </Typography>
                        ) : (
                          <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
                            {entity.added_columns.map((column) => (
                              <Chip key={column} size="small" label={`+${column}`} />
                            ))}
                            {entity.missing_columns.map((column) => (
                              <Chip
                                key={column}
                                size="small"
                                variant="outlined"
                                label={`−${column}`}
                              />
                            ))}
                          </Stack>
                        )}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </Box>
          </CardContent>
        </Card>
      )}

      {profile.documents.length > 0 && (
        <Card variant="outlined">
          <CardContent>
            <Typography variant="h3" sx={{ fontSize: "1rem", mb: 1 }}>
              Documents
            </Typography>
            <Stack spacing={1}>
              {profile.documents.map((doc) => (
                <Stack
                  key={doc.directory}
                  direction="row"
                  spacing={1.5}
                  alignItems="center"
                >
                  <DescriptionOutlinedIcon fontSize="small" color="disabled" />
                  <Typography variant="body2" sx={{ flex: 1 }}>
                    <code>{doc.directory}/</code> → {humanize(doc.document_class)}
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    {doc.documents}
                  </Typography>
                </Stack>
              ))}
            </Stack>
          </CardContent>
        </Card>
      )}

      {profile.absent_entities.length > 0 && (
        <Alert severity="info" variant="outlined">
          <AlertTitle>Delta load</AlertTitle>
          No {profile.absent_entities.map(humanize).join(" or ")} file in this
          drop. Existing records keep their current values — this is normal for a
          periodic export and is not an error.
        </Alert>
      )}

      {advisory.map((finding) => (
        <Alert key={finding.message} severity="warning" variant="outlined">
          {finding.message}
        </Alert>
      ))}
    </Stack>
  );
}

export function IngestPage() {
  const navigate = useNavigate();
  const { reviewer } = useReviewer();

  const [step, setStep] = useState(0);
  const [busy, setBusy] = useState(false);
  const [profile, setProfile] = useState<IngestProfile | null>(null);
  const [result, setResult] = useState<ConfirmResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [mappings, setMappings] = useState<Record<string, MappingDecision>>({});

  const upload = async (files: File[]) => {
    if (!files.length) return;
    setBusy(true);
    setError(null);
    try {
      const staged = await api.uploadData(files);
      setProfile(staged);
      setMappings({});
      setStep(1);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setBusy(false);
    }
  };

  const confirm = async () => {
    if (!profile) return;
    setBusy(true);
    setError(null);
    try {
      const confirmed = await api.confirmIngest(
        profile.upload_id,
        reviewer,
        Object.values(mappings)
      );
      setResult(confirmed);
      setStep(2);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setBusy(false);
    }
  };

  const cancel = async () => {
    if (profile) await api.discardUpload(profile.upload_id).catch(() => {});
    setProfile(null);
    setMappings({});
    setStep(0);
  };

  const unresolved = profile
    ? profile.unmatched.filter((item) => !mappings[item.path])
    : [];
  const otherBlockers = profile
    ? profile.findings.filter((f) => f.level === "blocking" && f.code !== "unmapped")
    : [];
  const ready =
    Boolean(profile) && unresolved.length === 0 && otherBlockers.length === 0;

  return (
    <Stack spacing={3}>
      <Stack direction="row" spacing={1.5} alignItems="center">
        <Button startIcon={<ArrowBackIcon />} onClick={() => navigate("/")} size="small">
          Dashboard
        </Button>
      </Stack>

      <Box>
        <Typography variant="h1" sx={{ fontSize: "1.6rem" }}>
          Upload data
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
          Files are held aside and profiled against the governed tables. Nothing
          is written until you confirm.
        </Typography>
      </Box>

      <Stepper activeStep={step} sx={{ maxWidth: 640 }}>
        {STEPS.map((label) => (
          <Step key={label}>
            <StepLabel>{label}</StepLabel>
          </Step>
        ))}
      </Stepper>

      {busy && <LinearProgress />}

      {error && (
        <Alert severity="error" onClose={() => setError(null)}>
          {error}
        </Alert>
      )}

      {step === 0 && <Dropzone onFiles={upload} busy={busy} />}

      {step === 1 && profile && (
        <>
          <Review
            profile={profile}
            mappings={mappings}
            setMapping={(path, next) =>
              setMappings((prev) => ({ ...prev, [path]: next }))
            }
          />
          <Stack direction="row" spacing={1.5} justifyContent="flex-end">
            <Button onClick={cancel} disabled={busy}>
              Discard
            </Button>
            <Button variant="contained" onClick={confirm} disabled={!ready || busy}>
              {busy ? <CircularProgress size={20} /> : "Confirm ingestion"}
            </Button>
          </Stack>
          {!ready && unresolved.length > 0 && (
            <Typography variant="caption" color="text.secondary" textAlign="right">
              {unresolved.length} item{unresolved.length === 1 ? "" : "s"} still
              need a decision.
            </Typography>
          )}
        </>
      )}

      {step === 2 && result && (
        <Card variant="outlined">
          <CardContent>
            <Stack direction="row" spacing={1.5} alignItems="center" sx={{ mb: 1.5 }}>
              <CheckCircleOutlineIcon color="success" />
              <Typography variant="h3" sx={{ fontSize: "1.05rem" }}>
                Ingested as batch {result.batch_name}
              </Typography>
            </Stack>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
              {result.files_promoted} file{result.files_promoted === 1 ? "" : "s"}{" "}
              promoted and registered at sequence {result.sequence}. Rebuild took{" "}
              {result.duration_seconds}s.
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
                {Object.keys(result.after).map((key) => (
                  <TableRow key={key}>
                    <TableCell>{humanize(key)}</TableCell>
                    <TableCell align="right">{result.before[key]}</TableCell>
                    <TableCell align="right">{result.after[key]}</TableCell>
                    <TableCell align="right" sx={{ fontWeight: 600 }}>
                      {result.delta[key] > 0 ? "+" : ""}
                      {result.delta[key]}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>

            {result.aliases_added.length > 0 && (
              <Alert severity="info" variant="outlined" sx={{ mt: 2 }}>
                Saved for next time: {result.aliases_added.join(", ")}
              </Alert>
            )}

            <Stack direction="row" spacing={1.5} sx={{ mt: 2.5 }}>
              <Button variant="contained" onClick={() => navigate("/")}>
                Back to dashboard
              </Button>
              <Button
                onClick={() => {
                  setProfile(null);
                  setResult(null);
                  setMappings({});
                  setStep(0);
                }}
              >
                Upload another
              </Button>
            </Stack>
          </CardContent>
        </Card>
      )}
    </Stack>
  );
}
