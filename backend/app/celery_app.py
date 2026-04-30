from celery import Celery

from app.config import get_settings


def _make_celery() -> Celery:
    settings = get_settings()
    app = Celery(
        "weftmark",
        broker=settings.redis_url,
        backend=settings.redis_url,
        include=["app.tasks.deletion"],
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
    )
    return app


celery_app = _make_celery()
