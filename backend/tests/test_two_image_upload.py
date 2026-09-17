"""Two-image (before/after) uploads create two jobs and a comparison (PRD §9.9)."""

from __future__ import annotations

import uuid

from conftest import sample_png_bytes
from sqlalchemy import select

from app.core.errors import ApiException, ErrorCode
from app.db.models import Compare, Job
from app.services import storage as storage_module
from app.tasks import process_image as task_module


def _png(name: str):
    return (name, sample_png_bytes(), "image/png")


def _upload_pair(client):
    return client.post("/api/v1/jobs", files={"file": _png("before.png"), "secondary_file": _png("after.png")})


def _jobs_for(db_session, user_id: str):
    return db_session.scalars(select(Job).where(Job.user_id == uuid.UUID(user_id))).all()


def test_single_upload_response_is_unchanged(client, user_box, new_user_id):
    user_box["user_id"] = new_user_id
    resp = client.post("/api/v1/jobs", files={"file": _png("a.png")})
    assert resp.status_code == 202
    assert set(resp.json()) == {"job_id", "status"}


def test_two_images_create_before_after_jobs_and_a_comparison(client, db_session, user_box, new_user_id, monkeypatch):
    enqueued = []

    class _Result:
        id = "task-id"

    monkeypatch.setattr(task_module.process_image, "delay", lambda job_id: (enqueued.append(job_id), _Result())[1])
    user_box["user_id"] = new_user_id

    resp = _upload_pair(client)

    assert resp.status_code == 202, resp.text
    body = resp.json()
    before_id, after_id = uuid.UUID(body["job_id"]), uuid.UUID(body["secondary_job_id"])
    compare = db_session.get(Compare, uuid.UUID(body["compare_id"]))
    assert (compare.before_job_id, compare.after_job_id, str(compare.user_id), compare.status) == (
        before_id,
        after_id,
        new_user_id,
        "queued",
    )
    assert db_session.get(Job, before_id).input_filename == "before.png"
    assert db_session.get(Job, after_id).input_filename == "after.png"
    assert sorted(enqueued) == sorted([str(before_id), str(after_id)])


def test_invalid_second_image_creates_nothing(client, db_session, user_box, new_user_id):
    user_box["user_id"] = new_user_id
    resp = client.post(
        "/api/v1/jobs",
        files={"file": _png("before.png"), "secondary_file": ("after.png", b"not an image", "image/png")},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "UNSUPPORTED_FILE"
    assert resp.json()["error"]["message"].startswith("Second image:")
    assert _jobs_for(db_session, new_user_id) == []


def test_second_storage_failure_removes_the_first_job(client, db_session, user_box, new_user_id, monkeypatch):
    stored, purged = [], []

    def save_input(user_id, job_id, content, media_type):
        stored.append(job_id)
        if len(stored) == 2:
            raise ApiException(ErrorCode.RESULT_STORAGE_FAILED, "Could not store the uploaded file.")
        return "path"

    monkeypatch.setattr(storage_module, "save_input", save_input)
    monkeypatch.setattr(storage_module, "delete_job_artifacts", lambda user_id, job_id: purged.append(job_id))
    user_box["user_id"] = new_user_id

    resp = _upload_pair(client)

    assert resp.json()["error"]["code"] == "RESULT_STORAGE_FAILED"
    assert _jobs_for(db_session, new_user_id) == []
    assert db_session.scalars(select(Compare).where(Compare.user_id == uuid.UUID(new_user_id))).all() == []
    assert purged == [stored[0]]


def test_other_user_cannot_read_either_job(client, user_box, new_user_id):
    user_box["user_id"] = new_user_id
    body = _upload_pair(client).json()

    user_box["user_id"] = str(uuid.uuid4())
    for job_id in (body["job_id"], body["secondary_job_id"]):
        assert client.get(f"/api/v1/jobs/{job_id}").status_code == 403


def test_deleting_a_source_job_removes_the_comparison(client, db_session, user_box, new_user_id):
    user_box["user_id"] = new_user_id
    body = _upload_pair(client).json()

    assert client.delete(f"/api/v1/jobs/{body['secondary_job_id']}").status_code == 204
    assert db_session.scalars(select(Compare).where(Compare.id == uuid.UUID(body["compare_id"]))).all() == []
