"""compare_images(compare_id) — the async before/after comparison task (PRD §8/§9.9).

Owner: Backend Engineer B. See PRD §9.

Mirrors process_image.py: load state, download inputs, run the ML function,
stage artifacts, re-check the row still exists, promote, mark completed. The
inputs here are two already-completed jobs' artifacts, so no image is
re-processed (PRD §9.9).
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
from app.services.compares import CompareService
from app.services.jobs import JobService

logger = logging.getLogger("depthwizard.worker")

_LOADING = ("loading_inputs", 10)
_ALIGNING = ("aligning", 35)
_COMPUTING = ("computing_diff", 60)
_PACKAGING = ("packaging", 85)
_UPLOADING = ("uploading_results", 95)


class _CompareContractError(Exception):
    """The ML comparison output failed contract validation, or the comparison
    model isn't available yet — distinct from a crash inside it."""


def _extents_overlap(before_dsm: Path, after_dsm: Path) -> bool:
    # Deferred import: the API image carries no rasterio (PRD §26).
    import rasterio
    from rasterio.warp import transform_bounds

    def bounds(path: Path):
        with rasterio.open(path) as src:
            return transform_bounds(src.crs, "EPSG:4326", *src.bounds)

    west, south, east, north = bounds(before_dsm)
    other_west, other_south, other_east, other_north = bounds(after_dsm)
    return max(west, other_west) < min(east, other_east) and max(south, other_south) < min(north, other_north)


@celery_app.task(
    name="app.tasks.compare_images.compare_images",
    bind=True,
    max_retries=3,
    default_retry_delay=10,
    acks_late=True,
)
def compare_images(self, compare_id: str) -> None:
    db = SessionLocal()
    compares = CompareService(db)
    jobs = JobService(db)
    compare_uuid = uuid.UUID(compare_id)
    workdir = Path(tempfile.mkdtemp(prefix=f"depthwizard-compare-{compare_id}-"))
    downloads: list[Path] = []

    try:
        compare = compares.get_for_processing(compare_uuid)
        if compare is None:
            return  # deleted before the worker even picked it up

        compares.set_celery_task_id(compare_uuid, self.request.id)
        before = jobs.get_for_processing(compare.before_job_id)
        after = jobs.get_for_processing(compare.after_job_id)
        if before is None or after is None:
            return  # a source job was deleted; the DB cascade removes this row too

        if before.status != "completed" or after.status != "completed":
            raise ApiException(ErrorCode.COMPARE_JOB_NOT_ELIGIBLE, "Both source jobs must be completed.")
        if not before.heightmap_path or not after.heightmap_path:
            raise ApiException(ErrorCode.COMPARE_JOB_NOT_ELIGIBLE, "A source job has no heightmap to compare.")

        compares.set_processing(compare_uuid)
        stage, progress = _LOADING
        compares.set_progress(compare_uuid, stage=stage, progress=progress)

        user_id = str(compare.user_id)
        before_heightmap = storage.download_input(before.heightmap_path)
        after_heightmap = storage.download_input(after.heightmap_path)
        downloads += [before_heightmap, after_heightmap]

        before_dsm = after_dsm = None
        if before.dsm_path and after.dsm_path:
            before_dsm = storage.download_input(before.dsm_path)
            after_dsm = storage.download_input(after.dsm_path)
            downloads += [before_dsm, after_dsm]

        stage, progress = _ALIGNING
        compares.set_progress(compare_uuid, stage=stage, progress=progress)
        # Only checkable when both sides carry geospatial bounds; otherwise the
        # ML function decides whether the pair is usable (docs/compare_contract).
        if before_dsm and after_dsm and not _extents_overlap(before_dsm, after_dsm):
            raise ApiException(ErrorCode.COMPARE_EXTENT_MISMATCH, "The two jobs do not cover overlapping areas.")

        stage, progress = _COMPUTING
        compares.set_progress(compare_uuid, stage=stage, progress=progress)
        # Deferred import: keeps ml/ and its dependencies out of the API image.
        from integration.compare_runner import CompareModelUnavailable, run_compare

        try:
            result = run_compare(
                before_heightmap_path=before_heightmap,
                after_heightmap_path=after_heightmap,
                before_metadata=before.job_metadata or {},
                after_metadata=after.job_metadata or {},
                output_dir=workdir,
                before_dsm_path=before_dsm,
                after_dsm_path=after_dsm,
            )
        except CompareModelUnavailable as exc:
            raise _CompareContractError(str(exc)) from exc

        both_absolute = before.output_type == "absolute_dsm" and after.output_type == "absolute_dsm"
        problems = result.validate(both_absolute=both_absolute)
        if problems:
            raise _CompareContractError("Comparison output does not satisfy the contract: " + "; ".join(problems))

        stage, progress = _PACKAGING
        compares.set_progress(compare_uuid, stage=stage, progress=progress)
        storage.upload_staged_outputs(user_id, compare_id, {"diff_map.png": Path(result.diff_map_path)})

        stage, progress = _UPLOADING
        compares.set_progress(compare_uuid, stage=stage, progress=progress)

        # Same delete-during-processing orphan-window close as process_image.py.
        if not compares.exists(compare_uuid):
            storage.delete_staging(user_id, compare_id)
            return

        promoted = storage.promote_staged_compare_outputs(user_id, compare_id)
        compares.set_completed(
            compare_uuid,
            result={
                "diff_map_path": promoted.get("diff_map.png"),
                # The source jobs' own textures, referenced rather than copied.
                "before_texture_path": before.texture_path,
                "after_texture_path": after.texture_path,
                "metadata": result.metadata,
                "warnings": result.warnings,
            },
        )

    except ApiException as exc:
        if exc.code not in NON_RETRYABLE_CODES:
            try:
                raise self.retry(exc=exc)
            except MaxRetriesExceededError:
                pass
        compares.set_failed(compare_uuid, error_code=exc.code, error_message=exc.message)

    except _CompareContractError as exc:
        compares.set_failed(compare_uuid, error_code=ErrorCode.ML_INFERENCE_FAILED, error_message=str(exc))

    except Exception:  # noqa: BLE001 — top-level task boundary
        logger.exception("Unexpected comparison failure for compare %s", compare_id)
        compares.set_failed(
            compare_uuid,
            error_code=ErrorCode.ML_INFERENCE_FAILED,
            error_message="Comparison processing failed unexpectedly.",
        )

    finally:
        db.close()
        shutil.rmtree(workdir, ignore_errors=True)
        for path in downloads:
            path.unlink(missing_ok=True)
