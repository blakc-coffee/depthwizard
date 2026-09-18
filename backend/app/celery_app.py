"""Celery app: Redis broker only, never job status (PRD §2).

Owner: Backend Engineer B. See PRD §9.
"""

from __future__ import annotations

from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "depthwizard",
    broker=settings.redis_url.get_secret_value(),
    backend=None,  # no result backend — Postgres is the source of truth, not Celery/Redis
)

celery_app.conf.update(
    task_default_queue="image_processing",
    task_routes={
        "app.tasks.process_image.process_image": {"queue": "image_processing"},
        "app.tasks.process_river_silt_image.process_river_silt_image": {"queue": "image_processing"},
        "app.tasks.compare_images.compare_images": {"queue": "image_processing"},
    },
    task_time_limit=settings.celery_task_time_limit_seconds,
    task_soft_time_limit=max(settings.celery_task_time_limit_seconds - 30, 30),
    task_acks_late=True,
    # One ML worker per GPU (PRD §9.10 B6) — don't let a worker process
    # start a second task before the first finishes.
    #
    # worker_prefetch_multiplier=1 alone does NOT achieve this — it only
    # limits how many tasks one worker PROCESS prefetches, not how many
    # worker processes Celery forks in the first place. Real prod incident
    # (2026-09-18): no --concurrency flag was set anywhere, so Celery
    # defaulted to os.cpu_count() fork workers. A two-image compare upload
    # queues both jobs back to back (routes/jobs.py's create_job loop), a
    # multi-core worker container picked both up in separate ForkPoolWorkers
    # simultaneously, each loading its own full copy of Depth Anything V2 +
    # the segmentation model, and the container OOM-killed (SIGKILL 9) both.
    # worker_concurrency=1 is the actual fix — it caps the number of worker
    # processes Celery forks, not just prefetch behavior.
    worker_prefetch_multiplier=1,
    worker_concurrency=1,
    imports=("app.tasks.process_image", "app.tasks.process_river_silt_image", "app.tasks.compare_images"),
)
