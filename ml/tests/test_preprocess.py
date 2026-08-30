"""Tests for ml/data/preprocess.py — terrain classification, patchify edge
policy, and stratified split logic (Phase 2)."""

import os

import numpy as np
import rasterio
from rasterio.transform import from_origin

from data.preprocess import (
    classify_terrain,
    patchify_rgb_only,
    patchify_tile,
    split_and_stratify_dataset,
)

TRANSFORM = from_origin(0, 10, 1, 1)


def _write_tif(path, bands: np.ndarray, dtype, nodata=None):
    count, height, width = bands.shape
    with rasterio.open(
        path, "w", driver="GTiff", height=height, width=width, count=count,
        dtype=dtype, crs="EPSG:4326", transform=TRANSFORM, nodata=nodata,
    ) as dst:
        dst.write(bands)


def test_classify_terrain_flat_is_sparse():
    flat = np.full((20, 20), 5.0, dtype=np.float32)
    terrain, std, _ = classify_terrain(flat)
    assert terrain == "sparse"
    assert std < 1.0


def test_classify_terrain_high_variance_is_urban():
    rng = np.random.default_rng(0)
    buildings = rng.normal(loc=20, scale=6.0, size=(20, 20)).astype(np.float32)
    terrain, std, _ = classify_terrain(buildings)
    assert terrain == "urban"
    assert std >= 3.5


def test_classify_terrain_excludes_nodata():
    arr = np.full((10, 10), 5.0, dtype=np.float32)
    arr[0, :] = -9999.0  # nodata row would otherwise blow up the std
    terrain, std, _ = classify_terrain(arr, nodata=-9999.0)
    assert terrain == "sparse"
    assert std == 0.0


def test_classify_terrain_excludes_stray_nan_regardless_of_nodata(tmp_path):
    """Regression test for the 2026-08-31 bug: a stray NaN pixel (nodata
    attribute unset) used to make std/roughness NaN, which fails every
    numeric threshold comparison and silently defaults to 'hilly'. All 33 of
    DFC2019's original 'hilly' patches turned out to be this bug — see
    docs/open_decisions.md."""
    rng = np.random.default_rng(0)
    buildings = rng.normal(loc=20, scale=6.0, size=(20, 20)).astype(np.float32)
    buildings[3, 7] = np.nan  # one stray NaN pixel, no nodata attribute set

    terrain, std, roughness = classify_terrain(buildings, nodata=None)

    assert terrain == "urban"  # matches what the NaN-free variant classifies as
    assert std == std and roughness == roughness  # neither is NaN


def test_classify_terrain_excludes_nan_even_when_nodata_also_set():
    """`!=` never excludes NaN, even when a nodata sentinel is set — NaN and
    the nodata sentinel are two independent things to filter out."""
    arr = np.full((10, 10), 5.0, dtype=np.float32)
    arr[0, :] = -9999.0
    arr[1, 0] = np.nan

    terrain, std, roughness = classify_terrain(arr, nodata=-9999.0)

    assert terrain == "sparse"
    assert std == std and roughness == roughness


def test_patchify_tile_pads_edge_patches(tmp_path):
    rgb_path = tmp_path / "tile_RGB.tif"
    truth_path = tmp_path / "tile_AGL.tif"
    # 300px tile, 256 patch size -> 2x2 = 4 patches, all but the top-left padded
    _write_tif(rgb_path, np.zeros((3, 300, 300), dtype=np.uint8), "uint8")
    _write_tif(truth_path, np.full((1, 300, 300), 5.0, dtype=np.float32), "float32", nodata=-9999.0)

    patches = patchify_tile(str(rgb_path), str(truth_path), patch_size=256, temp_dir=str(tmp_path / "temp"))

    assert len(patches) == 4
    padded_flags = {p["patch_id"]: p["padded"] for p in patches}
    assert padded_flags["tile_patch_0_0"] is False  # full 256x256, no padding needed
    assert padded_flags["tile_patch_1_1"] is True  # bottom-right corner is a 44x44 remainder

    with rasterio.open(patches[0]["temp_rgb"]) as f:
        assert f.width == 256 and f.height == 256


def test_patchify_rgb_only_has_no_ground_truth_fields(tmp_path):
    rgb_path = tmp_path / "bhuvan_RGB.tif"
    _write_tif(rgb_path, np.zeros((3, 100, 100), dtype=np.uint8), "uint8")

    patches = patchify_rgb_only(str(rgb_path), patch_size=256, temp_dir=str(tmp_path / "temp"))

    assert len(patches) == 1
    assert "terrain_type" not in patches[0]
    assert patches[0]["padded"] is True


def _fake_patch(patch_id, terrain_type, source_dir):
    rgb = source_dir / f"{patch_id}_rgb.tif"
    truth = source_dir / f"{patch_id}_truth.tif"
    rgb.write_bytes(b"")
    truth.write_bytes(b"")
    return {
        "patch_id": patch_id,
        "source_tile": "tile0",
        "temp_rgb": str(rgb),
        "temp_truth": str(truth),
        "terrain_type": terrain_type,
        "std": 1.0,
        "roughness": 0.01,
        "padded": False,
        "crs": "EPSG:4326",
    }


def test_split_and_stratify_keeps_every_terrain_in_train_and_val(tmp_path):
    temp_dir = tmp_path / "temp"
    temp_dir.mkdir()
    patches = [_fake_patch(f"urban_{i}", "urban", temp_dir) for i in range(10)]
    patches += [_fake_patch(f"forest_{i}", "forested", temp_dir) for i in range(10)]

    manifest = split_and_stratify_dataset(patches, str(tmp_path / "out"), seed=42)

    assert len(manifest) == 20
    splits_by_terrain = {}
    for entry in manifest:
        splits_by_terrain.setdefault(entry["terrain_type"], set()).add(entry["split"])
    assert splits_by_terrain["urban"] >= {"train", "val"}
    assert splits_by_terrain["forested"] >= {"train", "val"}


def test_split_and_stratify_is_reproducible_across_runs(tmp_path):
    def run(seed, root):
        temp_dir = root / "temp"
        temp_dir.mkdir(parents=True)
        patches = [_fake_patch(f"p{i}", "urban", temp_dir) for i in range(6)]
        return split_and_stratify_dataset(patches, str(root / "out"), seed=seed)

    manifest_a = run(42, tmp_path / "a")
    manifest_b = run(42, tmp_path / "b")

    splits_a = {e["patch_id"]: e["split"] for e in manifest_a}
    splits_b = {e["patch_id"]: e["split"] for e in manifest_b}
    assert splits_a == splits_b


def test_single_patch_terrain_goes_entirely_to_train(tmp_path):
    temp_dir = tmp_path / "temp"
    temp_dir.mkdir()
    patches = [_fake_patch("only_one", "hilly", temp_dir)]

    manifest = split_and_stratify_dataset(patches, str(tmp_path / "out"), seed=42)

    assert len(manifest) == 1
    assert manifest[0]["split"] == "train"
