/** Error code -> user-facing copy, plus recoverability (PRD §9.7, §10.2). */

import type { ErrorCode } from "./types";

interface ErrorCopy {
  title: string;
  detail: string;
  /** true  -> the user can fix this themselves; offer re-upload.
   *  false -> system-side; offer retry or support text. */
  userRecoverable: boolean;
}

export const ERROR_COPY: Record<ErrorCode, ErrorCopy> = {
  AUTH_REQUIRED:    { title: "Please sign in",        detail: "You need to be signed in to do that.", userRecoverable: true },
  INVALID_TOKEN:    { title: "Session expired",       detail: "Please sign in again.", userRecoverable: true },
  FORBIDDEN_JOB:    { title: "Not available",         detail: "This job belongs to another account.", userRecoverable: false },
  JOB_NOT_FOUND:    { title: "Job not found",         detail: "It may have been deleted.", userRecoverable: false },
  JOB_NOT_COMPLETE: { title: "Still processing",      detail: "Results aren't ready yet.", userRecoverable: false },

  UNSUPPORTED_FILE: { title: "Unsupported file type", detail: "Upload a PNG, JPEG or GeoTIFF image.", userRecoverable: true },
  FILE_TOO_LARGE:   { title: "File too large",        detail: "The maximum upload size is 50 MB.", userRecoverable: true },
  INVALID_IMAGE:    { title: "Couldn't read image",   detail: "The file may be corrupted. Try another.", userRecoverable: true },
  INVALID_GEOTIFF:  { title: "Invalid GeoTIFF",       detail: "Geospatial metadata couldn't be read. A plain PNG/JPG will still produce a relative result.", userRecoverable: true },

  SRTM_FETCH_FAILED:  { title: "Elevation data unavailable", detail: "Reference elevation couldn't be fetched. Try again shortly.", userRecoverable: false },
  CALIBRATION_FAILED: { title: "Calibration failed",         detail: "Heights couldn't be calibrated to metres for this scene.", userRecoverable: false },
  ML_INFERENCE_FAILED:{ title: "Processing failed",          detail: "The model couldn't process this image.", userRecoverable: false },

  QUEUE_UNAVAILABLE:    { title: "Service busy",       detail: "Processing is unavailable right now. Try again shortly.", userRecoverable: false },
  RESULT_STORAGE_FAILED:{ title: "Couldn't save results", detail: "Results were generated but couldn't be stored.", userRecoverable: false },
  INTERNAL_ERROR:       { title: "Something went wrong", detail: "An unexpected error occurred.", userRecoverable: false },

  COMPARE_JOB_NOT_ELIGIBLE: { title: "Can't compare these", detail: "Both jobs must be finished successfully.", userRecoverable: true },
  COMPARE_EXTENT_MISMATCH:  { title: "Areas don't overlap", detail: "These two images cover different places.", userRecoverable: true },
};

/** Human-readable stage labels. Jobs only — comparisons use their own set. */
export const STAGE_LABELS: Record<string, string> = {
  loading_input:     "Loading image",
  estimating_depth:  "Estimating depth",
  fetching_reference:"Fetching elevation reference",
  calibrating:       "Calibrating heights",
  packaging:         "Packaging results",
  validating_output: "Validating output",
  uploading_results: "Uploading results",
};

/** Comparison stages are a SEPARATE vocabulary (PRD §9.9). */
export const COMPARE_STAGE_LABELS: Record<string, string> = {
  loading_inputs:    "Loading both scenes",
  aligning:          "Aligning scenes",
  computing_diff:    "Computing change map",
  packaging:         "Packaging results",
  uploading_results: "Uploading results",
};
