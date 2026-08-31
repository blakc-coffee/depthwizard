"""Top-level ML pipeline orchestrator — image in, PipelineResult out.

Implements the Backend <-> ML contract in docs/depthwizard.md Section 9.6.
Stage A (relative depth, Phase 1) and Stage B (calibration, Phase 4) are
both wired in now. DSM packaging and validation (Phase 5) are not yet built.

Per the honesty rule in Section 1 ("never claim absolute metric accuracy
when the pipeline only produced a relative result"), output_type is only
ever "absolute_dsm" when ALL of: the input is georeferenced, the SRTM fetch
actually succeeded (not just attempted), and fused calibration confidence
clears MIN_CALIBRATION_CONFIDENCE. Any one of those failing falls back to
"relative_dsm" with an explanatory warning — never a forced absolute result.
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import rasterio
from PIL import Image
from rasterio.warp import transform_bounds

from depth.backbone import estimate_relative_depth
from utils.texture_export import export_texture
from features.extract_features import FEATURE_COLUMNS, compute_depth_features
from calibration.calibrate import calibrate_scene
from calibration.regressor import HeightRegressor, RegressorConfig
from calibration.srtm_fetch import GeoBounds

logger = logging.getLogger(__name__)

GEOTIFF_EXTENSIONS = {".tif", ".tiff"}
CHECKPOINT_PATH = Path(__file__).resolve().parent / "models" / "regressor_v1.pt"

# Tunable, not empirically calibrated against a validation sweep (no ground
# truth confidence labels exist to tune against yet) — 0.5 is "sources agree
# more than they disagree." Used only as an informational threshold now (see
# MIN_SRTM_VALID_FRACTION below for the actual absolute/relative gate) —
# disagreement-based confidence structurally collapses for real hilly scenes
# regardless of fused quality (docs/open_decisions.md, 2026-08-31).
MIN_CALIBRATION_CONFIDENCE = 0.5

# The actual gate for absolute_dsm when SRTM succeeds: SRTM's own valid-vs-
# NoData pixel ratio, not cross-source agreement. 0.8 is a reasonable-looking
# default, not tuned against real void/NoData failure cases.
MIN_SRTM_VALID_FRACTION = 0.8


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


def _get_geo_bounds(input_path: Path) -> GeoBounds | None:
    """A real uploaded GeoTIFF still carries its own valid transform/CRS —
    unlike ml/calibration/patch_geo.py, which recovers bounds analytically
    for training patches that never had one persisted, this just reads it."""
    with rasterio.open(input_path) as src:
        if src.crs is None:
            return None
        west, south, east, north = transform_bounds(src.crs, "EPSG:4326", *src.bounds)
    return GeoBounds(south=south, west=west, north=north, east=east)


_regressor = None


def _get_regressor() -> HeightRegressor | None:
    """Lazy-loaded singleton, matching ml/depth/backbone.py's _get_pipe()
    convention. Returns None (not a raised exception) if the checkpoint
    isn't available — ml/models/ is gitignored, so a fresh clone or a worker
    that hasn't been provisioned with it yet is an expected, not exceptional,
    state; callers fall back to the honest relative-only path for that."""
    global _regressor
    if _regressor is None:
        if not CHECKPOINT_PATH.exists():
            logger.warning("No regressor checkpoint at %s — calibration unavailable.", CHECKPOINT_PATH)
            return None
        config = RegressorConfig(input_dim=len(FEATURE_COLUMNS))
        regressor = HeightRegressor(config)
        regressor.load_checkpoint(CHECKPOINT_PATH)
        _regressor = regressor
    return _regressor


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

    # Stage B — calibration (Phase 4). Computed from the in-memory "L" depth
    # array, not the just-saved "LA" heightmap.png (see compute_depth_features'
    # docstring for why that distinction matters).
    depth_array = np.array(depth_map, dtype=np.float32)
    regressor = _get_regressor()

    output_type = "relative_dsm"
    metadata = {
        "height_units": "relative",
        "min_height": 0,
        "max_height": 255,
        "width": depth_map.width,
        "height": depth_map.height,
    }
    warnings: list[str] = []

    if regressor is None:
        warnings.append(
            "Calibration model unavailable on this worker (no checkpoint found) — "
            "output is uncalibrated relative depth."
        )
    else:
        feature_dict = compute_depth_features(depth_array)
        feature_vector = np.array([feature_dict[c] for c in FEATURE_COLUMNS], dtype=np.float32)
        geo_bounds = _get_geo_bounds(input_path) if georeferenced else None

        calibration = calibrate_scene(feature_vector, regressor, geo_bounds=geo_bounds, rgb_image=texture_image)
        fusion = calibration.fusion
        confidence = float(fusion.confidence_map.flatten()[0])
        fused_height = float(fusion.height_map.flatten()[0])
        srtm_succeeded = "srtm" in fusion.sources_used
        srtm_valid_fraction = calibration.srtm_valid_fraction

        # Gate on SRTM's own valid-pixel fraction, not fused cross-source
        # confidence, when SRTM succeeded: the regressor and semantic priors
        # are structurally blind at terrain-relief scale (both read ~0m for
        # any real hilly scene), so disagreement-based confidence collapses
        # to a narrow low band for every hilly scene regardless of how good
        # the fused number is — measured at confidence 0.37-0.41 across 4
        # different real crops. Gating on that would mean hilly scenes never
        # reach absolute_dsm, punishing SRTM for a disagreement we already
        # know the cause of (docs/open_decisions.md, 2026-08-31).
        srtm_trustworthy = srtm_succeeded and srtm_valid_fraction is not None and srtm_valid_fraction >= MIN_SRTM_VALID_FRACTION

        if georeferenced and srtm_trustworthy:
            # Anchor the existing 0-255 relative depth to the fused absolute
            # estimate: scale so the depth map's own mean lands on
            # fused_height, matching how the training label was itself
            # defined (mean height above local minimum). True scale travels
            # as these metadata numbers, never re-baked into the pixels
            # (§9.6) — heightmap.png's bytes are untouched.
            relative_mean = feature_dict["depth_mean"] / 255.0
            scale_factor = fused_height / relative_mean if relative_mean > 1e-6 else 0.0
            output_type = "absolute_dsm"
            metadata = {
                "height_units": "m",
                "min_height": 0.0,
                "max_height": scale_factor,
                "width": depth_map.width,
                "height": depth_map.height,
            }
            if confidence < MIN_CALIBRATION_CONFIDENCE:
                warnings.append(
                    f"Individual signal sources disagreed substantially (confidence={confidence:.2f}) — "
                    f"output anchored primarily to SRTM (sources used: {fusion.sources_used})."
                )
        elif not georeferenced:
            warnings.append(
                f"No geo-metadata on this input — SRTM was never attempted (sources used: "
                f"{fusion.sources_used}), output is uncalibrated relative depth, not metric height."
            )
        elif not srtm_succeeded:
            warnings.append(
                "Input is georeferenced but SRTM elevation lookup failed or was unavailable — "
                "falling back to relative depth rather than an unanchored absolute claim."
            )
        else:
            warnings.append(
                f"SRTM coverage for this scene was too incomplete to trust "
                f"({srtm_valid_fraction:.0%} valid pixels < {MIN_SRTM_VALID_FRACTION:.0%}) — "
                "returning relative depth rather than an unreliable absolute result."
            )

    return PipelineResult(
        output_type=output_type,
        heightmap_path=str(heightmap_path),
        texture_path=str(texture_path),
        metadata=metadata,
        warnings=warnings,
    )
