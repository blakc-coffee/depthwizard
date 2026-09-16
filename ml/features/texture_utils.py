"""Pure-numpy texture-pattern helpers, shared by extract_features.py (height
use case) and extract_river_silt_features.py (silt use case).

Split into their own dependency-free module 2026-09-16 after a real crash:
extract_features.py imports depth.backbone/calibration.semantic_priors at
module level, which pull in torch — and torch + xgboost loaded in the same
process segfaults on macOS (duplicate OpenMP runtime, reproduced directly:
`import torch; import xgboost; XGBRegressor().load_model(...)` crashes with
SIGSEGV). The river-silt pipeline only ever needed these three functions,
never torch — importing them via extract_features.py pulled torch in
transitively and crashed ml/river_silt_pipeline.py the moment it tried to
load its XGBoost checkpoint. These functions have zero torch dependency of
their own; moving them here breaks that transitive chain permanently,
instead of an import-order/env-var workaround (KMP_DUPLICATE_LIB_OK was
tried first and did not fix it).
"""

from __future__ import annotations

import numpy as np


def edge_density(depth: np.ndarray) -> float:
    """Fraction of pixels whose Sobel gradient magnitude exceeds its own
    scene's mean+std. Decoupled from raw gradient magnitude (depth_grad_std
    already captures that) — this captures *pattern*: a scene with a few
    strong, isolated edges (buildings, ridgelines) reads differently here
    than one with the same aggregate roughness spread diffusely (canopy
    noise), per ml/depth/PHASE1_NOTES.md's documented failure mode. Pure
    numpy — no scipy/cv2 available in ml/requirements.txt."""
    padded = np.pad(depth, 1, mode="edge")
    gx = (
        -padded[:-2, :-2] + padded[:-2, 2:]
        - 2 * padded[1:-1, :-2] + 2 * padded[1:-1, 2:]
        - padded[2:, :-2] + padded[2:, 2:]
    )
    gy = (
        -padded[:-2, :-2] - 2 * padded[:-2, 1:-1] - padded[:-2, 2:]
        + padded[2:, :-2] + 2 * padded[2:, 1:-1] + padded[2:, 2:]
    )
    magnitude = np.sqrt(gx ** 2 + gy ** 2)
    threshold = magnitude.mean() + magnitude.std()
    return float((magnitude > threshold).mean())


def freq_high_ratio(depth: np.ndarray) -> float:
    """Fraction of 2D FFT magnitude energy sitting in the outer 75% of the
    frequency radius. Canopy-noise texture shows up as high-frequency energy
    with no coherent structure; clean terrain/ridgelines are low-frequency
    dominant — same Phase 1 failure mode as edge_density, viewed from the
    frequency domain instead of the spatial one."""
    magnitude = np.abs(np.fft.fftshift(np.fft.fft2(depth)))
    h, w = depth.shape
    cy, cx = h / 2.0, w / 2.0
    y, x = np.ogrid[:h, :w]
    radius = np.sqrt((y - cy) ** 2 + (x - cx) ** 2)
    max_radius = np.sqrt(cy ** 2 + cx ** 2)
    high_mask = radius >= 0.25 * max_radius
    total = magnitude.sum()
    return float(magnitude[high_mask].sum() / total) if total > 0 else 0.0


def local_entropy(depth: np.ndarray, grid: int = 4, bins: int = 16) -> float:
    """Mean Shannon entropy of the pixel-value histogram over a grid of
    blocks (4x4 by default — works down to very small patches since block
    size is derived from the array's own shape, not fixed). A third way of
    looking at the same pattern-vs-magnitude question as edge_density and
    freq_high_ratio: a block of uniformly noisy canopy texture has a flatter
    local histogram (high entropy) than a block of the same std spent on a
    single clean edge (low entropy, most pixels on one side or the other).
    Pure numpy — no scipy/skimage available in ml/requirements.txt."""
    h, w = depth.shape
    bh, bw = max(1, h // grid), max(1, w // grid)
    entropies = []
    for i in range(0, h, bh):
        for j in range(0, w, bw):
            block = depth[i:i + bh, j:j + bw]
            if block.size == 0:
                continue
            hist, _ = np.histogram(block, bins=bins)
            probs = hist[hist > 0] / hist.sum()
            entropies.append(-np.sum(probs * np.log2(probs)))
    return float(np.mean(entropies)) if entropies else 0.0
