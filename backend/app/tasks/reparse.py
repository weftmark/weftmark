"""Celery task: re-parse WIF measurements and color palette for all existing drafts."""

import asyncio
import logging

from celery import Task
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.celery_app import celery_app

log = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    max_retries=0,
    soft_time_limit=600,
    time_limit=660,
    name="app.tasks.reparse.reparse_all_drafts",
)
def reparse_all_drafts(self: Task) -> dict:
    return asyncio.run(_reparse_all())


async def _reparse_all() -> dict:
    from app.config import get_settings
    from app.models.draft import Draft
    from app.services import storage
    from app.services.wif_parser import extract_colors, extract_measurements, extract_weft_color_stats

    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    updated = skipped = errors = 0

    try:
        async with async_session() as db:
            drafts = (
                await db.scalars(select(Draft).where(Draft.deleted_at.is_(None)).order_by(Draft.created_at))
            ).all()

            for draft in drafts:
                if not draft.wif_path or not storage.file_exists(draft.wif_path):
                    skipped += 1
                    continue
                try:
                    wif_bytes = storage.read_file(draft.wif_path)
                    measurements = extract_measurements(wif_bytes)
                    colors = extract_colors(wif_bytes)

                    draft.wif_measurements = measurements or None
                    draft.wif_colors = colors or None
                    draft.weft_color_stats = extract_weft_color_stats(wif_bytes) or None

                    # Only update warp_length_cm if the user hasn't manually overridden it.
                    if not draft.warp_length_overridden:
                        draft.warp_length_cm = measurements.get("warp_length")

                    updated += 1
                except Exception as exc:
                    log.warning("reparse_draft_failed draft_id=%s error=%s", draft.id, exc)
                    errors += 1

            await db.commit()
    finally:
        await engine.dispose()

    result = {"updated": updated, "skipped": skipped, "errors": errors}
    log.info("reparse_all_drafts_complete %s", result)
    return result
