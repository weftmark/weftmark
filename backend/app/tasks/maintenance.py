"""Celery tasks: scheduled maintenance operations.

Covers:
- dismiss_stale_signups                 — auto-dismiss pending signups older than N days
- prune_expired_invites                 — delete old non-active invite records
- prune_audit_log                       — delete old audit log entries (security events exempt)
- worker_heartbeat                      — no-op liveness signal
- retry_failed_previews                 — re-dispatch preview generation for drafts missing drawdown previews
- send_admin_digest                     — weekly digest email to all active admins
- backfill_project_drawdown_previews    — dispatch preview generation for active-project drafts missing tiles
- prune_inactive_project_tiles          — delete cached tiles for inactive or soft-deleted projects
- expire_project_slugs                  — revoke share slugs whose share_expires_at has passed
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
            dismissed = result.rowcount  # type: ignore[attr-defined]
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
            pruned = result.rowcount  # type: ignore[attr-defined]
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
                deleted = result.rowcount  # type: ignore[attr-defined]
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
            evt.elapsed_ms = int((evt.ended_at - evt.started_at).total_seconds() * 1000)  # type: ignore[operator]
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
            deleted_age = result.rowcount  # type: ignore[attr-defined]

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
                deleted_overflow = result2.rowcount  # type: ignore[attr-defined]
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


@celery_app.task(
    bind=True,
    max_retries=0,
    name="app.tasks.maintenance.check_credential_expiry",
)
def check_credential_expiry(self) -> dict:
    import asyncio

    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session

    from app.config import get_settings
    from app.models.credential_expiry import CredentialExpiry
    from app.models.user import User

    settings = get_settings()
    today = datetime.now(timezone.utc).date()
    now = datetime.now(timezone.utc)
    alerted = 0
    skipped = 0

    engine = create_engine(settings.database_url_sync)
    try:
        with Session(engine) as db:
            credentials = db.scalars(select(CredentialExpiry).where(CredentialExpiry.expires_on.isnot(None))).all()

            superuser_emails = [
                r
                for r in db.scalars(
                    select(User.email).where(User.is_superuser.is_(True), User.is_active.is_(True))
                ).all()
                if r
            ]
            admin_emails = [
                r
                for r in db.scalars(
                    select(User.email).where(
                        User.is_admin.is_(True),
                        User.is_superuser.is_(False),
                        User.is_active.is_(True),
                    )
                ).all()
                if r
            ]

            for cred in credentials:
                days_remaining = (cred.expires_on - today).days  # type: ignore[operator]

                if days_remaining > 30:
                    skipped += 1
                    continue

                # Determine required send interval
                if days_remaining <= 7:
                    interval_hours = 24
                else:
                    interval_hours = 24 * 7

                if cred.last_alerted_at is not None:
                    elapsed_hours = (now - cred.last_alerted_at).total_seconds() / 3600
                    if elapsed_hours < interval_hours:
                        skipped += 1
                        continue

                expires_on_str = cred.expires_on.strftime("%B %d, %Y")  # type: ignore[union-attr]
                display_days = max(days_remaining, 0)

                try:
                    import concurrent.futures

                    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                        pool.submit(
                            asyncio.run,
                            _send_credential_alerts(
                                superuser_emails=superuser_emails,
                                admin_emails=admin_emails,
                                credential_name=cred.name,
                                resource=cred.resource,
                                days_remaining=display_days,
                                expires_on=expires_on_str,
                            ),
                        ).result()
                    cred.last_alerted_at = now
                    alerted += 1
                except Exception:
                    log.exception("check_credential_expiry: failed to send alerts for credential id=%s", cred.id)
            db.commit()
    finally:
        engine.dispose()

    log.info("check_credential_expiry alerted=%d skipped=%d", alerted, skipped)
    return {"alerted": alerted, "skipped": skipped}


async def _send_credential_alerts(
    superuser_emails: list[str],
    admin_emails: list[str],
    credential_name: str,
    resource: str,
    days_remaining: int,
    expires_on: str,
) -> None:
    from app.services.email import send_credential_expiring_admin, send_credential_expiring_superuser

    await send_credential_expiring_superuser(
        superuser_emails=superuser_emails,
        credential_name=credential_name,
        resource=resource,
        days_remaining=days_remaining,
        expires_on=expires_on,
    )
    await send_credential_expiring_admin(
        admin_emails=admin_emails,
        credential_name=credential_name,
        resource=resource,
        days_remaining=days_remaining,
        expires_on=expires_on,
    )


DIGEST_STATE_KEY = "weftmark:admin_digest:last_sent"


def _fmt_bytes(b: int) -> str:
    if b >= 1_073_741_824:
        return f"{b / 1_073_741_824:.1f} GB"
    if b >= 1_048_576:
        return f"{b / 1_048_576:.1f} MB"
    if b >= 1024:
        return f"{b / 1024:.1f} KB"
    return f"{b} B"


def _fmt_delta(b: int) -> str:
    sign = "+" if b >= 0 else "-"
    return f"{sign}{_fmt_bytes(abs(b))}"


@celery_app.task(
    bind=True,
    max_retries=0,
    name="app.tasks.maintenance.send_admin_digest",
)
def send_admin_digest(self) -> dict:
    import asyncio
    import concurrent.futures
    import json

    from sqlalchemy import create_engine, func, select
    from sqlalchemy.orm import Session

    from app.config import get_settings
    from app.models.draft import Draft
    from app.models.loom import Loom, LoomVersionPhoto
    from app.models.pending_signup import PendingSignup
    from app.models.project import Project, ProjectPhoto
    from app.models.user import User

    settings = get_settings()
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=7)

    engine = create_engine(settings.database_url_sync)
    try:
        with Session(engine) as db:
            admin_emails = [
                r
                for r in db.scalars(
                    select(User.email).where(
                        User.is_admin.is_(True),
                        User.is_active.is_(True),
                        User.deleted_at.is_(None),
                    )
                ).all()
                if r
            ]

            if not admin_emails:
                return {"sent": 0}

            new_users = (
                db.scalar(
                    select(func.count()).select_from(User).where(User.deleted_at.is_(None), User.created_at >= cutoff)
                )
                or 0
            )

            pending_signups = db.scalar(select(func.count()).select_from(PendingSignup)) or 0

            new_drafts = (
                db.scalar(
                    select(func.count())
                    .select_from(Draft)
                    .where(Draft.deleted_at.is_(None), Draft.created_at >= cutoff)
                )
                or 0
            )

            new_projects = (
                db.scalar(
                    select(func.count())
                    .select_from(Project)
                    .where(Project.deleted_at.is_(None), Project.created_at >= cutoff)
                )
                or 0
            )

            new_looms = (
                db.scalar(
                    select(func.count()).select_from(Loom).where(Loom.deleted_at.is_(None), Loom.created_at >= cutoff)
                )
                or 0
            )

            project_storage = db.scalar(select(func.coalesce(func.sum(ProjectPhoto.file_size_bytes), 0))) or 0
            loom_storage = db.scalar(select(func.coalesce(func.sum(LoomVersionPhoto.file_size_bytes), 0))) or 0
            total_storage_bytes = int(project_storage) + int(loom_storage)
    finally:
        engine.dispose()

    cve_finding_count: int | None = None
    cve_scanned_at: str | None = None
    s3_orphaned_count: int | None = None
    s3_scanned_at: str | None = None
    storage_delta_bytes: int | None = None

    try:
        import redis as _redis

        from app.tasks.cve_scan import CVE_SUMMARY_KEY
        from app.tasks.s3_audit import S3_AUDIT_SUMMARY_KEY

        client = _redis.from_url(settings.redis_url, socket_connect_timeout=2)

        raw_cve = client.get(CVE_SUMMARY_KEY)
        if raw_cve:
            data = json.loads(raw_cve)
            cve_finding_count = data.get("finding_count")
            cve_scanned_at = data.get("scanned_at")

        raw_s3 = client.get(S3_AUDIT_SUMMARY_KEY)
        if raw_s3:
            data = json.loads(raw_s3)
            if not data.get("not_applicable"):
                s3_orphaned_count = data.get("orphaned_count")
                s3_scanned_at = data.get("scanned_at")

        raw_last = client.get(DIGEST_STATE_KEY)
        if raw_last:
            prev = json.loads(raw_last)
            prev_bytes = prev.get("storage_bytes")
            if prev_bytes is not None:
                storage_delta_bytes = total_storage_bytes - int(prev_bytes)

        client.set(
            DIGEST_STATE_KEY,
            json.dumps({"sent_at": now.isoformat(), "storage_bytes": total_storage_bytes}),
        )
        client.close()
    except Exception:
        log.warning("send_admin_digest: Redis state read/write failed", exc_info=True)

    week_start = (now - timedelta(days=7)).strftime("%b %d, %Y")
    week_end = now.strftime("%b %d, %Y")
    storage_str = _fmt_bytes(total_storage_bytes)
    storage_delta_str = _fmt_delta(storage_delta_bytes) if storage_delta_bytes is not None else None

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        pool.submit(
            asyncio.run,
            _send_admin_digest_email(
                admin_emails=admin_emails,
                week_start=week_start,
                week_end=week_end,
                new_users=new_users,
                pending_signups=pending_signups,
                new_drafts=new_drafts,
                new_projects=new_projects,
                new_looms=new_looms,
                storage_str=storage_str,
                storage_delta_str=storage_delta_str,
                cve_finding_count=cve_finding_count,
                cve_scanned_at=cve_scanned_at,
                s3_orphaned_count=s3_orphaned_count,
                s3_scanned_at=s3_scanned_at,
            ),
        ).result()

    log.info("send_admin_digest sent=%d", len(admin_emails))
    return {"sent": len(admin_emails)}


async def _send_admin_digest_email(
    admin_emails: list[str],
    week_start: str,
    week_end: str,
    new_users: int,
    pending_signups: int,
    new_drafts: int,
    new_projects: int,
    new_looms: int,
    storage_str: str,
    storage_delta_str: str | None,
    cve_finding_count: int | None,
    cve_scanned_at: str | None,
    s3_orphaned_count: int | None,
    s3_scanned_at: str | None,
) -> None:
    from app.services.email import send_admin_digest_email as _send

    await _send(
        admin_emails=admin_emails,
        week_start=week_start,
        week_end=week_end,
        new_users=new_users,
        pending_signups=pending_signups,
        new_drafts=new_drafts,
        new_projects=new_projects,
        new_looms=new_looms,
        storage_str=storage_str,
        storage_delta_str=storage_delta_str,
        cve_finding_count=cve_finding_count,
        cve_scanned_at=cve_scanned_at,
        s3_orphaned_count=s3_orphaned_count,
        s3_scanned_at=s3_scanned_at,
    )


@celery_app.task(
    bind=True,
    max_retries=0,
    name="app.tasks.maintenance.backfill_project_drawdown_previews",
)
def backfill_project_drawdown_previews(self, limit: int = 50) -> dict:
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session

    from app.config import get_settings
    from app.models.draft import Draft
    from app.models.project import Project
    from app.tasks.preview import generate_drawdown_preview

    settings = get_settings()
    engine = create_engine(settings.database_url_sync)
    dispatched = 0
    try:
        with Session(engine) as db:
            draft_ids = db.scalars(
                select(Project.draft_id)
                .join(Draft, Draft.id == Project.draft_id)
                .where(
                    Project.status == "active",
                    Project.deleted_at.is_(None),
                    Draft.drawdown_preview_path.is_(None),
                    Draft.deleted_at.is_(None),
                )
                .distinct()
                .limit(limit)
            ).all()
            for draft_id in draft_ids:
                generate_drawdown_preview.delay(str(draft_id))
                dispatched += 1
    finally:
        engine.dispose()
    log.info("backfill_project_drawdown_previews dispatched=%d limit=%d", dispatched, limit)
    return {"dispatched": dispatched}


@celery_app.task(
    bind=True,
    max_retries=0,
    name="app.tasks.maintenance.prune_inactive_project_tiles",
)
def prune_inactive_project_tiles(self, inactive_days: int = 10) -> dict:
    from sqlalchemy import create_engine, or_, select
    from sqlalchemy.orm import Session

    from app.config import get_settings
    from app.models.project import Project
    from app.services import storage

    settings = get_settings()
    cutoff = datetime.now(timezone.utc) - timedelta(days=inactive_days)
    pruned_projects = 0
    pruned_tiles = 0

    engine = create_engine(settings.database_url_sync)
    try:
        with Session(engine) as db:
            project_ids = db.scalars(
                select(Project.id).where(
                    or_(
                        Project.deleted_at.isnot(None),
                        Project.updated_at < cutoff,
                    )
                )
            ).all()
            for project_id in project_ids:
                try:
                    deleted = storage.delete_project_tiles(project_id)
                    if deleted > 0:
                        pruned_projects += 1
                        pruned_tiles += deleted
                except Exception:
                    log.exception("prune_inactive_project_tiles: error deleting tiles for project_id=%s", project_id)
    finally:
        engine.dispose()

    log.info(
        "prune_inactive_project_tiles pruned_projects=%d pruned_tiles=%d inactive_days=%d",
        pruned_projects,
        pruned_tiles,
        inactive_days,
    )
    return {"pruned_projects": pruned_projects, "pruned_tiles": pruned_tiles}


@celery_app.task(
    bind=True,
    max_retries=0,
    name="app.tasks.maintenance.expire_project_slugs",
)
def expire_project_slugs(self) -> dict:
    """Revoke share slugs whose share_expires_at has passed."""
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session

    from app.config import get_settings
    from app.models.project import Project

    settings = get_settings()
    now = datetime.now(timezone.utc)
    revoked = 0

    engine = create_engine(settings.database_url_sync)
    try:
        with Session(engine) as db:
            expired = db.scalars(
                select(Project).where(
                    Project.share_slug.isnot(None),
                    Project.share_expires_at.isnot(None),
                    Project.share_expires_at <= now,
                    Project.deleted_at.is_(None),
                )
            ).all()
            for project in expired:
                project.share_slug = None
                project.share_visibility = "private"
                project.share_expires_at = None
                revoked += 1
            db.commit()
    finally:
        engine.dispose()

    log.info("expire_project_slugs revoked=%d", revoked)
    return {"revoked": revoked}
