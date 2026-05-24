import asyncio
import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.logging_config import configure_logging
from app.middleware import SecurityHeadersMiddleware
from app.version import VERSION

# Configure logging before router imports — routers pull in celery_app which
# calls configure_telemetry(), and that confirmation log would be silently
# dropped if no handlers are set up yet.
settings = get_settings()
configure_logging(settings.log_level)

from app.routers import (  # noqa: E402
    admin,
    auth,
    collections,
    dev,
    drafts,
    feedback,
    health,
    logs,
    loom_catalog,
    looms,
    projects,
    ravelry,
    system,
    users,
    webhooks,
    yarn,
)
from app.telemetry import configure_telemetry  # noqa: E402

configure_telemetry(settings)
log = logging.getLogger(__name__)

start_time: datetime = datetime.now(timezone.utc)


async def _get_superuser_emails() -> list[str]:
    from sqlalchemy import select

    from app.database import AsyncSessionLocal
    from app.models.user import User

    async with AsyncSessionLocal() as db:
        rows = await db.scalars(select(User).where(User.is_superuser.is_(True), User.deleted_at.is_(None)))
        return [u.email for u in rows.all()]


async def _get_worker_version_for_alert() -> str | None:
    try:
        import redis.asyncio as aioredis

        from app.celery_app import WORKER_VERSION_KEY

        client = aioredis.from_url(settings.redis_url, socket_connect_timeout=2)
        val = await client.get(WORKER_VERSION_KEY)
        await client.aclose()
        return val.decode() if val else None
    except Exception:
        return None


async def _send_startup_alert(readiness) -> None:
    if not settings.stack_alert_emails_enabled:
        return
    try:
        from app.services.email import send_stack_startup_alert

        emails = await _get_superuser_emails()
        if not emails:
            return
        worker_version = await _get_worker_version_for_alert()
        probe_rows = [(s.name, s.ok, s.detail) for s in readiness.services]
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        base_url = settings.app_base_url or settings.frontend_url
        await send_stack_startup_alert(
            superuser_emails=emails,
            env=settings.app_env,
            app_base_url=base_url,
            version=VERSION,
            worker_version=worker_version,
            probe_status=readiness.status,
            probe_rows=probe_rows,
            timestamp=ts,
        )
    except Exception:
        log.exception("Failed to send startup alert email")


async def _send_shutdown_alert() -> None:
    if not settings.stack_alert_emails_enabled:
        return
    try:
        from app.services.email import send_stack_shutdown_alert

        emails = await _get_superuser_emails()
        if not emails:
            return
        uptime = (datetime.now(timezone.utc) - start_time).total_seconds()
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        base_url = settings.app_base_url or settings.frontend_url
        await send_stack_shutdown_alert(
            superuser_emails=emails,
            env=settings.app_env,
            app_base_url=base_url,
            version=VERSION,
            uptime_seconds=uptime,
            timestamp=ts,
        )
    except Exception:
        log.exception("Failed to send shutdown alert email")


async def _write_startup_server_event(readiness, boot_started_at: datetime) -> None:
    try:
        from app.database import AsyncSessionLocal
        from app.models.server_event import ServerEvent
        from app.services.server_events import ET_STARTUP, SEV_ERROR, SEV_INFO, SEV_WARN, close_open_events
        from app.version import VERSION as _VERSION

        async with AsyncSessionLocal() as db:
            await close_open_events(db, event_types=[ET_STARTUP])
            now = datetime.now(timezone.utc)
            elapsed_ms = int((now - boot_started_at).total_seconds() * 1000)
            sev = SEV_INFO if readiness.status == "ok" else (SEV_ERROR if readiness.status == "error" else SEV_WARN)
            failed = [s.name for s in readiness.services if not s.ok]
            evt = ServerEvent(
                event_type=ET_STARTUP,
                severity=sev,
                status="closed",
                started_at=boot_started_at,
                ended_at=now,
                elapsed_ms=elapsed_ms,
                app_version=_VERSION,
                message=f"Started — probe status: {readiness.status}",
                details={"probe_status": readiness.status, "failed_services": failed},
            )
            db.add(evt)
            await db.commit()
    except Exception:
        log.exception("Failed to write startup server event")


async def _write_shutdown_server_event() -> None:
    try:
        from app.database import AsyncSessionLocal
        from app.models.server_event import ServerEvent
        from app.services.server_events import ET_SHUTDOWN, SEV_INFO
        from app.version import VERSION as _VERSION

        now = datetime.now(timezone.utc)
        uptime_ms = int((now - start_time).total_seconds() * 1000)
        async with AsyncSessionLocal() as db:
            evt = ServerEvent(
                event_type=ET_SHUTDOWN,
                severity=SEV_INFO,
                status="closed",
                started_at=now,
                ended_at=now,
                elapsed_ms=uptime_ms,
                app_version=_VERSION,
                message=f"Stopped — {uptime_ms // 1000}s uptime",
                details={"uptime_ms": uptime_ms},
            )
            db.add(evt)
            await db.commit()
    except Exception:
        log.exception("Failed to write shutdown server event")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    global start_time
    start_time = datetime.now(timezone.utc)

    from app.routers.health import run_startup_probes, set_readiness, start_detailed_refresh, stop_detailed_refresh

    readiness = await run_startup_probes()
    set_readiness(readiness)
    start_detailed_refresh(initial_status=readiness.status)
    asyncio.create_task(_send_startup_alert(readiness))
    asyncio.create_task(_write_startup_server_event(readiness, start_time))

    from app.routers.yarn import refresh_yarn_properties_loop, warm_yarn_properties_cache

    asyncio.create_task(warm_yarn_properties_cache())
    asyncio.create_task(refresh_yarn_properties_loop())

    if settings.config_encryption_key:
        from app.services.config_file import sync_env_to_file

        try:
            await asyncio.to_thread(sync_env_to_file, settings.config_file_path, settings.config_encryption_key)
        except Exception:
            log.warning("config_file_env_sync_failed — continuing without sync")

    yield

    stop_detailed_refresh()
    try:
        await asyncio.wait_for(
            asyncio.gather(_send_shutdown_alert(), _write_shutdown_server_event(), return_exceptions=True),
            timeout=5.0,
        )
    except Exception:
        pass


app = FastAPI(
    title="WeftMark API",
    version=VERSION,
    lifespan=lifespan,
    docs_url="/api/docs" if settings.debug else None,
    redoc_url="/api/redoc" if settings.debug else None,
    openapi_url="/api/openapi.json" if settings.debug else None,
)

if settings.otel_exporter_otlp_endpoint:
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    FastAPIInstrumentor().instrument_app(app, excluded_urls="health,auth/clerk/webhook")

app.add_middleware(SecurityHeadersMiddleware, production=settings.app_env == "production")
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(system.router)
app.include_router(logs.router)
if settings.app_env == "dev":
    app.include_router(dev.router)
app.include_router(auth.router)
app.include_router(webhooks.router)
app.include_router(users.eula_router)
app.include_router(users.router)
app.include_router(drafts.router)
app.include_router(loom_catalog.public_router)
app.include_router(loom_catalog.admin_catalog_router)
app.include_router(looms.router)
app.include_router(yarn.router)
app.include_router(ravelry.router)
app.include_router(collections.router)
app.include_router(projects.router)
app.include_router(projects.share_router)
app.include_router(feedback.router)
app.include_router(feedback.admin_router)
app.include_router(admin.router)
