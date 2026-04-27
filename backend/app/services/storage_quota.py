import uuid

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity import Activity, ActivityPhoto
from app.models.loom import Loom, LoomVersion, LoomVersionPhoto

MAX_USER_STORAGE_BYTES = 500 * 1024 * 1024  # 500 MB


async def get_user_storage_used(user_id: uuid.UUID, db: AsyncSession) -> int:
    activity_bytes = await db.scalar(
        select(func.coalesce(func.sum(ActivityPhoto.file_size_bytes), 0))
        .join(Activity, ActivityPhoto.activity_id == Activity.id)
        .where(Activity.owner_id == user_id)
    )
    loom_version_bytes = await db.scalar(
        select(func.coalesce(func.sum(LoomVersionPhoto.file_size_bytes), 0))
        .join(LoomVersion, LoomVersionPhoto.loom_version_id == LoomVersion.id)
        .join(Loom, LoomVersion.loom_id == Loom.id)
        .where(Loom.owner_id == user_id)
    )
    return int(activity_bytes or 0) + int(loom_version_bytes or 0)


async def check_storage_quota(user_id: uuid.UUID, db: AsyncSession, incoming_bytes: int = 0) -> None:
    used = await get_user_storage_used(user_id, db)
    if used + incoming_bytes > MAX_USER_STORAGE_BYTES:
        used_mb = used / (1024 * 1024)
        raise HTTPException(
            status_code=400,
            detail=f"Storage limit reached ({used_mb:.0f} MB of 500 MB used). Delete some photos to free space.",
        )
