"""User settings, EULA acceptance, and account management.

Routes:
  GET    /api/eula/current           — current EULA version + HTML body (public)
  GET    /api/users/me/settings      — current user settings (same as /auth/me but explicit)
  PATCH  /api/users/me               — update settings
  POST   /api/users/me/eula          — accept the current EULA version
  DELETE /api/users/me               — hard-delete account + all data from DB and storage
  GET    /api/users/me/data-export   — Phase 2 stub
"""

import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_current_user, get_db
from app.models.activity import Activity, ActivityPhoto, ActivityStep
from app.models.draft import Draft
from app.models.eula_version import EulaVersion
from app.models.invite import Invite
from app.models.loom import Loom, LoomVersion, LoomVersionAccessory, LoomVersionPhoto, LoomVersionReceipt
from app.models.user import User
from app.models.user_identity import UserIdentity
from app.models.yarn import Skein, Yarn
from app.services import storage
from app.services.audit import write_audit_log

log = logging.getLogger(__name__)

eula_router = APIRouter(prefix="/api/eula", tags=["users"])

_VALID_THEMES = {"light", "dark", "system"}
_VALID_MEASUREMENT_SYSTEMS = {"metric", "imperial"}
_VALID_ACTIVITY_THEMES = {"default", "compact", "high_contrast"}
_VALID_IDLE_TIMEOUTS = {15, 30, 60, 120}

_SESSION_COOKIE = "session"


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class UserSettingsUpdate(BaseModel):
    display_name: str | None = None
    theme: str | None = None
    activity_theme: str | None = None
    idle_timeout_minutes: int | None = None
    measurement_system: str | None = None
    ai_training_consent: bool | None = None


class EulaAcceptRequest(BaseModel):
    version: str


class DeleteAccountRequest(BaseModel):
    confirm: str


class UserSettingsResponse(BaseModel):
    id: uuid.UUID
    email: str
    display_name: str
    is_admin: bool
    theme: str
    activity_theme: str | None
    idle_timeout_minutes: int
    measurement_system: str
    ai_training_consent: bool
    eula_accepted_version: str | None
    current_eula_version: str

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# EULA helpers
# ---------------------------------------------------------------------------


async def get_current_eula_version(db: AsyncSession) -> str:
    row = await db.scalar(
        select(EulaVersion).order_by(EulaVersion.effective_date.desc(), EulaVersion.id.desc()).limit(1)
    )
    return row.version if row else "0.3"


def _to_response(user: User, current_eula_version: str) -> UserSettingsResponse:
    return UserSettingsResponse(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        is_admin=user.is_admin,
        theme=user.theme,
        activity_theme=user.activity_theme,
        idle_timeout_minutes=user.idle_timeout_minutes,
        measurement_system=user.measurement_system,
        ai_training_consent=user.ai_training_consent,
        eula_accepted_version=user.eula_accepted_version,
        current_eula_version=current_eula_version,
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


class EulaCurrentResponse(BaseModel):
    version: str
    body_html: str
    effective_date: datetime


@eula_router.get("/current", response_model=EulaCurrentResponse)
async def get_current_eula(db: AsyncSession = Depends(get_db)) -> EulaCurrentResponse:
    row = await db.scalar(
        select(EulaVersion).order_by(EulaVersion.effective_date.desc(), EulaVersion.id.desc()).limit(1)
    )
    if not row:
        raise HTTPException(status_code=404, detail="No EULA version found")
    return EulaCurrentResponse(version=row.version, body_html=row.body_html, effective_date=row.effective_date)


router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("/me", response_model=UserSettingsResponse)
async def get_settings(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserSettingsResponse:
    version = await get_current_eula_version(db)
    return _to_response(current_user, version)


@router.patch("/me", response_model=UserSettingsResponse)
async def update_settings(
    body: UserSettingsUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserSettingsResponse:
    if body.display_name is not None:
        name = body.display_name.strip()
        if not name:
            raise HTTPException(status_code=422, detail="display_name cannot be empty")
        current_user.display_name = name

    if body.theme is not None:
        if body.theme not in _VALID_THEMES:
            raise HTTPException(status_code=422, detail=f"theme must be one of {sorted(_VALID_THEMES)}")
        current_user.theme = body.theme

    if body.activity_theme is not None:
        if body.activity_theme not in _VALID_ACTIVITY_THEMES:
            raise HTTPException(
                status_code=422,
                detail=f"activity_theme must be one of {sorted(_VALID_ACTIVITY_THEMES)}",
            )
        current_user.activity_theme = body.activity_theme

    if body.idle_timeout_minutes is not None:
        if body.idle_timeout_minutes not in _VALID_IDLE_TIMEOUTS:
            raise HTTPException(
                status_code=422,
                detail=f"idle_timeout_minutes must be one of {sorted(_VALID_IDLE_TIMEOUTS)}",
            )
        current_user.idle_timeout_minutes = body.idle_timeout_minutes

    if body.measurement_system is not None:
        if body.measurement_system not in _VALID_MEASUREMENT_SYSTEMS:
            raise HTTPException(
                status_code=422,
                detail=f"measurement_system must be one of {sorted(_VALID_MEASUREMENT_SYSTEMS)}",
            )
        current_user.measurement_system = body.measurement_system

    if body.ai_training_consent is not None:
        current_user.ai_training_consent = body.ai_training_consent
        if not body.ai_training_consent:
            shared = await db.scalars(
                select(Draft).where(
                    Draft.owner_id == current_user.id,
                    Draft.is_shared.is_(True),
                )
            )
            for draft in shared.all():
                draft.is_shared = False

    await db.commit()
    await db.refresh(current_user)
    version = await get_current_eula_version(db)
    return _to_response(current_user, version)


@router.post("/me/eula", response_model=UserSettingsResponse)
async def accept_eula(
    body: EulaAcceptRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserSettingsResponse:
    current_version = await get_current_eula_version(db)
    if body.version != current_version:
        raise HTTPException(
            status_code=422,
            detail=f"Version mismatch — current EULA is {current_version}",
        )
    current_user.eula_accepted_version = current_version
    current_user.eula_accepted_at = datetime.now(timezone.utc)
    await write_audit_log(db, event_type="eula.accepted", actor=current_user, details={"version": current_version})
    await db.commit()
    await db.refresh(current_user)
    return _to_response(current_user, current_version)


@router.delete("/me", status_code=204)
async def delete_account(
    body: DeleteAccountRequest,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    if body.confirm != "DELETE MY ACCOUNT":
        raise HTTPException(
            status_code=422,
            detail='confirm must be exactly "DELETE MY ACCOUNT"',
        )

    user_id = current_user.id
    await _purge_user_storage(db, user_id)
    await _purge_user_db(db, user_id, current_user)
    await db.commit()

    response.delete_cookie(_SESSION_COOKIE)


@router.get("/me/data-export")
async def data_export(_: User = Depends(get_current_user)) -> dict:
    return {
        "status": "not_implemented",
        "milestone": "2",
        "message": (
            "Data export is planned for Milestone 2. "
            "It will package your WIF files, photos, and activity history into a downloadable archive."
        ),
    }


# ---------------------------------------------------------------------------
# Account deletion helpers
# ---------------------------------------------------------------------------


async def _purge_user_storage(db: AsyncSession, user_id: uuid.UUID) -> None:
    """Delete all S3/local files belonging to the user. Storage errors are logged but not fatal."""

    # Activity photos
    photos = await db.scalars(
        select(ActivityPhoto)
        .join(Activity, ActivityPhoto.activity_id == Activity.id)
        .where(Activity.owner_id == user_id)
    )
    for p in photos.all():
        _safe_delete(p.file_path)

    # Yarn profile photos
    yarns = await db.scalars(select(Yarn).where(Yarn.owner_id == user_id))
    for y in yarns.all():
        if y.photo_path:
            _safe_delete(y.photo_path)

    # Loom profile photos + version photos/receipts
    looms = await db.scalars(select(Loom).where(Loom.owner_id == user_id))
    loom_ids = []
    for loom in looms.all():
        loom_ids.append(loom.id)
        if loom.photo_path:
            _safe_delete(loom.photo_path)

    if loom_ids:
        versions = await db.scalars(select(LoomVersion).where(LoomVersion.loom_id.in_(loom_ids)))
        version_ids = []
        for v in versions.all():
            version_ids.append(v.id)

        if version_ids:
            vp = await db.scalars(select(LoomVersionPhoto).where(LoomVersionPhoto.loom_version_id.in_(version_ids)))
            for p in vp.all():
                _safe_delete(p.path)

            vr = await db.scalars(select(LoomVersionReceipt).where(LoomVersionReceipt.loom_version_id.in_(version_ids)))
            for r in vr.all():
                _safe_delete(r.path)

    # Draft WIF files and previews
    drafts = await db.scalars(select(Draft).where(Draft.owner_id == user_id))
    for draft in drafts.all():
        if draft.wif_path:
            _safe_delete(draft.wif_path)
        if draft.preview_path:
            _safe_delete(draft.preview_path)


def _safe_delete(path: str) -> None:
    try:
        storage._delete(path)
    except Exception as exc:
        log.warning("Storage delete failed for %s: %s", path, exc)


async def _purge_user_db(db: AsyncSession, user_id: uuid.UUID, user: User) -> None:
    """Hard-delete all DB rows belonging to the user in FK-safe order."""
    activity_ids_subq = select(Activity.id).where(Activity.owner_id == user_id)
    await db.execute(delete(ActivityStep).where(ActivityStep.activity_id.in_(activity_ids_subq)))
    await db.execute(delete(ActivityPhoto).where(ActivityPhoto.activity_id.in_(activity_ids_subq)))
    await db.execute(delete(Activity).where(Activity.owner_id == user_id))

    yarn_ids_subq = select(Yarn.id).where(Yarn.owner_id == user_id)
    await db.execute(delete(Skein).where(Skein.yarn_id.in_(yarn_ids_subq)))
    await db.execute(delete(Yarn).where(Yarn.owner_id == user_id))

    loom_ids_subq = select(Loom.id).where(Loom.owner_id == user_id)
    version_ids_subq = select(LoomVersion.id).where(LoomVersion.loom_id.in_(loom_ids_subq))
    await db.execute(delete(LoomVersionAccessory).where(LoomVersionAccessory.loom_version_id.in_(version_ids_subq)))
    await db.execute(delete(LoomVersionReceipt).where(LoomVersionReceipt.loom_version_id.in_(version_ids_subq)))
    await db.execute(delete(LoomVersionPhoto).where(LoomVersionPhoto.loom_version_id.in_(version_ids_subq)))
    await db.execute(delete(LoomVersion).where(LoomVersion.loom_id.in_(loom_ids_subq)))
    await db.execute(delete(Loom).where(Loom.owner_id == user_id))

    await db.execute(delete(Draft).where(Draft.owner_id == user_id))

    await db.execute(delete(Invite).where(Invite.created_by_id == user_id))

    await db.execute(delete(UserIdentity).where(UserIdentity.user_id == user_id))

    await db.delete(user)
