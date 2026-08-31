"""Phase 4 Chunk 2 — the calibration orchestrator.

The single function Phase 4 was actually supposed to deliver: combine the
trained regressor, SRTM (when the scene is georeferenced), and semantic
priors into one height estimate + confidence, via fusion.fuse_height_estimates().

Operates at the same granularity Phase 3 trained the regressor at: one
scalar height estimate per scene (a depth map's summary statistics), not a
dense per-pixel height field. Turning this scalar into ml/pipeline.py's
dense heightmap output is Chunk 3's job, per docs/phase4.md's own chunk
boundaries — this chunk is about the estimate being correct, not about
pixel-level rendering.

Georeferenced/non-georeferenced branching (docs/depthwizard.md §7 Phase 4):
SRTM is only ever attempted when geo_bounds is not None. There is no
"try SRTM, fall back on failure" path for a scene with no coordinates at
all — that's not a fetch failure, it's the scene never having had a
location to look up in the first place.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
from PIL import Image

from calibration.fusion import FusionResult, fuse_height_estimates
from calibration.regressor import HeightRegressor
from calibration.semantic_priors import get_semantic_height_priors, segment_image
from calibration.srtm_fetch import GeoBounds, fetch_srtm_elevation
from features.extract_features import FEATURE_COLUMNS

logger = logging.getLogger(__name__)

_DEPTH_GRAD_STD_IDX = FEATURE_COLUMNS.index("depth_grad_std")
# Measured on real held-out non-hilly test data (docs/open_decisions.md,
# 2026-08-31): scenes with noisier depth-map texture (high depth_grad_std —
# e.g. forest canopy occlusion, per ml/depth/PHASE1_NOTES.md's own
# documented failure mode) have ~3x the regressor's error variance of
# clean-textured scenes. A continuous least-squares fit of squared-error vs
# depth_grad_std was tried first and rejected: R^2 = 0.007 (too noisy/
# outlier-dominated) and it produced a negative "variance" at low
# percentiles. A robust 2-bin split on the real median is what's actually
# supported by the data.
# Re-measured 2026-08-31 five times: after depth_edge_density/depth_freq_high_ratio,
# after depth_local_entropy + the height_min/height_max auxiliary-loss heads,
# after Task 2's semantic segmentation features, and again after the ADE20K
# interior-object keyword fix + semantic-cache regeneration (docs/
# open_decisions.md, docs/phase_optimization.md). Threshold is stable across
# all five schema/retrain versions (depth_grad_std's own values never
# changed — neither adding unrelated feature columns nor changing the
# segmentation keyword map touches it); variances drift each retrain since
# predictions shift even on old rows.
# History: 7.226/22.146 (11 features) -> 6.965/20.112 (13) -> 6.841/20.027 (14)
# -> 7.052/17.710 (18, pre-keyword-fix) -> 6.537/18.778 (18, current).
_TEXTURE_VARIANCE_THRESHOLD = 2.751  # median depth_grad_std, real non-hilly test set
_TEXTURE_LOW_VARIANCE = 6.537        # measured MSE below threshold
_TEXTURE_HIGH_VARIANCE = 18.778      # measured MSE at/above threshold


def _texture_adaptive_regressor_variance(depth_features: np.ndarray) -> float:
    """Regressor reliability varies with depth-map texture noise, not just
    with terrain type. Only meaningful when SRTM is unavailable — the
    with-SRTM regime is already dominated by SRTM's own tiny variance
    regardless of texture, so this is never applied there."""
    grad_std = float(depth_features[_DEPTH_GRAD_STD_IDX])
    return _TEXTURE_HIGH_VARIANCE if grad_std >= _TEXTURE_VARIANCE_THRESHOLD else _TEXTURE_LOW_VARIANCE


@dataclass
class CalibrationResult:
    """calibrate_scene()'s return: the fused estimate plus SRTM's own
    fetch-quality signal, kept separate from the fused confidence.

    Why separate: fusion's confidence is driven by cross-source
    disagreement, but for real hilly terrain the regressor and semantic
    priors are *structurally* blind (see fuse's docstring below) — 2 of 3
    sources read near-zero for any real terrain-relief scene regardless of
    how good SRTM's answer is, so disagreement-based confidence collapses
    to a narrow low band for every hilly scene, not just unreliable ones
    (measured: 4 different real crops all landed at confidence 0.37-0.41).
    Gating output_type on that would mean hilly scenes never reach
    absolute_dsm no matter how good the fused number is — punishing SRTM
    for a disagreement we already know the cause of. `srtm_valid_fraction`
    (SRTM's own valid-vs-NoData pixel ratio) is an independent, SRTM-only
    reliability signal ml/pipeline.py can gate on instead when SRTM is the
    scene's dominant source. See docs/open_decisions.md, 2026-08-31.
    """

    fusion: FusionResult
    srtm_valid_fraction: float | None  # None if SRTM wasn't attempted or the fetch failed


def _srtm_relative_height_estimate(geo_bounds: GeoBounds) -> tuple[float | None, float | None]:
    """Mean height-relative-to-local-minimum within a patch's footprint —
    matching the exact label definition ml/data/ingest_supplementary.py
    trains on (subtract the patch's own elevation minimum, then average),
    not the patch's overall relief span (max-min). These are different
    physical quantities — max-min answers "how much does elevation vary
    here," mean-of-relative answers "what's the typical height above this
    patch's local floor," which is what the regressor's height_mean target
    actually is. Conflating them was a real bug found while validating this
    chunk against real data: it produced SRTM estimates ~3x too large and
    made fusion's error *worse* than the regressor alone (docs/
    open_decisions.md, 2026-08-31).

    Returns (estimate, valid_pixel_fraction) — both None if the fetch fails.
    valid_pixel_fraction is SRTM's own internal reliability signal (how much
    of the fetched tile is real data vs NoData/void), independent of
    whether other sources happen to agree with it."""
    try:
        tile = fetch_srtm_elevation(geo_bounds)
    except Exception as exc:
        logger.warning("SRTM fetch failed for %s: %s", geo_bounds, exc)
        return None, None

    valid_fraction = float(tile.valid_mask.mean())
    valid = tile.valid_elevation
    if len(valid) == 0:
        return None, valid_fraction
    return float((valid - valid.min()).mean()), valid_fraction


def _semantic_estimate(rgb_image: Image.Image) -> float | None:
    """Scene-level semantic height prior — mean of the per-pixel class-prior
    map (ml/calibration/semantic_priors.py), collapsed to one scalar to
    match the scalar granularity everything else here operates at."""
    try:
        class_map = segment_image(rgb_image)
        mean_map, _, _, _ = get_semantic_height_priors(class_map)
    except Exception as exc:
        logger.warning("Semantic segmentation failed: %s", exc)
        return None
    return float(mean_map.mean())


def calibrate_scene(
    depth_features: np.ndarray,
    regressor: HeightRegressor,
    geo_bounds: GeoBounds | None = None,
    rgb_image: Image.Image | None = None,
    srtm_variance: float = 16.0,
    semantic_variance: float = 38.9,
    regressor_variance_with_srtm: float = 100.0,
    regressor_variance_without_srtm: float | None = None,
    disagreement_scale: float | None = None,
) -> CalibrationResult:
    """image in (already reduced to depth-map features) -> fused height + confidence out.

    `regressor_variance` is conditional on whether SRTM is present, not one
    fixed number — measured on real held-out test data (docs/
    open_decisions.md, 2026-08-31), the regressor's true error variance is
    wildly bimodal: ~14.7 m² on non-hilly terrain (urban/forested/sparse)
    vs ~15,379 m² on hilly. A single fixed variance cannot represent both:

    - When SRTM succeeds, `regressor_variance_with_srtm=100.0` (deliberately
      far above `srtm_variance` — the regressor cannot distinguish a
      400m-relief hilly scene from a ~0m-height flat one, an information
      limit, not a training bug, so treating it as more confident than SRTM
      was wrong for exactly the scenes SRTM is best at correcting). Kept at
      the already-validated 100 rather than the full measured ~15,379 — SRTM's
      own tiny variance already dominates fusion at either value, and 100 is
      the number Chunk 2's real held-out validation was run against.
    - When SRTM is unavailable (non-georeferenced input, the common case),
      `regressor_variance_without_srtm` defaults to `None`, which triggers
      `_texture_adaptive_regressor_variance()` — the regressor's real error
      varies ~3x with the scene's own depth-map texture noise (7.2 m² clean
      vs 22.1 m² noisy, e.g. forest canopy occlusion per ml/depth/
      PHASE1_NOTES.md), so a single fixed 14.7 was already an improvement
      over the old default of 100 but still averaged over two genuinely
      different reliability regimes. Pass an explicit float to override with
      a fixed value instead (matches `semantic_variance=38.9`, also
      measured — the old fixed default of 100 for this case was backwards:
      it made fusion trust the cruder semantic-prior heuristic ~4x more than
      a regressor that is actually ~2.6x *more* accurate for the common
      non-hilly scene).

    `disagreement_scale` (fusion.py's confidence-decay tau) defaults to None
    here and is picked adaptively from the estimates' own magnitude when
    unset — fusion.py's fixed tau=10.0 assumes building-height-scale
    disagreement (a few metres). On a real Himalayan test crop, regressor
    and semantic both landed near 0m while SRTM correctly reported ~1263m —
    627m of disagreement against tau=10 collapses confidence to ~5.6e-28,
    not just "low" but numerically meaningless, even though the fused
    estimate itself was a real improvement. A fixed absolute tau cannot
    serve both a ~5m-scale domain (urban) and a ~1000m-scale domain (hilly)
    at once (found 2026-08-31, docs/open_decisions.md).
    """
    regressor_estimate = float(regressor.predict(depth_features))

    srtm_estimate, srtm_valid_fraction = (
        _srtm_relative_height_estimate(geo_bounds) if geo_bounds is not None else (None, None)
    )
    semantic_estimate = _semantic_estimate(rgb_image) if rgb_image is not None else None

    if srtm_estimate is not None:
        regressor_variance = regressor_variance_with_srtm
    elif regressor_variance_without_srtm is not None:
        regressor_variance = regressor_variance_without_srtm
    else:
        regressor_variance = _texture_adaptive_regressor_variance(depth_features)

    if disagreement_scale is None:
        estimates = [e for e in (srtm_estimate, semantic_estimate, regressor_estimate) if e is not None]
        disagreement_scale = max(10.0, 0.5 * max((abs(e) for e in estimates), default=10.0))

    fusion = fuse_height_estimates(
        srtm_estimate=srtm_estimate,
        semantic_estimate=semantic_estimate,
        regressor_estimate=regressor_estimate,
        srtm_variance=srtm_variance,
        semantic_variance=semantic_variance,
        regressor_variance=regressor_variance,
        disagreement_scale=disagreement_scale,
    )
    return CalibrationResult(fusion=fusion, srtm_valid_fraction=srtm_valid_fraction)
