"""Local file storage service. S3 support can be added later via STORAGE_BACKEND."""

from __future__ import annotations

import os
import uuid
from pathlib import Path

from app.config import get_settings

settings = get_settings()


def _upload_root() -> Path:
    return Path(settings.upload_dir)


def project_dir(project_id: uuid.UUID) -> Path:
    p = _upload_root() / "projects" / str(project_id)
    p.mkdir(parents=True, exist_ok=True)
    return p


def save_wif(project_id: uuid.UUID, filename: str, data: bytes) -> str:
    """Save raw WIF bytes. Returns the relative storage path."""
    dest = project_dir(project_id) / "original.wif"
    dest.write_bytes(data)
    return str(dest.relative_to(_upload_root()))


def save_preview(project_id: uuid.UUID, data: bytes) -> str:
    """Save rendered preview PNG. Returns the relative storage path."""
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
