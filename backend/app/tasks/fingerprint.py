"""Celery tasks: compute the drawdown structural fingerprint for drafts (#983).

compute_draft_drawdown_fingerprint  — per-draft task dispatched on WIF upload
backfill_all_drawdown_fingerprints  — bulk task for drafts missing drawdown_fingerprint

threading_fingerprint/tieup_fingerprint are cheap and computed synchronously
at upload time (see app.routers.drafts.create_draft) — only the expensive
O(warp x weft) drawdown_fingerprint needs background-task treatment.
"""

import asyncio
import logging
import uuid

from celery import Task
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.celery_app import celery_app

log = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    max_retries=2,
    default_retry_delay=30,
    soft_time_limit=120,
    time_limit=150,
    name="app.tasks.fingerprint.compute_draft_drawdown_fingerprint",
)
def compute_draft_drawdown_fingerprint(self: Task, draft_id: str) -> None:
    asyncio.run(_compute_drawdown_fingerprint(self, uuid.UUID(draft_id)))


async def _compute_drawdown_fingerprint(task: Task, draft_id: uuid.UUID) -> None:
    from app.config import get_settings
    from app.models.draft import Draft
    from app.services import fingerprints, storage

    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False)
    async_session = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with async_session() as db:
            draft = await db.get(Draft, draft_id)
            if draft is None or draft.deleted_at is not None:
                return
            if not draft.wif_path or not storage.file_exists(draft.wif_path):
                log.warning("fingerprint_task_skip draft_id=%s reason=no_wif", draft_id)
                return

            try:
                wif_bytes = storage.read_file(draft.wif_path)
                draft.drawdown_fingerprint = fingerprints.compute_drawdown_fingerprint(wif_bytes)
                await db.commit()
                log.info("fingerprint_task_done draft_id=%s", draft_id)
            except Exception as exc:
                log.warning("fingerprint_task_failed draft_id=%s error=%s", draft_id, exc)
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
    name="app.tasks.fingerprint.backfill_all_drawdown_fingerprints",
)
def backfill_all_drawdown_fingerprints(self: Task) -> dict:
    """Dispatch compute_draft_drawdown_fingerprint for every draft missing one."""
    return asyncio.run(_backfill_all_drawdown_fingerprints())


async def _backfill_all_drawdown_fingerprints() -> dict:
    from sqlalchemy import select

    from app.config import get_settings
    from app.models.draft import Draft
    from app.services import storage

    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False)
    async_session = async_sessionmaker(engine, expire_on_commit=False)

    dispatched = skipped = 0
    try:
        async with async_session() as db:
            drafts = (
                await db.scalars(
                    select(Draft)
                    .where(
                        Draft.deleted_at.is_(None),
                        Draft.drawdown_fingerprint.is_(None),
                        Draft.wif_path.isnot(None),
                    )
                    .order_by(Draft.created_at)
                )
            ).all()

            for draft in drafts:
                if not storage.file_exists(draft.wif_path):
                    skipped += 1
                    continue
                compute_draft_drawdown_fingerprint.delay(str(draft.id))
                dispatched += 1
    finally:
        await engine.dispose()

    result = {"dispatched": dispatched, "skipped": skipped}
    log.info("backfill_all_drawdown_fingerprints_complete %s", result)
    return result
