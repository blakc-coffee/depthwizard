"""JobService — durable job state (PRD §9.1).

Owner: Backend Engineer A. See PRD §9.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.errors import ApiException, ErrorCode
from app.db.models import Compare, Job


class JobService:
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
    ) -> Job:
        job = Job(
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

    def get_owned(self, *, job_id: uuid.UUID, user_id: str) -> Job:
        """Ownership-checked read. FORBIDDEN_JOB and JOB_NOT_FOUND stay
        distinct codes (PRD §9.2/§11): the caller has already proven who
        they are via a verified JWT, so distinguishing "this job belongs to
        someone else" from "this job doesn't exist" doesn't leak anything a
        valid, authenticated caller couldn't otherwise infer."""
        job = self.db.get(Job, job_id)
        if job is None:
            raise ApiException(ErrorCode.JOB_NOT_FOUND, "Job not found.")
        if str(job.user_id) != str(user_id):
            raise ApiException(ErrorCode.FORBIDDEN_JOB, "You do not own this job.")
        return job

    def list_for_user(self, *, user_id: str) -> list[Job]:
        stmt = select(Job).where(Job.user_id == uuid.UUID(user_id)).order_by(Job.created_at.desc())
        return list(self.db.scalars(stmt))

    def set_celery_task_id(self, job: Job, task_id: str) -> None:
        job.celery_task_id = task_id
        self.db.commit()

    def set_processing(self, job_id: uuid.UUID) -> None:
        job = self.db.get(Job, job_id)
        if job is None:
            return
        job.status = "processing"
        job.started_at = datetime.now(UTC)
        self.db.commit()

    def set_progress(self, job_id: uuid.UUID, *, stage: str, progress: int) -> None:
        job = self.db.get(Job, job_id)
        if job is None:
            return
        # progress is monotonic (PRD §8) — never let an update move it backwards.
        job.progress = max(job.progress, progress)
        job.stage = stage
        self.db.commit()

    def set_completed(self, job_id: uuid.UUID, *, result: dict) -> None:
        job = self.db.get(Job, job_id)
        if job is None:
            return
        job.status = "completed"
        job.progress = 100
        job.output_type = result.get("output_type")
        job.texture_path = result.get("texture_path")
        job.heightmap_path = result.get("heightmap_path")
        job.heightmap_16bit_path = result.get("heightmap_16bit_path")
        job.confidence_map_path = result.get("confidence_map_path")
        job.dsm_path = result.get("dsm_path")
        job.job_metadata = result.get("metadata")
        job.metrics = result.get("metrics")
        job.warnings = result.get("warnings", [])
        job.completed_at = datetime.now(UTC)
        self.db.commit()

    def set_failed(self, job_id: uuid.UUID, *, error_code: str, error_message: str) -> None:
        job = self.db.get(Job, job_id)
        if job is None:
            return
        job.status = "failed"
        job.error_code = str(error_code)
        job.error_message = error_message
        job.completed_at = datetime.now(UTC)
        self.db.commit()

    def exists(self, job_id: uuid.UUID) -> bool:
        """Used by the worker's staging/promotion existence re-check (PRD
        §8) — deliberately not ownership-scoped, since the worker isn't
        acting on behalf of an HTTP caller."""
        return self.db.get(Job, job_id) is not None

    def delete(self, *, job_id: uuid.UUID, user_id: str) -> tuple[Job, list[uuid.UUID]]:
        """Deletes the job row (DB-level ON DELETE CASCADE removes any
        referencing compares) and returns the ids of those cascaded
        compares, so the caller can also purge their storage artifacts —
        the DB cascade only removes rows, not Supabase Storage objects
        (PRD §8)."""
        job = self.get_owned(job_id=job_id, user_id=user_id)
        stmt = select(Compare.id).where(or_(Compare.before_job_id == job_id, Compare.after_job_id == job_id))
        compare_ids = list(self.db.scalars(stmt))
        self.db.delete(job)
        self.db.commit()
        return job, compare_ids
