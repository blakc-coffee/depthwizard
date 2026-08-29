/**
 * Mock backend for Frontend Phases 1–5. Set VITE_USE_MOCKS=true.
 *
 * Deliberately exercises the awkward cases, because these are the ones that
 * break in the demo if the UI only ever sees the happy path:
 *   - a relative result from a GeoTIFF upload (warnings present, units "relative")
 *   - metrics === null (no ground truth — the NORMAL case for user uploads)
 *   - confidence_map_url absent (optional artifact)
 */

import type {
  CreateJobResponse, JobStatusResponse, JobResult, JobListResponse, JobStage,
} from "../lib/types";

const STAGES: JobStage[] = [
  "loading_input", "estimating_depth", "fetching_reference",
  "calibrating", "packaging", "validating_output", "uploading_results",
];

const started = new Map<string, number>();
const SIM_MS = 14_000;

export async function mockCreateJob(): Promise<CreateJobResponse> {
  const job_id = `mock-${Math.random().toString(36).slice(2, 10)}`;
  started.set(job_id, Date.now());
  return { job_id, status: "queued" };
}

export async function mockGetJob(job_id: string): Promise<JobStatusResponse> {
  const t0 = started.get(job_id) ?? Date.now();
  const elapsed = Date.now() - t0;
  const pct = Math.min(100, Math.floor((elapsed / SIM_MS) * 100));

  if (pct === 0) return { job_id, status: "queued", stage: null, progress: 0, error: null };
  if (pct >= 100) return { job_id, status: "completed", stage: null, progress: 100, error: null };

  return {
    job_id,
    status: "processing",
    stage: STAGES[Math.min(STAGES.length - 1, Math.floor((pct / 100) * STAGES.length))],
    progress: pct,
    error: null,
  };
}

/** Absolute result: metric units, DSM download, confidence map present. */
export const MOCK_ABSOLUTE: JobResult = {
  job_id: "mock-absolute",
  output_type: "absolute_dsm",
  artifacts: {
    texture_url: "/mocks/texture.png",
    heightmap_url: "/mocks/heightmap.png",
    heightmap_16bit_url: "/mocks/heightmap_16bit.png",
    confidence_map_url: "/mocks/confidence.png",
    dsm_url: "/mocks/dsm.tif",
  },
  metadata: { height_units: "m", min_height: 182.4, max_height: 251.7, width: 1024, height: 1024 },
  metrics: null,
  warnings: [],
};

/** Relative fallback FROM A GEOTIFF. The UI must not label this in metres,
 *  must show the warning, and must hide the DSM download. */
export const MOCK_RELATIVE_FALLBACK: JobResult = {
  job_id: "mock-relative",
  output_type: "relative_dsm",
  artifacts: {
    texture_url: "/mocks/texture.png",
    heightmap_url: "/mocks/heightmap.png",
    // no confidence_map_url — hide the toggle, don't error
    // no dsm_url — hide the download
  },
  metadata: { height_units: "relative", min_height: 0, max_height: 1, width: 1024, height: 1024 },
  metrics: null,
  warnings: ["Calibration confidence below threshold; returning relative heights."],
};

/** Rare: a benchmark scene that genuinely has ground truth. */
export const MOCK_WITH_METRICS: JobResult = {
  ...MOCK_ABSOLUTE,
  job_id: "mock-metrics",
  metrics: { rmse: 6.1, mae: 4.8, correlation: 0.91 },
};

export async function mockGetResult(job_id: string): Promise<JobResult> {
  if (job_id.includes("relative")) return { ...MOCK_RELATIVE_FALLBACK, job_id };
  if (job_id.includes("metrics"))  return { ...MOCK_WITH_METRICS, job_id };
  return { ...MOCK_ABSOLUTE, job_id };
}

export async function mockListJobs(): Promise<JobListResponse> {
  return {
    jobs: [
      { job_id: "mock-absolute", status: "completed", output_type: "absolute_dsm",
        input_filename: "chennai_liss4.tif", created_at: "2026-08-29T10:14:00Z", completed_at: "2026-08-29T10:16:32Z" },
      { job_id: "mock-relative", status: "completed", output_type: "relative_dsm",
        input_filename: "site_survey.png", created_at: "2026-08-28T09:02:00Z", completed_at: "2026-08-28T09:04:11Z" },
      { job_id: "mock-failed",   status: "failed",    output_type: null,
        input_filename: "corrupt.tif", created_at: "2026-08-27T18:40:00Z", completed_at: null },
    ],
  };
}
