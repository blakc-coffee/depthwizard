"""Comparison request/response schemas (PRD §9.9).

Owner: Backend Engineer A. See PRD §9.
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.errors import ApiError

CompareStatus = Literal["queued", "processing", "completed", "failed"]
# A separate vocabulary from job stages — no depth estimation or calibration
# happens here, both DSMs already exist (PRD §9.9).
CompareStage = Literal["loading_inputs", "aligning", "computing_diff", "packaging", "uploading_results"]
HeightUnits = Literal["m", "relative"]


class CreateCompareRequest(BaseModel):
    before_job_id: UUID
    after_job_id: UUID


class CreateCompareResponse(BaseModel):
    compare_id: UUID
    status: CompareStatus


class CompareStatusResponse(BaseModel):
    compare_id: UUID
    status: CompareStatus
    stage: CompareStage | None
    progress: int = Field(ge=0, le=100)
    error: ApiError | None


class CompareArtifacts(BaseModel):
    diff_map_url: str
    before_texture_url: str
    after_texture_url: str


class CompareMetadata(BaseModel):
    height_units: HeightUnits
    max_loss: float
    max_gain: float
    changed_area_fraction: float
    threshold: float


class CompareResultResponse(BaseModel):
    compare_id: UUID
    before_job_id: UUID
    after_job_id: UUID
    artifacts: CompareArtifacts
    metadata: CompareMetadata
    warnings: list[str]
