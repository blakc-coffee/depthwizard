#!/usr/bin/env python3
"""Phase 3 — dataset readiness check, batch depth-inference runner (Chunks
1-2), and scene-level feature extraction (Chunk 3).

Chunks 1-2 run Phase 1's frozen depth function (ml/depth/backbone.py, see
ml/depth/PHASE1_NOTES.md) over every trainable patch in Phase 2's manifest
(docs/phase2.md), caching the raw relative depth map per patch.

Chunk 3 converts those cached depth maps into the tabular feature+label
table Phase 4's calibration regressor actually trains on — see
ml/features/FEATURE_SCHEMA.md for the frozen column list and the reasoning
behind it. Running this script again after Chunk 2 has already completed is
cheap: the depth pass resumes into a no-op (everything's cached) and only
feature extraction — plain numpy over already-cached PNGs — does new work.

Resume-on-crash: a patch's cached output file existing on disk IS the
checkpoint. No separate state file to go stale — a killed run just skips
whatever's already on disk when restarted.

Run from the repo root (matches ml/data/preprocess.py's convention):
    python ml/features/extract_features.py --limit 30
"""

import argparse
import csv
import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import rasterio
from PIL import Image

# ml/features/ is not ml/ itself, so the flat sibling import below needs ml/
# on sys.path explicitly — same trick integration/pipeline_runner.py uses for
# ml/pipeline.py's own flat imports (see that module's docstring).
_ML_DIR = Path(__file__).resolve().parent.parent
if str(_ML_DIR) not in sys.path:
    sys.path.insert(0, str(_ML_DIR))

from depth.backbone import estimate_relative_depth_batch  # noqa: E402
from calibration.semantic_priors import CLASS_TO_IDX, SemanticClass, segment_image  # noqa: E402

DEFAULT_MANIFEST = "data/processed/v1/manifest.json"
DEFAULT_DATA_ROOT = "data/processed/v1"
DEFAULT_CACHE_DIR = "data/processed/v1/depth_cache"
DEFAULT_SEMANTIC_CACHE_DIR = "data/processed/v1/semantic_cache"
DEFAULT_FEATURES_PATH = "data/processed/v1/features/features_v1.csv"
EXPECTED_PATCH_SIZE = 256
REQUIRED_SPLITS = {"train", "val", "test"}

# Frozen Chunk 3 schema — Phase 4 builds directly against this column order.
# See ml/features/FEATURE_SCHEMA.md for what each column means and why.
METADATA_COLUMNS = ["patch_id", "split", "terrain_type", "source"]
DEPTH_FEATURE_COLUMNS = [
    "depth_min", "depth_max", "depth_mean", "depth_std",
    "depth_p10", "depth_p25", "depth_p50", "depth_p75", "depth_p90",
    "depth_grad_mean", "depth_grad_std",
    "depth_edge_density", "depth_freq_high_ratio", "depth_local_entropy",
]
# Added 2026-08-31 (Task 2, docs/phase_optimization.md): per-patch pixel
# fractions from ml/calibration/semantic_priors.py's segmentation, run on the
# patch's RGB image (not the depth map) — a legitimate, inference-available
# stand-in for terrain identity. ml/pipeline.py already runs this same
# segmentation at real inference time to build the semantic height prior, so
# this is genuinely available, unlike the ground-truth-derived `terrain_type`
# label (see docs/open_decisions.md's leakage finding).
SEMANTIC_FEATURE_COLUMNS = [
    "semantic_building_frac", "semantic_vegetation_frac",
    "semantic_road_frac", "semantic_other_frac",
]
FEATURE_COLUMNS = DEPTH_FEATURE_COLUMNS + SEMANTIC_FEATURE_COLUMNS
LABEL_COLUMNS = ["height_mean", "height_min", "height_max"]


def load_manifest(manifest_path=DEFAULT_MANIFEST):
    with open(manifest_path) as f:
        return json.load(f)


def verify_dataset_readiness(manifest, data_root=DEFAULT_DATA_ROOT, expected_patch_size=EXPECTED_PATCH_SIZE):
    """Chunk 1's acceptance check: confirm Phase 2's output is consumable
    before spending any GPU time on it. Raises AssertionError on the first
    problem found rather than silently proceeding on a bad dataset.

    'validation_only' (Bhuvan/Cartosat) entries have no ground-truth height
    label (docs/phase2.md Chunk 4) — Phase 3 trains features for the
    calibration regressor, so those entries are filtered out here, not
    processed as if they were trainable.
    """
    trainable = [e for e in manifest if e.get("truth_path")]
    if not trainable:
        raise AssertionError("manifest has no patches with a truth_path — nothing to train features from")

    missing_splits = REQUIRED_SPLITS - {e["split"] for e in trainable}
    if missing_splits:
        raise AssertionError(f"manifest is missing required split(s): {sorted(missing_splits)}")

    terrain_by_split = {}
    for e in trainable:
        terrain_by_split.setdefault(e["split"], set()).add(e["terrain_type"])
    for split in ("train", "val"):
        if not terrain_by_split.get(split):
            raise AssertionError(f"split '{split}' has no terrain-tagged patches")

    # Spot-check patch size on a sample rather than opening all patches —
    # Phase 2 already guarantees size; this only catches a stale or
    # mismatched dataset directory before Chunk 2's overnight run wastes
    # time on it.
    stride = max(1, len(trainable) // 20)
    sample = trainable[::stride][:20]
    for entry in sample:
        rgb_path = os.path.join(data_root, entry["rgb_path"])
        with rasterio.open(rgb_path) as src:
            if (src.width, src.height) != (expected_patch_size, expected_patch_size):
                raise AssertionError(
                    f"{rgb_path}: expected {expected_patch_size}x{expected_patch_size}, "
                    f"got {src.width}x{src.height}"
                )

    counts = {s: sum(e["split"] == s for e in trainable) for s in REQUIRED_SPLITS}
    print(
        f"Dataset ready: {len(trainable)} trainable patches {counts}, "
        f"{len(sample)} spot-checked at {expected_patch_size}x{expected_patch_size}."
    )
    return trainable


def _load_patch_image(rgb_path: str) -> Image.Image:
    """Read a patch tile as a PIL RGB image — the shape ml/depth/backbone.py expects."""
    with rasterio.open(rgb_path) as src:
        bands = src.read()  # (count, H, W)
    if bands.shape[0] == 1:
        bands = np.repeat(bands, 3, axis=0)
    rgb = np.moveaxis(bands[:3], 0, -1).astype(np.uint8)
    return Image.fromarray(rgb, "RGB")


def _output_path(cache_dir: str, entry: dict) -> str:
    return os.path.join(cache_dir, entry["split"], entry["terrain_type"], f"{entry['patch_id']}_depth.png")


def _semantic_output_path(cache_dir: str, entry: dict) -> str:
    return os.path.join(cache_dir, entry["split"], entry["terrain_type"], f"{entry['patch_id']}_classmap.png")


def run_batch_depth_extraction(
    entries,
    data_root=DEFAULT_DATA_ROOT,
    cache_dir=DEFAULT_CACHE_DIR,
    batch_size=8,
    limit=None,
    log_every=25,
):
    """Runs Phase 1's depth function over every entry. Resumable (skips
    already-cached output) and progress-logged (patches/total, ETA)."""
    if limit is not None:
        entries = entries[:limit]

    pending = [e for e in entries if not os.path.exists(_output_path(cache_dir, e))]
    already_done = len(entries) - len(pending)
    if already_done:
        print(f"Resuming: {already_done}/{len(entries)} patches already cached, skipping.")

    start = time.monotonic()
    processed = 0
    for i in range(0, len(pending), batch_size):
        batch = pending[i : i + batch_size]
        images = [_load_patch_image(os.path.join(data_root, e["rgb_path"])) for e in batch]
        depth_maps = estimate_relative_depth_batch(images)

        for entry, depth_map in zip(batch, depth_maps):
            out_path = _output_path(cache_dir, entry)
            os.makedirs(os.path.dirname(out_path), exist_ok=True)
            depth_map.save(out_path)

        processed += len(batch)
        if processed % log_every < batch_size or processed == len(pending):
            elapsed = time.monotonic() - start
            rate = processed / elapsed if elapsed > 0 else 0
            eta = (len(pending) - processed) / rate if rate > 0 else float("inf")
            print(
                f"  {already_done + processed}/{len(entries)} patches "
                f"({elapsed:.1f}s elapsed, {rate:.2f} patches/s, ETA {eta:.0f}s)"
            )

    print(f"Done: {len(entries)} total ({already_done} skipped, {processed} newly processed).")
    return {"total": len(entries), "skipped": already_done, "processed": processed}


def run_batch_semantic_extraction(
    entries,
    data_root=DEFAULT_DATA_ROOT,
    cache_dir=DEFAULT_SEMANTIC_CACHE_DIR,
    limit=None,
    log_every=25,
):
    """Runs the real segmentation model (ml/calibration/semantic_priors.py)
    over every entry's RGB patch, caching the class map. Resumable — a
    cached classmap PNG existing on disk IS the checkpoint, same convention
    as run_batch_depth_extraction. One call per patch (segment_image() takes
    a single image, unlike the depth model's batched call)."""
    if limit is not None:
        entries = entries[:limit]

    pending = [e for e in entries if not os.path.exists(_semantic_output_path(cache_dir, e))]
    already_done = len(entries) - len(pending)
    if already_done:
        print(f"Resuming: {already_done}/{len(entries)} patches already cached, skipping.")

    start = time.monotonic()
    for i, entry in enumerate(pending, 1):
        image = _load_patch_image(os.path.join(data_root, entry["rgb_path"]))
        class_map = segment_image(image)
        out_path = _semantic_output_path(cache_dir, entry)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        Image.fromarray(class_map, "L").save(out_path)

        if i % log_every == 0 or i == len(pending):
            elapsed = time.monotonic() - start
            rate = i / elapsed if elapsed > 0 else 0
            eta = (len(pending) - i) / rate if rate > 0 else float("inf")
            print(
                f"  {already_done + i}/{len(entries)} patches "
                f"({elapsed:.1f}s elapsed, {rate:.2f} patches/s, ETA {eta:.0f}s)"
            )

    print(f"Done: {len(entries)} total ({already_done} skipped, {len(pending)} newly processed).")
    return {"total": len(entries), "skipped": already_done, "processed": len(pending)}


def _edge_density(depth: np.ndarray) -> float:
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


def _freq_high_ratio(depth: np.ndarray) -> float:
    """Fraction of 2D FFT magnitude energy sitting in the outer 75% of the
    frequency radius. Canopy-noise texture shows up as high-frequency energy
    with no coherent structure; clean terrain/ridgelines are low-frequency
    dominant — same Phase 1 failure mode as _edge_density, viewed from the
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


def _local_entropy(depth: np.ndarray, grid: int = 4, bins: int = 16) -> float:
    """Mean Shannon entropy of the pixel-value histogram over a grid of
    blocks (4x4 by default — works down to very small patches since block
    size is derived from the array's own shape, not fixed). A third way of
    looking at the same pattern-vs-magnitude question as _edge_density and
    _freq_high_ratio: a block of uniformly noisy canopy texture has a flatter
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


def compute_depth_features(depth: np.ndarray) -> dict:
    """Summary statistics from a relative-depth array — the regressor's
    input features (never the raw pixel map itself, per docs/phase3.md).

    Computed over every pixel: Phase 1's frozen interface guarantees a dense,
    fully-valid uint8 output for any input (ml/depth/PHASE1_NOTES.md) — depth
    maps carry no NoData concept of their own, unlike the ground-truth patch.

    Takes a 2D array directly (not a path) so ml/pipeline.py can compute the
    exact same features from the in-memory single-channel depth map it
    already has — reading back its own saved "LA" heightmap.png instead
    would silently mix the always-255 alpha channel into every statistic.
    """
    depth = depth.astype(np.float32)
    grad = np.concatenate([np.abs(np.diff(depth, axis=0)).ravel(), np.abs(np.diff(depth, axis=1)).ravel()])
    p10, p25, p50, p75, p90 = np.percentile(depth, [10, 25, 50, 75, 90])
    return {
        "depth_min": float(depth.min()),
        "depth_max": float(depth.max()),
        "depth_mean": float(depth.mean()),
        "depth_std": float(depth.std()),
        "depth_p10": float(p10),
        "depth_p25": float(p25),
        "depth_p50": float(p50),
        "depth_p75": float(p75),
        "depth_p90": float(p90),
        "depth_grad_mean": float(grad.mean()),
        "depth_grad_std": float(grad.std()),
        "depth_edge_density": _edge_density(depth),
        "depth_freq_high_ratio": _freq_high_ratio(depth),
        "depth_local_entropy": _local_entropy(depth),
    }


def _depth_features(depth_path: str) -> dict:
    """Summary statistics from a cached relative-depth map PNG on disk."""
    return compute_depth_features(np.array(Image.open(depth_path)))


def compute_semantic_features(class_map: np.ndarray) -> dict:
    """Per-patch pixel fractions of each of segment_image()'s 4 canonical
    classes — a legitimate, RGB-derived terrain proxy (see
    SEMANTIC_FEATURE_COLUMNS's comment for why this isn't leakage, unlike
    the ground-truth-derived terrain_type label). Fractions sum to 1."""
    total = class_map.size
    return {
        "semantic_building_frac": float(np.sum(class_map == CLASS_TO_IDX[SemanticClass.BUILDING]) / total),
        "semantic_vegetation_frac": float(np.sum(class_map == CLASS_TO_IDX[SemanticClass.VEGETATION]) / total),
        "semantic_road_frac": float(np.sum(class_map == CLASS_TO_IDX[SemanticClass.ROAD]) / total),
        "semantic_other_frac": float(np.sum(class_map == CLASS_TO_IDX[SemanticClass.OTHER]) / total),
    }


def _semantic_features(classmap_path: str) -> dict:
    """Semantic pixel fractions from a cached class-map PNG on disk."""
    return compute_semantic_features(np.array(Image.open(classmap_path)))


def _height_label(truth_path: str):
    """Ground-truth regression target — mean height over the patch's valid
    pixels only (unlike depth features, truth patches can carry real NoData:
    DFC2019's own nodata value, or NODATA_SENTINEL for the ml/data/
    ingest_supplementary.py sources). Returns None if nothing in the patch
    is valid — happens on some heavily-padded edge patches.

    Excludes NaN independent of the `nodata` attribute: some DFC2019 tiles
    carry stray NaN pixels with `nodata` left unset, and `!=` never excludes
    NaN even when `nodata` IS set — see the matching fix + writeup in
    ml/data/preprocess.py::classify_terrain and docs/open_decisions.md
    (2026-08-31). classify_terrain() being fixed keeps new mislabeling from
    happening; this guards Chunk 3's own stats independent of that.
    """
    with rasterio.open(truth_path) as src:
        height = src.read(1).astype(np.float32)
        nodata = src.nodata
    valid = ~np.isnan(height)
    if nodata is not None:
        valid &= height != nodata
    if not valid.any():
        return None
    valid_h = height[valid]
    return {
        "height_mean": float(valid_h.mean()),
        "height_min": float(valid_h.min()),
        "height_max": float(valid_h.max()),
    }


def build_feature_table(entries, cache_dir=DEFAULT_CACHE_DIR, data_root=DEFAULT_DATA_ROOT, semantic_cache_dir=DEFAULT_SEMANTIC_CACHE_DIR):
    """One row per patch: metadata + depth-map features + semantic features +
    ground-truth label. Skips (and reports) patches missing any of: a cached
    depth map, a valid ground-truth pixel, or a cached semantic class map —
    never fabricates a value for any of them."""
    rows, skipped = [], []
    for entry in entries:
        depth_path = _output_path(cache_dir, entry)
        if not os.path.exists(depth_path):
            skipped.append((entry["patch_id"], "no cached depth map"))
            continue

        label = _height_label(os.path.join(data_root, entry["truth_path"]))
        if label is None:
            skipped.append((entry["patch_id"], "no valid ground-truth pixels"))
            continue

        semantic_path = _semantic_output_path(semantic_cache_dir, entry)
        if not os.path.exists(semantic_path):
            skipped.append((entry["patch_id"], "no cached semantic class map"))
            continue

        row = {col: entry[col] for col in METADATA_COLUMNS}
        row.update(_depth_features(depth_path))
        row.update(_semantic_features(semantic_path))
        row.update(label)
        rows.append(row)

    return rows, skipped


def save_feature_table(rows, path=DEFAULT_FEATURES_PATH):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fieldnames = METADATA_COLUMNS + FEATURE_COLUMNS + LABEL_COLUMNS
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def save_feature_table_by_split(rows, features_dir=None):
    """Chunk 4 — split the cache along the same train/val/test boundaries
    Phase 2 established, so Phase 4 loads exactly the rows it needs without
    filtering a monolithic file on every run. Returns {split: path}."""
    features_dir = features_dir or os.path.dirname(DEFAULT_FEATURES_PATH)
    by_split = {}
    for row in rows:
        by_split.setdefault(row["split"], []).append(row)

    paths = {}
    for split, split_rows in by_split.items():
        path = os.path.join(features_dir, f"features_{split}.csv")
        save_feature_table(split_rows, path)
        paths[split] = path
    return paths


def main():
    parser = argparse.ArgumentParser(description="Phase 3 — batch relative-depth feature extraction")
    parser.add_argument("--manifest", default=DEFAULT_MANIFEST)
    parser.add_argument("--data-root", default=DEFAULT_DATA_ROOT)
    parser.add_argument("--cache-dir", default=DEFAULT_CACHE_DIR)
    parser.add_argument("--semantic-cache-dir", default=DEFAULT_SEMANTIC_CACHE_DIR)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--limit", type=int, default=None, help="Cap patch count — Chunk 1's subset dry run")
    parser.add_argument("--features-out", default=DEFAULT_FEATURES_PATH)
    args = parser.parse_args()

    manifest = load_manifest(args.manifest)
    trainable = verify_dataset_readiness(manifest, data_root=args.data_root)
    if args.limit is not None:
        trainable = trainable[: args.limit]
    run_batch_depth_extraction(
        trainable,
        data_root=args.data_root,
        cache_dir=args.cache_dir,
        batch_size=args.batch_size,
    )

    print("\nExtracting semantic segmentation class maps (Task 2)...")
    run_batch_semantic_extraction(
        trainable,
        data_root=args.data_root,
        cache_dir=args.semantic_cache_dir,
    )

    print("\nExtracting scene-level features (Chunk 3)...")
    rows, skipped = build_feature_table(
        trainable, cache_dir=args.cache_dir, data_root=args.data_root, semantic_cache_dir=args.semantic_cache_dir
    )
    if skipped:
        print(f"  skipped {len(skipped)}/{len(trainable)} patches — showing first 5: {skipped[:5]}")

    nan_count = sum(1 for row in rows for col in FEATURE_COLUMNS + LABEL_COLUMNS if row[col] != row[col])
    depth_mean = np.array([row["depth_mean"] for row in rows])
    height_mean = np.array([row["height_mean"] for row in rows])
    correlation = float(np.corrcoef(depth_mean, height_mean)[0, 1]) if len(rows) > 1 else float("nan")

    save_feature_table(rows, args.features_out)
    print(f"  saved {len(rows)} feature rows to {args.features_out}")
    print(f"  NaN/missing values in feature table: {nan_count} (must be 0)")
    print(f"  sanity check — corr(depth_mean, height_mean) = {correlation:.3f} "
          f"(near-zero would suggest a bug, not just a weak signal)")

    print("\nSplitting feature cache by train/val/test (Chunk 4)...")
    split_paths = save_feature_table_by_split(rows)
    for split, path in sorted(split_paths.items()):
        print(f"  {split}: {sum(1 for r in rows if r['split'] == split)} rows -> {path}")


if __name__ == "__main__":
    main()
