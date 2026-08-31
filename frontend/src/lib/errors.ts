import { JobError } from './types';

export const KnownErrorCodes = {
  AUTH_REQUIRED: 'AUTH_REQUIRED',
  INVALID_TOKEN: 'INVALID_TOKEN',
  FORBIDDEN_JOB: 'FORBIDDEN_JOB',
  JOB_NOT_FOUND: 'JOB_NOT_FOUND',
  JOB_NOT_COMPLETE: 'JOB_NOT_COMPLETE',
  UNSUPPORTED_FILE: 'UNSUPPORTED_FILE',
  FILE_TOO_LARGE: 'FILE_TOO_LARGE',
  INVALID_IMAGE: 'INVALID_IMAGE',
  INVALID_GEOTIFF: 'INVALID_GEOTIFF',
  SRTM_FETCH_FAILED: 'SRTM_FETCH_FAILED',
  CALIBRATION_FAILED: 'CALIBRATION_FAILED',
  ML_INFERENCE_FAILED: 'ML_INFERENCE_FAILED',
  QUEUE_UNAVAILABLE: 'QUEUE_UNAVAILABLE',
  RESULT_STORAGE_FAILED: 'RESULT_STORAGE_FAILED',
  INTERNAL_ERROR: 'INTERNAL_ERROR',
} as const;

export type KnownErrorCode = (typeof KnownErrorCodes)[keyof typeof KnownErrorCodes];

export class ApiException extends Error {
  public readonly code: string;

  constructor(code: string, message: string) {
    super(message);
    this.name = 'ApiException';
    this.code = code;
  }
}

export function parseApiError(data: unknown): JobError {
  if (
    typeof data === 'object' &&
    data !== null &&
    'error' in data &&
    typeof (data as { error: unknown }).error === 'object' &&
    (data as { error: { code?: string; message?: string } }).error !== null
  ) {
    const err = (data as { error: { code?: string; message?: string } }).error;
    return {
      code: err.code || KnownErrorCodes.INTERNAL_ERROR,
      message: err.message || 'An unexpected error occurred.',
    };
  }
  return {
    code: KnownErrorCodes.INTERNAL_ERROR,
    message: 'An unexpected server response was received.',
  };
}

export function getFriendlyErrorMessage(error: JobError | ApiException | Error | unknown): string {
  if (error instanceof ApiException) {
    return error.message;
  }

  if (typeof error === 'object' && error !== null && 'code' in error && 'message' in error) {
    const jobErr = error as JobError;
    return jobErr.message;
  }

  if (error instanceof Error) {
    return error.message;
  }

  return 'An unexpected error occurred. Please try again.';
}
