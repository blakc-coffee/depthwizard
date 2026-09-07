"""process_image(job_id) — the async pipeline task (PRD §8/§9.10 B2–B3).

Owner: Backend Engineer B. See PRD §9.
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
from app.services.jobs import JobService
from integration.pipeline_runner import run_pipeline

logger = logging.getLogger("depthwizard.worker")

# Coarse stage reporting: ml/pipeline.py is currently one synchronous call
# with no progress callback, so intermediate stages (estimating_depth,
# fetching_reference, calibrating) can't be reported mid-run yet. Revisit
# once ML exposes progress hooks (Phase 4/5).
_BEFORE_PIPELINE = ("loading_input", 5)
_AFTER_PIPELINE = ("packaging", 85)
_AFTER_STAGING = ("uploading_results", 95)


class _PipelineContractError(Exception):
    """Raised when the pipeline's output fails strict contract validation —
    distinct from a real exception inside the pipeline, so the failure
    message can say exactly what's missing rather than looking like a crash."""


@celery_app.task(
    name="app.tasks.process_image.process_image",
    bind=True,
    max_retries=3,
    default_retry_delay=10,
    acks_late=True,
)
def process_image(self, job_id: str) -> None:
    """Load job -> download input -> run the ML pipeline -> stage artifacts
    -> re-check the job still exists -> promote -> mark completed.

    Transient failures (storage/network issues -> RESULT_STORAGE_FAILED,
    SRTM timeouts -> SRTM_FETCH_FAILED) retry with bounded backoff.
    Deterministic failures (bad input, ML inference failure, or the
    pipeline's output not yet satisfying the frozen contract) fail once —
    retrying those burns GPU time without changing the outcome (PRD §9.7).
    """
    db = SessionLocal()
    jobs = JobService(db)
    job_uuid = uuid.UUID(job_id)
    workdir = Path(tempfile.mkdtemp(prefix=f"depthwizard-{job_id}-"))
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

        result = run_pipeline(local_input, workdir)

        # This is the completion gate: a "completed" job in the database
        # must never violate the frozen contract. Today, until ML Phase 4/5
        # lands, this is expected to fail — see integration/contracts.py.
        problems = result.validate(strict=True)
        if problems:
            raise _PipelineContractError(
                "Pipeline output does not yet satisfy the frozen contract: " + "; ".join(problems)
            )

        stage, progress = _AFTER_PIPELINE
        jobs.set_progress(job_uuid, stage=stage, progress=progress)

        local_artifacts = {
            "texture.png": Path(result.texture_path),
            "heightmap.png": Path(result.heightmap_path),
            "heightmap_16bit.png": Path(result.heightmap_16bit_path) if result.heightmap_16bit_path else None,
            "confidence_map.png": Path(result.confidence_map_path) if result.confidence_map_path else None,
            "dsm.tif": Path(result.dsm_path) if result.dsm_path else None,
        }
        local_artifacts = {name: p for name, p in local_artifacts.items() if p is not None}

        staged = storage.upload_staged_outputs(user_id, job_id, local_artifacts)
        stage, progress = _AFTER_STAGING
        jobs.set_progress(job_uuid, stage=stage, progress=progress)

        # Re-check existence AFTER staging, BEFORE promoting (PRD §8) — this
        # is what closes the delete-during-processing orphan window: nothing
        # has reached outputs/ yet, so if the job was deleted mid-run there
        # is nothing to clean up there, only the staging prefix.
        if not jobs.exists(job_uuid):
            storage.delete_staging(user_id, job_id)
            return

        promoted = storage.promote_staged_outputs(user_id, job_id)
        del staged  # only used to decide what got promoted; promoted has the final paths

        jobs.set_completed(
            job_uuid,
            result={
                "output_type": result.output_type,
                "texture_path": promoted.get("texture.png"),
                "heightmap_path": promoted.get("heightmap.png"),
                "heightmap_16bit_path": promoted.get("heightmap_16bit.png"),
                "confidence_map_path": promoted.get("confidence_map.png"),
                "dsm_path": promoted.get("dsm.tif"),
                "metadata": result.metadata,
                "metrics": result.metrics,
                "warnings": result.warnings,
            },
        )

    except ApiException as exc:
        if exc.code not in NON_RETRYABLE_CODES:
            try:
                raise self.retry(exc=exc)
            except MaxRetriesExceededError:
                pass
        jobs.set_failed(job_uuid, error_code=exc.code, error_message=exc.message)

    except _PipelineContractError as exc:
        jobs.set_failed(job_uuid, error_code=ErrorCode.ML_INFERENCE_FAILED, error_message=str(exc))

    except Exception:  # noqa: BLE001 — top-level task boundary
        # Log the real exception server-side (redacted by core/logging.py's
        # formatter) but never store/return the raw exception text as job
        # state — str(exc) on an unexpected exception could in principle
        # echo back internal details a caller shouldn't see. The client only
        # ever gets the generic message below.
        logger.exception("Unexpected pipeline failure for job %s", job_id)
        jobs.set_failed(
            job_uuid,
            error_code=ErrorCode.ML_INFERENCE_FAILED,
            error_message="Pipeline processing failed unexpectedly.",
        )

    finally:
        db.close()
        shutil.rmtree(workdir, ignore_errors=True)
        if local_input is not None:
            local_input.unlink(missing_ok=True)
