"""FastAPI app factory (PRD §9.5).

Owner: Backend Engineer A. See PRD §9.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded

from app.core.body_limit import MaxBodySizeMiddleware
from app.core.config import get_settings
from app.core.errors import ApiException, ErrorCode
from app.core.logging import configure_logging
from app.core.rate_limit import limiter
from app.routes import health, jobs, silt_jobs

configure_logging()
logger = logging.getLogger("depthwizard.api")

app = FastAPI(title="DepthWizard API")

settings = get_settings()
# Added before CORS so CORS wraps it — a browser needs CORS headers on the
# 413 to read it. The 1 MiB of slack covers multipart framing overhead.
app.add_middleware(
    MaxBodySizeMiddleware,
    max_body_bytes=settings.max_upload_bytes + 1024 * 1024,
    max_upload_mb=settings.max_upload_mb,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.state.limiter = limiter

app.include_router(health.router)
app.include_router(jobs.router)
app.include_router(silt_jobs.router)
# routes/compare.py is mounted here once B7 starts (PRD §9.10 B7) — it's a
# stub today, not a router yet.


@app.exception_handler(ApiException)
def handle_api_exception(request: Request, exc: ApiException) -> JSONResponse:
    return JSONResponse(status_code=exc.http_status, content=exc.to_envelope())


@app.exception_handler(RateLimitExceeded)
def handle_rate_limit_exceeded(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    fallback = ApiException(ErrorCode.RATE_LIMITED, f"Rate limit exceeded: {exc.detail}")
    return JSONResponse(status_code=fallback.http_status, content=fallback.to_envelope())


@app.exception_handler(Exception)
def handle_unexpected_exception(request: Request, exc: Exception) -> JSONResponse:
    # Never return a raw stack trace to the client (PRD §9.2/§11) — but do
    # log it server-side, since the client only sees a generic message.
    logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
    fallback = ApiException(ErrorCode.INTERNAL_ERROR, "An unexpected error occurred.")
    return JSONResponse(status_code=fallback.http_status, content=fallback.to_envelope())
