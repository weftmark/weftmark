"""User settings, EULA acceptance, and account management.

Routes:
  GET    /api/eula/current                        — current EULA version + HTML body (public)
  GET    /api/users/me/settings                   — current user settings
  PATCH  /api/users/me                            — update settings
  POST   /api/users/me/eula                       — accept the current EULA version
  DELETE /api/users/me                            — hard-delete account + all data
  POST   /api/users/me/data-export                — queue a data export archive task
  GET    /api/users/me/data-export/status         — most recent export request status
  GET    /api/users/me/data-export/download/{id}  — stream the archive (auth-gated)
"""

import logging
import uuid
from datetime import date as date_cls
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import Date, and_, cast, delete, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_current_user, get_db
from app.metrics import eula_accepted_total
from app.models.collection import Collection, CollectionDraft, CollectionProject
from app.models.draft import Draft
from app.models.eula_version import EulaVersion
from app.models.invite import Invite
from app.models.loom import Loom, LoomVersion, LoomVersionAccessory, LoomVersionPhoto, LoomVersionReceipt
from app.models.project import Project, ProjectPhoto, ProjectStep
from app.models.user import User
from app.models.user_export import UserExportRequest
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
_VALID_COLOR_MODES = {"theme", "strip", "filled"}

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
    show_version_numbers: bool | None = None
    hide_unused_shafts_treadles: bool | None = None
    tracker_color_mode: str | None = None
    tracker_show_weft_color: bool | None = None
    tracker_show_drawdown: bool | None = None
    tracker_show_progress: bool | None = None
    tracker_show_pick_cards: bool | None = None
    onboarding_dismissed: bool | None = None


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
    show_version_numbers: bool
    hide_unused_shafts_treadles: bool
    tracker_color_mode: str
    tracker_show_weft_color: bool
    tracker_show_drawdown: bool
    tracker_show_progress: bool
    tracker_show_pick_cards: bool
    onboarding_dismissed: bool
    eula_accepted_version: str | None
    current_eula_version: str

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# EULA helpers
# ---------------------------------------------------------------------------


async def get_current_eula_version(db: AsyncSession) -> str:
    row = await db.scalar(select(EulaVersion).order_by(EulaVersion.id.desc()).limit(1))
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
        show_version_numbers=user.show_version_numbers,
        hide_unused_shafts_treadles=user.hide_unused_shafts_treadles,
        tracker_color_mode=user.tracker_color_mode,
        tracker_show_weft_color=user.tracker_show_weft_color,
        tracker_show_drawdown=user.tracker_show_drawdown,
        tracker_show_progress=user.tracker_show_progress,
        tracker_show_pick_cards=user.tracker_show_pick_cards,
        onboarding_dismissed=user.onboarding_dismissed,
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
    row = await db.scalar(select(EulaVersion).order_by(EulaVersion.id.desc()).limit(1))
    if not row:
        raise HTTPException(status_code=404, detail="No EULA version found")
    return EulaCurrentResponse(version=row.version, body_html=row.body_html, effective_date=row.effective_date)


router = APIRouter(prefix="/api/users", tags=["users"])


class HeatmapProjectEntry(BaseModel):
    id: str
    name: str
    step_count: int


class ActivityDayResponse(BaseModel):
    date: str
    count: int
    projects: list[HeatmapProjectEntry]


class ActivityHeatmapResponse(BaseModel):
    days: list[ActivityDayResponse]
    earliest_activity_date: str | None
    years_with_activity: list[int]


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

    if body.show_version_numbers is not None:
        current_user.show_version_numbers = body.show_version_numbers

    if body.hide_unused_shafts_treadles is not None:
        current_user.hide_unused_shafts_treadles = body.hide_unused_shafts_treadles

    if body.tracker_color_mode is not None:
        if body.tracker_color_mode not in _VALID_COLOR_MODES:
            raise HTTPException(
                status_code=422,
                detail=f"tracker_color_mode must be one of {sorted(_VALID_COLOR_MODES)}",
            )
        current_user.tracker_color_mode = body.tracker_color_mode

    if body.tracker_show_weft_color is not None:
        current_user.tracker_show_weft_color = body.tracker_show_weft_color

    if body.tracker_show_drawdown is not None:
        current_user.tracker_show_drawdown = body.tracker_show_drawdown

    if body.tracker_show_progress is not None:
        current_user.tracker_show_progress = body.tracker_show_progress

    if body.tracker_show_pick_cards is not None:
        current_user.tracker_show_pick_cards = body.tracker_show_pick_cards

    if body.onboarding_dismissed is not None:
        current_user.onboarding_dismissed = body.onboarding_dismissed

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
    eula_accepted_total.add(1)
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

    if current_user.clerk_user_id:
        from app.services.clerk import delete_clerk_user

        await delete_clerk_user(current_user.clerk_user_id)

    await _purge_user_storage(db, user_id)
    await _purge_user_db(db, user_id, current_user)
    await db.commit()

    response.delete_cookie(_SESSION_COOKIE)


class ExportStatusResponse(BaseModel):
    request_id: str | None = None
    status: str | None = None
    requested_at: str | None = None
    expires_at: str | None = None
    error: str | None = None


_EXPORT_COOLDOWN_HOURS = 24


@router.post("/me/data-export", status_code=202)
async def request_data_export(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ExportStatusResponse:
    """Queue a data export task. De-duplicated: one request per 24 h."""
    from datetime import timedelta

    cutoff = datetime.now(timezone.utc) - timedelta(hours=_EXPORT_COOLDOWN_HOURS)
    existing = await db.scalar(
        select(UserExportRequest)
        .where(
            UserExportRequest.user_id == current_user.id,
            UserExportRequest.requested_at >= cutoff,
            UserExportRequest.status.in_(("pending", "complete")),
        )
        .order_by(UserExportRequest.requested_at.desc())
        .limit(1)
    )
    if existing:
        return ExportStatusResponse(
            request_id=str(existing.id),
            status=existing.status,
            requested_at=existing.requested_at.isoformat(),
            expires_at=existing.expires_at.isoformat() if existing.expires_at else None,
        )

    req = UserExportRequest(
        id=uuid.uuid4(),
        user_id=current_user.id,
        requested_at=datetime.now(timezone.utc),
        status="pending",
    )
    db.add(req)
    await db.commit()
    await db.refresh(req)

    from app.tasks.export import run_user_export

    run_user_export.delay(str(current_user.id), str(req.id))

    return ExportStatusResponse(
        request_id=str(req.id),
        status="pending",
        requested_at=req.requested_at.isoformat(),
    )


@router.get("/me/data-export/status", response_model=ExportStatusResponse)
async def get_export_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ExportStatusResponse:
    """Return the most recent export request for the current user."""
    req = await db.scalar(
        select(UserExportRequest)
        .where(UserExportRequest.user_id == current_user.id)
        .order_by(UserExportRequest.requested_at.desc())
        .limit(1)
    )
    if req is None:
        return ExportStatusResponse()
    return ExportStatusResponse(
        request_id=str(req.id),
        status=req.status,
        requested_at=req.requested_at.isoformat(),
        expires_at=req.expires_at.isoformat() if req.expires_at else None,
        error=req.error,
    )


@router.get("/me/data-export/download/{request_id}")
async def download_data_export(
    request_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Stream the export archive. Auth-gated; returns 404 after expiry."""
    req = await db.get(UserExportRequest, request_id)
    if req is None or req.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Export not found")
    if req.status != "complete" or not req.archive_path:
        raise HTTPException(status_code=404, detail="Export not ready")
    if req.expires_at and req.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=410, detail="Export has expired")

    archive_bytes = storage.read_file(req.archive_path)
    date_str = req.requested_at.strftime("%Y%m%d")
    filename = f"weftmark-export-{date_str}.zip"

    return StreamingResponse(
        iter([archive_bytes]),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


class OnboardingStatusResponse(BaseModel):
    eula_accepted: bool
    has_loom: bool
    has_draft: bool
    has_project: bool


@router.get("/me/onboarding-status", response_model=OnboardingStatusResponse)
async def get_onboarding_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> OnboardingStatusResponse:
    current_version = await get_current_eula_version(db)
    has_loom = await db.scalar(select(func.count()).select_from(Loom).where(Loom.owner_id == current_user.id)) or 0
    has_draft = await db.scalar(select(func.count()).select_from(Draft).where(Draft.owner_id == current_user.id)) or 0
    has_project = (
        await db.scalar(select(func.count()).select_from(Project).where(Project.owner_id == current_user.id)) or 0
    )
    return OnboardingStatusResponse(
        eula_accepted=current_user.eula_accepted_version == current_version,
        has_loom=has_loom > 0,
        has_draft=has_draft > 0,
        has_project=has_project > 0,
    )


@router.get("/me/activity-heatmap", response_model=ActivityHeatmapResponse)
async def get_activity_heatmap(
    year: int | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ActivityHeatmapResponse:
    from collections import defaultdict

    day_col = cast(func.timezone("UTC", ProjectStep.created_at), Date)
    base_filter = and_(
        Project.owner_id == current_user.id,
        Project.deleted_at.is_(None),
    )

    if year is not None:
        date_filter = and_(day_col >= date_cls(year, 1, 1), day_col <= date_cls(year, 12, 31))
    else:
        date_filter = ProjectStep.created_at >= func.now() - text("interval '366 days'")

    rows = (
        await db.execute(
            select(
                day_col.label("day"),
                Project.id.label("project_id"),
                Project.name.label("project_name"),
                func.count().label("step_count"),
            )
            .join(Project, ProjectStep.project_id == Project.id)
            .where(base_filter, date_filter)
            .group_by(text("1"), Project.id, Project.name)
            .order_by(text("1"), func.count().desc())
        )
    ).all()

    days_map: dict[str, list[HeatmapProjectEntry]] = defaultdict(list)
    for row in rows:
        days_map[str(row.day)].append(
            HeatmapProjectEntry(id=str(row.project_id), name=row.project_name, step_count=row.step_count)
        )

    earliest = await db.scalar(
        select(func.min(day_col)).join(Project, ProjectStep.project_id == Project.id).where(base_filter)
    )

    years_rows = (
        await db.execute(
            select(func.extract("year", day_col).label("yr"))
            .join(Project, ProjectStep.project_id == Project.id)
            .where(base_filter)
            .distinct()
            .order_by(text("1"))
        )
    ).all()

    return ActivityHeatmapResponse(
        days=[
            ActivityDayResponse(
                date=date_str,
                count=sum(p.step_count for p in projects),
                projects=projects,
            )
            for date_str, projects in sorted(days_map.items())
        ],
        earliest_activity_date=str(earliest) if earliest else None,
        years_with_activity=[int(r.yr) for r in years_rows],
    )


# ---------------------------------------------------------------------------
# Account deletion helpers
# ---------------------------------------------------------------------------


async def _purge_user_storage(db: AsyncSession, user_id: uuid.UUID) -> None:
    """Delete all S3/local files belonging to the user. Storage errors are logged but not fatal."""

    # Project photos
    photos = await db.scalars(
        select(ProjectPhoto).join(Project, ProjectPhoto.project_id == Project.id).where(Project.owner_id == user_id)
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
            for lp in vp.all():
                _safe_delete(lp.path)

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
    project_ids_subq = select(Project.id).where(Project.owner_id == user_id)
    await db.execute(delete(ProjectStep).where(ProjectStep.project_id.in_(project_ids_subq)))
    await db.execute(delete(ProjectPhoto).where(ProjectPhoto.project_id.in_(project_ids_subq)))
    await db.execute(delete(Project).where(Project.owner_id == user_id))

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

    collection_ids_subq = select(Collection.id).where(Collection.owner_id == user_id)
    await db.execute(delete(CollectionDraft).where(CollectionDraft.collection_id.in_(collection_ids_subq)))
    await db.execute(delete(CollectionProject).where(CollectionProject.collection_id.in_(collection_ids_subq)))
    await db.execute(delete(Collection).where(Collection.owner_id == user_id))

    await db.execute(delete(Draft).where(Draft.owner_id == user_id))

    await db.execute(delete(Invite).where(Invite.created_by_id == user_id))

    await db.execute(delete(UserIdentity).where(UserIdentity.user_id == user_id))

    await db.delete(user)
