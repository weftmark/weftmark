from celery import Celery
from celery.signals import task_failure, task_postrun, task_prerun, worker_ready

from app.config import get_settings
from app.version import VERSION

WORKER_VERSION_KEY = "weftmark:worker_version"
WORKER_VERSION_NODE_PREFIX = "weftmark:worker_version:node:"


def _make_celery() -> Celery:
    settings = get_settings()
    app = Celery(
        "weftmark",
        broker=settings.redis_url,
        backend=settings.redis_url,
        include=[
            "app.tasks.deletion",
            "app.tasks.email_task",
            "app.tasks.preview",
            "app.tasks.purge",
            "app.tasks.s3_audit",
            "app.tasks.cve_scan",
            "app.tasks.debug",
            "app.tasks.scheduler",
        ],
    )
    app.conf.update(
        task_serializer="json",
        accept_content=["json"],
        result_serializer="json",
        timezone="UTC",
        enable_utc=True,
        task_track_started=True,
        worker_prefetch_multiplier=1,
        broker_connection_retry_on_startup=True,
        beat_schedule={
            "run-scheduled-tasks": {
                "task": "app.tasks.scheduler.run_scheduled_tasks",
                "schedule": 60.0,
            }
        },
    )
    return app


celery_app = _make_celery()


@task_prerun.connect
def _on_task_prerun(task_id=None, **kwargs):
    try:
        from app.services.task_history import record_started

        record_started(get_settings(), task_id)
    except Exception:
        pass


@task_postrun.connect
def _on_task_postrun(task_id=None, state=None, **kwargs):
    if state == "SUCCESS":
        try:
            from app.services.task_history import record_completed

            record_completed(get_settings(), task_id, "success")
        except Exception:
            pass


@task_failure.connect
def _on_task_failure(task_id=None, exception=None, **kwargs):
    try:
        from app.services.task_history import record_completed

        state = "revoked" if type(exception).__name__ == "Revoked" else "failed"
        record_completed(get_settings(), task_id, state, error=None if state == "revoked" else str(exception))
    except Exception:
        pass


@worker_ready.connect
def _publish_worker_version(sender=None, **kwargs):
    """Write VERSION to Redis when the worker process finishes startup."""
    try:
        import redis as _redis

        settings = get_settings()
        client = _redis.from_url(settings.redis_url, socket_connect_timeout=2)
        client.set(WORKER_VERSION_KEY, VERSION)
        if sender is not None:
            client.set(f"{WORKER_VERSION_NODE_PREFIX}{sender.hostname}", VERSION)
        client.close()
    except Exception:
        pass  # version badge degrades gracefully if Redis is unavailable
