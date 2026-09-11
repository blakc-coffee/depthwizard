import { ApiException, KnownErrorCodes } from './errors';
import {
  CreateJobResponse,
  JobListResponse,
  JobResult,
  JobStatusResponse,
} from './types';
import { mockAbsoluteJobResult, mockJobsList, mockRelativeJobResult } from './mockFixtures';

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
