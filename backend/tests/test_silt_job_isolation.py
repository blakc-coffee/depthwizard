"""Cross-user isolation tests for river-silt jobs — mirrors
test_job_isolation.py's coverage for the terrain job flow. Same minimum bar:
User A cannot read, poll, get results for, or delete User B's silt jobs.
"""

from __future__ import annotations

import uuid

from conftest import sample_png_bytes


def _create_silt_job(client, user_box, user_id: str) -> str:
    user_box["user_id"] = user_id
    resp = client.post("/api/v1/silt-jobs", files={"file": ("sample.png", sample_png_bytes(), "image/png")})
    assert resp.status_code == 202, resp.text
    return resp.json()["job_id"]


def test_owner_can_read_their_own_silt_job(client, user_box, new_user_id):
    job_id = _create_silt_job(client, user_box, new_user_id)
    user_box["user_id"] = new_user_id
    resp = client.get(f"/api/v1/silt-jobs/{job_id}")
    assert resp.status_code == 200
    assert resp.json()["job_id"] == job_id
    assert resp.json()["status"] == "queued"


def test_other_user_cannot_poll_silt_status(client, user_box, new_user_id):
    owner = new_user_id
    other = str(uuid.uuid4())
    job_id = _create_silt_job(client, user_box, owner)

    user_box["user_id"] = other
    resp = client.get(f"/api/v1/silt-jobs/{job_id}")
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "FORBIDDEN_JOB"


def test_other_user_cannot_get_silt_result(client, user_box, new_user_id):
    owner = new_user_id
    other = str(uuid.uuid4())
    job_id = _create_silt_job(client, user_box, owner)

    user_box["user_id"] = other
    resp = client.get(f"/api/v1/silt-jobs/{job_id}/result")
    assert resp.status_code == 403


def test_other_user_cannot_delete_silt_job(client, user_box, new_user_id):
    owner = new_user_id
    other = str(uuid.uuid4())
    job_id = _create_silt_job(client, user_box, owner)

    user_box["user_id"] = other
    resp = client.delete(f"/api/v1/silt-jobs/{job_id}")
    assert resp.status_code == 403


def test_owner_can_delete_their_own_silt_job(client, user_box, new_user_id):
    job_id = _create_silt_job(client, user_box, new_user_id)
    user_box["user_id"] = new_user_id
    resp = client.delete(f"/api/v1/silt-jobs/{job_id}")
    assert resp.status_code == 204

    resp = client.get(f"/api/v1/silt-jobs/{job_id}")
    assert resp.status_code == 404


def test_result_not_available_before_completion(client, user_box, new_user_id):
    job_id = _create_silt_job(client, user_box, new_user_id)
    user_box["user_id"] = new_user_id
    resp = client.get(f"/api/v1/silt-jobs/{job_id}/result")
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "JOB_NOT_COMPLETE"


def test_owner_sees_only_their_own_jobs_in_list(client, user_box, new_user_id):
    other = str(uuid.uuid4())
    _create_silt_job(client, user_box, other)
    my_job_id = _create_silt_job(client, user_box, new_user_id)

    user_box["user_id"] = new_user_id
    resp = client.get("/api/v1/silt-jobs")
    assert resp.status_code == 200
    job_ids = [j["job_id"] for j in resp.json()["jobs"]]
    assert job_ids == [my_job_id]
