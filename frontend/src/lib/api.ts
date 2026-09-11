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

export const isMockApi =
  import.meta.env.VITE_USE_MOCK_API === 'true' ||
  !import.meta.env.VITE_SUPABASE_URL ||
  import.meta.env.VITE_SUPABASE_URL.includes('placeholder') ||
  (typeof window !== 'undefined' && localStorage.getItem('depthwizard_mock_session') !== null);

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/+$/, '');

export function buildApiUrl(endpoint: string): string {
  const path = endpoint.startsWith('/') ? endpoint : `/${endpoint}`;
  // On Vercel deployments, use same-origin relative path to leverage the vercel.json
  // reverse proxy rewrite directly to Northflank, completely avoiding cross-origin preflight (OPTIONS) errors
  if (typeof window !== 'undefined' && window.location.hostname.endsWith('vercel.app')) {
    return path;
  }
  return API_BASE_URL ? `${API_BASE_URL}${path}` : path;
}

export async function getAuthHeader(): Promise<Record<string, string>> {
  try {
    const { data, error } = await supabase.auth.getSession();
    if (error) {
      console.warn('Supabase getSession error:', error.message);
      return {};
    }
    const token = data.session?.access_token;
    if (token) {
      return {
        Authorization: `Bearer ${token}`,
      };
    }
  } catch (err) {
    console.warn('Unexpected error retrieving auth session:', err);
  }
  return {};
}

function formatNetworkError(err: unknown): ApiException {
  if (err instanceof ApiException) {
    return err;
  }
  const message = err instanceof Error ? err.message : String(err);
  if (
    message.includes('Failed to fetch') ||
    message.includes('NetworkError') ||
    message.includes('Load failed') ||
    message.includes('ECONNREFUSED')
  ) {
    return new ApiException(
      'NETWORK_ERROR',
      'Unable to connect to the backend server. The service may be waking up (e.g. Render cold start) or unreachable. Please try again shortly.'
    );
  }
  return new ApiException(
    'NETWORK_ERROR',
    message || 'Network error connecting to backend service.'
  );
}

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    if (response.status === 502 || response.status === 503 || response.status === 504) {
      throw new ApiException(
        'SERVER_UNAVAILABLE',
        `Backend server is waking up or temporarily unavailable (HTTP ${response.status}). If using a free tier host (e.g. Render cold start), please wait 30-60 seconds and retry.`
      );
    }

    let errorData: unknown;
    try {
      errorData = await response.json();
    } catch {
      throw new ApiException(
        'HTTP_ERROR',
        `HTTP Error ${response.status}: ${response.statusText || 'Unknown server response'}`
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

    const response = await fetch(buildApiUrl('/api/v1/jobs'), {
      method: 'POST',
      headers: {
        ...authHeaders,
      },
      body: formData,
    });

    return await handleResponse<CreateJobResponse>(response);
  } catch (err) {
    throw formatNetworkError(err);
  }
}

export async function getJob(jobId: string): Promise<JobStatusResponse> {
  if (isMockApi || jobId.startsWith('mock-')) {
    return mockGetJob(jobId);
  }

  try {
    const authHeaders = await getAuthHeader();
    const response = await fetch(buildApiUrl(`/api/v1/jobs/${encodeURIComponent(jobId)}`), {
      method: 'GET',
      headers: {
        Accept: 'application/json',
        ...authHeaders,
      },
    });

    return await handleResponse<JobStatusResponse>(response);
  } catch (err) {
    throw formatNetworkError(err);
  }
}

export async function getJobResult(jobId: string): Promise<JobResult> {
  if (isMockApi || jobId.startsWith('mock-')) {
    return mockGetJobResult(jobId);
  }

  try {
    const authHeaders = await getAuthHeader();
    const response = await fetch(buildApiUrl(`/api/v1/jobs/${encodeURIComponent(jobId)}/result`), {
      method: 'GET',
      headers: {
        Accept: 'application/json',
        ...authHeaders,
      },
    });

    return await handleResponse<JobResult>(response);
  } catch (err) {
    throw formatNetworkError(err);
  }
}

export async function getJobs(): Promise<JobListResponse> {
  if (isMockApi) {
    return mockGetJobs();
  }

  try {
    const authHeaders = await getAuthHeader();
    const response = await fetch(buildApiUrl('/api/v1/jobs'), {
      method: 'GET',
      headers: {
        Accept: 'application/json',
        ...authHeaders,
      },
    });

    return await handleResponse<JobListResponse>(response);
  } catch (err) {
    throw formatNetworkError(err);
  }
}

export async function deleteJob(jobId: string): Promise<void> {
  if (isMockApi) {
    return mockDeleteJob(jobId);
  }

  try {
    const authHeaders = await getAuthHeader();
    const response = await fetch(buildApiUrl(`/api/v1/jobs/${encodeURIComponent(jobId)}`), {
      method: 'DELETE',
      headers: {
        ...authHeaders,
      },
    });

    return await handleResponse<void>(response);
  } catch (err) {
    throw formatNetworkError(err);
  }
}
