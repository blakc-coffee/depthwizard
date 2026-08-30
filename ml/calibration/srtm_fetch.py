"""SRTM Elevation Retrieval & Caching — Phase 4 Calibration Module.

Provides elevation retrieval for arbitrary bounding boxes (WGS84 lat/lon) via
OpenTopography Global DEM API (with API Key) and public AWS Open Data Terrain /
OpenTopoData global SRTM sources with local disk caching and multi-cell tile mosaicing.

Frozen interface per Phase 4 specification.
"""

from __future__ import annotations

import hashlib
import io
import logging
import math
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import numpy as np
import rasterio
from rasterio.crs import CRS
from rasterio.io import MemoryFile
from rasterio.merge import merge
from rasterio.transform import from_bounds
from rasterio.warp import Resampling, reproject
import requests

logger = logging.getLogger(__name__)

OPENTOPOGRAPHY_API_URL = "https://portal.opentopography.org/API/globaldem"
AWS_TERRAIN_GEOTIFF_BASE = "https://s3.amazonaws.com/elevation-tiles-prod/geotiff"
OPENTOPODATA_API_URL = "https://api.opentopodata.org/v1/srtm30m"

DEFAULT_CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "cache" / "srtm"
DEFAULT_DEM_TYPE = "SRTMGL1"
NODATA_VALUE = -32768.0


@dataclass(frozen=True)
class GeoBounds:
    """Geographic bounding box in WGS84 coordinates (degrees)."""

    south: float  # min latitude [-90.0, 90.0]
    west: float   # min longitude [-180.0, 180.0]
    north: float  # max latitude [-90.0, 90.0]
    east: float   # max longitude [-180.0, 180.0]

    def __post_init__(self) -> None:
        if not (-90.0 <= self.south <= 90.0 and -90.0 <= self.north <= 90.0):
            raise ValueError(f"Latitudes must be in [-90, 90], got south={self.south}, north={self.north}")
        if not (-180.0 <= self.west <= 180.0 and -180.0 <= self.east <= 180.0):
            raise ValueError(f"Longitudes must be in [-180, 180], got west={self.west}, east={self.east}")
        if self.south >= self.north:
            raise ValueError(f"south ({self.south}) must be strictly less than north ({self.north})")
        if self.west >= self.east:
            raise ValueError(f"west ({self.west}) must be strictly less than east ({self.east})")

    @classmethod
    def from_tuple(cls, bounds: Sequence[float]) -> GeoBounds:
        """Create from (south, west, north, east) or (min_lat, min_lon, max_lat, max_lon)."""
        if len(bounds) != 4:
            raise ValueError(f"Expected 4 bounds elements (south, west, north, east), got {len(bounds)}")
        return cls(south=float(bounds[0]), west=float(bounds[1]), north=float(bounds[2]), east=float(bounds[3]))


@dataclass
class ElevationData:
    """Structured elevation grid result."""

    elevation: np.ndarray  # 2D float32 array in meters
    bounds: GeoBounds
    resolution_deg: tuple[float, float]  # (lat_step, lon_step)
    nodata_value: float = NODATA_VALUE
    source: str = "SRTM"
    crs: str = "EPSG:4326"

    @property
    def shape(self) -> tuple[int, int]:
        return self.elevation.shape

    @property
    def valid_mask(self) -> np.ndarray:
        """Boolean mask where elevation data is valid (non-NoData, non-NaN)."""
        return (self.elevation != self.nodata_value) & ~np.isnan(self.elevation)

    @property
    def valid_elevation(self) -> np.ndarray:
        """1D array of only valid elevation values."""
        return self.elevation[self.valid_mask]


def _get_cache_path(bounds: GeoBounds, dem_type: str, cache_dir: Path) -> Path:
    """Generate a deterministic cache filename for a given bounds and DEM type."""
    key = f"{dem_type}_{bounds.south:.6f}_{bounds.west:.6f}_{bounds.north:.6f}_{bounds.east:.6f}"
    hash_str = hashlib.sha256(key.encode("utf-8")).hexdigest()[:12]
    filename = f"srtm_{dem_type}_{bounds.south:.3f}_{bounds.west:.3f}_{bounds.north:.3f}_{bounds.east:.3f}_{hash_str}.tif"
    return cache_dir / filename


def _read_geotiff_from_file_or_bytes(source: bytes | Path) -> tuple[np.ndarray, tuple[float, float], float, str]:
    """Read elevation array, resolution, nodata, and crs from GeoTIFF."""
    if isinstance(source, bytes):
        dataset_target = io.BytesIO(source)
    else:
        dataset_target = source

    with rasterio.open(dataset_target) as src:
        band = src.read(1).astype(np.float32)
        nodata = float(src.nodata) if src.nodata is not None else NODATA_VALUE
        res_x = float(src.res[0])
        res_y = float(src.res[1])
        crs_str = str(src.crs) if src.crs else "EPSG:4326"

    return band, (res_y, res_x), nodata, crs_str


def _deg2num(lat_deg: float, lon_deg: float, zoom: int) -> tuple[int, int]:
    """Convert WGS84 lat/lon to Slippy map tile X/Y at given zoom level."""
    lat_rad = math.radians(lat_deg)
    n = 2.0 ** zoom
    xtile = int((lon_deg + 180.0) / 360.0 * n)
    ytile = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
    return xtile, ytile


def _fetch_aws_terrain_tile(zoom: int, x: int, y: int, timeout_sec: int = 30) -> bytes:
    """Download an AWS Open Data Terrain GeoTIFF tile."""
    url = f"{AWS_TERRAIN_GEOTIFF_BASE}/{zoom}/{x}/{y}.tif"
    headers = {"User-Agent": "DepthWizard-Calibration/1.0"}
    response = requests.get(url, headers=headers, timeout=timeout_sec)
    response.raise_for_status()
    return response.content


def _reproject_to_wgs84_and_crop(
    datasets: list[rasterio.DatasetReader],
    target_bounds: GeoBounds,
) -> tuple[np.ndarray, tuple[float, float], float]:
    """Mosaic input GeoTIFFs, reproject from Web Mercator (EPSG:3857) to WGS84 (EPSG:4326), and crop to bounds."""
    # 1. Merge all tiles into a single memory dataset if multiple
    if len(datasets) == 1:
        mosaic, mosaic_transform = datasets[0].read(1), datasets[0].transform
        src_crs = datasets[0].crs
        nodata = datasets[0].nodata if datasets[0].nodata is not None else NODATA_VALUE
    else:
        mosaic_arr, mosaic_transform = merge(datasets)
        mosaic = mosaic_arr[0]
        src_crs = datasets[0].crs
        nodata = datasets[0].nodata if datasets[0].nodata is not None else NODATA_VALUE

    dst_crs = CRS.from_epsg(4326)

    # Estimate output pixel dimensions based on target bounds (~30m / 0.000277 deg resolution)
    lat_span = target_bounds.north - target_bounds.south
    lon_span = target_bounds.east - target_bounds.west

    # Target ~30m resolution (1 arc-second ~ 0.0002777 deg)
    res_deg = 0.0002777777777777778
    dst_width = max(int(round(lon_span / res_deg)), 16)
    dst_height = max(int(round(lat_span / res_deg)), 16)

    dst_transform = from_bounds(
        target_bounds.west,
        target_bounds.south,
        target_bounds.east,
        target_bounds.north,
        dst_width,
        dst_height,
    )

    destination = np.full((dst_height, dst_width), nodata, dtype=np.float32)

    with MemoryFile() as memfile:
        with memfile.open(
            driver="GTiff",
            height=mosaic.shape[0],
            width=mosaic.shape[1],
            count=1,
            dtype=mosaic.dtype,
            crs=src_crs,
            transform=mosaic_transform,
            nodata=nodata,
        ) as src_ds:
            src_ds.write(mosaic, 1)

            reproject(
                source=rasterio.band(src_ds, 1),
                destination=destination,
                src_transform=mosaic_transform,
                src_crs=src_crs,
                dst_transform=dst_transform,
                dst_crs=dst_crs,
                resampling=Resampling.bilinear,
                src_nodata=nodata,
                dst_nodata=nodata,
            )

    return destination, (res_deg, res_deg), float(nodata)


def _fetch_from_aws_terrain_tiles(
    bounds: GeoBounds,
    zoom: int = 10,
    timeout_sec: int = 30,
) -> tuple[np.ndarray, tuple[float, float], float, str]:
    """Fetch elevation grid for bounds by downloading and mosaicing AWS Open Data GeoTIFF tiles."""
    # Find tile range in Slippy map coordinates
    min_x, max_y = _deg2num(bounds.south, bounds.west, zoom)
    max_x, min_y = _deg2num(bounds.north, bounds.east, zoom)

    x_start = min(min_x, max_x)
    x_end = max(min_x, max_x)
    y_start = min(min_y, max_y)
    y_end = max(min_y, max_y)

    mem_files: list[MemoryFile] = []
    datasets: list[rasterio.DatasetReader] = []

    try:
        for ty in range(y_start, y_end + 1):
            for tx in range(x_start, x_end + 1):
                logger.info("Downloading AWS terrain GeoTIFF tile: z=%d, x=%d, y=%d", zoom, tx, ty)
                tile_bytes = _fetch_aws_terrain_tile(zoom, tx, ty, timeout_sec=timeout_sec)
                mf = MemoryFile(tile_bytes)
                mem_files.append(mf)
                datasets.append(mf.open())

        elevation, res, nodata = _reproject_to_wgs84_and_crop(datasets, bounds)
        return elevation, res, nodata, "EPSG:4326"
    finally:
        for ds in datasets:
            try:
                ds.close()
            except Exception:
                pass
        for mf in mem_files:
            try:
                mf.close()
            except Exception:
                pass


def _fetch_from_opentopography(
    bounds: GeoBounds,
    dem_type: str = DEFAULT_DEM_TYPE,
    api_key: str | None = None,
    timeout_sec: int = 60,
) -> bytes:
    """Fetch from OpenTopography Global DEM API."""
    api_key = api_key or os.environ.get("OPENTOPOGRAPHY_API_KEY")
    if not api_key:
        raise ValueError("OpenTopography API key required.")

    params = {
        "demtype": dem_type,
        "south": f"{bounds.south:.6f}",
        "north": f"{bounds.north:.6f}",
        "west": f"{bounds.west:.6f}",
        "east": f"{bounds.east:.6f}",
        "outputFormat": "GTiff",
        "API_Key": api_key,
    }
    headers = {"User-Agent": "DepthWizard-Calibration/1.0"}
    response = requests.get(OPENTOPOGRAPHY_API_URL, params=params, headers=headers, timeout=timeout_sec)
    response.raise_for_status()
    return response.content


def fetch_srtm_elevation(
    bounds: GeoBounds | Sequence[float],
    dem_type: str = DEFAULT_DEM_TYPE,
    cache_dir: str | Path | None = None,
    api_key: str | None = None,
    timeout_sec: int = 60,
    force_refresh: bool = False,
) -> ElevationData:
    """Fetch SRTM elevation grid for a bounding box, using disk caching and multi-cell tile retrieval.

    Parameters
    ----------
    bounds : GeoBounds | tuple[float, float, float, float]
        Geographic bounding box: (south, west, north, east) in WGS84 degrees.
    dem_type : str
        DEM type ('SRTMGL1' [30m], 'SRTMGL3' [90m], 'COP30', 'NASADEM').
    cache_dir : str | Path | None
        Local directory to store cached GeoTIFF tiles. Defaults to ml/data/cache/srtm.
    api_key : str | None
        OpenTopography API Key (or set OPENTOPOGRAPHY_API_KEY environment variable).
    timeout_sec : int
        HTTP request timeout in seconds.
    force_refresh : bool
        If True, ignore local cache and re-download.

    Returns
    -------
    ElevationData
        Structured elevation data containing 2D numpy array in meters, resolution, and CRS.
    """
    if isinstance(bounds, (list, tuple)):
        bounds = GeoBounds.from_tuple(bounds)

    cache_dir_path = Path(cache_dir) if cache_dir else DEFAULT_CACHE_DIR
    cache_dir_path.mkdir(parents=True, exist_ok=True)
    cache_file = _get_cache_path(bounds, dem_type, cache_dir_path)

    # 1. Check local cache
    if cache_file.exists() and not force_refresh:
        logger.info("Loading cached SRTM tile from %s", cache_file)
        try:
            elevation, res, nodata, crs_str = _read_geotiff_from_file_or_bytes(cache_file)
            return ElevationData(
                elevation=elevation,
                bounds=bounds,
                resolution_deg=res,
                nodata_value=nodata,
                source=f"Cache-{dem_type}",
                crs=crs_str,
            )
        except Exception as e:
            logger.warning("Failed to read cached SRTM file %s (%s). Re-fetching.", cache_file, e)

    # 2. Try OpenTopography if API Key is present
    effective_api_key = api_key or os.environ.get("OPENTOPOGRAPHY_API_KEY")
    if effective_api_key:
        try:
            tiff_bytes = _fetch_from_opentopography(
                bounds=bounds,
                dem_type=dem_type,
                api_key=effective_api_key,
                timeout_sec=timeout_sec,
            )
            cache_file.write_bytes(tiff_bytes)
            elevation, res, nodata, crs_str = _read_geotiff_from_file_or_bytes(tiff_bytes)
            return ElevationData(
                elevation=elevation,
                bounds=bounds,
                resolution_deg=res,
                nodata_value=nodata,
                source=f"OpenTopography-{dem_type}",
                crs=crs_str,
            )
        except Exception as e:
            logger.warning("OpenTopography API fetch failed (%s). Falling back to AWS Open Data Terrain.", e)

    # 3. Fallback to public AWS Open Data Terrain tiles (zero API key needed)
    elevation, res, nodata, crs_str = _fetch_from_aws_terrain_tiles(
        bounds=bounds,
        zoom=10,
        timeout_sec=timeout_sec,
    )

    # 4. Save to GeoTIFF cache
    try:
        h, w = elevation.shape
        dst_transform = from_bounds(bounds.west, bounds.south, bounds.east, bounds.north, w, h)
        with rasterio.open(
            cache_file,
            "w",
            driver="GTiff",
            height=h,
            width=w,
            count=1,
            dtype=np.float32,
            crs=CRS.from_epsg(4326),
            transform=dst_transform,
            nodata=nodata,
        ) as dst:
            dst.write(elevation, 1)
        logger.info("Saved merged SRTM elevation tile to cache: %s", cache_file)
    except Exception as e:
        logger.warning("Failed to cache GeoTIFF to %s: %s", cache_file, e)

    return ElevationData(
        elevation=elevation,
        bounds=bounds,
        resolution_deg=res,
        nodata_value=nodata,
        source=f"AWS-OpenData-{dem_type}",
        crs=crs_str,
    )


def get_elevation_at_point(
    lat: float,
    lon: float,
    buffer_deg: float = 0.01,
    dem_type: str = DEFAULT_DEM_TYPE,
    cache_dir: str | Path | None = None,
) -> float:
    """Fetch point elevation in meters at specific WGS84 lat/lon."""
    bounds = GeoBounds(
        south=lat - buffer_deg,
        west=lon - buffer_deg,
        north=lat + buffer_deg,
        east=lon + buffer_deg,
    )
    tile = fetch_srtm_elevation(bounds, dem_type=dem_type, cache_dir=cache_dir)
    valid = tile.valid_elevation
    if len(valid) == 0:
        return float("nan")
    h, w = tile.shape
    center_val = tile.elevation[h // 2, w // 2]
    if center_val != tile.nodata_value and not np.isnan(center_val):
        return float(center_val)
    return float(np.median(valid))


def test_fetch_chennai() -> ElevationData:
    """Sanity test fetching real SRTM elevation for Chennai, India (lat ~13.0827, lon ~80.2707)."""
    # Chennai bounds (~8km x ~8km box around central Chennai)
    chennai_bounds = GeoBounds(
        south=13.040,
        west=80.200,
        north=13.120,
        east=80.280,
    )
    print(f"Testing SRTM fetch for Chennai bounds: {chennai_bounds}")
    tile = fetch_srtm_elevation(chennai_bounds, dem_type="SRTMGL1")
    valid_elev = tile.valid_elevation

    print(f"Retrieved tile shape: {tile.shape}")
    print(f"Source: {tile.source}, CRS: {tile.crs}")
    print(f"Valid elevation pixels: {len(valid_elev)} / {tile.elevation.size}")
    if len(valid_elev) > 0:
        print(
            f"Elevation stats — Min: {valid_elev.min():.2f}m, Max: {valid_elev.max():.2f}m, "
            f"Mean: {valid_elev.mean():.2f}m, Median: {np.median(valid_elev):.2f}m"
        )

    assert tile.elevation.ndim == 2, f"Expected 2D elevation grid, got shape {tile.shape}"
    assert tile.elevation.size > 0, "Elevation grid is empty"
    assert len(valid_elev) > 0, "No valid elevation data found in Chennai tile"
    # Chennai elevation typically ranges between 0m (coast) and 100m (inland)
    assert valid_elev.min() >= -100.0, f"Unrealistic minimum elevation: {valid_elev.min()}m"
    assert valid_elev.max() <= 500.0, f"Unrealistic maximum elevation for Chennai: {valid_elev.max()}m"
    print("SRTM fetch test passed successfully!")
    return tile


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    test_fetch_chennai()
