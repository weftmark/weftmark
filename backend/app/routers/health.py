from __future__ import annotations

import asyncio
from typing import Literal

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.version import VERSION

router = APIRouter(tags=["health"])


class ReadinessService(BaseModel):
    name: str
    ok: bool
    critical: bool
    message: str = ""
    detail: str = ""


class ReadinessResponse(BaseModel):
    status: Literal["ok", "degraded", "error"]
    services: list[ReadinessService]


_readiness_cache: ReadinessResponse | None = None


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


async def run_startup_probes() -> ReadinessResponse:
    """Run service probes concurrently and return a ReadinessResponse.

    Covers PostgreSQL, S3, Clerk API, and SMTP — services that gate startup.
    Webhook round-trip health is checked separately via the admin Services tab.
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

    if has_hard_failure:
        status: Literal["ok", "degraded", "error"] = "error"
    elif has_soft_failure:
        status = "degraded"
    else:
        status = "ok"

    return ReadinessResponse(status=status, services=services)
