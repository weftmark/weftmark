#!/usr/bin/env python3
"""Clear all users from a Clerk instance.

Modes:
  --check    List users and count (read-only, no APP_ENV restriction)
  --dry-run  Show which users would be deleted (read-only)
  (default)  Delete all users — requires APP_ENV=dev
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _lib import dry, fail, header, info, load_env, ok, require_dev_env, warn

CLERK_API = "https://api.clerk.com/v1"


def _clerk_request(secret_key: str, method: str, path: str) -> object:
    req = urllib.request.Request(
        f"{CLERK_API}{path}",
        method=method,
        headers={
            "Authorization": f"Bearer {secret_key}",
            "User-Agent": "WeftMark-DevTools/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")
        fail(f"Clerk API {method} {path} → {exc.code}: {body[:200]}")


def fetch_all_users(secret_key: str) -> list[dict]:
    users: list[dict] = []
    limit = 100
    offset = 0
    while True:
        page = _clerk_request(secret_key, "GET", f"/users?limit={limit}&offset={offset}")
        if not isinstance(page, list) or not page:
            break
        users.extend(page)
        if len(page) < limit:
            break
        offset += limit
    return users


def _primary_email(user: dict) -> str:
    primary_id = user.get("primary_email_address_id", "")
    for addr in user.get("email_addresses", []):
        if addr.get("id") == primary_id:
            return addr.get("email_address", "—")
    return "—"


def _format_user(user: dict) -> str:
    email = _primary_email(user)
    username = user.get("username") or "—"
    return f"{user['id']}  {email}  ({username})"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--env-file", default=".env.local", metavar="PATH", help="Path to .env file (default: .env.local)")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--check", action="store_true", help="Report user count and list (read-only)")
    group.add_argument("--dry-run", action="store_true", help="Show what would be deleted (read-only)")
    args = parser.parse_args()

    env = load_env(args.env_file)
    secret_key = env.get("CLERK_SECRET_KEY", "").strip()
    if not secret_key:
        fail("CLERK_SECRET_KEY not set in env file")

    header("Clerk — users")
    users = fetch_all_users(secret_key)

    if not users:
        ok("Clerk instance is empty — 0 users")
        return

    if args.check:
        info(f"{len(users)} user(s) found:")
        for u in users:
            print(f"  {_format_user(u)}")
        return

    if args.dry_run:
        info(f"Would delete {len(users)} user(s):")
        for u in users:
            dry(_format_user(u))
        return

    require_dev_env(env)
    info(f"Deleting {len(users)} user(s)…")
    errors = 0
    for u in users:
        label = _primary_email(u)
        try:
            _clerk_request(secret_key, "DELETE", f"/users/{u['id']}")
            ok(f"Deleted {label}  ({u['id']})")
        except SystemExit:
            warn(f"Failed to delete {label}  ({u['id']})")
            errors += 1
        time.sleep(0.1)  # avoid Clerk rate limit

    print()
    if errors:
        warn(f"Done with {errors} error(s) — re-run --check to verify")
    else:
        ok(f"All {len(users)} user(s) deleted")


if __name__ == "__main__":
    main()
