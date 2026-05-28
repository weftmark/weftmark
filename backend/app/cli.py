"""CLI entry point — invoked as `python -m app.cli <command>`.

Usage:
    python -m app.cli seed [--config seed.json] [--poll-timeout 30]
    docker compose exec backend python -m app.cli seed
    docker compose run --rm backend python -m app.cli seed
"""

import argparse
import asyncio
import json
import shutil
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.config import get_settings
from app.models.seed_run import SeedRun
from app.models.user import User

_BACKEND_DIR = Path(__file__).parent.parent
_ALEMBIC_INI = _BACKEND_DIR / "alembic.ini"

_BASE = "https://api.clerk.com/v1"


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------


def _ok(msg: str) -> None:
    print(f"  ✓ {msg}")


def _err(msg: str) -> None:
    print(f"  ✗ {msg}", file=sys.stderr)


def _section(msg: str) -> None:
    print(f"\n{msg}")


# ---------------------------------------------------------------------------
# Clerk helpers (CLI-only)
# ---------------------------------------------------------------------------


async def _clerk_list_users(secret_key: str, limit: int = 2) -> list[dict]:
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.get(
            f"{_BASE}/users",
            headers={"Authorization": f"Bearer {secret_key}"},
            params={"limit": limit},
        )
        r.raise_for_status()
        return r.json()  # type: ignore[no-any-return]


async def _clerk_delete_all_users(secret_key: str) -> int:
    """Delete every user from the Clerk instance. Returns count deleted."""
    deleted = 0
    headers = {"Authorization": f"Bearer {secret_key}"}
    async with httpx.AsyncClient(timeout=30.0) as client:
        while True:
            r = await client.get(f"{_BASE}/users", headers=headers, params={"limit": 100})
            r.raise_for_status()
            users = r.json()
            if not users:
                break
            for user in users:
                d = await client.delete(f"{_BASE}/users/{user['id']}", headers=headers)
                d.raise_for_status()
                deleted += 1
    return deleted


async def _clerk_create_user(secret_key: str, email: str, username: str, password: str, display_name: str) -> dict:
    first, *rest = display_name.split(" ", 1)
    async with httpx.AsyncClient(timeout=10.0) as client:
        r = await client.post(
            f"{_BASE}/users",
            headers={"Authorization": f"Bearer {secret_key}"},
            json={
                "email_address": [email],
                "username": username,
                "password": password,
                "first_name": first,
                "last_name": rest[0] if rest else "",
            },
        )
        r.raise_for_status()
        return r.json()  # type: ignore[no-any-return]


# ---------------------------------------------------------------------------
# Alembic reset
# ---------------------------------------------------------------------------


def _alembic_reset() -> None:
    from alembic.config import Config

    from alembic import command as alembic_command

    cfg = Config(str(_ALEMBIC_INI))
    alembic_command.downgrade(cfg, "base")
    alembic_command.upgrade(cfg, "head")


# ---------------------------------------------------------------------------
# Storage clear
# ---------------------------------------------------------------------------


def _clear_storage(settings: Any) -> None:
    if settings.storage_backend == "s3":
        _clear_s3(settings)
    else:
        _clear_local(settings)


def _clear_local(settings: Any) -> None:
    upload_dir = Path(settings.upload_dir)
    if upload_dir.exists():
        shutil.rmtree(upload_dir)
    upload_dir.mkdir(parents=True, exist_ok=True)
    _ok(f"Local upload directory cleared ({upload_dir})")


def _clear_s3(settings: Any) -> None:
    import boto3

    client = boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url or None,
        aws_access_key_id=settings.s3_access_key_id,
        aws_secret_access_key=settings.s3_secret_access_key,
        region_name=settings.s3_region or "auto",
    )
    bucket = settings.s3_bucket_name
    paginator = client.get_paginator("list_objects_v2")
    total = 0
    for page in paginator.paginate(Bucket=bucket):
        objects = page.get("Contents", [])
        if objects:
            client.delete_objects(
                Bucket=bucket,
                Delete={"Objects": [{"Key": o["Key"]} for o in objects]},
                **settings.s3_owner_kwargs,
            )
            total += len(objects)
    _ok(f"S3 bucket '{bucket}' cleared ({total} objects deleted)")


# ---------------------------------------------------------------------------
# DB polling
# ---------------------------------------------------------------------------


async def _preregister_user(
    session_factory: async_sessionmaker,
    email: str,
    display_name: str,
    role: str,
) -> User:
    """Insert a pre-created User record (clerk_user_id=None). The webhook attaches the ID."""
    is_admin = role in ("admin", "superuser")
    is_superuser = role == "superuser"
    async with session_factory() as session:
        user = User(
            email=email,
            display_name=display_name,
            is_admin=is_admin,
            is_superuser=is_superuser,
            ai_training_consent=True,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


async def _poll_for_clerk_attach(
    session_factory: async_sessionmaker,
    user_id: uuid.UUID,
    timeout: int,
) -> User:
    """Poll until the webhook attaches a clerk_user_id to the pre-created User."""
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout
    while True:
        async with session_factory() as session:
            user = await session.get(User, user_id)
            if user and user.clerk_user_id is not None:
                return user  # type: ignore[no-any-return]
        if loop.time() >= deadline:
            raise TimeoutError(
                f"user_id={user_id} never received a clerk_user_id after {timeout}s — "
                "is the webhook configured and reachable?"
            )
        await asyncio.sleep(1)


# ---------------------------------------------------------------------------
# seed command
# ---------------------------------------------------------------------------


async def cmd_seed(config_path: str, poll_timeout: int) -> None:
    settings = get_settings()

    # ── Prechecks ──────────────────────────────────────────────────────────
    _section("Prechecks")

    if settings.app_env != "dev":
        _err(f"APP_ENV must be 'dev', got '{settings.app_env}'")
        sys.exit(1)
    _ok(f"APP_ENV = {settings.app_env}")

    if not settings.seed_enabled:
        _err("SEED_ENABLED is not set to true")
        sys.exit(1)
    _ok("SEED_ENABLED = true")

    if not settings.clerk_secret_key:
        _err("CLERK_SECRET_KEY is not set")
        sys.exit(1)

    try:
        existing_clerk = await _clerk_list_users(settings.clerk_secret_key, limit=1)
        user_word = "user" if len(existing_clerk) == 1 else "users"
        count_str = (
            f"{len(existing_clerk)} existing {user_word} — will be deleted" if existing_clerk else "0 existing users"
        )
        _ok(f"Clerk reachable ({count_str})")
    except Exception as exc:
        _err(f"Clerk API unreachable: {exc}")
        sys.exit(1)

    engine = create_async_engine(settings.database_url, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            await session.execute(text("SELECT 1"))
    except Exception as exc:
        _err(f"DB unreachable: {exc}")
        await engine.dispose()
        sys.exit(1)
    _ok("DB reachable")

    # ── Load config ────────────────────────────────────────────────────────
    config_file = Path(config_path)
    if not config_file.exists():
        _err(f"Seed config not found: {config_file.resolve()}")
        await engine.dispose()
        sys.exit(1)
    try:
        seed = json.loads(config_file.read_text())
    except Exception as exc:
        _err(f"Failed to parse seed config: {exc}")
        await engine.dispose()
        sys.exit(1)

    users_cfg: list[dict] = seed.get("users", [])
    if not users_cfg:
        _err("No users defined in seed config")
        await engine.dispose()
        sys.exit(1)

    # ── Reset ──────────────────────────────────────────────────────────────
    _section("Reset")

    await engine.dispose()

    try:
        deleted_count = await _clerk_delete_all_users(settings.clerk_secret_key)
        _ok(f"Clerk: deleted {deleted_count} user(s)")
    except Exception as exc:
        _err(f"Clerk user deletion failed: {exc}")
        sys.exit(1)

    try:
        _alembic_reset()
        _ok("Alembic downgrade base → upgrade head complete")
    except Exception as exc:
        _err(f"Alembic reset failed: {exc}")
        sys.exit(1)

    try:
        _clear_storage(settings)
    except Exception as exc:
        _err(f"Storage clear failed: {exc}")
        sys.exit(1)

    engine = create_async_engine(settings.database_url, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    # ── Seed users ─────────────────────────────────────────────────────────
    _section("Users")

    generated_passwords: list[tuple[str, str]] = []

    for cfg in users_cfg:
        email: str = cfg["email"]
        username: str = cfg["username"]
        display_name: str = cfg.get("display_name", username)
        role: str = cfg.get("role", "user")
        password: str | None = cfg.get("password")

        auto_password = password is None
        if auto_password:
            password = uuid.uuid4().hex

        # 1. Pre-create the User record with the intended role.
        pre_user = await _preregister_user(session_factory, email, display_name, role)
        _ok(f"{email} pre-registered in DB (id={pre_user.id}, role={role})")

        # 2. Create the Clerk account — the webhook will attach the clerk_user_id.
        try:
            clerk_user = await _clerk_create_user(settings.clerk_secret_key, email, username, password, display_name)  # type: ignore[arg-type]
            clerk_user_id: str = clerk_user["id"]
            _ok(f"{email} created in Clerk (clerk_user_id={clerk_user_id})")
        except httpx.HTTPStatusError as exc:
            _err(f"{email} — Clerk creation failed: {exc.response.text}")
            await engine.dispose()
            sys.exit(1)
        except Exception as exc:
            _err(f"{email} — Clerk creation failed: {exc}")
            await engine.dispose()
            sys.exit(1)

        # 3. Poll until the webhook attaches the Clerk ID to the pre-created User.
        try:
            db_user = await _poll_for_clerk_attach(session_factory, pre_user.id, poll_timeout)
            _ok(f"{email} confirmed in DB (clerk_user_id={db_user.clerk_user_id})")
        except TimeoutError as exc:
            _err(str(exc))
            await engine.dispose()
            sys.exit(1)

        if auto_password:
            generated_passwords.append((email, password))  # type: ignore[arg-type]

    # ── Record seed run ────────────────────────────────────────────────────
    async with session_factory() as session:
        await session.merge(SeedRun(id=1, ran_at=datetime.now(timezone.utc)))
        await session.commit()

    await engine.dispose()

    # ── Summary ────────────────────────────────────────────────────────────
    if generated_passwords:
        _section("Generated passwords")
        for addr, pw in generated_passwords:
            print(f"  {addr}: {pw}")

    print(f"\nSeed complete — {len(users_cfg)} user(s) created.")


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    sub = parser.add_subparsers(dest="command", required=True)

    seed_p = sub.add_parser("seed", help="Wipe and reseed a dev WeftMark instance")
    seed_p.add_argument(
        "--config",
        default="seed.json",
        help="Path to seed config JSON (default: seed.json)",
    )
    seed_p.add_argument(
        "--poll-timeout",
        type=int,
        default=30,
        metavar="SECONDS",
        help="How long to wait for the webhook to confirm each user in DB (default: 30)",
    )

    args = parser.parse_args()
    if args.command == "seed":
        asyncio.run(cmd_seed(args.config, args.poll_timeout))


if __name__ == "__main__":
    main()
