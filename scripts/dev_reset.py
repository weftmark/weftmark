#!/usr/bin/env python3
"""Master dev reset orchestrator — Clerk + S3 + Postgres.

Modes:
  --check    Report current state across all three systems (read-only)
  --dry-run  Show what each clear script would do (read-only)
  (default)  Interactively confirm, then clear all three — requires APP_ENV=dev

Individual scripts can be run in isolation:
  python scripts/clear_clerk.py    --env-file .env.local [--check | --dry-run]
  python scripts/clear_s3.py      --env-file .env.local [--check | --dry-run]
  python scripts/clear_postgres.py --env-file .env.local [--check | --dry-run]
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _lib import BOLD, RED, RESET, fail, header, info, load_env, ok, require_dev_env, warn

SCRIPTS_DIR = Path(__file__).resolve().parent


def run_script(script: str, extra_args: list[str], env_file: str) -> bool:
    """Run a sub-script and return True on success."""
    cmd = [sys.executable, str(SCRIPTS_DIR / script), "--env-file", env_file, *extra_args]
    result = subprocess.run(cmd)
    return result.returncode == 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--env-file", default=".env.local", metavar="PATH",
                        help="Path to .env file (default: .env.local)")
    parser.add_argument("--db-port", type=int, default=5435, metavar="PORT",
                        help="Host port the local DB is mapped to (default: 5435)")
    parser.add_argument("--compose-file", metavar="FILE",
                        help="Compose file for Postgres reset (default: auto-detect)")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--check", action="store_true",
                       help="Report state across all systems (read-only)")
    group.add_argument("--dry-run", action="store_true",
                       help="Show what would be done (read-only)")
    args = parser.parse_args()

    pg_extra = ["--db-port", str(args.db_port)]
    if args.compose_file:
        pg_extra += ["--compose-file", args.compose_file]

    # -----------------------------------------------------------------------
    # Check / dry-run: delegate and exit
    # -----------------------------------------------------------------------

    if args.check or args.dry_run:
        mode_flag = "--check" if args.check else "--dry-run"
        for script, extra in [
            ("clear_clerk.py", []),
            ("clear_s3.py", []),
            ("clear_postgres.py", pg_extra),
        ]:
            run_script(script, [mode_flag, *extra], args.env_file)
        return

    # -----------------------------------------------------------------------
    # Run mode: safety checks + confirmation
    # -----------------------------------------------------------------------

    env = load_env(args.env_file)
    require_dev_env(env)

    # Show current state first
    header("Current state (--check)")
    for script, extra in [
        ("clear_clerk.py", []),
        ("clear_s3.py", []),
        ("clear_postgres.py", pg_extra),
    ]:
        run_script(script, ["--check", *extra], args.env_file)

    # Confirmation prompt
    print(f"\n{BOLD}{RED}WARNING{RESET} — This will permanently delete all data in:")
    print("  • Clerk (all users)")
    print("  • S3 bucket (all objects)")
    print("  • Postgres (all tables, then re-migrate)")
    print()
    confirm = input("Type RESET to continue, or anything else to abort: ").strip()
    if confirm != "RESET":
        info("Aborted — nothing was changed")
        sys.exit(0)

    # -----------------------------------------------------------------------
    # Execute
    # -----------------------------------------------------------------------

    header("Clearing Clerk")
    if not run_script("clear_clerk.py", [], args.env_file):
        fail("Clerk clear failed — aborting before touching S3 or Postgres")

    header("Clearing S3")
    if not run_script("clear_s3.py", [], args.env_file):
        warn("S3 clear failed — continuing to Postgres reset")

    header("Resetting Postgres")
    if not run_script("clear_postgres.py", pg_extra, args.env_file):
        fail("Postgres reset failed")

    # Verify
    header("Verifying clean state")
    for script, extra in [
        ("clear_clerk.py", []),
        ("clear_s3.py", []),
        ("clear_postgres.py", pg_extra),
    ]:
        run_script(script, ["--check", *extra], args.env_file)

    print()
    ok("Reset complete — instance is in a clean state")
    info("Next: run 'python -m app.cli seed' to populate with seed users (see issue #140)")


if __name__ == "__main__":
    main()
