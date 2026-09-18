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
import { analyzeSiltImage, SiltAnalysisResult } from './clientSiltPipeline';
import {
  CompareResultResponse,
  CompareStatusResponse,
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
  mockCompareResult,
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
    hasComparison?: boolean;
    secondaryJobId?: string | null;
    compareId?: string | null;
  }
>();

const mockCompareStore = new Map<string, { startTime: number; beforeJobId: string; afterJobId: string }>();

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
  const hasComparison = Boolean(secondFile);
  const secondaryJobId = hasComparison ? `mock-job-after-${Date.now()}` : null;
  const compareId = hasComparison ? `mock-compare-${Date.now()}` : null;

  mockStateStore.set(jobId, {
    startTime: Date.now(),
    filename: file.name,
    isGeoTIFF,
    hasComparison,
    secondaryJobId,
    compareId,
  });

  if (typeof window !== 'undefined') {
    sessionStorage.setItem(`depthwizard_is_comparison_${jobId}`, hasComparison ? 'true' : 'false');
    if (secondFile) {
      sessionStorage.setItem(`depthwizard_secondary_${jobId}`, JSON.stringify({
        name: secondFile.name,
        size: secondFile.size,
      }));
    } else {
      sessionStorage.removeItem(`depthwizard_secondary_${jobId}`);
    }
  }

  if (!secondFile || !secondaryJobId || !compareId) {
    return {
      job_id: jobId,
      status: 'queued',
    };
  }

  // Register the secondary ("after") job itself too, so getJobResult(after_job_id)
  // — the real compare flow's source for the after job's own heightmap —
  // resolves to something real instead of 404ing in mock mode.
  mockStateStore.set(secondaryJobId, {
    startTime: Date.now(),
    filename: secondFile.name,
    isGeoTIFF: secondFile.name.endsWith('.tif') || secondFile.name.endsWith('.tiff'),
  });
  mockCompareStore.set(compareId, { startTime: Date.now(), beforeJobId: jobId, afterJobId: secondaryJobId });

  return {
    job_id: jobId,
    status: 'queued',
    secondary_job_id: secondaryJobId,
    compare_id: compareId,
  };
}

export async function mockGetCompare(compareId: string): Promise<CompareStatusResponse> {
  const state = mockCompareStore.get(compareId);
  const elapsedMs = state ? Date.now() - state.startTime : Infinity;

  // Mirrors mockGetJob's staged timing, offset later since a real compare
  // only starts once both source jobs finish.
  if (elapsedMs < 3200) {
    return { compare_id: compareId, status: 'queued', stage: 'loading_inputs', progress: 10 };
  }
  if (elapsedMs < 4200) {
    return { compare_id: compareId, status: 'processing', stage: 'computing_diff', progress: 55 };
  }
  return { compare_id: compareId, status: 'completed', stage: 'uploading_results', progress: 100 };
}

export async function mockGetCompareResult(compareId: string): Promise<CompareResultResponse> {
  const state = mockCompareStore.get(compareId);
  return {
    ...mockCompareResult,
    compare_id: compareId,
    before_job_id: state?.beforeJobId ?? mockCompareResult.before_job_id,
    after_job_id: state?.afterJobId ?? mockCompareResult.after_job_id,
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
  const sessionIsComparison = typeof window !== 'undefined'
    ? sessionStorage.getItem(`depthwizard_is_comparison_${jobId}`)
    : null;
  const hasComparison = sessionIsComparison !== null
    ? sessionIsComparison === 'true'
    : (jobState?.hasComparison ?? false);

  if (jobState) {
    const base = jobState.isGeoTIFF ? mockAbsoluteJobResult : mockRelativeJobResult;
    return {
      ...base,
      job_id: jobId,
      metadata: {
        ...base.metadata,
        has_comparison: hasComparison,
        compare_id: jobState.compareId,
        secondary_job_id: jobState.secondaryJobId,
      },
    };
  }

  if (jobId === mockRelativeJobResult.job_id) {
    return {
      ...mockRelativeJobResult,
      metadata: {
        ...mockRelativeJobResult.metadata,
        has_comparison: hasComparison,
      },
    };
  }

  return {
    ...mockAbsoluteJobResult,
    job_id: jobId,
    metadata: {
      ...mockAbsoluteJobResult.metadata,
      has_comparison: hasComparison,
    },
  };
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
const mockSiltStateStore = new Map<
  string,
  {
    startTime: number;
    previewUrl?: string;
    analysis?: SiltAnalysisResult;
  }
>();

export async function mockCreateSiltJob(file: File): Promise<CreateSiltJobResponse> {
  if (file.name.toLowerCase().includes('too_large')) {
    throw new ApiException(KnownErrorCodes.FILE_TOO_LARGE, 'File exceeds the maximum upload limit.');
  }
  const jobId = `mock-silt-job-${Date.now()}`;
  let previewUrl: string | undefined;
  if (typeof window !== 'undefined' && typeof URL !== 'undefined' && URL.createObjectURL) {
    try {
      previewUrl = URL.createObjectURL(file);
      sessionStorage.setItem(`depthwizard_silt_preview_${jobId}`, previewUrl);
    } catch {
      // ignore
    }
  }

  mockSiltStateStore.set(jobId, { startTime: Date.now(), previewUrl });

  // Run dynamic client-side optical analysis on the user's actual image
  if (typeof window !== 'undefined') {
    analyzeSiltImage(file).then((analysis) => {
      const state = mockSiltStateStore.get(jobId);
      if (state) {
        state.analysis = analysis;
      }
      try {
        sessionStorage.setItem(`depthwizard_silt_analysis_${jobId}`, JSON.stringify(analysis));
      } catch {
        // ignore quota limits
      }
    });
  }

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
  // Curated demo fixtures for testing pre-calculated scenes
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

  const storedPreview = typeof window !== 'undefined' ? sessionStorage.getItem(`depthwizard_silt_preview_${jobId}`) : null;
  const inMemoryState = mockSiltStateStore.get(jobId);
  const textureUrl = storedPreview || inMemoryState?.previewUrl || REAL_DEMO_TEXTURE_PNG;

  // Retrieve cached or in-memory analysis computed from the user's uploaded image
  const storedAnalysisJson = typeof window !== 'undefined' ? sessionStorage.getItem(`depthwizard_silt_analysis_${jobId}`) : null;
  let analysis = inMemoryState?.analysis;
  if (!analysis && storedAnalysisJson) {
    try {
      analysis = JSON.parse(storedAnalysisJson);
    } catch {
      // ignore
    }
  }

  if (analysis) {
    return {
      ...mockSiltJobResult,
      job_id: jobId,
      predicted_ssc_mg_l: analysis.predictedSscMgL,
      dredging_level: analysis.dredgingLevel,
      dredging_label: analysis.dredgingLabel,
      artifacts: {
        texture_url: textureUrl,
        heatmap_url: analysis.heatmapUrl || REAL_DEMO_HEATMAP_PNG,
      },
      cross_section_profile: analysis.crossSectionProfile,
    };
  }

  // If not yet analyzed but we have an image URL, perform live analysis on the fly
  if (textureUrl && textureUrl !== REAL_DEMO_TEXTURE_PNG && typeof window !== 'undefined') {
    try {
      const liveAnalysis = await analyzeSiltImage(textureUrl);
      if (inMemoryState) inMemoryState.analysis = liveAnalysis;
      return {
        ...mockSiltJobResult,
        job_id: jobId,
        predicted_ssc_mg_l: liveAnalysis.predictedSscMgL,
        dredging_level: liveAnalysis.dredgingLevel,
        dredging_label: liveAnalysis.dredgingLabel,
        artifacts: {
          texture_url: textureUrl,
          heatmap_url: liveAnalysis.heatmapUrl || REAL_DEMO_HEATMAP_PNG,
        },
        cross_section_profile: liveAnalysis.crossSectionProfile,
      };
    } catch {
      // fall through to default
    }
  }

  return {
    ...mockSiltJobResult,
    job_id: jobId,
    artifacts: {
      texture_url: textureUrl,
      heatmap_url: REAL_DEMO_HEATMAP_PNG,
    },
    cross_section_profile: REAL_DEMO_CROSS_SECTION,
  };
}

export async function mockGetSiltJobs(): Promise<SiltJobListResponse> {
  return { jobs: mockSiltJobsList };
}

export async function mockDeleteSiltJob(jobId: string): Promise<void> {
  mockSiltStateStore.delete(jobId);
}
