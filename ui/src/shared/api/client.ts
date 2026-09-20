import type {
  Alert,
  AlertDetail,
  ConfirmResult,
  DecisionResult,
  IngestProfile,
  MappingDecision,
  Overview,
  PipelineResult,
  ReviewItem,
} from "../types";

export class ApiError extends Error {
  constructor(readonly status: number, message: string) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  // A FormData body carries its own multipart Content-Type, including a
  // boundary the browser generates. Forcing application/json onto it makes
  // the upload unparseable server-side.
  const isForm = init?.body instanceof FormData;
  const response = await fetch(path, {
    headers: isForm ? undefined : { "Content-Type": "application/json" },
    ...init,
    ...(isForm ? { headers: undefined } : {}),
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

  alerts: (limit = 100, evidenceLimit = 3) =>
    request<Alert[]>(`/api/alerts?limit=${limit}&evidence_limit=${evidenceLimit}`),

  alert: (alertId: string) =>
    request<AlertDetail>(`/api/alerts/${encodeURIComponent(alertId)}`),

  runPipeline: () =>
    request<PipelineResult>("/api/pipeline/run", { method: "POST" }),

  /**
   * Stage an upload and get back what ingesting it would do.
   *
   * `webkitRelativePath` is sent alongside each file so a folder drop keeps
   * its structure -- it is how the backend tells `communications/` from a
   * loose file, and it is the whole reason folder upload is useful here.
   * Content-Type is deliberately unset: the browser must add the multipart
   * boundary itself.
   */
  uploadData: (files: File[]) => {
    const form = new FormData();
    for (const file of files) {
      form.append("files", file);
      form.append("paths", file.webkitRelativePath || file.name);
    }
    return request<IngestProfile>("/api/ingest/upload", {
      method: "POST",
      body: form,
      headers: {},
    });
  },

  ingestProfile: (uploadId: string) =>
    request<IngestProfile>(`/api/ingest/${encodeURIComponent(uploadId)}`),

  confirmIngest: (
    uploadId: string,
    body: {
      uploader: string;
      batch_name?: string;
      source_system?: string;
      mappings: MappingDecision[];
    }
  ) =>
    request<ConfirmResult>(
      `/api/ingest/${encodeURIComponent(uploadId)}/confirm`,
      { method: "POST", body: JSON.stringify(body) }
    ),

  discardUpload: (uploadId: string) =>
    request<{ status: string }>(`/api/ingest/${encodeURIComponent(uploadId)}`, {
      method: "DELETE",
    }),
};
