from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db
from app.models.user import User

router = APIRouter(prefix="/system", tags=["system"])


@router.get("/status")
async def system_status(db: AsyncSession = Depends(get_db)) -> dict:
    count = await db.scalar(select(func.count()).select_from(User).where(User.is_superuser.is_(True)))
    return {"initialized": (count or 0) > 0}
