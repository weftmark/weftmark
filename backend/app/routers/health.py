from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.celery_app import WORKER_VERSION_KEY
from app.config import get_settings
from app.version import VERSION

router = APIRouter(tags=["health"])
log = logging.getLogger(__name__)

DETAILED_REFRESH_INTERVAL_S = 30


class ReadinessService(BaseModel):
    name: str
    ok: bool
    critical: bool
    message: str = ""
    detail: str = ""


class ReadinessResponse(BaseModel):
    status: Literal["ok", "degraded", "error"]
    services: list[ReadinessService]
    checked_at: str | None = None


_readiness_cache: ReadinessResponse | None = None  # startup snapshot, never refreshed
_detailed_cache: ReadinessResponse | None = None  # live, refreshed every 30 s
_detailed_task: asyncio.Task | None = None

# Health-alert state — tracks transitions to avoid flooding
_last_alert_status: str | None = None
_last_alert_at: datetime | None = None
_HEALTH_ALERT_COOLDOWN_S = 3600  # re-alert at most once per hour if status stays bad

# Superuser email cache — refreshed when DB is healthy; used as fallback when DB is down
_superuser_email_cache: list[str] = []
_open_health_event_id: int | None = None


def set_readiness(result: ReadinessResponse) -> None:
    global _readiness_cache
    _readiness_cache = result


async def _get_worker_version() -> str | None:
    try:
        import redis.asyncio as aioredis

        settings = get_settings()
        client = aioredis.from_url(settings.redis_url, socket_connect_timeout=2)
        value = await client.get(WORKER_VERSION_KEY)
        await client.aclose()
        return value.decode() if value else None
    except Exception:
        return None


@router.get("/health")
async def health() -> dict:
    worker_version = await _get_worker_version()
    return {"status": "ok", "version": VERSION, "worker_version": worker_version}


@router.get("/health/ready")
async def readiness() -> JSONResponse:
    if _readiness_cache is None:
        return JSONResponse({"status": "starting", "services": []}, status_code=503)
    status_code = 503 if _readiness_cache.status == "error" else 200
    return JSONResponse(_readiness_cache.model_dump(), status_code=status_code)


@router.get("/health/detailed")
async def health_detailed() -> JSONResponse:
    """Live service health — refreshed every 30 s by a background task.

    Covers PostgreSQL, S3, Clerk API, SMTP, and the Clerk webhook round-trip.
    Returns the same shape as /health/ready with an added checked_at timestamp.
    """
    if _detailed_cache is None:
        return JSONResponse({"status": "starting", "services": [], "checked_at": None}, status_code=503)
    return JSONResponse(_detailed_cache.model_dump())


# ---------------------------------------------------------------------------
# Shared probe result processing
# ---------------------------------------------------------------------------


def _build_readiness_from_results(
    results: list,
    webhook_result,
    checked_at: str,
) -> ReadinessResponse:
    critical_names = {"PostgreSQL", "Clerk"}
    services: list[ReadinessService] = []
    has_hard_failure = False
    has_soft_failure = False

    for result in results:
        if isinstance(result, BaseException):
            services.append(ReadinessService(name="unknown", ok=False, critical=True, message=str(result)[:120]))
            has_hard_failure = True
            continue

        critical = result.service in critical_names
        ok = result.status == "ok"

        detail = ""
        if not ok:
            failed_check = next((c for c in result.checks if c.status == "error"), None)
            if failed_check:
                detail = failed_check.message[:120]

        services.append(
            ReadinessService(name=result.service, ok=ok, critical=critical, message=result.message, detail=detail)
        )
        if not ok:
            if critical:
                has_hard_failure = True
            else:
                has_soft_failure = True

    if webhook_result is not None:
        webhook_ok = webhook_result.status in ("ok", "skipped")
        services.append(
            ReadinessService(
                name="Clerk Webhook",
                ok=webhook_ok,
                critical=False,
                message=webhook_result.message,
            )
        )
        if not webhook_ok:
            has_soft_failure = True

    if has_hard_failure:
        status: Literal["ok", "degraded", "error"] = "error"
    elif has_soft_failure:
        status = "degraded"
    else:
        status = "ok"

    return ReadinessResponse(status=status, services=services, checked_at=checked_at)


# ---------------------------------------------------------------------------
# Startup probes (called once at boot, no webhook)
# ---------------------------------------------------------------------------


async def run_startup_probes() -> ReadinessResponse:
    """Run service probes concurrently and return a ReadinessResponse.

    Covers PostgreSQL, S3, Clerk API, and SMTP — services that gate startup.
    Webhook round-trip health is checked separately via /health/detailed.
    """
    from app.database import AsyncSessionLocal
    from app.routers.admin import _probe_clerk, _probe_postgres, _probe_s3, _probe_smtp

    try:
        async with AsyncSessionLocal() as db:
            results = await asyncio.gather(
                _probe_postgres(db),
                _probe_s3(),
                _probe_clerk(),
                _probe_smtp(),
                return_exceptions=True,
            )
    except Exception as exc:
        return ReadinessResponse(
            status="error",
            services=[ReadinessService(name="postgres", ok=False, critical=True, message=str(exc)[:120])],
        )

    return _build_readiness_from_results(
        results, webhook_result=None, checked_at=datetime.now(timezone.utc).isoformat()
    )


# ---------------------------------------------------------------------------
# Detailed live probes (called on background schedule, includes webhook)
# ---------------------------------------------------------------------------


async def _run_detailed_probes() -> ReadinessResponse:
    """Run all 5 probes and return a ReadinessResponse with a fresh checked_at."""
    from app.database import AsyncSessionLocal
    from app.routers.admin import _probe_clerk, _probe_postgres, _probe_s3, _probe_smtp
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
            checked_at=datetime.now(timezone.utc).isoformat(),
        )

    return _build_readiness_from_results(results, webhook_result, checked_at=datetime.now(timezone.utc).isoformat())


async def _refresh_superuser_email_cache() -> None:
    """Refresh the in-memory superuser email list from the DB. Silent on failure."""
    global _superuser_email_cache
    try:
        from sqlalchemy import select

        from app.database import AsyncSessionLocal
        from app.models.user import User

        async with AsyncSessionLocal() as db:
            rows = await db.scalars(select(User).where(User.is_superuser.is_(True), User.deleted_at.is_(None)))
            _superuser_email_cache = [u.email for u in rows.all()]
    except Exception:
        pass  # keep stale cache; logged by caller if needed


async def _dispatch_health_alert(result: ReadinessResponse, is_recovery: bool) -> None:
    settings = get_settings()
    if not settings.stack_alert_emails_enabled:
        return
    try:
        from app.services.email import send_health_degraded_alert, send_health_recovered_alert

        emails = _superuser_email_cache
        if not emails:
            return
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        base_url = settings.app_base_url or settings.frontend_url
        if is_recovery:
            await send_health_recovered_alert(
                superuser_emails=emails,
                env=settings.app_env,
                app_base_url=base_url,
                version=VERSION,
                timestamp=ts,
            )
        else:
            probe_rows = [(s.name, s.ok, s.detail) for s in result.services]
            await send_health_degraded_alert(
                superuser_emails=emails,
                env=settings.app_env,
                app_base_url=base_url,
                version=VERSION,
                probe_rows=probe_rows,
                status=result.status,
                timestamp=ts,
            )
    except Exception:
        log.exception("Failed to send health alert email")


async def _record_health_transition(prev_status: str | None, result: ReadinessResponse) -> None:
    """Write or close a ServerEvent row to capture health status transitions.

    Silently skips on any DB error — the events log is best-effort.
    """
    global _open_health_event_id
    new_status = result.status
    if prev_status == new_status:
        return
    try:
        from app.database import AsyncSessionLocal
        from app.services.server_events import (
            ET_HEALTH_DEGRADED,
            ET_HEALTH_ERROR,
            SEV_ERROR,
            SEV_WARN,
            STATUS_OPEN,
            close_event,
            write_event,
        )

        async with AsyncSessionLocal() as db:
            # Close any open health event when recovering
            if new_status == "ok" and _open_health_event_id is not None:
                from sqlalchemy import select

                from app.models.server_event import ServerEvent

                evt = await db.scalar(select(ServerEvent).where(ServerEvent.id == _open_health_event_id))
                if evt and evt.status == STATUS_OPEN:
                    await close_event(db, evt)
                    await db.commit()
                _open_health_event_id = None
                return

            # Open a new event when health goes bad
            if new_status in ("degraded", "error"):
                failed = [s.name for s in result.services if not s.ok]
                et = ET_HEALTH_ERROR if new_status == "error" else ET_HEALTH_DEGRADED
                sev = SEV_ERROR if new_status == "error" else SEV_WARN
                evt = await write_event(
                    db,
                    event_type=et,
                    severity=sev,
                    message=f"Services failing: {', '.join(failed)}" if failed else "Health probe failure",
                    details={"failed_services": failed, "probe_status": new_status},
                )
                await db.commit()
                await db.refresh(evt)
                _open_health_event_id = evt.id
    except Exception:
        log.debug("Could not record health transition event", exc_info=True)


async def _detailed_refresh_loop() -> None:
    global _detailed_cache, _last_alert_status, _last_alert_at
    while True:
        try:
            result = await _run_detailed_probes()
            # Keep superuser email cache fresh while DB is reachable
            postgres_ok = any(s.name == "PostgreSQL" and s.ok for s in result.services)
            if postgres_ok:
                await _refresh_superuser_email_cache()
            await _record_health_transition(_last_alert_status, result)
            new_status = result.status
            now = datetime.now(timezone.utc)
            prev_status = _last_alert_status

            if prev_status is None:
                # First detailed cycle — startup alert already covered initial state
                _last_alert_status = new_status
                if new_status != "ok":
                    _last_alert_at = now
            else:
                should_alert = False
                is_recovery = False

                if new_status in ("degraded", "error"):
                    if prev_status == "ok":
                        should_alert = True
                    elif prev_status != new_status:
                        # degraded ↔ error transition
                        should_alert = True
                    elif _last_alert_at and (now - _last_alert_at).total_seconds() >= _HEALTH_ALERT_COOLDOWN_S:
                        # Same bad state for >1 h — re-alert
                        should_alert = True
                elif new_status == "ok" and prev_status in ("degraded", "error"):
                    should_alert = True
                    is_recovery = True

                if should_alert:
                    asyncio.create_task(_dispatch_health_alert(result, is_recovery))
                    _last_alert_status = new_status
                    _last_alert_at = now if new_status != "ok" else None
                else:
                    _last_alert_status = new_status

            _detailed_cache = result
        except Exception:
            log.exception("Unexpected error in detailed health refresh loop")
        await asyncio.sleep(DETAILED_REFRESH_INTERVAL_S)


def start_detailed_refresh() -> None:
    """Create the background refresh task. Call from lifespan after startup."""
    global _detailed_task
    _detailed_task = asyncio.create_task(_detailed_refresh_loop())


def stop_detailed_refresh() -> None:
    """Cancel the background refresh task. Call from lifespan cleanup."""
    global _detailed_task
    if _detailed_task is not None:
        _detailed_task.cancel()
        _detailed_task = None
