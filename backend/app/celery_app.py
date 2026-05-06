from celery import Celery
from celery.signals import worker_ready

from app.config import get_settings
from app.version import VERSION

WORKER_VERSION_KEY = "weftmark:worker_version"


def _make_celery() -> Celery:
    settings = get_settings()
    app = Celery(
        "weftmark",
        broker=settings.redis_url,
        backend=settings.redis_url,
        include=["app.tasks.deletion", "app.tasks.preview", "app.tasks.s3_audit", "app.tasks.cve_scan"],
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


@worker_ready.connect
def _publish_worker_version(**kwargs):
    """Write VERSION to Redis when the worker process finishes startup."""
    try:
        import redis as _redis

        settings = get_settings()
        client = _redis.from_url(settings.redis_url, socket_connect_timeout=2)
        client.set(WORKER_VERSION_KEY, VERSION)
        client.close()
    except Exception:
        pass  # version badge degrades gracefully if Redis is unavailable
