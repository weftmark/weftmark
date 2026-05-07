"""Celery task: scheduled-task tick.

Runs every 60 seconds via Celery Beat. For each enabled ScheduledTask row,
checks whether the cron expression matches the current minute and dispatches
the corresponding Celery task if so.
"""

import logging
from datetime import datetime, timedelta, timezone

from app.celery_app import celery_app

log = logging.getLogger(__name__)

# Public registry: maps slug → metadata used by the admin endpoints.
REGISTRY: dict[str, dict] = {
    "cve_scan": {
        "display_name": "CVE Scan",
        "description": (
            "Scans Python dependencies via pip-audit for known vulnerabilities. "
            "Results are stored and shown in the CVE Scan tab and admin warning banner. "
            "Scheduled runs skip npm scanning (Python deps only)."
        ),
        "default_cron": "0 2 * * *",
    },
}


def _dispatch_cve_scan(settings):
    from app.services.task_history import record_queued
    from app.tasks.cve_scan import run_cve_scan

    task = run_cve_scan.delay({})
    record_queued(settings, task.id, "app.tasks.cve_scan.run_cve_scan", "scheduled:cve_scan")
    return task


DISPATCH_FNS: dict[str, object] = {
    "cve_scan": _dispatch_cve_scan,
}


@celery_app.task(
    name="app.tasks.scheduler.run_scheduled_tasks",
    max_retries=0,
    ignore_result=True,
)
def run_scheduled_tasks() -> None:
    from croniter import croniter

    from app.config import get_settings

    settings = get_settings()
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(seconds=70)

    try:
        from sqlalchemy import create_engine, select
        from sqlalchemy.orm import Session

        from app.models.scheduled_task import ScheduledTask

        engine = create_engine(settings.database_url_sync)
        with Session(engine) as db:
            tasks = db.scalars(select(ScheduledTask).where(ScheduledTask.enabled.is_(True))).all()
            fired = []
            for task in tasks:
                try:
                    cron = croniter(task.cron, window_start)
                    next_fire = cron.get_next(datetime)
                    if next_fire <= now:
                        dispatch_fn = DISPATCH_FNS.get(task.name)
                        if dispatch_fn:
                            dispatch_fn(settings)
                            task.last_fired_at = now
                            fired.append(task.name)
                            log.info("scheduled_task_fired name=%s", task.name)
                        else:
                            log.warning("scheduled_task_no_dispatch name=%s", task.name)
                except Exception:
                    log.exception("scheduled_task_error name=%s", task.name)
            if fired:
                db.commit()
        engine.dispose()
    except Exception:
        log.exception("run_scheduled_tasks_error")
