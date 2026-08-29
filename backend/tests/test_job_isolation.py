"""Cross-user job isolation tests (PRD §6/§9.2/§9.11).

Owner: Backend Engineer A. See PRD §9.

Required isolation: User A cannot read, poll, get results for, or delete
User B's jobs. This is the minimum coverage so isolation isn't unverified
from day one — full concurrency/security hardening is B6, later.
"""

from __future__ import annotations

import uuid

from conftest import sample_png_bytes


def _create_job(client, user_box, user_id: str) -> str:
    user_box["user_id"] = user_id
    resp = client.post("/api/v1/jobs", files={"file": ("sample.png", sample_png_bytes(), "image/png")})
    assert resp.status_code == 202, resp.text
    return resp.json()["job_id"]


def test_owner_can_read_their_own_job(client, user_box, new_user_id):
    job_id = _create_job(client, user_box, new_user_id)
    user_box["user_id"] = new_user_id
    resp = client.get(f"/api/v1/jobs/{job_id}")
    assert resp.status_code == 200
    assert resp.json()["job_id"] == job_id
    assert resp.json()["status"] == "queued"


def test_other_user_cannot_poll_status(client, user_box, new_user_id):
    owner = new_user_id
    other = str(uuid.uuid4())
    job_id = _create_job(client, user_box, owner)

    user_box["user_id"] = other
    resp = client.get(f"/api/v1/jobs/{job_id}")
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "FORBIDDEN_JOB"


def test_other_user_cannot_get_result(client, user_box, new_user_id):
    owner = new_user_id
    other = str(uuid.uuid4())
    job_id = _create_job(client, user_box, owner)

    user_box["user_id"] = other
    resp = client.get(f"/api/v1/jobs/{job_id}/result")
    assert resp.status_code == 403


def test_other_user_cannot_delete(client, user_box, new_user_id):
    owner = new_user_id
    other = str(uuid.uuid4())
    job_id = _create_job(client, user_box, owner)

    user_box["user_id"] = other
    resp = client.delete(f"/api/v1/jobs/{job_id}")
    assert resp.status_code == 403

    # and it must still exist for the real owner afterwards
    user_box["user_id"] = owner
    assert client.get(f"/api/v1/jobs/{job_id}").status_code == 200


def test_other_user_job_list_never_shows_it(client, user_box, new_user_id):
    owner = new_user_id
    other = str(uuid.uuid4())
    _create_job(client, user_box, owner)

    user_box["user_id"] = other
    resp = client.get("/api/v1/jobs")
    assert resp.status_code == 200
    assert resp.json()["jobs"] == []


def test_nonexistent_job_is_not_found(client, user_box, new_user_id):
    user_box["user_id"] = new_user_id
    resp = client.get(f"/api/v1/jobs/{uuid.uuid4()}")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "JOB_NOT_FOUND"


def test_result_not_ready_before_completion(client, user_box, new_user_id):
    job_id = _create_job(client, user_box, new_user_id)
    user_box["user_id"] = new_user_id
    resp = client.get(f"/api/v1/jobs/{job_id}/result")
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "JOB_NOT_COMPLETE"


def test_owner_can_delete_their_own_job(client, user_box, new_user_id):
    job_id = _create_job(client, user_box, new_user_id)
    user_box["user_id"] = new_user_id
    assert client.delete(f"/api/v1/jobs/{job_id}").status_code == 204
    assert client.get(f"/api/v1/jobs/{job_id}").status_code == 404
