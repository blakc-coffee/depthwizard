"""Top-level ML pipeline orchestrator — image in, PipelineResult out.

Implements the Backend <-> ML contract in docs/depthwizard.md Section 9.6.
Depth estimation, calibration, DSM packaging, and validation (Phase 4/5) are
not yet built — per the pure-function design principle in Section 4, this
returns a partial, honest PipelineResult (real texture_path, everything else
None/empty + a warning) rather than fabricating those fields, so Backend/
Frontend can build against the contract now and get real output swapped in
per-field as later phases land.
"""

from dataclasses import dataclass, field
from pathlib import Path

import rasterio

from utils.texture_export import export_texture

GEOTIFF_EXTENSIONS = {".tif", ".tiff"}


@dataclass
class PipelineResult:
    output_type: str  # "relative_dsm" | "absolute_dsm"
    heightmap_path: str | None
    texture_path: str
    confidence_map_path: str | None = None
    dsm_path: str | None = None
    metadata: dict = field(default_factory=dict)
    metrics: dict = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


def _is_georeferenced(input_path: Path) -> bool:
    if input_path.suffix.lower() not in GEOTIFF_EXTENSIONS:
        return False
    with rasterio.open(input_path) as src:
        return src.crs is not None


def run_pipeline(input_path: str | Path, output_dir: str | Path) -> PipelineResult:
    """image in -> PipelineResult out. See Section 9.6 for the frozen contract."""
    input_path = Path(input_path)
    georeferenced = _is_georeferenced(input_path)

    # Texture export runs for every branch — the viewer needs a browser-
    # displayable texture regardless of whether calibration ends up absolute
    # or relative (Section 9.5: texture_url is always present).
    texture_path = export_texture(input_path, output_dir)

    return PipelineResult(
        output_type="absolute_dsm" if georeferenced else "relative_dsm",
        heightmap_path=None,
        texture_path=str(texture_path),
        metadata={"height_units": "m" if georeferenced else "relative"},
        warnings=[
            "Depth estimation and calibration stages are not yet implemented "
            "(Phase 4/5) — only texture_path is real output from this call."
        ],
    )
