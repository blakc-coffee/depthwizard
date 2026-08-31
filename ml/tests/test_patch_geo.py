"""Tests for ml/calibration/patch_geo.py — Phase 4 Chunk 2's per-patch
geo-bounds recovery. Verified against real data/processed/v1 patches
(no synthetic fixtures — the whole point is recovering *real* bounds)."""

from calibration.patch_geo import get_patch_bounds


def _entry(source, source_tile, patch_id):
    return {"source": source, "source_tile": source_tile, "patch_id": patch_id}


def test_dfc2019_patches_have_no_recoverable_bounds():
    assert get_patch_bounds(_entry("dfc2019", "OMA_176_004", "OMA_176_004_patch_0_1")) is None


def test_unknown_region_label_returns_none():
    assert get_patch_bounds(_entry("copernicus_dem", "atlantis", "atlantis_patch_0_0")) is None


def test_malformed_patch_id_returns_none():
    assert get_patch_bounds(_entry("copernicus_dem", "scotland", "not_a_valid_id")) is None


def test_scotland_patch_recovers_real_scottish_highlands_coordinates():
    bounds = get_patch_bounds(_entry("copernicus_dem", "scotland", "scotland_patch_12_3"))

    assert bounds is not None
    # Scotland's DEM tile is N56_00_W005_00 -> 56-57N, -5..-4W
    assert 56.0 <= bounds.south < bounds.north <= 57.0
    assert -5.0 <= bounds.west < bounds.east <= -4.0


def test_adjacent_patches_do_not_overlap():
    b1 = get_patch_bounds(_entry("copernicus_dem", "scotland", "scotland_patch_0_0"))
    b2 = get_patch_bounds(_entry("copernicus_dem", "scotland", "scotland_patch_0_1"))

    assert b1 is not None and b2 is not None
    assert b1.east <= b2.west + 1e-9  # patch (0,1) is one column east of (0,0)
