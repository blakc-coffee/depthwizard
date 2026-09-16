#!/usr/bin/env python3
"""River-silt use case — standalone inference pipeline.

Mirrors ml/pipeline.py's role for the height use case: the one function
backend wiring calls, self-contained, no backend imports (ml/ stays
standalone per this project's convention).

Chunk 3 (gauge-anchor fusion) and Chunk 4 (dense heatmap) now both wired in:

- **Chunk 3**: if the input is georeferenced, checks silt_gauge_anchor.py for
  a real, live, nearby USGS SSC reading. Found -> that real measurement
  IS the output (output_type="absolute_ssc"), not blended with the model —
  ground truth beats a model estimate, same as SRTM overriding the height
  regressor when valid. Not found (the common case — see that module's own
  measured scarcity finding) -> falls back to the model prediction,
  output_type stays "relative_silt_index", same honesty discipline as the
  height pipeline's absolute_dsm gating.
- **Chunk 4**: the heatmap is no longer uniform. Trend (the scalar SSC
  value, anchor or model) sets the scene's overall level; per-pixel NDTI
  (compute_ndti_map(), real RGB-derived signal, not fabricated) sets local
  variation around it — same trend+detail composition principle as
  ml/calibration/dense_fusion.py's SRTM+relative-depth split. Honest
  caveat, stated in warnings: a generic RGB-only upload has no
  multispectral bands to build a real water mask from, so this pattern
  spans the whole image, not just water pixels — it shows real relative
  color variation, not a verified water boundary.

Run standalone via tools/run_river_silt_pipeline.py — no infra needed.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import rasterio
from PIL import Image
from rasterio.warp import transform_bounds

_ML_DIR = Path(__file__).resolve().parent
if str(_ML_DIR) not in sys.path:
    sys.path.insert(0, str(_ML_DIR))

from features.extract_river_silt_features import (  # noqa: E402
    FEATURE_COLUMNS, compute_koppen_features, compute_ndti_map, compute_river_silt_features,
)
from features.koppen_climate import KOPPEN_GROUPS  # noqa: E402
from calibration.silt_gauge_anchor import GaugeAnchor, find_gauge_anchor  # noqa: E402

import xgboost  # noqa: E402

DEFAULT_CHECKPOINT = _ML_DIR / "models" / "river_silt_regressor_xgb_v1.json"  # CWD-independent, matches ml/pipeline.py's own pattern
# Real measured SSC distribution (ml/data/river_silt_raw/imagery_manifest.csv,
# 7276 rows post-MAX_PLAUSIBLE_SSC_MG_L cap, 2026-09-16): p99~900 mg/L. Used
# as the heatmap's normalization ceiling — a real max would let one extreme
# station compress every ordinary reading toward black.
HEATMAP_NORMALIZATION_CEILING_MG_L = 900.0
DETAIL_GAIN = 60.0  # how strongly per-pixel NDTI variation perturbs the trend value, in 0-255 units — unvalidated, a visual-only choice, not measured against real per-pixel ground truth (none exists)
# Real bug found and fixed 2026-09-16: encoding trend directly as 0-255
# meant a low (common) predicted SSC left almost no positive headroom for
# per-pixel detail variation before clipping at 0 — measured on a real image,
# 54% of pixels clipped to exactly black. TREND_MARGIN reserves headroom at
# both ends so detail is visible regardless of the trend value.
TREND_MARGIN = 40.0

MODEL_QUALITY_WARNING = (
    "The underlying SSC regressor's typical (median) error is a few mg/L on "
    "held-out real data, but it cannot detect elevated/flood-condition SSC from a "
    "single static image with no temporal context (docs/open_decisions.md, "
    "2026-09-16) — treat this as a rough estimate for a typical-conditions reading, "
    "not a reliable flood/event detector."
)
DENSE_HEATMAP_CAVEAT = (
    "Heatmap spatial pattern comes from per-pixel color (NDTI) variation across the "
    "whole image, not a verified water mask — a generic RGB-only upload has no "
    "multispectral bands to detect water reliably (an RGB-only \"blueness\" water-mask "
    "heuristic was tried and measured unreliable: 24-71% false-positive coverage "
    "across 5 real test images, vs. a real river's ~2-4% of a similar-size crop — "
    "see docs/open_decisions.md). Shows real relative color variation, not confirmed "
    "water-only turbidity structure."
)
CROSS_SECTION_CAVEAT = (
    "Cross-section shape is derived from real per-pixel image variation (NDTI "
    "profile) and the predicted SSC level, not a measured riverbed survey — it "
    "preserves the river's real relative shape/skeleton but is not a literal "
    "bathymetric reconstruction."
)

# Real, measured tercile thresholds from training data (docs/open_decisions.md,
# ml/data/river_silt_raw/features/features_train.csv, n=5884, 2026-09-16) — NOT
# an engineering/regulatory dredging standard (no such standard was sourced or
# fabricated). These mark where a reading falls relative to the real global
# distribution of river SSC this project's own dataset actually observed:
# roughly bottom third / middle third / top third of real rivers worldwide.
DREDGING_LOW_THRESHOLD_MG_L = 7.2   # p33 of real training data
DREDGING_HIGH_THRESHOLD_MG_L = 20.0  # p66 of real training data


def compute_dredging_indicator(ssc_mg_l: float) -> tuple[str, str]:
    """Returns (level, label). level in {"low","moderate","high"} for
    frontend styling; label is the human-readable recommendation. Thresholds
    are real percentiles of this project's own training data (see constants
    above) — an honest relative-to-observed-range signal, not a claim of
    engineering authority on when dredging is actually required."""
    if ssc_mg_l < DREDGING_LOW_THRESHOLD_MG_L:
        return "low", "No dredging indicated — sediment level is in the lower third of observed rivers."
    if ssc_mg_l < DREDGING_HIGH_THRESHOLD_MG_L:
        return "moderate", "Monitor — sediment level is mid-range; consider scheduling an inspection."
    return "high", "Dredging likely warranted — sediment level is in the upper third of observed rivers."


def compute_cross_section_profile(ndti_map: np.ndarray, n_points: int = 48) -> list[float]:
    """Collapses the per-pixel NDTI map into a 1D across-channel profile by
    averaging along the vertical axis, resampled to n_points and normalized
    to 0-1 — a real, image-derived shape (preserves the river's actual
    relative cross-channel variation, not fabricated from nothing), used as
    the frontend 3D cross-section's sediment-height skeleton. Explicitly not
    a real bathymetric survey — see CROSS_SECTION_CAVEAT."""
    column_means = ndti_map.mean(axis=0)  # collapse height -> one value per horizontal position
    resampled = np.interp(
        np.linspace(0, len(column_means) - 1, n_points),
        np.arange(len(column_means)),
        column_means,
    )
    lo, hi = resampled.min(), resampled.max()
    normalized = np.zeros_like(resampled) if hi <= lo else (resampled - lo) / (hi - lo)
    return [float(v) for v in normalized]


def _anchor_warning(anchor: GaugeAnchor) -> str:
    return (
        f"Anchored to a real USGS gauge reading: {anchor.site_name} (site {anchor.site_id}), "
        f"{anchor.distance_km:.1f} km away, {anchor.age_hours:.1f} hours old."
    )


def get_image_center_latlon(image_path: str) -> tuple[float, float] | None:
    """Returns (lat, lon) of the image's center for a georeferenced input,
    None for a plain JPG/PNG with no CRS — same distinction ml/pipeline.py's
    absolute_dsm gating already makes for height."""
    with rasterio.open(image_path) as src:
        if src.crs is None:
            return None
        west, south, east, north = transform_bounds(src.crs, "EPSG:4326", *src.bounds)
    return (south + north) / 2.0, (west + east) / 2.0


@dataclass
class SiltPipelineResult:
    output_type: str  # "absolute_ssc" when a real gauge anchor was found, else "relative_silt_index"
    predicted_ssc_mg_l: float
    heatmap_path: str
    texture_path: str
    dredging_level: str = "low"  # "low" | "moderate" | "high" — see compute_dredging_indicator()
    dredging_label: str = ""
    cross_section_profile: list[float] = field(default_factory=list)  # 0-1 normalized, see compute_cross_section_profile()
    warnings: list[str] = field(default_factory=list)


def load_rgb_uint8(image_path: str) -> np.ndarray:
    """Reads any raster (JPG/PNG/GeoTIFF) and returns a (3, H, W) uint8
    array — real uploads aren't guaranteed to already be uint8 (a
    georeferenced source could be uint16), so min-max rescale when needed
    rather than assuming."""
    with rasterio.open(image_path) as src:
        arr = src.read()
    if arr.shape[0] < 3:
        raise ValueError(f"{image_path}: expected >=3 bands, got {arr.shape[0]}")
    rgb = arr[:3]
    if rgb.dtype != np.uint8:
        lo, hi = rgb.min(), rgb.max()
        rgb = np.zeros_like(rgb, dtype=np.uint8) if hi <= lo else \
            ((rgb.astype(np.float32) - lo) / (hi - lo) * 255).astype(np.uint8)
    return rgb


def run_silt_pipeline(image_path: str, workdir: str, checkpoint_path: str | Path = DEFAULT_CHECKPOINT) -> SiltPipelineResult:
    rgb = load_rgb_uint8(image_path)
    latlon = get_image_center_latlon(image_path)
    # Non-georeferenced input has no coordinates to classify — honest
    # all-zero Köppen one-hot (no region known), same "disqualify, don't
    # guess" pattern as everywhere else, not a crash (real bug found and
    # fixed 2026-09-16: this feature merge was missing entirely before).
    koppen_features = compute_koppen_features(*latlon) if latlon is not None else {f"silt_koppen_{g}": 0.0 for g in KOPPEN_GROUPS}
    features = {**compute_river_silt_features(rgb), **koppen_features}
    X = np.array([[features[col] for col in FEATURE_COLUMNS]], dtype=np.float32)

    model = xgboost.XGBRegressor()
    model.load_model(str(checkpoint_path))
    model_predicted = max(0.0, float(np.expm1(model.predict(X)[0])))  # trained on log1p, SSC can't be physically negative

    # Chunk 3: a real, live, nearby gauge reading beats the model outright —
    # only checked for georeferenced input, and only fires in practice for
    # the rare case a real SSC (not turbidity) sensor exists nearby and
    # fresh (silt_gauge_anchor.py's own measured scarcity finding).
    warnings: list[str] = []
    output_type = "relative_silt_index"
    predicted = model_predicted
    if latlon is not None:
        anchor = find_gauge_anchor(*latlon)
        if anchor is not None:
            output_type = "absolute_ssc"
            predicted = anchor.ssc_mg_l
            warnings.append(_anchor_warning(anchor))
    if output_type == "relative_silt_index":
        warnings.append(MODEL_QUALITY_WARNING)

    # Chunk 4: trend (the scalar SSC value above) sets overall heatmap
    # level, per-pixel NDTI sets real spatial variation around it — see
    # module docstring for the trend+detail reasoning and its honest limits.
    _, h, w = rgb.shape
    intensity = np.clip(predicted / HEATMAP_NORMALIZATION_CEILING_MG_L, 0.0, 1.0)
    trend_255 = TREND_MARGIN + intensity * (255.0 - 2 * TREND_MARGIN)
    ndti_map = compute_ndti_map(rgb)
    detail = (ndti_map - ndti_map.mean()) * DETAIL_GAIN
    heatmap = np.clip(trend_255 + detail, 0, 255).astype(np.uint8)
    warnings.append(DENSE_HEATMAP_CAVEAT)

    dredging_level, dredging_label = compute_dredging_indicator(predicted)
    cross_section_profile = compute_cross_section_profile(ndti_map)
    warnings.append(CROSS_SECTION_CAVEAT)

    os.makedirs(workdir, exist_ok=True)
    heatmap_path = os.path.join(workdir, "silt_heatmap.png")
    Image.fromarray(heatmap, mode="L").save(heatmap_path)

    texture_path = os.path.join(workdir, "silt_texture.png")
    Image.fromarray(np.transpose(rgb, (1, 2, 0))).save(texture_path)

    return SiltPipelineResult(
        output_type=output_type,
        predicted_ssc_mg_l=predicted,
        heatmap_path=heatmap_path,
        texture_path=texture_path,
        dredging_level=dredging_level,
        dredging_label=dredging_label,
        cross_section_profile=cross_section_profile,
        warnings=warnings,
    )
