import asyncio
import uuid
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.draft import Draft
from app.models.loom import Loom, LoomVersion, LoomVersionPhoto, LoomVersionReceipt
from app.models.project import Project, ProjectPhoto
from app.models.yarn import Yarn

MAX_USER_STORAGE_BYTES = 500 * 1024 * 1024  # 500 MB


async def get_user_storage_used(user_id: uuid.UUID, db: AsyncSession) -> int:
    project_bytes = await db.scalar(
        select(func.coalesce(func.sum(ProjectPhoto.file_size_bytes), 0))
        .join(Project, ProjectPhoto.project_id == Project.id)
        .where(Project.owner_id == user_id)
    )
    loom_version_bytes = await db.scalar(
        select(func.coalesce(func.sum(LoomVersionPhoto.file_size_bytes), 0))
        .join(LoomVersion, LoomVersionPhoto.loom_version_id == LoomVersion.id)
        .join(Loom, LoomVersion.loom_id == Loom.id)
        .where(Loom.owner_id == user_id)
    )
    return int(project_bytes or 0) + int(loom_version_bytes or 0)


def _s3_head(key: str) -> tuple[bool, int | None]:
    """Call head_object for one S3 key; returns (exists, size_bytes)."""
    from app.config import get_settings
    from app.services.storage import _s3

    settings = get_settings()
    if settings.storage_backend != "s3":
        full = Path(settings.upload_dir) / key
        if full.exists():
            return True, full.stat().st_size
        return False, None
    from botocore.exceptions import ClientError

    try:
        resp = _s3().head_object(Bucket=settings.s3_bucket_name, Key=key, **settings.s3_owner_kwargs)
        return True, resp.get("ContentLength")
    except ClientError:
        return False, None


def _file_entry(entity_type: str, entity_id: uuid.UUID, filename: str, s3_key: str, size_bytes: int | None) -> dict:
    return {
        "entity_type": entity_type,
        "entity_id": entity_id,
        "filename": filename,
        "s3_key": s3_key,
        "size_bytes": size_bytes,
        "s3_verified": False,
        "exists_in_s3": None,
    }


async def _draft_file_entries(db: AsyncSession, user_id: uuid.UUID) -> list[dict]:
    files: list[dict] = []
    drafts = (await db.scalars(select(Draft).where(Draft.owner_id == user_id))).all()
    for d in drafts:
        files.append(_file_entry("draft_wif", d.id, d.wif_filename, d.wif_path, None))
        if d.wif_modified_path:
            files.append(
                _file_entry("draft_wif_modified", d.id, Path(d.wif_modified_path).name, d.wif_modified_path, None)
            )
        if d.preview_path:
            files.append(_file_entry("draft_preview", d.id, Path(d.preview_path).name, d.preview_path, None))
        if d.drawdown_preview_path:
            files.append(
                _file_entry(
                    "draft_drawdown_preview", d.id, Path(d.drawdown_preview_path).name, d.drawdown_preview_path, None
                )
            )
    return files


async def _project_file_entries(db: AsyncSession, user_id: uuid.UUID) -> list[dict]:
    files: list[dict] = []
    projects = (await db.scalars(select(Project).where(Project.owner_id == user_id))).all()
    for p in projects:
        if p.drawdown_preview_path:
            files.append(
                _file_entry(
                    "project_drawdown_preview", p.id, Path(p.drawdown_preview_path).name, p.drawdown_preview_path, None
                )
            )
        if p.drawdown_svg_path:
            files.append(
                _file_entry("project_drawdown_svg", p.id, Path(p.drawdown_svg_path).name, p.drawdown_svg_path, None)
            )
    return files


async def _project_photo_file_entries(db: AsyncSession, user_id: uuid.UUID) -> list[dict]:
    proj_photos = (
        await db.scalars(
            select(ProjectPhoto).join(Project, ProjectPhoto.project_id == Project.id).where(Project.owner_id == user_id)
        )
    ).all()
    return [
        _file_entry("project_photo", ph.project_id, ph.filename, ph.file_path, ph.file_size_bytes) for ph in proj_photos
    ]


async def _loom_photo_file_entries(db: AsyncSession, user_id: uuid.UUID) -> list[dict]:
    files: list[dict] = []
    looms = (await db.scalars(select(Loom).where(Loom.owner_id == user_id))).all()
    for lm in looms:
        if lm.photo_path:
            files.append(_file_entry("loom_photo", lm.id, Path(lm.photo_path).name, lm.photo_path, None))
    return files


async def _loom_version_photo_file_entries(db: AsyncSession, user_id: uuid.UUID) -> list[dict]:
    lv_photos = (
        await db.scalars(
            select(LoomVersionPhoto)
            .join(LoomVersion, LoomVersionPhoto.loom_version_id == LoomVersion.id)
            .join(Loom, LoomVersion.loom_id == Loom.id)
            .where(Loom.owner_id == user_id)
        )
    ).all()
    return [
        _file_entry("loom_version_photo", lvp.loom_version_id, lvp.filename, lvp.path, lvp.file_size_bytes)
        for lvp in lv_photos
    ]


async def _loom_version_receipt_file_entries(db: AsyncSession, user_id: uuid.UUID) -> list[dict]:
    lv_receipts = (
        await db.scalars(
            select(LoomVersionReceipt)
            .join(LoomVersion, LoomVersionReceipt.loom_version_id == LoomVersion.id)
            .join(Loom, LoomVersion.loom_id == Loom.id)
            .where(Loom.owner_id == user_id)
        )
    ).all()
    return [
        _file_entry("loom_version_receipt", lvr.loom_version_id, lvr.filename, lvr.path, None) for lvr in lv_receipts
    ]


async def _yarn_photo_file_entries(db: AsyncSession, user_id: uuid.UUID) -> list[dict]:
    files: list[dict] = []
    yarns = (await db.scalars(select(Yarn).where(Yarn.owner_id == user_id, Yarn.photo_path.is_not(None)))).all()
    for yn in yarns:
        if yn.photo_path:
            files.append(_file_entry("yarn_photo", yn.id, Path(yn.photo_path).name, yn.photo_path, None))
    return files


async def _verify_files_in_s3(files: list[dict]) -> None:
    results = await asyncio.gather(*[asyncio.to_thread(_s3_head, f["s3_key"]) for f in files])
    for f, (exists, size) in zip(files, results):
        f["s3_verified"] = True
        f["exists_in_s3"] = exists
        if exists and size is not None:
            f["size_bytes"] = size


async def get_user_files_report(
    db: AsyncSession,
    user_id: uuid.UUID,
    verify_s3: bool = False,
) -> list[dict]:
    """Return one dict per stored file owned by user_id.

    Each dict contains: entity_type, entity_id, filename, s3_key,
    size_bytes (int|None), s3_verified (bool), exists_in_s3 (bool|None).
    """
    files: list[dict] = []
    files += await _draft_file_entries(db, user_id)
    files += await _project_file_entries(db, user_id)
    files += await _project_photo_file_entries(db, user_id)
    files += await _loom_photo_file_entries(db, user_id)
    files += await _loom_version_photo_file_entries(db, user_id)
    files += await _loom_version_receipt_file_entries(db, user_id)
    files += await _yarn_photo_file_entries(db, user_id)

    if verify_s3:
        await _verify_files_in_s3(files)

    return files


async def check_storage_quota(user_id: uuid.UUID, db: AsyncSession, incoming_bytes: int = 0) -> None:
    used = await get_user_storage_used(user_id, db)
    if used + incoming_bytes > MAX_USER_STORAGE_BYTES:
        used_mb = used / (1024 * 1024)
        raise HTTPException(
            status_code=400,
            detail=f"Storage limit reached ({used_mb:.0f} MB of 500 MB used). Delete some photos to free space.",
        )
