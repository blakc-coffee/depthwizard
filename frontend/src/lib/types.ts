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
