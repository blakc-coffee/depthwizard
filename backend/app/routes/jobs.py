"""Job endpoints (PRD §9.5–§9.6).

Owner: Backend Engineer A. See PRD §9.
"""

from __future__ import annotations

import uuid
from io import BytesIO

from fastapi import APIRouter, Depends, UploadFile
from PIL import Image
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user_id
from app.core.config import get_settings
from app.core.errors import ApiException, ErrorCode
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
from app.services.jobs import JobService
from app.tasks.process_image import process_image

router = APIRouter(prefix="/api/v1/jobs", tags=["jobs"])


def _sniff_media_type(content: bytes) -> str:
    """Content-based type detection (PRD §9.5) — never trust the declared
    Content-Type, especially for TIFF (§17: client MIME for TIFF is
    unreliable)."""
    if content[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if content[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if content[:4] in (b"II*\x00", b"MM\x00*"):
        return "image/tiff"
    raise ApiException(ErrorCode.UNSUPPORTED_FILE, "File is not a PNG, JPEG, or TIFF/GeoTIFF.")


def _validate_image_content(content: bytes, media_type: str) -> None:
    """PNG/JPEG are fully verified via Pillow — simple, universally
    supported formats, so a corrupt file should be caught now. TIFF
    deliberately stops at the magic-byte check above: many valid GeoTIFFs
    (multi-band, 16-bit, unusual compression) aren't Pillow-decodable, but
    rasterio (ml/pipeline.py, worker-side) can read them. Rejecting here on
    Pillow's narrower support would silently disable the GeoTIFF path
    (PRD §12.1)."""
    if media_type == "image/tiff":
        return
    try:
        with Image.open(BytesIO(content)) as img:
            img.verify()
    except Exception as exc:
        raise ApiException(ErrorCode.INVALID_IMAGE, "File could not be decoded as a valid image.") from exc


@router.post("", status_code=202, response_model=CreateJobResponse)
async def create_job(
    file: UploadFile,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> CreateJobResponse:
    settings = get_settings()
    content = await file.read()

    if len(content) > settings.max_upload_bytes:
        raise ApiException(ErrorCode.FILE_TOO_LARGE, f"File exceeds the {settings.max_upload_mb} MB limit.")

    media_type = _sniff_media_type(content)
    _validate_image_content(content, media_type)

    filename = file.filename or "upload"
    job_id = uuid.uuid4()
    stored_path = storage.input_path(user_id, str(job_id), filename)

    jobs = JobService(db)
    job = jobs.create(
        job_id=job_id,
        user_id=user_id,
        input_path=stored_path,
        input_filename=filename,
        input_media_type=media_type,
    )

    try:
        storage.save_input(user_id, str(job_id), content, filename, media_type)
    except ApiException:
        db.delete(job)
        db.commit()
        raise

    async_result = process_image.delay(str(job.id))
    jobs.set_celery_task_id(job, async_result.id)

    return CreateJobResponse(job_id=job.id, status="queued")


@router.get("/{job_id}", response_model=JobStatusResponse)
def get_job(
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
def get_job_result(
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
def list_jobs(
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
def delete_job(
    job_id: uuid.UUID,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> None:
    _job, compare_ids = JobService(db).delete(job_id=job_id, user_id=user_id)
    storage.delete_job_artifacts(user_id, str(job_id))
    for compare_id in compare_ids:
        storage.delete_compare_artifacts(user_id, str(compare_id))
