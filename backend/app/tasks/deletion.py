"""Celery task: cascade-delete all data for a soft-deleted user.

The task is dispatched by the deletion service immediately after soft-delete.
It creates its own DB session (separate Celery worker process).
"""

import asyncio
import logging
import uuid

from celery import Task
from celery.exceptions import SoftTimeLimitExceeded
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.celery_app import celery_app

log = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    soft_time_limit=600,
    time_limit=660,
    name="app.tasks.deletion.run_user_deletion",
)
def run_user_deletion(self: Task, user_id: str) -> None:
    asyncio.run(_delete_user(self, uuid.UUID(user_id)))


async def _delete_user(task: Task, user_id: uuid.UUID) -> None:
    from app.config import get_settings
    from app.models.draft import Draft
    from app.models.invite import Invite
    from app.models.loom import Loom, LoomVersion, LoomVersionAccessory, LoomVersionPhoto, LoomVersionReceipt
    from app.models.pending_signup import PendingSignup
    from app.models.project import Project, ProjectPhoto, ProjectStep
    from app.models.user import User
    from app.models.user_identity import UserIdentity
    from app.models.yarn import Skein, Yarn
    from app.services import storage

    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False)
    async_session = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with async_session() as db:
            user = await db.get(User, user_id)
            if user is None:
                log.warning("deletion_task_skip user_id=%s reason=not_found", user_id)
                return
            if user.deletion_state == "complete":
                log.info("deletion_task_skip user_id=%s reason=already_complete", user_id)
                return

            user_email = user.email
            user_display = user.display_name

            try:
                user.deletion_state = "in_progress"
                await db.commit()
                log.info("deletion_task_started user_id=%s", user_id)

                # --- Storage purge ---
                await _purge_storage(db, user_id, storage)

                # --- DB cascade ---
                project_ids_subq = select(Project.id).where(Project.owner_id == user_id)
                await db.execute(delete(ProjectStep).where(ProjectStep.project_id.in_(project_ids_subq)))
                await db.execute(delete(ProjectPhoto).where(ProjectPhoto.project_id.in_(project_ids_subq)))
                await db.execute(delete(Project).where(Project.owner_id == user_id))

                yarn_ids_subq = select(Yarn.id).where(Yarn.owner_id == user_id)
                await db.execute(delete(Skein).where(Skein.yarn_id.in_(yarn_ids_subq)))
                await db.execute(delete(Yarn).where(Yarn.owner_id == user_id))

                loom_ids_subq = select(Loom.id).where(Loom.owner_id == user_id)
                version_ids_subq = select(LoomVersion.id).where(LoomVersion.loom_id.in_(loom_ids_subq))
                await db.execute(
                    delete(LoomVersionAccessory).where(LoomVersionAccessory.loom_version_id.in_(version_ids_subq))
                )
                await db.execute(
                    delete(LoomVersionReceipt).where(LoomVersionReceipt.loom_version_id.in_(version_ids_subq))
                )
                await db.execute(delete(LoomVersionPhoto).where(LoomVersionPhoto.loom_version_id.in_(version_ids_subq)))
                await db.execute(delete(LoomVersion).where(LoomVersion.loom_id.in_(loom_ids_subq)))
                await db.execute(delete(Loom).where(Loom.owner_id == user_id))

                await db.execute(delete(Draft).where(Draft.owner_id == user_id))
                await db.execute(delete(Invite).where(Invite.created_by_id == user_id))
                await db.execute(delete(UserIdentity).where(UserIdentity.user_id == user_id))

                # Resolve any lingering pending signups for this Clerk user
                if user.clerk_user_id:
                    await db.execute(delete(PendingSignup).where(PendingSignup.clerk_user_id == user.clerk_user_id))

                user.deletion_state = "complete"
                await db.commit()
                log.info("deletion_task_complete user_id=%s email=%s", user_id, user_email)

            except SoftTimeLimitExceeded:
                user.deletion_state = "stalled"
                await db.commit()
                log.warning("deletion_task_stalled user_id=%s reason=soft_time_limit", user_id)
                await _notify_stalled(db, user_id, user_email, user_display)
                raise

            except Exception as exc:
                log.exception("deletion_task_error user_id=%s attempt=%s", user_id, task.request.retries + 1)
                if task.request.retries >= task.max_retries:
                    user.deletion_state = "stalled"
                    await db.commit()
                    await _notify_stalled(db, user_id, user_email, user_display)
                else:
                    raise task.retry(exc=exc)

            else:
                await _notify_admins_complete(db, user_email, user_display)

    finally:
        await engine.dispose()


async def _delete_project_files(db: AsyncSession, user_id: uuid.UUID, storage) -> None:
    from app.models.project import Project, ProjectPhoto

    photos = await db.scalars(
        select(ProjectPhoto).join(Project, ProjectPhoto.project_id == Project.id).where(Project.owner_id == user_id)
    )
    for p in photos.all():
        _safe_delete(storage, p.file_path)

    projects = await db.scalars(select(Project).where(Project.owner_id == user_id))
    for project in projects.all():
        try:
            storage.delete_project_tiles(project.id)
        except Exception as exc:
            log.warning("deletion_storage_error project_tiles project_id=%s error=%s", project.id, exc)


async def _delete_yarn_files(db: AsyncSession, user_id: uuid.UUID, storage) -> None:
    from app.models.yarn import Yarn

    yarns = await db.scalars(select(Yarn).where(Yarn.owner_id == user_id))
    for y in yarns.all():
        if y.photo_path:
            _safe_delete(storage, y.photo_path)


async def _delete_loom_files(db: AsyncSession, user_id: uuid.UUID, storage) -> None:
    from app.models.loom import Loom, LoomVersion, LoomVersionPhoto, LoomVersionReceipt

    loom_ids = []
    for loom in (await db.scalars(select(Loom).where(Loom.owner_id == user_id))).all():
        loom_ids.append(loom.id)
        if loom.photo_path:
            _safe_delete(storage, loom.photo_path)

    if loom_ids:
        versions = await db.scalars(select(LoomVersion).where(LoomVersion.loom_id.in_(loom_ids)))
        version_ids = [v.id for v in versions.all()]
        if version_ids:
            vp = await db.scalars(select(LoomVersionPhoto).where(LoomVersionPhoto.loom_version_id.in_(version_ids)))
            for lp in vp.all():
                _safe_delete(storage, lp.path)
            vr = await db.scalars(select(LoomVersionReceipt).where(LoomVersionReceipt.loom_version_id.in_(version_ids)))
            for r in vr.all():
                _safe_delete(storage, r.path)


async def _delete_draft_files(db: AsyncSession, user_id: uuid.UUID, storage) -> None:
    from app.models.draft import Draft

    drafts = await db.scalars(select(Draft).where(Draft.owner_id == user_id))
    for draft in drafts.all():
        if draft.wif_path:
            _safe_delete(storage, draft.wif_path)
        if draft.preview_path:
            _safe_delete(storage, draft.preview_path)


async def _purge_storage(db: AsyncSession, user_id: uuid.UUID, storage) -> None:
    await _delete_project_files(db, user_id, storage)
    await _delete_yarn_files(db, user_id, storage)
    await _delete_loom_files(db, user_id, storage)
    await _delete_draft_files(db, user_id, storage)


def _safe_delete(storage, path: str) -> None:
    try:
        storage._delete(path)
    except Exception as exc:
        log.warning("deletion_storage_error path=%s error=%s", path, exc)


async def _get_admin_emails(db: AsyncSession) -> list[str]:
    from app.models.user import User

    users = await db.scalars(select(User).where(User.is_admin.is_(True), User.deleted_at.is_(None)))
    return [u.email for u in users.all()]


async def _get_superuser_emails(db: AsyncSession) -> list[str]:
    from app.models.user import User

    users = await db.scalars(select(User).where(User.is_superuser.is_(True), User.deleted_at.is_(None)))
    return [u.email for u in users.all()]


async def _notify_admins_complete(db: AsyncSession, email: str, display_name: str) -> None:
    from app.services.email import send_deletion_completed_admin

    admin_emails = await _get_admin_emails(db)
    if admin_emails:
        try:
            await send_deletion_completed_admin(admin_emails, display_name, email)
        except Exception as exc:
            log.warning("deletion_notify_failed event=completed error=%s", exc)


async def _notify_stalled(db: AsyncSession, user_id: uuid.UUID, email: str, display_name: str) -> None:
    from app.services.email import send_deletion_stalled_superuser

    superuser_emails = await _get_superuser_emails(db)
    if superuser_emails:
        try:
            await send_deletion_stalled_superuser(superuser_emails, display_name, email, str(user_id))
        except Exception as exc:
            log.warning("deletion_notify_failed event=stalled error=%s", exc)
