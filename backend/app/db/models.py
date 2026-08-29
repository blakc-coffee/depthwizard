"""SQLAlchemy models: jobs, compares.

Owner: Backend Engineer A. See PRD §9.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import CheckConstraint, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    pass


# Job lifecycle (PRD §8): queued -> processing -> completed | failed. No cancelled state.
JOB_STATUSES = ("queued", "processing", "completed", "failed")

# Stages reported during `processing` (PRD §8).
JOB_STAGES = (
    "loading_input",
    "estimating_depth",
    "fetching_reference",
    "calibrating",
    "packaging",
    "validating_output",
    "uploading_results",
)

# Compare stages are a SEPARATE vocabulary (PRD §9.9/§21) — depth estimation
# and calibration don't happen here, both DSMs already exist.
COMPARE_STAGES = ("loading_inputs", "aligning", "computing_diff", "packaging", "uploading_results")

OUTPUT_TYPES = ("relative_dsm", "absolute_dsm")


class Job(Base):
    """Durable job state (PRD §9.4). Postgres is the source of truth —
    Redis carries only the Celery task id, never status (PRD §2)."""

    __tablename__ = "jobs"
    __table_args__ = (
        CheckConstraint(f"status IN {JOB_STATUSES}", name="jobs_status_valid"),
        CheckConstraint(f"stage IS NULL OR stage IN {JOB_STAGES}", name="jobs_stage_valid"),
        CheckConstraint("progress >= 0 AND progress <= 100", name="jobs_progress_range"),
        CheckConstraint(f"output_type IS NULL OR output_type IN {OUTPUT_TYPES}", name="jobs_output_type_valid"),
        Index("ix_jobs_user_id_created_at", "user_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    status: Mapped[str] = mapped_column(String(16), nullable=False, default="queued")
    stage: Mapped[str | None] = mapped_column(String(32), nullable=True)
    progress: Mapped[int] = mapped_column(nullable=False, default=0)

    input_path: Mapped[str] = mapped_column(Text, nullable=False)
    input_filename: Mapped[str] = mapped_column(Text, nullable=False)
    input_media_type: Mapped[str] = mapped_column(String(64), nullable=False)

    output_type: Mapped[str | None] = mapped_column(String(16), nullable=True)
    texture_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    heightmap_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    heightmap_16bit_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence_map_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    dsm_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_path: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Named `job_metadata` in Python — `metadata` is reserved on Declarative
    # models (it's SQLAlchemy's own schema-reflection attribute). The DB
    # column is still literally named `metadata`, matching the contract.
    job_metadata: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB, nullable=True)
    metrics: Mapped[dict[str, float] | None] = mapped_column(JSONB, nullable=True)
    warnings: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)

    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    celery_task_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now(), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)


class Compare(Base):
    """Comparison job state (PRD §9.9/§21, stretch). Same lifecycle as Job,
    a different stage vocabulary. Both FKs are ON DELETE CASCADE rather than
    SET NULL: a compare whose source job is gone can't be re-run or
    re-rendered, so the row is removed rather than kept in a broken state
    that every read path would have to special-case (PRD §8)."""

    __tablename__ = "compares"
    __table_args__ = (
        CheckConstraint(f"status IN {JOB_STATUSES}", name="compares_status_valid"),
        CheckConstraint(f"stage IS NULL OR stage IN {COMPARE_STAGES}", name="compares_stage_valid"),
        CheckConstraint("progress >= 0 AND progress <= 100", name="compares_progress_range"),
        Index("ix_compares_user_id_created_at", "user_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    before_job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
    )
    after_job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False
    )

    status: Mapped[str] = mapped_column(String(16), nullable=False, default="queued")
    stage: Mapped[str | None] = mapped_column(String(32), nullable=True)
    progress: Mapped[int] = mapped_column(nullable=False, default=0)

    diff_map_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    before_texture_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    after_texture_path: Mapped[str | None] = mapped_column(Text, nullable=True)

    compare_metadata: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB, nullable=True)
    warnings: Mapped[list[str]] = mapped_column(ARRAY(Text), nullable=False, default=list)

    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    celery_task_id: Mapped[str | None] = mapped_column(String(64), nullable=True)

    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now(), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)
