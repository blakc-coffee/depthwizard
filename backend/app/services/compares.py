"""CompareService — durable comparison state (PRD §9.9).

Owner: Backend Engineer A. See PRD §9.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.db.models import Compare, Job


class CompareService:
    def __init__(self, db: Session):
        self.db = db

    def create(self, *, user_id: str, before_job_id: uuid.UUID, after_job_id: uuid.UUID) -> Compare:
        compare = Compare(
            id=uuid.uuid4(),
            user_id=uuid.UUID(user_id),
            before_job_id=before_job_id,
            after_job_id=after_job_id,
            status="queued",
            progress=0,
            warnings=[],
        )
        self.db.add(compare)
        self.db.commit()
        self.db.refresh(compare)
        return compare

    def get_for_processing(self, compare_id: uuid.UUID) -> Compare | None:
        """Worker-side read, not ownership-scoped — the worker isn't acting on
        behalf of an HTTP caller (same reasoning as JobService)."""
        return self.db.get(Compare, compare_id)

    def exists(self, compare_id: uuid.UUID) -> bool:
        return self.db.get(Compare, compare_id) is not None

    def set_processing(self, compare_id: uuid.UUID) -> None:
        compare = self.db.get(Compare, compare_id)
        if compare is None:
            return
        compare.status = "processing"
        compare.started_at = datetime.now(UTC)
        self.db.commit()

    def set_progress(self, compare_id: uuid.UUID, *, stage: str, progress: int) -> None:
        compare = self.db.get(Compare, compare_id)
        if compare is None:
            return
        compare.progress = max(compare.progress, progress)
        compare.stage = stage
        self.db.commit()

    def set_completed(self, compare_id: uuid.UUID, *, result: dict) -> None:
        compare = self.db.get(Compare, compare_id)
        if compare is None:
            return
        compare.status = "completed"
        compare.progress = 100
        compare.diff_map_path = result.get("diff_map_path")
        compare.before_texture_path = result.get("before_texture_path")
        compare.after_texture_path = result.get("after_texture_path")
        compare.compare_metadata = result.get("metadata")
        compare.warnings = result.get("warnings", [])
        compare.completed_at = datetime.now(UTC)
        self.db.commit()

    def set_failed(self, compare_id: uuid.UUID, *, error_code: str, error_message: str) -> None:
        compare = self.db.get(Compare, compare_id)
        if compare is None:
            return
        compare.status = "failed"
        compare.error_code = str(error_code)
        compare.error_message = error_message
        compare.completed_at = datetime.now(UTC)
        self.db.commit()

    def set_celery_task_id(self, compare_id: uuid.UUID, task_id: str) -> None:
        compare = self.db.get(Compare, compare_id)
        if compare is None:
            return
        compare.celery_task_id = task_id
        self.db.commit()

    def _queued_referencing(self, job_id: uuid.UUID) -> list[Compare]:
        stmt = select(Compare).where(
            Compare.status == "queued",
            or_(Compare.before_job_id == job_id, Compare.after_job_id == job_id),
        )
        return list(self.db.scalars(stmt))

    def ready_compare_ids(self, job_id: uuid.UUID) -> list[uuid.UUID]:
        """Queued comparisons referencing this job whose BOTH source jobs are
        now completed — the worker enqueues these once the second job lands."""
        ready = []
        for compare in self._queued_referencing(job_id):
            sources = [self.db.get(Job, compare.before_job_id), self.db.get(Job, compare.after_job_id)]
            if all(job is not None and job.status == "completed" for job in sources):
                ready.append(compare.id)
        return ready

    def fail_pending_for_job(self, job_id: uuid.UUID, *, error_code: str, error_message: str) -> None:
        """A source job failed, so its queued comparisons can never run — fail
        them now rather than leaving them queued forever."""
        for compare in self._queued_referencing(job_id):
            self.set_failed(compare.id, error_code=error_code, error_message=error_message)
