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
        "default_config": {},
    },
    "s3_audit": {
        "display_name": "S3 Orphan Audit",
        "description": (
            "Scans S3 bucket for files not referenced in the database. "
            "Results are flagged in the admin warning banner. "
            "Not applicable when STORAGE_BACKEND=local."
        ),
        "default_cron": "0 3 * * 0",
        "default_config": {},
    },
    "stale_signup_dismissal": {
        "display_name": "Stale Signup Dismissal",
        "description": (
            "Auto-dismisses pending signup requests older than the configured threshold. "
            "Dismissed signups are removed with no notification sent."
        ),
        "default_cron": "0 4 * * *",
        "default_config": {"days": 30},
    },
    "invite_pruning": {
        "display_name": "Expired Invite Pruning",
        "description": (
            "Deletes expired, accepted, and revoked invite records older than the retention window. "
            "Active (pending, not expired) invites are never deleted."
        ),
        "default_cron": "30 3 * * 1",
        "default_config": {"retention_days": 90},
    },
    "audit_log_pruning": {
        "display_name": "Audit Log Pruning",
        "description": (
            "Deletes audit log entries older than the retention window. "
            "Security events (user.banned, user.deleted, user.elevated) are never pruned."
        ),
        "default_cron": "0 3 * * 2",
        "default_config": {"retention_days": 90},
    },
    "heartbeat": {
        "display_name": "Worker Heartbeat",
        "description": (
            "No-op task that records itself in the task history every 15 minutes. "
            "Absence of recent heartbeat entries indicates a worker outage."
        ),
        "default_cron": "*/15 * * * *",
        "default_config": {},
    },
    "preview_retry": {
        "display_name": "Failed Preview Retry",
        "description": (
            "Re-dispatches drawdown preview generation for drafts missing a preview. "
            "Skips drafts uploaded in the last 10 minutes to avoid racing initial generation."
        ),
        "default_cron": "0 5 * * *",
        "default_config": {"limit": 50},
    },
    "daily_health_check": {
        "display_name": "Daily Health Check",
        "description": (
            "Runs all service probes once daily and writes the result to the server events log. "
            "Sends a health degraded alert email if any probe is failing."
        ),
        "default_cron": "0 2 * * *",
        "default_config": {},
    },
    "server_event_log_pruning": {
        "display_name": "Server Event Log Pruning",
        "description": (
            "Removes server event log entries older than the configured age limit "
            "and trims the table when it exceeds the maximum entry count."
        ),
        "default_cron": "30 2 * * *",
        "default_config": {"max_age_days": 28, "max_entries": 1000},
    },
}


def _dispatch_cve_scan(settings, task=None):
    from app.services.task_history import record_queued
    from app.tasks.cve_scan import run_cve_scan

    t = run_cve_scan.delay({})
    record_queued(settings, t.id, "app.tasks.cve_scan.run_cve_scan", "scheduled:cve_scan")
    return t


def _dispatch_s3_audit(settings, task=None):
    from app.services.task_history import record_queued
    from app.tasks.s3_audit import run_s3_orphan_scan

    t = run_s3_orphan_scan.delay()
    record_queued(settings, t.id, "app.tasks.s3_audit.run_s3_orphan_scan", "scheduled:s3_audit")
    return t


def _dispatch_stale_signup_dismissal(settings, task=None):
    from app.services.task_history import record_queued
    from app.tasks.maintenance import dismiss_stale_signups

    cfg = (task.config or {}) if task else {}
    days = int(cfg.get("days", 30))
    t = dismiss_stale_signups.delay(days=days)
    record_queued(settings, t.id, "app.tasks.maintenance.dismiss_stale_signups", "scheduled:stale_signup_dismissal")
    return t


def _dispatch_invite_pruning(settings, task=None):
    from app.services.task_history import record_queued
    from app.tasks.maintenance import prune_expired_invites

    cfg = (task.config or {}) if task else {}
    retention_days = int(cfg.get("retention_days", 90))
    t = prune_expired_invites.delay(retention_days=retention_days)
    record_queued(settings, t.id, "app.tasks.maintenance.prune_expired_invites", "scheduled:invite_pruning")
    return t


def _dispatch_audit_log_pruning(settings, task=None):
    from app.services.task_history import record_queued
    from app.tasks.maintenance import prune_audit_log

    cfg = (task.config or {}) if task else {}
    retention_days = int(cfg.get("retention_days", 90))
    t = prune_audit_log.delay(retention_days=retention_days)
    record_queued(settings, t.id, "app.tasks.maintenance.prune_audit_log", "scheduled:audit_log_pruning")
    return t


def _dispatch_heartbeat(settings, task=None):
    from app.services.task_history import record_queued
    from app.tasks.maintenance import worker_heartbeat

    t = worker_heartbeat.delay()
    record_queued(settings, t.id, "app.tasks.maintenance.worker_heartbeat", "scheduled:heartbeat")
    return t


def _dispatch_preview_retry(settings, task=None):
    from app.services.task_history import record_queued
    from app.tasks.maintenance import retry_failed_previews

    cfg = (task.config or {}) if task else {}
    limit = int(cfg.get("limit", 50))
    t = retry_failed_previews.delay(limit=limit)
    record_queued(settings, t.id, "app.tasks.maintenance.retry_failed_previews", "scheduled:preview_retry")
    return t


def _dispatch_daily_health_check(settings, task=None):
    from app.services.task_history import record_queued
    from app.tasks.maintenance import daily_health_check

    t = daily_health_check.delay()
    record_queued(settings, t.id, "app.tasks.maintenance.daily_health_check", "scheduled:daily_health_check")
    return t


def _dispatch_server_event_log_pruning(settings, task=None):
    from app.services.task_history import record_queued
    from app.tasks.maintenance import prune_server_event_log

    cfg = (task.config or {}) if task else {}
    max_age_days = int(cfg.get("max_age_days", 28))
    max_entries = int(cfg.get("max_entries", 1000))
    t = prune_server_event_log.delay(max_age_days=max_age_days, max_entries=max_entries)
    record_queued(settings, t.id, "app.tasks.maintenance.prune_server_event_log", "scheduled:server_event_log_pruning")
    return t


DISPATCH_FNS: dict[str, object] = {
    "cve_scan": _dispatch_cve_scan,
    "s3_audit": _dispatch_s3_audit,
    "stale_signup_dismissal": _dispatch_stale_signup_dismissal,
    "invite_pruning": _dispatch_invite_pruning,
    "audit_log_pruning": _dispatch_audit_log_pruning,
    "heartbeat": _dispatch_heartbeat,
    "preview_retry": _dispatch_preview_retry,
    "daily_health_check": _dispatch_daily_health_check,
    "server_event_log_pruning": _dispatch_server_event_log_pruning,
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
                            dispatch_fn(settings, task)
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
