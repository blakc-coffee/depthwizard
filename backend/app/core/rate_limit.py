"""Rate limiting: per-user request throttling.

Owner: Backend Engineer A. See PRD §9.

Added post-security-review: POST /api/v1/jobs triggers real GPU/CPU-consuming
ML inference and an external SRTM API call, with no cap on how often one
account can trigger it. Keyed by the authenticated user's id when available
(set on request.state by auth/dependencies.py), falling back to client IP
for requests that never get that far (e.g. a missing/invalid token).

Backed by the same Redis Celery already uses. This is a different kind of
use than the "Redis is Celery broker only, never job status" rule guards
against — that rule is specifically about not using Redis as a second,
possibly-inconsistent source of truth for JOB STATE. Rate-limit counters
are ephemeral request-throttling data, not business state, and Redis is
the standard tool for exactly this.
"""

from __future__ import annotations

from slowapi import Limiter
from slowapi.util import get_remote_address
from starlette.requests import Request

from app.core.config import get_settings


def rate_limit_key(request: Request) -> str:
    user_id = getattr(request.state, "user_id", None)
    return f"user:{user_id}" if user_id else f"ip:{get_remote_address(request)}"


limiter = Limiter(
    key_func=rate_limit_key,
    storage_uri=get_settings().redis_url.get_secret_value(),
    default_limits=["100/minute"],
)
