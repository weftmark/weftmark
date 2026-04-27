import importlib.metadata
import platform
import time
import uuid
from datetime import datetime, timedelta, timezone

import psutil
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db, require_admin
from app.models.activity import Activity
from app.models.invite import Invite
from app.models.loom import Loom
from app.models.project import Project
from app.models.user import User
from app.models.yarn import Yarn
from app.version import VERSION

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
    is_active: bool
    created_at: datetime
    last_active_at: datetime | None
    counts: AdminUserCounts

    model_config = {"from_attributes": False}


class AdminUserPatch(BaseModel):
    is_active: bool | None = None
    is_admin: bool | None = None


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
            created_at=u.created_at,
            last_active_at=u.last_active_at,
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

    if body.is_active is not None:
        user.is_active = body.is_active
    if body.is_admin is not None:
        user.is_admin = body.is_admin

    await db.commit()
    await db.refresh(user)

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
        created_at=user.created_at,
        last_active_at=user.last_active_at,
        counts=AdminUserCounts(
            projects=projects,
            activities_active=act_active,
            activities_completed=act_completed,
            looms=looms,
        ),
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
