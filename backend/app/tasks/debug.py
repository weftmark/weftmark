"""Debug tasks — superuser-only utilities for testing the worker pipeline."""

import time

from celery import Task

from app.celery_app import celery_app


@celery_app.task(
    bind=True,
    max_retries=0,
    soft_time_limit=120,
    time_limit=130,
    name="app.tasks.debug.debug_sleep",
)
def debug_sleep(self: Task, seconds: int = 30) -> dict:
    """Sleep for `seconds` seconds so the worker dashboard shows an active task."""
    seconds = max(1, min(seconds, 120))
    time.sleep(seconds)
    return {"slept": seconds}
