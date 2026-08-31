import { JobResult, JobSummary } from './types';

export const mockAbsoluteJobResult: JobResult = {
  job_id: 'mock-absolute-job-1234',
  output_type: 'absolute_dsm',
  artifacts: {
    texture_url: 'https://images.unsplash.com/photo-1506744038136-46273834b3fb?w=800&auto=format&fit=crop',
    heightmap_url: 'https://images.unsplash.com/photo-1579546929518-9e396f3cc809?w=800&auto=format&fit=crop',
    heightmap_16bit_url: null,
    confidence_map_url: 'https://images.unsplash.com/photo-1550684848-fac1c5b4e853?w=800&auto=format&fit=crop',
    dsm_url: 'https://example.com/downloads/mock_absolute_dsm.tif',
  },
  metadata: {
    height_units: 'm',
    min_height: 182.4,
    max_height: 251.7,
    sensor: 'Aerial RGB',
    calibration_source: 'SRTM30',
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
    texture_url: 'https://images.unsplash.com/photo-1506744038136-46273834b3fb?w=800&auto=format&fit=crop',
    heightmap_url: 'https://images.unsplash.com/photo-1579546929518-9e396f3cc809?w=800&auto=format&fit=crop',
    heightmap_16bit_url: null,
    confidence_map_url: null,
    dsm_url: null,
  },
  metadata: {
    height_units: 'relative',
    min_height: 0.0,
    max_height: 1.0,
  },
  metrics: null,
  warnings: ['SRTM reference fetch failed; output uncalibrated relative DSM.'],
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
