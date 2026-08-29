/**
 * Typed API client. Every endpoint from PRD §9.5.
 *
 * Injects the Supabase bearer token, normalizes the §9.7 error envelope,
 * and retries once on 401 after a token refresh (PRD §9.2).
 */

import type {
  CreateJobResponse, JobStatusResponse, JobResult, JobListResponse,
  CreateCompareRequest, CompareResult, ApiErrorResponse, ApiError,
} from "./types";
import { MAX_UPLOAD_BYTES, ACCEPTED_MIME, ACCEPTED_EXTENSIONS } from "./types";
import { supabase } from "./supabase";

const BASE = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";
const USE_MOCKS = import.meta.env.VITE_USE_MOCKS === "true";

/** Thrown for every non-2xx response. `code` is the contract error code. */
export class DepthWizardError extends Error {
  constructor(public code: ApiError["code"], message: string, public httpStatus: number) {
    super(message);
    this.name = "DepthWizardError";
  }
}

async function authHeader(): Promise<Record<string, string>> {
  const { data } = await supabase.auth.getSession();
  const token = data.session?.access_token;
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function request<T>(path: string, init: RequestInit = {}, isRetry = false): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: { ...(init.headers ?? {}), ...(await authHeader()) },
  });

  // Token can expire mid-job: refresh once, then retry (PRD §9.2).
  if (res.status === 401 && !isRetry) {
    const { error } = await supabase.auth.refreshSession();
    if (!error) return request<T>(path, init, true);
  }

  if (!res.ok) {
    let code: ApiError["code"] = "INTERNAL_ERROR";
    let message = res.statusText;
    try {
      const body = (await res.json()) as ApiErrorResponse;
      if (body?.error) { code = body.error.code; message = body.error.message; }
    } catch { /* non-JSON error body */ }
    throw new DepthWizardError(code, message, res.status);
  }

  return res.status === 204 ? (undefined as T) : ((await res.json()) as T);
}

/**
 * Client-side file check. A courtesy to save a 50 MB upload, NOT a security
 * boundary — the backend validates by inspecting file contents.
 *
 * Accepts on MIME *or* extension: File.type comes from the OS file-association
 * table and is frequently blank or non-standard for TIFF. A strict MIME check
 * would reject valid GeoTIFFs before the backend ever sees them, silently
 * disabling the absolute-DSM path on some machines (PRD §10.3).
 */
export function validateFile(file: File): { ok: true } | { ok: false; reason: string } {
  if (file.size > MAX_UPLOAD_BYTES) {
    return { ok: false, reason: "File is larger than 50 MB." };
  }
  const mimeOk = (ACCEPTED_MIME as readonly string[]).includes(file.type);
  const extOk = ACCEPTED_EXTENSIONS.some((e) => file.name.toLowerCase().endsWith(e));
  if (mimeOk || (!file.type && extOk) || extOk) return { ok: true };
  return { ok: false, reason: "Use a PNG, JPEG or GeoTIFF image." };
}

// ── Jobs ────────────────────────────────────────────────────────────────────

export async function createJob(file: File): Promise<CreateJobResponse> {
  if (USE_MOCKS) return (await import("../mocks/fixtures")).mockCreateJob();
  const form = new FormData();
  form.append("file", file);           // field name is "file" — PRD §9.5
  return request<CreateJobResponse>("/api/v1/jobs", { method: "POST", body: form });
}

export async function getJob(jobId: string): Promise<JobStatusResponse> {
  if (USE_MOCKS) return (await import("../mocks/fixtures")).mockGetJob(jobId);
  return request<JobStatusResponse>(`/api/v1/jobs/${jobId}`);
}

export async function getJobResult(jobId: string): Promise<JobResult> {
  if (USE_MOCKS) return (await import("../mocks/fixtures")).mockGetResult(jobId);
  return request<JobResult>(`/api/v1/jobs/${jobId}/result`);
}

export async function listJobs(): Promise<JobListResponse> {
  if (USE_MOCKS) return (await import("../mocks/fixtures")).mockListJobs();
  return request<JobListResponse>("/api/v1/jobs");
}

export async function deleteJob(jobId: string): Promise<void> {
  return request<void>(`/api/v1/jobs/${jobId}`, { method: "DELETE" });
}

// ── Comparison (stretch, PRD §9.9) ──────────────────────────────────────────

export async function createCompare(body: CreateCompareRequest) {
  return request<{ compare_id: string; status: string }>("/api/v1/compare", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export async function getCompareResult(compareId: string): Promise<CompareResult> {
  return request<CompareResult>(`/api/v1/compare/${compareId}/result`);
}
