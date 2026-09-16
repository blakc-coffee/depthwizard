#!/usr/bin/env python3
"""River-silt use case — multispectral re-pull.

Chunk 2's RGB-only baseline flat-lined near R²=0 regardless of sample size
(315 -> 830 -> 1532 rows, MLP and XGBoost both — docs/open_decisions.md,
2026-09-14). Literature review found the likely root cause: true-color RGB
discards NIR/red-edge/SWIR bands turbidity signal actually depends on
(green/red reflectance saturates in highly turbid water). This script pulls
those bands for the same scenes already matched by fetch_river_silt_imagery.py
— reusing each row's own `scene_id` from imagery_manifest.csv, not
re-searching, so every image here is guaranteed to be the exact same scene
the RGB crop came from (same date, same cloud cover, no drift).

Raw scaled reflectance (Sentinel-2 SR's native int16 x10000 scale), not
visualize()'d to uint8 — literature band ratios need real reflectance
values, and a true-color stretch would distort them the same way it likely
hurt the RGB-only baseline.

One file per site_id under OUT_DIR is its own resume checkpoint (matches
this project's existing "cached output IS the checkpoint" convention,
ml/features/extract_features.py) — no separate manifest needed, since
imagery_manifest.csv already has every row's metadata; this script only
adds a second image per already-known site_id.

Run from the repo root:
    python ml/data/fetch_river_silt_multispectral.py --key-file ~/secrets/depthwizard-ee-key.json
"""

import argparse
import csv
import json
import os
import re
import sys
import time
import urllib.request
from pathlib import Path

MANIFEST_PATH = "ml/data/river_silt_raw/imagery_manifest.csv"
OUT_DIR = "ml/data/river_silt_raw/imagery_multispectral"
BUFFER_METERS = 1280  # matches fetch_river_silt_imagery.py's crop size, so pixel grids line up
PATCH_PX = 256
# B2 blue, B3 green, B4 red, B5 red-edge, B8 NIR, B11 SWIR1, B12 SWIR2 — the
# literature set (docs/open_decisions.md's literature-review entry) minus
# B6/B7 (further red-edge bands the reviewed papers didn't single out).
BANDS = ["B2", "B3", "B4", "B5", "B8", "B11", "B12"]


def safe_id(site_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", site_id)


def fetch_multispectral_crop(scene_id: str, lat: float, lon: float,
                              buffer_m=BUFFER_METERS, patch_px=PATCH_PX):
    """Real scaled reflectance for BANDS, cropped to the same region the RGB
    pull used. Raises if the scene_id is no longer resolvable (rare — Earth
    Engine's catalog doesn't remove scenes, but a real network/auth error
    should propagate, not be swallowed)."""
    import ee

    point = ee.Geometry.Point([lon, lat])
    region = point.buffer(buffer_m).bounds()
    image = ee.Image(scene_id).select(BANDS)
    return image.getDownloadURL({
        "region": region,
        "dimensions": f"{patch_px}x{patch_px}",
        "format": "GEO_TIFF",
    })


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--key-file", required=True, help="GCP service-account JSON key path")
    parser.add_argument("--manifest", default=MANIFEST_PATH)
    parser.add_argument("--out-dir", default=OUT_DIR)
    args = parser.parse_args()

    import socket
    socket.setdefaulttimeout(60)  # real incident 2026-09-14: an unbounded network call hung the whole
    # batch indefinitely with zero CPU/progress — a bad row must time out and be skipped, not hang forever.

    import ee

    with open(args.key_file) as f:
        service_account = json.load(f)["client_email"]
    ee.Initialize(ee.ServiceAccountCredentials(service_account, args.key_file))

    os.makedirs(args.out_dir, exist_ok=True)
    with open(args.manifest, newline="") as f:
        rows = list(csv.DictReader(f))
    print(f"{len(rows)} rows in {args.manifest}")

    pulled, skipped, already_done = 0, 0, 0
    for i, row in enumerate(rows):
        out_path = Path(args.out_dir) / f"{safe_id(row['site_id'])}.tif"
        if out_path.exists():
            already_done += 1
            continue

        try:
            url = fetch_multispectral_crop(row["scene_id"], float(row["lat"]), float(row["lon"]))
            urllib.request.urlretrieve(url, out_path)
        except Exception as exc:  # a scene that fails shouldn't kill a 1500+-row batch
            print(f"  [{i}] {row['site_id']}: error, skipping — {exc}")
            skipped += 1
            continue

        pulled += 1
        if pulled % 25 == 0:
            print(f"  [{i}] {pulled} pulled so far ({row['site_id']} -> {out_path})")
        time.sleep(0.2)  # ponytail: fixed pacing, same as fetch_river_silt_imagery.py

    print(f"\nDone: {pulled} new multispectral crops pulled, {already_done} already on disk "
          f"(skipped as resumed), {skipped} failed. Output: {args.out_dir}")


if __name__ == "__main__":
    sys.exit(main())
