"""Celery task: pre-render drawdown tiles for a draft and store them in R2."""

from __future__ import annotations

import asyncio
import io
import logging
import uuid

from celery import Task

from app.celery_app import celery_app

log = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    max_retries=2,
    default_retry_delay=60,
    soft_time_limit=300,
    time_limit=360,
    name="app.tasks.tiles.prerender_drawdown_tiles",
)
def prerender_drawdown_tiles(self: Task, draft_id: str) -> None:
    asyncio.run(_prerender(self, uuid.UUID(draft_id)))


async def _prerender(task: Task, draft_id: uuid.UUID) -> None:
    from PIL import Image as PILImage
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    from app.config import get_settings
    from app.models.draft import Draft
    from app.services import rendering, storage
    from app.services.rendering import ImageRenderer

    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    try:
        async with async_session() as db:
            draft = await db.get(Draft, draft_id)
            if draft is None or draft.deleted_at is not None:
                return
            if not draft.wif_path or not storage.file_exists(draft.wif_path):
                log.warning("tile_prerender_skip draft_id=%s reason=no_wif", draft_id)
                return

            try:
                wif_bytes = storage.read_file(draft.wif_path)
                wif_draft = rendering.load_draft(wif_bytes)

                warp_count = len(wif_draft.warp)
                weft_count = len(wif_draft.weft)
                if warp_count <= 0 or weft_count <= 0:
                    log.warning("tile_prerender_skip draft_id=%s reason=empty_draft", draft_id)
                    return

                effective_scale = min(settings.render_max_width // warp_count, rendering.DRAWDOWN_SCALE)
                if effective_scale < 1:
                    log.warning("tile_prerender_skip draft_id=%s reason=too_wide", draft_id)
                    return

                margin = 20
                renderer = ImageRenderer(wif_draft, scale=effective_scale, margin_pixels=margin)
                full_im = renderer.make_pil_image()

                offsetx = margin
                offsety = margin + (6 + len(wif_draft.shafts)) * effective_scale
                drawdown_w = warp_count * effective_scale
                drawdown_h = weft_count * effective_scale
                full_drawdown = full_im.crop((offsetx, offsety, offsetx + drawdown_w, offsety + drawdown_h))
                full_drawdown = full_drawdown.transpose(PILImage.Transpose.FLIP_TOP_BOTTOM)

                tile_row_count = settings.tile_row_count
                tile_count = 0
                for tile_start in range(0, weft_count, tile_row_count):
                    tile_end = min(tile_start + tile_row_count, weft_count)
                    tile_px_top = tile_start * effective_scale
                    tile_px_bottom = tile_end * effective_scale
                    tile_im = full_drawdown.crop((0, tile_px_top, drawdown_w, tile_px_bottom))
                    out = io.BytesIO()
                    tile_im.save(out, format="PNG")
                    storage.save_drawdown_tile(draft_id, effective_scale, tile_start, out.getvalue())
                    tile_count += 1

                log.info(
                    "tile_prerender_done draft_id=%s scale=%d tiles=%d",
                    draft_id,
                    effective_scale,
                    tile_count,
                )
            except Exception as exc:
                log.warning("tile_prerender_failed draft_id=%s error=%s", draft_id, exc)
                try:
                    raise task.retry(exc=exc)
                except task.MaxRetriesExceededError:
                    pass
    finally:
        await engine.dispose()
