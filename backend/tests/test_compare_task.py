"""compare_images task: runs the ML diff for two completed jobs (PRD §9.9)."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.orm import sessionmaker

from app.db.models import Compare
from app.services import storage as storage_module
from app.services.compares import CompareService
from app.services.jobs import JobService
from app.tasks import compare_images as compare_task
from integration import compare_runner as compare_runner_module
from integration.compare_runner import CompareModelUnavailable
from integration.contracts import CompareResult


def _metadata(**overrides):
    base = {"height_units": "relative", "max_loss": -9.0, "max_gain": 3.0, "changed_area_fraction": 0.1, "threshold": 2.0}
    base.update(overrides)
    return base


def _completed_job(db, user_id: str, name: str, *, status: str = "completed", output_type: str = "relative_dsm"):
    jobs = JobService(db)
    job = jobs.create(user_id=user_id, input_path=f"inputs/{user_id}/{name}/original.png", input_filename=f"{name}.png", input_media_type="image/png")
    if status == "completed":
        jobs.set_completed(
            job.id,
            result={
                "output_type": output_type,
                "texture_path": f"outputs/{user_id}/{job.id}/texture.png",
                "heightmap_path": f"outputs/{user_id}/{job.id}/heightmap.png",
                "metadata": {"height_units": "relative", "min_height": 0, "max_height": 255, "width": 8, "height": 8},
                "warnings": [],
            },
        )
    return job


@pytest.fixture()
def compare_setup(engine, db_session, new_user_id, monkeypatch, tmp_path):
    """Two completed jobs plus a queued comparison, with storage faked and the
    task given its own session against the test database."""
    monkeypatch.setattr(compare_task, "SessionLocal", sessionmaker(bind=engine))

    diff_file = tmp_path / "diff_map.png"
    diff_file.write_bytes(b"png")
    staged, promoted, deleted = [], [], []

    def download_input(path):
        local = tmp_path / path.replace("/", "_")
        local.write_bytes(b"data")
        return local

    monkeypatch.setattr(storage_module, "download_input", download_input)
    monkeypatch.setattr(storage_module, "upload_staged_outputs", lambda user_id, obj_id, paths: staged.append((obj_id, sorted(paths))) or {})
    monkeypatch.setattr(
        storage_module,
        "promote_staged_compare_outputs",
        lambda user_id, compare_id: promoted.append(compare_id) or {"diff_map.png": f"compares/{user_id}/{compare_id}/diff_map.png"},
    )
    monkeypatch.setattr(storage_module, "delete_staging", lambda user_id, obj_id: deleted.append(obj_id))

    before = _completed_job(db_session, new_user_id, "before")
    after = _completed_job(db_session, new_user_id, "after")
    compare = CompareService(db_session).create(user_id=new_user_id, before_job_id=before.id, after_job_id=after.id)
    return {"before": before, "after": after, "compare": compare, "diff_file": diff_file,
            "staged": staged, "promoted": promoted, "user_id": new_user_id}


def _run(compare_id) -> None:
    compare_task.compare_images.apply(args=[str(compare_id)])


def _reloaded(db_session, compare_id) -> Compare:
    db_session.expire_all()
    return db_session.get(Compare, compare_id)


def test_completed_comparison_stores_diff_map_and_metadata(compare_setup, db_session, monkeypatch):
    setup = compare_setup
    received = {}

    def run_compare(**kwargs):
        received.update(kwargs)
        return CompareResult(diff_map_path=str(setup["diff_file"]), metadata=_metadata(), warnings=["relative change only"])

    monkeypatch.setattr(compare_runner_module, "run_compare", run_compare)

    _run(setup["compare"].id)

    compare = _reloaded(db_session, setup["compare"].id)
    assert (compare.status, compare.progress, compare.stage) == ("completed", 100, "uploading_results")
    assert compare.diff_map_path == f"compares/{setup['user_id']}/{compare.id}/diff_map.png"
    assert compare.before_texture_path == setup["before"].texture_path
    assert compare.after_texture_path == setup["after"].texture_path
    assert compare.compare_metadata == _metadata()
    assert compare.warnings == ["relative change only"]
    assert setup["staged"] == [(str(compare.id), ["diff_map.png"])]
    assert setup["promoted"] == [str(compare.id)]
    # The ML function receives both jobs' heightmaps and metadata, no DSMs here.
    assert received["before_dsm_path"] is None and received["after_dsm_path"] is None
    assert received["before_metadata"]["width"] == 8


def test_missing_comparison_model_fails_honestly(compare_setup, db_session, monkeypatch):
    def run_compare(**kwargs):
        raise CompareModelUnavailable("Comparison model not available yet.")

    monkeypatch.setattr(compare_runner_module, "run_compare", run_compare)

    _run(compare_setup["compare"].id)

    compare = _reloaded(db_session, compare_setup["compare"].id)
    assert compare.status == "failed"
    assert compare.error_code == "ML_INFERENCE_FAILED"
    assert "not available yet" in compare.error_message
    assert compare.diff_map_path is None


def test_contract_violation_fails_the_comparison(compare_setup, db_session, monkeypatch):
    # Claims metres, but both source jobs are relative.
    monkeypatch.setattr(
        compare_runner_module,
        "run_compare",
        lambda **kwargs: CompareResult(diff_map_path=str(compare_setup["diff_file"]), metadata=_metadata(height_units="m")),
    )

    _run(compare_setup["compare"].id)

    compare = _reloaded(db_session, compare_setup["compare"].id)
    assert compare.status == "failed"
    assert "does not satisfy the contract" in compare.error_message


def test_unfinished_source_job_is_not_eligible(engine, db_session, new_user_id, monkeypatch):
    monkeypatch.setattr(compare_task, "SessionLocal", sessionmaker(bind=engine))
    before = _completed_job(db_session, new_user_id, "before")
    after = _completed_job(db_session, new_user_id, "after", status="queued")
    compare = CompareService(db_session).create(user_id=new_user_id, before_job_id=before.id, after_job_id=after.id)

    _run(compare.id)

    reloaded = _reloaded(db_session, compare.id)
    assert reloaded.status == "failed"
    assert reloaded.error_code == "COMPARE_JOB_NOT_ELIGIBLE"


def test_comparison_is_ready_only_when_both_jobs_completed(db_session, new_user_id):
    compares = CompareService(db_session)
    before = _completed_job(db_session, new_user_id, "before")
    after = _completed_job(db_session, new_user_id, "after", status="queued")
    compare = compares.create(user_id=new_user_id, before_job_id=before.id, after_job_id=after.id)

    assert compares.ready_compare_ids(before.id) == []

    JobService(db_session).set_completed(
        after.id,
        result={"output_type": "relative_dsm", "texture_path": "t", "heightmap_path": "h", "metadata": {}, "warnings": []},
    )
    assert compares.ready_compare_ids(after.id) == [compare.id]


def test_failed_source_job_fails_its_pending_comparisons(db_session, new_user_id):
    compares = CompareService(db_session)
    before = _completed_job(db_session, new_user_id, "before")
    after = _completed_job(db_session, new_user_id, "after", status="queued")
    compare = compares.create(user_id=new_user_id, before_job_id=before.id, after_job_id=after.id)

    compares.fail_pending_for_job(after.id, error_code="COMPARE_JOB_NOT_ELIGIBLE", error_message="A source job failed.")

    reloaded = db_session.get(Compare, compare.id)
    assert (reloaded.status, reloaded.error_code) == ("failed", "COMPARE_JOB_NOT_ELIGIBLE")
    assert compares.ready_compare_ids(before.id) == []


def test_deleted_comparison_row_is_left_alone(compare_setup, db_session, monkeypatch):
    monkeypatch.setattr(
        compare_runner_module,
        "run_compare",
        lambda **kwargs: CompareResult(diff_map_path=str(compare_setup["diff_file"]), metadata=_metadata(), warnings=["w"]),
    )
    compare_id = uuid.uuid4()  # never created

    _run(compare_id)

    assert db_session.get(Compare, compare_id) is None
    assert compare_setup["promoted"] == []
