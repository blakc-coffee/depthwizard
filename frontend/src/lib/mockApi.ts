import { ApiException, KnownErrorCodes } from './errors';
import {
  REAL_DEMO_CROSS_SECTION,
  REAL_DEMO_HEATMAP_PNG,
  REAL_DEMO_TEXTURE_PNG,
} from './realSiltDemoFixture';
import {
  REAL_DEMO_2_CROSS_SECTION,
  REAL_DEMO_2_HEATMAP_PNG,
  REAL_DEMO_2_TEXTURE_PNG,
} from './realSiltDemoFixture2';
import {
  REAL_DEMO_3_CROSS_SECTION,
  REAL_DEMO_3_HEATMAP_PNG,
  REAL_DEMO_3_TEXTURE_PNG,
} from './realSiltDemoFixture3';
import {
  CreateJobResponse,
  CreateSiltJobResponse,
  JobListResponse,
  JobResult,
  JobStatusResponse,
  SiltJobListResponse,
  SiltJobResult,
  SiltJobStatusResponse,
} from './types';
import {
  mockAbsoluteJobResult,
  mockJobsList,
  mockRelativeJobResult,
  mockSiltJobResult,
  mockSiltJobsList,
} from './mockFixtures';

const mockStateStore = new Map<
  string,
  {
    startTime: number;
    filename: string;
    isGeoTIFF: boolean;
  }
>();

export async function mockCreateJob(file: File, secondFile?: File | null): Promise<CreateJobResponse> {
  if (file.name.toLowerCase().includes('too_large') || secondFile?.name.toLowerCase().includes('too_large')) {
    throw new ApiException(
      KnownErrorCodes.FILE_TOO_LARGE,
      'File exceeds the maximum upload limit.'
    );
  }

  const isFailedTest = file.name.toLowerCase().includes('corrupt') || file.name.toLowerCase().includes('failed');
  const jobId = isFailedTest ? `mock-failed-job-${Date.now()}` : `mock-job-${Date.now()}`;
  const isGeoTIFF = file.name.endsWith('.tif') || file.name.endsWith('.tiff');

  mockStateStore.set(jobId, {
    startTime: Date.now(),
    filename: file.name,
    isGeoTIFF,
  });

  if (typeof window !== 'undefined' && secondFile) {
    sessionStorage.setItem(`depthwizard_secondary_${jobId}`, JSON.stringify({
      name: secondFile.name,
      size: secondFile.size,
    }));
  }

  return {
    job_id: jobId,
    status: 'queued',
  };
}

export async function mockGetJob(jobId: string): Promise<JobStatusResponse> {
  if (jobId.includes('failed')) {
    return {
      job_id: jobId,
      status: 'failed',
      stage: 'calibrating',
      progress: 45,
      error: {
        code: KnownErrorCodes.CALIBRATION_FAILED,
        message: 'SRTM reference elevation fetch failed for input coordinates.',
      },
    };
  }

  if (jobId.includes('queued')) {
    return {
      job_id: jobId,
      status: 'queued',
      stage: 'loading_input',
      progress: 10,
    };
  }

  if (jobId.includes('processing')) {
    return {
      job_id: jobId,
      status: 'processing',
      stage: 'estimating_depth',
      progress: 40,
    };
  }

  const jobState = mockStateStore.get(jobId);

  if (!jobState) {
    // Default fallback for pre-seeded mock IDs
    if (jobId === mockAbsoluteJobResult.job_id || jobId === mockRelativeJobResult.job_id) {
      return {
        job_id: jobId,
        status: 'completed',
        stage: 'uploading_results',
        progress: 100,
      };
    }
    return {
      job_id: jobId,
      status: 'completed',
      stage: 'uploading_results',
      progress: 100,
    };
  }

  const elapsedMs = Date.now() - jobState.startTime;

  if (elapsedMs < 800) {
    return {
      job_id: jobId,
      status: 'queued',
      stage: 'loading_input',
      progress: 10,
    };
  } else if (elapsedMs < 1800) {
    return {
      job_id: jobId,
      status: 'processing',
      stage: 'estimating_depth',
      progress: 40,
    };
  } else if (elapsedMs < 2800) {
    return {
      job_id: jobId,
      status: 'processing',
      stage: jobState.isGeoTIFF ? 'calibrating' : 'packaging',
      progress: 75,
    };
  }

  return {
    job_id: jobId,
    status: 'completed',
    stage: 'uploading_results',
    progress: 100,
  };
}

export async function mockGetJobResult(jobId: string): Promise<JobResult> {
  const jobState = mockStateStore.get(jobId);

  if (jobState) {
    if (jobState.isGeoTIFF) {
      return {
        ...mockAbsoluteJobResult,
        job_id: jobId,
      };
    }
    return {
      ...mockRelativeJobResult,
      job_id: jobId,
    };
  }

  if (jobId === mockRelativeJobResult.job_id) {
    return mockRelativeJobResult;
  }

  return mockAbsoluteJobResult;
}

export async function mockGetJobs(): Promise<JobListResponse> {
  return {
    jobs: mockJobsList,
  };
}

export async function mockDeleteJob(jobId: string): Promise<void> {
  mockStateStore.delete(jobId);
}

// River-silt mock endpoints — simpler than the terrain mocks above (one
// output shape, no GeoTIFF/relative branching) since the real pipeline
// itself only has one placeholder path right now (ml/river_silt_pipeline.py).
const mockSiltStateStore = new Map<string, { startTime: number }>();

export async function mockCreateSiltJob(file: File): Promise<CreateSiltJobResponse> {
  if (file.name.toLowerCase().includes('too_large')) {
    throw new ApiException(KnownErrorCodes.FILE_TOO_LARGE, 'File exceeds the maximum upload limit.');
  }
  const jobId = `mock-silt-job-${Date.now()}`;
  mockSiltStateStore.set(jobId, { startTime: Date.now() });
  return { job_id: jobId, status: 'queued' };
}

export async function mockGetSiltJob(jobId: string): Promise<SiltJobStatusResponse> {
  const jobState = mockSiltStateStore.get(jobId);
  if (!jobState) {
    return { job_id: jobId, status: 'completed', stage: 'uploading_results', progress: 100 };
  }

  const elapsedMs = Date.now() - jobState.startTime;
  if (elapsedMs < 800) {
    return { job_id: jobId, status: 'queued', stage: 'loading_input', progress: 10 };
  } else if (elapsedMs < 1800) {
    return { job_id: jobId, status: 'processing', stage: 'estimating_silt', progress: 50 };
  }
  return { job_id: jobId, status: 'completed', stage: 'uploading_results', progress: 100 };
}

export async function mockGetSiltJobResult(jobId: string): Promise<SiltJobResult> {
  // Dev-only: real pipeline output on test_input_river_silt.tif, not the
  // 1x1 placeholder images — visit /silt-results/real-demo to sanity-check
  // actual heatmap/cross-section rendering. See realSiltDemoFixture.ts.
  if (jobId === 'real-demo') {
    return {
      ...mockSiltJobResult,
      job_id: jobId,
      predicted_ssc_mg_l: 1.31,
      dredging_level: 'low',
      dredging_label: 'No dredging indicated — sediment level is in the lower third of observed rivers.',
      artifacts: {
        texture_url: REAL_DEMO_TEXTURE_PNG,
        heatmap_url: REAL_DEMO_HEATMAP_PNG,
      },
      cross_section_profile: REAL_DEMO_CROSS_SECTION,
    };
  }
  if (jobId === 'real-demo-2') {
    return {
      ...mockSiltJobResult,
      job_id: jobId,
      predicted_ssc_mg_l: 17.72,
      dredging_level: 'moderate',
      dredging_label: 'Monitor — sediment level is mid-range; consider scheduling an inspection.',
      artifacts: {
        texture_url: REAL_DEMO_2_TEXTURE_PNG,
        heatmap_url: REAL_DEMO_2_HEATMAP_PNG,
      },
      cross_section_profile: REAL_DEMO_2_CROSS_SECTION,
    };
  }
  if (jobId === 'real-demo-3') {
    return {
      ...mockSiltJobResult,
      job_id: jobId,
      predicted_ssc_mg_l: 3.93,
      dredging_level: 'low',
      dredging_label: 'No dredging indicated — sediment level is in the lower third of observed rivers.',
      artifacts: {
        texture_url: REAL_DEMO_3_TEXTURE_PNG,
        heatmap_url: REAL_DEMO_3_HEATMAP_PNG,
      },
      cross_section_profile: REAL_DEMO_3_CROSS_SECTION,
    };
  }
  return { ...mockSiltJobResult, job_id: jobId };
}

export async function mockGetSiltJobs(): Promise<SiltJobListResponse> {
  return { jobs: mockSiltJobsList };
}

export async function mockDeleteSiltJob(jobId: string): Promise<void> {
  mockSiltStateStore.delete(jobId);
}
