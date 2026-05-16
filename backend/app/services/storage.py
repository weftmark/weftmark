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

import asyncio
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
# Drawdown tiles — pre-rendered strips stored at deterministic paths
# ---------------------------------------------------------------------------


def drawdown_tile_path(draft_id: uuid.UUID, scale: int, start_row: int) -> str:
    return f"drafts/{draft_id}/tiles/s{scale}/t{start_row}.png"


def save_drawdown_tile(draft_id: uuid.UUID, scale: int, start_row: int, data: bytes) -> str:
    return _put(drawdown_tile_path(draft_id, scale, start_row), data)


def drawdown_tile_exists(draft_id: uuid.UUID, scale: int, start_row: int) -> bool:
    return _exists(drawdown_tile_path(draft_id, scale, start_row))


def read_drawdown_tile(draft_id: uuid.UUID, scale: int, start_row: int) -> bytes:
    return _get(drawdown_tile_path(draft_id, scale, start_row))


async def adrawdown_tile_exists(draft_id: uuid.UUID, scale: int, start_row: int) -> bool:
    return await asyncio.to_thread(drawdown_tile_exists, draft_id, scale, start_row)


async def aread_drawdown_tile(draft_id: uuid.UUID, scale: int, start_row: int) -> bytes:
    return await asyncio.to_thread(read_drawdown_tile, draft_id, scale, start_row)


async def asave_drawdown_tile(draft_id: uuid.UUID, scale: int, start_row: int, data: bytes) -> str:
    return await asyncio.to_thread(save_drawdown_tile, draft_id, scale, start_row, data)


# ---------------------------------------------------------------------------
# Project tiles — pre-rendered row strips keyed by project_id
# ---------------------------------------------------------------------------


def project_tile_path(project_id: uuid.UUID, scale: int, start_row: int) -> str:
    return f"projects/{project_id}/tiles/s{scale}/r{start_row}.png"


def save_project_tile(project_id: uuid.UUID, scale: int, start_row: int, data: bytes) -> str:
    return _put(project_tile_path(project_id, scale, start_row), data)


def project_tile_exists(project_id: uuid.UUID, scale: int, start_row: int) -> bool:
    return _exists(project_tile_path(project_id, scale, start_row))


def read_project_tile(project_id: uuid.UUID, scale: int, start_row: int) -> bytes:
    return _get(project_tile_path(project_id, scale, start_row))


async def aproject_tile_exists(project_id: uuid.UUID, scale: int, start_row: int) -> bool:
    return await asyncio.to_thread(project_tile_exists, project_id, scale, start_row)


async def aread_project_tile(project_id: uuid.UUID, scale: int, start_row: int) -> bytes:
    return await asyncio.to_thread(read_project_tile, project_id, scale, start_row)


async def asave_project_tile(project_id: uuid.UUID, scale: int, start_row: int, data: bytes) -> str:
    return await asyncio.to_thread(save_project_tile, project_id, scale, start_row, data)


def save_project_drawdown_preview(data: bytes) -> str:
    return _put(f"projects/{uuid.uuid4()}.png", data)


def read_project_drawdown_preview(path: str) -> bytes:
    return _get(path)


def project_drawdown_preview_exists(path: str | None) -> bool:
    return _exists(path)


def save_project_drawdown_svg(data: str) -> str:
    return _put(f"projects/{uuid.uuid4()}.svg", data.encode("utf-8"))


def read_project_drawdown_svg(path: str) -> str:
    return _get(path).decode("utf-8")


def project_drawdown_svg_exists(path: str | None) -> bool:
    return _exists(path)


def delete_project_tiles(project_id: uuid.UUID) -> int:
    """Delete all pre-rendered tiles for a project. Returns the count of deleted objects."""
    prefix = f"projects/{project_id}/tiles/"
    if settings.storage_backend == "s3":
        paginator = _s3().get_paginator("list_objects_v2")
        keys = []
        for page in paginator.paginate(Bucket=settings.s3_bucket_name, Prefix=prefix):
            for obj in page.get("Contents", []):
                keys.append(obj["Key"])
        if keys:
            for i in range(0, len(keys), 1000):
                batch = [{"Key": k} for k in keys[i : i + 1000]]
                _s3().delete_objects(Bucket=settings.s3_bucket_name, Delete={"Objects": batch})
        return len(keys)
    else:
        prefix_path = Path(settings.upload_dir) / prefix
        if not prefix_path.exists():
            return 0
        count = 0
        for f in prefix_path.rglob("*.png"):
            f.unlink()
            count += 1
        return count


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


# ---------------------------------------------------------------------------
# Async wrappers for use in FastAPI async handlers
# All storage primitives (boto3, pathlib) are synchronous blocking I/O.
# These wrappers offload to a thread pool so the event loop is not blocked.
# ---------------------------------------------------------------------------


async def aread_file(path: str) -> bytes:
    return await asyncio.to_thread(_get, path)


async def afile_exists(path: str | None) -> bool:
    return await asyncio.to_thread(_exists, path)


async def asave_wif(draft_id: uuid.UUID, filename: str, data: bytes) -> str:
    return await asyncio.to_thread(save_wif, draft_id, filename, data)


async def asave_preview(draft_id: uuid.UUID, data: bytes) -> str:
    return await asyncio.to_thread(save_preview, draft_id, data)


async def asave_drawdown_preview(data: bytes) -> str:
    return await asyncio.to_thread(save_drawdown_preview, data)


async def aread_drawdown_preview(path: str) -> bytes:
    return await asyncio.to_thread(read_drawdown_preview, path)


async def asave_project_photo(project_id: uuid.UUID, photo_id: uuid.UUID, ext: str, data: bytes) -> str:
    return await asyncio.to_thread(save_project_photo, project_id, photo_id, ext, data)


async def adelete_project_photo(path: str) -> None:
    await asyncio.to_thread(delete_project_photo, path)


async def asave_loom_photo(loom_id: uuid.UUID, ext: str, data: bytes) -> str:
    return await asyncio.to_thread(save_loom_photo, loom_id, ext, data)


async def adelete_loom_photo(photo_path: str) -> None:
    await asyncio.to_thread(delete_loom_photo, photo_path)


async def asave_version_photo(
    loom_id: uuid.UUID, version_id: uuid.UUID, photo_id: uuid.UUID, ext: str, data: bytes
) -> str:
    return await asyncio.to_thread(save_version_photo, loom_id, version_id, photo_id, ext, data)


async def adelete_version_photo(path: str) -> None:
    await asyncio.to_thread(delete_version_photo, path)


async def asave_version_receipt(
    loom_id: uuid.UUID, version_id: uuid.UUID, receipt_id: uuid.UUID, ext: str, data: bytes
) -> str:
    return await asyncio.to_thread(save_version_receipt, loom_id, version_id, receipt_id, ext, data)


async def adelete_version_receipt(path: str) -> None:
    await asyncio.to_thread(delete_version_receipt, path)


async def asave_yarn_photo(yarn_id: uuid.UUID, ext: str, data: bytes) -> str:
    return await asyncio.to_thread(save_yarn_photo, yarn_id, ext, data)


async def adelete_yarn_photo(photo_path: str) -> None:
    await asyncio.to_thread(delete_yarn_photo, photo_path)


async def asave_project_drawdown_preview(data: bytes) -> str:
    return await asyncio.to_thread(save_project_drawdown_preview, data)


async def aread_project_drawdown_preview(path: str) -> bytes:
    return await asyncio.to_thread(read_project_drawdown_preview, path)


async def aproject_drawdown_preview_exists(path: str | None) -> bool:
    return await asyncio.to_thread(project_drawdown_preview_exists, path)


async def asave_project_drawdown_svg(data: str) -> str:
    return await asyncio.to_thread(save_project_drawdown_svg, data)


async def aread_project_drawdown_svg(path: str) -> str:
    return await asyncio.to_thread(read_project_drawdown_svg, path)


async def aproject_drawdown_svg_exists(path: str | None) -> bool:
    return await asyncio.to_thread(project_drawdown_svg_exists, path)
