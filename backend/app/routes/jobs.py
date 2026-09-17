"""Job endpoints (PRD §9.5–§9.6).

Owner: Backend Engineer A. See PRD §9.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request, UploadFile
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user_id
from app.core.config import get_settings
from app.core.errors import ApiException, ErrorCode
from app.core.rate_limit import limiter
from app.db.models import Job
from app.db.session import get_db
from app.schemas.errors import ApiError
from app.schemas.jobs import (
    CreateJobResponse,
    JobArtifacts,
    JobListResponse,
    JobMetadata,
    JobMetrics,
    JobResult,
    JobStatusResponse,
    JobSummary,
)
from app.services import storage
from app.services.compares import CompareService
from app.services.jobs import JobService
from app.services.upload_validation import sanitize_filename, sniff_media_type, validate_image_content
from app.tasks.process_image import process_image

router = APIRouter(prefix="/api/v1/jobs", tags=["jobs"])


def _validate_upload(content: bytes, filename: str | None, *, label: str | None = None) -> tuple[str, str]:
    """Returns (media_type, sanitized filename). `label` prefixes error messages
    so a two-image upload says which image was rejected."""
    settings = get_settings()
    try:
        if len(content) > settings.max_upload_bytes:
            raise ApiException(ErrorCode.FILE_TOO_LARGE, f"File exceeds the {settings.max_upload_mb} MB limit.")
        media_type = sniff_media_type(content)
        validate_image_content(content, media_type, settings.max_image_pixels)
    except ApiException as exc:
        if label:
            raise ApiException(exc.code, f"{label}: {exc.message}") from exc
        raise
    return media_type, sanitize_filename(filename)


def _create_job_with_input(
    jobs: JobService, db: Session, user_id: str, content: bytes, media_type: str, filename: str
) -> Job:
    job_id = uuid.uuid4()
    job = jobs.create(
        job_id=job_id,
        user_id=user_id,
        input_path=storage.input_path(user_id, str(job_id), media_type),
        input_filename=filename,
        input_media_type=media_type,
    )
    try:
        storage.save_input(user_id, str(job_id), content, media_type)
    except ApiException:
        db.delete(job)
        db.commit()
        raise
    return job


@router.post("", status_code=202, response_model=CreateJobResponse, response_model_exclude_none=True)
@limiter.limit("10/hour")
async def create_job(
    request: Request,
    file: UploadFile,
    secondary_file: UploadFile | None = None,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> CreateJobResponse:
    content = await file.read()
    media_type, filename = _validate_upload(content, file.filename)

    if secondary_file is not None:
        after_content = await secondary_file.read()
        after_media_type, after_filename = _validate_upload(
            after_content, secondary_file.filename, label="Second image"
        )

    jobs = JobService(db)
    job = _create_job_with_input(jobs, db, user_id, content, media_type, filename)

    if secondary_file is None:
        async_result = process_image.delay(str(job.id))
        jobs.set_celery_task_id(job.id, async_result.id)
        return CreateJobResponse(job_id=job.id, status="queued")

    try:
        after_job = _create_job_with_input(jobs, db, user_id, after_content, after_media_type, after_filename)
    except ApiException:
        db.delete(job)
        db.commit()
        storage.delete_job_artifacts(user_id, str(job.id))
        raise

    compare = CompareService(db).create(user_id=user_id, before_job_id=job.id, after_job_id=after_job.id)
    for queued_job in (job, after_job):
        async_result = process_image.delay(str(queued_job.id))
        jobs.set_celery_task_id(queued_job.id, async_result.id)

    return CreateJobResponse(
        job_id=job.id, status="queued", secondary_job_id=after_job.id, compare_id=compare.id
    )


@router.get("/{job_id}", response_model=JobStatusResponse)
@limiter.limit("60/minute")
def get_job(
    request: Request,
    job_id: uuid.UUID,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> JobStatusResponse:
    job = JobService(db).get_owned(job_id=job_id, user_id=user_id)
    error = None
    if job.status == "failed":
        error = ApiError(code=job.error_code or ErrorCode.INTERNAL_ERROR, message=job.error_message or "Job failed.")
    return JobStatusResponse(job_id=job.id, status=job.status, stage=job.stage, progress=job.progress, error=error)


@router.get("/{job_id}/result", response_model=JobResult)
@limiter.limit("30/minute")
def get_job_result(
    request: Request,
    job_id: uuid.UUID,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> JobResult:
    job = JobService(db).get_owned(job_id=job_id, user_id=user_id)
    if job.status != "completed":
        raise ApiException(ErrorCode.JOB_NOT_COMPLETE, "Job has not completed yet.")

    # Signed URLs are generated only after the JWT + ownership check above
    # has already happened (PRD §7).
    artifacts = JobArtifacts(
        texture_url=storage.create_signed_url(job.texture_path),
        heightmap_url=storage.create_signed_url(job.heightmap_path),
        heightmap_16bit_url=storage.create_signed_url(job.heightmap_16bit_path) if job.heightmap_16bit_path else None,
        confidence_map_url=storage.create_signed_url(job.confidence_map_path) if job.confidence_map_path else None,
        dsm_url=storage.create_signed_url(job.dsm_path) if job.dsm_path else None,
    )

    return JobResult(
        job_id=job.id,
        output_type=job.output_type,
        artifacts=artifacts,
        metadata=JobMetadata(**job.job_metadata),
        metrics=JobMetrics(**job.metrics) if job.metrics else None,
        warnings=job.warnings or [],
    )


@router.get("", response_model=JobListResponse)
@limiter.limit("30/minute")
def list_jobs(
    request: Request,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> JobListResponse:
    owned = JobService(db).list_for_user(user_id=user_id)
    return JobListResponse(
        jobs=[
            JobSummary(
                job_id=j.id,
                status=j.status,
                output_type=j.output_type,
                input_filename=j.input_filename,
                created_at=j.created_at,
                completed_at=j.completed_at,
            )
            for j in owned
        ]
    )


@router.delete("/{job_id}", status_code=204)
@limiter.limit("20/minute")
def delete_job(
    request: Request,
    job_id: uuid.UUID,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> None:
    _job, compare_ids = JobService(db).delete(job_id=job_id, user_id=user_id)
    storage.delete_job_artifacts(user_id, str(job_id))
    for compare_id in compare_ids:
        storage.delete_compare_artifacts(user_id, str(compare_id))
