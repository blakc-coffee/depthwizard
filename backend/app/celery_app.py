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
        # compare_images is wired in here when B7 starts (PRD §9.10 B7) —
        # routes/compare.py and tasks/compare_images.py stay stubs until then.
    },
    task_time_limit=settings.celery_task_time_limit_seconds,
    task_soft_time_limit=max(settings.celery_task_time_limit_seconds - 30, 30),
    task_acks_late=True,
    # One ML worker per GPU (PRD §9.10 B6) — don't let a worker process
    # start a second task before the first finishes.
    worker_prefetch_multiplier=1,
    imports=("app.tasks.process_image",),
)
