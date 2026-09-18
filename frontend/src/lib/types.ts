export type JobStatus = 'queued' | 'processing' | 'completed' | 'failed';

export type JobStage =
  | 'loading_input'
  | 'estimating_depth'
  | 'fetching_reference'
  | 'calibrating'
  | 'packaging'
  | 'validating_output'
  | 'uploading_results';

export type OutputType = 'absolute_dsm' | 'relative_dsm';
export type HeightUnits = 'm' | 'relative';

export interface JobError {
  code: string;
  message: string;
}

export interface ApiErrorResponse {
  error: JobError;
}

export interface CreateJobResponse {
  job_id: string;
  status: JobStatus;
  // Present only when a secondary (comparison) image was uploaded alongside
  // the primary one — backend/app/schemas/jobs.py's response_model_exclude_none
  // omits both otherwise.
  secondary_job_id?: string;
  compare_id?: string;
}

export interface JobStatusResponse {
  job_id: string;
  status: JobStatus;
  stage?: JobStage | null;
  progress?: number | null;
  error?: JobError | null;
}

export interface JobSummary {
  job_id: string;
  status: JobStatus;
  output_type?: OutputType | null;
  input_filename: string;
  created_at: string;
  completed_at?: string | null;
}

export interface JobListResponse {
  jobs: JobSummary[];
}

// River-silt use case — a sibling shape to Job*, not a variant of it (see
// backend/app/db/models.py::SiltJob and docs/phase_river_silt.md).
export type SiltJobStage = 'loading_input' | 'estimating_silt' | 'packaging' | 'uploading_results';
export type SiltOutputType = 'relative_silt_index' | 'absolute_ssc';
export type DredgingLevel = 'low' | 'moderate' | 'high';

export interface CreateSiltJobResponse {
  job_id: string;
  status: JobStatus;
}

export interface SiltJobStatusResponse {
  job_id: string;
  status: JobStatus;
  stage?: SiltJobStage | null;
  progress?: number | null;
  error?: JobError | null;
}

export interface SiltJobArtifacts {
  texture_url: string;
  heatmap_url: string;
}

export interface SiltJobResult {
  job_id: string;
  output_type: SiltOutputType;
  artifacts: SiltJobArtifacts;
  predicted_ssc_mg_l: number;
  dredging_level: DredgingLevel;
  dredging_label: string;
  cross_section_profile: number[];
  warnings: string[];
}

export interface SiltJobSummary {
  job_id: string;
  status: JobStatus;
  output_type?: SiltOutputType | null;
  input_filename: string;
  created_at: string;
  completed_at?: string | null;
}

export interface SiltJobListResponse {
  jobs: SiltJobSummary[];
}

export interface JobArtifacts {
  texture_url: string;
  heightmap_url: string;
  heightmap_16bit_url?: string | null;
  confidence_map_url?: string | null;
  dsm_url?: string | null;
}

export interface JobMetadata {
  height_units: HeightUnits;
  min_height: number;
  max_height: number;
  width: number;
  height: number;
  [key: string]: unknown;
}

export interface JobMetrics {
  rmse: number;
  mae: number;
  correlation: number;
  [key: string]: unknown;
}

export interface JobResult {
  job_id: string;
  output_type: OutputType;
  artifacts: JobArtifacts;
  metadata: JobMetadata;
  metrics: JobMetrics | null;
  warnings: string[];
}

// Comparison (change detection) — backend/app/schemas/compare.py. A separate
// stage vocabulary from Job's: no depth estimation/calibration happens here,
// both source DSMs already exist.
export type CompareStatus = 'queued' | 'processing' | 'completed' | 'failed';
export type CompareStage = 'loading_inputs' | 'aligning' | 'computing_diff' | 'packaging' | 'uploading_results';

export interface CompareStatusResponse {
  compare_id: string;
  status: CompareStatus;
  stage?: CompareStage | null;
  progress?: number | null;
  error?: JobError | null;
}

export interface CompareArtifacts {
  diff_map_url: string;
  before_texture_url: string;
  after_texture_url: string;
}

export interface CompareMetadata {
  height_units: HeightUnits;
  max_loss: number;
  max_gain: number;
  changed_area_fraction: number;
  threshold: number;
}

export interface CompareResultResponse {
  compare_id: string;
  before_job_id: string;
  after_job_id: string;
  artifacts: CompareArtifacts;
  metadata: CompareMetadata;
  warnings: string[];
}
