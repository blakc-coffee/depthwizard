"""Comparison endpoints (PRD §9.9).

Owner: Backend Engineer A. See PRD §9.

The user picks two of their own already-completed jobs; nothing is
re-processed here, so this reads their stored artifacts only.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user_id
from app.core.errors import ApiException, ErrorCode
from app.core.rate_limit import limiter
from app.db.session import get_db
from app.schemas.compare import (
    CompareArtifacts,
    CompareMetadata,
    CompareResultResponse,
    CompareStatusResponse,
    CreateCompareRequest,
    CreateCompareResponse,
)
from app.schemas.errors import ApiError
from app.services import storage
from app.services.compares import CompareService
from app.services.jobs import JobService
from app.tasks.compare_images import compare_images

router = APIRouter(prefix="/api/v1/compare", tags=["compare"])


@router.post("", status_code=202, response_model=CreateCompareResponse)
@limiter.limit("20/hour")
def create_compare(
    request: Request,
    body: CreateCompareRequest,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> CreateCompareResponse:
    if body.before_job_id == body.after_job_id:
        raise ApiException(ErrorCode.COMPARE_JOB_NOT_ELIGIBLE, "A comparison needs two different jobs.")

    jobs = JobService(db)
    # Ownership of BOTH jobs is verified before anything is queued (PRD §9.9).
    sources = [jobs.get_owned(job_id=body.before_job_id, user_id=user_id), jobs.get_owned(job_id=body.after_job_id, user_id=user_id)]
    if any(job.status != "completed" for job in sources):
        raise ApiException(ErrorCode.COMPARE_JOB_NOT_ELIGIBLE, "Both jobs must be completed before comparing them.")

    compares = CompareService(db)
    compare = compares.create(user_id=user_id, before_job_id=body.before_job_id, after_job_id=body.after_job_id)
    async_result = compare_images.delay(str(compare.id))
    compares.set_celery_task_id(compare.id, async_result.id)

    return CreateCompareResponse(compare_id=compare.id, status="queued")


@router.get("/{compare_id}", response_model=CompareStatusResponse)
@limiter.limit("60/minute")
def get_compare(
    request: Request,
    compare_id: uuid.UUID,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> CompareStatusResponse:
    compare = CompareService(db).get_owned(compare_id=compare_id, user_id=user_id)
    error = None
    if compare.status == "failed":
        error = ApiError(
            code=compare.error_code or ErrorCode.INTERNAL_ERROR,
            message=compare.error_message or "Comparison failed.",
        )
    return CompareStatusResponse(
        compare_id=compare.id,
        status=compare.status,
        stage=compare.stage,
        progress=compare.progress,
        error=error,
    )


@router.get("/{compare_id}/result", response_model=CompareResultResponse)
@limiter.limit("30/minute")
def get_compare_result(
    request: Request,
    compare_id: uuid.UUID,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> CompareResultResponse:
    compare = CompareService(db).get_owned(compare_id=compare_id, user_id=user_id)
    if compare.status != "completed":
        raise ApiException(ErrorCode.JOB_NOT_COMPLETE, "Comparison has not completed yet.")

    # Signed URLs only after the JWT + ownership check above (PRD §7). The
    # textures are the source jobs' own artifacts, referenced not copied.
    artifacts = CompareArtifacts(
        diff_map_url=storage.create_signed_url(compare.diff_map_path),
        before_texture_url=storage.create_signed_url(compare.before_texture_path),
        after_texture_url=storage.create_signed_url(compare.after_texture_path),
    )

    return CompareResultResponse(
        compare_id=compare.id,
        before_job_id=compare.before_job_id,
        after_job_id=compare.after_job_id,
        artifacts=artifacts,
        metadata=CompareMetadata(**compare.compare_metadata),
        warnings=compare.warnings or [],
    )
