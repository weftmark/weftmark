"""Celery tasks: scheduled maintenance operations.

Covers:
- dismiss_stale_signups      — auto-dismiss pending signups older than N days
- prune_expired_invites      — delete old non-active invite records
- prune_audit_log            — delete old audit log entries (security events exempt)
- worker_heartbeat           — no-op liveness signal
- retry_failed_previews      — re-dispatch preview generation for drafts missing drawdown previews
"""

import logging
from datetime import datetime, timedelta, timezone

from app.celery_app import celery_app

log = logging.getLogger(__name__)

_AUDIT_LOG_EXEMPT_EVENTS = frozenset({"user.banned", "user.deleted", "user.elevated"})
_AUDIT_LOG_BATCH_SIZE = 1000


@celery_app.task(
    bind=True,
    max_retries=0,
    name="app.tasks.maintenance.dismiss_stale_signups",
)
def dismiss_stale_signups(self, days: int = 30) -> dict:
    from sqlalchemy import create_engine, delete
    from sqlalchemy.orm import Session

    from app.config import get_settings
    from app.models.pending_signup import PendingSignup

    settings = get_settings()
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    engine = create_engine(settings.database_url_sync)
    try:
        with Session(engine) as db:
            result = db.execute(delete(PendingSignup).where(PendingSignup.created_at < cutoff))
            db.commit()
            dismissed = result.rowcount
    finally:
        engine.dispose()
    log.info("dismiss_stale_signups dismissed=%d days=%d", dismissed, days)
    return {"dismissed": dismissed}


@celery_app.task(
    bind=True,
    max_retries=0,
    name="app.tasks.maintenance.prune_expired_invites",
)
def prune_expired_invites(self, retention_days: int = 90) -> dict:
    from sqlalchemy import create_engine, delete, or_
    from sqlalchemy.orm import Session

    from app.config import get_settings
    from app.models.invite import Invite

    settings = get_settings()
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=retention_days)

    engine = create_engine(settings.database_url_sync)
    try:
        with Session(engine) as db:
            result = db.execute(
                delete(Invite).where(
                    or_(
                        Invite.accepted_at.isnot(None),
                        Invite.revoked_at.isnot(None),
                        Invite.expires_at < now,
                    ),
                    Invite.expires_at < cutoff,
                )
            )
            db.commit()
            pruned = result.rowcount
    finally:
        engine.dispose()
    log.info("prune_expired_invites pruned=%d retention_days=%d", pruned, retention_days)
    return {"pruned": pruned}


@celery_app.task(
    bind=True,
    max_retries=0,
    name="app.tasks.maintenance.prune_audit_log",
)
def prune_audit_log(self, retention_days: int = 90) -> dict:
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import Session

    from app.config import get_settings

    settings = get_settings()
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    total_deleted = 0

    exempt = list(_AUDIT_LOG_EXEMPT_EVENTS)
    engine = create_engine(settings.database_url_sync)
    try:
        with Session(engine) as db:
            while True:
                result = db.execute(
                    text(
                        "DELETE FROM audit_logs WHERE id IN ("
                        "  SELECT id FROM audit_logs"
                        "  WHERE created_at < :cutoff"
                        "  AND event_type != ALL(:exempt)"
                        "  LIMIT :batch"
                        ")"
                    ),
                    {"cutoff": cutoff, "exempt": exempt, "batch": _AUDIT_LOG_BATCH_SIZE},
                )
                db.commit()
                deleted = result.rowcount
                total_deleted += deleted
                if deleted < _AUDIT_LOG_BATCH_SIZE:
                    break
    finally:
        engine.dispose()
    log.info("prune_audit_log deleted=%d retention_days=%d", total_deleted, retention_days)
    return {"deleted": total_deleted}


@celery_app.task(
    bind=True,
    max_retries=0,
    name="app.tasks.maintenance.worker_heartbeat",
)
def worker_heartbeat(self) -> dict:
    ts = datetime.now(timezone.utc).isoformat()
    return {"ok": True, "ts": ts}


@celery_app.task(
    bind=True,
    max_retries=0,
    name="app.tasks.maintenance.retry_failed_previews",
)
def retry_failed_previews(self, limit: int = 50) -> dict:
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session

    from app.config import get_settings
    from app.models.draft import Draft
    from app.tasks.preview import generate_drawdown_preview

    settings = get_settings()
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=10)
    retried = 0

    engine = create_engine(settings.database_url_sync)
    try:
        with Session(engine) as db:
            drafts = db.scalars(
                select(Draft)
                .where(
                    Draft.wif_path.isnot(None),
                    Draft.drawdown_preview_path.is_(None),
                    Draft.deleted_at.is_(None),
                    Draft.created_at < cutoff,
                )
                .limit(limit)
            ).all()
            for draft in drafts:
                generate_drawdown_preview.delay(str(draft.id))
                retried += 1
    finally:
        engine.dispose()
    log.info("retry_failed_previews retried=%d limit=%d", retried, limit)
    return {"retried": retried}
