"""SiltJobService — durable river-silt job state.

Mirrors JobService (app/services/jobs.py) — same lifecycle methods, a
separate class rather than a shared one because set_completed()'s result
shape genuinely differs (no heightmap_16bit/dsm/confidence_map, no metrics
object; predicted_ssc_mg_l instead).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import ApiException, ErrorCode
from app.db.models import SiltJob


class SiltJobService:
    def __init__(self, db: Session):
        self.db = db

    def create(
        self,
        *,
        user_id: str,
        input_path: str,
        input_filename: str,
        input_media_type: str,
        job_id: uuid.UUID | None = None,
    ) -> SiltJob:
        job = SiltJob(
            id=job_id or uuid.uuid4(),
            user_id=uuid.UUID(user_id),
            status="queued",
            progress=0,
            input_path=input_path,
            input_filename=input_filename,
            input_media_type=input_media_type,
            warnings=[],
        )
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)
        return job

    def get_owned(self, *, job_id: uuid.UUID, user_id: str) -> SiltJob:
        job = self.db.get(SiltJob, job_id)
        if job is None:
            raise ApiException(ErrorCode.JOB_NOT_FOUND, "Job not found.")
        if str(job.user_id) != str(user_id):
            raise ApiException(ErrorCode.FORBIDDEN_JOB, "You do not own this job.")
        return job

    def list_for_user(self, *, user_id: str) -> list[SiltJob]:
        stmt = select(SiltJob).where(SiltJob.user_id == uuid.UUID(user_id)).order_by(SiltJob.created_at.desc())
        return list(self.db.scalars(stmt))

    def get_for_processing(self, job_id: uuid.UUID) -> SiltJob | None:
        return self.db.get(SiltJob, job_id)

    def set_celery_task_id(self, job_id: uuid.UUID, task_id: str) -> None:
        job = self.db.get(SiltJob, job_id)
        if job is None:
            return
        job.celery_task_id = task_id
        self.db.commit()

    def set_processing(self, job_id: uuid.UUID) -> None:
        job = self.db.get(SiltJob, job_id)
        if job is None:
            return
        job.status = "processing"
        job.started_at = datetime.now(UTC)
        self.db.commit()

    def set_progress(self, job_id: uuid.UUID, *, stage: str, progress: int) -> None:
        job = self.db.get(SiltJob, job_id)
        if job is None:
            return
        job.progress = max(job.progress, progress)  # monotonic, same rule as JobService
        job.stage = stage
        self.db.commit()

    def set_completed(self, job_id: uuid.UUID, *, result: dict) -> None:
        job = self.db.get(SiltJob, job_id)
        if job is None:
            return
        job.status = "completed"
        job.progress = 100
        job.output_type = result.get("output_type")
        job.texture_path = result.get("texture_path")
        job.heatmap_path = result.get("heatmap_path")
        job.predicted_ssc_mg_l = result.get("predicted_ssc_mg_l")
        job.job_metadata = result.get("metadata")
        job.warnings = result.get("warnings", [])
        job.completed_at = datetime.now(UTC)
        self.db.commit()

    def set_failed(self, job_id: uuid.UUID, *, error_code: str, error_message: str) -> None:
        job = self.db.get(SiltJob, job_id)
        if job is None:
            return
        job.status = "failed"
        job.error_code = str(error_code)
        job.error_message = error_message
        job.completed_at = datetime.now(UTC)
        self.db.commit()

    def exists(self, job_id: uuid.UUID) -> bool:
        return self.db.get(SiltJob, job_id) is not None

    def delete(self, *, job_id: uuid.UUID, user_id: str) -> SiltJob:
        job = self.get_owned(job_id=job_id, user_id=user_id)
        self.db.delete(job)
        self.db.commit()
        return job
