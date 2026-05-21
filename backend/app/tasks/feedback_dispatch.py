"""Celery task: dispatch user feedback to GitHub Discussions + send confirmation emails."""

import asyncio
import logging
import uuid

from app.celery_app import celery_app

log = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    name="app.tasks.feedback_dispatch.dispatch_feedback",
    max_retries=3,
    soft_time_limit=60,
    time_limit=90,
)
def dispatch_feedback(self, feedback_id: str) -> dict:
    """Post feedback to GitHub Discussions and update dispatch_status."""
    return asyncio.run(_dispatch(self, feedback_id))


async def _dispatch(task, feedback_id: str) -> dict:
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from app.config import get_settings
    from app.database import CeleryAsyncSession
    from app.models.feedback import UserFeedback
    from app.services.github_discussions import (
        build_discussion_body,
        build_discussion_title,
        create_discussion,
        get_discussion_state,
    )

    settings = get_settings()
    if not settings.github_feedback_token:
        log.info("feedback_dispatch skipped — no token feedback_id=%s", feedback_id)
        async with CeleryAsyncSession() as db:
            row = await db.get(UserFeedback, uuid.UUID(feedback_id))
            if row:
                row.dispatch_status = "skipped"
                await db.commit()
        return {"status": "skipped"}

    async with CeleryAsyncSession() as db:
        row = (
            await db.execute(
                select(UserFeedback)
                .options(selectinload(UserFeedback.user))
                .where(UserFeedback.id == uuid.UUID(feedback_id))
            )
        ).scalar_one_or_none()
        if not row:
            log.warning("feedback_dispatch feedback_id=%s not found", feedback_id)
            return {"status": "not_found"}

        title = build_discussion_title(row.submission_type, row.subject)
        body = build_discussion_body(
            submission_type=row.submission_type,
            subject=row.subject,
            body=row.body,
            diagnostics=row.diagnostics,
            is_anonymous=row.is_anonymous,
        )

        try:
            url = await create_discussion(
                token=settings.github_feedback_token,
                repo=settings.github_feedback_repo,
                submission_type=row.submission_type,
                title=title,
                body=body,
            )
            row.github_discussion_url = url
            row.dispatch_status = "sent"
            row.dispatch_error = None
            row.github_discussion_state = await get_discussion_state(settings.github_feedback_token, url)
            await db.commit()
            log.info("feedback_dispatch sent feedback_id=%s url=%s", feedback_id, url)

        except Exception as exc:
            row.dispatch_status = "failed"
            row.dispatch_error = str(exc)[:500]
            await db.commit()
            log.exception("feedback_dispatch failed feedback_id=%s", feedback_id)
            countdown = min(60 * (2**task.request.retries), 1800)
            raise task.retry(exc=exc, countdown=countdown)

    # Send emails after successful dispatch (fire and forget; don't retry on email failure)
    try:
        await _send_emails(feedback_id, url, settings)
    except Exception:
        log.exception("feedback_dispatch email failed feedback_id=%s — ignoring", feedback_id)

    return {"status": "sent", "url": url}


async def _send_emails(feedback_id: str, discussion_url: str, settings) -> None:
    from sqlalchemy import select
    from sqlalchemy.orm import selectinload

    from app.database import CeleryAsyncSession
    from app.models.feedback import UserFeedback
    from app.models.user import User
    from app.services import email as mail_svc
    from app.services.github_discussions import _type_label

    async with CeleryAsyncSession() as db:
        row = (
            await db.execute(
                select(UserFeedback)
                .options(selectinload(UserFeedback.user))
                .where(UserFeedback.id == uuid.UUID(feedback_id))
            )
        ).scalar_one_or_none()
        if not row:
            return
        type_label = _type_label(row.submission_type)

        # Admin alert
        admin_emails = (
            (
                await db.execute(
                    select(User.email).where(User.is_admin == True, User.is_active == True, User.deleted_at.is_(None))  # noqa: E712
                )
            )
            .scalars()
            .all()
        )
        if admin_emails:
            await mail_svc.send_feedback_admin_alert(list(admin_emails), type_label, discussion_url, row.subject)

        # User confirmation (non-anonymous authenticated users only; email from relationship)
        if not row.is_anonymous and row.user and row.user.email:
            await mail_svc.send_feedback_user_confirmation(row.user.email, type_label, discussion_url)


@celery_app.task(
    bind=True,
    name="app.tasks.feedback_dispatch.retry_failed_feedback",
    max_retries=0,
    soft_time_limit=120,
    time_limit=150,
)
def retry_failed_feedback(self, limit: int = 20) -> dict:
    """Re-dispatch feedback submissions that failed to post to GitHub Discussions."""
    return asyncio.run(_retry_failed(limit))


async def _retry_failed(limit: int) -> dict:
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import or_, select

    from app.config import get_settings
    from app.database import CeleryAsyncSession
    from app.models.feedback import UserFeedback
    from app.services.task_history import record_queued

    settings = get_settings()
    if not settings.github_feedback_token:
        return {"dispatched": 0, "reason": "no_token"}

    stale_cutoff = datetime.now(timezone.utc) - timedelta(minutes=10)

    async with CeleryAsyncSession() as db:
        rows = (
            (
                await db.execute(
                    select(UserFeedback.id)
                    .where(UserFeedback.deleted_at.is_(None))
                    .where(
                        or_(
                            UserFeedback.dispatch_status == "failed",
                            (UserFeedback.dispatch_status == "pending") & (UserFeedback.created_at < stale_cutoff),
                        )
                    )
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )

    dispatched = 0
    for row_id in rows:
        t = dispatch_feedback.delay(str(row_id))
        record_queued(settings, t.id, "app.tasks.feedback_dispatch.dispatch_feedback", "feedback:retry")
        dispatched += 1

    log.info("retry_failed_feedback dispatched=%d", dispatched)
    return {"dispatched": dispatched}


@celery_app.task(
    bind=True,
    name="app.tasks.feedback_dispatch.purge_deleted_feedback",
    max_retries=0,
    soft_time_limit=60,
    time_limit=90,
)
def purge_deleted_feedback(self, retention_days: int = 7) -> dict:
    """Hard-delete feedback that has been soft-deleted for longer than retention_days."""
    return asyncio.run(_purge_deleted(retention_days))


async def _purge_deleted(retention_days: int) -> dict:
    from datetime import datetime, timedelta, timezone

    from sqlalchemy import delete

    from app.database import CeleryAsyncSession
    from app.models.feedback import UserFeedback

    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    async with CeleryAsyncSession() as db:
        result = await db.execute(
            delete(UserFeedback).where(
                UserFeedback.deleted_at.is_not(None),
                UserFeedback.deleted_at < cutoff,
            )
        )
        await db.commit()

    deleted = result.rowcount
    log.info("purge_deleted_feedback deleted=%d retention_days=%d", deleted, retention_days)
    return {"deleted": deleted}


@celery_app.task(
    bind=True,
    name="app.tasks.feedback_dispatch.sync_discussion_states",
    max_retries=0,
    soft_time_limit=120,
    time_limit=150,
)
def sync_discussion_states(self, limit: int = 100) -> dict:
    """Sync github_discussion_state for all sent feedback with a discussion URL."""
    return asyncio.run(_sync_states(limit))


async def _sync_states(limit: int) -> dict:
    from sqlalchemy import select

    from app.config import get_settings
    from app.database import CeleryAsyncSession
    from app.models.feedback import UserFeedback
    from app.services.github_discussions import get_discussion_state

    settings = get_settings()
    if not settings.github_feedback_token:
        return {"updated": 0, "reason": "no_token"}

    async with CeleryAsyncSession() as db:
        rows = (
            (
                await db.execute(
                    select(UserFeedback)
                    .where(UserFeedback.deleted_at.is_(None))
                    .where(UserFeedback.dispatch_status == "sent")
                    .where(UserFeedback.github_discussion_url.is_not(None))
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )

        updated = 0
        for row in rows:
            state = await get_discussion_state(settings.github_feedback_token, row.github_discussion_url)
            if state is not None and state != row.github_discussion_state:
                row.github_discussion_state = state
                updated += 1

        if updated:
            await db.commit()

    log.info("sync_discussion_states updated=%d", updated)
    return {"updated": updated}
