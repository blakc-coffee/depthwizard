#!/usr/bin/env python3
"""Relative-depth vs. ground-truth structure-agreement diff.

Dataset-auditing tool, not a runtime feature: it needs ground-truth height,
which only exists for manifest patches (the training/test set), never for a
real user upload. Use this to eyeball where the relative depth model
(ml/depth/backbone.py) and the real LiDAR/DEM truth disagree about *where
structure is*, independent of absolute scale (they're in different units and
were never expected to match numerically) — this catches things aggregate R²
numbers hide, e.g. a real finding from 2026-08-31 (docs/open_decisions.md):
DFC2019's truth height appears to score vegetation as ~0 (building-AGL-only
semantics), while the depth model reads tree canopy as "elevated" same as a
building — a real, systematic false-positive class in relative depth's
structure signal, not evenly distributed across terrain.

Both maps are reduced to a per-patch binary "elevated vs background" mask via
their own (mean + 0.5*std) threshold before comparing — comparing raw pixel
values directly would be meaningless (0-255 unitless depth vs. real meters).
This is about agreement on *where* structure is, not on absolute height.

Run from the repo root:
    python tools/depth_truth_diff.py --patch-id JAX_427_012_patch_1_3 --out review_samples
    python tools/depth_truth_diff.py --terrain urban --count 4 --out review_samples
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ML_DIR = REPO_ROOT / "ml"
if str(ML_DIR) not in sys.path:
    sys.path.insert(0, str(ML_DIR))

import numpy as np
import rasterio
from PIL import Image
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

DEFAULT_MANIFEST = REPO_ROOT / "data" / "processed" / "v1" / "manifest.json"
DEFAULT_DATA_ROOT = REPO_ROOT / "data" / "processed" / "v1"
DEFAULT_DEPTH_CACHE = REPO_ROOT / "data" / "processed" / "v1" / "depth_cache"


def _load_manifest(manifest_path=DEFAULT_MANIFEST):
    with open(manifest_path) as f:
        return json.load(f)


def _load_rgb(entry, data_root=DEFAULT_DATA_ROOT):
    with rasterio.open(data_root / entry["rgb_path"]) as src:
        bands = src.read()
        if bands.shape[0] == 1:
            bands = np.repeat(bands, 3, axis=0)
        return np.moveaxis(bands[:3], 0, -1).astype(np.uint8)


def _load_depth(entry, depth_cache=DEFAULT_DEPTH_CACHE):
    path = depth_cache / entry["split"] / entry["terrain_type"] / f"{entry['patch_id']}_depth.png"
    if not path.exists():
        raise FileNotFoundError(f"no cached depth map at {path} — run ml/features/extract_features.py first")
    return np.array(Image.open(path)).astype(np.float32)


def _load_truth(entry, data_root=DEFAULT_DATA_ROOT):
    with rasterio.open(data_root / entry["truth_path"]) as src:
        height = src.read(1).astype(np.float32)
        nodata = src.nodata
    valid = ~np.isnan(height)
    if nodata is not None:
        valid &= height != nodata
    return np.ma.masked_where(~valid, height)


def _elevated_mask(arr: np.ndarray) -> np.ndarray:
    """Per-map adaptive 'is this pixel structure, not background' threshold —
    mean + 0.5*std of the map's own valid pixels, same style of heuristic
    already used elsewhere in this codebase (e.g.
    ml/features/extract_features.py::_edge_density)."""
    valid = arr if not np.ma.is_masked(arr) else arr.compressed()
    threshold = valid.mean() + 0.5 * valid.std()
    return arr > threshold


def compute_diff(depth: np.ndarray, truth: np.ma.MaskedArray) -> dict:
    """Structure-agreement diff between relative depth and ground truth.

    Returns a dict with the 4-category confusion mask (uint8: 0=TN/background
    agree, 1=TP/both elevated, 2=FP/depth-only, 3=FN/truth-only) plus summary
    fractions over valid (non-masked-truth) pixels."""
    depth_elevated = _elevated_mask(depth)
    truth_elevated = _elevated_mask(truth)
    valid = ~np.ma.getmaskarray(truth)

    category = np.zeros(depth.shape, dtype=np.uint8)
    category[depth_elevated & truth_elevated] = 1   # TP
    category[depth_elevated & ~truth_elevated] = 2  # FP — depth flags structure truth doesn't
    category[~depth_elevated & truth_elevated] = 3  # FN — truth has structure depth misses
    category[~valid] = 0

    n_valid = valid.sum()
    return {
        "category": category,
        "tp_frac": float(((category == 1) & valid).sum() / n_valid) if n_valid else float("nan"),
        "fp_frac": float(((category == 2) & valid).sum() / n_valid) if n_valid else float("nan"),
        "fn_frac": float(((category == 3) & valid).sum() / n_valid) if n_valid else float("nan"),
    }


def render_comparison(entry, out_dir: Path, data_root=DEFAULT_DATA_ROOT, depth_cache=DEFAULT_DEPTH_CACHE):
    """4-panel PNG: RGB | relative depth | truth height | structure diff."""
    rgb = _load_rgb(entry, data_root)
    depth = _load_depth(entry, depth_cache)
    truth = _load_truth(entry, data_root)
    diff = compute_diff(depth, truth)

    fig, axes = plt.subplots(1, 4, figsize=(16, 4))

    axes[0].imshow(rgb)
    axes[0].set_title(f"{entry['terrain_type']} RGB\n{entry['patch_id']} ({entry['source']})")
    axes[0].axis("off")

    im1 = axes[1].imshow(depth, cmap="viridis")
    axes[1].set_title(f"relative depth\nmean={depth.mean():.1f} std={depth.std():.1f}")
    axes[1].axis("off")
    plt.colorbar(im1, ax=axes[1], fraction=0.046)

    im2 = axes[2].imshow(truth, cmap="terrain")
    axes[2].set_title(f"truth height (m)\nmean={truth.mean():.2f} std={truth.std():.2f}")
    axes[2].axis("off")
    plt.colorbar(im2, ax=axes[2], fraction=0.046)

    # 0=background(white) 1=TP(green) 2=FP-depth-only(red) 3=FN-truth-only(blue)
    from matplotlib.colors import ListedColormap

    diff_cmap = ListedColormap(["#f0f0f0", "#2ca02c", "#d62728", "#1f77b4"])
    axes[3].imshow(diff["category"], cmap=diff_cmap, vmin=0, vmax=3)
    axes[3].set_title(
        f"structure diff\nFP(red, depth-only)={diff['fp_frac']:.1%}  "
        f"FN(blue, truth-only)={diff['fn_frac']:.1%}"
    )
    axes[3].axis("off")

    plt.tight_layout()
    out_path = out_dir / f"{entry['terrain_type']}_{entry['patch_id']}_diff.png"
    plt.savefig(out_path, dpi=100)
    plt.close(fig)
    return out_path, diff


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--patch-id", help="Render one specific patch by patch_id")
    parser.add_argument("--terrain", help="Render N sample patches from this terrain_type (test split)")
    parser.add_argument("--count", type=int, default=4)
    parser.add_argument("--out", type=Path, default=REPO_ROOT / "review_samples")
    args = parser.parse_args()

    manifest = _load_manifest(args.manifest)
    args.out.mkdir(parents=True, exist_ok=True)

    if args.patch_id:
        entries = [e for e in manifest if e["patch_id"] == args.patch_id]
        if not entries:
            print(f"no manifest entry for patch_id={args.patch_id}")
            return 1
    elif args.terrain:
        candidates = [e for e in manifest if e.get("truth_path") and e["split"] == "test" and e["terrain_type"] == args.terrain]
        stride = max(1, len(candidates) // args.count)
        entries = candidates[::stride][: args.count]
    else:
        print("pass --patch-id or --terrain")
        return 1

    for entry in entries:
        out_path, diff = render_comparison(entry, args.out)
        print(f"{entry['patch_id']:<30} FP={diff['fp_frac']:.1%} FN={diff['fn_frac']:.1%} -> {out_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
