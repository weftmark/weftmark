"""Celery task: hard-delete soft-deleted records that have exceeded the retention period.

Covers Draft, Loom, Project, and Yarn. User deletion is handled separately
by run_user_deletion. Storage files associated with purged records are removed
before the DB rows are deleted.

Dispatched from the admin maintenance panel or by a future scheduled task.
"""

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from celery import Task
from celery.exceptions import SoftTimeLimitExceeded

from app.celery_app import celery_app

log = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    max_retries=0,
    soft_time_limit=300,
    time_limit=360,
    name="app.tasks.purge.purge_soft_deleted_records",
)
def purge_soft_deleted_records(self: Task, retention_days: int | None = None) -> dict:
    from app.config import get_settings

    days = retention_days if retention_days is not None else get_settings().soft_delete_retention_days
    return asyncio.run(_purge(days))


async def _purge_projects(db, cutoff: datetime, storage) -> int:
    from sqlalchemy import delete, select

    from app.models.project import Project, ProjectPhoto, ProjectStep

    project_ids = list(
        await db.scalars(select(Project.id).where(Project.deleted_at.is_not(None), Project.deleted_at < cutoff))
    )
    if project_ids:
        photos = await db.scalars(select(ProjectPhoto).where(ProjectPhoto.project_id.in_(project_ids)))
        for p in photos.all():
            _safe_delete(storage, p.file_path)
        await db.execute(delete(ProjectStep).where(ProjectStep.project_id.in_(project_ids)))
        await db.execute(delete(ProjectPhoto).where(ProjectPhoto.project_id.in_(project_ids)))
        await db.execute(delete(Project).where(Project.id.in_(project_ids)))
        await db.commit()
    log.info("purge_soft_deleted projects=%d cutoff=%s", len(project_ids), cutoff.date())
    return len(project_ids)


async def _purge_yarn(db, cutoff: datetime, storage) -> int:
    from sqlalchemy import delete, select

    from app.models.yarn import Skein, Yarn

    yarn_ids = list(await db.scalars(select(Yarn.id).where(Yarn.deleted_at.is_not(None), Yarn.deleted_at < cutoff)))
    if yarn_ids:
        yarns = await db.scalars(select(Yarn).where(Yarn.id.in_(yarn_ids)))
        for y in yarns.all():
            if y.photo_path:
                _safe_delete(storage, y.photo_path)
        await db.execute(delete(Skein).where(Skein.yarn_id.in_(yarn_ids)))
        await db.execute(delete(Yarn).where(Yarn.id.in_(yarn_ids)))
        await db.commit()
    log.info("purge_soft_deleted yarn=%d cutoff=%s", len(yarn_ids), cutoff.date())
    return len(yarn_ids)


async def _purge_looms(db, cutoff: datetime, storage) -> int:
    from sqlalchemy import delete, select

    from app.models.loom import Loom, LoomVersion, LoomVersionAccessory, LoomVersionPhoto, LoomVersionReceipt

    loom_ids = list(await db.scalars(select(Loom.id).where(Loom.deleted_at.is_not(None), Loom.deleted_at < cutoff)))
    if loom_ids:
        looms = await db.scalars(select(Loom).where(Loom.id.in_(loom_ids)))
        for loom in looms.all():
            if loom.photo_path:
                _safe_delete(storage, loom.photo_path)
        version_ids = list(await db.scalars(select(LoomVersion.id).where(LoomVersion.loom_id.in_(loom_ids))))
        if version_ids:
            vp = await db.scalars(select(LoomVersionPhoto).where(LoomVersionPhoto.loom_version_id.in_(version_ids)))
            for lp in vp.all():
                _safe_delete(storage, lp.path)
            vr = await db.scalars(select(LoomVersionReceipt).where(LoomVersionReceipt.loom_version_id.in_(version_ids)))
            for r in vr.all():
                _safe_delete(storage, r.path)
            await db.execute(delete(LoomVersionAccessory).where(LoomVersionAccessory.loom_version_id.in_(version_ids)))
            await db.execute(delete(LoomVersionReceipt).where(LoomVersionReceipt.loom_version_id.in_(version_ids)))
            await db.execute(delete(LoomVersionPhoto).where(LoomVersionPhoto.loom_version_id.in_(version_ids)))
            await db.execute(delete(LoomVersion).where(LoomVersion.id.in_(version_ids)))
        await db.execute(delete(Loom).where(Loom.id.in_(loom_ids)))
        await db.commit()
    log.info("purge_soft_deleted looms=%d cutoff=%s", len(loom_ids), cutoff.date())
    return len(loom_ids)


async def _purge_drafts(db, cutoff: datetime, storage) -> int:
    from sqlalchemy import delete, select

    from app.models.draft import Draft

    draft_ids = list(await db.scalars(select(Draft.id).where(Draft.deleted_at.is_not(None), Draft.deleted_at < cutoff)))
    if draft_ids:
        drafts = await db.scalars(select(Draft).where(Draft.id.in_(draft_ids)))
        for d in drafts.all():
            _safe_delete(storage, d.wif_path)
            if d.preview_path:
                _safe_delete(storage, d.preview_path)
            if d.drawdown_preview_path:
                _safe_delete(storage, d.drawdown_preview_path)
        await db.execute(delete(Draft).where(Draft.id.in_(draft_ids)))
        await db.commit()
    log.info("purge_soft_deleted drafts=%d cutoff=%s", len(draft_ids), cutoff.date())
    return len(draft_ids)


async def _purge(retention_days: int) -> dict:
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from app.config import get_settings
    from app.services import storage

    settings = get_settings()
    cutoff = datetime.now(timezone.utc) - timedelta(days=retention_days)
    engine = create_async_engine(settings.database_url, echo=False)
    async_session = async_sessionmaker(engine, expire_on_commit=False)
    counts: dict[str, int] = {}

    try:
        async with async_session() as db:
            try:
                counts["projects"] = await _purge_projects(db, cutoff, storage)
                counts["yarn"] = await _purge_yarn(db, cutoff, storage)
                counts["looms"] = await _purge_looms(db, cutoff, storage)
                counts["drafts"] = await _purge_drafts(db, cutoff, storage)

            except SoftTimeLimitExceeded:
                log.warning("purge_soft_deleted_stalled reason=soft_time_limit counts_so_far=%s", counts)
                raise

    finally:
        await engine.dispose()

    total = sum(counts.values())
    log.info("purge_soft_deleted_complete total=%d retention_days=%d counts=%s", total, retention_days, counts)
    return {"retention_days": retention_days, "total": total, **counts}


def _safe_delete(storage, path: str) -> None:
    try:
        storage._delete(path)
    except Exception as exc:
        log.warning("purge_storage_error path=%s error=%s", path, exc)
