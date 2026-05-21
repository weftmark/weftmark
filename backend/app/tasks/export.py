"""Celery task: build a data export archive for a user.

Packages WIF files, project photos, and JSON records for all user data
into a ZIP archive, uploads it to storage, and emails the user a download link.
"""

import asyncio
import io
import json
import logging
import re
import uuid
import zipfile
from datetime import datetime, timedelta, timezone

from celery import Task
from celery.exceptions import SoftTimeLimitExceeded
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.celery_app import celery_app

log = logging.getLogger(__name__)

EXPORT_TTL_DAYS = 7


@celery_app.task(
    bind=True,
    max_retries=1,
    default_retry_delay=120,
    soft_time_limit=300,
    time_limit=360,
    name="app.tasks.export.run_user_export",
)
def run_user_export(self: Task, user_id: str, request_id: str) -> None:
    asyncio.run(_build_export(uuid.UUID(user_id), uuid.UUID(request_id)))


async def _build_export(user_id: uuid.UUID, request_id: uuid.UUID) -> None:
    from sqlalchemy import select

    from app.config import get_settings
    from app.models.collection import Collection
    from app.models.draft import Draft
    from app.models.loom import Loom
    from app.models.project import Project, ProjectPhoto
    from app.models.user import User
    from app.models.user_export import UserExportRequest
    from app.models.yarn import Yarn
    from app.services import storage

    settings = get_settings()
    engine = create_async_engine(settings.database_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as db:
        req = await db.get(UserExportRequest, request_id)
        if req is None:
            log.warning("export_task_skip request_id=%s reason=not_found", request_id)
            return

        user = await db.get(User, user_id)
        if user is None:
            req.status = "failed"
            req.error = "User not found"
            await db.commit()
            return

        try:
            date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            prefix = f"weftmark-export-{date_str}"
            buf = io.BytesIO()

            with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                # ── Drafts ────────────────────────────────────────────────────
                drafts = (
                    await db.scalars(select(Draft).where(Draft.owner_id == user_id, Draft.deleted_at.is_(None)))
                ).all()

                drafts_json = []
                for d in drafts:
                    drafts_json.append(
                        {
                            "id": str(d.id),
                            "title": d.title,
                            "created_at": d.created_at.isoformat(),
                            "updated_at": d.updated_at.isoformat(),
                        }
                    )
                    if d.wif_path:
                        try:
                            wif_bytes = await storage.aread_file(d.wif_path)
                            safe = _safe_filename(d.title or str(d.id))
                            zf.writestr(f"{prefix}/drafts/{safe}.wif", wif_bytes)
                        except Exception as exc:
                            log.warning("export_skip_wif draft_id=%s error=%s", d.id, exc)

                zf.writestr(f"{prefix}/data/drafts.json", json.dumps(drafts_json, indent=2))

                # ── Projects + photos ─────────────────────────────────────────
                projects = (
                    await db.scalars(select(Project).where(Project.owner_id == user_id, Project.deleted_at.is_(None)))
                ).all()

                projects_json = []
                for p in projects:
                    projects_json.append(
                        {
                            "id": str(p.id),
                            "title": p.title,
                            "status": p.status,
                            "start_date": p.start_date.isoformat() if p.start_date else None,
                            "end_date": p.end_date.isoformat() if p.end_date else None,
                            "notes": p.notes,
                            "created_at": p.created_at.isoformat(),
                        }
                    )
                    photos = (await db.scalars(select(ProjectPhoto).where(ProjectPhoto.project_id == p.id))).all()
                    safe_proj = _safe_filename(p.title or str(p.id))
                    for i, photo in enumerate(photos):
                        try:
                            photo_bytes = await storage.aread_file(photo.file_path)
                            ext = photo.file_path.rsplit(".", 1)[-1] if "." in photo.file_path else "jpg"
                            zf.writestr(f"{prefix}/projects/{safe_proj}/photos/{i + 1}.{ext}", photo_bytes)
                        except Exception as exc:
                            log.warning("export_skip_photo photo_id=%s error=%s", photo.id, exc)

                zf.writestr(f"{prefix}/data/projects.json", json.dumps(projects_json, indent=2))

                # ── Yarn ─────────────────────────────────────────────────────
                yarns = (
                    await db.scalars(select(Yarn).where(Yarn.owner_id == user_id, Yarn.deleted_at.is_(None)))
                ).all()
                yarns_json = [
                    {
                        "id": str(y.id),
                        "name": y.name,
                        "brand": y.brand,
                        "colorway": y.colorway,
                        "fiber_content": y.fiber_content,
                        "weight": y.weight,
                        "created_at": y.created_at.isoformat(),
                    }
                    for y in yarns
                ]
                zf.writestr(f"{prefix}/data/yarn.json", json.dumps(yarns_json, indent=2))

                # ── Looms ─────────────────────────────────────────────────────
                looms = (
                    await db.scalars(select(Loom).where(Loom.owner_id == user_id, Loom.deleted_at.is_(None)))
                ).all()
                looms_json = [
                    {
                        "id": str(lo.id),
                        "name": lo.name,
                        "loom_type": lo.loom_type,
                        "created_at": lo.created_at.isoformat(),
                    }
                    for lo in looms
                ]
                zf.writestr(f"{prefix}/data/looms.json", json.dumps(looms_json, indent=2))

                # ── Collections ───────────────────────────────────────────────
                collections = (
                    await db.scalars(
                        select(Collection).where(Collection.owner_id == user_id, Collection.deleted_at.is_(None))
                    )
                ).all()
                collections_json = [
                    {
                        "id": str(c.id),
                        "name": c.name,
                        "created_at": c.created_at.isoformat(),
                    }
                    for c in collections
                ]
                zf.writestr(f"{prefix}/data/collections.json", json.dumps(collections_json, indent=2))

                # ── Profile ───────────────────────────────────────────────────
                zf.writestr(
                    f"{prefix}/data/profile.json",
                    json.dumps(
                        {
                            "display_name": user.display_name,
                            "email": user.email,
                            "created_at": user.created_at.isoformat(),
                            "exported_at": datetime.now(timezone.utc).isoformat(),
                        },
                        indent=2,
                    ),
                )

                # ── README ────────────────────────────────────────────────────
                zf.writestr(f"{prefix}/README.txt", _readme(user, date_str))

            archive_key = f"exports/{user_id}/{request_id}.zip"
            await asyncio.to_thread(storage._put, archive_key, buf.getvalue())

            req.status = "complete"
            req.archive_path = archive_key
            req.expires_at = datetime.now(timezone.utc) + timedelta(days=EXPORT_TTL_DAYS)
            await db.commit()

            log.info("export_complete user_id=%s request_id=%s", user_id, request_id)

            try:
                from app.services.email import send_export_ready

                await send_export_ready(user.email, user.display_name or "there", EXPORT_TTL_DAYS)
            except Exception as exc:
                log.warning("export_email_failed user_id=%s error=%s", user_id, exc)

        except SoftTimeLimitExceeded:
            req.status = "failed"
            req.error = "Task timed out"
            await db.commit()
            raise

        except Exception as exc:
            log.error("export_failed user_id=%s request_id=%s error=%s", user_id, request_id, exc, exc_info=True)
            req.status = "failed"
            req.error = str(exc)[:500]
            await db.commit()


def _safe_filename(name: str) -> str:
    safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)
    return safe[:80].strip("._") or "untitled"


def _readme(user, date_str: str) -> str:
    return (
        "weftmark Data Export\n"
        "====================\n\n"
        f"Exported:  {date_str}\n"
        f"Account:   {user.display_name} <{user.email}>\n\n"
        "Contents\n"
        "--------\n"
        "  drafts/                  WIF files for each of your drafts\n"
        "  projects/<name>/photos/  Project photos\n"
        "  data/profile.json        Account details\n"
        "  data/drafts.json         Draft metadata\n"
        "  data/projects.json       Project records\n"
        "  data/yarn.json           Yarn inventory\n"
        "  data/looms.json          Loom inventory\n"
        "  data/collections.json    Collections\n\n"
        f"This archive is valid for {EXPORT_TTL_DAYS} days from the export date.\n"
    )
