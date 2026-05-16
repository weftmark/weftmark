"""Celery tasks: pre-generate draft preview images.

generate_drawdown_preview  — per-draft task dispatched on WIF upload
backfill_all_drawdown_previews — bulk task dispatched by post_migrate for
                                  drafts missing drawdown_preview_path
"""

import asyncio
import logging
import uuid

from celery import Task
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.celery_app import celery_app

log = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    max_retries=2,
    default_retry_delay=30,
    soft_time_limit=120,
    time_limit=150,
    name="app.tasks.preview.generate_drawdown_preview",
)
def generate_drawdown_preview(self: Task, draft_id: str) -> None:
    asyncio.run(_generate_preview(self, uuid.UUID(draft_id)))


async def _generate_preview(task: Task, draft_id: uuid.UUID) -> None:
    from app.config import get_settings
    from app.models.draft import Draft
    from app.services import rendering, storage

    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    try:
        async with async_session() as db:
            draft = await db.get(Draft, draft_id)
            if draft is None or draft.deleted_at is not None:
                return
            if not draft.wif_path or not storage.file_exists(draft.wif_path):
                log.warning("preview_task_skip draft_id=%s reason=no_wif", draft_id)
                return

            try:
                wif_bytes = storage.read_file(draft.wif_path)
                wif_draft = rendering.load_draft(wif_bytes)

                # Full color preview (threading + tie-up + drawdown) if not yet generated
                if not draft.preview_path:
                    try:
                        png_full = rendering.render_full_draft(wif_draft)
                        draft.preview_path = storage.save_preview(draft.id, png_full)
                    except Exception as exc:
                        log.warning("preview_task_full_failed draft_id=%s error=%s", draft_id, exc)

                # Reduced drawdown preview for the project screen
                png, scale = rendering.render_drawdown_preview(wif_draft, settings.drawdown_preview_max_px)
                preview_path = storage.save_drawdown_preview(png)
                draft.drawdown_preview_path = preview_path
                draft.drawdown_preview_scale = scale
                await db.commit()
                log.info("preview_task_done draft_id=%s scale=%s", draft_id, scale)
            except Exception as exc:
                log.warning("preview_task_failed draft_id=%s error=%s", draft_id, exc)
                try:
                    raise task.retry(exc=exc)
                except task.MaxRetriesExceededError:
                    pass
    finally:
        await engine.dispose()


@celery_app.task(
    bind=True,
    max_retries=0,
    soft_time_limit=300,
    time_limit=360,
    name="app.tasks.preview.backfill_all_drawdown_previews",
)
def backfill_all_drawdown_previews(self: Task) -> dict:
    """Dispatch generate_drawdown_preview for every draft missing a thumbnail PNG."""
    return asyncio.run(_backfill_all_previews())


async def _backfill_all_previews() -> dict:
    from sqlalchemy import select

    from app.config import get_settings
    from app.models.draft import Draft
    from app.services import storage

    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    dispatched = skipped = 0
    try:
        async with async_session() as db:
            drafts = (
                await db.scalars(
                    select(Draft)
                    .where(
                        Draft.deleted_at.is_(None),
                        Draft.drawdown_preview_path.is_(None),
                        Draft.wif_path.isnot(None),
                    )
                    .order_by(Draft.created_at)
                )
            ).all()

            for draft in drafts:
                if not storage.file_exists(draft.wif_path):
                    skipped += 1
                    continue
                generate_drawdown_preview.delay(str(draft.id))
                dispatched += 1
    finally:
        await engine.dispose()

    result = {"dispatched": dispatched, "skipped": skipped}
    log.info("backfill_all_drawdown_previews_complete %s", result)
    return result
