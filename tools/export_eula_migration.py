"""
export_eula_migration.py — sync admin-UI EULA versions back to Alembic migrations.

Workflow:
  1. Publish a new EULA version via the admin UI (POST /api/admin/eula).
  2. Run this script:  python tools/export_eula_migration.py
  3. Review the generated migration file in backend/alembic/versions/.
  4. Commit and push.

The script reads EULA versions either from the REST API or directly from the
database, compares against versions already seeded in existing migration files,
and generates a new migration for any gaps.  It never commits, pushes, or
modifies the database.

Usage:
  python tools/export_eula_migration.py [--api-url URL] [--db-url URL] [--dry-run]

  --api-url  Fetch the current EULA from the public REST endpoint (GET URL).
             Takes precedence over --db-url and .env database credentials.
             Use this in CI pipelines that cannot access the database directly.
  --db-url   Explicit DB connection string (postgresql://...).  Defaults to
             POSTGRES_DSN_DIRECT, then POSTGRES_DSN from the nearest .env file.
             Ignored when --api-url is supplied.
  --dry-run  Print the migration content instead of writing the file.
"""

import argparse
import os
import re
import sys
import textwrap
from datetime import datetime, timezone
from pathlib import Path

from packaging.version import Version

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parent.parent
MIGRATIONS_DIR = REPO_ROOT / "backend" / "alembic" / "versions"


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def _load_env() -> dict[str, str]:
    """Read key=value pairs from the nearest .env file (no external deps)."""
    env_path = REPO_ROOT / ".env"
    if not env_path.exists():
        return {}
    result: dict[str, str] = {}
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        result[k.strip()] = v.strip()
    return result


def _resolve_db_url(cli_url: str | None) -> str:
    env = {**_load_env(), **os.environ}
    url = (
        cli_url
        or env.get("POSTGRES_DSN_DIRECT")
        or env.get("POSTGRES_DSN")
    )
    if not url:
        sys.exit(
            "ERROR: No database URL found.\n"
            "Set POSTGRES_DSN_DIRECT (or POSTGRES_DSN) in .env, or pass --db-url."
        )
    # Ensure sync psycopg2 driver; strip asyncpg if present
    url = url.replace("postgres://", "postgresql://", 1)
    url = url.replace("postgresql+asyncpg://", "postgresql://", 1)
    return url


# ---------------------------------------------------------------------------
# REST API: fetch current EULA version
# ---------------------------------------------------------------------------

def _fetch_api_version(api_url: str) -> list[dict]:
    """Fetch the current EULA version from the public REST endpoint."""
    import json
    import urllib.request

    req = urllib.request.Request(api_url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
    except Exception as exc:
        sys.exit(f"ERROR: Could not fetch EULA from {api_url}: {exc}")

    return [{
        "version": data["version"],
        "body_html": data["body_html"],
        "effective_date": data["effective_date"],
        "created_at": data.get("created_at", ""),
    }]


# ---------------------------------------------------------------------------
# Database: fetch all EULA versions
# ---------------------------------------------------------------------------

def _fetch_db_versions(db_url: str) -> list[dict]:
    import psycopg2
    import psycopg2.extras

    conn = psycopg2.connect(db_url)
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute(
                "SELECT id, version, body_html, effective_date, created_at "
                "FROM eula_versions ORDER BY id"
            )
            return [dict(row) for row in cur.fetchall()]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Migration scanner: find versions already seeded in migration files
# ---------------------------------------------------------------------------

def _seeded_versions() -> set[str]:
    """Return the set of EULA version strings already present in migration files."""
    seeded: list[str] = []
    # Look for  version="X.Y"  or  version='X.Y'  inside INSERT statements
    pattern = re.compile(r"""version\s*=\s*["']([^"']+)["']""")
    for path in MIGRATIONS_DIR.glob("*.py"):
        content = path.read_text(encoding="utf-8")
        if "eula_versions" not in content:
            continue
        for match in pattern.finditer(content):
            seeded.append(match.group(1))
    return set(seeded)


# ---------------------------------------------------------------------------
# Migration file generator
# ---------------------------------------------------------------------------

def _next_file_prefix() -> str:
    """Return the next four-digit filename prefix (zero-padded)."""
    existing = [
        int(m.group(1))
        for p in MIGRATIONS_DIR.glob("*.py")
        if (m := re.match(r"^(\d{4})_", p.name))
    ]
    return f"{(max(existing) + 1) if existing else 1:04d}"


def _head_revision_id() -> str:
    """Return the actual revision ID string from the last migration file."""
    numbered = sorted(
        p for p in MIGRATIONS_DIR.glob("*.py")
        if re.match(r"^\d{4}_", p.name)
    )
    if not numbered:
        return "0000"
    content = numbered[-1].read_text(encoding="utf-8")
    m = re.search(r'^revision\s*(?::\s*str)?\s*=\s*["\']([^"\']+)["\']', content, re.MULTILINE)
    return m.group(1) if m else numbered[-1].stem.split("_")[0]


def _new_revision_id() -> str:
    """Generate a random 12-hex-char revision ID matching Alembic's default style."""
    import secrets
    return secrets.token_hex(6)


def _make_migration(version: dict, revision: str, prev_revision: str) -> str:
    ver = version["version"]
    body_html = version["body_html"]
    effective = version["effective_date"]
    if hasattr(effective, "isoformat"):
        effective_iso = effective.astimezone(timezone.utc).isoformat()
    else:
        effective_iso = str(effective)

    # Indent the HTML body so it fits cleanly inside a triple-quoted string
    indented_html = textwrap.indent(body_html, "")

    return f'''\
"""seed eula version {ver}

Revision ID: {revision}
Revises: {prev_revision}
Create Date: {datetime.now(timezone.utc).strftime("%Y-%m-%d")}

Generated by tools/export_eula_migration.py — do not edit the HTML by hand;
update via the admin UI and re-run the script.
"""

from alembic import op
import sqlalchemy as sa

revision = "{revision}"
down_revision = "{prev_revision}"
branch_labels = None
depends_on = None

_BODY_HTML = """\
{indented_html}
"""


def upgrade() -> None:
    op.execute(
        sa.text(
            "INSERT INTO eula_versions (version, body_html, effective_date) "
            "VALUES (:version, :body_html, :effective_date) "
            "ON CONFLICT (version) DO NOTHING"
        ).bindparams(
            version={ver!r},
            body_html=_BODY_HTML,
            effective_date={effective_iso!r},
        )
    )


def downgrade() -> None:
    op.execute(
        sa.text("DELETE FROM eula_versions WHERE version = :version").bindparams(
            version={ver!r}
        )
    )
'''


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--api-url", help="REST endpoint to fetch current EULA (takes precedence over --db-url)")
    parser.add_argument("--db-url", help="Database connection string (overrides .env)")
    parser.add_argument("--dry-run", action="store_true", help="Print migration content; do not write file")
    args = parser.parse_args()

    if args.api_url:
        print(f"Fetching EULA from {args.api_url}…")
        db_versions = _fetch_api_version(args.api_url)
        print(f"Found {len(db_versions)} EULA version(s) via API.")
    else:
        db_url = _resolve_db_url(args.db_url)
        print("Connecting to database…")
        try:
            db_versions = _fetch_db_versions(db_url)
        except Exception as exc:
            sys.exit(f"ERROR: Could not connect to database: {exc}")
        print(f"Found {len(db_versions)} EULA version(s) in database.")

    seeded = _seeded_versions()
    seeded_sorted = sorted(seeded, key=lambda v: Version(v))
    print(f"Already seeded in migrations: {seeded_sorted or '(none)'}")

    pending = [v for v in db_versions if v["version"] not in seeded]

    if not pending and args.api_url and seeded:
        max_seeded = max(seeded, key=lambda v: Version(v))
        returned = db_versions[0]["version"] if db_versions else None
        if returned and Version(returned) <= Version(max_seeded):
            print(
                f"WARNING: API returned version {returned!r} which is not newer than "
                f"the latest seeded version {max_seeded!r}.\n"
                f"This may mean a newer EULA exists in the database with an earlier\n"
                f"effective_date. Re-run with --db-url to export all versions directly."
            )

    if not pending:
        print("Nothing to do — all database versions are already in migration files.")
        return

    print(f"\n{len(pending)} version(s) need a migration: {[v['version'] for v in pending]}\n")

    prev_revision = _head_revision_id()

    generated: list[Path] = []
    for version in pending:
        file_prefix = _next_file_prefix()
        revision = _new_revision_id()
        content = _make_migration(version, revision, prev_revision)
        slug = re.sub(r"[^a-z0-9]+", "_", version["version"].lower()).strip("_")
        filename = f"{file_prefix}_eula_version_{slug}.py"
        out_path = MIGRATIONS_DIR / filename

        if args.dry_run:
            print(f"--- {filename} ---")
            print(content)
        else:
            out_path.write_text(content, encoding="utf-8")
            print(f"Written: {out_path.relative_to(REPO_ROOT)}")
            generated.append(out_path)

        prev_revision = revision  # chain: next migration's down_revision is this one's revision

    if generated and not args.dry_run:
        print("\nNext steps:")
        print("  1. Review the generated file(s) above.")
        print("  2. git add backend/alembic/versions/<file>")
        print("  3. git commit -m 'chore: persist EULA version <X> to migrations'")
        print("  4. git push")


if __name__ == "__main__":
    main()
