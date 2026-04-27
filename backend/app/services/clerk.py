"""Clerk Backend API — user metadata helpers."""

import logging

import httpx

from app.config import get_settings

log = logging.getLogger(__name__)

_BASE = "https://api.clerk.com/v1"


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {get_settings().clerk_secret_key}"}


async def set_user_metadata(clerk_user_id: str, public_metadata: dict) -> None:
    """Merge public_metadata onto the Clerk user. Silently logs on failure."""
    try:
        async with httpx.AsyncClient() as client:
            r = await client.patch(
                f"{_BASE}/users/{clerk_user_id}/metadata",
                headers=_headers(),
                json={"public_metadata": public_metadata},
                timeout=10,
            )
            r.raise_for_status()
    except Exception:
        log.exception("Failed to update Clerk metadata for %s", clerk_user_id)


async def ban_clerk_user(clerk_user_id: str) -> None:
    async with httpx.AsyncClient() as client:
        r = await client.post(f"{_BASE}/users/{clerk_user_id}/ban", headers=_headers(), timeout=10)
        r.raise_for_status()


async def unban_clerk_user(clerk_user_id: str) -> None:
    async with httpx.AsyncClient() as client:
        r = await client.post(f"{_BASE}/users/{clerk_user_id}/unban", headers=_headers(), timeout=10)
        r.raise_for_status()
