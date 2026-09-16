"""process_river_silt_image(job_id) — the async river-silt pipeline task.

Mirrors app/tasks/process_image.py's structure — load job, download input,
run the ML pipeline, stage artifacts, re-check existence, promote, mark
completed. Simpler than the terrain task: no strict-contract validation gate
(ml/river_silt_pipeline.py has no frozen contract yet, unlike
integration/contracts.py — this is placeholder scope, see that module's
docstring) and only two artifacts (texture, heatmap) instead of five.
"""

from __future__ import annotations

import logging
import shutil
import tempfile
import uuid
from pathlib import Path

from celery.exceptions import MaxRetriesExceededError

from app.celery_app import celery_app
from app.core.errors import NON_RETRYABLE_CODES, ApiException, ErrorCode
from app.db.session import SessionLocal
from app.services import storage
from app.services.silt_jobs import SiltJobService

logger = logging.getLogger("depthwizard.worker")

_BEFORE_PIPELINE = ("loading_input", 5)
_AFTER_PIPELINE = ("packaging", 85)
_AFTER_STAGING = ("uploading_results", 95)


@celery_app.task(
    name="app.tasks.process_river_silt_image.process_river_silt_image",
    bind=True,
    max_retries=3,
    default_retry_delay=10,
    acks_late=True,
)
def process_river_silt_image(self, job_id: str) -> None:
    db = SessionLocal()
    jobs = SiltJobService(db)
    job_uuid = uuid.UUID(job_id)
    workdir = Path(tempfile.mkdtemp(prefix=f"depthwizard-silt-{job_id}-"))
    local_input: Path | None = None

    try:
        job = jobs.get_for_processing(job_uuid)
        if job is None:
            return  # deleted before the worker even picked it up

        jobs.set_celery_task_id(job_uuid, self.request.id)
        jobs.set_processing(job_uuid)
        stage, progress = _BEFORE_PIPELINE
        jobs.set_progress(job_uuid, stage=stage, progress=progress)

        user_id = str(job.user_id)
        local_input = storage.download_input(job.input_path)

        # Deferred: the API imports this module only to enqueue the task, and
        # its image has neither ml/ nor the ML libraries — only the worker runs this.
        from ml.river_silt_pipeline import run_silt_pipeline

        result = run_silt_pipeline(str(local_input), str(workdir))

        stage, progress = _AFTER_PIPELINE
        jobs.set_progress(job_uuid, stage=stage, progress=progress)

        local_artifacts = {
            "texture.png": Path(result.texture_path),
            "heatmap.png": Path(result.heatmap_path),
        }

        staged = storage.upload_staged_outputs(user_id, job_id, local_artifacts)
        stage, progress = _AFTER_STAGING
        jobs.set_progress(job_uuid, stage=stage, progress=progress)

        # Same delete-during-processing orphan-window close as process_image.py.
        if not jobs.exists(job_uuid):
            storage.delete_staging(user_id, job_id)
            return

        promoted = storage.promote_staged_outputs(user_id, job_id)
        del staged

        jobs.set_completed(
            job_uuid,
            result={
                "output_type": result.output_type,
                "texture_path": promoted.get("texture.png"),
                "heatmap_path": promoted.get("heatmap.png"),
                "predicted_ssc_mg_l": result.predicted_ssc_mg_l,
                "warnings": result.warnings,
                # Reuses the existing (previously-unused) job_metadata JSONB
                # column — no migration needed for dredging/cross-section.
                "metadata": {
                    "dredging_level": result.dredging_level,
                    "dredging_label": result.dredging_label,
                    "cross_section_profile": result.cross_section_profile,
                },
            },
        )

    except ApiException as exc:
        if exc.code not in NON_RETRYABLE_CODES:
            try:
                raise self.retry(exc=exc)
            except MaxRetriesExceededError:
                pass
        jobs.set_failed(job_uuid, error_code=exc.code, error_message=exc.message)

    except Exception:  # noqa: BLE001 — top-level task boundary
        logger.exception("Unexpected river-silt pipeline failure for job %s", job_id)
        jobs.set_failed(
            job_uuid,
            error_code=ErrorCode.ML_INFERENCE_FAILED,
            error_message="River-silt pipeline processing failed unexpectedly.",
        )

    finally:
        db.close()
        shutil.rmtree(workdir, ignore_errors=True)
        if local_input is not None:
            local_input.unlink(missing_ok=True)
