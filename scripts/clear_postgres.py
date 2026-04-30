#!/usr/bin/env python3
"""Reset the Postgres database via Alembic downgrade base → upgrade head.

Modes:
  --check    Count rows per table (read-only, no APP_ENV restriction)
  --dry-run  Show the Alembic commands that would run (read-only)
  (default)  Run downgrade base + upgrade head — requires APP_ENV=dev

Check mode requires asyncpg (already in the project virtualenv).
Run mode requires Docker and the backend image to be built.
"""

from __future__ import annotations

import argparse
import asyncio
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _lib import dry, fail, header, info, load_env, ok, require_dev_env, resolve_postgres_dsn, warn

REPO_ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Check mode — count rows via asyncpg
# ---------------------------------------------------------------------------


async def _count_rows(dsn: str) -> dict[str, int]:
    try:
        import asyncpg  # type: ignore[import]
    except ImportError:
        fail(
            "asyncpg is required for --check mode.\n"
            "  Activate the project virtualenv or: pip install asyncpg"
        )

    conn = await asyncpg.connect(dsn)
    try:
        tables = await conn.fetch(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename"
        )
        counts: dict[str, int] = {}
        for row in tables:
            table = row["tablename"]
            count = await conn.fetchval(f"SELECT COUNT(*) FROM {table}")
            counts[table] = count
        return counts
    finally:
        await conn.close()


# ---------------------------------------------------------------------------
# Run mode — Alembic via Docker
# ---------------------------------------------------------------------------


def _find_compose_file() -> Path:
    for name in ("docker-compose.build.yml", "docker-compose.dev.yml"):
        path = REPO_ROOT / name
        if path.exists():
            return path
    fail("No docker-compose.build.yml or docker-compose.dev.yml found in repo root")


def _run_alembic(cmd: str, env_file: str, compose_file: Path) -> None:
    """Run an Alembic command inside a one-shot backend container."""
    docker_cmd = [
        "docker", "compose",
        "--env-file", env_file,
        "-f", str(compose_file),
        "run", "--rm", "--no-deps", "backend",
        "alembic", *cmd.split(),
    ]
    info(f"Running: {' '.join(docker_cmd)}")
    result = subprocess.run(docker_cmd, cwd=REPO_ROOT)
    if result.returncode != 0:
        fail(f"alembic {cmd} failed (exit {result.returncode})")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--env-file", default=".env.local", metavar="PATH", help="Path to .env file (default: .env.local)")
    parser.add_argument("--db-port", type=int, default=5435, metavar="PORT",
                        help="Host port the local DB container is mapped to (default: 5435 for docker-compose.build.yml)")
    parser.add_argument("--compose-file", metavar="FILE", help="Override compose file for run mode")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--check", action="store_true", help="Count rows per table (read-only)")
    group.add_argument("--dry-run", action="store_true", help="Show Alembic commands that would run (read-only)")
    args = parser.parse_args()

    env = load_env(args.env_file)

    header("Postgres — database")

    if args.check:
        dsn = resolve_postgres_dsn(env, host_port=args.db_port)
        info(f"Connecting to: {dsn.split('@')[-1]}")  # hide credentials
        try:
            counts = asyncio.run(_count_rows(dsn))
        except Exception as exc:
            fail(f"Connection failed: {exc}")

        total = sum(counts.values())
        if total == 0:
            ok("Database is empty — all tables have 0 rows")
        else:
            info(f"Row counts ({total} total):")
            for table, count in sorted(counts.items()):
                flag = "  " if count == 0 else "⚠ "
                print(f"  {flag}{table}: {count}")
        return

    compose_file = Path(args.compose_file) if args.compose_file else _find_compose_file()

    alembic_cmds = ["downgrade base", "upgrade head"]

    if args.dry_run:
        info(f"Compose file: {compose_file.name}")
        info("Would run:")
        for cmd in alembic_cmds:
            dry(f"docker compose run --rm --no-deps backend alembic {cmd}")
        return

    require_dev_env(env)
    info(f"Compose file: {compose_file.name}")
    for cmd in alembic_cmds:
        _run_alembic(cmd, args.env_file, compose_file)

    print()
    ok("Database reset complete (downgrade base → upgrade head)")


if __name__ == "__main__":
    main()
