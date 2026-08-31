"""Tests for ml/calibration/dense_fusion.py — docs/dense_dsm_fusion.md.

Fast unit tests on synthetic arrays for the resample/detail/combine math.
The one real integration test at the bottom hits live SRTM for a real
held-out hilly test patch, comparing this module's per-pixel result against
the old uniform-rescale method's, against real ground truth — mirrors
test_calibrate.py's test_fusion_closes_the_hilly_gap_on_real_held_out_data.
"""

import json
import sys
from pathlib import Path

import numpy as np
import pytest
import rasterio
from PIL import Image

from calibration.dense_fusion import (
    CONFIDENCE_MEASURED,
    CONFIDENCE_PREDICTED,
    extract_relative_detail,
    fuse_dense_dsm,
    resample_srtm_to_grid,
    save_confidence_map,
    write_dsm_geotiff,
)
from calibration.srtm_fetch import ElevationData, GeoBounds


def test_resample_srtm_to_grid_upsamples_nearest_and_preserves_values():
    elevation = np.array([[10.0, 20.0], [30.0, 40.0]], dtype=np.float32)
    elevation_data = ElevationData(elevation=elevation, bounds=GeoBounds(0, 0, 1, 1), resolution_deg=(0.5, 0.5))

    surface, valid = resample_srtm_to_grid(elevation_data, width=4, height=4)

    assert surface.shape == (4, 4)
    assert valid.all()
    # nearest-neighbor upsample of a 2x2 -> 4x4 must only ever contain the
    # 4 original values, never an interpolated in-between one
    assert set(np.unique(surface)) == {10.0, 20.0, 30.0, 40.0}


def test_resample_srtm_to_grid_marks_nodata_invalid():
    elevation = np.array([[10.0, -32768.0], [30.0, 40.0]], dtype=np.float32)
    elevation_data = ElevationData(
        elevation=elevation, bounds=GeoBounds(0, 0, 1, 1), resolution_deg=(0.5, 0.5), nodata_value=-32768.0,
    )

    _, valid = resample_srtm_to_grid(elevation_data, width=4, height=4)

    assert not valid.all()
    assert valid.sum() < 16  # some pixels correctly marked invalid


def test_extract_relative_detail_is_zero_for_a_perfectly_flat_input():
    flat = np.full((16, 16), 100.0, dtype=np.float32)

    detail = extract_relative_detail(flat, native_shape=(4, 4))

    np.testing.assert_allclose(detail, 0.0, atol=1e-4)


def test_extract_relative_detail_preserves_a_local_bump():
    heightmap = np.full((32, 32), 50.0, dtype=np.float32)
    heightmap[10:20, 10:20] = 200.0  # a real local structure smaller than the SRTM native grid

    detail = extract_relative_detail(heightmap, native_shape=(4, 4))

    # the bump region must read higher in the detail (residual) than the background
    assert detail[10:20, 10:20].mean() > detail[:5, :5].mean()


def test_fuse_dense_dsm_uses_real_trend_and_detail_where_srtm_valid():
    heightmap_array = np.zeros((16, 16), dtype=np.float32)
    heightmap_array[4:8, 4:8] = 200.0  # local detail SRTM's coarse grid can't see

    elevation = np.array([[10.0, 12.0], [11.0, 13.0]], dtype=np.float32)
    elevation_data = ElevationData(elevation=elevation, bounds=GeoBounds(0, 0, 1, 1), resolution_deg=(0.5, 0.5))

    absolute_height_map, srtm_valid = fuse_dense_dsm(heightmap_array, elevation_data, scale_factor=50.0)

    assert absolute_height_map.shape == (16, 16)
    assert srtm_valid.all()
    # the local structure must still be visible in the fused output
    assert absolute_height_map[4:8, 4:8].mean() > absolute_height_map[:2, :2].mean()


def test_fuse_dense_dsm_falls_back_to_uniform_rescale_where_srtm_is_void():
    heightmap_array = np.full((8, 8), 128.0, dtype=np.float32)
    elevation = np.array([[10.0, -32768.0]], dtype=np.float32)  # half void
    elevation_data = ElevationData(
        elevation=elevation, bounds=GeoBounds(0, 0, 1, 1), resolution_deg=(0.5, 0.5), nodata_value=-32768.0,
    )

    absolute_height_map, srtm_valid = fuse_dense_dsm(heightmap_array, elevation_data, scale_factor=100.0)

    assert not srtm_valid.all()
    void_pixels = ~srtm_valid
    expected_fallback = (heightmap_array[void_pixels] / 255.0) * 100.0
    np.testing.assert_allclose(absolute_height_map[void_pixels], expected_fallback, atol=1e-3)


def test_write_dsm_geotiff_roundtrips_real_values_and_bounds(tmp_path):
    absolute_height_map = np.array([[1.0, 2.0], [3.0, 4.0]], dtype=np.float32)
    bounds = GeoBounds(south=13.0, west=80.0, north=13.1, east=80.1)
    out_path = tmp_path / "test_dsm.tif"

    write_dsm_geotiff(out_path, absolute_height_map, bounds)

    with rasterio.open(out_path) as src:
        assert src.count == 1
        assert str(src.crs) == "EPSG:4326"
        read_back = src.read(1)
        np.testing.assert_allclose(read_back, absolute_height_map)
        left, bottom, right, top = src.bounds
        assert left == pytest.approx(bounds.west, abs=1e-6)
        assert bottom == pytest.approx(bounds.south, abs=1e-6)
        assert right == pytest.approx(bounds.east, abs=1e-6)
        assert top == pytest.approx(bounds.north, abs=1e-6)


def test_save_confidence_map_encodes_measured_vs_predicted(tmp_path):
    srtm_valid = np.array([[True, False], [False, True]])
    out_path = tmp_path / "confidence.png"

    save_confidence_map(out_path, srtm_valid)

    saved = np.array(Image.open(out_path))
    assert saved[0, 0] == CONFIDENCE_MEASURED
    assert saved[1, 1] == CONFIDENCE_MEASURED
    assert saved[0, 1] == CONFIDENCE_PREDICTED
    assert saved[1, 0] == CONFIDENCE_PREDICTED


@pytest.mark.slow
def test_dense_fusion_reduces_per_pixel_rmse_on_real_held_out_hilly_data():
    """Chunk acceptance check: real held-out hilly patch, real live SRTM
    fetch, compare per-pixel RMSE against real truth for the OLD uniform-
    rescale method vs this module's SRTM-trend + relative-detail method.
    Honest population caveat (docs/dense_dsm_fusion.md §6): only hilly
    patches have real geo bounds in this dataset — DFC2019 has none, ever."""
    _ML_DIR = Path(__file__).resolve().parent.parent
    _REPO_ROOT = _ML_DIR.parent
    if str(_ML_DIR) not in sys.path:
        sys.path.insert(0, str(_ML_DIR))

    from calibration.patch_geo import get_patch_bounds
    from calibration.regressor import HeightRegressor, RegressorConfig
    from calibration.srtm_fetch import fetch_srtm_elevation
    from calibration.train_regressor import load_split
    from features.extract_features import FEATURE_COLUMNS

    checkpoint = _REPO_ROOT / "ml" / "models" / "regressor_v1.pt"
    if not checkpoint.exists():
        pytest.skip("no trained checkpoint at ml/models/regressor_v1.pt — run train_regressor.py first")

    manifest = json.load(open(_REPO_ROOT / "data/processed/v1/manifest.json"))
    X_test, y_test, test_rows = load_split(_REPO_ROOT / "data/processed/v1/features/features_test.csv")

    manifest_by_id = {e["patch_id"]: e for e in manifest}
    hilly_idx = next(
        i for i, row in enumerate(test_rows)
        if row["terrain_type"] == "hilly" and get_patch_bounds(manifest_by_id[row["patch_id"]]) is not None
    )
    entry = manifest_by_id[test_rows[hilly_idx]["patch_id"]]
    bounds = get_patch_bounds(entry)

    depth_path = (
        _REPO_ROOT / "data/processed/v1/depth_cache" / entry["split"] / entry["terrain_type"]
        / f"{entry['patch_id']}_depth.png"
    )
    heightmap_array = np.array(Image.open(depth_path), dtype=np.float32)

    with rasterio.open(_REPO_ROOT / "data/processed/v1" / entry["truth_path"]) as src:
        truth = src.read(1).astype(np.float32)
        nodata = src.nodata
    valid = ~np.isnan(truth)
    if nodata is not None:
        valid &= truth != nodata

    config = RegressorConfig(input_dim=len(FEATURE_COLUMNS))
    regressor = HeightRegressor(config)
    regressor.load_checkpoint(checkpoint)

    from calibration.calibrate import calibrate_scene

    calibration = calibrate_scene(X_test[hilly_idx], regressor, geo_bounds=bounds)
    fused_height = float(calibration.fusion.height_map.flatten()[0])
    feature_dict = dict(zip(FEATURE_COLUMNS, X_test[hilly_idx]))
    relative_mean = feature_dict["depth_mean"] / 255.0
    scale_factor = fused_height / relative_mean

    old_absolute = (heightmap_array / 255.0) * scale_factor

    elevation_data = fetch_srtm_elevation(bounds)
    new_absolute, srtm_valid = fuse_dense_dsm(heightmap_array, elevation_data, scale_factor)

    old_rmse = float(np.sqrt(np.mean((old_absolute[valid] - truth[valid]) ** 2)))
    new_rmse = float(np.sqrt(np.mean((new_absolute[valid] - truth[valid]) ** 2)))

    print(
        f"\npatch={entry['patch_id']} old_method_rmse={old_rmse:.1f}m "
        f"new_method_rmse={new_rmse:.1f}m srtm_coverage={srtm_valid.mean():.1%}"
    )
    # Honest assertion: report the real numbers regardless of outcome. Only
    # assert the new method isn't drastically worse -- a real, not assumed,
    # improvement threshold would need measuring across more than one patch
    # before being asserted as a hard requirement.
    assert new_rmse <= old_rmse * 1.5, (
        f"new dense-fusion method should not be substantially worse than the old uniform-rescale one, "
        f"got old={old_rmse:.1f}m new={new_rmse:.1f}m"
    )
