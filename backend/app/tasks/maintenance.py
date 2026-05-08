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


@celery_app.task(
    bind=True,
    max_retries=0,
    name="app.tasks.maintenance.daily_health_check",
)
def daily_health_check(self) -> dict:
    import asyncio

    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from app.config import get_settings
    from app.models.server_event import ServerEvent
    from app.version import VERSION

    settings = get_settings()
    ts = datetime.now(timezone.utc)

    async def _run():
        from app.database import AsyncSessionLocal
        from app.routers.admin import _probe_clerk, _probe_postgres, _probe_s3, _probe_smtp
        from app.routers.health import ReadinessResponse, ReadinessService, _build_readiness_from_results
        from app.services.clerk_webhook_probe import run_webhook_probe

        try:
            async with AsyncSessionLocal() as db:
                results, webhook_result = await asyncio.gather(
                    asyncio.gather(
                        _probe_postgres(db),
                        _probe_s3(),
                        _probe_clerk(),
                        _probe_smtp(),
                        return_exceptions=True,
                    ),
                    run_webhook_probe(),
                )
        except Exception as exc:
            return ReadinessResponse(
                status="error",
                services=[ReadinessService(name="postgres", ok=False, critical=True, message=str(exc)[:120])],
                checked_at=ts.isoformat(),
            )
        return _build_readiness_from_results(results, webhook_result, checked_at=ts.isoformat())

    result = asyncio.run(_run())
    probe_rows = [(s.name, s.ok, s.detail) for s in result.services]
    failed = [s.name for s in result.services if not s.ok]
    sev = "error" if result.status == "error" else ("warn" if result.status == "degraded" else "info")

    engine = create_engine(settings.database_url_sync)
    try:
        with Session(engine) as db:
            evt = ServerEvent(
                event_type="health.check",
                severity=sev,
                status="closed",
                started_at=ts,
                ended_at=datetime.now(timezone.utc),
                app_version=VERSION,
                message=f"Daily health check — {result.status}",
                details={"probe_status": result.status, "failed_services": failed},
            )
            evt.elapsed_ms = int((evt.ended_at - evt.started_at).total_seconds() * 1000)
            db.add(evt)
            db.commit()
    finally:
        engine.dispose()

    if result.status != "ok":
        try:
            from sqlalchemy import select

            email_engine = create_engine(settings.database_url_sync)
            try:
                with Session(email_engine) as db:
                    from app.models.user import User

                    emails = [
                        r
                        for r in db.scalars(
                            select(User.email).where(User.is_superuser.is_(True), User.is_active.is_(True))
                        ).all()
                        if r
                    ]
            finally:
                email_engine.dispose()
            if emails:
                import asyncio as _asyncio

                from app.services.email import send_health_degraded_alert

                _asyncio.run(
                    send_health_degraded_alert(
                        superuser_emails=emails,
                        env=settings.app_env,
                        app_base_url=settings.app_base_url or settings.frontend_url,
                        version=VERSION,
                        probe_rows=probe_rows,
                        status=result.status,
                        timestamp=ts.isoformat(),
                    )
                )
        except Exception:
            log.exception("daily_health_check: failed to send degraded alert email")

    log.info("daily_health_check status=%s failed=%s", result.status, failed)
    return {"status": result.status, "failed_services": failed}


@celery_app.task(
    bind=True,
    max_retries=0,
    name="app.tasks.maintenance.prune_server_event_log",
)
def prune_server_event_log(self, max_age_days: int = 28, max_entries: int = 1000) -> dict:
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import Session

    from app.config import get_settings

    settings = get_settings()
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)
    deleted_age = 0
    deleted_overflow = 0

    engine = create_engine(settings.database_url_sync)
    try:
        with Session(engine) as db:
            result = db.execute(
                text("DELETE FROM server_events WHERE started_at < :cutoff"),
                {"cutoff": cutoff},
            )
            db.commit()
            deleted_age = result.rowcount

            count_result = db.execute(text("SELECT COUNT(*) FROM server_events"))
            total = count_result.scalar() or 0
            if total > max_entries:
                overflow = total - max_entries
                result2 = db.execute(
                    text(
                        "DELETE FROM server_events WHERE id IN ("
                        "  SELECT id FROM server_events ORDER BY started_at ASC LIMIT :overflow"
                        ")"
                    ),
                    {"overflow": overflow},
                )
                db.commit()
                deleted_overflow = result2.rowcount
    finally:
        engine.dispose()

    log.info(
        "prune_server_event_log deleted_age=%d deleted_overflow=%d max_age_days=%d max_entries=%d",
        deleted_age,
        deleted_overflow,
        max_age_days,
        max_entries,
    )
    return {"deleted_age": deleted_age, "deleted_overflow": deleted_overflow}
