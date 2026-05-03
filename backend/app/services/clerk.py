"""Clerk Backend API — user metadata helpers."""

import logging

import httpx

from app.config import get_settings

log = logging.getLogger(__name__)

_BASE = "https://api.clerk.com/v1"


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {get_settings().clerk_secret_key}"}


def _parse_clerk_user(u: dict) -> dict:
    email = (u.get("email_addresses") or [{}])[0].get("email_address", "")
    first = u.get("first_name") or ""
    last = u.get("last_name") or ""
    display_name = f"{first} {last}".strip() or email
    return {"id": u["id"], "email": email, "display_name": display_name}


async def get_clerk_user(clerk_user_id: str) -> dict | None:
    """Fetch a single Clerk user. Returns None if not found."""
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{_BASE}/users/{clerk_user_id}", headers=_headers(), timeout=10)
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return _parse_clerk_user(r.json())
    except Exception:
        log.exception("Failed to fetch Clerk user %s", clerk_user_id)
        return None


async def list_clerk_users() -> list[dict]:
    """Return all Clerk users as [{id, email, display_name}], paginated."""
    users: list[dict] = []
    limit = 500
    offset = 0
    async with httpx.AsyncClient() as client:
        while True:
            r = await client.get(
                f"{_BASE}/users",
                headers=_headers(),
                params={"limit": limit, "offset": offset},
                timeout=30,
            )
            r.raise_for_status()
            batch = r.json()
            users.extend(_parse_clerk_user(u) for u in batch)
            if len(batch) < limit:
                break
            offset += limit
    return users


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
