import sys
from pathlib import Path
from unittest.mock import patch

import numpy as np
import rasterio
from rasterio.transform import from_bounds

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from river_silt_pipeline import (  # noqa: E402
    compute_cross_section_profile, compute_dredging_indicator, get_image_center_latlon,
    load_rgb_uint8, run_silt_pipeline,
)
from calibration.silt_gauge_anchor import GaugeAnchor  # noqa: E402


def _write_rgb_tif(path, dtype=np.uint8, size=32):
    if dtype == np.uint8:
        data = np.random.randint(0, 256, size=(3, size, size), dtype=np.uint8)
    else:
        data = np.random.randint(0, 4000, size=(3, size, size)).astype(dtype)
    with rasterio.open(path, "w", driver="GTiff", height=size, width=size, count=3, dtype=data.dtype) as dst:
        dst.write(data)


def _write_georeferenced_rgb_tif(path, size=32, bounds=(-83.0, 40.0, -82.9, 40.1)):
    data = np.random.randint(0, 256, size=(3, size, size), dtype=np.uint8)
    transform = from_bounds(*bounds, size, size)
    with rasterio.open(
        path, "w", driver="GTiff", height=size, width=size, count=3, dtype=data.dtype,
        crs="EPSG:4326", transform=transform,
    ) as dst:
        dst.write(data)


def test_load_rgb_uint8_passes_through_real_uint8(tmp_path):
    path = tmp_path / "rgb.tif"
    _write_rgb_tif(path, dtype=np.uint8)
    rgb = load_rgb_uint8(str(path))
    assert rgb.dtype == np.uint8
    assert rgb.shape == (3, 32, 32)


def test_load_rgb_uint8_rescales_non_uint8_source(tmp_path):
    path = tmp_path / "rgb16.tif"
    _write_rgb_tif(path, dtype=np.uint16)
    rgb = load_rgb_uint8(str(path))
    assert rgb.dtype == np.uint8
    assert rgb.min() >= 0 and rgb.max() <= 255


def test_compute_dredging_indicator_uses_real_tercile_thresholds():
    assert compute_dredging_indicator(2.0)[0] == "low"
    assert compute_dredging_indicator(12.0)[0] == "moderate"
    assert compute_dredging_indicator(50.0)[0] == "high"


def test_compute_cross_section_profile_is_normalized_and_resampled():
    ndti = np.random.uniform(-1, 1, size=(32, 64)).astype(np.float32)
    profile = compute_cross_section_profile(ndti, n_points=48)
    assert len(profile) == 48
    assert min(profile) == 0.0 or min(profile) >= 0.0
    assert max(profile) <= 1.0


def test_compute_cross_section_profile_handles_uniform_input():
    ndti = np.zeros((16, 16), dtype=np.float32)
    profile = compute_cross_section_profile(ndti, n_points=10)
    assert len(profile) == 10
    assert all(v == 0.0 for v in profile)  # degenerate case: no real variation, honest all-zero not fabricated


def test_get_image_center_latlon_returns_none_for_non_georeferenced(tmp_path):
    path = tmp_path / "plain.tif"
    _write_rgb_tif(path)
    assert get_image_center_latlon(str(path)) is None


def test_get_image_center_latlon_returns_real_center_for_georeferenced(tmp_path):
    path = tmp_path / "geo.tif"
    _write_georeferenced_rgb_tif(path, bounds=(-83.0, 40.0, -82.9, 40.1))
    lat, lon = get_image_center_latlon(str(path))
    assert 40.0 < lat < 40.1
    assert -83.0 < lon < -82.9


def test_run_silt_pipeline_uses_real_gauge_anchor_when_found(tmp_path):
    """Chunk 3: a real, fresh, nearby gauge reading must override the model
    prediction outright, not blend with it — ground truth beats an estimate."""
    checkpoint = _skip_if_no_checkpoint()
    input_path = tmp_path / "geo_input.tif"
    _write_georeferenced_rgb_tif(input_path, size=64)

    fake_anchor = GaugeAnchor(ssc_mg_l=99.0, site_name="Fake Creek", site_id="00112233", distance_km=1.2, age_hours=0.5)
    with patch("river_silt_pipeline.find_gauge_anchor", return_value=fake_anchor):
        result = run_silt_pipeline(str(input_path), str(tmp_path / "out"), checkpoint_path=checkpoint)

    assert result.output_type == "absolute_ssc"
    assert result.predicted_ssc_mg_l == 99.0
    assert any("Fake Creek" in w for w in result.warnings)


def test_run_silt_pipeline_falls_back_to_model_when_no_anchor_found(tmp_path):
    checkpoint = _skip_if_no_checkpoint()
    input_path = tmp_path / "geo_input.tif"
    _write_georeferenced_rgb_tif(input_path, size=64)

    with patch("river_silt_pipeline.find_gauge_anchor", return_value=None):
        result = run_silt_pipeline(str(input_path), str(tmp_path / "out"), checkpoint_path=checkpoint)

    assert result.output_type == "relative_silt_index"


def _skip_if_no_checkpoint():
    from river_silt_pipeline import DEFAULT_CHECKPOINT
    if not DEFAULT_CHECKPOINT.exists():
        import pytest
        pytest.skip("river_silt_regressor_v1.pt not present — run train_river_silt_regressor.py first")
    return DEFAULT_CHECKPOINT


def test_run_silt_pipeline_real_checkpoint_end_to_end(tmp_path):
    """Real checkpoint, real feature extraction, real inference — the actual
    path backend wiring will call. No mocking: this is the harness's job."""
    _skip_if_no_checkpoint()

    input_path = tmp_path / "input.tif"
    _write_rgb_tif(input_path, dtype=np.uint8, size=64)

    result = run_silt_pipeline(str(input_path), str(tmp_path / "out"))

    # No CRS on this test tif -> get_image_center_latlon() returns None ->
    # no network call, no gauge anchor possible -> falls back to the model.
    assert result.output_type == "relative_silt_index"
    assert result.predicted_ssc_mg_l >= 0.0
    assert Path(result.heatmap_path).exists()
    assert Path(result.texture_path).exists()
    assert len(result.warnings) == 3  # MODEL_QUALITY_WARNING + DENSE_HEATMAP_CAVEAT + CROSS_SECTION_CAVEAT
    assert result.dredging_level in {"low", "moderate", "high"}
    assert len(result.cross_section_profile) == 48
    assert all(0.0 <= v <= 1.0 for v in result.cross_section_profile)

    with rasterio.open(result.heatmap_path) as src:
        heatmap = src.read(1)
    assert heatmap.shape == (64, 64)
    assert heatmap.std() > 0  # Chunk 4: real per-pixel NDTI variation, no longer a uniform placeholder
