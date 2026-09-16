#!/usr/bin/env python3
"""River-silt use case — multispectral feature extraction.

Combines the existing RGB color/texture features (extract_river_silt_features.py,
kept as-is — cheap, already computed, no reason to drop) with real reflectance
band means and literature band ratios from fetch_river_silt_multispectral.py's
raw B2/B3/B4/B5/B8/B11/B12 crops. This is the direct test of the literature-
review hypothesis: docs/open_decisions.md's 2026-09-14 entries found RGB-only
features flat-lined near R^2=0 regardless of sample size (315 -> 1532 rows) —
if that was a feature-representation ceiling, not a data-size one, real
reflectance + NIR/SWIR-based ratios should move it.

Run from the repo root, after fetch_river_silt_multispectral.py:
    python ml/features/extract_river_silt_multispectral_features.py
"""

import csv
import random
import re
import sys
from pathlib import Path

import numpy as np
import rasterio

_ML_DIR = Path(__file__).resolve().parent.parent
if str(_ML_DIR) not in sys.path:
    sys.path.insert(0, str(_ML_DIR))

from features.extract_river_silt_features import compute_koppen_features, compute_river_silt_features  # noqa: E402
from features.extract_river_silt_features import FEATURE_COLUMNS as RGB_FEATURE_COLUMNS  # noqa: E402
from features.extract_river_silt_features import MAX_PLAUSIBLE_SSC_MG_L  # noqa: E402

DEFAULT_MANIFEST = "ml/data/river_silt_raw/imagery_manifest.csv"
DEFAULT_MS_DIR = "ml/data/river_silt_raw/imagery_multispectral"
DEFAULT_FEATURES_DIR = "ml/data/river_silt_raw/features_multispectral"
SPLIT_RATIOS = (0.7, 0.15, 0.15)
LABEL_COLUMN = "ssc_value"

# Sentinel-2 SR band order this project's fetch script requests, see
# fetch_river_silt_multispectral.py's BANDS constant — must match exactly,
# rasterio reads bands in request order, not by name.
MS_BAND_ORDER = ["blue", "green", "red", "rededge", "nir", "swir1", "swir2"]
REFLECTANCE_SCALE = 10000.0  # Sentinel-2 SR's native int16 scaling factor

MS_FEATURE_COLUMNS = [
    "ms_blue_mean", "ms_green_mean", "ms_red_mean", "ms_rededge_mean",
    "ms_nir_mean", "ms_swir1_mean", "ms_swir2_mean",
    "ms_blue_red_ratio", "ms_blue_green_ratio", "ms_red_green_ratio",
    "ms_nir_red_ratio", "ms_ndti_nir", "ms_water_fraction",
]
FEATURE_COLUMNS = RGB_FEATURE_COLUMNS + MS_FEATURE_COLUMNS

MNDWI_THRESHOLD = 0.0  # standard water/non-water cutoff for modified NDWI (Xu 2006)
MIN_WATER_FRACTION = 0.05  # below this, the mask is untrustworthy (tiny/no river in frame) — fall back to whole-crop


def compute_water_mask(green: np.ndarray, swir1: np.ndarray, threshold: float = MNDWI_THRESHOLD) -> np.ndarray:
    """Modified NDWI (Xu 2006): (green - swir1) / (green + swir1). Water
    pixels read positive, built-up/bare-soil/vegetation read negative — the
    literature-standard way to isolate water before computing turbidity
    stats, so bank/vegetation pixels in the crop don't dilute the signal
    (docs/open_decisions.md, 2026-09-14 literature-review entry).

    Fixed global threshold — kept as-is for backward compatibility and
    simple/predictable test behavior. Real-data visual review (2026-09-14)
    found this threshold silently zeroes out real, visible rivers: for a
    narrow, tree-shadowed stream, mixed-pixel contamination (water + canopy
    + shadow within one 10m Sentinel-2 pixel) never pushes mNDWI above 0.0
    anywhere in the crop, even though the *relative* signal (river vs its
    surroundings) is real and spatially coherent — confirmed by inspecting
    the top-1%-mNDWI pixels of a real failing crop, which traced the actual
    visible river channel almost exactly. See compute_adaptive_water_mask()
    for the fix actually used in the feature-extraction pipeline now."""
    eps = 1e-4
    mndwi = (green - swir1) / (green + swir1 + eps)
    return mndwi > threshold


def _otsu_threshold(values: np.ndarray, bins: int = 256) -> float:
    """Pure-numpy Otsu's method (no scipy/cv2/skimage, per this project's
    existing constraint) — picks the threshold that maximizes between-class
    variance of a 1D value array, i.e. the split that best separates two
    populations in the array's own histogram, whatever their absolute
    values happen to be. This is the adaptive alternative to a fixed global
    cutoff: it finds "unusually high mNDWI for *this* scene" rather than
    "mNDWI above a value calibrated for open, easily-resolved water"."""
    hist, edges = np.histogram(values, bins=bins)
    hist = hist.astype(np.float64)
    centers = (edges[:-1] + edges[1:]) / 2.0

    weight1 = np.cumsum(hist)
    weight2 = np.cumsum(hist[::-1])[::-1]
    # Avoid 0/0 at the extremes (all-below or all-above splits) — those
    # split points just get filled with -inf so argmax never picks them.
    with np.errstate(invalid="ignore", divide="ignore"):
        mean1 = np.cumsum(hist * centers) / weight1
        mean2 = (np.cumsum((hist * centers)[::-1])[::-1]) / weight2

    inter_class_variance = weight1[:-1] * weight2[1:] * (mean1[:-1] - mean2[1:]) ** 2
    inter_class_variance = np.nan_to_num(inter_class_variance, nan=-np.inf)
    if not np.any(np.isfinite(inter_class_variance)) or inter_class_variance.max() <= 0:
        return float(values.max()) + 1.0  # degenerate/near-uniform input — threshold above everything, empty mask
    return float(centers[np.argmax(inter_class_variance)])


def compute_adaptive_water_mask(green: np.ndarray, swir1: np.ndarray, max_water_fraction: float = 0.3) -> np.ndarray:
    """Per-scene adaptive water mask via Otsu's method on that crop's own
    mNDWI histogram, instead of one fixed global threshold — the real fix
    for the narrow/shadowed-river failure mode documented above.

    Guarded, not blind: a real river in a wide crop is always a small
    minority of pixels (docs/open_decisions.md's crop-size-falsification
    entry already showed a correctly-detected river is only ~2-4% of a
    2.56km crop by geometry). If Otsu's split flags more than
    `max_water_fraction` of the crop as "water," that split is untrustworthy
    (e.g. a genuinely uniform scene with no water at all, where Otsu just
    bisects noise) — returns an all-False mask rather than mislabeling a
    large chunk of land as water."""
    eps = 1e-4
    mndwi = (green - swir1) / (green + swir1 + eps)
    threshold = _otsu_threshold(mndwi.ravel())
    mask = mndwi > threshold
    if mask.mean() > max_water_fraction:
        return np.zeros_like(mask, dtype=bool)
    return mask


def compute_multispectral_features(bands: np.ndarray, water_mask: np.ndarray | None = None) -> dict:
    """bands: (7, H, W) int16 array in MS_BAND_ORDER, Sentinel-2 SR's native
    x10000 scale. Ratios are mean-of-per-pixel-ratio, same convention as
    compute_river_silt_features(). If `water_mask` covers too little of the
    crop to trust (MIN_WATER_FRACTION), falls back to the whole crop rather
    than computing stats over a handful of pixels — same disqualify-don't-
    silently-degrade pattern as this project's other confidence gates
    (MIN_SRTM_VALID_FRACTION etc.)."""
    refl = {name: bands[i].astype(np.float32) / REFLECTANCE_SCALE for i, name in enumerate(MS_BAND_ORDER)}
    eps = 1e-4  # reflectance is ~0-1 scale here, unlike the 0-255 RGB crop — eps matched accordingly

    water_fraction = float(water_mask.mean()) if water_mask is not None else 1.0
    use_mask = water_mask if (water_mask is not None and water_fraction >= MIN_WATER_FRACTION) else None
    masked = {name: (arr[use_mask] if use_mask is not None else arr.ravel()) for name, arr in refl.items()}
    blue, green, red, nir = masked["blue"], masked["green"], masked["red"], masked["nir"]

    ndti_nir = (nir - red) / (nir + red + eps)  # NIR-based turbidity index, distinct from the RGB pull's NDTI

    return {
        "ms_blue_mean": float(blue.mean()), "ms_green_mean": float(green.mean()),
        "ms_red_mean": float(red.mean()), "ms_rededge_mean": float(masked["rededge"].mean()),
        "ms_nir_mean": float(nir.mean()), "ms_swir1_mean": float(masked["swir1"].mean()),
        "ms_swir2_mean": float(masked["swir2"].mean()),
        "ms_blue_red_ratio": float(((blue + eps) / (red + eps)).mean()),
        "ms_blue_green_ratio": float(((blue + eps) / (green + eps)).mean()),
        "ms_red_green_ratio": float(((red + eps) / (green + eps)).mean()),
        "ms_nir_red_ratio": float(((nir + eps) / (red + eps)).mean()),
        "ms_ndti_nir": float(ndti_nir.mean()),
        "ms_water_fraction": water_fraction,
    }


def _safe_id(site_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", site_id)


def build_feature_table(rows, ms_dir=DEFAULT_MS_DIR):
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
            lat, lon = float(row["lat"]), float(row["lon"])
        except (KeyError, ValueError):
            skipped.append((row.get("site_id", "?"), "missing/unparseable lat or lon"))
            continue

        ms_path = Path(ms_dir) / f"{_safe_id(row['site_id'])}.tif"
        if not ms_path.exists():
            skipped.append((row["site_id"], "no multispectral crop yet (pull still running or failed for this row)"))
            continue

        try:
            with rasterio.open(row["image_path"]) as src:
                rgb = src.read()[:3]
            with rasterio.open(ms_path) as src:
                ms_bands = src.read()
        except Exception as exc:
            skipped.append((row["site_id"], f"image read failed: {exc}"))
            continue
        if ms_bands.shape[0] != len(MS_BAND_ORDER):
            skipped.append((row["site_id"], f"expected {len(MS_BAND_ORDER)} MS bands, got {ms_bands.shape[0]}"))
            continue

        green = ms_bands[MS_BAND_ORDER.index("green")].astype(np.float32) / REFLECTANCE_SCALE
        swir1 = ms_bands[MS_BAND_ORDER.index("swir1")].astype(np.float32) / REFLECTANCE_SCALE
        water_mask = compute_adaptive_water_mask(green, swir1)

        features = {
            **compute_river_silt_features(rgb),
            **compute_koppen_features(lat, lon),
            **compute_multispectral_features(ms_bands, water_mask),
        }
        table.append({"site_id": row["site_id"], LABEL_COLUMN: ssc_value, **features})

    return table, skipped


def split_table(table, ratios=SPLIT_RATIOS, seed=42):
    shuffled = table.copy()
    random.Random(seed).shuffle(shuffled)
    n = len(shuffled)
    n_train, n_val = int(n * ratios[0]), int(n * ratios[1])
    return {"train": shuffled[:n_train], "val": shuffled[n_train:n_train + n_val], "test": shuffled[n_train + n_val:]}


def save_split(rows, path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["site_id", LABEL_COLUMN] + FEATURE_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def main():
    with open(DEFAULT_MANIFEST, newline="") as f:
        rows = list(csv.DictReader(f))
    print(f"{len(rows)} rows in {DEFAULT_MANIFEST}")

    table, skipped = build_feature_table(rows)
    print(f"{len(table)} combined RGB+multispectral feature rows built, {len(skipped)} skipped")
    reasons = {}
    for _, reason in skipped:
        key = reason.split("(")[0].strip()
        reasons[key] = reasons.get(key, 0) + 1
    for reason, count in reasons.items():
        print(f"  {count}x: {reason}")

    splits = split_table(table)
    for name, split_rows in splits.items():
        path = f"{DEFAULT_FEATURES_DIR}/features_{name}.csv"
        save_split(split_rows, path)
        print(f"  {name}: {len(split_rows)} rows -> {path}")


if __name__ == "__main__":
    main()
