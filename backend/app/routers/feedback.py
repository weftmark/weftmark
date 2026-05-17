"""In-app feedback submission and admin review endpoints."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, field_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.deps import get_current_user, get_db, get_optional_user, require_admin
from app.models.feedback import SUBMISSION_TYPES, UserFeedback
from app.models.user import User
from app.services.rate_limiter import rate_limit

router = APIRouter(tags=["feedback"])

_submit_limit = rate_limit("feedback_submit", max_requests=5, window_seconds=3600)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class DiagnosticsPayload(BaseModel):
    environment: str | None = None
    page_url: str | None = None
    user_agent: str | None = None
    app_version: str | None = None
    project_id: str | None = None
    draft_id: str | None = None


class SubmitFeedbackRequest(BaseModel):
    submission_type: str
    body: str
    subject: str | None = None
    is_anonymous: bool = False
    diagnostics: DiagnosticsPayload | None = None

    @field_validator("submission_type")
    @classmethod
    def _valid_type(cls, v: str) -> str:
        if v not in SUBMISSION_TYPES:
            raise ValueError(f"submission_type must be one of: {', '.join(SUBMISSION_TYPES)}")
        return v

    @field_validator("body")
    @classmethod
    def _nonempty_body(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("body must not be blank")
        return v


class FeedbackResponse(BaseModel):
    id: str
    submission_type: str
    subject: str | None
    body: str
    is_anonymous: bool
    diagnostics: dict | None
    github_discussion_url: str | None
    dispatch_status: str
    user_email: str | None
    deleted_at: str | None
    created_at: str

    model_config = {"from_attributes": True}


class FeedbackPage(BaseModel):
    items: list[FeedbackResponse]
    total: int
    page: int
    page_size: int
    pages: int


def _serialize(row: UserFeedback, include_user_email: bool = False) -> FeedbackResponse:
    user_email: str | None = None
    if include_user_email and not row.is_anonymous and row.user is not None:
        user_email = row.user.email
    return FeedbackResponse(
        id=str(row.id),
        submission_type=row.submission_type,
        subject=row.subject,
        body=row.body,
        is_anonymous=row.is_anonymous,
        diagnostics=row.diagnostics,
        github_discussion_url=row.github_discussion_url,
        dispatch_status=row.dispatch_status,
        user_email=user_email,
        deleted_at=row.deleted_at.isoformat() if row.deleted_at else None,
        created_at=row.created_at.isoformat(),
    )


# ---------------------------------------------------------------------------
# Submit feedback (auth optional)
# ---------------------------------------------------------------------------


@router.post("/api/feedback", status_code=201)
async def submit_feedback(
    body: SubmitFeedbackRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_optional_user),
    _rl: None = Depends(_submit_limit),
) -> FeedbackResponse:
    from app.config import get_settings

    has_token = bool(get_settings().github_feedback_token)
    row = UserFeedback(
        id=uuid.uuid4(),
        user_id=current_user.id if current_user else None,
        submission_type=body.submission_type,
        is_anonymous=body.is_anonymous,
        subject=body.subject,
        body=body.body,
        diagnostics=body.diagnostics.model_dump() if body.diagnostics else None,
        dispatch_status="pending" if has_token else "skipped",
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)

    if has_token:
        _enqueue_dispatch(str(row.id))

    return _serialize(row)


def _enqueue_dispatch(feedback_id: str) -> None:
    from app.config import get_settings
    from app.services.task_history import record_queued

    settings = get_settings()
    if not settings.github_feedback_token:
        return
    from app.tasks.feedback_dispatch import dispatch_feedback

    t = dispatch_feedback.delay(feedback_id)
    record_queued(settings, t.id, "app.tasks.feedback_dispatch.dispatch_feedback", "feedback")


# ---------------------------------------------------------------------------
# User feedback history
# ---------------------------------------------------------------------------


@router.get("/api/feedback/mine")
async def list_my_feedback(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[FeedbackResponse]:
    q = (
        select(UserFeedback)
        .where(UserFeedback.user_id == current_user.id)
        .where(UserFeedback.deleted_at.is_(None))
        .order_by(UserFeedback.created_at.desc())
    )
    rows = (await db.execute(q)).scalars().all()
    return [_serialize(r) for r in rows]


# ---------------------------------------------------------------------------
# Submitter dispatch-status poll
# ---------------------------------------------------------------------------


class FeedbackStatusResponse(BaseModel):
    dispatch_status: str
    github_discussion_url: str | None


@router.get("/api/feedback/{feedback_id}/status")
async def get_feedback_status(
    feedback_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> FeedbackStatusResponse:
    row = await db.get(UserFeedback, feedback_id)
    if not row or row.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Feedback not found")
    return FeedbackStatusResponse(
        dispatch_status=row.dispatch_status,
        github_discussion_url=row.github_discussion_url,
    )


# ---------------------------------------------------------------------------
# Admin endpoints
# ---------------------------------------------------------------------------


@router.get("/api/admin/feedback")
async def list_feedback(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    submission_type: str | None = None,
    dispatch_status: str | None = None,
    include_deleted: bool = False,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> FeedbackPage:
    from sqlalchemy.orm import selectinload

    q = select(UserFeedback).options(selectinload(UserFeedback.user))
    if not include_deleted:
        q = q.where(UserFeedback.deleted_at.is_(None))
    if submission_type:
        q = q.where(UserFeedback.submission_type == submission_type)
    if dispatch_status:
        q = q.where(UserFeedback.dispatch_status == dispatch_status)

    total_q = select(func.count()).select_from(q.subquery())
    total = (await db.execute(total_q)).scalar_one()

    q = q.order_by(UserFeedback.created_at.desc())
    q = q.offset((page - 1) * page_size).limit(page_size)
    rows = (await db.execute(q)).scalars().all()

    pages = max(1, (total + page_size - 1) // page_size)
    return FeedbackPage(
        items=[_serialize(r, include_user_email=True) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
        pages=pages,
    )


@router.get("/api/admin/feedback/{feedback_id}")
async def get_feedback_detail(
    feedback_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> FeedbackResponse:
    from sqlalchemy.orm import selectinload

    row = (
        await db.execute(
            select(UserFeedback).options(selectinload(UserFeedback.user)).where(UserFeedback.id == feedback_id)
        )
    ).scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=404, detail="Feedback not found")
    return _serialize(row, include_user_email=True)


@router.delete("/api/admin/feedback/{feedback_id}")
async def soft_delete_feedback(
    feedback_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> FeedbackResponse:
    row = await db.get(UserFeedback, feedback_id)
    if not row:
        raise HTTPException(status_code=404, detail="Feedback not found")
    row.soft_delete()
    await db.commit()
    await db.refresh(row)
    return _serialize(row)


@router.post("/api/admin/feedback/{feedback_id}/retry-dispatch")
async def retry_feedback_dispatch(
    feedback_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> FeedbackResponse:
    row = await db.get(UserFeedback, feedback_id)
    if not row:
        raise HTTPException(status_code=404, detail="Feedback not found")
    if row.dispatch_status not in ("pending", "failed"):
        raise HTTPException(status_code=400, detail=f"Cannot retry dispatch with status '{row.dispatch_status}'")
    row.dispatch_status = "pending"
    row.dispatch_error = None
    await db.commit()
    await db.refresh(row)
    _enqueue_dispatch(str(row.id))
    return _serialize(row, include_user_email=True)


@router.post("/api/admin/feedback/{feedback_id}/recover")
async def recover_feedback(
    feedback_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
) -> FeedbackResponse:
    row = await db.get(UserFeedback, feedback_id)
    if not row:
        raise HTTPException(status_code=404, detail="Feedback not found")
    if not row.is_deleted:
        raise HTTPException(status_code=400, detail="Feedback is not deleted")
    row.deleted_at = None
    await db.commit()
    await db.refresh(row)
    return _serialize(row)
