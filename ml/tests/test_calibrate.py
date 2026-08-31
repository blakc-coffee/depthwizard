"""Tests for ml/calibration/calibrate.py — Phase 4 Chunk 2's orchestrator.

Fast unit tests mock srtm_fetch/semantic_priors entirely. The one real
integration test at the bottom hits live SRTM for an actual held-out hilly
test patch — this is Chunk 2's own acceptance check (docs/phase4.md):
"verified against real held-out hilly patches," not a mocked approximation
of it. Chunk 4 will add offline mocking without removing this test's intent.
"""

import json
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from calibration import calibrate
from calibration.calibrate import _texture_adaptive_regressor_variance, calibrate_scene
from calibration.srtm_fetch import ElevationData, GeoBounds
from features.extract_features import FEATURE_COLUMNS


class _FakeRegressor:
    def __init__(self, value):
        self.value = value

    def predict(self, X):
        return np.float32(self.value)


def test_non_georeferenced_scene_never_attempts_srtm(monkeypatch):
    def fail_if_called(*a, **k):
        raise AssertionError("SRTM must not be attempted with geo_bounds=None")

    monkeypatch.setattr(calibrate, "fetch_srtm_elevation", fail_if_called)

    result = calibrate_scene(np.zeros(11), _FakeRegressor(5.0), geo_bounds=None)

    assert "srtm" not in result.fusion.sources_used
    assert "regressor" in result.fusion.sources_used
    assert result.srtm_valid_fraction is None


def test_georeferenced_scene_uses_srtm_when_available(monkeypatch):
    def fake_fetch(bounds):
        return ElevationData(
            elevation=np.array([[100.0, 150.0], [120.0, 140.0]], dtype=np.float32),
            bounds=bounds, resolution_deg=(0.01, 0.01),
        )

    monkeypatch.setattr(calibrate, "fetch_srtm_elevation", fake_fetch)

    bounds = GeoBounds(south=13.0, west=80.0, north=13.1, east=80.1)
    result = calibrate_scene(np.zeros(11), _FakeRegressor(5.0), geo_bounds=bounds)

    assert "srtm" in result.fusion.sources_used
    assert "regressor" in result.fusion.sources_used
    assert result.srtm_valid_fraction == 1.0  # all 4 fake pixels are valid


def test_srtm_fetch_failure_degrades_gracefully_not_crash(monkeypatch):
    def fake_fetch(bounds):
        raise ConnectionError("network unavailable")

    monkeypatch.setattr(calibrate, "fetch_srtm_elevation", fake_fetch)

    bounds = GeoBounds(south=13.0, west=80.0, north=13.1, east=80.1)
    result = calibrate_scene(np.zeros(11), _FakeRegressor(5.0), geo_bounds=bounds)

    assert "srtm" not in result.fusion.sources_used
    assert "regressor" in result.fusion.sources_used
    assert result.srtm_valid_fraction is None


def test_srtm_partial_coverage_reports_valid_fraction_below_one(monkeypatch):
    def fake_fetch(bounds):
        return ElevationData(
            elevation=np.array([[100.0, -32768.0], [120.0, -32768.0]], dtype=np.float32),
            bounds=bounds, resolution_deg=(0.01, 0.01), nodata_value=-32768.0,
        )

    monkeypatch.setattr(calibrate, "fetch_srtm_elevation", fake_fetch)

    bounds = GeoBounds(south=13.0, west=80.0, north=13.1, east=80.1)
    result = calibrate_scene(np.zeros(11), _FakeRegressor(5.0), geo_bounds=bounds)

    assert result.srtm_valid_fraction == 0.5  # 2 of 4 pixels are NoData


def test_semantic_estimate_included_when_rgb_provided(monkeypatch):
    def fake_segment(image):
        return np.zeros((8, 8), dtype=np.uint8)

    monkeypatch.setattr(calibrate, "segment_image", fake_segment)

    rgb = Image.new("RGB", (8, 8))
    result = calibrate_scene(np.zeros(11), _FakeRegressor(5.0), rgb_image=rgb)

    assert "semantic" in result.fusion.sources_used


def _features_with_grad_std(value):
    features = np.zeros(len(FEATURE_COLUMNS))
    features[FEATURE_COLUMNS.index("depth_grad_std")] = value
    return features


def test_texture_adaptive_variance_low_below_threshold():
    features = _features_with_grad_std(calibrate._TEXTURE_VARIANCE_THRESHOLD - 0.5)
    assert _texture_adaptive_regressor_variance(features) == calibrate._TEXTURE_LOW_VARIANCE


def test_texture_adaptive_variance_high_at_or_above_threshold():
    features = _features_with_grad_std(calibrate._TEXTURE_VARIANCE_THRESHOLD)
    assert _texture_adaptive_regressor_variance(features) == calibrate._TEXTURE_HIGH_VARIANCE

    features_noisy = _features_with_grad_std(calibrate._TEXTURE_VARIANCE_THRESHOLD + 5.0)
    assert _texture_adaptive_regressor_variance(features_noisy) == calibrate._TEXTURE_HIGH_VARIANCE


def test_calibrate_scene_uses_texture_adaptive_variance_by_default(monkeypatch):
    import calibration.fusion as fusion_module

    captured = {}
    original_fuse = fusion_module.fuse_height_estimates

    def spy_fuse(**kwargs):
        captured["regressor_variance"] = kwargs["regressor_variance"]
        return original_fuse(**kwargs)

    monkeypatch.setattr(calibrate, "fuse_height_estimates", spy_fuse)

    noisy_features = _features_with_grad_std(calibrate._TEXTURE_VARIANCE_THRESHOLD + 5.0)
    calibrate_scene(noisy_features, _FakeRegressor(5.0), geo_bounds=None)
    assert captured["regressor_variance"] == calibrate._TEXTURE_HIGH_VARIANCE


def test_calibrate_scene_explicit_override_bypasses_texture_adaptive(monkeypatch):
    import calibration.fusion as fusion_module

    captured = {}
    original_fuse = fusion_module.fuse_height_estimates

    def spy_fuse(**kwargs):
        captured["regressor_variance"] = kwargs["regressor_variance"]
        return original_fuse(**kwargs)

    monkeypatch.setattr(calibrate, "fuse_height_estimates", spy_fuse)

    noisy_features = _features_with_grad_std(calibrate._TEXTURE_VARIANCE_THRESHOLD + 5.0)
    calibrate_scene(noisy_features, _FakeRegressor(5.0), geo_bounds=None, regressor_variance_without_srtm=42.0)
    assert captured["regressor_variance"] == 42.0


def test_regressor_variance_defaults_are_measured_and_bimodal():
    """Guard against re-reversing either fix. Measured on real held-out data
    (docs/open_decisions.md, 2026-08-31): the regressor's true error
    variance is ~7.2-22.1 m² on non-hilly terrain (texture-dependent) but
    ~15,379 m² on hilly — a single fixed variance is wrong in one direction
    or the other.
    - With SRTM present: regressor must stay far LESS trusted than SRTM
      (it can't distinguish a 400m-relief hilly scene from a ~0m-height
      flat one — an information limit, not a training bug).
    - Without SRTM: the default (texture-adaptive, `None`) must be trusted
      MORE than semantic priors even at its noisiest (measured ~2.6x more
      accurate for the common non-hilly case — the old fixed default of 100
      had this backwards)."""
    import inspect

    defaults = {
        p.name: p.default
        for p in inspect.signature(calibrate_scene).parameters.values()
        if p.default is not inspect.Parameter.empty
    }
    assert defaults["regressor_variance_with_srtm"] > defaults["srtm_variance"]
    assert defaults["regressor_variance_without_srtm"] is None  # triggers texture-adaptive variance
    assert calibrate._TEXTURE_HIGH_VARIANCE < defaults["semantic_variance"]
    assert calibrate._TEXTURE_HIGH_VARIANCE < defaults["regressor_variance_with_srtm"]


def test_regressor_variance_switches_based_on_srtm_availability(monkeypatch):
    """calibrate_scene must actually use the conditional variance, not just
    define it — verified by checking fuse_height_estimates receives the
    right one in each branch."""
    import calibration.fusion as fusion_module

    captured = {}
    original_fuse = fusion_module.fuse_height_estimates

    def spy_fuse(**kwargs):
        captured["regressor_variance"] = kwargs["regressor_variance"]
        return original_fuse(**kwargs)

    monkeypatch.setattr(calibrate, "fuse_height_estimates", spy_fuse)

    # zeros -> depth_grad_std=0, below the texture threshold -> low-texture variance
    calibrate_scene(np.zeros(11), _FakeRegressor(5.0), geo_bounds=None)
    assert captured["regressor_variance"] == calibrate._TEXTURE_LOW_VARIANCE

    def fake_fetch(bounds):
        return ElevationData(
            elevation=np.array([[100.0, 150.0], [120.0, 140.0]], dtype=np.float32),
            bounds=bounds, resolution_deg=(0.01, 0.01),
        )

    monkeypatch.setattr(calibrate, "fetch_srtm_elevation", fake_fetch)
    bounds = GeoBounds(south=13.0, west=80.0, north=13.1, east=80.1)
    calibrate_scene(np.zeros(11), _FakeRegressor(5.0), geo_bounds=bounds)
    assert captured["regressor_variance"] == 100.0


@pytest.mark.slow
def test_fusion_closes_the_hilly_gap_on_real_held_out_data():
    """Chunk 2's actual acceptance check: pick a real held-out hilly test
    patch, run it through the real trained regressor AND real SRTM fetch,
    and confirm the fused estimate is dramatically closer to the true
    height than the regressor alone (which measured ~197-200m MAE on hilly
    before this fix)."""
    _ML_DIR = Path(__file__).resolve().parent.parent
    _REPO_ROOT = _ML_DIR.parent
    if str(_ML_DIR) not in sys.path:
        sys.path.insert(0, str(_ML_DIR))

    from calibration.patch_geo import get_patch_bounds
    from calibration.regressor import HeightRegressor, RegressorConfig
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
    actual_height = float(y_test[hilly_idx])

    config = RegressorConfig(input_dim=len(FEATURE_COLUMNS))
    regressor = HeightRegressor(config)
    regressor.load_checkpoint(checkpoint)

    regressor_only = float(regressor.predict(X_test[hilly_idx]))
    result = calibrate_scene(X_test[hilly_idx], regressor, geo_bounds=bounds)
    fused_height = float(result.fusion.height_map.flatten()[0])

    regressor_error = abs(regressor_only - actual_height)
    fused_error = abs(fused_height - actual_height)

    print(f"\npatch={entry['patch_id']} actual={actual_height:.1f}m "
          f"regressor_only={regressor_only:.1f}m (err={regressor_error:.1f}m) "
          f"fused={fused_height:.1f}m (err={fused_error:.1f}m) sources={result.fusion.sources_used} "
          f"srtm_valid_fraction={result.srtm_valid_fraction}")

    assert "srtm" in result.fusion.sources_used
    assert fused_error < regressor_error * 0.5, (
        f"fusion should dramatically cut the regressor's error on hilly terrain, "
        f"got regressor_error={regressor_error:.1f}m fused_error={fused_error:.1f}m"
    )
