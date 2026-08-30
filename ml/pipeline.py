"""Top-level ML pipeline orchestrator — image in, PipelineResult out.

Implements the Backend <-> ML contract in docs/depthwizard.md Section 9.6.
Stage A (relative depth, Phase 1) is wired in; calibration/fusion, DSM
packaging, and validation (Phase 4/5) are not yet built. Per the honesty
rule in Section 1 ("never claim absolute metric accuracy when the pipeline
only produced a relative result"), output_type is always "relative_dsm"
until Phase 4's calibration lands — a georeferenced input alone is not
sufficient to claim an absolute DSM.
"""

from dataclasses import dataclass, field
from pathlib import Path

import rasterio
from PIL import Image

from depth.backbone import estimate_relative_depth
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
    output_dir = Path(output_dir)
    georeferenced = _is_georeferenced(input_path)

    # Texture export runs for every branch — the viewer needs a browser-
    # displayable texture regardless of whether calibration ends up absolute
    # or relative (Section 9.5: texture_url is always present).
    texture_path = export_texture(input_path, output_dir)

    # Stage A — the texture is already a normalized, browser-viewable RGB
    # image at heightmap resolution for both PNG/JPG and GeoTIFF inputs, so
    # running depth on it (rather than the raw upload) keeps texture and
    # heightmap pixel-aligned for free (§9.8).
    texture_image = Image.open(texture_path).convert("RGB")
    depth_map = estimate_relative_depth(texture_image)  # mode "L", same size as input

    heightmap_path = output_dir / f"{input_path.stem}_heightmap.png"
    heightmap = Image.merge("LA", (depth_map, Image.new("L", depth_map.size, 255)))
    heightmap.save(heightmap_path)

    warning = (
        "Calibration stage (Phase 4) is not yet implemented — output is "
        "uncalibrated relative depth, not absolute height, even though the "
        "input is georeferenced."
        if georeferenced
        else "Calibration/cleanup stage (Phase 4) is not yet implemented — "
        "output is raw relative depth."
    )

    return PipelineResult(
        output_type="relative_dsm",
        heightmap_path=str(heightmap_path),
        texture_path=str(texture_path),
        metadata={
            "height_units": "relative",
            "min_height": 0,
            "max_height": 255,
            "width": depth_map.width,
            "height": depth_map.height,
        },
        warnings=[warning],
    )
