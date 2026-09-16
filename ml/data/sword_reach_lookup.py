#!/usr/bin/env python3
"""River-silt use case — resolves GloRivSed's (OC_data.csv) `reach_ID` to
real lat/lon, using SWORD's own reach shapefiles.

SWORD's reach records already carry a representative `x`/`y` point per
reach (no need to compute a polyline centroid ourselves — checked directly
against a real extracted file before writing this, not assumed). Only the
Oceania (`OC`) continent is extracted locally
(ml/data/river_silt_raw/sword/shp/OC/, gitignored, 79MB) — matches
OC_data.csv's own scope; the full SWORD archive is a ~2GB global download
not kept locally (docs/open_decisions.md, 2026-09-14).

Uses `pyshp` (pure Python, `pip install pyshp`) — no GDAL/geopandas needed
for this simple id->point lookup.

Run from the repo root:
    python ml/data/sword_reach_lookup.py
"""

from __future__ import annotations

import csv
import glob

import shapefile

DEFAULT_SWORD_DIR = "ml/data/river_silt_raw/sword/shp/OC"
DEFAULT_OC_CSV = "ml/data/river_silt_raw/OC_data.csv"
DEFAULT_OUT_CSV = "ml/data/river_silt_raw/OC_data_with_coords.csv"


def build_reach_coordinate_index(sword_dir: str = DEFAULT_SWORD_DIR) -> dict[str, tuple[float, float]]:
    """reach_id (str) -> (lat, lon). Reads every *reaches*.shp part in
    sword_dir — SWORD splits each continent into several hydrobasin files,
    none of which overlap in reach_id."""
    index: dict[str, tuple[float, float]] = {}
    for shp_path in sorted(glob.glob(f"{sword_dir}/*reaches*.shp")):
        sf = shapefile.Reader(shp_path)
        reach_idx = [f[0] for f in sf.fields[1:]].index("reach_id")
        x_idx = [f[0] for f in sf.fields[1:]].index("x")
        y_idx = [f[0] for f in sf.fields[1:]].index("y")
        for record in sf.records():
            index[str(record[reach_idx])] = (record[y_idx], record[x_idx])  # (lat, lon)
    return index


def join_oc_data_to_coordinates(oc_csv: str = DEFAULT_OC_CSV, sword_dir: str = DEFAULT_SWORD_DIR) -> tuple[list[dict], int]:
    """Reads OC_data.csv, adds lat/lon columns from the SWORD index. Rows
    whose reach_ID isn't found are dropped (reported via the returned
    miss count), not silently kept with fabricated coordinates."""
    index = build_reach_coordinate_index(sword_dir)
    with open(oc_csv, newline="") as f:
        rows = list(csv.DictReader(f))

    joined, missed = [], 0
    for row in rows:
        coords = index.get(row["reach_ID"])
        if coords is None:
            missed += 1
            continue
        lat, lon = coords
        joined.append({**row, "lat": lat, "lon": lon})

    return joined, missed


def main():
    joined, missed = join_oc_data_to_coordinates()
    print(f"{len(joined)} rows resolved to real coordinates, {missed} reach_IDs not found in SWORD OC index")

    if joined:
        with open(DEFAULT_OUT_CSV, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=list(joined[0].keys()))
            writer.writeheader()
            writer.writerows(joined)
        print(f"Wrote {DEFAULT_OUT_CSV}")


if __name__ == "__main__":
    main()
