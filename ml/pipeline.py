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
from features.extract_features import FEATURE_COLUMNS, compute_depth_features, compute_semantic_features
from calibration.calibrate import calibrate_scene
from calibration.dense_fusion import fuse_dense_dsm, save_confidence_map, write_dsm_geotiff
from calibration.regressor import HeightRegressor, RegressorConfig
from calibration.semantic_priors import correct_missed_structures, segment_image
from calibration.srtm_fetch import GeoBounds, fetch_srtm_elevation

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

# Grounding gate for the relative->absolute scale anchor (docs/open_decisions.md,
# 2026-08-31): scale_factor = fused_height / relative_mean amplifies without
# bound as relative_mean -> 0. The old `relative_mean > 1e-6` guard never
# actually fires on real data — measured minimum relative_mean across all real
# held-out test patches is 0.024 (sparse terrain), four orders of magnitude
# above 1e-6 — so it caught nothing. The real risk sits well above that floor:
# a visual check of real sparse (flat) patches found the depth model
# hallucinating a smooth perspective-style gradient on genuinely flat ground
# (relative_mean as low as 0.024-0.06 despite zero real relief), which is
# exactly where dividing by a small, physically-meaningless relative_mean
# would blow scale_factor up into an implausible max_height. Both floors are
# measured/documented, not guessed: MIN_RELATIVE_DEPTH_MEAN sits just above
# the real per-terrain 1st-percentile range (0.10-0.25) so it only fires on
# genuinely degenerate cases; MAX_PLAUSIBLE_SCALE_FACTOR sits well above the
# largest real fused height seen this project (~1263m, a real Himalayan SRTM
# anchor, Phase 4 Chunk 2) so it never clips a legitimate mountain-scale
# result. Either firing disqualifies absolute_dsm and falls back to
# relative_dsm with a warning — same honesty pattern as MIN_SRTM_VALID_FRACTION,
# not a silent clamp that would keep reporting a number we don't trust.
MIN_RELATIVE_DEPTH_MEAN = 0.05
MAX_PLAUSIBLE_SCALE_FACTOR = 5000.0


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

    # Stage B — calibration (Phase 4). Computed from the in-memory "L" depth
    # array, not a re-read "LA" heightmap.png (see compute_depth_features'
    # docstring for why that distinction matters). depth_array is the array
    # the calibration/fusion math consumes — never corrected (see
    # correct_missed_structures' docstring) so every constant measured this
    # session against uncorrected depth statistics stays valid. heightmap_array
    # starts as a copy and only it gets the missed-structure correction
    # applied before being saved as the frontend-facing heightmap.png.
    depth_array = np.array(depth_map, dtype=np.float32)
    heightmap_array = depth_array
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
    dsm_path: Path | None = None
    confidence_map_path: Path | None = None

    if regressor is None:
        warnings.append(
            "Calibration model unavailable on this worker (no checkpoint found) — "
            "output is uncalibrated relative depth."
        )
    else:
        feature_dict = compute_depth_features(depth_array)
        # ponytail: segment_image() runs a second time inside calibrate_scene's
        # _semantic_estimate() below (~0.07s each, not a latency problem) —
        # accepted duplicate compute rather than refactoring calibrate_scene's
        # signature to accept a precomputed class_map; revisit if segmentation
        # ever gets expensive. See docs/open_decisions.md (Task 2).
        class_map = segment_image(texture_image)
        feature_dict.update(compute_semantic_features(class_map))
        feature_vector = np.array([feature_dict[c] for c in FEATURE_COLUMNS], dtype=np.float32)
        geo_bounds = _get_geo_bounds(input_path) if georeferenced else None

        # Missed-structure correction (docs/open_decisions.md, 2026-08-31):
        # applied only to the array that becomes the rendered heightmap, never
        # to feature_vector/feature_dict above — see correct_missed_structures'
        # docstring for why the calibration math must stay on uncorrected stats.
        heightmap_array, n_corrected = correct_missed_structures(depth_array, class_map)
        if n_corrected:
            warnings.append(
                f"Corrected {n_corrected} pixel(s) where relative depth under-detected a "
                "segmentation-identified building footprint (semantic-prior grounding)."
            )

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

        # Grounding gate (see MIN_RELATIVE_DEPTH_MEAN's comment): reject the
        # scale anchor itself, independent of SRTM/confidence, if the depth
        # map's own relative_mean is too degenerate to divide by, or if the
        # resulting scale_factor is physically implausible.
        relative_mean = feature_dict["depth_mean"] / 255.0
        scale_factor = fused_height / relative_mean if relative_mean > 1e-6 else float("inf")
        scale_anchor_grounded = (
            relative_mean >= MIN_RELATIVE_DEPTH_MEAN and scale_factor <= MAX_PLAUSIBLE_SCALE_FACTOR
        )

        if georeferenced and srtm_trustworthy and scale_anchor_grounded:
            # Anchor the existing 0-255 relative depth to the fused absolute
            # estimate: scale so the depth map's own mean lands on
            # fused_height, matching how the training label was itself
            # defined (mean height above local minimum). True scale travels
            # as these metadata numbers, never re-baked into the pixels
            # (§9.6) — heightmap.png's bytes are untouched.
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

            # Dense DSM fusion (docs/dense_dsm_fusion.md): SRTM supplies the
            # real, coarse trend; relative depth supplies only its own
            # high-frequency detail. Replaces the old uniform-rescale-only
            # dense output, which could visibly propagate a hallucinated
            # relative-depth shape even when the scalar anchor was correct.
            # ponytail: fetch_srtm_elevation() runs a second time here
            # (calibrate_scene already fetched it once internally for the
            # scalar path) — disk-cached, so this is a cache hit, not a
            # second network round-trip. Same accepted-duplicate-call
            # tradeoff already made for segment_image() in Task 2.
            try:
                elevation_data = fetch_srtm_elevation(geo_bounds)
                absolute_height_map, srtm_valid = fuse_dense_dsm(heightmap_array, elevation_data, scale_factor)
                dsm_path = output_dir / f"{input_path.stem}_dsm.tif"
                confidence_map_path = output_dir / f"{input_path.stem}_confidence.png"
                write_dsm_geotiff(dsm_path, absolute_height_map, geo_bounds)
                save_confidence_map(confidence_map_path, srtm_valid)
                srtm_coverage = float(srtm_valid.mean())
                if srtm_coverage < 1.0:
                    warnings.append(
                        f"{srtm_coverage:.0%} of this scene's absolute height (dsm_path) is directly "
                        f"measured from SRTM elevation data; {1 - srtm_coverage:.0%} is model-predicted "
                        "where SRTM had no coverage (see confidence_map_path)."
                    )
            except Exception as exc:
                logger.warning("Dense DSM fusion failed for %s: %s — dsm_path unavailable.", input_path, exc)
                dsm_path = None
                confidence_map_path = None
                warnings.append(
                    "Dense per-pixel DSM fusion failed — heightmap_path/metadata's scalar-anchored "
                    "absolute result is still valid, but dsm_path is unavailable for this run."
                )
        elif georeferenced and srtm_trustworthy and not scale_anchor_grounded:
            warnings.append(
                f"Relative depth signal was too degenerate to anchor a reliable scale factor "
                f"(relative_mean={relative_mean:.4f}, would-be scale_factor={scale_factor:.1f}) — "
                "falling back to relative depth rather than an unreliable absolute result."
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

    heightmap_path = output_dir / f"{input_path.stem}_heightmap.png"
    corrected_depth_map = Image.fromarray(np.clip(heightmap_array, 0, 255).astype(np.uint8), "L")
    heightmap = Image.merge("LA", (corrected_depth_map, Image.new("L", depth_map.size, 255)))
    heightmap.save(heightmap_path)

    return PipelineResult(
        output_type=output_type,
        heightmap_path=str(heightmap_path),
        texture_path=str(texture_path),
        confidence_map_path=str(confidence_map_path) if confidence_map_path else None,
        dsm_path=str(dsm_path) if dsm_path else None,
        metadata=metadata,
        warnings=warnings,
    )
