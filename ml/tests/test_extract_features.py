"""Tests for ml/features/extract_features.py — Phase 3 Chunk 1.

The batch model call is monkeypatched everywhere except test_pipeline.py's
end-to-end test, so this file runs fast and doesn't duplicate the real-model
coverage that already exists there.
"""

import csv

import numpy as np
import pytest
import rasterio
from PIL import Image
from rasterio.transform import from_origin

from features import extract_features as ef

TRANSFORM = from_origin(0, 10, 1, 1)


def _write_rgb_patch(path, size=256):
    count = 3
    bands = np.random.randint(0, 255, (count, size, size), dtype=np.uint8)
    with rasterio.open(
        path, "w", driver="GTiff", height=size, width=size, count=count,
        dtype="uint8", crs="EPSG:4326", transform=TRANSFORM,
    ) as dst:
        dst.write(bands)


def _manifest_entry(patch_id, split, terrain, rgb_path, has_truth=True):
    return {
        "patch_id": patch_id,
        "source": "dfc2019",
        "source_tile": "tile0",
        "split": split,
        "terrain_type": terrain,
        "rgb_path": rgb_path,
        "truth_path": f"{rgb_path}.truth" if has_truth else None,
        "std": 1.0,
        "roughness": 0.01,
        "padded": False,
        "crs": "EPSG:4326",
    }


def _fake_batch_depth(monkeypatch, size=256):
    """Returns solid-grey 'L' images matching each input's size — fast stand-in
    for the real Depth Anything V2 call."""

    def fake(images):
        return [Image.new("L", img.size, color=128) for img in images]

    monkeypatch.setattr(ef, "estimate_relative_depth_batch", fake)


def _fake_segment(monkeypatch):
    """Solid 'building' class map — fast stand-in for the real segmentation
    model, matching each input's size."""

    def fake(image):
        w, h = image.size
        return np.zeros((h, w), dtype=np.uint8)  # 0 == BUILDING, see CLASS_TO_IDX

    monkeypatch.setattr(ef, "segment_image", fake)


def _build_manifest(tmp_path, per_split=(("train", "urban"), ("val", "urban"), ("test", "urban"))):
    manifest = []
    rgb_dir = tmp_path / "rgb"
    rgb_dir.mkdir()
    for i, (split, terrain) in enumerate(per_split):
        rgb_path = rgb_dir / f"p{i}_RGB.tif"
        _write_rgb_patch(rgb_path)
        manifest.append(_manifest_entry(f"p{i}", split, terrain, str(rgb_path.relative_to(tmp_path))))
    return manifest


def test_verify_dataset_readiness_filters_out_validation_only(tmp_path):
    manifest = _build_manifest(tmp_path)
    rgb_dir = tmp_path / "rgb"
    bhuvan_path = rgb_dir / "bhuvan_RGB.tif"
    _write_rgb_patch(bhuvan_path)
    manifest.append(
        _manifest_entry("bhuvan_0", "validation_only", "unclassified",
                         str(bhuvan_path.relative_to(tmp_path)), has_truth=False)
    )

    trainable = ef.verify_dataset_readiness(manifest, data_root=str(tmp_path))

    assert len(trainable) == 3
    assert all(e["split"] != "validation_only" for e in trainable)


def test_verify_dataset_readiness_raises_on_missing_split(tmp_path):
    manifest = _build_manifest(tmp_path, per_split=(("train", "urban"), ("val", "urban")))
    with pytest.raises(AssertionError, match="missing required split"):
        ef.verify_dataset_readiness(manifest, data_root=str(tmp_path))


def test_verify_dataset_readiness_raises_on_wrong_patch_size(tmp_path):
    manifest = _build_manifest(tmp_path)
    # Corrupt one patch to the wrong size.
    _write_rgb_patch(tmp_path / manifest[0]["rgb_path"], size=128)

    with pytest.raises(AssertionError, match="expected 256x256"):
        ef.verify_dataset_readiness(manifest, data_root=str(tmp_path))


def test_run_batch_depth_extraction_writes_expected_output_structure(tmp_path, monkeypatch):
    _fake_batch_depth(monkeypatch)
    manifest = _build_manifest(tmp_path)
    cache_dir = tmp_path / "cache"

    result = ef.run_batch_depth_extraction(manifest, data_root=str(tmp_path), cache_dir=str(cache_dir))

    assert result == {"total": 3, "skipped": 0, "processed": 3}
    for entry in manifest:
        out_path = tmp_path / "cache" / entry["split"] / entry["terrain_type"] / f"{entry['patch_id']}_depth.png"
        assert out_path.exists()
        with Image.open(out_path) as img:
            assert img.mode == "L"
            assert img.size == (256, 256)


def test_run_batch_depth_extraction_respects_limit(tmp_path, monkeypatch):
    _fake_batch_depth(monkeypatch)
    manifest = _build_manifest(tmp_path)
    cache_dir = tmp_path / "cache"

    result = ef.run_batch_depth_extraction(manifest, data_root=str(tmp_path), cache_dir=str(cache_dir), limit=1)

    assert result == {"total": 1, "skipped": 0, "processed": 1}


def _write_truth_patch(path, values, nodata=None, size=4):
    """values: 2D array or scalar to fill a size x size float32 patch."""
    arr = np.full((size, size), values, dtype=np.float32) if np.isscalar(values) else values.astype(np.float32)
    with rasterio.open(
        path, "w", driver="GTiff", height=size, width=size, count=1,
        dtype="float32", crs="EPSG:4326", transform=TRANSFORM, nodata=nodata,
    ) as dst:
        dst.write(arr[np.newaxis, ...])


def test_depth_features_has_no_nans_and_matches_schema(tmp_path):
    depth_path = tmp_path / "d.png"
    depth = np.random.randint(0, 255, (16, 16), dtype=np.uint8)
    Image.fromarray(depth, "L").save(depth_path)

    features = ef._depth_features(str(depth_path))

    assert set(features.keys()) == set(ef.DEPTH_FEATURE_COLUMNS)
    assert all(v == v for v in features.values())  # no NaNs
    assert features["depth_min"] <= features["depth_p50"] <= features["depth_max"]


def test_semantic_features_matches_schema_and_sums_to_one(tmp_path):
    class_map_path = tmp_path / "c.png"
    class_map = np.random.randint(0, 4, (16, 16), dtype=np.uint8)
    Image.fromarray(class_map, "L").save(class_map_path)

    features = ef._semantic_features(str(class_map_path))

    assert set(features.keys()) == set(ef.SEMANTIC_FEATURE_COLUMNS)
    assert all(v == v for v in features.values())  # no NaNs
    assert abs(sum(features.values()) - 1.0) < 1e-6


def test_run_batch_semantic_extraction_writes_expected_output_structure(tmp_path, monkeypatch):
    _fake_segment(monkeypatch)
    manifest = _build_manifest(tmp_path)
    cache_dir = tmp_path / "semantic_cache"

    result = ef.run_batch_semantic_extraction(manifest, data_root=str(tmp_path), cache_dir=str(cache_dir))

    assert result == {"total": 3, "skipped": 0, "processed": 3}
    for entry in manifest:
        out_path = cache_dir / entry["split"] / entry["terrain_type"] / f"{entry['patch_id']}_classmap.png"
        assert out_path.exists()
        with Image.open(out_path) as img:
            assert img.mode == "L"
            assert img.size == (256, 256)


def test_run_batch_semantic_extraction_resumes_without_recalling_model(tmp_path, monkeypatch):
    _fake_segment(monkeypatch)
    manifest = _build_manifest(tmp_path)
    cache_dir = tmp_path / "semantic_cache"

    first = ef.run_batch_semantic_extraction(manifest, data_root=str(tmp_path), cache_dir=str(cache_dir))
    assert first["processed"] == 3

    def fail_if_called(image):
        raise AssertionError("model should not be re-invoked for already-cached patches")

    monkeypatch.setattr(ef, "segment_image", fail_if_called)

    second = ef.run_batch_semantic_extraction(manifest, data_root=str(tmp_path), cache_dir=str(cache_dir))
    assert second == {"total": 3, "skipped": 3, "processed": 0}


def test_height_label_excludes_nodata_pixels(tmp_path):
    truth_path = tmp_path / "truth.tif"
    arr = np.full((4, 4), 100.0, dtype=np.float32)
    arr[0, :] = -9999.0  # a padded/nodata row that must not skew the mean
    _write_truth_patch(truth_path, arr, nodata=-9999.0)

    label = ef._height_label(str(truth_path))

    assert label == {"height_mean": 100.0, "height_min": 100.0, "height_max": 100.0}


def test_height_label_excludes_nan_even_without_nodata_set(tmp_path):
    """Regression test for the 2026-08-31 bug: a stray NaN pixel with no
    nodata attribute set used to poison height_mean/min/max to NaN for every
    one of DFC2019's 33 original 'hilly' patches — see docs/open_decisions.md."""
    truth_path = tmp_path / "truth.tif"
    arr = np.full((4, 4), 10.0, dtype=np.float32)
    arr[0, 0] = np.nan
    _write_truth_patch(truth_path, arr, nodata=None)

    label = ef._height_label(str(truth_path))

    assert label == {"height_mean": 10.0, "height_min": 10.0, "height_max": 10.0}


def test_height_label_returns_none_when_fully_nodata(tmp_path):
    truth_path = tmp_path / "truth.tif"
    _write_truth_patch(truth_path, -9999.0, nodata=-9999.0)

    assert ef._height_label(str(truth_path)) is None


def test_height_label_treats_all_pixels_valid_when_nodata_unset(tmp_path):
    truth_path = tmp_path / "truth.tif"
    _write_truth_patch(truth_path, 50.0, nodata=None)

    label = ef._height_label(str(truth_path))

    assert label["height_mean"] == 50.0


def test_build_feature_table_skips_patch_with_no_cached_depth(tmp_path):
    manifest = _build_manifest(tmp_path, per_split=(("train", "urban"),))
    # No depth cache written for this entry -> must be skipped, not crash.
    rows, skipped = ef.build_feature_table(manifest, cache_dir=str(tmp_path / "cache"), data_root=str(tmp_path))

    assert rows == []
    assert len(skipped) == 1
    assert skipped[0][1] == "no cached depth map"


def test_build_feature_table_skips_patch_with_no_valid_ground_truth(tmp_path, monkeypatch):
    _fake_batch_depth(monkeypatch)
    manifest = _build_manifest(tmp_path, per_split=(("train", "urban"),))
    cache_dir = tmp_path / "cache"
    ef.run_batch_depth_extraction(manifest, data_root=str(tmp_path), cache_dir=str(cache_dir))

    # truth_path in _manifest_entry doesn't point at a real file -> simulate
    # a real but fully-invalid truth patch instead.
    truth_path = tmp_path / "truth0.tif"
    _write_truth_patch(truth_path, -9999.0, nodata=-9999.0)
    manifest[0]["truth_path"] = str(truth_path.relative_to(tmp_path))

    rows, skipped = ef.build_feature_table(manifest, cache_dir=str(cache_dir), data_root=str(tmp_path))

    assert rows == []
    assert skipped == [(manifest[0]["patch_id"], "no valid ground-truth pixels")]


def test_build_feature_table_end_to_end_row_has_frozen_columns(tmp_path, monkeypatch):
    _fake_batch_depth(monkeypatch)
    _fake_segment(monkeypatch)
    manifest = _build_manifest(tmp_path, per_split=(("train", "urban"), ("val", "hilly")))
    cache_dir = tmp_path / "cache"
    semantic_cache_dir = tmp_path / "semantic_cache"
    ef.run_batch_depth_extraction(manifest, data_root=str(tmp_path), cache_dir=str(cache_dir))
    ef.run_batch_semantic_extraction(manifest, data_root=str(tmp_path), cache_dir=str(semantic_cache_dir))

    for i, entry in enumerate(manifest):
        truth_path = tmp_path / f"truth{i}.tif"
        _write_truth_patch(truth_path, 30.0 + i * 10)
        entry["truth_path"] = str(truth_path.relative_to(tmp_path))

    rows, skipped = ef.build_feature_table(
        manifest, cache_dir=str(cache_dir), data_root=str(tmp_path), semantic_cache_dir=str(semantic_cache_dir)
    )

    assert skipped == []
    assert len(rows) == 2
    expected_columns = set(ef.METADATA_COLUMNS + ef.FEATURE_COLUMNS + ef.LABEL_COLUMNS)
    assert set(rows[0].keys()) == expected_columns
    assert rows[0]["height_mean"] == 30.0
    assert rows[1]["height_mean"] == 40.0


def test_build_feature_table_skips_patch_with_no_cached_semantic(tmp_path, monkeypatch):
    _fake_batch_depth(monkeypatch)
    manifest = _build_manifest(tmp_path, per_split=(("train", "urban"),))
    cache_dir = tmp_path / "cache"
    ef.run_batch_depth_extraction(manifest, data_root=str(tmp_path), cache_dir=str(cache_dir))

    truth_path = tmp_path / "truth0.tif"
    _write_truth_patch(truth_path, 30.0)
    manifest[0]["truth_path"] = str(truth_path.relative_to(tmp_path))

    # No semantic cache written for this entry -> must be skipped, not crash.
    rows, skipped = ef.build_feature_table(manifest, cache_dir=str(cache_dir), data_root=str(tmp_path))

    assert rows == []
    assert skipped == [(manifest[0]["patch_id"], "no cached semantic class map")]


def test_save_feature_table_writes_frozen_column_order(tmp_path):
    rows = [{col: 1.0 for col in ef.METADATA_COLUMNS + ef.FEATURE_COLUMNS + ef.LABEL_COLUMNS}]
    out_path = tmp_path / "features.csv"

    ef.save_feature_table(rows, str(out_path))

    with open(out_path) as f:
        header = f.readline().strip().split(",")
    assert header == ef.METADATA_COLUMNS + ef.FEATURE_COLUMNS + ef.LABEL_COLUMNS


def test_save_feature_table_by_split_writes_one_file_per_split(tmp_path):
    def row(patch_id, split):
        r = {col: 1.0 for col in ef.METADATA_COLUMNS + ef.FEATURE_COLUMNS + ef.LABEL_COLUMNS}
        r["patch_id"], r["split"] = patch_id, split
        return r

    rows = [row("a", "train"), row("b", "train"), row("c", "val"), row("d", "test")]
    features_dir = tmp_path / "features"

    paths = ef.save_feature_table_by_split(rows, features_dir=str(features_dir))

    assert set(paths.keys()) == {"train", "val", "test"}
    with open(paths["train"]) as f:
        assert len(f.readlines()) == 3  # header + 2 rows
    with open(paths["val"]) as f:
        assert len(f.readlines()) == 2  # header + 1 row


def test_baseline_mean_predictor_loads_split_files_without_error(tmp_path):
    """Chunk 4's acceptance check: Phase 4 must be able to load the cache
    and run something trivial against it without errors."""

    def row(patch_id, split, height_mean):
        r = {col: 1.0 for col in ef.METADATA_COLUMNS + ef.FEATURE_COLUMNS + ef.LABEL_COLUMNS}
        r["patch_id"], r["split"], r["height_mean"] = patch_id, split, height_mean
        return r

    rows = [row("a", "train", 10.0), row("b", "train", 20.0), row("c", "val", 12.0), row("d", "val", 18.0)]
    paths = ef.save_feature_table_by_split(rows, features_dir=str(tmp_path))

    with open(paths["train"]) as f:
        train_rows = list(csv.DictReader(f))
    with open(paths["val"]) as f:
        val_rows = list(csv.DictReader(f))

    baseline = sum(float(r["height_mean"]) for r in train_rows) / len(train_rows)
    mae = sum(abs(float(r["height_mean"]) - baseline) for r in val_rows) / len(val_rows)

    assert baseline == 15.0
    assert mae == 3.0  # mean(|12-15|, |18-15|) = mean(3, 3) = 3


def test_run_batch_depth_extraction_resumes_without_recalling_model(tmp_path, monkeypatch):
    _fake_batch_depth(monkeypatch)
    manifest = _build_manifest(tmp_path)
    cache_dir = tmp_path / "cache"

    first = ef.run_batch_depth_extraction(manifest, data_root=str(tmp_path), cache_dir=str(cache_dir))
    assert first["processed"] == 3

    def fail_if_called(images):
        raise AssertionError("model should not be re-invoked for already-cached patches")

    monkeypatch.setattr(ef, "estimate_relative_depth_batch", fail_if_called)

    second = ef.run_batch_depth_extraction(manifest, data_root=str(tmp_path), cache_dir=str(cache_dir))
    assert second == {"total": 3, "skipped": 3, "processed": 0}
