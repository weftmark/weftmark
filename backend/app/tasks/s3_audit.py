"""Celery task: S3 orphan file audit.

Scans all keys in the configured S3 bucket, collects all storage paths
referenced in the database, and returns the difference (orphaned keys).
Only meaningful when STORAGE_BACKEND=s3; returns not_applicable otherwise.
"""

import asyncio
import logging

from celery import Task

from app.celery_app import celery_app

log = logging.getLogger(__name__)

S3_AUDIT_SUMMARY_KEY = "weftmark:s3_audit:summary"


@celery_app.task(
    bind=True,
    max_retries=0,
    soft_time_limit=300,
    time_limit=360,
    name="app.tasks.s3_audit.run_s3_orphan_scan",
)
def run_s3_orphan_scan(self: Task) -> dict:
    return asyncio.run(_do_scan())


async def _do_scan() -> dict:
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    from app.config import get_settings
    from app.models.draft import Draft
    from app.models.loom import Loom, LoomVersionPhoto, LoomVersionReceipt
    from app.models.project import ProjectPhoto
    from app.models.yarn import Yarn

    settings = get_settings()

    if settings.storage_backend != "s3":
        _store_s3_summary(settings, 0, not_applicable=True)
        return {
            "total_s3_keys": 0,
            "total_db_paths": 0,
            "orphaned_count": 0,
            "orphaned_files": [],
            "not_applicable": True,
        }

    import boto3

    s3 = boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.s3_access_key_id,
        aws_secret_access_key=settings.s3_secret_access_key,
        region_name=settings.s3_region or "auto",
    )

    s3_files: dict[str, dict] = {}
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=settings.s3_bucket_name):
        for obj in page.get("Contents", []):
            s3_files[obj["Key"]] = {
                "size": obj["Size"],
                "last_modified": obj["LastModified"].isoformat(),
            }

    engine = create_async_engine(settings.database_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    db_paths: set[str] = set()
    try:
        async with async_session() as db:
            drafts = await db.scalars(select(Draft))
            for d in drafts.all():
                for p in [d.wif_path, d.preview_path, d.drawdown_preview_path, d.wif_modified_path]:
                    if p:
                        db_paths.add(p)

            yarns = await db.scalars(select(Yarn))
            for y in yarns.all():
                if y.photo_path:
                    db_paths.add(y.photo_path)

            looms = await db.scalars(select(Loom))
            for lm in looms.all():
                if lm.photo_path:
                    db_paths.add(lm.photo_path)

            vps = await db.scalars(select(LoomVersionPhoto))
            for vp in vps.all():
                if vp.path:
                    db_paths.add(vp.path)

            vrs = await db.scalars(select(LoomVersionReceipt))
            for vr in vrs.all():
                if vr.path:
                    db_paths.add(vr.path)

            pps = await db.scalars(select(ProjectPhoto))
            for pp in pps.all():
                if pp.file_path:
                    db_paths.add(pp.file_path)
    finally:
        await engine.dispose()

    orphaned_keys = set(s3_files.keys()) - db_paths
    orphaned_files = [
        {"key": k, "size": s3_files[k]["size"], "last_modified": s3_files[k]["last_modified"]}
        for k in sorted(orphaned_keys)
    ]

    result = {
        "total_s3_keys": len(s3_files),
        "total_db_paths": len(db_paths),
        "orphaned_count": len(orphaned_files),
        "orphaned_files": orphaned_files,
        "not_applicable": False,
    }
    _store_s3_summary(settings, len(orphaned_files))
    return result


def _store_s3_summary(settings, orphaned_count: int, not_applicable: bool = False) -> None:
    import json
    from datetime import datetime, timezone

    try:
        import redis as _redis

        scanned_at = datetime.now(timezone.utc).isoformat()
        client = _redis.from_url(settings.redis_url, socket_connect_timeout=2)
        client.set(
            S3_AUDIT_SUMMARY_KEY,
            json.dumps({"orphaned_count": orphaned_count, "scanned_at": scanned_at, "not_applicable": not_applicable}),
        )
        client.close()
    except Exception as exc:
        log.warning("s3_audit summary redis error: %s", exc)
