import { ApiException, parseApiError } from './errors';
import {
  mockCreateJob,
  mockDeleteJob,
  mockGetJob,
  mockGetJobResult,
  mockGetJobs,
} from './mockApi';
import { supabase } from './supabase';
import {
  CreateJobResponse,
  JobListResponse,
  JobResult,
  JobStatusResponse,
} from './types';

const isMockApi =
  import.meta.env.VITE_USE_MOCK_API === 'true' ||
  !import.meta.env.VITE_SUPABASE_URL ||
  import.meta.env.VITE_SUPABASE_URL.includes('placeholder');

async function getAuthHeader(): Promise<Record<string, string>> {
  try {
    const { data } = await supabase.auth.getSession();
    const token = data.session?.access_token;
    if (!token) {
      return {};
    }
    return {
      Authorization: `Bearer ${token}`,
    };
  } catch {
    return {};
  }
}

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    let errorData: unknown;
    try {
      errorData = await response.json();
    } catch {
      throw new ApiException(
        'HTTP_ERROR',
        `HTTP Error ${response.status}: ${response.statusText}`
      );
    }
    const parsed = parseApiError(errorData);
    throw new ApiException(parsed.code, parsed.message);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}

export async function createJob(file: File): Promise<CreateJobResponse> {
  if (isMockApi) {
    return mockCreateJob(file);
  }

  try {
    const authHeaders = await getAuthHeader();
    const formData = new FormData();
    formData.append('file', file);

    const response = await fetch('/api/v1/jobs', {
      method: 'POST',
      headers: {
        ...authHeaders,
      },
      body: formData,
    });

    return await handleResponse<CreateJobResponse>(response);
  } catch (err) {
    if (err instanceof ApiException) {
      throw err;
    }
    // Fallback to mock API if backend dev server is not reachable
    return mockCreateJob(file);
  }
}

export async function getJob(jobId: string): Promise<JobStatusResponse> {
  if (isMockApi) {
    return mockGetJob(jobId);
  }

  try {
    const authHeaders = await getAuthHeader();
    const response = await fetch(`/api/v1/jobs/${encodeURIComponent(jobId)}`, {
      method: 'GET',
      headers: {
        ...authHeaders,
      },
    });

    return await handleResponse<JobStatusResponse>(response);
  } catch (err) {
    if (err instanceof ApiException) {
      throw err;
    }
    return mockGetJob(jobId);
  }
}

export async function getJobResult(jobId: string): Promise<JobResult> {
  if (isMockApi) {
    return mockGetJobResult(jobId);
  }

  try {
    const authHeaders = await getAuthHeader();
    const response = await fetch(`/api/v1/jobs/${encodeURIComponent(jobId)}/result`, {
      method: 'GET',
      headers: {
        ...authHeaders,
      },
    });

    return await handleResponse<JobResult>(response);
  } catch (err) {
    if (err instanceof ApiException) {
      throw err;
    }
    return mockGetJobResult(jobId);
  }
}

export async function getJobs(): Promise<JobListResponse> {
  if (isMockApi) {
    return mockGetJobs();
  }

  try {
    const authHeaders = await getAuthHeader();
    const response = await fetch('/api/v1/jobs', {
      method: 'GET',
      headers: {
        ...authHeaders,
      },
    });

    return await handleResponse<JobListResponse>(response);
  } catch (err) {
    if (err instanceof ApiException) {
      throw err;
    }
    return mockGetJobs();
  }
}

export async function deleteJob(jobId: string): Promise<void> {
  if (isMockApi) {
    return mockDeleteJob(jobId);
  }

  try {
    const authHeaders = await getAuthHeader();
    const response = await fetch(`/api/v1/jobs/${encodeURIComponent(jobId)}`, {
      method: 'DELETE',
      headers: {
        ...authHeaders,
      },
    });

    return await handleResponse<void>(response);
  } catch (err) {
    if (err instanceof ApiException) {
      throw err;
    }
    return mockDeleteJob(jobId);
  }
}
