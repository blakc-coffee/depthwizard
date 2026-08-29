/**
 * DepthWizard API contract types.
 *
 * Generated from PRD §9.5–§9.7. Do NOT hand-edit to make a component compile —
 * if the shape is wrong, the contract is wrong, and that is a cross-team change
 * that must be agreed before merge (PRD §11 shared-repo rules).
 */

// ── Job lifecycle (PRD §9.4) ────────────────────────────────────────────────

export type JobStatus = "queued" | "processing" | "completed" | "failed";

export type JobStage =
  | "loading_input"
  | "estimating_depth"
  | "fetching_reference"
  | "calibrating"
  | "packaging"
  | "validating_output"
  | "uploading_results";

/** Comparisons use a DIFFERENT stage vocabulary (PRD §9.9). Do not reuse the
 *  job-stage label map for these. */
export type CompareStage =
  | "loading_inputs"
  | "aligning"
  | "computing_diff"
  | "packaging"
  | "uploading_results";

// ── Errors (PRD §9.7) ───────────────────────────────────────────────────────

export type ErrorCode =
  | "AUTH_REQUIRED" | "INVALID_TOKEN" | "FORBIDDEN_JOB"
  | "JOB_NOT_FOUND" | "JOB_NOT_COMPLETE"
  | "UNSUPPORTED_FILE" | "FILE_TOO_LARGE" | "INVALID_IMAGE" | "INVALID_GEOTIFF"
  | "SRTM_FETCH_FAILED" | "CALIBRATION_FAILED" | "ML_INFERENCE_FAILED"
  | "QUEUE_UNAVAILABLE" | "RESULT_STORAGE_FAILED" | "INTERNAL_ERROR"
  | "COMPARE_JOB_NOT_ELIGIBLE" | "COMPARE_EXTENT_MISMATCH";

export interface ApiError {
  code: ErrorCode;
  message: string;
}

export interface ApiErrorResponse {
  error: ApiError;
}

// ── Results (PRD §9.6) ──────────────────────────────────────────────────────

/** Authoritative for every UI decision about units and downloads.
 *  NEVER infer this from the uploaded file extension — a GeoTIFF can
 *  legitimately produce a relative result. */
export type OutputType = "absolute_dsm" | "relative_dsm";

export type HeightUnits = "m" | "relative";

export interface JobArtifacts {
  /** Always present on a completed job. Web-renderable RGB, pixel-aligned
   *  to the heightmap, for both PNG/JPG and GeoTIFF inputs. */
  texture_url: string;
  /** Always present. 8-bit grayscale + alpha; alpha carries NoData validity
   *  (255 = valid, 0 = NoData). Render from this, not the 16-bit file. */
  heightmap_url: string;
  /** Optional. For download/analysis only — canvas decoding downconverts
   *  16-bit to 8-bit, so Three.js gains nothing from it. */
  heightmap_16bit_url?: string;
  /** Optional and genuinely so: early ML builds and fallback paths may not
   *  produce one. Hide the confidence toggle when absent. */
  confidence_map_url?: string;
  /** Optional. Absolute results only. */
  dsm_url?: string;
}

export interface JobMetadata {
  height_units: HeightUnits;
  min_height: number;
  max_height: number;
  width: number;
  height: number;
}

export interface JobMetrics {
  rmse: number;
  mae: number;
  correlation: number;
}

export interface JobResult {
  job_id: string;
  output_type: OutputType;
  artifacts: JobArtifacts;
  metadata: JobMetadata;
  /** Explicitly null when no reference elevation exists for the scene — the
   *  normal case for user uploads. Never an empty object, never zeros.
   *  Render an honest "not measurable" state, not a 0.00. */
  metrics: JobMetrics | null;
  /** Must be VISIBLE in the UI, not logged. This is how "we could not
   *  calibrate this reliably" reaches the user. */
  warnings: string[];
}

// ── Job endpoints (PRD §9.5) ────────────────────────────────────────────────

export interface CreateJobResponse {
  job_id: string;
  status: JobStatus;
}

export interface JobStatusResponse {
  job_id: string;
  status: JobStatus;
  stage: JobStage | null;
  /** Integer 0–100, monotonic. */
  progress: number;
  error: ApiError | null;
}

export interface JobSummary {
  job_id: string;
  status: JobStatus;
  /** null until the job completes. */
  output_type: OutputType | null;
  input_filename: string;
  created_at: string;
  completed_at: string | null;
}

export interface JobListResponse {
  jobs: JobSummary[];
}

// ── Comparison, stretch (PRD §9.9) ──────────────────────────────────────────

export interface CreateCompareRequest {
  before_job_id: string;
  after_job_id: string;
}

export interface CompareResult {
  compare_id: string;
  before_job_id: string;
  after_job_id: string;
  artifacts: {
    diff_map_url: string;
    before_texture_url: string;
    after_texture_url: string;
  };
  metadata: {
    height_units: HeightUnits;
    max_loss: number;
    max_gain: number;
    changed_area_fraction: number;
    threshold: number;
  };
  warnings: string[];
}

// ── Benchmarks — model-level, NOT per-scene (PRD §10.6) ─────────────────────

export interface TerrainMetrics extends JobMetrics {
  n: number;
}

/** Shape of src/data/validation_report.json, committed by the ML team.
 *  Measured once on the held-out test split. Says NOTHING about the accuracy
 *  of any user upload — must never share a panel with per-scene metrics. */
export interface ValidationReport {
  generated_at: string;
  test_split_size: number;
  aggregate: JobMetrics;
  per_terrain: {
    urban: TerrainMetrics;
    sparse: TerrainMetrics;
    hilly: TerrainMetrics;
    forested: TerrainMetrics;
  };
  notes?: string;
}

// ── Frontend-local state (PRD §10.5) ────────────────────────────────────────

export type AuthState = "loading" | "authenticated" | "unauthenticated";

/** Independent of OverlayMode. The viewer must be able to be simultaneously
 *  `ready` and showing `confidence`. */
export type ViewerStatus = "loading" | "ready" | "error";

/** Three values. There is deliberately no validation overlay — nothing in the
 *  system produces a per-pixel error map (PRD §10.5). */
export type OverlayMode = "normal" | "slope" | "confidence";

// ── Upload constraints (PRD §9.5) ───────────────────────────────────────────

export const MAX_UPLOAD_BYTES = 50 * 1024 * 1024;

export const ACCEPTED_MIME = ["image/png", "image/jpeg", "image/tiff"] as const;

export const ACCEPTED_EXTENSIONS = [".png", ".jpg", ".jpeg", ".tif", ".tiff"] as const;
