from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db
from app.models.seed_run import SeedRun

router = APIRouter(prefix="/dev", tags=["dev"])


@router.get("/status")
async def dev_status(db: AsyncSession = Depends(get_db)) -> dict:
    seed_run = await db.get(SeedRun, 1)
    return {"last_seed": seed_run.ran_at.isoformat() if seed_run else None}
