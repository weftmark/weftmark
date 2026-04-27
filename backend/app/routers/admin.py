import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db, require_admin
from app.models.activity import Activity
from app.models.invite import Invite
from app.models.loom import Loom
from app.models.project import Project
from app.models.user import User
from app.models.yarn import Yarn

router = APIRouter(prefix="/api/admin", tags=["admin"])


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class AdminUserResponse(BaseModel):
    id: uuid.UUID
    email: str
    display_name: str
    is_admin: bool
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class AdminUserPatch(BaseModel):
    is_active: bool | None = None
    is_admin: bool | None = None


class AdminStatsResponse(BaseModel):
    total_users: int
    active_users: int
    total_projects: int
    total_activities: int
    total_looms: int
    total_yarn: int
    pending_invites: int


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------


@router.get("/users", response_model=list[AdminUserResponse])
async def list_users(
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> list[User]:
    result = await db.scalars(select(User).where(User.deleted_at.is_(None)).order_by(User.created_at.asc()))
    return list(result.all())


@router.patch("/users/{user_id}", response_model=AdminUserResponse)
async def patch_user(
    user_id: uuid.UUID,
    body: AdminUserPatch,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> User:
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
    return user


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


@router.get("/stats", response_model=AdminStatsResponse)
async def get_stats(
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> AdminStatsResponse:
    now = datetime.now(timezone.utc)

    total_users = await db.scalar(select(func.count()).select_from(User).where(User.deleted_at.is_(None))) or 0
    active_users = (
        await db.scalar(
            select(func.count()).select_from(User).where(User.deleted_at.is_(None), User.is_active.is_(True))
        )
        or 0
    )
    total_projects = await db.scalar(select(func.count()).select_from(Project).where(Project.deleted_at.is_(None))) or 0
    total_activities = (
        await db.scalar(select(func.count()).select_from(Activity).where(Activity.deleted_at.is_(None))) or 0
    )
    total_looms = await db.scalar(select(func.count()).select_from(Loom).where(Loom.deleted_at.is_(None))) or 0
    total_yarn = await db.scalar(select(func.count()).select_from(Yarn).where(Yarn.deleted_at.is_(None))) or 0
    pending_invites = (
        await db.scalar(
            select(func.count())
            .select_from(Invite)
            .where(
                Invite.accepted_at.is_(None),
                Invite.revoked_at.is_(None),
                Invite.expires_at > now,
            )
        )
        or 0
    )

    return AdminStatsResponse(
        total_users=total_users,
        active_users=active_users,
        total_projects=total_projects,
        total_activities=total_activities,
        total_looms=total_looms,
        total_yarn=total_yarn,
        pending_invites=pending_invites,
    )
