"""Job request/response schemas (PRD §9.5–§9.6).

Owner: Backend Engineer A. See PRD §9.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.errors import ApiError

JobStatus = Literal["queued", "processing", "completed", "failed"]
JobStage = Literal[
    "loading_input",
    "estimating_depth",
    "fetching_reference",
    "calibrating",
    "packaging",
    "validating_output",
    "uploading_results",
]
OutputType = Literal["relative_dsm", "absolute_dsm"]
HeightUnits = Literal["m", "relative"]


class CreateJobResponse(BaseModel):
    job_id: UUID
    status: JobStatus


class JobStatusResponse(BaseModel):
    job_id: UUID
    status: JobStatus
    stage: JobStage | None
    progress: int = Field(ge=0, le=100)
    error: ApiError | None


class JobArtifacts(BaseModel):
    # Always present on a completed job (§9.6).
    texture_url: str
    heightmap_url: str
    # Optional.
    heightmap_16bit_url: str | None = None
    confidence_map_url: str | None = None
    dsm_url: str | None = None


class JobMetadata(BaseModel):
    height_units: HeightUnits
    min_height: float
    max_height: float
    width: int
    height: int


class JobMetrics(BaseModel):
    rmse: float
    mae: float
    correlation: float


class JobResult(BaseModel):
    job_id: UUID
    output_type: OutputType
    artifacts: JobArtifacts
    metadata: JobMetadata
    # Explicitly null when no reference elevation exists for the scene — the
    # normal case for user uploads. Never an empty object, never zeros (§9.6).
    metrics: JobMetrics | None
    warnings: list[str]


class JobSummary(BaseModel):
    job_id: UUID
    status: JobStatus
    output_type: OutputType | None  # null for jobs that have not completed
    input_filename: str
    created_at: datetime
    completed_at: datetime | None


class JobListResponse(BaseModel):
    jobs: list[JobSummary]
