import importlib.metadata
import logging
import platform
import time
import uuid
from datetime import datetime, timedelta, timezone

import psutil
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db, require_admin, require_superuser
from app.models.activity import Activity
from app.models.eula_version import EulaVersion
from app.models.invite import Invite
from app.models.loom import Loom
from app.models.pending_signup import PendingSignup
from app.models.project import Project
from app.models.user import User
from app.models.yarn import Yarn
from app.services.clerk import ban_clerk_user, set_user_metadata, unban_clerk_user
from app.services.email import (
    send_account_approved_email,
    send_account_denied_email,
    send_approval_confirmation_to_admins,
)
from app.version import VERSION

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin", tags=["admin"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class AdminUserCounts(BaseModel):
    projects: int
    activities_active: int
    activities_completed: int
    looms: int


class AdminUserResponse(BaseModel):
    id: uuid.UUID
    email: str
    display_name: str
    is_admin: bool
    is_superuser: bool
    is_active: bool
    clerk_banned: bool
    created_at: datetime
    last_active_at: datetime | None
    approved_by_name: str | None
    approved_by_email: str | None
    counts: AdminUserCounts

    model_config = {"from_attributes": False}


class AdminUserPatch(BaseModel):
    is_active: bool | None = None
    is_admin: bool | None = None
    is_superuser: bool | None = None


class AdminStatsResponse(BaseModel):
    total_users: int
    active_users: int
    active_7d: int
    active_30d: int
    active_90d: int
    total_projects: int
    total_activities: int
    total_looms: int
    total_yarn: int
    pending_invites: int


class AdminHealthResponse(BaseModel):
    cpu_percent: float
    memory_percent: float
    memory_used_mb: int
    memory_total_mb: int
    db_ping_ms: float
    uptime_seconds: int


class AdminVersionsResponse(BaseModel):
    app: str
    python: str
    fastapi: str
    sqlalchemy: str
    alembic: str
    pyweaving: str
    pillow: str
    boto3: str
    psutil: str


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------


@router.get("/users", response_model=list[AdminUserResponse])
async def list_users(
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> list[AdminUserResponse]:
    users = list(
        (await db.scalars(select(User).where(User.deleted_at.is_(None)).order_by(User.created_at.asc()))).all()
    )
    if not users:
        return []

    user_ids = [u.id for u in users]

    # Per-user project counts
    project_rows = (
        await db.execute(
            select(Project.owner_id, func.count().label("cnt"))
            .where(Project.owner_id.in_(user_ids), Project.deleted_at.is_(None))
            .group_by(Project.owner_id)
        )
    ).all()
    project_counts = {row.owner_id: row.cnt for row in project_rows}

    # Per-user activity counts by status
    activity_rows = (
        await db.execute(
            select(Activity.owner_id, Activity.status, func.count().label("cnt"))
            .where(Activity.owner_id.in_(user_ids), Activity.deleted_at.is_(None))
            .group_by(Activity.owner_id, Activity.status)
        )
    ).all()
    activity_active: dict[uuid.UUID, int] = {}
    activity_completed: dict[uuid.UUID, int] = {}
    for row in activity_rows:
        if row.status == "active":
            activity_active[row.owner_id] = row.cnt
        elif row.status == "completed":
            activity_completed[row.owner_id] = row.cnt

    # Per-user loom counts
    loom_rows = (
        await db.execute(
            select(Loom.owner_id, func.count().label("cnt"))
            .where(Loom.owner_id.in_(user_ids), Loom.deleted_at.is_(None))
            .group_by(Loom.owner_id)
        )
    ).all()
    loom_counts = {row.owner_id: row.cnt for row in loom_rows}

    return [
        AdminUserResponse(
            id=u.id,
            email=u.email,
            display_name=u.display_name,
            is_admin=u.is_admin,
            is_active=u.is_active,
            clerk_banned=u.clerk_banned,
            created_at=u.created_at,
            last_active_at=u.last_active_at,
            approved_by_name=u.approved_by_name,
            approved_by_email=u.approved_by_email,
            is_superuser=u.is_superuser,
            counts=AdminUserCounts(
                projects=project_counts.get(u.id, 0),
                activities_active=activity_active.get(u.id, 0),
                activities_completed=activity_completed.get(u.id, 0),
                looms=loom_counts.get(u.id, 0),
            ),
        )
        for u in users
    ]


@router.patch("/users/{user_id}", response_model=AdminUserResponse)
async def patch_user(
    user_id: uuid.UUID,
    body: AdminUserPatch,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> AdminUserResponse:
    user = await db.scalar(select(User).where(User.id == user_id, User.deleted_at.is_(None)))
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == admin.id:
        raise HTTPException(status_code=400, detail="Cannot modify your own account")

    if body.is_admin is not None or body.is_superuser is not None:
        if not admin.is_superuser:
            raise HTTPException(status_code=403, detail="Superuser required to change admin or superuser roles")
        if body.is_admin is False and user.is_superuser:
            raise HTTPException(status_code=400, detail="Cannot remove admin from a superuser")

    if body.is_active is False and user.is_admin:
        raise HTTPException(status_code=422, detail="Remove admin rights before deactivating this user")

    if body.is_active is not None:
        user.is_active = body.is_active
    if body.is_admin is not None:
        user.is_admin = body.is_admin
    if body.is_superuser is not None:
        user.is_superuser = body.is_superuser

    await db.commit()
    await db.refresh(user)

    if (body.is_admin is not None or body.is_superuser is not None) and user.clerk_user_id:
        await set_user_metadata(user.clerk_user_id, {"is_admin": user.is_admin, "is_superuser": user.is_superuser})

    # Re-fetch counts for the patched user
    projects = (
        await db.scalar(
            select(func.count()).select_from(Project).where(Project.owner_id == user.id, Project.deleted_at.is_(None))
        )
        or 0
    )
    act_active = (
        await db.scalar(
            select(func.count())
            .select_from(Activity)
            .where(Activity.owner_id == user.id, Activity.status == "active", Activity.deleted_at.is_(None))
        )
        or 0
    )
    act_completed = (
        await db.scalar(
            select(func.count())
            .select_from(Activity)
            .where(Activity.owner_id == user.id, Activity.status == "completed", Activity.deleted_at.is_(None))
        )
        or 0
    )
    looms = (
        await db.scalar(
            select(func.count()).select_from(Loom).where(Loom.owner_id == user.id, Loom.deleted_at.is_(None))
        )
        or 0
    )

    return AdminUserResponse(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        is_admin=user.is_admin,
        is_active=user.is_active,
        clerk_banned=user.clerk_banned,
        created_at=user.created_at,
        last_active_at=user.last_active_at,
        approved_by_name=user.approved_by_name,
        approved_by_email=user.approved_by_email,
        is_superuser=user.is_superuser,
        counts=AdminUserCounts(
            projects=projects,
            activities_active=act_active,
            activities_completed=act_completed,
            looms=looms,
        ),
    )


# ---------------------------------------------------------------------------
# Ban / unban
# ---------------------------------------------------------------------------


@router.post("/users/{user_id}/ban", status_code=200)
async def ban_user(
    user_id: uuid.UUID,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> AdminUserResponse:
    user = await db.scalar(select(User).where(User.id == user_id, User.deleted_at.is_(None)))
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if user.id == admin.id:
        raise HTTPException(status_code=400, detail="Cannot ban your own account")
    if not user.clerk_user_id:
        raise HTTPException(status_code=400, detail="User has no Clerk account")
    if user.is_admin:
        raise HTTPException(status_code=422, detail="Remove admin rights before banning this user")

    await ban_clerk_user(user.clerk_user_id)
    await set_user_metadata(user.clerk_user_id, {"status": "banned"})
    user.clerk_banned = True
    user.is_active = False
    await db.commit()
    await db.refresh(user)

    return AdminUserResponse(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        is_admin=user.is_admin,
        is_active=user.is_active,
        clerk_banned=user.clerk_banned,
        created_at=user.created_at,
        last_active_at=user.last_active_at,
        approved_by_name=user.approved_by_name,
        approved_by_email=user.approved_by_email,
        is_superuser=user.is_superuser,
        counts=AdminUserCounts(projects=0, activities_active=0, activities_completed=0, looms=0),
    )


@router.post("/users/{user_id}/unban", status_code=200)
async def unban_user(
    user_id: uuid.UUID,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> AdminUserResponse:
    user = await db.scalar(select(User).where(User.id == user_id, User.deleted_at.is_(None)))
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if not user.clerk_user_id:
        raise HTTPException(status_code=400, detail="User has no Clerk account")

    await unban_clerk_user(user.clerk_user_id)
    await set_user_metadata(user.clerk_user_id, {"status": "active"})
    user.clerk_banned = False
    user.is_active = True
    await db.commit()
    await db.refresh(user)

    return AdminUserResponse(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        is_admin=user.is_admin,
        is_active=user.is_active,
        clerk_banned=user.clerk_banned,
        created_at=user.created_at,
        last_active_at=user.last_active_at,
        approved_by_name=user.approved_by_name,
        approved_by_email=user.approved_by_email,
        is_superuser=user.is_superuser,
        counts=AdminUserCounts(projects=0, activities_active=0, activities_completed=0, looms=0),
    )


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


@router.get("/stats", response_model=AdminStatsResponse)
async def get_stats(
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> AdminStatsResponse:
    now = datetime.now(timezone.utc)

    async def count(stmt):  # type: ignore[no-untyped-def]
        return await db.scalar(stmt) or 0

    total_users = await count(select(func.count()).select_from(User).where(User.deleted_at.is_(None)))
    active_users = await count(
        select(func.count()).select_from(User).where(User.deleted_at.is_(None), User.is_active.is_(True))
    )
    active_7d = await count(
        select(func.count())
        .select_from(User)
        .where(User.deleted_at.is_(None), User.last_active_at >= now - timedelta(days=7))
    )
    active_30d = await count(
        select(func.count())
        .select_from(User)
        .where(User.deleted_at.is_(None), User.last_active_at >= now - timedelta(days=30))
    )
    active_90d = await count(
        select(func.count())
        .select_from(User)
        .where(User.deleted_at.is_(None), User.last_active_at >= now - timedelta(days=90))
    )
    total_projects = await count(select(func.count()).select_from(Project).where(Project.deleted_at.is_(None)))
    total_activities = await count(select(func.count()).select_from(Activity).where(Activity.deleted_at.is_(None)))
    total_looms = await count(select(func.count()).select_from(Loom).where(Loom.deleted_at.is_(None)))
    total_yarn = await count(select(func.count()).select_from(Yarn).where(Yarn.deleted_at.is_(None)))
    pending_invites = await count(
        select(func.count())
        .select_from(Invite)
        .where(Invite.accepted_at.is_(None), Invite.revoked_at.is_(None), Invite.expires_at > now)
    )

    return AdminStatsResponse(
        total_users=total_users,
        active_users=active_users,
        active_7d=active_7d,
        active_30d=active_30d,
        active_90d=active_90d,
        total_projects=total_projects,
        total_activities=total_activities,
        total_looms=total_looms,
        total_yarn=total_yarn,
        pending_invites=pending_invites,
    )


# ---------------------------------------------------------------------------
# Health snapshot
# ---------------------------------------------------------------------------


@router.get("/health", response_model=AdminHealthResponse)
async def get_health(
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> AdminHealthResponse:
    from app.main import start_time

    cpu = psutil.cpu_percent(interval=None)
    mem = psutil.virtual_memory()

    t0 = time.monotonic()
    await db.execute(text("SELECT 1"))
    db_ping_ms = round((time.monotonic() - t0) * 1000, 1)

    uptime_seconds = int((datetime.now(timezone.utc) - start_time).total_seconds())

    return AdminHealthResponse(
        cpu_percent=cpu,
        memory_percent=round(mem.percent, 1),
        memory_used_mb=mem.used // (1024 * 1024),
        memory_total_mb=mem.total // (1024 * 1024),
        db_ping_ms=db_ping_ms,
        uptime_seconds=uptime_seconds,
    )


# ---------------------------------------------------------------------------
# Versions
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Elevate admin to superuser
# ---------------------------------------------------------------------------


class ElevateContentSummary(BaseModel):
    activities: int
    looms: int
    projects: int
    yarn: int


class ElevateRequest(BaseModel):
    confirm_delete_content: bool = False


@router.post("/users/{user_id}/elevate-to-superuser", status_code=200)
async def elevate_to_superuser(
    user_id: uuid.UUID,
    body: ElevateRequest,
    admin: User = Depends(require_superuser),
    db: AsyncSession = Depends(get_db),
) -> dict:
    user = await db.scalar(select(User).where(User.id == user_id, User.deleted_at.is_(None)))
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    if not user.is_admin:
        raise HTTPException(status_code=400, detail="User must be an admin before being elevated to superuser")
    if user.is_superuser:
        raise HTTPException(status_code=400, detail="User is already a superuser")
    if user.id == admin.id:
        raise HTTPException(status_code=400, detail="Cannot elevate yourself")

    activities = (
        await db.scalar(
            select(func.count())
            .select_from(Activity)
            .where(Activity.owner_id == user_id, Activity.deleted_at.is_(None))
        )
        or 0
    )
    looms = (
        await db.scalar(
            select(func.count()).select_from(Loom).where(Loom.owner_id == user_id, Loom.deleted_at.is_(None))
        )
        or 0
    )
    projects = (
        await db.scalar(
            select(func.count()).select_from(Project).where(Project.owner_id == user_id, Project.deleted_at.is_(None))
        )
        or 0
    )
    yarn = (
        await db.scalar(
            select(func.count()).select_from(Yarn).where(Yarn.owner_id == user_id, Yarn.deleted_at.is_(None))
        )
        or 0
    )

    has_content = any([activities, looms, projects, yarn])

    if has_content and not body.confirm_delete_content:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "has_content",
                "summary": {"activities": activities, "looms": looms, "projects": projects, "yarn": yarn},
            },
        )

    if has_content:
        await db.execute(Activity.__table__.delete().where(Activity.owner_id == user_id))
        await db.execute(Loom.__table__.delete().where(Loom.owner_id == user_id))
        await db.execute(Project.__table__.delete().where(Project.owner_id == user_id))
        await db.execute(Yarn.__table__.delete().where(Yarn.owner_id == user_id))

    user.is_superuser = True
    await db.commit()
    if user.clerk_user_id:
        await set_user_metadata(user.clerk_user_id, {"is_superuser": True})

    return {"status": "elevated"}


# ---------------------------------------------------------------------------
# Pending signups
# ---------------------------------------------------------------------------


class PendingSignupResponse(BaseModel):
    id: uuid.UUID
    clerk_user_id: str
    email: str
    display_name: str
    created_at: datetime

    model_config = {"from_attributes": True}


@router.get("/pending-signups", response_model=list[PendingSignupResponse])
async def list_pending_signups(
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> list[PendingSignup]:
    result = await db.scalars(select(PendingSignup).order_by(PendingSignup.created_at.desc()))
    return list(result.all())


@router.post("/pending-signups/{signup_id}/approve", response_model=None, status_code=201)
async def approve_pending_signup(
    signup_id: uuid.UUID,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    signup = await db.scalar(select(PendingSignup).where(PendingSignup.id == signup_id))
    if signup is None:
        raise HTTPException(status_code=404, detail="Pending signup not found")

    existing = await db.scalar(
        select(User).where(User.clerk_user_id == signup.clerk_user_id, User.deleted_at.is_(None))
    )
    if existing is not None:
        await db.delete(signup)
        await db.commit()
        return {"status": "already_exists"}

    user = User(
        email=signup.email,
        display_name=signup.display_name,
        clerk_user_id=signup.clerk_user_id,
        is_admin=False,
        approved_by_name=admin.display_name,
        approved_by_email=admin.email,
    )
    db.add(user)
    await db.delete(signup)
    await db.commit()
    await set_user_metadata(signup.clerk_user_id, {"status": "active", "is_admin": False, "is_superuser": False})

    admin_emails = list(await db.scalars(select(User.email).where(User.is_admin.is_(True), User.deleted_at.is_(None))))

    try:
        await send_account_approved_email(signup.email, signup.display_name)
    except Exception:
        log.exception("Failed to send account approved email to %s", signup.email)

    if admin_emails:
        try:
            await send_approval_confirmation_to_admins(
                admin_emails, signup.display_name, signup.email, admin.display_name
            )
        except Exception:
            log.exception("Failed to send approval confirmation to admins")

    return {"status": "created"}


@router.post("/pending-signups/{signup_id}/ban", status_code=204)
async def ban_pending_signup(
    signup_id: uuid.UUID,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> None:
    signup = await db.scalar(select(PendingSignup).where(PendingSignup.id == signup_id))
    if signup is None:
        raise HTTPException(status_code=404, detail="Pending signup not found")
    email, display_name, clerk_user_id = signup.email, signup.display_name, signup.clerk_user_id
    await db.delete(signup)
    await db.commit()
    await ban_clerk_user(clerk_user_id)
    await set_user_metadata(clerk_user_id, {"status": "banned"})
    try:
        await send_account_denied_email(email, display_name)
    except Exception:
        log.exception("Failed to send account denied email to %s", email)


@router.delete("/pending-signups/{signup_id}", status_code=204)
async def dismiss_pending_signup(
    signup_id: uuid.UUID,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> None:
    signup = await db.scalar(select(PendingSignup).where(PendingSignup.id == signup_id))
    if signup is None:
        raise HTTPException(status_code=404, detail="Pending signup not found")
    email, display_name, clerk_user_id = signup.email, signup.display_name, signup.clerk_user_id
    await db.delete(signup)
    await db.commit()
    await set_user_metadata(clerk_user_id, {"status": "denied"})
    try:
        await send_account_denied_email(email, display_name)
    except Exception:
        log.exception("Failed to send account denied email to %s", email)


# ---------------------------------------------------------------------------
# EULA management (superuser only)
# ---------------------------------------------------------------------------


class EulaCreateRequest(BaseModel):
    version: str
    body_html: str
    effective_date: datetime | None = None


class EulaVersionResponse(BaseModel):
    id: int
    version: str
    effective_date: datetime
    created_at: datetime


class EulaCurrentAdminResponse(BaseModel):
    id: int
    version: str
    body_html: str
    effective_date: datetime
    created_at: datetime


@router.get("/eula", response_model=EulaCurrentAdminResponse)
async def get_eula_admin(
    _: User = Depends(require_superuser),
    db: AsyncSession = Depends(get_db),
) -> EulaCurrentAdminResponse:
    row = await db.scalar(
        select(EulaVersion).order_by(EulaVersion.effective_date.desc(), EulaVersion.id.desc()).limit(1)
    )
    if not row:
        raise HTTPException(status_code=404, detail="No EULA version found")
    return EulaCurrentAdminResponse(
        id=row.id,
        version=row.version,
        body_html=row.body_html,
        effective_date=row.effective_date,
        created_at=row.created_at,
    )


@router.post("/eula", response_model=EulaVersionResponse, status_code=201)
async def create_eula_version(
    body: EulaCreateRequest,
    _: User = Depends(require_superuser),
    db: AsyncSession = Depends(get_db),
) -> EulaVersionResponse:
    existing = await db.scalar(select(EulaVersion).where(EulaVersion.version == body.version))
    if existing:
        raise HTTPException(status_code=409, detail=f"EULA version '{body.version}' already exists")

    effective = body.effective_date or datetime.now(timezone.utc)
    row = EulaVersion(version=body.version, body_html=body.body_html, effective_date=effective)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    log.info("New EULA version created: %s (effective %s)", row.version, row.effective_date)
    return EulaVersionResponse(
        id=row.id,
        version=row.version,
        effective_date=row.effective_date,
        created_at=row.created_at,
    )


def _pkg(name: str) -> str:
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return "unknown"


@router.get("/versions", response_model=AdminVersionsResponse)
async def get_versions(
    _: User = Depends(require_admin),
) -> AdminVersionsResponse:
    return AdminVersionsResponse(
        app=VERSION,
        python=platform.python_version(),
        fastapi=_pkg("fastapi"),
        sqlalchemy=_pkg("sqlalchemy"),
        alembic=_pkg("alembic"),
        pyweaving=_pkg("pyweaving"),
        pillow=_pkg("pillow"),
        boto3=_pkg("boto3"),
        psutil=_pkg("psutil"),
    )
