"""Local file storage service. S3 support can be added later via STORAGE_BACKEND."""

from __future__ import annotations

import uuid
from pathlib import Path

from app.config import get_settings

settings = get_settings()


def _upload_root() -> Path:
    return Path(settings.upload_dir)


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------


def project_dir(project_id: uuid.UUID) -> Path:
    p = _upload_root() / "projects" / str(project_id)
    p.mkdir(parents=True, exist_ok=True)
    return p


def save_wif(project_id: uuid.UUID, filename: str, data: bytes) -> str:
    dest = project_dir(project_id) / "original.wif"
    dest.write_bytes(data)
    return str(dest.relative_to(_upload_root()))


def save_preview(project_id: uuid.UUID, data: bytes) -> str:
    dest = project_dir(project_id) / "preview.png"
    dest.write_bytes(data)
    return str(dest.relative_to(_upload_root()))


def read_wif(wif_path: str) -> bytes:
    return (_upload_root() / wif_path).read_bytes()


def read_preview(preview_path: str) -> bytes:
    return (_upload_root() / preview_path).read_bytes()


def preview_exists(preview_path: str | None) -> bool:
    if not preview_path:
        return False
    return (_upload_root() / preview_path).exists()


# ---------------------------------------------------------------------------
# Looms — profile photo
# ---------------------------------------------------------------------------


def loom_dir(loom_id: uuid.UUID) -> Path:
    p = _upload_root() / "looms" / str(loom_id)
    p.mkdir(parents=True, exist_ok=True)
    return p


def save_loom_photo(loom_id: uuid.UUID, ext: str, data: bytes) -> str:
    """Save or replace the loom profile photo. Returns relative storage path."""
    dest = loom_dir(loom_id) / f"profile{ext}"
    dest.write_bytes(data)
    return str(dest.relative_to(_upload_root()))


def delete_loom_photo(photo_path: str) -> None:
    full = _upload_root() / photo_path
    if full.exists():
        full.unlink()


# ---------------------------------------------------------------------------
# Loom version photos
# ---------------------------------------------------------------------------


def version_photo_dir(loom_id: uuid.UUID, version_id: uuid.UUID) -> Path:
    p = loom_dir(loom_id) / "versions" / str(version_id) / "photos"
    p.mkdir(parents=True, exist_ok=True)
    return p


def save_version_photo(loom_id: uuid.UUID, version_id: uuid.UUID, photo_id: uuid.UUID, ext: str, data: bytes) -> str:
    dest = version_photo_dir(loom_id, version_id) / f"{photo_id}{ext}"
    dest.write_bytes(data)
    return str(dest.relative_to(_upload_root()))


def delete_version_photo(path: str) -> None:
    full = _upload_root() / path
    if full.exists():
        full.unlink()


# ---------------------------------------------------------------------------
# Loom version receipts
# ---------------------------------------------------------------------------


def version_receipt_dir(loom_id: uuid.UUID, version_id: uuid.UUID) -> Path:
    p = loom_dir(loom_id) / "versions" / str(version_id) / "receipts"
    p.mkdir(parents=True, exist_ok=True)
    return p


def save_version_receipt(
    loom_id: uuid.UUID, version_id: uuid.UUID, receipt_id: uuid.UUID, ext: str, data: bytes
) -> str:
    dest = version_receipt_dir(loom_id, version_id) / f"{receipt_id}{ext}"
    dest.write_bytes(data)
    return str(dest.relative_to(_upload_root()))


def delete_version_receipt(path: str) -> None:
    full = _upload_root() / path
    if full.exists():
        full.unlink()


# ---------------------------------------------------------------------------
# Yarn — profile photo
# ---------------------------------------------------------------------------


def yarn_dir(yarn_id: uuid.UUID) -> Path:
    p = _upload_root() / "yarn" / str(yarn_id)
    p.mkdir(parents=True, exist_ok=True)
    return p


def save_yarn_photo(yarn_id: uuid.UUID, ext: str, data: bytes) -> str:
    dest = yarn_dir(yarn_id) / f"profile{ext}"
    dest.write_bytes(data)
    return str(dest.relative_to(_upload_root()))


def delete_yarn_photo(photo_path: str) -> None:
    full = _upload_root() / photo_path
    if full.exists():
        full.unlink()


# ---------------------------------------------------------------------------
# Activity photos
# ---------------------------------------------------------------------------


def activity_photo_dir(activity_id: uuid.UUID) -> Path:
    p = _upload_root() / "activities" / str(activity_id) / "photos"
    p.mkdir(parents=True, exist_ok=True)
    return p


def save_activity_photo(activity_id: uuid.UUID, photo_id: uuid.UUID, ext: str, data: bytes) -> str:
    dest = activity_photo_dir(activity_id) / f"{photo_id}{ext}"
    dest.write_bytes(data)
    return str(dest.relative_to(_upload_root()))


def delete_activity_photo(path: str) -> None:
    full = _upload_root() / path
    if full.exists():
        full.unlink()


# ---------------------------------------------------------------------------
# Generic read
# ---------------------------------------------------------------------------


def read_file(path: str) -> bytes:
    return (_upload_root() / path).read_bytes()


def file_exists(path: str | None) -> bool:
    if not path:
        return False
    return (_upload_root() / path).exists()
