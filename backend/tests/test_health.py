"""Health check test — runs standalone, no DB or infra required.

Owner: Backend Engineer A. See PRD §9.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_health_unauthenticated():
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
