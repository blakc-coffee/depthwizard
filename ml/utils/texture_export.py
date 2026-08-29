"""Texture export — image/GeoTIFF in, browser-viewable PNG out.

Produces `texture_path` in `PipelineResult` (docs/depthwizard.md Section 9.5/9.6),
used by the frontend's Three.js viewer to texture-map the reconstructed mesh.
Called from ml/pipeline.py for every input branch, not just GeoTIFF — a plain
PNG/JPG input is close to a pass-through, a GeoTIFF is not (a raw GeoTIFF is
not directly displayable in a browser).

GeoTIFF band selection: true RGB is used when available. Many optical remote-
sensing sensors (e.g. Resourcesat-2 LISS-IV) don't capture a blue band at all,
so "true RGB" isn't always possible — for those, GDAL still tags 3-band rasters
with red/green/blue color interpretation positionally, it does not know the
sensor lacks blue. There is no way to detect this from pixel data alone without
sensor metadata. The heuristic used here: processed, web-ready RGB composites
are conventionally delivered as uint8; raw sensor products (multispectral
digital numbers straight off the sensor) are conventionally uint16 or higher
bit depth. A uint16+ 3-band GeoTIFF is therefore treated as raw multispectral
and rendered as a false-color composite (R=NIR, G=Red, B=Green — the standard
convention for Green/Red/NIR sensors), matching the exact failure mode hit
during Phase 1 sample testing on Resourcesat/Bhuvan/Cartosat imagery, where
this had to be done by hand. This is a heuristic, not a guarantee — a future
phase with access to per-product sensor metadata (as in the BAND_META.txt
sidecar seen during Phase 1) could make this exact instead of inferred.
"""

from pathlib import Path

import numpy as np
import rasterio
from PIL import Image

GEOTIFF_EXTENSIONS = {".tif", ".tiff"}
NODATA_SENTINEL = -32000  # covers common fill values like -32768 when src.nodata is unset


def export_texture(input_path: str | Path, output_dir: str | Path) -> Path:
    """Produce a normal, browser-viewable PNG from any accepted input (PNG/JPG/GeoTIFF).

    Returns the path to the exported PNG — this is `texture_path` in PipelineResult.
    """
    input_path = Path(input_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{input_path.stem}_texture.png"

    if input_path.suffix.lower() in GEOTIFF_EXTENSIONS:
        image = _render_geotiff(input_path)
    else:
        image = Image.open(input_path).convert("RGB")

    image.save(output_path)
    return output_path


def _render_geotiff(input_path: Path) -> Image.Image:
    """Read a GeoTIFF's viewable bands, contrast-stretch, return an RGB PIL image."""
    with rasterio.open(input_path) as src:
        band_count = src.count
        nodata = src.nodata

        if band_count == 1:
            band = src.read(1)
            stretched = _stretch(band, nodata)
            return Image.fromarray(np.dstack([stretched] * 3), "RGB")

        if band_count >= 4:
            # Convention: extra bands beyond the first three are additional
            # channels (e.g. NIR) layered on top of a true-color base.
            r, g, b = src.read(1), src.read(2), src.read(3)
        elif band_count == 3:
            r_raw, g_raw, b_raw = src.read(1), src.read(2), src.read(3)
            if r_raw.dtype == np.uint8:
                # Processed, web-ready composite — trust it as true RGB.
                r, g, b = r_raw, g_raw, b_raw
            else:
                # Raw sensor digital numbers, band order Green/Red/NIR (e.g.
                # LISS-IV) — no blue band exists. False-color: R=NIR, G=Red, B=Green.
                green, red, nir = r_raw, g_raw, b_raw
                r, g, b = nir, red, green
        else:
            raise ValueError(f"Unsupported band count for texture export: {band_count}")

    rgb = np.dstack([_stretch(r, nodata), _stretch(g, nodata), _stretch(b, nodata)])
    return Image.fromarray(rgb, "RGB")


def _stretch(band: np.ndarray, nodata: float | None, lo_pct: float = 2, hi_pct: float = 98) -> np.ndarray:
    """Percentile contrast-stretch a band to uint8, excluding NoData pixels."""
    band = band.astype(np.float32)
    if nodata is not None:
        valid = band[band != nodata]
    elif band.min() < NODATA_SENTINEL:
        valid = band[band > NODATA_SENTINEL]
    else:
        valid = band

    if valid.size == 0:
        return np.zeros_like(band, dtype=np.uint8)

    lo, hi = np.percentile(valid, [lo_pct, hi_pct])
    stretched = np.clip((band - lo) / (hi - lo + 1e-6), 0, 1)
    return (stretched * 255).astype(np.uint8)
