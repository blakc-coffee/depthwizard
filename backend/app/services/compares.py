"""CompareService — durable comparison state (PRD §9.9).

Owner: Backend Engineer A. See PRD §9.
"""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.db.models import Compare


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
