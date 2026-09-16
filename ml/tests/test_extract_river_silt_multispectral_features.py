import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "features"))
from extract_river_silt_multispectral_features import (  # noqa: E402
    MS_FEATURE_COLUMNS, build_feature_table, compute_adaptive_water_mask, compute_multispectral_features,
    compute_water_mask, split_table,
)


def test_compute_multispectral_features_returns_all_columns():
    bands = np.random.randint(0, 4000, size=(7, 16, 16)).astype(np.int16)
    features = compute_multispectral_features(bands)
    assert set(features.keys()) == set(MS_FEATURE_COLUMNS)
    assert all(np.isfinite(v) for v in features.values())


def test_compute_water_mask_flags_water_not_land():
    # Water: green > swir1 (mNDWI positive). Land: swir1 > green (negative).
    green = np.full((8, 8), 0.15, dtype=np.float32)
    swir1_water = np.full((8, 8), 0.03, dtype=np.float32)
    swir1_land = np.full((8, 8), 0.35, dtype=np.float32)

    assert compute_water_mask(green, swir1_water).all()
    assert not compute_water_mask(green, swir1_land).any()


def test_compute_multispectral_features_falls_back_when_water_fraction_too_low():
    """A mask covering almost none of the crop (e.g. a river barely in
    frame) must not be trusted — falls back to whole-crop stats rather than
    computing means over a handful of pixels."""
    bands = np.random.randint(1000, 3000, size=(7, 16, 16)).astype(np.int16)
    sparse_mask = np.zeros((16, 16), dtype=bool)
    sparse_mask[0, 0] = True  # 1/256 = 0.4%, well under MIN_WATER_FRACTION

    masked_result = compute_multispectral_features(bands, water_mask=sparse_mask)
    whole_crop_result = compute_multispectral_features(bands, water_mask=None)
    assert masked_result["ms_blue_mean"] == whole_crop_result["ms_blue_mean"]
    assert masked_result["ms_water_fraction"] < 0.05


def test_compute_multispectral_features_detects_high_turbidity_nir_shift():
    """Turbid water reflects more strongly in NIR than clear water (the
    literature-cited reason RGB alone saturates for high-SSC water) — a
    higher NIR/red ratio and NDTI-NIR should follow."""
    turbid = np.zeros((7, 8, 8), dtype=np.int16)
    turbid[4] = 1800  # nir
    turbid[2] = 900   # red

    clear = np.zeros((7, 8, 8), dtype=np.int16)
    clear[4] = 300   # nir
    clear[2] = 400   # red

    turbid_features = compute_multispectral_features(turbid)
    clear_features = compute_multispectral_features(clear)

    assert turbid_features["ms_nir_red_ratio"] > clear_features["ms_nir_red_ratio"]
    assert turbid_features["ms_ndti_nir"] > clear_features["ms_ndti_nir"]


def test_compute_adaptive_water_mask_recovers_a_narrow_river_below_the_fixed_threshold():
    """Real failure mode found via visual review (docs/open_decisions.md,
    2026-09-14): a narrow, tree-shadowed river never pushes mNDWI above the
    fixed 0.0 threshold anywhere in the crop, even though it reads
    relatively higher than its surroundings. Build a synthetic scene with
    exactly that shape — a thin "river" strip with slightly less negative
    mNDWI than a uniform negative background — and confirm the adaptive
    mask recovers it while the fixed-threshold mask misses it entirely."""
    size = 32
    green = np.full((size, size), 0.08, dtype=np.float32)
    swir1 = np.full((size, size), 0.26, dtype=np.float32)  # background: strongly non-water, matches real data
    # A narrow "river" column: still net-negative mNDWI (real mixed-pixel
    # case), just less negative than the background.
    swir1[:, 14:18] = 0.12

    fixed_mask = compute_water_mask(green, swir1)
    adaptive_mask = compute_adaptive_water_mask(green, swir1)

    assert not fixed_mask.any()  # the exact failure mode found on real data
    assert adaptive_mask[:, 14:18].all()  # river strip recovered
    assert not adaptive_mask[:, :10].any()  # background correctly left unmarked


def test_compute_adaptive_water_mask_returns_empty_on_uniform_scene():
    """No real split exists in a genuinely uniform scene — Otsu shouldn't
    bisect noise into a fake 50/50 water/non-water split."""
    green = np.full((16, 16), 0.1, dtype=np.float32)
    swir1 = np.full((16, 16), 0.3, dtype=np.float32)
    mask = compute_adaptive_water_mask(green, swir1)
    assert not mask.any()


def test_compute_adaptive_water_mask_rejects_majority_water_splits():
    """A split that flags a large fraction of the crop as 'water' is
    untrustworthy by this project's own crop-size-vs-real-river-width
    finding (a real river is always a small minority of a wide crop) — the
    max_water_fraction guard must reject it rather than trust Otsu blindly."""
    green = np.zeros((20, 20), dtype=np.float32)
    swir1 = np.zeros((20, 20), dtype=np.float32)
    green[:, :12] = 0.05   # 60% of the crop reads as the "high mNDWI" half
    green[:, 12:] = 0.30
    swir1[:, :] = 0.15

    mask = compute_adaptive_water_mask(green, swir1, max_water_fraction=0.3)
    assert not mask.any()


def test_build_feature_table_skips_rows_missing_multispectral_crop(tmp_path):
    rows = [{"site_id": "no_ms_file", "ssc_value": "5.0", "image_path": "irrelevant.tif"}]
    table, skipped = build_feature_table(rows, ms_dir=str(tmp_path))
    assert table == []
    assert len(skipped) == 1
    assert skipped[0][0] == "no_ms_file"


def test_split_table_covers_every_row_exactly_once():
    table = [{"site_id": str(i)} for i in range(100)]
    splits = split_table(table, seed=7)
    all_rows = splits["train"] + splits["val"] + splits["test"]
    assert len(all_rows) == 100
    assert {row["site_id"] for row in all_rows} == {str(i) for i in range(100)}
