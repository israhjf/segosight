import { Suspense, lazy, useCallback, useEffect, useState } from "react";
import { Route, Routes } from "react-router-dom";
import Alert from "@mui/material/Alert";
import LinearProgress from "@mui/material/LinearProgress";
import Snackbar from "@mui/material/Snackbar";

import { ReviewerProvider } from "@/features/review/ReviewerContext";
import { api } from "@/shared/api/client";
import type { Alert as AlertType, Overview, ReviewItem } from "@/shared/types";
import { AppShell } from "./AppShell";

// The detail route owns the charting library; splitting it keeps the initial
// bundle to what the Overview screen actually needs.
const AlertDetailPage = lazy(() =>
  import("@/features/alerts/AlertDetailPage").then((module) => ({
    default: module.AlertDetailPage,
  }))
);
import { OverviewPage } from "@/features/overview/OverviewPage";

export function App() {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [reviewItems, setReviewItems] = useState<ReviewItem[]>([]);
  const [alerts, setAlerts] = useState<AlertType[]>([]);
  const [loading, setLoading] = useState(true);
  const [toast, setToast] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Load the three panels independently. Promise.all would discard every
  // successful response the moment one endpoint failed, blanking a page that
  // still had most of its data -- which is what a single failing /api/overview
  // did: alerts had loaded fine and the queue still rendered "0 active".
  const load = useCallback(async () => {
    setLoading(true);
    const [overviewResult, reviewResult, alertsResult] = await Promise.allSettled([
      api.overview(),
      api.reviewQueue(),
      api.alerts(),
    ]);

    if (overviewResult.status === "fulfilled") setOverview(overviewResult.value);
    if (reviewResult.status === "fulfilled") setReviewItems(reviewResult.value);
    if (alertsResult.status === "fulfilled") setAlerts(alertsResult.value);

    const failures = [
      ["summary counts", overviewResult],
      ["review queue", reviewResult],
      ["alert queue", alertsResult],
    ]
      .filter(([, result]) => (result as PromiseSettledResult<unknown>).status === "rejected")
      .map(([label, result]) => {
        const reason = (result as PromiseRejectedResult).reason;
        return `${label} (${reason instanceof Error ? reason.message : "unknown error"})`;
      });

    setError(
      failures.length
        ? `Could not load ${failures.join(" and ")}. The rest of the page is current.`
        : null
    );
    setLoading(false);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const onChanged = useCallback(
    (message: string) => {
      setToast(message);
      void load();
    },
    [load]
  );

  return (
    <ReviewerProvider>
      <AppShell overview={overview} onRefresh={load}>
        {error && (
          <Alert severity="error" sx={{ mb: 3 }}>
            {error}
          </Alert>
        )}
        <Routes>
          <Route
            path="/"
            element={
              <OverviewPage
                overview={overview}
                reviewItems={reviewItems}
                alerts={alerts}
                loading={loading}
                onChanged={onChanged}
              />
            }
          />
          <Route
            path="/alerts/:alertId"
            element={
              <Suspense fallback={<LinearProgress />}>
                <AlertDetailPage />
              </Suspense>
            }
          />
        </Routes>
      </AppShell>

      <Snackbar
        open={Boolean(toast)}
        autoHideDuration={5000}
        onClose={() => setToast(null)}
        anchorOrigin={{ vertical: "bottom", horizontal: "center" }}
      >
        <Alert severity="success" onClose={() => setToast(null)} variant="filled">
          {toast}
        </Alert>
      </Snackbar>
    </ReviewerProvider>
  );
}
