"""Shared utilities for WeftMark dev scripts."""

from __future__ import annotations

import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# ANSI output
# ---------------------------------------------------------------------------

BOLD = "\033[1m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
CYAN = "\033[36m"
DIM = "\033[2m"
RESET = "\033[0m"


def ok(msg: str) -> None:
    print(f"{GREEN}✓{RESET} {msg}")


def warn(msg: str) -> None:
    print(f"{YELLOW}⚠{RESET}  {msg}")


def fail(msg: str, exit_code: int = 1) -> None:
    print(f"{RED}✗{RESET}  {msg}", file=sys.stderr)
    sys.exit(exit_code)


def info(msg: str) -> None:
    print(f"{CYAN}→{RESET} {msg}")


def header(msg: str) -> None:
    print(f"\n{BOLD}{msg}{RESET}")


def dry(msg: str) -> None:
    print(f"{DIM}  (dry-run){RESET} {msg}")


# ---------------------------------------------------------------------------
# Env file loading
# ---------------------------------------------------------------------------


def load_env(path: str) -> dict[str, str]:
    """Parse a .env file and return {KEY: value}, stripping quotes and comments."""
    env: dict[str, str] = {}
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("export "):
                    line = line[7:]
                if "=" not in line:
                    continue
                key, _, val = line.partition("=")
                key = key.strip()
                val = val.strip()
                # strip surrounding single or double quotes
                if len(val) >= 2 and val[0] == val[-1] and val[0] in "\"'":
                    val = val[1:-1]
                env[key] = val
    except FileNotFoundError:
        fail(f"Env file not found: {path}")
    return env


# ---------------------------------------------------------------------------
# Safety gate
# ---------------------------------------------------------------------------


def require_dev_env(env: dict[str, str]) -> None:
    """Abort unless APP_ENV=dev. Call this before any destructive operation."""
    app_env = env.get("APP_ENV", "")
    if app_env != "dev":
        fail(
            f"APP_ENV='{app_env}' — must be 'dev' to run destructive operations.\n"
            "  Set APP_ENV=dev in your env file, or use --check / --dry-run."
        )


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


def format_bytes(n: int | float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


# ---------------------------------------------------------------------------
# Postgres DSN resolution
# ---------------------------------------------------------------------------


def resolve_postgres_dsn(env: dict[str, str], host_port: int = 5435) -> str:
    """
    Return a plain postgresql:// DSN suitable for asyncpg or psql.

    Priority:
    1. POSTGRES_DSN_DIRECT (Neon direct connection / explicit override)
    2. POSTGRES_DSN (pooled connection — works for read-only checks)
    3. Build from POSTGRES_HOST / USER / PASSWORD / DB with host_port override
       for local Docker setups where the container port is remapped on the host.
    """
    dsn = env.get("POSTGRES_DSN_DIRECT") or env.get("POSTGRES_DSN") or ""
    if dsn:
        # strip SQLAlchemy driver prefix if present
        for prefix in ("postgresql+asyncpg://", "postgresql+psycopg2://"):
            if dsn.startswith(prefix):
                dsn = "postgresql://" + dsn[len(prefix):]
        return dsn

    # Build from individual vars
    host = env.get("POSTGRES_HOST", "localhost")
    if host == "db":
        host = "127.0.0.1"
    db = env.get("POSTGRES_DB", "weaving_site")
    user = env.get("POSTGRES_USER", "")
    password = env.get("POSTGRES_PASSWORD", "")
    return f"postgresql://{user}:{password}@{host}:{host_port}/{db}"
