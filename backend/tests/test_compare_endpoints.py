"""Comparison endpoints: ownership, eligibility, result delivery (PRD §9.9)."""

from __future__ import annotations

import uuid

import pytest

from app.services.compares import CompareService
from app.services.jobs import JobService
from app.tasks import compare_images as compare_task


@pytest.fixture(autouse=True)
def _no_real_queue(monkeypatch):
    queued = []

    class _Result:
        id = "compare-task-id"

    monkeypatch.setattr(compare_task.compare_images, "delay", lambda compare_id: (queued.append(compare_id), _Result())[1])
    return queued


def _job(db, user_id: str, name: str, *, completed: bool = True):
    jobs = JobService(db)
    job = jobs.create(user_id=user_id, input_path=f"inputs/{user_id}/{name}/original.png", input_filename=f"{name}.png", input_media_type="image/png")
    if completed:
        jobs.set_completed(
            job.id,
            result={
                "output_type": "relative_dsm",
                "texture_path": f"outputs/{user_id}/{job.id}/texture.png",
                "heightmap_path": f"outputs/{user_id}/{job.id}/heightmap.png",
                "metadata": {"height_units": "relative", "min_height": 0, "max_height": 255, "width": 8, "height": 8},
                "warnings": [],
            },
        )
    return job


def test_create_compare_queues_the_task(client, db_session, user_box, new_user_id, _no_real_queue):
    user_box["user_id"] = new_user_id
    before, after = _job(db_session, new_user_id, "before"), _job(db_session, new_user_id, "after")

    resp = client.post("/api/v1/compare", json={"before_job_id": str(before.id), "after_job_id": str(after.id)})

    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "queued"
    assert _no_real_queue == [body["compare_id"]]


def test_cannot_compare_a_job_you_do_not_own(client, db_session, user_box, new_user_id):
    owner = new_user_id
    before, after = _job(db_session, owner, "before"), _job(db_session, owner, "after")

    user_box["user_id"] = str(uuid.uuid4())
    resp = client.post("/api/v1/compare", json={"before_job_id": str(before.id), "after_job_id": str(after.id)})

    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "FORBIDDEN_JOB"


def test_unfinished_or_identical_jobs_are_not_eligible(client, db_session, user_box, new_user_id):
    user_box["user_id"] = new_user_id
    done = _job(db_session, new_user_id, "before")
    pending = _job(db_session, new_user_id, "after", completed=False)

    same = client.post("/api/v1/compare", json={"before_job_id": str(done.id), "after_job_id": str(done.id)})
    unfinished = client.post("/api/v1/compare", json={"before_job_id": str(done.id), "after_job_id": str(pending.id)})

    for resp in (same, unfinished):
        assert resp.status_code == 409
        assert resp.json()["error"]["code"] == "COMPARE_JOB_NOT_ELIGIBLE"


def test_status_and_result_before_completion(client, db_session, user_box, new_user_id):
    user_box["user_id"] = new_user_id
    before, after = _job(db_session, new_user_id, "before"), _job(db_session, new_user_id, "after")
    compare = CompareService(db_session).create(user_id=new_user_id, before_job_id=before.id, after_job_id=after.id)

    status = client.get(f"/api/v1/compare/{compare.id}")
    assert status.status_code == 200
    assert status.json() == {"compare_id": str(compare.id), "status": "queued", "stage": None, "progress": 0, "error": None}

    result = client.get(f"/api/v1/compare/{compare.id}/result")
    assert result.status_code == 409
    assert result.json()["error"]["code"] == "JOB_NOT_COMPLETE"


def test_completed_result_returns_signed_urls_and_metadata(client, db_session, user_box, new_user_id):
    user_box["user_id"] = new_user_id
    before, after = _job(db_session, new_user_id, "before"), _job(db_session, new_user_id, "after")
    compares = CompareService(db_session)
    compare = compares.create(user_id=new_user_id, before_job_id=before.id, after_job_id=after.id)
    metadata = {"height_units": "relative", "max_loss": -9.0, "max_gain": 3.0, "changed_area_fraction": 0.1, "threshold": 2.0}
    compares.set_completed(
        compare.id,
        result={
            "diff_map_path": f"compares/{new_user_id}/{compare.id}/diff_map.png",
            "before_texture_path": before.texture_path,
            "after_texture_path": after.texture_path,
            "metadata": metadata,
            "warnings": ["relative change only"],
        },
    )

    body = client.get(f"/api/v1/compare/{compare.id}/result").json()

    assert body["before_job_id"] == str(before.id) and body["after_job_id"] == str(after.id)
    assert body["metadata"] == metadata
    assert body["warnings"] == ["relative change only"]
    assert body["artifacts"]["diff_map_url"].endswith(f"compares/{new_user_id}/{compare.id}/diff_map.png")
    assert body["artifacts"]["before_texture_url"].endswith(before.texture_path)
    assert body["artifacts"]["after_texture_url"].endswith(after.texture_path)


def test_other_user_cannot_read_status_or_result(client, db_session, user_box, new_user_id):
    owner = new_user_id
    before, after = _job(db_session, owner, "before"), _job(db_session, owner, "after")
    compare = CompareService(db_session).create(user_id=owner, before_job_id=before.id, after_job_id=after.id)

    user_box["user_id"] = str(uuid.uuid4())
    for path in (f"/api/v1/compare/{compare.id}", f"/api/v1/compare/{compare.id}/result"):
        resp = client.get(path)
        assert resp.status_code == 403
        assert resp.json()["error"]["code"] == "FORBIDDEN_JOB"


def test_unknown_comparison_is_not_found(client, user_box, new_user_id):
    user_box["user_id"] = new_user_id
    resp = client.get(f"/api/v1/compare/{uuid.uuid4()}")
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "JOB_NOT_FOUND"
