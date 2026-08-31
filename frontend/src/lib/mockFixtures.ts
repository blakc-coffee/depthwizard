import { JobResult, JobSummary } from './types';

// Valid 1x1 base64 PNG Data URIs that decode instantly in all browser environments
const SAMPLE_TEXTURE_PNG =
  'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==';

const SAMPLE_HEIGHTMAP_PNG =
  'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==';

export const mockAbsoluteJobResult: JobResult = {
  job_id: 'mock-absolute-job-1234',
  output_type: 'absolute_dsm',
  artifacts: {
    texture_url: SAMPLE_TEXTURE_PNG,
    heightmap_url: SAMPLE_HEIGHTMAP_PNG,
    heightmap_16bit_url: null,
    confidence_map_url: null,
    dsm_url: 'https://example.com/downloads/mock_absolute_dsm.tif',
  },
  metadata: {
    height_units: 'm',
    min_height: 0.0,
    max_height: 69.3,
    width: 256,
    height: 256,
  },
  metrics: {
    rmse: 6.1,
    mae: 4.8,
    correlation: 0.91,
  },
  warnings: [],
};

export const mockRelativeJobResult: JobResult = {
  job_id: 'mock-relative-job-5678',
  output_type: 'relative_dsm',
  artifacts: {
    texture_url: SAMPLE_TEXTURE_PNG,
    heightmap_url: SAMPLE_HEIGHTMAP_PNG,
    heightmap_16bit_url: null,
    confidence_map_url: null,
    dsm_url: null,
  },
  metadata: {
    height_units: 'relative',
    min_height: 0.0,
    max_height: 255.0,
    width: 256,
    height: 256,
  },
  metrics: null,
  warnings: [
    'No geo-metadata on this input — SRTM was never attempted, output is uncalibrated relative depth.',
  ],
};

export const mockJobsList: JobSummary[] = [
  {
    job_id: 'mock-absolute-job-1234',
    status: 'completed',
    output_type: 'absolute_dsm',
    input_filename: 'sample_terrain_geotiff.tif',
    created_at: new Date(Date.now() - 3600000).toISOString(),
    completed_at: new Date(Date.now() - 3500000).toISOString(),
  },
  {
    job_id: 'mock-relative-job-5678',
    status: 'completed',
    output_type: 'relative_dsm',
    input_filename: 'aerial_photo.png',
    created_at: new Date(Date.now() - 7200000).toISOString(),
    completed_at: new Date(Date.now() - 7100000).toISOString(),
  },
];
