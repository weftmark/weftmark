#!/usr/bin/env python3
"""Clear all objects from the configured S3 bucket.

Modes:
  --check    List object count and total size (read-only, no APP_ENV restriction)
  --dry-run  Show what would be deleted (read-only)
  (default)  Delete all objects — requires APP_ENV=dev

Requires boto3: pip install boto3  (already in backend/requirements.txt)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _lib import dry, fail, format_bytes, header, info, load_env, ok, require_dev_env, warn

try:
    import boto3
    import botocore.exceptions
except ImportError:
    print("boto3 is required — activate the project virtualenv or: pip install boto3", file=sys.stderr)
    sys.exit(1)


def make_s3_client(env: dict[str, str]):  # type: ignore[return]
    endpoint = env.get("S3_ENDPOINT_URL", "").strip() or None
    access_key = env.get("S3_ACCESS_KEY_ID", "").strip() or None
    secret_key = env.get("S3_SECRET_ACCESS_KEY", "").strip() or None
    region = env.get("S3_REGION", "auto").strip() or "auto"
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=region,
    )


def list_all_objects(s3, bucket: str) -> list[dict]:
    objects: list[dict] = []
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket):
        objects.extend(page.get("Contents", []))
    return objects


def delete_objects_batch(s3, bucket: str, keys: list[str]) -> int:
    """Delete up to 1000 keys in one request. Returns number of errors."""
    resp = s3.delete_objects(
        Bucket=bucket,
        Delete={"Objects": [{"Key": k} for k in keys], "Quiet": True},
    )
    errors = resp.get("Errors", [])
    for err in errors:
        warn(f"Failed to delete {err['Key']}: {err['Message']}")
    return len(errors)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--env-file", default=".env.local", metavar="PATH", help="Path to .env file (default: .env.local)")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--check", action="store_true", help="Report object count and size (read-only)")
    group.add_argument("--dry-run", action="store_true", help="Show what would be deleted (read-only)")
    args = parser.parse_args()

    env = load_env(args.env_file)

    storage_backend = env.get("STORAGE_BACKEND", "local").strip()
    if storage_backend != "s3":
        info(f"STORAGE_BACKEND={storage_backend!r} — not S3, nothing to clear")
        return

    bucket = env.get("S3_BUCKET_NAME", "").strip()
    if not bucket:
        fail("S3_BUCKET_NAME not set in env file")

    header(f"S3 — bucket: {bucket}")
    s3 = make_s3_client(env)

    try:
        objects = list_all_objects(s3, bucket)
    except botocore.exceptions.ClientError as exc:
        fail(f"S3 error listing objects: {exc}")

    if not objects:
        ok("Bucket is empty — 0 objects")
        return

    total_bytes = sum(o.get("Size", 0) for o in objects)
    summary = f"{len(objects)} object(s), {format_bytes(total_bytes)}"

    if args.check:
        info(f"Found {summary}:")
        sample = objects[:20]
        for o in sample:
            print(f"  {o['Key']}  ({format_bytes(o.get('Size', 0))})")
        if len(objects) > 20:
            print(f"  … and {len(objects) - 20} more")
        return

    if args.dry_run:
        info(f"Would delete {summary}:")
        sample = objects[:20]
        for o in sample:
            dry(f"{o['Key']}  ({format_bytes(o.get('Size', 0))})")
        if len(objects) > 20:
            print(f"  … and {len(objects) - 20} more")
        return

    require_dev_env(env)
    info(f"Deleting {summary}…")

    keys = [o["Key"] for o in objects]
    total_errors = 0
    for i in range(0, len(keys), 1000):
        batch = keys[i : i + 1000]
        total_errors += delete_objects_batch(s3, bucket, batch)
        info(f"  Deleted batch {i // 1000 + 1} ({len(batch)} keys)")

    print()
    if total_errors:
        warn(f"Done with {total_errors} error(s) — re-run --check to verify")
    else:
        ok(f"All {len(objects)} object(s) deleted from {bucket}")


if __name__ == "__main__":
    main()
