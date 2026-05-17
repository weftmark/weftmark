import logging

from celery import Celery
from celery.signals import setup_logging as celery_setup_logging
from celery.signals import task_failure, task_postrun, task_prerun, task_retry, worker_ready

from app.config import get_settings
from app.logging_config import configure_logging
from app.version import VERSION

log = logging.getLogger(__name__)

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
            "app.tasks.feedback_dispatch",
            "app.tasks.geo",
            "app.tasks.maintenance",
            "app.tasks.metrics",
            "app.tasks.preview",
            "app.tasks.purge",
            "app.tasks.tiles",
            "app.tasks.s3_audit",
            "app.tasks.cve_scan",
            "app.tasks.debug",
            "app.tasks.post_migrate",
            "app.tasks.reparse",
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
            },
            "record-business-metrics": {
                "task": "app.tasks.metrics.record_business_metrics",
                "schedule": 300.0,
            },
            "backfill-project-drawdown-previews": {
                "task": "app.tasks.maintenance.backfill_project_drawdown_previews",
                "schedule": 300.0,
            },
            "refresh-geoip-database": {
                "task": "app.tasks.geo.refresh_geoip_database",
                "schedule": 604800.0,  # weekly
            },
            "expire-project-slugs": {
                "task": "app.tasks.maintenance.expire_project_slugs",
                "schedule": 86400.0,  # nightly
            },
        },
    )
    return app


celery_app = _make_celery()

_settings = get_settings()
if _settings.otel_exporter_otlp_endpoint:
    from app.telemetry import configure_telemetry

    configure_telemetry(_settings)


@celery_setup_logging.connect
def _configure_worker_logging(**kwargs):
    # Connecting to this signal suppresses Celery's own root-logger hijacking.
    # We replicate what main.py does: JSON StreamHandler first, then re-attach
    # the OTel LoggingHandler (configure_logging() clears root handlers, which
    # would otherwise strip the handler added by configure_telemetry()).
    settings = get_settings()
    configure_logging(settings.log_level)
    if settings.otel_exporter_otlp_endpoint:
        try:
            from opentelemetry._logs import get_logger_provider
            from opentelemetry.sdk._logs import LoggingHandler

            logging.getLogger().addHandler(LoggingHandler(logger_provider=get_logger_provider()))
        except Exception:
            pass


@task_prerun.connect
def _on_task_prerun(task_id=None, **kwargs):
    try:
        from app.services.task_history import record_started

        record_started(get_settings(), task_id)
    except Exception:
        pass


@task_postrun.connect
def _on_task_postrun(task_id=None, state=None, sender=None, **kwargs):
    task_name = sender.name if sender is not None else "unknown"
    if state == "SUCCESS":
        try:
            from app.services.task_history import record_completed

            record_completed(get_settings(), task_id, "success")
        except Exception:
            pass
        try:
            from app.metrics import celery_tasks_total

            celery_tasks_total.add(1, {"state": "succeeded", "task": task_name})
        except Exception:
            pass


@task_failure.connect
def _on_task_failure(task_id=None, exception=None, sender=None, **kwargs):
    task_name = sender.name if sender is not None else "unknown"
    outcome = "revoked" if type(exception).__name__ == "Revoked" else "failed"
    try:
        from app.services.task_history import record_completed

        record_completed(get_settings(), task_id, outcome, error=None if outcome == "revoked" else str(exception))
    except Exception:
        pass
    try:
        from app.metrics import celery_tasks_total

        celery_tasks_total.add(1, {"state": outcome, "task": task_name})
    except Exception:
        pass


@task_retry.connect
def _on_task_retry(sender=None, **kwargs):
    task_name = sender.name if sender is not None else "unknown"
    try:
        from app.metrics import celery_tasks_total

        celery_tasks_total.add(1, {"state": "retried", "task": task_name})
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


@worker_ready.connect
def _initial_geoip_download(sender=None, **kwargs):
    """Queue a GeoLite2 download if the MMDB is absent and the license key is set."""
    try:
        import os

        settings = get_settings()
        if settings.maxmind_license_key and not os.path.exists(settings.geoip_db_path):
            from app.tasks.geo import refresh_geoip_database

            refresh_geoip_database.delay()
            log.info("GeoLite2-City MMDB absent — queued initial download")
    except Exception:
        pass


@worker_ready.connect
def _run_post_migrate_backfills(sender=None, **kwargs):
    """Dispatch post-migration backfills on every worker startup.

    Each backfill is idempotent (checks null rows) and guarded by a Redis
    SETNX lock, so only one worker dispatches per deploy window.
    """
    try:
        from app.tasks.post_migrate import run_post_migrate_backfills

        run_post_migrate_backfills.delay()
        log.info("post_migrate_backfills queued on worker_ready")
    except Exception:
        pass
