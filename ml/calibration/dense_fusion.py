"""Dense DSM fusion — SRTM-as-trend + relative-depth-as-detail.

Full design rationale: docs/dense_dsm_fusion.md. Short version: the scalar
calibration path (calibrate.py) already fuses SRTM + regressor + semantic
into one number (`fused_height`), but ml/pipeline.py's dense per-pixel output
only ever used that scalar to uniformly rescale relative depth's own shape —
discarding SRTM's real (if coarse, ~30m/pixel) spatial detail entirely. A
real visual-review finding this session (docs/open_decisions.md, 2026-08-31)
showed relative depth can hallucinate a smooth gradient on genuinely flat
ground; uniformly rescaling that fake shape by a correct scalar still
produces a visibly wrong dense heightmap even when the scalar is right.

This module fixes that: SRTM supplies the low-frequency trend (real,
measured), relative depth supplies only the high-frequency detail (its own
trend removed first, so it never fights or duplicates SRTM's real one).
Nearest-neighbor for SRTM resampling (a mask-like void-safe resize, matches
ml/calibration/semantic_priors.py::segment_image's own convention);
bilinear for the relative-depth low-pass filter (a real smooth signal, no
NoData concept, per compute_depth_features' docstring).

Never touches the scalar calibration path (calibrate_scene, fusion.py, the
regressor, texture-adaptive variance) — this only changes how the dense
output is built once that path has already decided absolute is warranted.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import rasterio
from PIL import Image
from rasterio.transform import from_bounds

from calibration.srtm_fetch import ElevationData, GeoBounds

CONFIDENCE_MEASURED = 255  # SRTM had real coverage for this pixel
CONFIDENCE_PREDICTED = 76  # ~0.3 * 255 -- model-predicted, SRTM had no coverage here


def resample_srtm_to_grid(elevation_data: ElevationData, width: int, height: int) -> tuple[np.ndarray, np.ndarray]:
    """SRTM's raw (Hs, Ws) elevation grid -> (height, width), matching the
    output image's resolution. Nearest-neighbor, deliberately: SRTM is
    already coarse (it supplies the trend, not detail), and nearest never
    blends a valid cell with an adjacent NoData one the way bilinear would.

    Returns (srtm_surface, srtm_valid) both at (height, width).
    """
    elevation = elevation_data.elevation.astype(np.float32)
    valid = elevation_data.valid_mask

    srtm_surface = np.array(
        Image.fromarray(elevation, mode="F").resize((width, height), Image.Resampling.NEAREST)
    )
    srtm_valid = np.array(
        Image.fromarray((valid.astype(np.uint8) * 255), mode="L").resize((width, height), Image.Resampling.NEAREST)
    ) > 0
    return srtm_surface, srtm_valid


def extract_relative_detail(heightmap_array: np.ndarray, native_shape: tuple[int, int]) -> np.ndarray:
    """heightmap_array's own high-frequency residual, after removing a trend
    matched to SRTM's native spatial resolution (native_shape = SRTM's raw
    (Hs, Ws) before any resampling). Downsample-then-upsample is a real
    low-pass filter at that exact frequency; bilinear both ways since this
    is a smooth dense array with no NoData concept (unlike SRTM's mask)."""
    height, width = heightmap_array.shape
    native_h, native_w = native_shape
    trend = np.array(
        Image.fromarray(heightmap_array.astype(np.float32))
        .resize((native_w, native_h), Image.Resampling.BILINEAR)
        .resize((width, height), Image.Resampling.BILINEAR)
    )
    return heightmap_array.astype(np.float32) - trend


def fuse_dense_dsm(
    heightmap_array: np.ndarray,
    elevation_data: ElevationData,
    scale_factor: float,
) -> tuple[np.ndarray, np.ndarray]:
    """The full per-pixel fusion: SRTM trend + relative-depth detail where
    SRTM has coverage, today's existing uniform-rescale formula elsewhere.

    Returns (absolute_height_map_meters, srtm_valid_at_output_resolution).
    """
    height, width = heightmap_array.shape
    srtm_surface, srtm_valid = resample_srtm_to_grid(elevation_data, width, height)

    srtm_min = float(srtm_surface[srtm_valid].min()) if srtm_valid.any() else 0.0
    srtm_trend_m = srtm_surface - srtm_min

    detail = extract_relative_detail(heightmap_array, elevation_data.elevation.shape)
    detail_m = (detail / 255.0) * scale_factor

    fallback_m = (heightmap_array.astype(np.float32) / 255.0) * scale_factor
    absolute_height_map = np.where(srtm_valid, srtm_trend_m + detail_m, fallback_m)

    return absolute_height_map.astype(np.float32), srtm_valid


def write_dsm_geotiff(path: str | Path, absolute_height_map: np.ndarray, geo_bounds: GeoBounds) -> None:
    """Real, georeferenced absolute elevation product — docs/depthwizard.md
    §9.8's `dsm_path` contract ("GeoTIFF, absolute results only")."""
    height, width = absolute_height_map.shape
    transform = from_bounds(geo_bounds.west, geo_bounds.south, geo_bounds.east, geo_bounds.north, width, height)
    with rasterio.open(
        path, "w", driver="GTiff", height=height, width=width, count=1,
        dtype="float32", crs="EPSG:4326", transform=transform,
    ) as dst:
        dst.write(absolute_height_map.astype(np.float32), 1)


def save_confidence_map(path: str | Path, srtm_valid: np.ndarray) -> None:
    """Per-pixel provenance: 255 where SRTM directly measured this pixel,
    76 (~0.3) where it's model-predicted infill. Format is this task's own
    choice -- docs/depthwizard.md §9.8 doesn't mandate one for this field."""
    confidence = np.where(srtm_valid, CONFIDENCE_MEASURED, CONFIDENCE_PREDICTED).astype(np.uint8)
    Image.fromarray(confidence, "L").save(path)


def demo():
    """Self-check with synthetic data -- no real SRTM/network needed."""
    height, width = 64, 64
    heightmap_array = np.zeros((height, width), dtype=np.float32)
    heightmap_array[20:40, 20:40] = 200.0  # a "building" the SRTM grid is too coarse to see

    elevation = np.array([[10.0, 12.0], [11.0, 13.0]], dtype=np.float32)  # a real, coarse 2x2 SRTM trend
    elevation_data = ElevationData(
        elevation=elevation,
        bounds=GeoBounds(south=0.0, west=0.0, north=0.01, east=0.01),
        resolution_deg=(0.005, 0.005),
    )

    absolute_height_map, srtm_valid = fuse_dense_dsm(heightmap_array, elevation_data, scale_factor=50.0)

    assert absolute_height_map.shape == (height, width)
    assert srtm_valid.all()  # synthetic elevation has no NoData
    # the "building" region should read higher than the flat background
    assert absolute_height_map[20:40, 20:40].mean() > absolute_height_map[:10, :10].mean()
    print(f"background mean: {absolute_height_map[:10, :10].mean():.2f}m")
    print(f"'building' region mean: {absolute_height_map[20:40, 20:40].mean():.2f}m")
    print("dense_fusion self-check passed")


if __name__ == "__main__":
    demo()
