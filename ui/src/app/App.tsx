import { Suspense, lazy, useCallback, useEffect, useState } from "react";
import { Route, Routes } from "react-router-dom";
import Alert from "@mui/material/Alert";
import LinearProgress from "@mui/material/LinearProgress";
import Snackbar from "@mui/material/Snackbar";

import { ReviewerProvider } from "@/features/review/ReviewerContext";
import { api } from "@/shared/api";
import type { Alert as AlertType, Overview, ReviewItem } from "@/shared/types";
import { AppShell } from "./AppShell";

// The detail route owns the charting library; splitting it keeps the initial
// bundle to what the Overview screen actually needs.
const AlertDetailPage = lazy(() =>
  import("@/features/alerts/AlertDetailPage").then((module) => ({
    default: module.AlertDetailPage,
  }))
);
import { OverviewPage } from "./OverviewPage";

export function App() {
  const [overview, setOverview] = useState<Overview | null>(null);
  const [reviewItems, setReviewItems] = useState<ReviewItem[]>([]);
  const [alerts, setAlerts] = useState<AlertType[]>([]);
  const [loading, setLoading] = useState(true);
  const [toast, setToast] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [nextOverview, nextReview, nextAlerts] = await Promise.all([
        api.overview(),
        api.reviewQueue(),
        api.alerts(),
      ]);
      setOverview(nextOverview);
      setReviewItems(nextReview);
      setAlerts(nextAlerts);
      setError(null);
    } catch (caught) {
      setError(
        caught instanceof Error
          ? `Could not reach the API: ${caught.message}`
          : "Could not reach the API."
      );
    } finally {
      setLoading(false);
    }
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
