"""Error codes and response envelope (PRD §9.7).

Owner: Backend Engineer A. See PRD §9.
"""

from __future__ import annotations

from enum import StrEnum
from http import HTTPStatus


class ErrorCode(StrEnum):
    # Auth / ownership
    AUTH_REQUIRED = "AUTH_REQUIRED"
    INVALID_TOKEN = "INVALID_TOKEN"
    FORBIDDEN_JOB = "FORBIDDEN_JOB"
    JOB_NOT_FOUND = "JOB_NOT_FOUND"
    JOB_NOT_COMPLETE = "JOB_NOT_COMPLETE"

    # Input validation
    UNSUPPORTED_FILE = "UNSUPPORTED_FILE"
    FILE_TOO_LARGE = "FILE_TOO_LARGE"
    INVALID_IMAGE = "INVALID_IMAGE"
    INVALID_GEOTIFF = "INVALID_GEOTIFF"

    # ML
    SRTM_FETCH_FAILED = "SRTM_FETCH_FAILED"
    CALIBRATION_FAILED = "CALIBRATION_FAILED"
    ML_INFERENCE_FAILED = "ML_INFERENCE_FAILED"

    # Infrastructure
    QUEUE_UNAVAILABLE = "QUEUE_UNAVAILABLE"
    RESULT_STORAGE_FAILED = "RESULT_STORAGE_FAILED"
    INTERNAL_ERROR = "INTERNAL_ERROR"
    RATE_LIMITED = "RATE_LIMITED"

    # Comparison (stretch, PRD §9.9 — begins only after B6 is stable)
    COMPARE_JOB_NOT_ELIGIBLE = "COMPARE_JOB_NOT_ELIGIBLE"
    COMPARE_EXTENT_MISMATCH = "COMPARE_EXTENT_MISMATCH"


# HTTP status per code. Never a bare 500 with a stack trace attached (§9.2/§11)
# — the global handler in main.py always emits the §9.7 envelope instead.
_HTTP_STATUS: dict[ErrorCode, HTTPStatus] = {
    ErrorCode.AUTH_REQUIRED: HTTPStatus.UNAUTHORIZED,
    ErrorCode.INVALID_TOKEN: HTTPStatus.UNAUTHORIZED,
    ErrorCode.FORBIDDEN_JOB: HTTPStatus.FORBIDDEN,
    ErrorCode.JOB_NOT_FOUND: HTTPStatus.NOT_FOUND,
    ErrorCode.JOB_NOT_COMPLETE: HTTPStatus.CONFLICT,
    ErrorCode.UNSUPPORTED_FILE: HTTPStatus.BAD_REQUEST,
    ErrorCode.FILE_TOO_LARGE: HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
    ErrorCode.INVALID_IMAGE: HTTPStatus.BAD_REQUEST,
    ErrorCode.INVALID_GEOTIFF: HTTPStatus.BAD_REQUEST,
    ErrorCode.SRTM_FETCH_FAILED: HTTPStatus.BAD_GATEWAY,
    ErrorCode.CALIBRATION_FAILED: HTTPStatus.BAD_GATEWAY,
    ErrorCode.ML_INFERENCE_FAILED: HTTPStatus.BAD_GATEWAY,
    ErrorCode.QUEUE_UNAVAILABLE: HTTPStatus.SERVICE_UNAVAILABLE,
    ErrorCode.RESULT_STORAGE_FAILED: HTTPStatus.BAD_GATEWAY,
    ErrorCode.INTERNAL_ERROR: HTTPStatus.INTERNAL_SERVER_ERROR,
    ErrorCode.RATE_LIMITED: HTTPStatus.TOO_MANY_REQUESTS,
    ErrorCode.COMPARE_JOB_NOT_ELIGIBLE: HTTPStatus.CONFLICT,
    ErrorCode.COMPARE_EXTENT_MISMATCH: HTTPStatus.UNPROCESSABLE_ENTITY,
}

# Deterministic failures — never retry (PRD §9.7: "Retrying these burns GPU
# time without changing the outcome"). Everything else may be retried with
# bounded attempts and backoff by the Celery task.
NON_RETRYABLE_CODES = frozenset(
    {
        ErrorCode.UNSUPPORTED_FILE,
        ErrorCode.FILE_TOO_LARGE,
        ErrorCode.INVALID_IMAGE,
        ErrorCode.INVALID_GEOTIFF,
        ErrorCode.CALIBRATION_FAILED,
        ErrorCode.ML_INFERENCE_FAILED,
    }
)


class ApiException(Exception):
    """Raised anywhere in a request or task path; the global handler in
    main.py turns this into the §9.7 envelope. Never let a raw exception
    reach the client."""

    def __init__(self, code: ErrorCode, message: str):
        self.code = code
        self.message = message
        self.http_status = int(_HTTP_STATUS[code])
        super().__init__(message)

    def to_envelope(self) -> dict:
        return {"error": {"code": self.code.value, "message": self.message}}
