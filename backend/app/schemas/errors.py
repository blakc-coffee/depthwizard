"""Error envelope schemas.

Owner: Backend Engineer A. See PRD §9.
"""

from __future__ import annotations

from pydantic import BaseModel

from app.core.errors import ErrorCode


class ApiError(BaseModel):
    code: ErrorCode
    message: str


class ApiErrorResponse(BaseModel):
    error: ApiError
