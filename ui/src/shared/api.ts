import type {
  Alert,
  AlertDetail,
  DecisionResult,
  Overview,
  PipelineResult,
  ReviewItem,
} from "./types";

export class ApiError extends Error {
  constructor(readonly status: number, message: string) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!response.ok) {
    // FastAPI returns {detail: string} for handled errors and a validation
    // array for 422; surface whichever is present rather than "Bad Request".
    let message = response.statusText;
    try {
      const body = await response.json();
      if (typeof body?.detail === "string") message = body.detail;
      else if (Array.isArray(body?.detail)) message = body.detail[0]?.msg ?? message;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(response.status, message);
  }
  return response.json() as Promise<T>;
}

export const api = {
  overview: () => request<Overview>("/api/overview"),

  reviewQueue: (limit = 50) =>
    request<ReviewItem[]>(`/api/review?limit=${limit}`),

  decide: (insightId: string, decision: "approved" | "rejected", reviewer: string, note?: string) =>
    request<DecisionResult>(
      `/api/review/${encodeURIComponent(insightId)}/decision`,
      {
        method: "POST",
        body: JSON.stringify({ decision, reviewer, note }),
      }
    ),

  alerts: (limit = 100) => request<Alert[]>(`/api/alerts?limit=${limit}`),

  alert: (alertId: string) =>
    request<AlertDetail>(`/api/alerts/${encodeURIComponent(alertId)}`),

  runPipeline: () =>
    request<PipelineResult>("/api/pipeline/run", { method: "POST" }),
};
