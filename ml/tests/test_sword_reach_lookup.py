import csv
import sys
from pathlib import Path

import shapefile

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "data"))
from sword_reach_lookup import build_reach_coordinate_index, join_oc_data_to_coordinates  # noqa: E402


def _write_test_shapefile(dir_path: Path, name: str, reaches: list[tuple[str, float, float]]):
    path = str(dir_path / name)
    with shapefile.Writer(path, shapeType=shapefile.POLYLINE) as w:
        w.field("x", "F", decimal=10)
        w.field("y", "F", decimal=10)
        w.field("reach_id", "C")
        for reach_id, x, y in reaches:
            w.line([[[x, y], [x + 0.01, y + 0.01]]])
            w.record(x=x, y=y, reach_id=reach_id)


def test_build_reach_coordinate_index_reads_x_y_fields(tmp_path):
    _write_test_shapefile(tmp_path, "test_reaches.shp", [("111", 103.5, -4.7), ("222", 140.0, -10.0)])
    index = build_reach_coordinate_index(str(tmp_path))
    assert index["111"] == (-4.7, 103.5)
    assert index["222"] == (-10.0, 140.0)


def test_build_reach_coordinate_index_merges_multiple_shapefile_parts(tmp_path):
    _write_test_shapefile(tmp_path, "hb51_reaches.shp", [("111", 103.5, -4.7)])
    _write_test_shapefile(tmp_path, "hb52_reaches.shp", [("222", 140.0, -10.0)])
    index = build_reach_coordinate_index(str(tmp_path))
    assert set(index.keys()) == {"111", "222"}


def test_join_oc_data_to_coordinates_drops_unresolvable_rows_not_silently(tmp_path):
    _write_test_shapefile(tmp_path, "test_reaches.shp", [("111", 103.5, -4.7)])
    csv_path = tmp_path / "OC_data.csv"
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["reach_ID", "y_pred"])
        writer.writeheader()
        writer.writerow({"reach_ID": "111", "y_pred": "5.0"})
        writer.writerow({"reach_ID": "999_unknown", "y_pred": "6.0"})

    joined, missed = join_oc_data_to_coordinates(oc_csv=str(csv_path), sword_dir=str(tmp_path))
    assert missed == 1
    assert len(joined) == 1
    assert joined[0]["lat"] == -4.7
    assert joined[0]["lon"] == 103.5
