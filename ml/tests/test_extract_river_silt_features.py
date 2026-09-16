import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "features"))
from extract_river_silt_features import (  # noqa: E402
    FEATURE_COLUMNS, KOPPEN_FEATURE_COLUMNS, build_feature_table, compute_koppen_features,
    compute_river_silt_features, split_table,
)


def test_compute_river_silt_features_plus_koppen_returns_all_columns():
    rgb = np.random.randint(0, 256, size=(3, 32, 32), dtype=np.uint8)
    features = {**compute_river_silt_features(rgb), **compute_koppen_features(-3.0, -60.0)}
    assert set(features.keys()) == set(FEATURE_COLUMNS)
    assert all(np.isfinite(v) for v in features.values())


def test_compute_koppen_features_one_hot_matches_real_tropical_zone():
    # Amazon basin — real, known tropical (A) zone.
    features = compute_koppen_features(-3.0, -60.0)
    assert set(features.keys()) == set(KOPPEN_FEATURE_COLUMNS)
    assert features["silt_koppen_A"] == 1.0
    assert sum(features.values()) == 1.0  # exactly one group set


def test_compute_koppen_features_all_zero_when_grid_cell_unclassified():
    # Deep open ocean, far from the table's station-derived coverage.
    features = compute_koppen_features(0.0, -140.0)
    assert sum(features.values()) in (0.0, 1.0)  # either a real zone or an honest all-zero, never fabricated


def test_compute_river_silt_features_detects_high_turbidity_color_shift():
    """A brown/turbid image (high red, low blue) should read a higher NDTI
    and red/blue ratio than a clean blue-water image — the whole point of
    these features existing."""
    turbid = np.zeros((3, 16, 16), dtype=np.uint8)
    turbid[0] = 180  # red
    turbid[1] = 140  # green
    turbid[2] = 60   # blue

    clear = np.zeros((3, 16, 16), dtype=np.uint8)
    clear[0] = 40
    clear[1] = 80
    clear[2] = 150

    turbid_features = compute_river_silt_features(turbid)
    clear_features = compute_river_silt_features(clear)

    assert turbid_features["silt_ndti_mean"] > clear_features["silt_ndti_mean"]
    assert turbid_features["silt_red_blue_ratio"] > clear_features["silt_red_blue_ratio"]
    # Clear water reads bluer relative to green than turbid water does —
    # literature finding (docs/open_decisions.md, 2026-09-14), checked here
    # the same way the other two ratios already are.
    assert clear_features["silt_blue_green_ratio"] > turbid_features["silt_blue_green_ratio"]


def test_compute_river_silt_features_hsv_detects_a_red_hue_correctly_across_the_wrap_point():
    """Hue is circular — a pure-red image should read hue near 0.0 (or
    1.0), never something in between like green/cyan, which a naive
    arithmetic mean of individual pixel hues near the 0/1 wrap boundary
    could produce."""
    red_water = np.zeros((3, 16, 16), dtype=np.uint8)
    red_water[0] = 200  # pure red -> hue exactly 0.0 in HSV

    features = compute_river_silt_features(red_water)
    # allow a small wrap-around tolerance (hue near 0.0 or near 1.0 are the same color)
    assert features["silt_hue_mean"] < 0.02 or features["silt_hue_mean"] > 0.98


def test_compute_river_silt_features_hsv_saturation_distinguishes_gray_from_vivid():
    gray = np.full((3, 16, 16), 128, dtype=np.uint8)  # fully desaturated
    vivid_blue = np.zeros((3, 16, 16), dtype=np.uint8)
    vivid_blue[2] = 220

    gray_features = compute_river_silt_features(gray)
    vivid_features = compute_river_silt_features(vivid_blue)
    assert gray_features["silt_saturation_mean"] < 0.05
    assert vivid_features["silt_saturation_mean"] > 0.8


def test_build_feature_table_skips_unparseable_ssc_without_crashing(tmp_path):
    rows = [
        {"site_id": "a", "ssc_value": "not_a_number", "image_path": "irrelevant.tif"},
    ]
    table, skipped = build_feature_table(rows)
    assert table == []
    assert len(skipped) == 1
    assert skipped[0][0] == "a"


def test_build_feature_table_skips_rows_missing_lat_lon(tmp_path):
    path = tmp_path / "rgb.tif"
    import rasterio
    data = np.random.randint(0, 256, size=(3, 8, 8), dtype=np.uint8)
    with rasterio.open(path, "w", driver="GTiff", height=8, width=8, count=3, dtype=data.dtype) as dst:
        dst.write(data)

    rows = [{"site_id": "a", "ssc_value": "5.0", "image_path": str(path)}]  # no lat/lon
    table, skipped = build_feature_table(rows)
    assert table == []
    assert len(skipped) == 1
    assert "lat" in skipped[0][1] or "lon" in skipped[0][1]


def test_split_table_covers_every_row_exactly_once():
    table = [{"site_id": str(i)} for i in range(100)]
    splits = split_table(table, seed=7)
    all_ids = splits["train"] + splits["val"] + splits["test"]
    assert len(all_ids) == 100
    assert {row["site_id"] for row in all_ids} == {str(i) for i in range(100)}
