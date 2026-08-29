"""PipelineResult — frozen backend/ML contract (Master PRD §12, Merged PRD §9.8).

This is the one shape every pipeline run must produce, whether it comes from
`tools/run_pipeline.py` (local, no infra) or `integration/pipeline_runner.py`
(inside the Celery worker). Freezing it here — not duplicating it in FastAPI
schemas or inside `ml/pipeline.py` — is what lets Backend and ML build in
parallel: each side commits to this shape and nothing else about the other.

Owner: Backend — ML infrastructure. See PRD §9. Do not import FastAPI,
Celery, or database internals here — this module must stay importable by
`ml/` tooling with zero backend dependencies.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

VALID_OUTPUT_TYPES = {"relative_dsm", "absolute_dsm"}
VALID_HEIGHT_UNITS = {"m", "relative"}
REQUIRED_METADATA_KEYS = {"height_units", "min_height", "max_height", "width", "height"}


@dataclass
class PipelineResult:
    """image in -> this out. Field table: Master PRD §12.

    Every field marked "required" in §12 is contractually required once the
    ML pipeline is complete (Phase 4/5, PRD §14). `ml/pipeline.py` is still a
    partial, honest implementation today — it returns a real `texture_path`
    and warns about the rest rather than fabricating it. `validate()` has two
    modes for exactly that reason: `strict=False` (tools/run_pipeline.py's
    default) is a diagnostic mode for ML to see what's still missing without
    treating it as a failure; `strict=True` (what the production worker task
    uses as its completion gate) enforces the contract in full. A "completed"
    job in the database must never violate the frozen contract — so today,
    until ML Phase 4/5 lands, jobs legitimately fail strict validation and
    the worker marks them `failed`, not `completed`. See `docs/API.md`.
    """

    output_type: str  # "relative_dsm" | "absolute_dsm"
    texture_path: str  # required on every run
    heightmap_path: str | None = None  # required once ML Phase 4/5 lands
    heightmap_16bit_path: str | None = None  # optional
    confidence_map_path: str | None = None  # optional
    dsm_path: str | None = None  # optional — absolute results only
    metadata: dict[str, Any] = field(default_factory=dict)
    metrics: dict[str, float] | None = None  # None when no reference data exists — never {}
    warnings: list[str] = field(default_factory=list)

    def validate(self, *, strict: bool = False) -> list[str]:
        """Check this result against the frozen contract.

        Returns a list of human-readable problems; empty means contract-clean.
        Structural violations (bad enum values, missing texture_path, metrics
        as an empty dict, a dsm_path on a relative result, a contradictory
        height_units) are always reported — those are bugs, partial pipeline
        or not. `heightmap_path` and full `metadata` are gated by `strict`
        since `ml/pipeline.py` doesn't produce them yet (see class docstring).
        """
        problems: list[str] = []

        if self.output_type not in VALID_OUTPUT_TYPES:
            problems.append(f"output_type must be one of {sorted(VALID_OUTPUT_TYPES)}, got {self.output_type!r}")

        if not self.texture_path:
            problems.append("texture_path is required on every run (§12)")

        if strict and self.heightmap_path is None:
            problems.append("heightmap_path is required on every run (§12)")

        if self.dsm_path and self.output_type != "absolute_dsm":
            problems.append("dsm_path is only valid when output_type == 'absolute_dsm'")

        missing_meta = REQUIRED_METADATA_KEYS - self.metadata.keys()
        if strict and missing_meta:
            problems.append(f"metadata is missing required keys: {sorted(missing_meta)}")

        if "height_units" in self.metadata:
            units = self.metadata["height_units"]
            if units not in VALID_HEIGHT_UNITS:
                problems.append(f"metadata.height_units must be one of {sorted(VALID_HEIGHT_UNITS)}, got {units!r}")
            elif self.output_type == "relative_dsm" and units == "m":
                problems.append("relative_dsm output must not carry height_units == 'm' (§4 scientific boundary)")

        if self.metrics is not None and not self.metrics:
            problems.append("metrics must be null (None) when absent, never an empty object (§9.6)")

        return problems

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
