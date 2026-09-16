import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "features"))
from koppen_climate import KOPPEN_GROUPS, _nearest_grid_center, get_koppen_group, get_koppen_subtype  # noqa: E402


def test_nearest_grid_center_snaps_to_regular_half_degree_grid():
    assert _nearest_grid_center(40.3) == 40.25
    assert _nearest_grid_center(40.6) == 40.75
    assert _nearest_grid_center(-4.7) == -4.75


def test_get_koppen_group_returns_known_polar_zone_for_antarctica():
    # -89.75, -179.75 is the table's first real row, class "EF" (polar).
    group = get_koppen_group(-89.75, -179.75)
    assert group == "E"
    assert group in KOPPEN_GROUPS


def test_get_koppen_group_returns_a_real_tropical_zone():
    # Amazon basin, deep in a known Af/Am tropical region.
    group = get_koppen_group(-3.0, -60.0)
    assert group == "A"


def test_get_koppen_subtype_is_finer_than_group():
    subtype = get_koppen_subtype(-3.0, -60.0)
    assert subtype is not None and subtype.startswith("A")
    assert len(subtype) >= 2  # a real subtype, not just the top-level group
