#!/usr/bin/env python3
"""Phase 2 addition — ingest supplementary hilly/sparse-terrain sources
(Copernicus GLO-30 DEM + Sentinel-2 RGB; USGS 3DEP DEM + matching Sentinel-2
RGB) into the same patch manifest DFC2019 already populates.

Why this needs its own ingestion path instead of reusing patchify_tile():
unlike DFC2019's pre-aligned RGB/AGL tile pairs (same CRS, same dims), these
sources arrive at different resolutions and in a different CRS per region —
each RGB tile is reprojected onto its DEM's own grid before patchifying,
resampled down to the coarser grid, never upsampling a DEM to fabricate
detail it doesn't have.

Height semantics differ too: these DEMs are absolute terrain elevation above
sea level (metres, roughly 0-5000+ depending on region), not the
above-ground-level object height DFC2019's AGL patches encode. Blending that
scale directly into the same manifest would give Phase 4's regressor an
inconsistent target across sources — so every patch here is normalized to
height *relative to its own local minimum* before saving. Absolute elevation
is discarded; only the within-patch terrain-relief signal survives, which is
consistent with DFC2019's AGL scale (both are "height above some local
baseline", not "height above sea level").

Terrain labels are assigned from each region's known geography, not from
preprocess.py::classify_terrain()'s std/roughness heuristic. That heuristic's
thresholds (std>=3.5 -> urban) were calibrated for DFC2019's building-height
scale (0-50m); real topographic relief in a 256px patch of Himalaya/Tuscany/
Sierra Nevada terrain routinely exceeds that by an order of magnitude, so
every region here initially came back mislabeled "urban" when the heuristic
was applied out of its calibrated domain (found and reverted 2026-08-30 —
see docs/open_decisions.md). We picked these specific regions *because* they
are hilly or sparse; trusting that over a heuristic already documented as
unreliable is the more honest choice, not a shortcut.

Run from the repo root:
    python ml/data/ingest_supplementary.py
"""

import json
import os
import shutil
import sys
from pathlib import Path

import numpy as np
import rasterio
from rasterio.warp import Resampling, reproject

# Flat sibling import — same convention as preprocess.py/download_datasets.py,
# resolved relative to ml/data/ being on sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from preprocess import DEFAULT_PATCH_SIZE, classify_terrain, split_and_stratify_dataset  # noqa: E402

NODATA_SENTINEL = -9999.0
MIN_VALID_FRACTION = 0.5  # skip patches mostly outside the RGB tile's real coverage
MANIFEST_PATH = "data/processed/v1/manifest.json"
OUTPUT_DIR = "data/processed/v1"

REGIONS = [
    {
        "label": "nepal", "source": "copernicus_dem", "terrain_type": "hilly",
        "dem": "supplementary-data/copernicus-dem/Copernicus_DSM_COG_10_N28_00_E084_00_DEM.tif",
        "rgb": "supplementary-data/sentinel-2/sentinel2_nepal_TCI.tif",
    },
    {
        "label": "tuscany", "source": "copernicus_dem", "terrain_type": "hilly",
        "dem": "supplementary-data/copernicus-dem/Copernicus_DSM_COG_10_N43_00_E011_00_DEM.tif",
        "rgb": "supplementary-data/sentinel-2/sentinel2_tuscany_TCI.tif",
    },
    {
        "label": "appalachians", "source": "usgs_3dep", "terrain_type": "hilly",
        "dem": "supplementary-data/3dep/USGS_13_n36w083.tif",
        "rgb": "supplementary-data/sentinel-2/sentinel2_appalachian_n36w083_TCI.tif",
    },
    {
        "label": "sierra_nevada", "source": "usgs_3dep", "terrain_type": "hilly",
        "dem": "supplementary-data/3dep/USGS_13_n39w121.tif",
        "rgb": "supplementary-data/sentinel-2/sentinel2_sierra_n39w121_TCI.tif",
    },
    {
        "label": "west_virginia", "source": "usgs_3dep", "terrain_type": "hilly",
        "dem": "supplementary-data/3dep/USGS_13_n38w080.tif",
        "rgb": "supplementary-data/sentinel-2/sentinel2_westvirginia_n38w080_TCI.tif",
    },
    {
        "label": "scotland", "source": "copernicus_dem", "terrain_type": "hilly",
        "dem": "supplementary-data/copernicus-dem/Copernicus_DSM_COG_10_N56_00_W005_00_DEM.tif",
        "rgb": "supplementary-data/sentinel-2/sentinel2_scotland_n56w005_TCI.tif",
    },
    # kansas (Copernicus N39_00_W099_00) intentionally removed 2026-08-30 —
    # user pruned the sparse/rural supplementary set entirely, hilly-only
    # from here on (see docs/open_decisions.md).
    #
    # Excluded — no geographic overlap between the DEM tile and its only
    # candidate RGB match (flagged, not silently dropped):
    #   australia (Copernicus S25_00_E132_00): DEM covers -24.0..-25.0N,
    #     its candidate RGB covers -25.3..-26.3N.
    #   USGS_13_n41w106.tif (Wyoming, 40.0-41.0N): its candidate RGB covers
    #     41.5-42.5N. Left out per explicit instruction even after a
    #     Wyoming-labeled RGB file showed up — still doesn't overlap.
    # Both need a correctly-matched RGB tile re-sourced before they can be
    # added the same way as the regions above.
]


def reproject_rgb_to_grid(rgb_path, dst_crs, dst_transform, dst_shape):
    """Reproject/resample a 3-band RGB tile onto another raster's grid.

    Average resampling (never upsampling a DEM to fabricate resolution it
    doesn't have — the DEM's own grid is always the reprojection target).
    """
    height, width = dst_shape
    dst = np.zeros((3, height, width), dtype=np.uint8)
    with rasterio.open(rgb_path) as src:
        for band_idx in range(3):
            reproject(
                source=rasterio.band(src, band_idx + 1),
                destination=dst[band_idx],
                src_transform=src.transform,
                src_crs=src.crs,
                dst_transform=dst_transform,
                dst_crs=dst_crs,
                dst_nodata=0,
                resampling=Resampling.average,
            )
    return dst


def _patch_windows(height, width, patch_size):
    y_steps = int(np.ceil(height / patch_size))
    x_steps = int(np.ceil(width / patch_size))
    for y in range(y_steps):
        for x in range(x_steps):
            row_off, col_off = y * patch_size, x * patch_size
            yield y, x, row_off, col_off, min(patch_size, height - row_off), min(patch_size, width - col_off)


def patchify_region(dem_array, rgb_array, region_label, temp_dir, terrain_type,
                     patch_size=DEFAULT_PATCH_SIZE, min_valid_fraction=MIN_VALID_FRACTION, crs="relative"):
    """Slice an already-aligned (DEM, RGB) pair into patches, normalizing
    each patch's height to relative-to-local-minimum. `terrain_type` is fixed
    per region (known geography), not derived from classify_terrain()'s
    height heuristic — see module docstring for why."""
    os.makedirs(os.path.join(temp_dir, "rgb"), exist_ok=True)
    os.makedirs(os.path.join(temp_dir, "truth"), exist_ok=True)

    height, width = dem_array.shape
    dem_valid_mask = np.isfinite(dem_array)  # caller has already NaN'd DEM nodata
    patches_meta = []

    for y, x, row_off, col_off, h, w in _patch_windows(height, width, patch_size):
        dem_patch = dem_array[row_off : row_off + h, col_off : col_off + w]
        rgb_patch = rgb_array[:, row_off : row_off + h, col_off : col_off + w]

        valid = dem_valid_mask[row_off : row_off + h, col_off : col_off + w] & (rgb_patch.sum(axis=0) > 0)
        if valid.mean() < min_valid_fraction:
            continue  # mostly outside the RGB tile's real coverage — not a usable training pair

        padded = h < patch_size or w < patch_size

        relative = np.full((patch_size, patch_size), NODATA_SENTINEL, dtype=np.float32)
        local_min = dem_patch[valid].min()
        relative[:h, :w] = np.where(valid, dem_patch - local_min, NODATA_SENTINEL)

        rgb_padded = np.zeros((3, patch_size, patch_size), dtype=np.uint8)
        rgb_padded[:, :h, :w] = rgb_patch

        # std/roughness still computed for the manifest's own record-keeping
        # (matches DFC2019 patches' fields) — just not used to pick the label.
        _, std, roughness = classify_terrain(relative, nodata=NODATA_SENTINEL)

        patch_id = f"{region_label}_patch_{y}_{x}"
        temp_rgb_path = os.path.join(temp_dir, "rgb", f"{patch_id}_RGB.tif")
        temp_truth_path = os.path.join(temp_dir, "truth", f"{patch_id}_AGL.tif")

        with rasterio.open(temp_rgb_path, "w", driver="GTiff", height=patch_size, width=patch_size,
                            count=3, dtype="uint8") as dst:
            dst.write(rgb_padded)
        with rasterio.open(temp_truth_path, "w", driver="GTiff", height=patch_size, width=patch_size,
                            count=1, dtype="float32", nodata=NODATA_SENTINEL) as dst:
            dst.write(relative[np.newaxis, ...])

        patches_meta.append({
            "patch_id": patch_id,
            "source_tile": region_label,
            "temp_rgb": temp_rgb_path,
            "temp_truth": temp_truth_path,
            "terrain_type": terrain_type,
            "std": std,
            "roughness": roughness,
            "padded": padded,
            "crs": crs,
        })

    return patches_meta


def ingest_region(region, temp_dir, patch_size=DEFAULT_PATCH_SIZE):
    with rasterio.open(region["dem"]) as dem_src:
        dem_array = dem_src.read(1).astype(np.float32)
        if dem_src.nodata is not None:
            dem_array[dem_array == dem_src.nodata] = np.nan
        dem_crs, dem_transform, dem_shape = dem_src.crs, dem_src.transform, (dem_src.height, dem_src.width)

    rgb_array = reproject_rgb_to_grid(region["rgb"], dem_crs, dem_transform, dem_shape)

    return patchify_region(dem_array, rgb_array, region["label"], temp_dir, region["terrain_type"],
                            patch_size=patch_size, crs=str(dem_crs))


def main():
    with open(MANIFEST_PATH) as f:
        manifest = json.load(f)

    temp_dir = os.path.join(OUTPUT_DIR, "temp_supplementary")
    by_source = {}
    report_rows = []

    for region in REGIONS:
        print(f"Ingesting {region['label']} ({region['source']})...")
        patches = ingest_region(region, temp_dir)
        by_source.setdefault(region["source"], []).extend(patches)
        report_rows.append((region["label"], region["source"], len(patches)))
        print(f"  {len(patches)} patches kept ({MIN_VALID_FRACTION:.0%}+ valid coverage required)")

    new_entries = []
    for source, patches in by_source.items():
        new_entries.extend(split_and_stratify_dataset(patches, OUTPUT_DIR, seed=42, source=source))

    manifest.extend(new_entries)
    with open(MANIFEST_PATH, "w") as f:
        json.dump(manifest, f, indent=2)

    if os.path.exists(temp_dir):
        shutil.rmtree(temp_dir)

    print(f"\nAdded {len(new_entries)} new patches. Manifest now has {len(manifest)} total entries.")
    return report_rows, manifest


if __name__ == "__main__":
    main()
