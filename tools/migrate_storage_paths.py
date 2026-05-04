"""
migrate_storage_paths.py — migrate R2/S3 draft objects from projects/ prefix to drafts/ prefix.

Background:
  The `drafts` table was previously called `projects`. Storage objects were written to
  `projects/{draft_id}/original.wif` and `projects/{draft_id}/preview.png`. After the
  rename this script copies each object to `drafts/{draft_id}/...`, updates the DB path
  columns, and deletes the old objects.

  Columns migrated:
    drafts.wif_path
    drafts.wif_modified_path
    drafts.preview_path

Usage:
  python tools/migrate_storage_paths.py [--dry-run] [--db-url URL]

  --dry-run  Print planned operations without writing anything.
  --db-url   Explicit DB connection string. Defaults to POSTGRES_DSN (or POSTGRES_DSN_DIRECT)
             from the nearest .env file.

Environment variables (from .env or shell):
  POSTGRES_DSN / POSTGRES_DSN_DIRECT  — database connection string
  STORAGE_BACKEND                     — "s3" or "local" (default: local)
  S3_ENDPOINT_URL, S3_ACCESS_KEY_ID, S3_SECRET_ACCESS_KEY, S3_BUCKET_NAME, S3_REGION
  UPLOAD_DIR                          — local storage root (when STORAGE_BACKEND=local)

Local docker stack note:
  POSTGRES_DSN is blank in the local compose env (the app builds the URL from individual
  POSTGRES_* vars, but this script uses psycopg2 directly). Pass --db-url explicitly:

  docker exec weaving_site_backend python migrate_storage_paths.py --dry-run \\
    --db-url "postgresql://weaving_user:weaving_password@db:5432/weaving_site"

  The URL scheme must be plain postgresql:// — not postgresql+asyncpg://.

Related: issue #312 (project→draft rename)
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# .env loader (same pattern as export_eula_migration.py)
# ---------------------------------------------------------------------------

def _load_dotenv() -> None:
    env_path = Path(__file__).parent.parent / ".env.local"
    if not env_path.exists():
        env_path = Path(__file__).parent.parent / ".env"
    if not env_path.exists():
        return
    with env_path.open() as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, val = line.partition("=")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            os.environ.setdefault(key, val)

_load_dotenv()

# ---------------------------------------------------------------------------
# Args
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dry-run", action="store_true", help="Print planned operations, make no changes")
    p.add_argument("--db-url", help="Explicit database URL (overrides env)")
    return p.parse_args()

# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def _get_db_url(override: str | None) -> str:
    if override:
        return override
    for var in ("POSTGRES_DSN_DIRECT", "POSTGRES_DSN"):
        val = os.environ.get(var, "")
        if val:
            # Convert async driver to sync for this script
            return val.replace("+asyncpg", "").replace("postgresql+asyncpg", "postgresql")
    print("ERROR: No database URL found. Set POSTGRES_DSN or pass --db-url.", file=sys.stderr)
    sys.exit(1)

# ---------------------------------------------------------------------------
# Storage helpers
# ---------------------------------------------------------------------------

_s3_client = None

def _s3():
    global _s3_client
    if _s3_client is None:
        import boto3
        _s3_client = boto3.client(
            "s3",
            endpoint_url=os.environ.get("S3_ENDPOINT_URL"),
            aws_access_key_id=os.environ.get("S3_ACCESS_KEY_ID"),
            aws_secret_access_key=os.environ.get("S3_SECRET_ACCESS_KEY"),
            region_name=os.environ.get("S3_REGION", "auto"),
        )
    return _s3_client

_BUCKET = None

def _bucket() -> str:
    global _BUCKET
    if _BUCKET is None:
        _BUCKET = os.environ.get("S3_BUCKET_NAME", "")
        if not _BUCKET:
            print("ERROR: S3_BUCKET_NAME not set.", file=sys.stderr)
            sys.exit(1)
    return _BUCKET

_BACKEND = os.environ.get("STORAGE_BACKEND", "local")
_UPLOAD_DIR = Path(os.environ.get("UPLOAD_DIR", "uploads"))


def _object_exists(key: str) -> bool:
    if _BACKEND == "s3":
        from botocore.exceptions import ClientError
        try:
            _s3().head_object(Bucket=_bucket(), Key=key)
            return True
        except ClientError:
            return False
    return (_UPLOAD_DIR / key).exists()


def _copy_object(src: str, dst: str) -> None:
    if _BACKEND == "s3":
        _s3().copy_object(
            Bucket=_bucket(),
            CopySource={"Bucket": _bucket(), "Key": src},
            Key=dst,
        )
    else:
        src_path = _UPLOAD_DIR / src
        dst_path = _UPLOAD_DIR / dst
        dst_path.parent.mkdir(parents=True, exist_ok=True)
        dst_path.write_bytes(src_path.read_bytes())


def _delete_object(key: str) -> None:
    if _BACKEND == "s3":
        _s3().delete_object(Bucket=_bucket(), Key=key)
    else:
        full = _UPLOAD_DIR / key
        if full.exists():
            full.unlink()


# ---------------------------------------------------------------------------
# Migration logic
# ---------------------------------------------------------------------------

def _new_path(old_path: str) -> str | None:
    """Return the migrated path, or None if no migration needed."""
    if old_path and old_path.startswith("projects/"):
        return "drafts/" + old_path[len("projects/"):]
    return None


def run(db_url: str, dry_run: bool) -> None:
    import psycopg2  # type: ignore

    conn = psycopg2.connect(db_url)
    conn.autocommit = False
    cur = conn.cursor()

    cur.execute(
        "SELECT id, wif_path, wif_modified_path, preview_path FROM drafts WHERE "
        "wif_path LIKE 'projects/%' OR wif_modified_path LIKE 'projects/%' OR preview_path LIKE 'projects/%'"
    )
    rows = cur.fetchall()

    if not rows:
        print("No drafts with legacy 'projects/' paths found. Nothing to do.")
        conn.close()
        return

    print(f"Found {len(rows)} draft(s) with legacy paths.")

    migrated = 0
    errors = 0

    for (draft_id, wif_path, wif_modified_path, preview_path) in rows:
        print(f"\nDraft {draft_id}:")
        updates: dict[str, str] = {}

        for col, old in [("wif_path", wif_path), ("wif_modified_path", wif_modified_path), ("preview_path", preview_path)]:
            if not old:
                continue
            new = _new_path(old)
            if not new:
                continue

            # Skip if source doesn't exist (already migrated or missing)
            if not _object_exists(old):
                print(f"  {col}: {old} — SOURCE MISSING, skipping")
                updates[col] = new  # still update DB to reflect correct path
                continue

            if _object_exists(new):
                print(f"  {col}: {old} → {new} — destination already exists, skipping copy")
            else:
                print(f"  {col}: {old} → {new}")
                if not dry_run:
                    try:
                        _copy_object(old, new)
                    except Exception as exc:
                        print(f"    ERROR copying: {exc}")
                        errors += 1
                        continue

            updates[col] = new

        if not updates:
            continue

        if not dry_run:
            set_clause = ", ".join(f"{col} = %s" for col in updates)
            cur.execute(
                f"UPDATE drafts SET {set_clause} WHERE id = %s",
                [*updates.values(), str(draft_id)],
            )
            # Delete old objects after DB is updated (within same transaction)
            for col, old in [("wif_path", wif_path), ("wif_modified_path", wif_modified_path), ("preview_path", preview_path)]:
                if col in updates and old and _new_path(old):
                    try:
                        _delete_object(old)
                    except Exception as exc:
                        print(f"  WARNING: failed to delete {old}: {exc}")

        migrated += 1

    if dry_run:
        print(f"\nDRY RUN complete — {migrated} draft(s) would be migrated.")
        conn.close()
        return

    if errors:
        print(f"\n{errors} error(s) occurred. Rolling back.")
        conn.rollback()
    else:
        conn.commit()
        print(f"\nMigrated {migrated} draft(s) successfully.")

    conn.close()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    args = _parse_args()
    db_url = _get_db_url(args.db_url)
    run(db_url, dry_run=args.dry_run)
