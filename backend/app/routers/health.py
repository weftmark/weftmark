from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

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


def set_readiness(result: ReadinessResponse) -> None:
    global _readiness_cache
    _readiness_cache = result


@router.get("/health")
async def health() -> dict:
    return {"status": "ok", "version": VERSION}


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
        return JSONResponse(
            {"status": "starting", "services": [], "checked_at": None}, status_code=503
        )
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

    return _build_readiness_from_results(
        results, webhook_result, checked_at=datetime.now(timezone.utc).isoformat()
    )


async def _detailed_refresh_loop() -> None:
    global _detailed_cache
    while True:
        try:
            _detailed_cache = await _run_detailed_probes()
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
