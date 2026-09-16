import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "calibration"))
from silt_gauge_anchor import _haversine_km, _parse_rdb_site_ids, find_gauge_anchor  # noqa: E402

SAMPLE_RDB = (
    "# comment line\n"
    "agency_cd\tsite_no\tstation_nm\n"
    "5s\t15s\t50s\n"
    "USGS\t03145483\tRaccoon Creek near Granville OH\n"
    "USGS\t03146500\tLicking River at Newark OH\n"
)


def _iv_payload(site_lat, site_lon, ssc_value, age_hours, site_name="Test Site", site_id="00000000"):
    observed_at = (datetime.now(timezone.utc) - timedelta(hours=age_hours)).isoformat()
    return {
        "value": {
            "timeSeries": [{
                "sourceInfo": {
                    "siteName": site_name,
                    "siteCode": [{"value": site_id}],
                    "geoLocation": {"geogLocation": {"latitude": site_lat, "longitude": site_lon}},
                },
                "values": [{"value": [{"value": str(ssc_value), "dateTime": observed_at}]}],
            }]
        }
    }


def test_haversine_km_known_distance():
    # NYC to LA, real-world reference distance ~3936 km
    dist = _haversine_km(40.7128, -74.0060, 34.0522, -118.2437)
    assert 3900 < dist < 3980


def test_parse_rdb_site_ids_extracts_real_format():
    ids = _parse_rdb_site_ids(SAMPLE_RDB)
    assert ids == ["03145483", "03146500"]


def test_parse_rdb_site_ids_handles_empty_response():
    assert _parse_rdb_site_ids("# no data\n") == []


def test_find_gauge_anchor_returns_none_on_network_failure():
    import requests
    with patch("silt_gauge_anchor.requests.get", side_effect=requests.RequestException("boom")):
        assert find_gauge_anchor(40.0, -82.0) is None


def test_find_gauge_anchor_returns_none_when_no_sites_found():
    site_resp = MagicMock(text="# no sites\n", status_code=200)
    with patch("silt_gauge_anchor.requests.get", return_value=site_resp):
        assert find_gauge_anchor(40.0, -82.0) is None


def test_find_gauge_anchor_returns_real_nearby_fresh_reading():
    site_resp = MagicMock(text=SAMPLE_RDB, status_code=200)
    iv_resp = MagicMock(status_code=200)
    iv_resp.json.return_value = _iv_payload(40.069, -82.552, 45.0, age_hours=2.0)

    with patch("silt_gauge_anchor.requests.get", side_effect=[site_resp, iv_resp]):
        anchor = find_gauge_anchor(40.068, -82.551, max_distance_km=25, max_age_hours=24)

    assert anchor is not None
    assert anchor.ssc_mg_l == 45.0
    assert anchor.distance_km < 1.0


def test_find_gauge_anchor_disqualifies_stale_reading():
    """A real reading that's too old must not be used as if it were
    current — same disqualify-don't-fabricate rule as everywhere else in
    this project's calibration code."""
    site_resp = MagicMock(text=SAMPLE_RDB, status_code=200)
    iv_resp = MagicMock(status_code=200)
    iv_resp.json.return_value = _iv_payload(40.069, -82.552, 45.0, age_hours=72.0)

    with patch("silt_gauge_anchor.requests.get", side_effect=[site_resp, iv_resp]):
        anchor = find_gauge_anchor(40.068, -82.551, max_distance_km=25, max_age_hours=24)

    assert anchor is None


def test_find_gauge_anchor_disqualifies_distant_reading():
    site_resp = MagicMock(text=SAMPLE_RDB, status_code=200)
    iv_resp = MagicMock(status_code=200)
    iv_resp.json.return_value = _iv_payload(45.0, -100.0, 45.0, age_hours=1.0)  # far from the query point

    with patch("silt_gauge_anchor.requests.get", side_effect=[site_resp, iv_resp]):
        anchor = find_gauge_anchor(40.068, -82.551, max_distance_km=25, max_age_hours=24)

    assert anchor is None
