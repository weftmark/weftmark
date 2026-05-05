#!/usr/bin/env python3
"""Compare S3 objects against all Postgres file references to find orphaned objects.

File columns checked:
  project_photos.file_path
  loom_version_photos.path
  loom_version_receipts.path
  projects.wif_path
  projects.preview_path
  looms.photo_path

Modes:
  --check    List orphaned S3 keys and sizes (read-only, no prompt)
  --dry-run  Show which delete operations would run (read-only, no prompt)
  (default)  List orphans then prompt to delete — defaults to N (requires APP_ENV=dev)

Requires asyncpg and boto3 (both in the project virtualenv).
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _lib import dry, fail, format_bytes, header, info, load_env, ok, require_dev_env, resolve_postgres_dsn, warn

try:
    import boto3
    import botocore.exceptions
except ImportError:
    print("boto3 is required — activate the project virtualenv or: pip install boto3", file=sys.stderr)
    sys.exit(1)

# ---------------------------------------------------------------------------
# Postgres — collect all referenced S3 keys
# ---------------------------------------------------------------------------

_QUERIES = [
    ("project_photos",       "SELECT file_path    FROM project_photos WHERE file_path IS NOT NULL"),
    ("loom_version_photos",  "SELECT path         FROM loom_version_photos WHERE path IS NOT NULL"),
    ("loom_version_receipts","SELECT path         FROM loom_version_receipts WHERE path IS NOT NULL"),
    ("projects.wif_path",    "SELECT wif_path     FROM projects WHERE wif_path IS NOT NULL"),
    ("projects.preview_path","SELECT preview_path FROM projects WHERE preview_path IS NOT NULL"),
    ("looms.photo_path",     "SELECT photo_path   FROM looms WHERE photo_path IS NOT NULL"),
    ("yarns.photo_path",     "SELECT photo_path   FROM yarns WHERE photo_path IS NOT NULL"),
]


async def _fetch_referenced_keys(dsn: str) -> tuple[set[str], dict[str, int]]:
    """Return (all_referenced_keys, {source_label: count})."""
    try:
        import asyncpg  # type: ignore[import]
    except ImportError:
        fail(
            "asyncpg is required.\n"
            "  Activate the project virtualenv or: pip install asyncpg"
        )

    conn = await asyncpg.connect(dsn)
    try:
        keys: set[str] = set()
        counts: dict[str, int] = {}
        for label, sql in _QUERIES:
            rows = await conn.fetch(sql)
            vals = {row[0] for row in rows if row[0]}
            keys |= vals
            counts[label] = len(vals)
        return keys, counts
    finally:
        await conn.close()


# ---------------------------------------------------------------------------
# S3 — list all objects
# ---------------------------------------------------------------------------


def _make_s3_client(env: dict[str, str]):  # type: ignore[return]
    return boto3.client(
        "s3",
        endpoint_url=env.get("S3_ENDPOINT_URL") or None,
        aws_access_key_id=env.get("S3_ACCESS_KEY_ID") or None,
        aws_secret_access_key=env.get("S3_SECRET_ACCESS_KEY") or None,
        region_name=env.get("S3_REGION", "auto") or "auto",
    )


def _list_s3_objects(s3, bucket: str) -> dict[str, int]:
    """Return {key: size_bytes} for all objects in the bucket."""
    objects: dict[str, int] = {}
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket):
        for obj in page.get("Contents", []):
            objects[obj["Key"]] = obj.get("Size", 0)
    return objects


def _delete_objects(s3, bucket: str, keys: list[str]) -> int:
    """Delete keys in batches of 1000. Returns error count."""
    errors = 0
    for i in range(0, len(keys), 1000):
        batch = keys[i : i + 1000]
        resp = s3.delete_objects(
            Bucket=bucket,
            Delete={"Objects": [{"Key": k} for k in batch], "Quiet": True},
        )
        for err in resp.get("Errors", []):
            warn(f"Failed to delete {err['Key']}: {err['Message']}")
            errors += 1
    return errors


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--env-file", default=".env.local", metavar="PATH",
                        help="Path to .env file (default: .env.local)")
    parser.add_argument("--db-port", type=int, default=5435, metavar="PORT",
                        help="Host port for local DB (default: 5435)")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--check", action="store_true",
                       help="List orphaned keys (read-only, no prompt)")
    group.add_argument("--dry-run", action="store_true",
                       help="Show delete operations that would run (read-only, no prompt)")
    args = parser.parse_args()

    env = load_env(args.env_file)

    storage_backend = env.get("STORAGE_BACKEND", "local").strip()
    if storage_backend != "s3":
        info(f"STORAGE_BACKEND={storage_backend!r} — not S3, nothing to audit")
        return

    bucket = env.get("S3_BUCKET_NAME", "").strip()
    if not bucket:
        fail("S3_BUCKET_NAME not set in env file")

    # --- Collect Postgres references ---
    header("Postgres — collecting file references")
    dsn = resolve_postgres_dsn(env, host_port=args.db_port)
    info(f"Connecting to: {dsn.split('@')[-1]}")

    try:
        referenced_keys, counts = asyncio.run(_fetch_referenced_keys(dsn))
    except Exception as exc:
        fail(f"Postgres connection failed: {exc}")

    for label, count in counts.items():
        print(f"  {label}: {count} reference(s)")
    info(f"Total unique referenced keys: {len(referenced_keys)}")

    # --- Collect S3 objects ---
    header(f"S3 — listing objects in {bucket}")
    s3 = _make_s3_client(env)
    try:
        s3_objects = _list_s3_objects(s3, bucket)
    except botocore.exceptions.ClientError as exc:
        fail(f"S3 error: {exc}")

    info(f"Total S3 objects: {len(s3_objects)}")

    # --- Compare ---
    header("Comparison")
    s3_keys = set(s3_objects.keys())
    orphaned_keys = sorted(s3_keys - referenced_keys)
    referenced_present = s3_keys & referenced_keys
    missing_from_s3 = referenced_keys - s3_keys

    ok(f"Referenced and present in S3: {len(referenced_present)}")

    if missing_from_s3:
        warn(f"Referenced in Postgres but MISSING from S3: {len(missing_from_s3)}")
        for key in sorted(missing_from_s3):
            print(f"  {key}")

    if not orphaned_keys:
        ok("No orphaned S3 objects found")
        return

    orphaned_bytes = sum(s3_objects[k] for k in orphaned_keys)
    print()
    warn(f"Orphaned S3 objects (not referenced in Postgres): {len(orphaned_keys)}  ({format_bytes(orphaned_bytes)})")
    for key in orphaned_keys:
        size = s3_objects[key]
        print(f"  {key}  ({format_bytes(size)})")

    # --- Dry-run: show delete commands ---
    if args.dry_run:
        print()
        info("Would delete:")
        for key in orphaned_keys:
            dry(f"s3://{bucket}/{key}  ({format_bytes(s3_objects[key])})")
        return

    # --- Check: stop here ---
    if args.check:
        return

    # --- Default run mode: prompt to delete ---
    require_dev_env(env)
    print()
    answer = input(f"Delete {len(orphaned_keys)} orphaned object(s) ({format_bytes(orphaned_bytes)})? [y/N]: ").strip().lower()
    if answer != "y":
        info("Skipped — no objects deleted")
        return

    info(f"Deleting {len(orphaned_keys)} orphaned object(s)…")
    errors = _delete_objects(s3, bucket, orphaned_keys)
    print()
    if errors:
        warn(f"Done with {errors} error(s)")
    else:
        ok(f"Deleted {len(orphaned_keys)} orphaned object(s), freed {format_bytes(orphaned_bytes)}")


if __name__ == "__main__":
    main()
