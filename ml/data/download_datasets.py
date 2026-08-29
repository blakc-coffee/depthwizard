#!/usr/bin/env python3
"""
Dataset acquisition for DepthWizard Phase 2 (DFC2019/US3D).

Registration is manual (IEEE DataPort account, free) — see acquisition_notes()
below or docs/depthwizard.md Section 7.0. What CAN be scripted is everything
after that: unpacking the downloaded archives into the layout preprocess.py
expects, and inspecting one tile pair's actual format (Chunk 1's acceptance
check) rather than assuming it.
"""

import argparse
import os
import zipfile

import numpy as np
import rasterio

RAW_DIR = "data/raw"
ARCHIVE_DIR = os.path.join(RAW_DIR, "archives", "DFC2019_track1_trainval")
BHUVAN_DIR = os.path.join(RAW_DIR, "bhuvan_cartosat")
TRACK1_DIR = os.path.join(RAW_DIR, "dfc2019", "track1")


def acquisition_notes():
    """Print sourcing and registration details for DFC2019 (Track 1) / US3D."""
    notes = """
================================================================================
                       DEPTHWIZARD - DATASET ACQUISITION
================================================================================

1. DFC2019 / US3D Dataset Sourcing
----------------------------------
- **Host:** IEEE DataPort — https://ieee-dataport.org/open-access/data-fusion-contest-2019-dfc2019
- **Registration:** free IEEE account required, no paid membership needed.
- **Manual step (cannot be scripted — no static download URLs exist without
  an authenticated session):**
  Download `Train-Track1-RGB.zip` and `Train-Track1-Truth.zip` and place them in:
    {archive_dir}/
  (No-login alternative: the pubgeo/dfc2019 GitHub repo hosts .torrent files
  for the same archives, if you'd rather not create an IEEE account.)

2. Bhuvan / Cartosat Sourcing (Chunk 4 — Indian-terrain validation)
--------------------------------------------------------------------
- **Host:** Bhuvan portal (bhuvan.nrsc.gov.in) — no API, manual download,
  free account required. Separate from the DFC2019/US3D pipeline; qualitative
  validation only (PRD Section 3.2), no ground truth needed.
- Source a small RGB sample by hand, then register it:
    add_bhuvan_sample("/path/to/downloaded.tif")
  which copies it into {bhuvan_dir}/ for preprocess.py's --bhuvan-dir.

3. What this script automates from here
-----------------------------------------
- `unpack_archives()` — extracts the DFC2019 zips into the layout preprocess.py
  expects: {track1_dir}/rgb/*_RGB.tif, {track1_dir}/truth/*_AGL.tif
- `inspect_format()` — opens one real RGB/height pair, prints its actual
  shape/CRS/units/nodata (not assumed), checks spatial alignment, and writes
  a findings note to ml/data/FORMAT_NOTES.md — Chunk 1's acceptance check.
- `add_bhuvan_sample(path)` — registers a manually-sourced Bhuvan/Cartosat
  image for Chunk 4's separate validation-only manifest section.

Run: python download_datasets.py --unpack --inspect
================================================================================
""".format(archive_dir=ARCHIVE_DIR, track1_dir=TRACK1_DIR, bhuvan_dir=BHUVAN_DIR)
    print(notes)


def add_bhuvan_sample(image_path, tile_name=None, out_dir=BHUVAN_DIR):
    """Register a manually-sourced Bhuvan/Cartosat RGB image for Phase 2 (Chunk 4).

    No API exists for Bhuvan/Cartosat (docs/depthwizard.md Section 7.0) — source
    the image by hand from the Bhuvan portal, then call this to place it where
    preprocess.py's --bhuvan-dir expects it. No paired ground truth is required
    (qualitative Indian-terrain validation, not training — PRD Section 3.2).
    """
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"{image_path} not found.")

    os.makedirs(out_dir, exist_ok=True)
    tile_name = tile_name or os.path.splitext(os.path.basename(image_path))[0]
    ext = os.path.splitext(image_path)[1]
    dest = os.path.join(out_dir, f"{tile_name}{ext}")

    with open(image_path, "rb") as src, open(dest, "wb") as dst:
        dst.write(src.read())

    print(f"Registered Bhuvan/Cartosat sample: {dest}")
    return dest


def unpack_archives(archive_dir=ARCHIVE_DIR, out_dir=TRACK1_DIR):
    """Extract the manually-downloaded DFC2019 zips into preprocess.py's expected layout."""
    rgb_zip = os.path.join(archive_dir, "Train-Track1-RGB.zip")
    truth_zip = os.path.join(archive_dir, "Train-Track1-Truth.zip")

    for path in (rgb_zip, truth_zip):
        if not os.path.exists(path):
            raise FileNotFoundError(
                f"{path} not found. Download it manually per acquisition_notes() first."
            )

    rgb_out = os.path.join(out_dir, "rgb")
    truth_out = os.path.join(out_dir, "truth")
    os.makedirs(rgb_out, exist_ok=True)
    os.makedirs(truth_out, exist_ok=True)

    for zip_path, out_subdir, suffix in [(rgb_zip, rgb_out, "_RGB.tif"), (truth_zip, truth_out, "_AGL.tif")]:
        with zipfile.ZipFile(zip_path) as zf:
            tif_members = [m for m in zf.namelist() if m.lower().endswith(suffix.lower())]
            print(f"{os.path.basename(zip_path)}: {len(tif_members)} tiles matching *{suffix}")
            for member in tif_members:
                dest = os.path.join(out_subdir, os.path.basename(member))
                if os.path.exists(dest):
                    continue
                with zf.open(member) as src, open(dest, "wb") as dst:
                    dst.write(src.read())

    print(f"Unpacked to {out_dir}/rgb and {out_dir}/truth")
    return out_dir


def inspect_format(track1_dir=TRACK1_DIR, notes_path="ml/data/FORMAT_NOTES.md"):
    """Open one real RGB/height tile pair, log its actual format, check alignment.

    Chunk 1's acceptance check: load one pair, print shape/CRS/units, confirm
    the height map isn't offset or upside-down relative to the RGB image.
    """
    rgb_files = sorted(
        os.path.join(track1_dir, "rgb", f) for f in os.listdir(os.path.join(track1_dir, "rgb"))
    ) if os.path.isdir(os.path.join(track1_dir, "rgb")) else []

    if not rgb_files:
        raise FileNotFoundError(f"No tiles found in {track1_dir}/rgb — run unpack_archives() first.")

    # The RGB and Truth zips can extract independently (e.g. a truncated
    # download of one but not the other) — don't assume the first RGB tile
    # has a matching truth tile, find one that actually does.
    for candidate in rgb_files:
        candidate_tile = os.path.basename(candidate).replace("_RGB.tif", "")
        candidate_truth = os.path.join(track1_dir, "truth", f"{candidate_tile}_AGL.tif")
        if os.path.exists(candidate_truth):
            rgb_path, tile_name, truth_path = candidate, candidate_tile, candidate_truth
            break
    else:
        raise FileNotFoundError(
            f"No RGB tile in {track1_dir}/rgb has a matching truth tile in {track1_dir}/truth."
        )

    with rasterio.open(rgb_path) as rgb_src, rasterio.open(truth_path) as truth_src:
        same_dims = rgb_src.width == truth_src.width and rgb_src.height == truth_src.height
        same_crs = rgb_src.crs == truth_src.crs
        same_bounds = rgb_src.bounds == truth_src.bounds

        height_data = truth_src.read(1)
        nodata = truth_src.nodata
        valid = height_data[height_data != nodata] if nodata is not None else height_data

        findings = f"""# DFC2019 Format Notes (Chunk 1)

Inspected tile: `{tile_name}`

| Property | RGB | Truth (AGL height) |
|---|---|---|
| Shape | {rgb_src.width}x{rgb_src.height}, {rgb_src.count} band(s) | {truth_src.width}x{truth_src.height}, {truth_src.count} band(s) |
| Dtype | {rgb_src.dtypes[0]} | {truth_src.dtypes[0]} |
| CRS | {rgb_src.crs} | {truth_src.crs} |
| Bounds | {rgb_src.bounds} | {truth_src.bounds} |
| NoData | {rgb_src.nodata} | {truth_src.nodata} |

**Alignment check:** dimensions match: {same_dims} | CRS match: {same_crs} | bounds match: {same_bounds}
**Height stats (excluding NoData):** min={valid.min():.2f}m max={valid.max():.2f}m mean={valid.mean():.2f}m

**Patch size:** {TRACK1_DIR} tiles are patchified at 256x256 (see ml/data/preprocess.py DEFAULT_PATCH_SIZE).
Not a guess — Phase 1's frozen interface (ml/depth/PHASE1_NOTES.md) accepts "any size" input,
so 256 is a free choice, not a constraint; picked as a conventional ML patch size that divides
this tile's {rgb_src.width}px width evenly ({rgb_src.width // 256} whole patches, {rgb_src.width % 256}px remainder handled by the pad edge policy).
"""
        os.makedirs(os.path.dirname(notes_path), exist_ok=True)
        with open(notes_path, "w") as f:
            f.write(findings)

        print(findings)
        assert same_dims and same_crs, "RGB/height tile misaligned — do not proceed to patchify"
        print(f"Format notes written to {notes_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="DepthWizard dataset acquisition")
    parser.add_argument("--unpack", action="store_true", help="Extract downloaded zips into raw data layout")
    parser.add_argument("--inspect", action="store_true", help="Inspect one real tile pair's format")
    parser.add_argument("--add-bhuvan", type=str, default=None,
                        help="Path to a manually-downloaded Bhuvan/Cartosat image to register")
    args = parser.parse_args()

    if not (args.unpack or args.inspect or args.add_bhuvan):
        acquisition_notes()
    if args.unpack:
        unpack_archives()
    if args.inspect:
        inspect_format()
    if args.add_bhuvan:
        add_bhuvan_sample(args.add_bhuvan)
