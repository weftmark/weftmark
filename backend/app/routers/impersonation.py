"""Impersonation session endpoints — audit trail only; state is managed client-side."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_db, require_superuser
from app.models.user import User
from app.services.audit import write_audit_log

router = APIRouter(prefix="/api/impersonation", tags=["impersonation"])


class ImpersonationStartRequest(BaseModel):
    target_user_id: uuid.UUID


class ImpersonationEndRequest(BaseModel):
    target_user_id: uuid.UUID
    duration_seconds: int = 0


class UserSummary(BaseModel):
    id: uuid.UUID
    email: str
    display_name: str

    model_config = {"from_attributes": True}


class ImpersonationStartResponse(BaseModel):
    target: UserSummary


@router.post("/start", response_model=ImpersonationStartResponse)
async def impersonation_start(
    body: ImpersonationStartRequest,
    superuser: User = Depends(require_superuser),
    db: AsyncSession = Depends(get_db),
) -> ImpersonationStartResponse:
    """Validate the impersonation target and write the audit log entry."""
    target = await db.scalar(select(User).where(User.id == body.target_user_id))
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if target.is_superuser:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot impersonate a superuser")

    if target.deleted_at is not None or not target.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot impersonate an inactive user")

    await write_audit_log(
        db,
        event_type="impersonation.started",
        actor=superuser,
        target=target,
    )
    await db.commit()

    return ImpersonationStartResponse(
        target=UserSummary(id=target.id, email=target.email, display_name=target.display_name)
    )


@router.post("/end")
async def impersonation_end(
    body: ImpersonationEndRequest,
    superuser: User = Depends(require_superuser),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Write the impersonation-ended audit log entry."""
    target = await db.scalar(select(User).where(User.id == body.target_user_id))
    if target is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    await write_audit_log(
        db,
        event_type="impersonation.ended",
        actor=superuser,
        target=target,
        details={"duration_seconds": body.duration_seconds},
    )
    await db.commit()

    return {}
