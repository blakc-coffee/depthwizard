"""Per-patch geographic bounds recovery — Phase 4 Chunk 2.

SRTM fusion needs a patch's real-world bounding box to fetch elevation for.
No patch file currently carries one: DFC2019 tiles genuinely have no usable
CRS at all (ml/data/FORMAT_NOTES.md's own format inspection found this —
DFC2019 patches can never be georeferenced, full stop). Supplementary
(Copernicus/USGS) patches ARE georeferenced, but ml/data/
ingest_supplementary.py never wrote a transform onto the individual patch
files (only a `crs` string in the manifest, for bookkeeping) — this
recomputes the same bounds analytically from the source DEM's own transform
plus the patch's (y_idx, x_idx) offset, encoded in patch_id, rather than
re-running ingestion just to persist something recoverable for free.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import rasterio
from rasterio.warp import transform_bounds
from rasterio.windows import Window, bounds as window_bounds

_ML_DIR = Path(__file__).resolve().parent.parent
_REPO_ROOT = _ML_DIR.parent
if str(_ML_DIR) not in sys.path:
    sys.path.insert(0, str(_ML_DIR))

from data.ingest_supplementary import REGIONS  # noqa: E402
from data.preprocess import DEFAULT_PATCH_SIZE  # noqa: E402
from calibration.srtm_fetch import GeoBounds  # noqa: E402

_REGIONS_BY_LABEL = {r["label"]: r for r in REGIONS}
_PATCH_ID_RE = re.compile(r"_patch_(\d+)_(\d+)$")
GEOREFERENCEABLE_SOURCES = {"copernicus_dem", "usgs_3dep"}


def get_patch_bounds(entry: dict, patch_size: int = DEFAULT_PATCH_SIZE) -> GeoBounds | None:
    """Recover a manifest patch's real-world WGS84 bounding box, if it has
    one. Returns None for DFC2019 patches (no CRS, ever) and for anything
    whose region/patch_id doesn't resolve — that's the correct signal for
    calibrate.py to skip SRTM entirely rather than guess.
    """
    if entry.get("source") not in GEOREFERENCEABLE_SOURCES:
        return None

    region = _REGIONS_BY_LABEL.get(entry.get("source_tile"))
    if region is None:
        return None

    match = _PATCH_ID_RE.search(entry.get("patch_id", ""))
    if not match:
        return None
    y_idx, x_idx = int(match.group(1)), int(match.group(2))

    dem_path = _REPO_ROOT / region["dem"]  # REGIONS' paths are repo-root-relative, not cwd-relative
    with rasterio.open(dem_path) as dem_src:
        window = Window(x_idx * patch_size, y_idx * patch_size, patch_size, patch_size)
        left, bottom, right, top = window_bounds(window, dem_src.transform)
        dem_crs = dem_src.crs

    west, south, east, north = transform_bounds(dem_crs, "EPSG:4326", left, bottom, right, top)
    return GeoBounds(south=south, west=west, north=north, east=east)
