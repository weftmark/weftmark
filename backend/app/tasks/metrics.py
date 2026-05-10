"""Celery task: periodic DB-backed business metric gauges.

Runs every 5 minutes via beat. Queries the database for entity counts and
storage totals, then updates the in-process gauge cache so the OTel
PeriodicExportingMetricReader can export them on its next collection cycle.
"""

import logging

from app.celery_app import celery_app

log = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    max_retries=0,
    name="app.tasks.metrics.record_business_metrics",
)
def record_business_metrics(self) -> dict:
    from sqlalchemy import create_engine, func, select
    from sqlalchemy.orm import Session

    from app.config import get_settings
    from app.metrics import update_gauge_cache
    from app.models.loom import Loom, LoomVersion, LoomVersionPhoto
    from app.models.pending_signup import PendingSignup
    from app.models.project import Project, ProjectPhoto
    from app.models.user import User
    from app.services.storage_quota import MAX_USER_STORAGE_BYTES

    settings = get_settings()
    engine = create_engine(settings.database_url_sync)

    try:
        with Session(engine) as db:
            users_total = (
                db.scalar(
                    select(func.count(User.id)).where(
                        User.clerk_user_id.is_not(None),
                        User.deleted_at.is_(None),
                        User.clerk_banned.is_(False),
                    )
                )
                or 0
            )

            pending_approval = db.scalar(select(func.count(PendingSignup.id))) or 0

            projects_total = db.scalar(select(func.count(Project.id))) or 0

            project_bytes = db.scalar(select(func.coalesce(func.sum(ProjectPhoto.file_size_bytes), 0))) or 0
            loom_bytes = (
                db.scalar(
                    select(func.coalesce(func.sum(LoomVersionPhoto.file_size_bytes), 0))
                    .join(LoomVersion, LoomVersionPhoto.loom_version_id == LoomVersion.id)
                    .join(Loom, LoomVersion.loom_id == Loom.id)
                )
                or 0
            )
            storage_used_bytes = int(project_bytes) + int(loom_bytes)

            # Count users whose per-user storage >= 90% of quota
            # Subquery: storage per user from project photos
            project_storage = (
                select(
                    Project.owner_id.label("user_id"),
                    func.coalesce(func.sum(ProjectPhoto.file_size_bytes), 0).label("bytes"),
                )
                .join(ProjectPhoto, ProjectPhoto.project_id == Project.id, isouter=True)
                .group_by(Project.owner_id)
                .subquery()
            )
            loom_storage = (
                select(
                    Loom.owner_id.label("user_id"),
                    func.coalesce(func.sum(LoomVersionPhoto.file_size_bytes), 0).label("bytes"),
                )
                .join(LoomVersion, LoomVersion.loom_id == Loom.id, isouter=True)
                .join(LoomVersionPhoto, LoomVersionPhoto.loom_version_id == LoomVersion.id, isouter=True)
                .group_by(Loom.owner_id)
                .subquery()
            )
            combined = (
                select(
                    func.coalesce(project_storage.c.user_id, loom_storage.c.user_id).label("user_id"),
                    (func.coalesce(project_storage.c.bytes, 0) + func.coalesce(loom_storage.c.bytes, 0)).label(
                        "total_bytes"
                    ),
                )
                .join(
                    loom_storage,
                    project_storage.c.user_id == loom_storage.c.user_id,
                    full=True,
                )
                .subquery()
            )
            threshold = MAX_USER_STORAGE_BYTES * 0.9
            users_at_quota = db.scalar(select(func.count()).where(combined.c.total_bytes >= threshold)) or 0

    finally:
        engine.dispose()

    update_gauge_cache("weftmark.users.total", users_total)
    update_gauge_cache("weftmark.users.pending_approval", pending_approval)
    update_gauge_cache("weftmark.projects.total", projects_total)
    update_gauge_cache("weftmark.storage.used_bytes", storage_used_bytes)
    update_gauge_cache("weftmark.storage.users_at_quota", users_at_quota)

    log.info(
        "record_business_metrics users=%d pending=%d projects=%d storage_mb=%.1f at_quota=%d",
        users_total,
        pending_approval,
        projects_total,
        storage_used_bytes / (1024 * 1024),
        users_at_quota,
    )
    return {
        "users_total": users_total,
        "pending_approval": pending_approval,
        "projects_total": projects_total,
        "storage_used_bytes": storage_used_bytes,
        "users_at_quota": users_at_quota,
    }
