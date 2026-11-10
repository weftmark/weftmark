"""Ravelry OAuth and stash sync endpoints."""

import logging
import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.deps import get_current_user, get_db
from app.models.user import User
from app.services import ravelry as svc

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/ravelry", tags=["ravelry"])

_NOT_CONNECTED = "Not connected to Ravelry"


def _safe(s: str | None, maxlen: int = 100) -> str:
    """Strip newlines and truncate before logging user-supplied values."""
    if s is None:
        return ""
    return s.replace("\n", "\\n").replace("\r", "\\r")[:maxlen]


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class RavelryStatus(BaseModel):
    connected: bool
    ravelry_username: str | None = None
    last_synced_at: datetime | None = None


class SyncResult(BaseModel):
    synced: int
    unchanged: bool
    last_synced_at: datetime | None = None


class RavelryCompany(BaseModel):
    id: int
    name: str
    permalink: str


class RavelryYarnResult(BaseModel):
    id: int
    name: str
    company_name: str
    permalink: str
    weight_name: str | None = None
    photo_url: str | None = None


class ImportYarnPayload(BaseModel):
    ravelry_yarn_id: int
    color_name: str | None = None
    color_hex: str | None = None


class StashPushResult(BaseModel):
    ravelry_stash_id: int


class BulkStashPushResult(BaseModel):
    pushed: int
    skipped: int


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/authorize", responses={503: {"description": "Ravelry integration is not configured on this server"}})
async def authorize(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Return a Ravelry OAuth authorization URL for the current user."""
    settings = get_settings()
    if not settings.ravelry_oauth_client_id:
        raise HTTPException(status_code=503, detail="Ravelry integration is not configured on this server")
    _, auth_url = await svc.create_oauth_state(current_user.id, db)
    return {"url": auth_url}


@router.get("/callback")
async def oauth_callback(
    db: Annotated[AsyncSession, Depends(get_db)],
    state: Annotated[str, Query()],
    code: Annotated[str | None, Query()] = None,
    error: Annotated[str | None, Query()] = None,
    error_description: Annotated[str | None, Query()] = None,
) -> RedirectResponse:
    """Ravelry redirects here after the user approves or denies access.

    NOT protected by get_current_user — the user is identified via the state
    record created in /authorize. Handles both success and error responses.
    """
    settings = get_settings()
    frontend_url = settings.frontend_url.rstrip("/")

    if error:
        logger.warning(
            "Ravelry OAuth error for state %s: %s — %s", _safe(state), _safe(error), _safe(error_description)
        )
        await svc.consume_oauth_state(state, db)  # clean up the state record
        return RedirectResponse(url=f"{frontend_url}/settings/connections?ravelry=error&reason=ravelry_denied")

    if not code:
        logger.warning("Ravelry callback missing code and error for state: %s", _safe(state))
        await svc.consume_oauth_state(state, db)
        return RedirectResponse(url=f"{frontend_url}/settings/connections?ravelry=error&reason=missing_code")

    state_record = await svc.consume_oauth_state(state, db)
    if state_record is None:
        logger.warning("Ravelry callback received invalid or expired state: %s", _safe(state))
        return RedirectResponse(url=f"{frontend_url}/settings/connections?ravelry=error&reason=invalid_state")

    try:
        token_data = await svc.exchange_code(code)
        await svc.save_credential(state_record.user_id, token_data, db)
    except Exception:
        logger.exception("Ravelry token exchange failed for user %s", state_record.user_id)
        return RedirectResponse(url=f"{frontend_url}/settings/connections?ravelry=error&reason=token_exchange")

    return RedirectResponse(url=f"{frontend_url}/settings/connections?ravelry=connected")


@router.get("/status")
async def status(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RavelryStatus:
    cred = await svc.get_credential(current_user.id, db)
    if cred is None:
        return RavelryStatus(connected=False)
    return RavelryStatus(
        connected=True,
        ravelry_username=cred.ravelry_username,
        last_synced_at=cred.stash_last_synced_at,
    )


@router.delete("/connection", status_code=204, responses={404: {"description": "Not connected to Ravelry"}})
async def disconnect(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    """Remove stored Ravelry credentials for the current user."""
    cred = await svc.get_credential(current_user.id, db)
    if cred is None:
        raise HTTPException(status_code=404, detail=_NOT_CONNECTED)
    await db.delete(cred)
    await db.commit()


@router.get("/yarn-detail/{ravelry_yarn_id}", responses={502: {"description": "Ravelry yarn detail fetch failed"}})
async def yarn_detail(
    ravelry_yarn_id: int,
    _current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    """Proxy a single yarn's full detail from the Ravelry API (no OAuth required)."""
    try:
        data = await svc.fetch_yarn_detail(ravelry_yarn_id)
    except Exception as exc:
        logger.exception("Ravelry yarn detail fetch failed for yarn %s", ravelry_yarn_id)
        raise HTTPException(status_code=502, detail="Ravelry yarn detail fetch failed") from exc
    return data


@router.get(
    "/popular/companies",
    responses={502: {"description": "Ravelry request failed"}},
)
async def popular_companies(
    _current_user: Annotated[User, Depends(get_current_user)],
    limit: Annotated[int, Query(ge=1, le=20)] = 10,
) -> list[RavelryCompany]:
    """Return popular yarn companies (uses dev read-only key, sort=best)."""
    try:
        results = await svc.get_popular_yarn_companies(limit)
    except Exception as exc:
        logger.exception("Ravelry popular companies fetch failed")
        raise HTTPException(status_code=502, detail="Ravelry request failed") from exc
    return [RavelryCompany(**r) for r in results]


@router.get("/popular/yarns", responses={502: {"description": "Ravelry request failed"}})
async def popular_yarns(
    _current_user: Annotated[User, Depends(get_current_user)],
    company_id: Annotated[int, Query()],
    company_name: Annotated[str, Query()],
    limit: Annotated[int, Query(ge=1, le=20)] = 8,
) -> list[RavelryYarnResult]:
    """Return popular yarns for a company (uses dev read-only key, seeded by company name)."""
    try:
        results = await svc.get_popular_yarns_for_company(company_id, company_name, limit)
    except Exception as exc:
        logger.exception("Ravelry popular yarns fetch failed for company %s", company_id)
        raise HTTPException(status_code=502, detail="Ravelry request failed") from exc
    return [RavelryYarnResult(**r) for r in results]


@router.get("/search/companies", responses={502: {"description": "Ravelry search failed"}})
async def search_companies(
    _current_user: Annotated[User, Depends(get_current_user)],
    q: Annotated[str, Query(min_length=1)],
) -> list[RavelryCompany]:
    """Search Ravelry yarn companies by name (uses dev read-only key)."""
    try:
        results = await svc.search_yarn_companies(q)
    except Exception as exc:
        logger.exception("Ravelry company search failed")
        raise HTTPException(status_code=502, detail="Ravelry search failed") from exc
    return [RavelryCompany(**r) for r in results]


@router.get("/search/yarns", responses={502: {"description": "Ravelry search failed"}})
async def search_yarns(
    _current_user: Annotated[User, Depends(get_current_user)],
    q: Annotated[str, Query(min_length=1)],
    company_id: Annotated[int | None, Query()] = None,
) -> list[RavelryYarnResult]:
    """Search Ravelry yarns, optionally filtered by company (uses dev read-only key)."""
    try:
        results = await svc.search_yarns(q, company_id)
    except Exception as exc:
        logger.exception("Ravelry yarn search failed")
        raise HTTPException(status_code=502, detail="Ravelry search failed") from exc
    return [RavelryYarnResult(**r) for r in results]


@router.post(
    "/import-yarn",
    responses={404: {"description": "Yarn not found or not importable"}, 502: {"description": "Ravelry import failed"}},
)
async def import_yarn(
    payload: ImportYarnPayload,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    """Import a Ravelry yarn into the user's WeftMark inventory (uses dev read-only key)."""
    try:
        yarn = await svc.import_yarn_from_ravelry(
            current_user.id,
            payload.ravelry_yarn_id,
            payload.color_name,
            payload.color_hex,
            db,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Ravelry yarn import failed for yarn %s", payload.ravelry_yarn_id)
        raise HTTPException(status_code=502, detail="Ravelry import failed") from exc
    return {"id": str(yarn.id)}


@router.post(
    "/stash-push/bulk",
    responses={
        404: {"description": "Not connected to Ravelry"},
        502: {"description": "Ravelry bulk stash push failed"},
    },
)
async def push_bulk_to_stash(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> BulkStashPushResult:
    """Push all eligible Tier 1 yarns to the user's Ravelry stash."""
    cred = await svc.get_credential(current_user.id, db)
    if cred is None:
        raise HTTPException(status_code=404, detail=_NOT_CONNECTED)
    try:
        result = await svc.push_eligible_yarns_to_stash(current_user.id, db)
    except Exception as exc:
        logger.exception("Ravelry bulk stash push failed for user %s", current_user.id)
        raise HTTPException(status_code=502, detail="Ravelry bulk stash push failed") from exc
    return BulkStashPushResult(**result)


@router.post(
    "/stash-push/{yarn_id}",
    responses={
        404: {"description": "Yarn not found"},
        422: {"description": "Yarn cannot be pushed to Ravelry stash"},
        502: {"description": "Ravelry stash push failed"},
    },
)
async def push_yarn_to_stash(
    yarn_id: uuid.UUID,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> StashPushResult:
    """Push a single yarn to the user's Ravelry stash."""
    try:
        stash_id = await svc.push_yarn_to_stash(yarn_id, current_user.id, db)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Ravelry stash push failed for yarn %s", yarn_id)
        raise HTTPException(status_code=502, detail="Ravelry stash push failed") from exc
    return StashPushResult(ravelry_stash_id=stash_id)


@router.post(
    "/sync",
    responses={404: {"description": "Not connected to Ravelry"}, 502: {"description": "Ravelry stash sync failed"}},
)
async def sync_stash(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SyncResult:
    """Trigger an on-demand stash sync for the current user."""
    cred = await svc.get_credential(current_user.id, db)
    if cred is None:
        raise HTTPException(status_code=404, detail=_NOT_CONNECTED)
    try:
        result = await svc.sync_stash(current_user.id, db)
    except Exception as exc:
        logger.exception("Ravelry stash sync failed for user %s", current_user.id)
        raise HTTPException(status_code=502, detail="Ravelry stash sync failed") from exc
    return SyncResult(**result)
