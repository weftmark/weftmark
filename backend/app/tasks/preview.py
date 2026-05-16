"""Celery tasks: pre-generate draft and project preview images.

generate_drawdown_preview          — per-draft task dispatched on WIF upload
backfill_all_drawdown_previews     — bulk task for drafts missing drawdown_preview_path
generate_project_drawdown_preview  — per-project task dispatched on creation and color save
backfill_all_project_drawdown_previews — bulk task for projects missing drawdown_preview_path
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


@celery_app.task(
    bind=True,
    max_retries=2,
    default_retry_delay=30,
    soft_time_limit=120,
    time_limit=150,
    name="app.tasks.preview.generate_project_drawdown_preview",
)
def generate_project_drawdown_preview(self: Task, project_id: str) -> None:
    asyncio.run(_generate_project_preview(self, uuid.UUID(project_id)))


async def _generate_project_preview(task: Task, project_id: uuid.UUID) -> None:
    from app.config import get_settings
    from app.models.draft import Draft
    from app.models.project import Project
    from app.services import rendering, storage

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

            # Match the router's _wif_path_for_project logic
            if (
                project.project_type == "lift"
                and draft.wif_modified_path
                and storage.file_exists(draft.wif_modified_path)
            ):
                wif_path = draft.wif_modified_path
            else:
                wif_path = draft.wif_path
            if not wif_path or not storage.file_exists(wif_path):
                log.warning("project_preview_skip project_id=%s reason=no_wif", project_id)
                return

            try:
                wif_bytes = storage.read_file(wif_path)
                color_replacements = project.color_replacements or {}

                def _render() -> bytes:
                    d = rendering.load_draft(wif_bytes)
                    if color_replacements:
                        rendering.apply_color_replacements(d, color_replacements)
                    png, _ = rendering.render_drawdown_preview(d, settings.drawdown_preview_max_px)
                    return png

                png_bytes = await asyncio.to_thread(_render)
                old_path = project.drawdown_preview_path
                project.drawdown_preview_path = storage.save_project_drawdown_preview(png_bytes)
                await db.commit()
                if old_path:
                    try:
                        storage._delete(old_path)
                    except Exception:
                        pass
                log.info("project_preview_done project_id=%s", project_id)
            except Exception as exc:
                log.warning("project_preview_failed project_id=%s error=%s", project_id, exc)
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
    name="app.tasks.preview.backfill_all_project_drawdown_previews",
)
def backfill_all_project_drawdown_previews(self: Task) -> dict:
    """Dispatch generate_project_drawdown_preview for every project missing a thumbnail PNG."""
    return asyncio.run(_backfill_all_project_previews())


async def _backfill_all_project_previews() -> dict:
    from sqlalchemy import select

    from app.config import get_settings
    from app.models.draft import Draft
    from app.models.project import Project
    from app.services import storage

    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    dispatched = skipped = 0
    try:
        async with async_session() as db:
            projects = (
                await db.scalars(
                    select(Project)
                    .where(
                        Project.deleted_at.is_(None),
                        Project.drawdown_preview_path.is_(None),
                    )
                    .order_by(Project.created_at)
                )
            ).all()

            for project in projects:
                draft = await db.get(Draft, project.draft_id)
                if not draft or draft.deleted_at is not None:
                    skipped += 1
                    continue
                if (
                    project.project_type == "lift"
                    and draft.wif_modified_path
                    and storage.file_exists(draft.wif_modified_path)
                ):
                    wif_path = draft.wif_modified_path
                else:
                    wif_path = draft.wif_path
                if not wif_path or not storage.file_exists(wif_path):
                    skipped += 1
                    continue
                generate_project_drawdown_preview.delay(str(project.id))
                dispatched += 1
    finally:
        await engine.dispose()

    result = {"dispatched": dispatched, "skipped": skipped}
    log.info("backfill_all_project_drawdown_previews_complete %s", result)
    return result
