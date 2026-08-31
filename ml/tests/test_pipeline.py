"""End-to-end test for ml/pipeline.py's Stage A wiring.

Runs the real Depth Anything V2 backbone (cached locally after Phase 1) — no
network required, but this is the slow test in the suite: run it whenever
depth/backbone.py, pipeline.py, or the contract in integration/contracts.py
change, not on every save.

Goes through integration.pipeline_runner rather than calling ml.pipeline
directly: that's the actual production entry point (same one
backend/app/tasks/process_image.py uses), and it's what converts ml/
pipeline.py's local, minimal PipelineResult into the frozen contract object
that has .validate() — ml/pipeline.py deliberately does not import
integration/contracts.py itself, to keep ml/ importable standalone with zero
backend dependencies.
"""

import sys
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from integration.pipeline_runner import run_pipeline  # noqa: E402

SAMPLE_DIR = Path(__file__).resolve().parent.parent / "depth" / "samples"


def _first_sample() -> Path:
    samples = sorted(SAMPLE_DIR.glob("*.jpg"))
    if not samples:
        import pytest

        pytest.skip(f"no sample images in {SAMPLE_DIR} — see ml/depth/PHASE1_NOTES.md")
    return samples[0]


def test_run_pipeline_produces_a_contract_valid_relative_result(tmp_path):
    result = run_pipeline(_first_sample(), tmp_path)

    problems = result.validate(strict=True)
    assert problems == []

    # Honesty rule (docs/depthwizard.md Section 1): calibration isn't built
    # yet, so nothing may claim absolute/metric height regardless of input.
    assert result.output_type == "relative_dsm"
    assert result.metadata["height_units"] == "relative"
    assert result.warnings  # the calibration-not-implemented warning must be visible


def test_run_pipeline_heightmap_is_pixel_aligned_with_texture(tmp_path):
    from PIL import Image

    result = run_pipeline(_first_sample(), tmp_path)

    texture = Image.open(result.texture_path)
    heightmap = Image.open(result.heightmap_path)
    assert texture.size == heightmap.size
    assert heightmap.mode == "LA"  # grey=height, alpha=NoData validity (Section 9.6)


def _write_georeferenced_rgb(path, size=64):
    """A minimal real GeoTIFF — real CRS/transform, uint8 3-band — matching
    ml/tests/test_extract_features.py's convention, so _is_georeferenced()
    and _get_geo_bounds() see a real, valid input."""
    import numpy as np
    import rasterio
    from rasterio.transform import from_origin

    bands = np.random.randint(0, 255, (3, size, size), dtype=np.uint8)
    with rasterio.open(
        path, "w", driver="GTiff", height=size, width=size, count=3,
        dtype="uint8", crs="EPSG:4326", transform=from_origin(80.0, 13.0, 0.01, 0.01),
    ) as dst:
        dst.write(bands)


class _FakeCalibration:
    def __init__(self, fused_height, srtm_valid_fraction=1.0):
        self.fusion = type(
            "F", (), {
                "sources_used": ["srtm", "regressor"],
                "confidence_map": np.array([[0.9]]),
                "height_map": np.array([[fused_height]]),
            }
        )()
        self.srtm_valid_fraction = srtm_valid_fraction


def _patch_pipeline_for_grounding_test(monkeypatch, depth_fill, fused_height):
    """Isolate run_pipeline()'s scale-anchor grounding gate from everything
    it doesn't need for this test — no real depth model, regressor, SRTM
    fetch, or segmentation call."""
    import numpy as np
    from PIL import Image

    import pipeline as ml_pipeline

    from calibration.srtm_fetch import ElevationData

    monkeypatch.setattr(ml_pipeline, "estimate_relative_depth", lambda img: Image.new("L", img.size, depth_fill))
    monkeypatch.setattr(ml_pipeline, "_get_regressor", lambda: object())
    monkeypatch.setattr(ml_pipeline, "segment_image", lambda img: np.zeros((img.size[1], img.size[0]), dtype=np.uint8))
    monkeypatch.setattr(
        ml_pipeline, "calibrate_scene",
        lambda *a, **k: _FakeCalibration(fused_height=fused_height, srtm_valid_fraction=1.0),
    )
    monkeypatch.setattr(
        ml_pipeline, "fetch_srtm_elevation",
        lambda bounds: ElevationData(elevation=np.full((4, 4), 10.0, dtype=np.float32), bounds=bounds, resolution_deg=(0.01, 0.01)),
    )
    return ml_pipeline


def test_run_pipeline_rejects_absolute_dsm_when_relative_mean_too_degenerate(tmp_path, monkeypatch):
    """Regression test for the 2026-08-31 scale-explosion fix: a near-flat
    relative depth map (mimicking the real hallucinated-gradient artifact
    found on sparse terrain) must not get amplified into an absolute claim,
    even with SRTM trustworthy and a real fused height — see
    docs/open_decisions.md."""
    ml_pipeline = _patch_pipeline_for_grounding_test(monkeypatch, depth_fill=5, fused_height=50.0)
    # relative_mean = 5/255 = 0.0196, below MIN_RELATIVE_DEPTH_MEAN (0.05)

    geotiff_path = tmp_path / "input.tif"
    _write_georeferenced_rgb(geotiff_path)

    result = ml_pipeline.run_pipeline(geotiff_path, tmp_path)

    assert result.output_type == "relative_dsm"
    assert any("too degenerate to anchor" in w for w in result.warnings)


def test_run_pipeline_rejects_absolute_dsm_when_scale_factor_implausible(tmp_path, monkeypatch):
    """A well-formed relative_mean can still produce an implausible
    scale_factor if fused_height itself is huge — must still fall back."""
    ml_pipeline = _patch_pipeline_for_grounding_test(monkeypatch, depth_fill=100, fused_height=1_000_000.0)
    # relative_mean = 100/255 = 0.392 (fine), scale_factor ~2.55M, way above cap

    geotiff_path = tmp_path / "input.tif"
    _write_georeferenced_rgb(geotiff_path)

    result = ml_pipeline.run_pipeline(geotiff_path, tmp_path)

    assert result.output_type == "relative_dsm"
    assert any("too degenerate to anchor" in w for w in result.warnings)


def test_run_pipeline_accepts_absolute_dsm_when_scale_anchor_is_grounded(tmp_path, monkeypatch):
    """Sanity check the other direction: a well-formed relative_mean and a
    plausible fused_height must still reach absolute_dsm — the new gate
    shouldn't block legitimate results."""
    ml_pipeline = _patch_pipeline_for_grounding_test(monkeypatch, depth_fill=100, fused_height=50.0)
    # relative_mean = 100/255 = 0.392, scale_factor ~127.5 — both well within bounds

    geotiff_path = tmp_path / "input.tif"
    _write_georeferenced_rgb(geotiff_path)

    result = ml_pipeline.run_pipeline(geotiff_path, tmp_path)

    assert result.output_type == "absolute_dsm"
    # Dense DSM fusion (docs/dense_dsm_fusion.md) should populate both
    # previously-always-None contract fields on a successful absolute run.
    assert result.dsm_path is not None
    assert result.confidence_map_path is not None
    assert Path(result.dsm_path).exists()
    assert Path(result.confidence_map_path).exists()


def test_run_pipeline_dense_dsm_fields_stay_none_on_non_georeferenced_input(tmp_path, monkeypatch):
    """dsm_path/confidence_map_path must never be populated for a
    relative_dsm result -- this feature only ever fires on the absolute
    branch (docs/dense_dsm_fusion.md's scope section). Uses the same
    lightweight mocking as the grounding tests -- no need for a 3rd real
    depth-model invocation in this file to prove a None-stays-None path."""
    ml_pipeline = _patch_pipeline_for_grounding_test(monkeypatch, depth_fill=100, fused_height=50.0)

    from PIL import Image as PILImage

    png_path = tmp_path / "input.png"
    PILImage.fromarray(np.zeros((64, 64, 3), dtype=np.uint8)).save(png_path)  # non-georeferenced

    result = ml_pipeline.run_pipeline(png_path, tmp_path)

    assert result.output_type == "relative_dsm"
    assert result.dsm_path is None
    assert result.confidence_map_path is None
