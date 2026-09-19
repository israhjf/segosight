import { useEffect, useState } from "react";
import { Link as RouterLink, useParams } from "react-router-dom";
import Alert from "@mui/material/Alert";
import Box from "@mui/material/Box";
import Breadcrumbs from "@mui/material/Breadcrumbs";
import Button from "@mui/material/Button";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import CircularProgress from "@mui/material/CircularProgress";
import Divider from "@mui/material/Divider";
import Link from "@mui/material/Link";
import Stack from "@mui/material/Stack";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableContainer from "@mui/material/TableContainer";
import TableHead from "@mui/material/TableHead";
import TableRow from "@mui/material/TableRow";
import Typography from "@mui/material/Typography";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";

import { SeverityChip } from "@/shared/SeverityChip";
import { api } from "@/shared/api";
import { currency, humanize, isoDate, shortDate } from "@/shared/format";
import type { AlertDetail } from "@/shared/types";
import { EvidenceLine } from "./EvidenceLine";
import { TrendChart } from "./TrendChart";

function Facts({ detail }: { detail: AlertDetail }) {
  const rows: Array<[string, string]> = [
    ["Customer", detail.customer_name ?? "—"],
    ["Account tier", detail.account_tier ?? "—"],
    ["Contract value", currency(detail.acv_usd)],
    ["Facility", detail.facility_name ?? detail.facility_id ?? "—"],
    ["System", detail.system_label ?? detail.system_id ?? "—"],
    ["Treatment program", detail.governing_program ?? "—"],
    ["Risk class", humanize(detail.risk_class)],
    ["First observed", shortDate(detail.first_observed)],
    ["Last observed", shortDate(detail.last_observed)],
  ];
  return (
    <Stack spacing={1}>
      {rows.map(([label, value]) => (
        <Stack key={label} direction="row" justifyContent="space-between" spacing={2}>
          <Typography variant="body2" color="text.secondary">
            {label}
          </Typography>
          <Typography variant="body2" sx={{ fontWeight: 500, textAlign: "right" }}>
            {value}
          </Typography>
        </Stack>
      ))}
    </Stack>
  );
}

export function AlertDetailPage() {
  const { alertId = "" } = useParams();
  const [detail, setDetail] = useState<AlertDetail | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setDetail(null);
    setError(null);
    api
      .alert(alertId)
      .then((data) => active && setDetail(data))
      .catch((caught) => active && setError(String(caught.message ?? caught)));
    return () => {
      active = false;
    };
  }, [alertId]);

  if (error) {
    return (
      <Box sx={{ p: 3 }}>
        <Alert severity="error">{error}</Alert>
        <Button component={RouterLink} to="/" startIcon={<ArrowBackIcon />} sx={{ mt: 2 }}>
          Back to overview
        </Button>
      </Box>
    );
  }

  if (!detail) {
    return (
      <Stack alignItems="center" sx={{ py: 10 }}>
        <CircularProgress />
      </Stack>
    );
  }

  const unreviewed = detail.evidence_basis === "prose_pending_review";

  return (
    <Stack spacing={2.5}>
      <Breadcrumbs>
        <Link component={RouterLink} to="/" underline="hover" color="inherit">
          Overview
        </Link>
        <Typography color="text.primary">{humanize(detail.risk_class)}</Typography>
      </Breadcrumbs>

      <Stack direction="row" spacing={1.5} alignItems="center" flexWrap="wrap">
        <SeverityChip severity={detail.severity} size="medium" />
        <Typography variant="h1">{detail.title}</Typography>
      </Stack>

      {unreviewed && (
        <Alert severity="warning" variant="outlined">
          This alert rests on a prose extraction that has not been reviewed.
          Approve or reject it in the review queue before acting on it with a
          customer.
        </Alert>
      )}

      <Box
        sx={{
          display: "grid",
          gap: 2.5,
          gridTemplateColumns: { xs: "1fr", lg: "minmax(0, 2fr) minmax(280px, 1fr)" },
        }}
      >
        <Stack spacing={2.5} sx={{ minWidth: 0 }}>
          <Card>
            <CardContent>
              <Typography variant="overline" color="text.secondary">
                Why this is flagged
              </Typography>
              <Typography variant="body1" sx={{ mt: 0.5 }}>
                {detail.why}
              </Typography>
              <Divider sx={{ my: 2 }} />
              <Typography variant="overline" color="text.secondary">
                What it costs to wait
              </Typography>
              <Typography variant="body2" sx={{ mt: 0.5 }} color="text.secondary">
                {detail.consequence}
              </Typography>
            </CardContent>
          </Card>

          {detail.series.length > 0 && (
            <Card>
              <CardContent>
                <TrendChart
                  series={detail.series}
                  unit={detail.standard_unit}
                  lowerLimit={detail.lower_limit}
                  upperLimit={detail.upper_limit}
                  parameter={detail.parameter_code ?? "measurement"}
                />
              </CardContent>
            </Card>
          )}

          {detail.escalations.length > 0 && (
            <Card>
              <CardContent>
                <Typography variant="subtitle2" sx={{ mb: 1 }}>
                  Escalation history
                </Typography>
                <TableContainer sx={{ maxHeight: 320 }}>
                  <Table size="small" stickyHeader>
                    <TableHead>
                      <TableRow>
                        <TableCell>Date</TableCell>
                        <TableCell>Result</TableCell>
                        <TableCell>Trigger</TableCell>
                        <TableCell>Documented</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {detail.escalations.map((row, index) => (
                        <TableRow key={index}>
                          <TableCell>{isoDate(String(row.observed_at))}</TableCell>
                          <TableCell>10^{String(row.dipslide_log10).replace(".0", "")}</TableCell>
                          <TableCell>{humanize(String(row.escalation_type))}</TableCell>
                          <TableCell>
                            {row.documented ? (
                              "Yes"
                            ) : (
                              <Typography
                                variant="body2"
                                sx={{ color: "severity.critical.main", fontWeight: 600 }}
                              >
                                No — {String(row.days_undocumented)}d
                              </Typography>
                            )}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableContainer>
              </CardContent>
            </Card>
          )}
        </Stack>

        <Stack spacing={2.5} sx={{ minWidth: 0 }}>
          <Card>
            <CardContent>
              <Typography variant="subtitle2" sx={{ mb: 1.5 }}>
                Account
              </Typography>
              <Facts detail={detail} />
            </CardContent>
          </Card>

          {detail.coverage && (
            <Card>
              <CardContent>
                <Typography variant="subtitle2" sx={{ mb: 1 }}>
                  Service coverage
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  {String(detail.coverage.explanation)}
                </Typography>
              </CardContent>
            </Card>
          )}

          <Card>
            <CardContent>
              <Typography variant="subtitle2" sx={{ mb: 1.5 }}>
                Evidence ({detail.evidence.length})
              </Typography>
              {detail.evidence.length === 0 ? (
                <Typography variant="body2" color="text.secondary">
                  This alert rests entirely on structured measurements.
                </Typography>
              ) : (
                <Stack spacing={1.25}>
                  {detail.evidence.map((evidence) => (
                    <EvidenceLine key={evidence.evidence_id} evidence={evidence} />
                  ))}
                </Stack>
              )}
            </CardContent>
          </Card>
        </Stack>
      </Box>
    </Stack>
  );
}
