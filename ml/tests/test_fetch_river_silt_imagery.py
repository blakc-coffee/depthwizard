import csv
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "data"))
from fetch_river_silt_imagery import load_river_rows, sample_rows  # noqa: E402


def _write_csv(path, rows):
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["SiteID", "Lat", "Lon", "Value", "Date", "WaterType"])
        writer.writeheader()
        writer.writerows(rows)


def test_load_river_rows_filters_to_river_types_only(tmp_path):
    csv_path = tmp_path / "ssc.csv"
    _write_csv(csv_path, [
        {"SiteID": "a", "Lat": "10.0", "Lon": "20.0", "Value": "5.0", "Date": "2020-01-01", "WaterType": "River"},
        {"SiteID": "b", "Lat": "11.0", "Lon": "21.0", "Value": "6.0", "Date": "2020-02-01", "WaterType": "Lake"},
        {"SiteID": "c", "Lat": "12.0", "Lon": "22.0", "Value": "7.0", "Date": "2020-03-01", "WaterType": "River/Stream"},
    ])
    rows = load_river_rows(csv_path)
    assert {r["site_id"] for r in rows} == {"a", "c"}
    assert rows[0]["date"] == datetime(2020, 1, 1) or rows[1]["date"] == datetime(2020, 1, 1)


def test_load_river_rows_skips_malformed_rows_without_crashing(tmp_path):
    csv_path = tmp_path / "ssc.csv"
    _write_csv(csv_path, [
        {"SiteID": "a", "Lat": "not_a_number", "Lon": "20.0", "Value": "5.0", "Date": "2020-01-01", "WaterType": "River"},
        {"SiteID": "b", "Lat": "11.0", "Lon": "21.0", "Value": "6.0", "Date": "2020-02-01", "WaterType": "River"},
    ])
    rows = load_river_rows(csv_path)
    assert len(rows) == 1
    assert rows[0]["site_id"] == "b"


def test_sample_rows_is_deterministic_given_a_seed():
    rows = [{"site_id": str(i)} for i in range(50)]
    first = sample_rows(rows.copy(), n_samples=5, seed=7)
    second = sample_rows(rows.copy(), n_samples=5, seed=7)
    assert first == second
    assert len(first) == 5
