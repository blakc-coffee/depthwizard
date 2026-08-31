"""Tests for ml/data/download_datasets.py — archive unpacking and Bhuvan
sample registration (Phase 2, Chunk 1/4)."""

import os
import zipfile

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from data.download_datasets import add_bhuvan_sample, inspect_format, unpack_archives

TRANSFORM = from_origin(0, 10, 1, 1)


def _write_tif(path, bands: np.ndarray, dtype, nodata=None):
    count, height, width = bands.shape
    with rasterio.open(
        path, "w", driver="GTiff", height=height, width=width, count=count,
        dtype=dtype, crs="EPSG:4326", transform=TRANSFORM, nodata=nodata,
    ) as dst:
        dst.write(bands)


def test_unpack_archives_extracts_matching_suffix_only(tmp_path):
    archive_dir = tmp_path / "archives"
    archive_dir.mkdir()
    rgb_zip = archive_dir / "Train-Track1-RGB.zip"
    truth_zip = archive_dir / "Train-Track1-Truth.zip"

    with zipfile.ZipFile(rgb_zip, "w") as zf:
        zf.writestr("tile0_RGB.tif", b"fake-rgb-bytes")
        zf.writestr("readme.txt", b"not a tile")
    with zipfile.ZipFile(truth_zip, "w") as zf:
        zf.writestr("tile0_AGL.tif", b"fake-truth-bytes")

    out_dir = tmp_path / "track1"
    unpack_archives(archive_dir=str(archive_dir), out_dir=str(out_dir))

    assert (out_dir / "rgb" / "tile0_RGB.tif").read_bytes() == b"fake-rgb-bytes"
    assert (out_dir / "truth" / "tile0_AGL.tif").read_bytes() == b"fake-truth-bytes"
    assert not (out_dir / "rgb" / "readme.txt").exists()


def test_unpack_archives_missing_zip_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        unpack_archives(archive_dir=str(tmp_path / "nope"), out_dir=str(tmp_path / "out"))


def test_add_bhuvan_sample_copies_file(tmp_path):
    src = tmp_path / "source.tif"
    src.write_bytes(b"bhuvan-bytes")
    out_dir = tmp_path / "bhuvan"

    dest = add_bhuvan_sample(str(src), tile_name="chennai_01", out_dir=str(out_dir))

    assert os.path.exists(dest)
    assert open(dest, "rb").read() == b"bhuvan-bytes"
    assert dest.endswith("chennai_01.tif")


def test_add_bhuvan_sample_missing_source_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        add_bhuvan_sample(str(tmp_path / "missing.tif"), out_dir=str(tmp_path / "out"))


def test_inspect_format_writes_notes_for_aligned_pair(tmp_path):
    track1_dir = tmp_path / "track1"
    (track1_dir / "rgb").mkdir(parents=True)
    (track1_dir / "truth").mkdir(parents=True)

    _write_tif(track1_dir / "rgb" / "t0_RGB.tif", np.zeros((3, 8, 8), dtype=np.uint8), "uint8")
    _write_tif(
        track1_dir / "truth" / "t0_AGL.tif",
        np.full((1, 8, 8), 12.5, dtype=np.float32),
        "float32",
        nodata=-9999.0,
    )

    notes_path = tmp_path / "FORMAT_NOTES.md"
    inspect_format(track1_dir=str(track1_dir), notes_path=str(notes_path))

    content = notes_path.read_text()
    assert "t0" in content
    assert "dimensions match: True" in content


def test_inspect_format_no_tiles_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        inspect_format(track1_dir=str(tmp_path / "empty"), notes_path=str(tmp_path / "notes.md"))
