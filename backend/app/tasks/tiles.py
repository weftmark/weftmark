"""Celery tasks: pre-render drawdown tiles for a draft or project and store them in R2.

prerender_drawdown_tiles — draft-keyed tiles (used by the draft library endpoint)
prerender_project_tiles  — project-keyed tiles (used by the project weaving view)
"""

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
    asyncio.run(_prerender_draft(self, uuid.UUID(draft_id)))


@celery_app.task(
    bind=True,
    max_retries=2,
    default_retry_delay=60,
    soft_time_limit=300,
    time_limit=360,
    name="app.tasks.tiles.prerender_project_tiles",
)
def prerender_project_tiles(self: Task, project_id: str) -> None:
    asyncio.run(_prerender_project(self, uuid.UUID(project_id)))


async def _prerender_draft(task: Task, draft_id: uuid.UUID) -> None:
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
                tile_count = _render_and_store_tiles(
                    wif_bytes,
                    settings,
                    rendering,
                    ImageRenderer,
                    PILImage,
                    lambda pid, scale, start, data: storage.save_drawdown_tile(draft_id, scale, start, data),
                    entity_id=draft_id,
                    entity_label="draft_id",
                )
                log.info("tile_prerender_done draft_id=%s tiles=%d", draft_id, tile_count)
            except Exception as exc:
                log.warning("tile_prerender_failed draft_id=%s error=%s", draft_id, exc)
                try:
                    raise task.retry(exc=exc)
                except task.MaxRetriesExceededError:
                    pass
    finally:
        await engine.dispose()


async def _prerender_project(task: Task, project_id: uuid.UUID) -> None:
    from PIL import Image as PILImage
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    from app.config import get_settings
    from app.models.draft import Draft
    from app.models.project import Project
    from app.services import rendering, storage
    from app.services.rendering import ImageRenderer

    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    try:
        async with async_session() as db:
            project = await db.get(Project, project_id)
            if project is None or project.deleted_at is not None:
                return

            draft = await db.get(Draft, project.draft_id)
            if draft is None or draft.deleted_at is not None:
                return

            wif_path = draft.wif_path
            if project.project_type == "lift" and draft.wif_modified_path:
                if storage.file_exists(draft.wif_modified_path):
                    wif_path = draft.wif_modified_path

            if not wif_path or not storage.file_exists(wif_path):
                log.warning("tile_prerender_skip project_id=%s reason=no_wif", project_id)
                return

            try:
                wif_bytes = storage.read_file(wif_path)
                tile_count = _render_and_store_tiles(
                    wif_bytes,
                    settings,
                    rendering,
                    ImageRenderer,
                    PILImage,
                    lambda _pid, scale, start, data: storage.save_project_tile(project_id, scale, start, data),
                    entity_id=project_id,
                    entity_label="project_id",
                    color_replacements=project.color_replacements or {},
                )
                log.info("tile_prerender_done project_id=%s tiles=%d", project_id, tile_count)
            except Exception as exc:
                log.warning("tile_prerender_failed project_id=%s error=%s", project_id, exc)
                try:
                    raise task.retry(exc=exc)
                except task.MaxRetriesExceededError:
                    pass
    finally:
        await engine.dispose()


def _render_and_store_tiles(
    wif_bytes: bytes,
    settings,
    rendering,
    ImageRenderer,
    PILImage,
    save_fn,
    entity_id: uuid.UUID,
    entity_label: str,
    color_replacements: dict | None = None,
) -> int:
    wif_draft = rendering.load_draft(wif_bytes)
    if color_replacements:
        rendering.apply_color_replacements(wif_draft, color_replacements)

    warp_count = len(wif_draft.warp)
    weft_count = len(wif_draft.weft)
    if warp_count <= 0 or weft_count <= 0:
        log.warning("tile_prerender_skip %s=%s reason=empty_draft", entity_label, entity_id)
        return 0

    effective_scale = min(settings.render_max_width // warp_count, rendering.DRAWDOWN_SCALE)
    if effective_scale < 1:
        log.warning("tile_prerender_skip %s=%s reason=too_wide", entity_label, entity_id)
        return 0

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
        save_fn(entity_id, effective_scale, tile_start, out.getvalue())
        tile_count += 1

    return tile_count
