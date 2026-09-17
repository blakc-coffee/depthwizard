import { JobResult, JobSummary, SiltJobResult, SiltJobSummary } from './types';
import { getSampleTerrain } from '../viewer/sampleTerrainGenerator';

// High-relief procedural 3D DEM dataset generated for sample terrain inspection
const defaultTerrainSample = typeof document !== 'undefined' ? getSampleTerrain('before') : null;

const SAMPLE_TEXTURE_PNG =
  defaultTerrainSample?.textureUrl ||
  'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==';

const SAMPLE_HEIGHTMAP_PNG =
  defaultTerrainSample?.heightmapUrl ||
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

// 1x1 gray PNG — same "instantly decodes anywhere" convention as the
// terrain fixtures above, standing in for the placeholder uniform heatmap
// ml/river_silt_pipeline.py actually produces (see its module docstring).
const SAMPLE_SILT_TEXTURE_PNG = SAMPLE_TEXTURE_PNG;
const SAMPLE_SILT_HEATMAP_PNG =
  'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=';

export const mockSiltJobResult: SiltJobResult = {
  job_id: 'mock-silt-job-1234',
  output_type: 'relative_silt_index',
  artifacts: {
    texture_url: SAMPLE_SILT_TEXTURE_PNG,
    heatmap_url: SAMPLE_SILT_HEATMAP_PNG,
  },
  predicted_ssc_mg_l: 22.3,
  dredging_level: 'moderate',
  dredging_label: 'Monitor — sediment level is mid-range; consider scheduling an inspection.',
  cross_section_profile: [
    0.62, 0.58, 0.51, 0.44, 0.35, 0.27, 0.2, 0.14, 0.09, 0.05, 0.03, 0.02, 0.02, 0.03, 0.05, 0.08,
    0.12, 0.17, 0.23, 0.3, 0.38, 0.46, 0.54, 0.61, 0.67, 0.72, 0.76, 0.78, 0.79, 0.78, 0.76, 0.72,
    0.67, 0.61, 0.55, 0.49, 0.44, 0.4, 0.37, 0.35, 0.34, 0.35, 0.37, 0.41, 0.46, 0.52, 0.58, 0.63,
  ],
  warnings: [
    "The underlying SSC regressor's typical (median) error is a few mg/L on held-out real data, but it cannot detect elevated/flood-condition SSC from a single static image with no temporal context — treat this as a rough estimate for a typical-conditions reading, not a reliable flood/event detector.",
    'Heatmap spatial pattern comes from per-pixel color (NDTI) variation across the whole image, not a verified water mask.',
    'Cross-section shape is derived from real per-pixel image variation and the predicted SSC level, not a measured riverbed survey.',
  ],
};

export const mockSiltJobsList: SiltJobSummary[] = [
  {
    job_id: 'mock-silt-job-1234',
    status: 'completed',
    output_type: 'relative_silt_index',
    input_filename: 'river_reach_042.tif',
    created_at: new Date(Date.now() - 1800000).toISOString(),
    completed_at: new Date(Date.now() - 1700000).toISOString(),
  },
];
