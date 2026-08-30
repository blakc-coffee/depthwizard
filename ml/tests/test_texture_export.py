"""Tests for ml/utils/texture_export.py — PNG/JPG pass-through and GeoTIFF
band-selection/contrast-stretch logic (docs/depthwizard.md Section 9.8)."""

import numpy as np
import pytest
import rasterio
from PIL import Image
from rasterio.transform import from_origin

from utils.texture_export import _render_geotiff, _stretch, export_texture

TRANSFORM = from_origin(0, 10, 1, 1)


def _write_geotiff(path, bands: np.ndarray, dtype, nodata=None):
    """bands: array shaped (count, height, width)."""
    count, height, width = bands.shape
    with rasterio.open(
        path, "w", driver="GTiff", height=height, width=width, count=count,
        dtype=dtype, crs="EPSG:4326", transform=TRANSFORM, nodata=nodata,
    ) as dst:
        dst.write(bands)


def test_png_passthrough_is_rgb_same_size(tmp_path):
    src = tmp_path / "in.png"
    Image.new("RGB", (16, 10), color=(10, 20, 30)).save(src)

    out = export_texture(src, tmp_path / "out")

    result = Image.open(out)
    assert result.mode == "RGB"
    assert result.size == (16, 10)


def test_stretch_maps_percentile_range_to_full_uint8():
    band = np.linspace(0, 100, 100).reshape(10, 10).astype(np.float32)
    stretched = _stretch(band, nodata=None)
    assert stretched.dtype == np.uint8
    assert stretched.min() == 0
    assert stretched.max() == 255


def test_stretch_excludes_nodata_pixels():
    band = np.full((4, 4), 50.0, dtype=np.float32)
    band[0, 0] = -9999.0  # nodata outlier — must not skew the percentile range
    stretched = _stretch(band, nodata=-9999.0)
    # every valid pixel has the same value -> flat output, nodata pixel included
    # in the array shape but excluded from the lo/hi percentile computation
    assert stretched[1, 1] == stretched[2, 2]


def test_geotiff_single_band_replicated_to_rgb(tmp_path):
    path = tmp_path / "single.tif"
    band = np.linspace(0, 255, 64).reshape(1, 8, 8).astype(np.uint8)
    _write_geotiff(path, band, "uint8")

    image = _render_geotiff(path)
    arr = np.array(image)
    assert image.mode == "RGB"
    assert np.array_equal(arr[..., 0], arr[..., 1])
    assert np.array_equal(arr[..., 1], arr[..., 2])


def test_geotiff_uint8_three_band_is_true_rgb_no_reorder(tmp_path):
    path = tmp_path / "rgb.tif"
    r = np.full((8, 8), 10, dtype=np.uint8)
    g = np.full((8, 8), 20, dtype=np.uint8)
    b = np.full((8, 8), 30, dtype=np.uint8)
    # vary within each band so the percentile stretch isn't degenerate
    r[0, 0], g[0, 0], b[0, 0] = 250, 250, 250
    bands = np.stack([r, g, b])
    _write_geotiff(path, bands, "uint8")

    image = _render_geotiff(path)
    arr = np.array(image)

    expected_r = _stretch(r.astype(np.float32), None)
    expected_g = _stretch(g.astype(np.float32), None)
    expected_b = _stretch(b.astype(np.float32), None)
    assert np.array_equal(arr[..., 0], expected_r)
    assert np.array_equal(arr[..., 1], expected_g)
    assert np.array_equal(arr[..., 2], expected_b)


def test_geotiff_uint16_three_band_is_false_color_reordered(tmp_path):
    """Raw multispectral (no blue band) — band order is Green/Red/NIR (e.g.
    LISS-IV). Output must be R=NIR, G=Red, B=Green per texture_export.py's
    documented heuristic."""
    path = tmp_path / "multispectral.tif"
    green = np.full((8, 8), 100, dtype=np.uint16)
    red = np.full((8, 8), 200, dtype=np.uint16)
    nir = np.full((8, 8), 300, dtype=np.uint16)
    green[0, 0], red[0, 0], nir[0, 0] = 900, 900, 900  # avoid degenerate stretch
    bands = np.stack([green, red, nir])  # on-disk order: green, red, nir
    _write_geotiff(path, bands, "uint16")

    image = _render_geotiff(path)
    arr = np.array(image)

    expected_r = _stretch(nir.astype(np.float32), None)
    expected_g = _stretch(red.astype(np.float32), None)
    expected_b = _stretch(green.astype(np.float32), None)
    assert np.array_equal(arr[..., 0], expected_r)
    assert np.array_equal(arr[..., 1], expected_g)
    assert np.array_equal(arr[..., 2], expected_b)


def test_geotiff_two_band_is_unsupported(tmp_path):
    path = tmp_path / "twoband.tif"
    bands = np.zeros((2, 8, 8), dtype=np.uint8)
    _write_geotiff(path, bands, "uint8")

    with pytest.raises(ValueError):
        _render_geotiff(path)
