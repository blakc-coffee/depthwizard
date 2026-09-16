#!/usr/bin/env python3
"""River-silt use case, Chunk 3 — real-time gauge-anchor lookup.

Given an uploaded image's real-world coordinates, checks USGS NWIS
(waterservices.usgs.gov, public, no API key) for a real, live, nearby SSC
(suspended sediment concentration, parameter code 80154) reading to anchor
the prediction to — same "grounded independent measurement overrides the
model" pattern this project's height pipeline already uses for SRTM, and
the same disqualify-don't-fabricate discipline (MIN_SRTM_VALID_FRACTION,
MIN_WATER_FRACTION, etc.) applied here.

REAL, MEASURED LIMITATION (checked before writing this module, not assumed):
live SSC (param 80154) sensors are genuinely rare on USGS's network — a
same-county query returned zero sites, and an entire-California query
returned only 2. Turbidity (param 63680, FNU) is common and easy to find,
but is NOT the same physical quantity as SSC (mg/L) — converting FNU to
mg/L needs a site-specific calibration this project doesn't have, and
guessing a generic ratio would be exactly the kind of fabricated precision
this project's own honesty standard rejects. This module intentionally
anchors ONLY on real SSC readings, never turbidity — expect it to return
None for the overwhelming majority of real-world locations. That is
correct behavior, not a bug: a rare, honest anchor beats a common, wrong one.

Also US-only (NWIS has no non-US coverage) — a real, stated scope limit,
not a hidden one.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import requests

NWIS_SITE_URL = "https://waterservices.usgs.gov/nwis/site/"
NWIS_IV_URL = "https://waterservices.usgs.gov/nwis/iv/"
SSC_PARAMETER_CODE = "80154"  # Suspended sediment concentration, mg/L — the real target quantity
DEFAULT_MAX_DISTANCE_KM = 25.0
DEFAULT_MAX_AGE_HOURS = 24.0  # matches the literature's own "matchup window should be ~1 day" finding


@dataclass
class GaugeAnchor:
    ssc_mg_l: float
    site_name: str
    site_id: str
    distance_km: float
    age_hours: float


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def _bbox(lat: float, lon: float, radius_km: float) -> tuple[float, float, float, float]:
    """west, south, east, north — a simple degree-per-km approximation is
    fine here, this only sizes the initial site search, not the final
    distance filter (which uses real haversine below)."""
    dlat = radius_km / 111.0
    dlon = radius_km / (111.0 * max(0.1, math.cos(math.radians(lat))))
    return (lon - dlon, lat - dlat, lon + dlon, lat + dlat)


def find_gauge_anchor(
    lat: float,
    lon: float,
    max_distance_km: float = DEFAULT_MAX_DISTANCE_KM,
    max_age_hours: float = DEFAULT_MAX_AGE_HOURS,
    timeout: float = 15.0,
) -> GaugeAnchor | None:
    """Real network call, real USGS data — no mocking, no synthetic
    fallback. Returns None (not a guess) when no real, fresh, nearby SSC
    site exists, which per the module's own measured finding above is the
    common case."""
    west, south, east, north = _bbox(lat, lon, max_distance_km)
    try:
        site_resp = requests.get(
            NWIS_SITE_URL,
            params={
                "format": "rdb", "bBox": f"{west},{south},{east},{north}",
                "parameterCd": SSC_PARAMETER_CODE, "siteStatus": "active", "siteType": "ST",
            },
            timeout=timeout,
        )
        site_resp.raise_for_status()
    except requests.RequestException:
        return None  # network failure — no anchor, not a crash (same as SRTM_FETCH_FAILED's role upstream)

    site_ids = _parse_rdb_site_ids(site_resp.text)
    if not site_ids:
        return None

    try:
        iv_resp = requests.get(
            NWIS_IV_URL,
            params={"format": "json", "sites": ",".join(site_ids), "parameterCd": SSC_PARAMETER_CODE, "siteStatus": "active"},
            timeout=timeout,
        )
        iv_resp.raise_for_status()
        payload = iv_resp.json()
    except (requests.RequestException, ValueError):
        return None

    candidates = _extract_candidates(payload, lat, lon)
    trustworthy = [c for c in candidates if c.distance_km <= max_distance_km and c.age_hours <= max_age_hours]
    if not trustworthy:
        return None
    return min(trustworthy, key=lambda c: c.distance_km)


def _parse_rdb_site_ids(rdb_text: str) -> list[str]:
    """USGS's tab-delimited 'rdb' format: comment lines start with '#', the
    first non-comment line is a header, the second is a format-spec line
    (all dashes/numbers), data rows follow."""
    lines = [ln for ln in rdb_text.splitlines() if ln and not ln.startswith("#")]
    if len(lines) < 3:
        return []
    header = lines[0].split("\t")
    try:
        site_col = header.index("site_no")
    except ValueError:
        return []
    return [row.split("\t")[site_col] for row in lines[2:] if len(row.split("\t")) > site_col]


def _extract_candidates(payload: dict, lat: float, lon: float) -> list[GaugeAnchor]:
    from datetime import datetime, timezone

    candidates = []
    for series in payload.get("value", {}).get("timeSeries", []):
        source = series.get("sourceInfo", {})
        geo = source.get("geoLocation", {}).get("geogLocation", {})
        site_lat, site_lon = geo.get("latitude"), geo.get("longitude")
        if site_lat is None or site_lon is None:
            continue
        values = series.get("values", [{}])[0].get("value", [])
        if not values:
            continue
        latest = values[-1]
        try:
            ssc = float(latest["value"])
        except (KeyError, ValueError):
            continue
        try:
            observed_at = datetime.fromisoformat(latest["dateTime"])
        except (KeyError, ValueError):
            continue
        age_hours = (datetime.now(timezone.utc) - observed_at.astimezone(timezone.utc)).total_seconds() / 3600.0
        candidates.append(GaugeAnchor(
            ssc_mg_l=ssc,
            site_name=source.get("siteName", "unknown"),
            site_id=(source.get("siteCode") or [{}])[0].get("value", "unknown"),
            distance_km=_haversine_km(lat, lon, site_lat, site_lon),
            age_hours=abs(age_hours),
        ))
    return candidates
