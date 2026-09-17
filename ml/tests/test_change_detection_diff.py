"""Tests for ml/change_detection/diff.py -- the compare-runner contract."""

from pathlib import Path

import numpy as np
import pytest
import rasterio
from PIL import Image
from rasterio.transform import from_bounds

from change_detection.diff import compute_height_change


def _heightmap(path: Path, values: np.ndarray, alpha: int | np.ndarray = 255) -> str:
    h, w = values.shape
    alpha_arr = np.full((h, w), alpha, dtype=np.uint8) if isinstance(alpha, int) else alpha
    Image.merge("LA", (Image.fromarray(values), Image.fromarray(alpha_arr))).save(path)
    return str(path)


def _dsm(path: Path, values: np.ndarray) -> str:
    height, width = values.shape
    transform = from_bounds(0, 0, 0.01, 0.01, width, height)
    with rasterio.open(
        path, "w", driver="GTiff", height=height, width=width, count=1,
        dtype="float32", crs="EPSG:4326", transform=transform,
    ) as dst:
        dst.write(values.astype(np.float32), 1)
    return str(path)


RELATIVE_META = {"height_units": "relative", "min_height": 0, "max_height": 255, "width": 32, "height": 32}


def test_relative_vs_relative_flags_directional_only(tmp_path):
    before = np.full((32, 32), 100, dtype=np.uint8)
    after = before.copy()
    after[10:20, 10:20] = 200

    result = compute_height_change(
        before_heightmap_path=_heightmap(tmp_path / "b.png", before),
        after_heightmap_path=_heightmap(tmp_path / "a.png", after),
        before_metadata=RELATIVE_META,
        after_metadata=RELATIVE_META,
        output_dir=str(tmp_path),
        before_dsm_path=None,
        after_dsm_path=None,
    )

    assert result.metadata["height_units"] == "relative"
    assert result.metadata["max_gain"] > 0
    assert result.metadata["changed_area_fraction"] == pytest.approx(100 / (32 * 32))
    assert any("relative" in w for w in result.warnings)
    assert Path(result.diff_map_path).exists()


def test_absolute_vs_absolute_uses_heightmap_scale_without_dsm(tmp_path):
    before = np.full((16, 16), 50, dtype=np.uint8)
    after = np.full((16, 16), 100, dtype=np.uint8)
    meta_before = {"height_units": "m", "min_height": 0.0, "max_height": 20.0, "width": 16, "height": 16}
    meta_after = {"height_units": "m", "min_height": 0.0, "max_height": 20.0, "width": 16, "height": 16}

    result = compute_height_change(
        before_heightmap_path=_heightmap(tmp_path / "b.png", before),
        after_heightmap_path=_heightmap(tmp_path / "a.png", after),
        before_metadata=meta_before,
        after_metadata=meta_after,
        output_dir=str(tmp_path),
        before_dsm_path=None,
        after_dsm_path=None,
    )

    assert result.metadata["height_units"] == "m"
    expected_gain = (100 / 255 * 20.0) - (50 / 255 * 20.0)
    assert result.metadata["max_gain"] == pytest.approx(expected_gain, rel=1e-3)


def test_absolute_vs_absolute_prefers_dsm_when_both_present(tmp_path):
    before_dsm = np.full((16, 16), 10.0, dtype=np.float32)
    after_dsm = before_dsm.copy()
    after_dsm[5:10, 5:10] = 25.0

    meta = {"height_units": "m", "min_height": 0.0, "max_height": 999.0, "width": 16, "height": 16}
    before_hm = np.full((16, 16), 5, dtype=np.uint8)  # would give a very different value if used

    result = compute_height_change(
        before_heightmap_path=_heightmap(tmp_path / "b.png", before_hm),
        after_heightmap_path=_heightmap(tmp_path / "a.png", before_hm),
        before_metadata=meta,
        after_metadata=meta,
        output_dir=str(tmp_path),
        before_dsm_path=_dsm(tmp_path / "b.tif", before_dsm),
        after_dsm_path=_dsm(tmp_path / "a.tif", after_dsm),
    )

    assert result.metadata["max_gain"] == pytest.approx(15.0)
    assert not result.warnings


def test_mixed_absolute_and_relative_downgrades_to_relative(tmp_path):
    values = np.full((16, 16), 100, dtype=np.uint8)
    meta_absolute = {"height_units": "m", "min_height": 0.0, "max_height": 20.0, "width": 16, "height": 16}

    result = compute_height_change(
        before_heightmap_path=_heightmap(tmp_path / "b.png", values),
        after_heightmap_path=_heightmap(tmp_path / "a.png", values),
        before_metadata=meta_absolute,
        after_metadata=RELATIVE_META,
        output_dir=str(tmp_path),
        before_dsm_path=None,
        after_dsm_path=None,
    )

    assert result.metadata["height_units"] == "relative"
    assert any("downgraded to relative" in w for w in result.warnings)


def test_dimension_mismatch_raises(tmp_path):
    before = np.full((16, 16), 100, dtype=np.uint8)
    after = np.full((8, 8), 100, dtype=np.uint8)

    with pytest.raises(ValueError, match="size mismatch"):
        compute_height_change(
            before_heightmap_path=_heightmap(tmp_path / "b.png", before),
            after_heightmap_path=_heightmap(tmp_path / "a.png", after),
            before_metadata=RELATIVE_META,
            after_metadata=RELATIVE_META,
            output_dir=str(tmp_path),
            before_dsm_path=None,
            after_dsm_path=None,
        )


def test_no_overlapping_valid_pixels_raises(tmp_path):
    values = np.full((16, 16), 100, dtype=np.uint8)
    zero_alpha = np.zeros((16, 16), dtype=np.uint8)

    with pytest.raises(ValueError, match="no overlapping valid pixels"):
        compute_height_change(
            before_heightmap_path=_heightmap(tmp_path / "b.png", values, alpha=zero_alpha),
            after_heightmap_path=_heightmap(tmp_path / "a.png", values),
            before_metadata=RELATIVE_META,
            after_metadata=RELATIVE_META,
            output_dir=str(tmp_path),
            before_dsm_path=None,
            after_dsm_path=None,
        )


def test_unreadable_file_raises(tmp_path):
    bogus = tmp_path / "missing.png"
    with pytest.raises(ValueError, match="could not read heightmap"):
        compute_height_change(
            before_heightmap_path=str(bogus),
            after_heightmap_path=str(bogus),
            before_metadata=RELATIVE_META,
            after_metadata=RELATIVE_META,
            output_dir=str(tmp_path),
            before_dsm_path=None,
            after_dsm_path=None,
        )
