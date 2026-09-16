#!/usr/bin/env python3
"""River-silt use case, Chunk 1 — pull Sentinel-2 RGB crops matched to real
in-situ SSC (suspended sediment concentration) readings from
ml/data/river_silt_raw/SSC_in_situ.csv (Lat, Lon, Value, Date, WaterType).

Only `SSC_in_situ.csv` is used here, not `OC_data.csv` (GloRivSed) — that
file's `reach_ID` needs a separate SWORD river-geometry join to resolve to
coordinates at all, and its `y_pred` column is the source paper's own
*modeled* SSC estimate, not a raw measurement. See docs/open_decisions.md,
2026-09-14 entries, for the full reasoning. Revisit once SWORD is in hand.

Auth: reads a GCP service-account JSON key (never checked into this repo —
see .gitignore's `/*.json`). The key's own `client_email` field is used as
the Earth Engine service-account identity, so only one path needs passing:

    python ml/data/fetch_river_silt_imagery.py \
        --key-file ~/secrets/depthwizard-ee-key.json --n-samples 200

Pulls a small Sentinel-2 true-color crop (visualize()'d to uint8 RGB, same
convention as DFC2019's RGB patches) for each sampled row, within a date
window of its SSC reading, picking the least-cloudy scene in that window.
Rows with no scene found in-window are skipped and reported, not silently
dropped.
"""

import argparse
import csv
import json
import os
import random
import re
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta

SSC_CSV = "ml/data/river_silt_raw/SSC_in_situ.csv"
OUT_DIR = "ml/data/river_silt_raw/imagery"
MANIFEST_PATH = "ml/data/river_silt_raw/imagery_manifest.csv"
RIVER_WATER_TYPES = {"River", "River/Stream"}
SENTINEL2_LAUNCH = datetime(2015, 6, 23)

DAY_WINDOW = 8          # +/- days around the SSC reading date to search for a scene
BUFFER_METERS = 1280    # half-width of the square crop around the point
PATCH_PX = 256          # output image size, matches this project's existing patch convention
MAX_CLOUD_PCT = 40      # skip scenes cloudier than this even if they're the only match
VIS_MAX_REFLECTANCE = 3000  # Sentinel-2 SR stretch ceiling for an 8-bit true-color render


def load_river_rows(csv_path, water_types=RIVER_WATER_TYPES):
    """water_types defaults to rivers — pass {"Reservoir"} etc. to pull a
    different WaterType from the same SSC_in_situ.csv shape (real gap found
    2026-09-16: this was hardcoded to rivers only, would have silently
    zeroed out a reservoir-filtered input CSV)."""
    rows = []
    with open(csv_path, newline="") as f:
        for row in csv.DictReader(f):
            if row["WaterType"] not in water_types:
                continue
            try:
                lat, lon = float(row["Lat"]), float(row["Lon"])
                date = datetime.strptime(row["Date"], "%Y-%m-%d")
            except (ValueError, KeyError):
                continue  # malformed row — skip, don't crash a 467k-row scan on one bad line
            if date < SENTINEL2_LAUNCH:
                continue  # unmatchable by construction — 58% of real rows predate Sentinel-2 (measured 2026-09-14)
            rows.append({"site_id": row["SiteID"], "lat": lat, "lon": lon,
                         "date": date, "ssc_value": row["Value"]})
    return rows


def sample_rows(rows, n_samples, seed):
    random.Random(seed).shuffle(rows)
    return rows[:n_samples]


def fetch_scene(lat, lon, date, day_window=DAY_WINDOW, buffer_m=BUFFER_METERS,
                 patch_px=PATCH_PX, max_cloud_pct=MAX_CLOUD_PCT):
    """Find the least-cloudy Sentinel-2 scene near (lat, lon) within
    +/- day_window of `date`, return its download URL and metadata, or None
    if nothing usable was found — never fabricates a match."""
    import ee  # lazy: keeps load_river_rows()/sample_rows() testable without earthengine-api installed

    point = ee.Geometry.Point([lon, lat])
    region = point.buffer(buffer_m).bounds()
    start = (date - timedelta(days=day_window)).strftime("%Y-%m-%d")
    end = (date + timedelta(days=day_window)).strftime("%Y-%m-%d")

    collection = (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterBounds(region)
        .filterDate(start, end)
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", max_cloud_pct))
        .sort("CLOUDY_PIXEL_PERCENTAGE")
    )
    image = collection.first()
    info = image.getInfo()  # None if the collection is empty — real network round-trip
    if info is None:
        return None

    vis = image.select(["B4", "B3", "B2"]).visualize(min=0, max=VIS_MAX_REFLECTANCE)
    url = vis.getDownloadURL({
        "region": region,
        "dimensions": f"{patch_px}x{patch_px}",
        "format": "GEO_TIFF",
    })
    props = info.get("properties", {})
    return {
        "url": url,
        "scene_id": info.get("id"),
        "scene_date": props.get("PRODUCT_ID", "")[7:15] or None,
        "cloud_pct": props.get("CLOUDY_PIXEL_PERCENTAGE"),
    }


def _process_one_row(row, out_dir):
    """Runs in a worker thread — fetch_scene() + urlretrieve() only, no
    shared-file writes (the manifest write stays single-threaded in main(),
    the only thing that actually needs serializing). Real measured bottleneck
    (2026-09-16): the sequential version spent ~5s/row almost entirely on
    Earth Engine API latency, not local disk I/O — parallelizing the network
    calls is the actual fix, not changing where the file lands (S3 vs local
    would add a hop on top of the same EE latency, not remove it)."""
    try:
        scene = fetch_scene(row["lat"], row["lon"], row["date"])
        if scene is None:
            return row, None, None, None

        safe_id = re.sub(r"[^A-Za-z0-9._-]", "_", row["site_id"])  # real SiteIDs include URLs (slashes/colons)
        image_path = os.path.join(out_dir, f"{safe_id}.tif")
        urllib.request.urlretrieve(scene["url"], image_path)
        return row, scene, image_path, None
    except Exception as exc:  # a real large batch shouldn't die on one bad row (bad URL, EE hiccup, etc.)
        return row, None, None, exc


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--key-file", required=True, help="GCP service-account JSON key path")
    parser.add_argument("--n-samples", type=int, default=200)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--csv", default=SSC_CSV)
    parser.add_argument("--out-dir", default=OUT_DIR)
    parser.add_argument("--water-types", default="River,River/Stream",
                         help="Comma-separated WaterType values to include (default: River,River/Stream)")
    parser.add_argument("--concurrency", type=int, default=8,
                         help="Parallel Earth Engine requests (default 8) — the real bottleneck is sequential "
                              "network latency per row, not local disk I/O, so this is the actual speed lever.")
    args = parser.parse_args()

    import socket
    socket.setdefaulttimeout(60)  # same fix as fetch_river_silt_multispectral.py — an unbounded network
    # call can hang the whole batch indefinitely with zero progress; a bad row must time out, not hang.

    import ee  # lazy, see fetch_scene()

    with open(args.key_file) as f:
        service_account = json.load(f)["client_email"]
    ee.Initialize(ee.ServiceAccountCredentials(service_account, args.key_file))

    os.makedirs(args.out_dir, exist_ok=True)

    # Resumable/additive, matching this project's existing "cached output IS
    # the checkpoint" convention (ml/features/extract_features.py) — a
    # re-run with a bigger --n-samples grows the manifest instead of
    # re-downloading and overwriting everything already pulled.
    existing_rows = []
    existing_ids = set()
    if os.path.exists(MANIFEST_PATH):
        with open(MANIFEST_PATH, newline="") as f:
            existing_rows = list(csv.DictReader(f))
        existing_ids = {row["site_id"] for row in existing_rows}
        print(f"{len(existing_rows)} rows already pulled in {MANIFEST_PATH} — will not be re-fetched")

    water_types = {t.strip() for t in args.water_types.split(",")}
    river_rows = [r for r in load_river_rows(args.csv, water_types=water_types) if r["site_id"] not in existing_ids]
    print(f"{len(river_rows)} real, not-yet-pulled {'/'.join(sorted(water_types))} rows in {args.csv}")
    sampled = sample_rows(river_rows, args.n_samples, args.seed)

    fieldnames = ["site_id", "lat", "lon", "date", "ssc_value",
                  "image_path", "scene_id", "scene_date", "cloud_pct", "url"]
    manifest_is_new = not existing_rows
    # Append per successful row, not once at the end — a killed/crashed run
    # (real incident: OOM-killed mid-batch, 2026-09-14) must not orphan
    # already-downloaded images outside the manifest, which would make the
    # "already pulled" resume check above blind to them on the next run.
    manifest_file = open(MANIFEST_PATH, "a" if existing_rows else "w", newline="")
    writer = csv.DictWriter(manifest_file, fieldnames=fieldnames)
    if manifest_is_new:
        writer.writeheader()

    pulled, skipped = 0, 0
    try:
        with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
            futures = {executor.submit(_process_one_row, row, args.out_dir): i for i, row in enumerate(sampled)}
            for future in as_completed(futures):
                i = futures[future]
                row, scene, image_path, exc = future.result()

                if exc is not None:
                    print(f"  [{i}] {row['site_id']}: error, skipping — {exc}")
                    skipped += 1
                    continue
                if scene is None:
                    skipped += 1
                    continue

                # Manifest write stays single-threaded here in the main
                # thread (as_completed() yields one at a time) — no lock
                # needed, this is the only writer.
                writer.writerow({**row, "date": row["date"].strftime("%Y-%m-%d"),
                                  "image_path": image_path, **scene})
                manifest_file.flush()  # survive a kill mid-batch, not just a clean exit
                pulled += 1
                print(f"  [{i}] {row['site_id']}: matched scene {scene['scene_id']} "
                      f"(cloud {scene['cloud_pct']:.1f}%) -> {image_path}")
    finally:
        manifest_file.close()

    print(f"\nDone: {pulled} new images pulled ({len(existing_rows) + pulled} total), {skipped} rows skipped "
          f"(no cloud-free scene in +/-{DAY_WINDOW}d window). Manifest: {MANIFEST_PATH}")


if __name__ == "__main__":
    sys.exit(main())
