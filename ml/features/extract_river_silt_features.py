#!/usr/bin/env python3
"""River-silt use case, Chunk 2 — turbidity feature extraction.

Reads ml/data/river_silt_raw/imagery_manifest.csv (built by
ml/data/fetch_river_silt_imagery.py: real Sentinel-2 RGB crop + real in-situ
SSC reading per row), computes a small RGB-derived turbidity feature vector
per image (color statistics, band ratios, texture — same pattern-vs-magnitude
texture trio already proven useful in ml/features/extract_features.py,
reused here rather than reinvented), and writes train/val/test feature CSVs
for ml/calibration/train_river_silt_regressor.py to train on.

No depth/segmentation model involved here — this is the CNN's *classical*
baseline, same role compute_depth_features() played before Phase 4's
regressor existed. Measure this honestly before reaching for a CNN (see
docs/phase_river_silt.md Chunk 2 — a CNN is worth it only if it beats this).

Run from the repo root:
    python ml/features/extract_river_silt_features.py
"""

import csv
import random
import sys
from pathlib import Path

import matplotlib.colors
import numpy as np
import rasterio

_ML_DIR = Path(__file__).resolve().parent.parent
if str(_ML_DIR) not in sys.path:
    sys.path.insert(0, str(_ML_DIR))

from features.texture_utils import edge_density as _edge_density  # noqa: E402
from features.texture_utils import freq_high_ratio as _freq_high_ratio  # noqa: E402
from features.texture_utils import local_entropy as _local_entropy  # noqa: E402
from features.koppen_climate import KOPPEN_GROUPS, get_koppen_group  # noqa: E402

DEFAULT_MANIFEST = "ml/data/river_silt_raw/imagery_manifest.csv"
DEFAULT_FEATURES_DIR = "ml/data/river_silt_raw/features"
SPLIT_RATIOS = (0.7, 0.15, 0.15)  # train, val, test
LABEL_COLUMN = "ssc_value"
# Real, measured cap, not guessed (docs/open_decisions.md, 2026-09-16): a
# single extreme test-set row (30,390 mg/L) was found to swing R^2
# dramatically depending on train/test placement — R^2 is normalized by
# target variance, and one row that large inflates the denominator enough
# to make the metric meaningless regardless of real predictive skill. The
# real distribution has a clean natural break: values run continuously up
# to 11,260 (a real, plausible severe-flood reading), then jump straight to
# 30,390+ — the top 4 rows (30390-52230) are a distinct population, most
# likely data errors or a different reporting convention, not the same kind
# of event as everything below the gap. Excludes 9/7285 rows (0.12%).
MAX_PLAUSIBLE_SSC_MG_L = 5000.0

KOPPEN_FEATURE_COLUMNS = [f"silt_koppen_{g}" for g in KOPPEN_GROUPS]
FEATURE_COLUMNS = [
    "silt_red_mean", "silt_green_mean", "silt_blue_mean",
    "silt_red_std", "silt_green_std", "silt_blue_std",
    "silt_brightness_mean", "silt_brightness_std",
    "silt_ndti_mean", "silt_red_blue_ratio", "silt_blue_green_ratio",
    "silt_edge_density", "silt_freq_high_ratio", "silt_local_entropy",
    "silt_hue_mean", "silt_saturation_mean", "silt_value_mean", "silt_saturation_std",
] + KOPPEN_FEATURE_COLUMNS


def compute_river_silt_features(rgb: np.ndarray) -> dict:
    """rgb: (3, H, W) uint8 array, band order R, G, B (rasterio's default
    read order, matches how fetch_river_silt_imagery.py wrote these tifs).

    Band ratios/NDTI computed as mean-of-per-pixel-ratio, not
    ratio-of-means — keeps a single very bright or very dark pixel from
    dominating the statistic the way a ratio-of-means would.
    """
    r, g, b = rgb[0].astype(np.float32), rgb[1].astype(np.float32), rgb[2].astype(np.float32)
    eps = 1.0  # avoid divide-by-zero on true-black pixels without materially skewing real ones (0-255 scale)
    brightness = 0.299 * r + 0.587 * g + 0.114 * b
    ndti = (r - g) / (r + g + eps)
    red_blue_ratio = (r + eps) / (b + eps)
    # Blue/green: literature-flagged as inversely correlated with turbidity
    # independent of NDTI/red-blue (SHAP finding, open PMC coastal-SSC study —
    # docs/open_decisions.md, 2026-09-14 "literature review" entry). Cheap to
    # add, not yet known whether it helps this dataset — measure, don't assume.
    blue_green_ratio = (b + eps) / (g + eps)

    return {
        "silt_red_mean": float(r.mean()), "silt_green_mean": float(g.mean()), "silt_blue_mean": float(b.mean()),
        "silt_red_std": float(r.std()), "silt_green_std": float(g.std()), "silt_blue_std": float(b.std()),
        "silt_brightness_mean": float(brightness.mean()), "silt_brightness_std": float(brightness.std()),
        "silt_ndti_mean": float(ndti.mean()), "silt_red_blue_ratio": float(red_blue_ratio.mean()),
        "silt_blue_green_ratio": float(blue_green_ratio.mean()),
        "silt_edge_density": _edge_density(brightness),
        "silt_freq_high_ratio": _freq_high_ratio(brightness),
        "silt_local_entropy": _local_entropy(brightness),
        **_hsv_features(rgb),
    }


def compute_ndti_map(rgb: np.ndarray) -> np.ndarray:
    """Per-pixel NDTI (red-green turbidity index), not just the scalar mean
    compute_river_silt_features() returns — used by ml/river_silt_pipeline.py
    (Chunk 4) as real per-pixel spatial detail for the dense heatmap, since a
    generic RGB-only user upload has no multispectral bands to build a real
    water mask from (see that module's docstring for the honesty caveat this
    implies)."""
    r, g = rgb[0].astype(np.float32), rgb[1].astype(np.float32)
    eps = 1.0
    return (r - g) / (r + g + eps)


def _hsv_features(rgb: np.ndarray) -> dict:
    """Hue/Saturation/Value features — the literature's own global SSC model
    (Prum/Lucchese/Gardner, docs/open_decisions.md 2026-09-14 research entry)
    uses HSV water-color features alongside raw reflectance, not tried here
    until now. matplotlib.colors.rgb_to_hsv is vectorized numpy under the
    hood — already a dependency (tools/depth_truth_diff.py), no new one
    needed. Hue is circular (0 and 1 are the same color) — averaged via unit
    vectors, not a naive arithmetic mean, so red water samples near the
    hue=0/1 wrap point don't cancel out to a false green/yellow mean."""
    rgb_float = np.transpose(rgb, (1, 2, 0)).astype(np.float32) / 255.0
    hsv = matplotlib.colors.rgb_to_hsv(rgb_float)
    hue, sat, val = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    hue_angle = hue * 2 * np.pi
    mean_hue = (np.arctan2(np.sin(hue_angle).mean(), np.cos(hue_angle).mean()) / (2 * np.pi)) % 1.0
    return {
        "silt_hue_mean": float(mean_hue),
        "silt_saturation_mean": float(sat.mean()),
        "silt_value_mean": float(val.mean()),
        "silt_saturation_std": float(sat.std()),
    }


def compute_koppen_features(lat: float, lon: float) -> dict:
    """One-hot Köppen climate group — a legitimate regional proxy, not raw
    lat/lon (see koppen_climate.py's module docstring for the full
    reasoning). All-zero when the lookup grid has no classification for
    that cell (rare — open ocean/polar interior), not guessed."""
    group = get_koppen_group(lat, lon)
    return {f"silt_koppen_{g}": float(g == group) for g in KOPPEN_GROUPS}


def load_manifest_rows(manifest_path):
    with open(manifest_path, newline="") as f:
        return list(csv.DictReader(f))


def build_feature_table(rows):
    """Computes features for every manifest row, skipping (and reporting,
    not silently dropping) any row whose image can't be read or whose SSC
    value isn't a real number."""
    table, skipped = [], []
    for row in rows:
        try:
            ssc_value = float(row[LABEL_COLUMN])
        except (ValueError, KeyError):
            skipped.append((row.get("site_id", "?"), "unparseable ssc_value"))
            continue
        if ssc_value > MAX_PLAUSIBLE_SSC_MG_L:
            skipped.append((row.get("site_id", "?"), f"ssc_value {ssc_value:.0f} exceeds MAX_PLAUSIBLE_SSC_MG_L "
                                                       f"({MAX_PLAUSIBLE_SSC_MG_L:.0f}) — excluded, not a real training target"))
            continue
        try:
            with rasterio.open(row["image_path"]) as src:
                rgb = src.read()
        except Exception as exc:  # a missing/corrupt file shouldn't kill the whole batch
            skipped.append((row.get("site_id", "?"), f"image read failed: {exc}"))
            continue
        if rgb.shape[0] < 3:
            skipped.append((row["site_id"], f"expected >=3 bands, got {rgb.shape[0]}"))
            continue

        try:
            lat, lon = float(row["lat"]), float(row["lon"])
        except (KeyError, ValueError):
            skipped.append((row.get("site_id", "?"), "missing/unparseable lat or lon"))
            continue

        features = {**compute_river_silt_features(rgb[:3]), **compute_koppen_features(lat, lon)}
        table.append({"site_id": row["site_id"], LABEL_COLUMN: ssc_value, **features})

    return table, skipped


def split_table(table, ratios=SPLIT_RATIOS, seed=42):
    shuffled = table.copy()
    random.Random(seed).shuffle(shuffled)
    n = len(shuffled)
    n_train = int(n * ratios[0])
    n_val = int(n * ratios[1])
    return {
        "train": shuffled[:n_train],
        "val": shuffled[n_train:n_train + n_val],
        "test": shuffled[n_train + n_val:],
    }


def save_split(rows, path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["site_id", LABEL_COLUMN] + FEATURE_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def main():
    rows = load_manifest_rows(DEFAULT_MANIFEST)
    print(f"{len(rows)} rows in {DEFAULT_MANIFEST}")

    table, skipped = build_feature_table(rows)
    print(f"{len(table)} feature rows built, {len(skipped)} skipped")
    for site_id, reason in skipped:
        print(f"  skipped {site_id}: {reason}")

    splits = split_table(table)
    for name, split_rows in splits.items():
        path = f"{DEFAULT_FEATURES_DIR}/features_{name}.csv"
        save_split(split_rows, path)
        print(f"  {name}: {len(split_rows)} rows -> {path}")


if __name__ == "__main__":
    main()
