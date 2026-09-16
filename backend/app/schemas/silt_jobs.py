"""Silt-job request/response schemas — mirrors app/schemas/jobs.py's shape,
a separate model set since the fields genuinely differ (no heightmap/DSM/
height metadata; one heatmap + a scalar SSC prediction instead).
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.errors import ApiError

JobStatus = Literal["queued", "processing", "completed", "failed"]
SiltJobStage = Literal["loading_input", "estimating_silt", "packaging", "uploading_results"]
# PLACEHOLDER SCOPE (ml/river_silt_pipeline.py, 2026-09-14): only
# relative_silt_index is ever actually produced today — absolute_ssc is
# listed so the schema doesn't need another change once gauge-anchor fusion
# (PRD Chunk 3) lands.
SiltOutputType = Literal["relative_silt_index", "absolute_ssc"]
DredgingLevel = Literal["low", "moderate", "high"]


class CreateSiltJobResponse(BaseModel):
    job_id: UUID
    status: JobStatus


class SiltJobStatusResponse(BaseModel):
    job_id: UUID
    status: JobStatus
    stage: SiltJobStage | None
    progress: int = Field(ge=0, le=100)
    error: ApiError | None


class SiltJobArtifacts(BaseModel):
    texture_url: str
    heatmap_url: str


class SiltJobResult(BaseModel):
    job_id: UUID
    output_type: SiltOutputType
    artifacts: SiltJobArtifacts
    predicted_ssc_mg_l: float
    dredging_level: DredgingLevel
    dredging_label: str
    cross_section_profile: list[float]
    warnings: list[str]


class SiltJobSummary(BaseModel):
    job_id: UUID
    status: JobStatus
    output_type: SiltOutputType | None
    input_filename: str
    created_at: datetime
    completed_at: datetime | None


class SiltJobListResponse(BaseModel):
    jobs: list[SiltJobSummary]
