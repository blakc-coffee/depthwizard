"""Multi-Source Elevation Fusion & Confidence Estimation — Phase 4 Calibration Module.

Fuses multi-modal height estimators:
1. SRTM (coarse regional baseline / AGL ground truth)
2. Semantic Land-Cover Priors (class-conditional distribution)
3. Depth Anything Regressor (fine-grained relative-to-absolute metric depth)

Calculates an explicit, mathematically sound confidence map derived from spatial
inter-estimator disagreement (variance / standard deviation of source estimates).

Frozen interface per Phase 4 specification.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Sequence

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class FusionResult:
    """Output package of the multi-source fusion engine."""

    height_map: np.ndarray        # (H, W) float32 fused absolute/metric height in meters
    confidence_map: np.ndarray    # (H, W) float32 confidence scores in [0.0, 1.0]
    disagreement_map: np.ndarray  # (H, W) float32 spatial standard deviation among sources (m)
    variance_map: np.ndarray      # (H, W) float32 fused theoretical variance (m^2)
    sources_used: list[str] = field(default_factory=list)

    @property
    def shape(self) -> tuple[int, int]:
        return self.height_map.shape


def _broadcast_to_shape(arr: np.ndarray | float | None, shape: tuple[int, int], name: str) -> np.ndarray | None:
    """Broadcast scalar or 2D array to target (H, W) shape."""
    if arr is None:
        return None
    if isinstance(arr, (int, float)):
        return np.full(shape, float(arr), dtype=np.float32)
    arr_np = np.asarray(arr, dtype=np.float32)
    if arr_np.ndim == 0:
        return np.full(shape, float(arr_np), dtype=np.float32)
    if arr_np.shape != shape:
        raise ValueError(f"Shape mismatch for {name}: expected {shape}, got {arr_np.shape}")
    return arr_np


def fuse_height_estimates(
    srtm_estimate: np.ndarray | float | None = None,
    semantic_estimate: np.ndarray | float | None = None,
    regressor_estimate: np.ndarray | float | None = None,
    srtm_variance: np.ndarray | float = 16.0,      # Default SRTM 1-sigma ~4m -> Var = 16 m^2
    semantic_variance: np.ndarray | float = 25.0,  # Default Semantic prior 1-sigma ~5m -> Var = 25 m^2
    regressor_variance: np.ndarray | float = 9.0,  # Default Regressor 1-sigma ~3m -> Var = 9 m^2
    disagreement_scale: float = 10.0,              # Characteristic decay scale tau in meters
) -> FusionResult:
    """Fuse multi-source height estimates with explicit disagreement-based confidence.

    Mathematical formulation
    ------------------------
    Let K be the set of active (non-null, finite) estimators at pixel (y, x).
    For each source k in K with estimate h_k and variance sigma_k^2:
      1. Inverse-variance weight: w_k = 1 / sigma_k^2
      2. Total weight: W = sum_{k in K} w_k
      3. Fused height: mu(y, x) = sum_{k in K} (w_k * h_k) / W
      4. Weighted disagreement (spatial sample std dev):
           sigma_disagree(y, x) = sqrt( sum_{k in K} w_k * (h_k - mu)^2 / W )
      5. Coverage ratio: C_cov(y, x) = |K| / K_max  (where K_max = 3)
      6. Confidence score:
           Confidence(y, x) = C_cov(y, x) * exp( - sigma_disagree(y, x) / tau )
         where tau = disagreement_scale (default 10.0m).

    Parameters
    ----------
    srtm_estimate : np.ndarray | float | None
        SRTM elevation map (H, W) or scalar in meters.
    semantic_estimate : np.ndarray | float | None
        Semantic prior height map (H, W) or scalar in meters.
    regressor_estimate : np.ndarray | float | None
        Depth regressor predicted height map (H, W) or scalar in meters.
    srtm_variance : np.ndarray | float
        Prior variance for SRTM estimates (default 16.0 m^2).
    semantic_variance : np.ndarray | float
        Prior variance for semantic estimates (default 25.0 m^2).
    regressor_variance : np.ndarray | float
        Prior variance for regressor estimates (default 9.0 m^2).
    disagreement_scale : float
        Characteristic scale (tau) in meters for exponential confidence decay.

    Returns
    -------
    FusionResult
        Package with fused height map, confidence map, disagreement map, and variance.
    """
    candidates = [srtm_estimate, semantic_estimate, regressor_estimate]
    shape: tuple[int, int] | None = None
    for cand in candidates:
        if cand is not None and isinstance(cand, np.ndarray) and cand.ndim >= 2:
            shape = cand.shape[:2]
            break
    if shape is None:
        shape = (1, 1)

    h_srtm = _broadcast_to_shape(srtm_estimate, shape, "srtm_estimate")
    h_sem = _broadcast_to_shape(semantic_estimate, shape, "semantic_estimate")
    h_reg = _broadcast_to_shape(regressor_estimate, shape, "regressor_estimate")

    var_srtm = _broadcast_to_shape(srtm_variance, shape, "srtm_variance")
    var_sem = _broadcast_to_shape(semantic_variance, shape, "semantic_variance")
    var_reg = _broadcast_to_shape(regressor_variance, shape, "regressor_variance")

    sources_used: list[str] = []
    source_items = [
        ("srtm", h_srtm, var_srtm),
        ("semantic", h_sem, var_sem),
        ("regressor", h_reg, var_reg),
    ]

    for name, h_arr, _ in source_items:
        if h_arr is not None:
            sources_used.append(name)

    if not sources_used:
        raise ValueError("At least one height estimate source must be provided to fuse_height_estimates.")

    total_possible_sources = 3.0

    fused_height = np.zeros(shape, dtype=np.float32)
    sum_weights = np.zeros(shape, dtype=np.float32)
    source_counts = np.zeros(shape, dtype=np.float32)

    valid_masks = {}
    weights_dict = {}

    for name, h_arr, var_arr in source_items:
        if h_arr is None or var_arr is None:
            continue
        valid = ~np.isnan(h_arr) & ~np.isnan(var_arr) & (var_arr > 1e-6)
        valid_masks[name] = valid
        w = np.zeros(shape, dtype=np.float32)
        w[valid] = 1.0 / var_arr[valid]
        weights_dict[name] = w

        fused_height[valid] += (w[valid] * h_arr[valid])
        sum_weights[valid] += w[valid]
        source_counts[valid] += 1.0

    has_weights = sum_weights > 0
    fused_height[has_weights] /= sum_weights[has_weights]
    fused_height[~has_weights] = np.nan

    fused_variance = np.zeros(shape, dtype=np.float32)
    fused_variance[has_weights] = 1.0 / sum_weights[has_weights]
    fused_variance[~has_weights] = np.nan

    weighted_diff_sq = np.zeros(shape, dtype=np.float32)

    for name, h_arr, _ in source_items:
        if name not in weights_dict:
            continue
        valid = valid_masks[name] & has_weights
        diff = h_arr[valid] - fused_height[valid]
        weighted_diff_sq[valid] += weights_dict[name][valid] * (diff ** 2)

    disagreement_map = np.zeros(shape, dtype=np.float32)
    multi_mask = (source_counts > 1) & has_weights
    disagreement_map[multi_mask] = np.sqrt(weighted_diff_sq[multi_mask] / sum_weights[multi_mask])

    single_mask = (source_counts == 1) & has_weights
    disagreement_map[single_mask] = np.sqrt(fused_variance[single_mask])

    tau = max(float(disagreement_scale), 1e-3)
    coverage_ratio = source_counts / total_possible_sources

    confidence_map = np.zeros(shape, dtype=np.float32)
    confidence_map[has_weights] = coverage_ratio[has_weights] * np.exp(
        -disagreement_map[has_weights] / tau
    )
    confidence_map = np.clip(confidence_map, 0.0, 1.0)

    return FusionResult(
        height_map=fused_height,
        confidence_map=confidence_map,
        disagreement_map=disagreement_map,
        variance_map=fused_variance,
        sources_used=sources_used,
    )


def test_fusion_logic() -> None:
    """Unit test for fusion logic and confidence mathematical properties."""
    print("Testing multi-source elevation fusion engine...")

    h_srtm = np.full((64, 64), 15.0, dtype=np.float32)
    h_sem = np.full((64, 64), 15.0, dtype=np.float32)
    h_reg = np.full((64, 64), 15.0, dtype=np.float32)

    res_perfect = fuse_height_estimates(
        srtm_estimate=h_srtm,
        semantic_estimate=h_sem,
        regressor_estimate=h_reg,
    )

    print(f"Case 1 (Perfect Agreement): Mean fused height = {res_perfect.height_map.mean():.2f}m, Confidence = {res_perfect.confidence_map.mean():.4f}")
    assert np.allclose(res_perfect.height_map, 15.0, atol=1e-4)
    assert np.allclose(res_perfect.disagreement_map, 0.0, atol=1e-4)
    assert np.allclose(res_perfect.confidence_map, 1.0, atol=1e-3)
    assert res_perfect.sources_used == ["srtm", "semantic", "regressor"]

    h_srtm_diff = np.full((64, 64), 0.0, dtype=np.float32)
    h_sem_diff = np.full((64, 64), 30.0, dtype=np.float32)
    h_reg_diff = np.full((64, 64), 60.0, dtype=np.float32)

    res_disagree = fuse_height_estimates(
        srtm_estimate=h_srtm_diff,
        semantic_estimate=h_sem_diff,
        regressor_estimate=h_reg_diff,
        disagreement_scale=10.0,
    )

    print(f"Case 2 (High Disagreement): Disagreement std = {res_disagree.disagreement_map.mean():.2f}m, Confidence = {res_disagree.confidence_map.mean():.4f}")
    assert res_disagree.disagreement_map.mean() > 15.0
    assert res_disagree.confidence_map.mean() < 0.25

    res_partial = fuse_height_estimates(
        srtm_estimate=None,
        semantic_estimate=h_sem,
        regressor_estimate=h_reg,
    )
    print(f"Case 3 (Partial 2/3 Sources): Coverage = 2/3, Confidence = {res_partial.confidence_map.mean():.4f}")
    assert np.allclose(res_partial.confidence_map, 2.0 / 3.0, atol=1e-3)
    assert "srtm" not in res_partial.sources_used

    print("All fusion logic tests passed successfully!")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test_fusion_logic()
