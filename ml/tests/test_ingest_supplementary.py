"""Tests for ml/data/ingest_supplementary.py — reprojection alignment and
relative-height normalization for the Copernicus DEM / USGS 3DEP sources
(docs/open_decisions.md, 2026-08-30 entry)."""

import numpy as np
import rasterio
from rasterio.transform import from_origin

from data import ingest_supplementary as ing

DEM_TRANSFORM = from_origin(0, 10, 1, 1)  # 1 unit/px, matches dem_array indexing 1:1


def _write_tif(path, array, dtype, transform, crs="EPSG:4326", nodata=None):
    count, height, width = (1, *array.shape) if array.ndim == 2 else array.shape
    data = array[np.newaxis, ...] if array.ndim == 2 else array
    with rasterio.open(
        path, "w", driver="GTiff", height=height, width=width, count=count,
        dtype=dtype, crs=crs, transform=transform, nodata=nodata,
    ) as dst:
        dst.write(data)


def test_reproject_rgb_to_grid_same_crs_is_pixel_identity(tmp_path):
    """Same CRS, coarser target grid at 2x the source pixel size — average
    resampling should land each dest pixel near the mean of its 2x2 block."""
    rgb_path = tmp_path / "rgb.tif"
    fine_transform = from_origin(0, 20, 1, 1)  # 20x20 at 1 unit/px
    rgb = np.zeros((3, 20, 20), dtype=np.uint8)
    rgb[0, :10, :10] = 100  # top-left quadrant distinct per band
    rgb[1, :10, 10:] = 150
    rgb[2, 10:, :] = 200
    _write_tif(rgb_path, rgb, "uint8", fine_transform)

    dst_transform = from_origin(0, 20, 2, 2)  # 10x10 at 2 units/px
    result = ing.reproject_rgb_to_grid(str(rgb_path), "EPSG:4326", dst_transform, (10, 10))

    assert result.shape == (3, 10, 10)
    assert result.dtype == np.uint8
    assert result[0, 0, 0] == 100  # top-left block, band 0
    assert result[2, 9, 9] == 200  # bottom-right block, band 2


def test_patchify_region_normalizes_height_to_local_minimum(tmp_path):
    dem = np.full((8, 8), 1000.0, dtype=np.float32)  # absolute elevation, e.g. Himalaya-scale
    dem[0, 0] = 1005.0  # 5m of local relief
    rgb = np.full((3, 8, 8), 50, dtype=np.uint8)

    patches = ing.patchify_region(dem, rgb, "test_region", str(tmp_path), "hilly", patch_size=8)

    assert len(patches) == 1
    assert patches[0]["terrain_type"] == "hilly"  # fixed from known geography, not re-derived
    with rasterio.open(patches[0]["temp_truth"]) as src:
        relative = src.read(1)
    # Absolute elevation (~1000m) must not survive — only the within-patch
    # relief (0-5m) does, so Phase 4 sees a scale consistent with DFC2019's
    # AGL patches instead of raw sea-level elevation.
    assert relative.min() == 0.0
    assert relative.max() == 5.0


def test_patchify_region_does_not_use_height_heuristic_for_label(tmp_path):
    """A flat patch (std ~0, would classify_terrain() as 'sparse') must still
    come out labeled by the region's known geography, not the heuristic —
    this is the fix for the 2026-08-30 all-patches-mislabeled-urban bug."""
    dem = np.full((8, 8), 200.0, dtype=np.float32)  # perfectly flat -> heuristic would say "sparse"
    rgb = np.full((3, 8, 8), 50, dtype=np.uint8)

    patches = ing.patchify_region(dem, rgb, "flat_but_hilly_region", str(tmp_path), "hilly", patch_size=8)

    assert patches[0]["terrain_type"] == "hilly"


def test_patchify_region_skips_patches_below_valid_coverage_threshold(tmp_path):
    dem = np.full((8, 8), 100.0, dtype=np.float32)
    rgb = np.zeros((3, 8, 8), dtype=np.uint8)
    rgb[:, :2, :2] = 50  # only 4/64 = 6% pixels have real RGB coverage

    patches = ing.patchify_region(dem, rgb, "sparse_coverage", str(tmp_path), "sparse", patch_size=8)

    assert patches == []


def test_patchify_region_marks_nodata_pixels_with_sentinel(tmp_path):
    dem = np.full((8, 8), 100.0, dtype=np.float32)
    dem[0, :] = np.nan  # e.g. a DEM nodata row
    rgb = np.full((3, 8, 8), 50, dtype=np.uint8)

    patches = ing.patchify_region(dem, rgb, "with_nodata", str(tmp_path), "hilly",
                                   patch_size=8, min_valid_fraction=0.5)

    assert len(patches) == 1
    with rasterio.open(patches[0]["temp_truth"]) as src:
        relative = src.read(1)
    assert (relative[0, :] == ing.NODATA_SENTINEL).all()
    assert (relative[1:, :] != ing.NODATA_SENTINEL).all()


def test_patchify_region_pads_edge_patches(tmp_path):
    dem = np.full((10, 10), 50.0, dtype=np.float32)
    rgb = np.full((3, 10, 10), 50, dtype=np.uint8)

    patches = ing.patchify_region(dem, rgb, "edge", str(tmp_path), "sparse", patch_size=8)

    padded_flags = {p["patch_id"]: p["padded"] for p in patches}
    assert padded_flags["edge_patch_0_0"] is False  # full 8x8
    assert padded_flags["edge_patch_1_1"] is True  # 2x2 remainder, padded


def test_ingest_region_end_to_end_on_synthetic_files(tmp_path):
    dem_path = tmp_path / "dem.tif"
    rgb_path = tmp_path / "rgb.tif"
    transform = from_origin(0, 16, 1, 1)

    dem = np.linspace(500, 520, 16 * 16, dtype=np.float32).reshape(16, 16)
    _write_tif(dem_path, dem, "float32", transform)

    rgb = np.full((3, 16, 16), 80, dtype=np.uint8)
    _write_tif(rgb_path, rgb, "uint8", transform)

    region = {"label": "synthetic", "source": "test_source", "terrain_type": "hilly",
              "dem": str(dem_path), "rgb": str(rgb_path)}
    patches = ing.ingest_region(region, str(tmp_path / "temp"), patch_size=8)

    assert len(patches) == 4  # 16x16 at patch_size 8 -> 2x2, no padding needed
    assert all(p["source_tile"] == "synthetic" for p in patches)
    assert all(p["terrain_type"] == "hilly" for p in patches)
