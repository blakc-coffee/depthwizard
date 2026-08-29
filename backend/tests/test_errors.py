"""Error envelope shape tests (PRD §9.7) — no DB or infra required.

Owner: Backend Engineer A. See PRD §9.
"""

from __future__ import annotations

from app.core.errors import ApiException, ErrorCode


def test_envelope_shape():
    exc = ApiException(ErrorCode.FILE_TOO_LARGE, "File exceeds the 50 MB limit.")
    assert exc.to_envelope() == {"error": {"code": "FILE_TOO_LARGE", "message": "File exceeds the 50 MB limit."}}
    assert exc.http_status == 413


def test_every_error_code_maps_to_a_client_or_server_http_status():
    for code in ErrorCode:
        exc = ApiException(code, "test")
        assert 400 <= exc.http_status < 600


def test_forbidden_and_not_found_are_distinct():
    # PRD §9.2: ownership mismatch -> FORBIDDEN_JOB, nonexistent -> JOB_NOT_FOUND.
    assert ApiException(ErrorCode.FORBIDDEN_JOB, "x").http_status == 403
    assert ApiException(ErrorCode.JOB_NOT_FOUND, "x").http_status == 404
