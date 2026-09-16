"""River-silt job endpoints — mirrors app/routes/jobs.py's shape and
validation (same upload sniffing/verification, same auth/ownership pattern),
pointed at SiltJobService and process_river_silt_image instead.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, UploadFile
from sqlalchemy.orm import Session

from app.auth.dependencies import get_current_user_id
from app.core.config import get_settings
from app.core.errors import ApiException, ErrorCode
from app.db.session import get_db
from app.schemas.errors import ApiError
from app.schemas.silt_jobs import (
    CreateSiltJobResponse,
    SiltJobArtifacts,
    SiltJobListResponse,
    SiltJobResult,
    SiltJobStatusResponse,
    SiltJobSummary,
)
from app.services import storage
from app.services.silt_jobs import SiltJobService
from app.services.upload_validation import sniff_media_type, validate_image_content
from app.tasks.process_river_silt_image import process_river_silt_image

router = APIRouter(prefix="/api/v1/silt-jobs", tags=["silt-jobs"])


@router.post("", status_code=202, response_model=CreateSiltJobResponse)
async def create_silt_job(
    file: UploadFile,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> CreateSiltJobResponse:
    settings = get_settings()
    content = await file.read()

    if len(content) > settings.max_upload_bytes:
        raise ApiException(ErrorCode.FILE_TOO_LARGE, f"File exceeds the {settings.max_upload_mb} MB limit.")

    media_type = sniff_media_type(content)
    validate_image_content(content, media_type)

    filename = file.filename or "upload"
    job_id = uuid.uuid4()
    stored_path = storage.input_path(user_id, str(job_id), filename)

    jobs = SiltJobService(db)
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

    async_result = process_river_silt_image.delay(str(job.id))
    jobs.set_celery_task_id(job.id, async_result.id)

    return CreateSiltJobResponse(job_id=job.id, status="queued")


@router.get("/{job_id}", response_model=SiltJobStatusResponse)
def get_silt_job(
    job_id: uuid.UUID,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> SiltJobStatusResponse:
    job = SiltJobService(db).get_owned(job_id=job_id, user_id=user_id)
    error = None
    if job.status == "failed":
        error = ApiError(code=job.error_code or ErrorCode.INTERNAL_ERROR, message=job.error_message or "Job failed.")
    return SiltJobStatusResponse(job_id=job.id, status=job.status, stage=job.stage, progress=job.progress, error=error)


@router.get("/{job_id}/result", response_model=SiltJobResult)
def get_silt_job_result(
    job_id: uuid.UUID,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> SiltJobResult:
    job = SiltJobService(db).get_owned(job_id=job_id, user_id=user_id)
    if job.status != "completed":
        raise ApiException(ErrorCode.JOB_NOT_COMPLETE, "Job has not completed yet.")

    artifacts = SiltJobArtifacts(
        texture_url=storage.create_signed_url(job.texture_path),
        heatmap_url=storage.create_signed_url(job.heatmap_path),
    )
    metadata = job.job_metadata or {}

    return SiltJobResult(
        job_id=job.id,
        output_type=job.output_type,
        artifacts=artifacts,
        predicted_ssc_mg_l=job.predicted_ssc_mg_l,
        dredging_level=metadata.get("dredging_level", "low"),
        dredging_label=metadata.get("dredging_label", ""),
        cross_section_profile=metadata.get("cross_section_profile", []),
        warnings=job.warnings or [],
    )


@router.get("", response_model=SiltJobListResponse)
def list_silt_jobs(
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> SiltJobListResponse:
    owned = SiltJobService(db).list_for_user(user_id=user_id)
    return SiltJobListResponse(
        jobs=[
            SiltJobSummary(
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
def delete_silt_job(
    job_id: uuid.UUID,
    user_id: str = Depends(get_current_user_id),
    db: Session = Depends(get_db),
) -> None:
    SiltJobService(db).delete(job_id=job_id, user_id=user_id)
    storage.delete_job_artifacts(user_id, str(job_id))
