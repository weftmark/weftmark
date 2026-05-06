"""Storage service — local filesystem or S3-compatible (Cloudflare R2, AWS S3, etc.).

Backend is selected by STORAGE_BACKEND env var:
  local  — files written to UPLOAD_DIR on disk (default, dev)
  s3     — files written to S3_BUCKET_NAME via S3-compatible API (production)

The public API is identical for both backends. Keys/paths stored in the
database are backend-agnostic relative strings (e.g. "drafts/{uuid}.wif").
All save_* functions generate a fresh UUID for the storage key so each upload
gets a unique, collision-free path. Original filenames are stored in DB columns
and returned via Content-Disposition headers — not embedded in storage keys.
"""

from __future__ import annotations

import uuid
from pathlib import Path

from app.config import get_settings

settings = get_settings()

# ---------------------------------------------------------------------------
# Backend primitives
# ---------------------------------------------------------------------------

_s3_client = None


def _s3():
    global _s3_client
    if _s3_client is None:
        import boto3

        _s3_client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            aws_access_key_id=settings.s3_access_key_id,
            aws_secret_access_key=settings.s3_secret_access_key,
            region_name=settings.s3_region or "auto",
        )
    return _s3_client


def _put(key: str, data: bytes) -> str:
    if settings.storage_backend == "s3":
        _s3().put_object(Bucket=settings.s3_bucket_name, Key=key, Body=data)
    else:
        path = Path(settings.upload_dir) / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return key


def _get(key: str) -> bytes:
    if settings.storage_backend == "s3":
        return _s3().get_object(Bucket=settings.s3_bucket_name, Key=key)["Body"].read()
    return (Path(settings.upload_dir) / key).read_bytes()


def _delete(key: str) -> None:
    if settings.storage_backend == "s3":
        # delete_object is idempotent — no error if key does not exist
        _s3().delete_object(Bucket=settings.s3_bucket_name, Key=key)
    else:
        full = Path(settings.upload_dir) / key
        if full.exists():
            full.unlink()


def _exists(key: str | None) -> bool:
    if not key:
        return False
    if settings.storage_backend == "s3":
        from botocore.exceptions import ClientError

        try:
            _s3().head_object(Bucket=settings.s3_bucket_name, Key=key)
            return True
        except ClientError:
            return False
    return (Path(settings.upload_dir) / key).exists()


# ---------------------------------------------------------------------------
# Drafts
# ---------------------------------------------------------------------------


def save_wif(draft_id: uuid.UUID, filename: str, data: bytes) -> str:
    ext = Path(filename).suffix or ".wif"
    return _put(f"drafts/{uuid.uuid4()}{ext}", data)


def save_preview(draft_id: uuid.UUID, data: bytes) -> str:
    return _put(f"drafts/{uuid.uuid4()}.png", data)


def save_drawdown_preview(data: bytes) -> str:
    return _put(f"drafts/{uuid.uuid4()}.png", data)


def read_wif(wif_path: str) -> bytes:
    return _get(wif_path)


def read_preview(preview_path: str) -> bytes:
    return _get(preview_path)


def read_drawdown_preview(path: str) -> bytes:
    return _get(path)


def preview_exists(preview_path: str | None) -> bool:
    return _exists(preview_path)


def drawdown_preview_exists(path: str | None) -> bool:
    return _exists(path)


# ---------------------------------------------------------------------------
# Looms — profile photo
# ---------------------------------------------------------------------------


def save_loom_photo(loom_id: uuid.UUID, ext: str, data: bytes) -> str:
    return _put(f"looms/{uuid.uuid4()}{ext}", data)


def delete_loom_photo(photo_path: str) -> None:
    _delete(photo_path)


# ---------------------------------------------------------------------------
# Loom version photos
# ---------------------------------------------------------------------------


def save_version_photo(loom_id: uuid.UUID, version_id: uuid.UUID, photo_id: uuid.UUID, ext: str, data: bytes) -> str:
    return _put(f"looms/{photo_id}{ext}", data)


def delete_version_photo(path: str) -> None:
    _delete(path)


# ---------------------------------------------------------------------------
# Loom version receipts
# ---------------------------------------------------------------------------


def save_version_receipt(
    loom_id: uuid.UUID, version_id: uuid.UUID, receipt_id: uuid.UUID, ext: str, data: bytes
) -> str:
    return _put(f"looms/{receipt_id}{ext}", data)


def delete_version_receipt(path: str) -> None:
    _delete(path)


# ---------------------------------------------------------------------------
# Yarn — profile photo
# ---------------------------------------------------------------------------


def save_yarn_photo(yarn_id: uuid.UUID, ext: str, data: bytes) -> str:
    return _put(f"yarn/{uuid.uuid4()}{ext}", data)


def delete_yarn_photo(photo_path: str) -> None:
    _delete(photo_path)


# ---------------------------------------------------------------------------
# Project photos
# ---------------------------------------------------------------------------


def save_project_photo(project_id: uuid.UUID, photo_id: uuid.UUID, ext: str, data: bytes) -> str:
    return _put(f"projects/{photo_id}{ext}", data)


def delete_project_photo(path: str) -> None:
    _delete(path)


# ---------------------------------------------------------------------------
# Generic read / exists / copy
# ---------------------------------------------------------------------------


def read_file(path: str) -> bytes:
    return _get(path)


def file_exists(path: str | None) -> bool:
    return _exists(path)


def copy_file(old_key: str, new_key: str) -> str:
    """Copy a stored file to a new key. Used by migrations."""
    data = _get(old_key)
    return _put(new_key, data)
