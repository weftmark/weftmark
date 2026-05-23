"""Ravelry OAuth and stash sync service — uses ravelpy 0.3.0 async client."""

import asyncio
import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import httpx
from ravelpy import RavelryClient
from ravelpy.oauth import OAuthClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.ravelry import RavelryCredential, RavelryOAuthState
from app.models.yarn import Yarn

logger = logging.getLogger(__name__)

OAUTH_SCOPE = "offline"
STATE_TTL_MINUTES = 10
_RAVELRY_API = "https://api.ravelry.com"


async def _basic_auth_get(path: str, params: dict | None = None) -> dict:
    """GET against the Ravelry API using the developer read-only key (no OAuth)."""
    settings = get_settings()
    if not settings.ravelry_read_access_username or not settings.ravelry_read_access_key:
        raise ValueError("RAVELRY_READ_ACCESS_USERNAME / RAVELRY_READ_ACCESS_KEY are not configured")
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{_RAVELRY_API}{path}",
            params={k: v for k, v in (params or {}).items() if v is not None},
            auth=(settings.ravelry_read_access_username, settings.ravelry_read_access_key),
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()


# ---------------------------------------------------------------------------
# CSRF state helpers
# ---------------------------------------------------------------------------


def _generate_state() -> str:
    return secrets.token_urlsafe(32)


def _oauth_client() -> OAuthClient:
    settings = get_settings()
    return OAuthClient(
        client_id=settings.ravelry_oauth_client_id,
        client_secret=settings.ravelry_oauth_client_secret,
        redirect_uri=settings.ravelry_oauth_redirect_uri,
    )


# ---------------------------------------------------------------------------
# OAuth state persistence
# ---------------------------------------------------------------------------


async def create_oauth_state(user_id: uuid.UUID, db: AsyncSession) -> tuple[str, str]:
    """Persist CSRF state; return (state, authorization_url)."""
    settings = get_settings()
    if not settings.ravelry_oauth_client_id:
        raise ValueError("RAVELRY_OAUTH_CLIENT_ID is not configured")

    state = _generate_state()
    db.add(
        RavelryOAuthState(
            state=state,
            user_id=user_id,
            code_verifier="",  # Ravelry does not support PKCE; kept for schema compat
            created_at=datetime.now(timezone.utc),
        )
    )
    await db.commit()

    auth_url, _ = _oauth_client().auth_url(scopes=[OAUTH_SCOPE], state=state)
    return state, auth_url


async def consume_oauth_state(state: str, db: AsyncSession) -> RavelryOAuthState | None:
    """Return the state record if valid and not expired; delete it."""
    record = await db.get(RavelryOAuthState, state)
    if record is None:
        return None
    if datetime.now(timezone.utc) > record.created_at + timedelta(minutes=STATE_TTL_MINUTES):
        await db.delete(record)
        await db.commit()
        return None
    await db.delete(record)
    await db.commit()
    return record


# ---------------------------------------------------------------------------
# Token exchange and refresh
# ---------------------------------------------------------------------------


async def exchange_code(code: str) -> dict:
    """Exchange authorization code for tokens; return raw token response dict."""
    token_resp = await _oauth_client().exchange_code(code)
    return token_resp.to_dict()


async def refresh_access_token(credential: RavelryCredential, db: AsyncSession) -> None:
    """Refresh access token in-place and persist."""
    if not credential.refresh_token:
        raise ValueError("No refresh token available")
    token_resp = await _oauth_client().refresh(credential.refresh_token)
    credential.access_token = token_resp.access_token
    if token_resp.refresh_token:
        credential.refresh_token = token_resp.refresh_token
    credential.expires_at = datetime.now(timezone.utc) + timedelta(seconds=token_resp.expires_in)
    await db.commit()


async def _get_valid_token(credential: RavelryCredential, db: AsyncSession) -> str:
    if credential.expires_at:
        if credential.expires_at <= datetime.now(timezone.utc) + timedelta(seconds=60):
            await refresh_access_token(credential, db)
    return credential.access_token


# ---------------------------------------------------------------------------
# Current user lookup
# ---------------------------------------------------------------------------


async def fetch_ravelry_username(access_token: str) -> str:
    async with RavelryClient.from_oauth_token(access_token) as client:
        _, _, raw = await client.people.me()
    return raw["user"]["username"]


# ---------------------------------------------------------------------------
# Credential persistence helpers
# ---------------------------------------------------------------------------


async def get_credential(user_id: uuid.UUID, db: AsyncSession) -> RavelryCredential | None:
    return await db.scalar(select(RavelryCredential).where(RavelryCredential.user_id == user_id))


async def save_credential(user_id: uuid.UUID, token_data: dict, db: AsyncSession) -> RavelryCredential:
    access_token = token_data["access_token"]
    username = await fetch_ravelry_username(access_token)

    existing = await get_credential(user_id, db)
    expires_at = None
    if "expires_in" in token_data:
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=int(token_data["expires_in"]))

    if existing:
        existing.access_token = access_token
        existing.refresh_token = token_data.get("refresh_token")
        existing.expires_at = expires_at
        existing.ravelry_username = username
        await db.commit()
        return existing

    cred = RavelryCredential(
        id=uuid.uuid4(),
        user_id=user_id,
        ravelry_username=username,
        access_token=access_token,
        refresh_token=token_data.get("refresh_token"),
        expires_at=expires_at,
    )
    db.add(cred)
    await db.commit()
    return cred


# ---------------------------------------------------------------------------
# Yarn detail proxy
# ---------------------------------------------------------------------------


async def fetch_yarn_detail(ravelry_yarn_id: int, cred: RavelryCredential, db: AsyncSession) -> dict:
    """Fetch full yarn detail from Ravelry including colorways."""
    token = await _get_valid_token(cred, db)
    # Use direct HTTP call — the ravelpy model strips the top-level `colorways` key
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{_RAVELRY_API}/yarns/{ravelry_yarn_id}.json",
            params={"include": "colorways"},
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()


async def get_popular_yarn_companies(limit: int = 10) -> list[dict]:
    """Return popular yarn companies using Ravelry's best sort (no specific query)."""
    raw = await _basic_auth_get(
        "/yarn_companies/search.json",
        {"sort": "best", "page_size": limit},
    )
    companies = (raw or {}).get("yarn_companies") or []
    return [{"id": c["id"], "name": c.get("name") or "", "permalink": c.get("permalink") or ""} for c in companies]


async def get_popular_yarns_for_company(company_id: int, company_name: str, limit: int = 8) -> list[dict]:
    """Return popular yarns for a company — yarn_company_id filter requires a non-empty query,
    so we seed with the first meaningful word of the company name."""
    words = [w for w in company_name.split() if len(w) > 3]
    seed = words[0] if words else company_name.split()[0]
    params: dict = {"query": f"{seed}*", "yarn_company_id": company_id, "sort": "best", "page_size": limit}
    raw = await _basic_auth_get("/yarns/search.json", params)
    yarns = (raw or {}).get("yarns") or []
    results = []
    for y in yarns:
        photos = y.get("photos") or []
        photo_url = photos[0].get("square_url") if photos else None
        results.append(
            {
                "id": y["id"],
                "name": y.get("name") or "",
                "company_name": y.get("yarn_company_name") or "",
                "permalink": y.get("permalink") or "",
                "weight_name": (y.get("yarn_weight") or {}).get("name"),
                "photo_url": photo_url,
            }
        )
    return results


async def search_yarn_companies(query: str) -> list[dict]:
    """Search Ravelry yarn companies using the dev read-only key."""
    raw = await _basic_auth_get("/yarn_companies/search.json", {"query": f"{query}*", "page_size": 20})
    companies = (raw or {}).get("yarn_companies") or []
    return [{"id": c["id"], "name": c.get("name") or "", "permalink": c.get("permalink") or ""} for c in companies]


async def search_yarns(query: str, company_id: int | None) -> list[dict]:
    """Search Ravelry yarns using the dev read-only key, optionally filtered by company."""
    params: dict = {"query": f"{query}*", "page_size": 20}
    if company_id:
        params["yarn_company_id"] = company_id
    raw = await _basic_auth_get("/yarns/search.json", params)
    yarns = (raw or {}).get("yarns") or []
    results = []
    for y in yarns:
        photos = y.get("photos") or []
        photo_url = photos[0].get("square_url") if photos else None
        results.append(
            {
                "id": y["id"],
                "name": y.get("name") or "",
                "company_name": y.get("yarn_company_name") or "",
                "permalink": y.get("permalink") or "",
                "weight_name": (y.get("yarn_weight") or {}).get("name"),
                "photo_url": photo_url,
            }
        )
    return results


async def import_yarn_from_ravelry(
    user_id: uuid.UUID,
    ravelry_yarn_id: int,
    color_name: str | None,
    color_hex: str | None,
    db: AsyncSession,
) -> Yarn:
    """Create a Yarn record from a Ravelry yarn using the dev read-only key."""
    raw = await _basic_auth_get(f"/yarns/{ravelry_yarn_id}.json")
    yarn_data = raw.get("yarn") or {}
    company = yarn_data.get("yarn_company") or {}
    weight_info = yarn_data.get("yarn_weight") or {}

    brand = company.get("name") or "Unknown"
    name = yarn_data.get("name") or "Unknown"
    weight_category = _map_weight(weight_info.get("name"))
    fiber_content = yarn_data.get("fiber_content")
    permalink = yarn_data.get("permalink") or None
    discontinued = bool(yarn_data.get("discontinued") or False)
    machine_washable = yarn_data.get("machine_washable")
    yarn_company_url = company.get("url") or None
    unit_yardage_raw = yarn_data.get("yardage")
    unit_yardage = Decimal(str(unit_yardage_raw)) if unit_yardage_raw else None

    photos = yarn_data.get("photos") or []
    photo_url = None
    thumbnail_url = None
    if photos:
        sorted_photos = sorted(photos, key=lambda p: p.get("sort_order") or 999)
        first = sorted_photos[0]
        photo_url = first.get("medium_url") or first.get("small_url") or first.get("square_url")
        thumbnail_url = first.get("square_url") or first.get("thumbnail_url") or first.get("small_url")

    yarn = Yarn(
        owner_id=user_id,
        brand=brand,
        name=name,
        color_name=color_name or None,
        color_hex=color_hex or None,
        weight_category=weight_category,
        fiber_content=fiber_content,
        unit_yardage=unit_yardage,
        ravelry_yarn_id=ravelry_yarn_id,
        ravelry_photo_url=photo_url,
        ravelry_thumbnail_url=thumbnail_url,
        ravelry_permalink=permalink,
        ravelry_discontinued=discontinued,
        ravelry_machine_washable=machine_washable,
        ravelry_yarn_company_url=yarn_company_url,
    )
    db.add(yarn)
    await db.commit()
    await db.refresh(yarn)
    logger.info("Imported yarn %s from Ravelry yarn %s for user %s", yarn.id, ravelry_yarn_id, user_id)
    return yarn


# ---------------------------------------------------------------------------
# Weight / color helpers
# ---------------------------------------------------------------------------


def _map_weight(ravelry_weight_name: str | None) -> str | None:
    if not ravelry_weight_name:
        return None
    mapping = {
        "Thread": "thread",
        "Cobweb": "lace",
        "Lace": "lace",
        "Light Fingering": "fingering",
        "Fingering": "fingering",
        "Sport": "sport",
        "DK": "dk",
        "Worsted": "worsted",
        "Aran": "aran",
        "Bulky": "bulky",
        "Super Bulky": "super_bulky",
        "Jumbo": "super_bulky",
    }
    return mapping.get(ravelry_weight_name)


_COLOR_FAMILY_HEX: dict[str, str | None] = {
    "Black": "#1a1a1a",
    "White": "#f5f5f5",
    "Gray": "#9e9e9e",
    "Grey": "#9e9e9e",
    "Beige / Tan": "#c8a97a",
    "Brown": "#7b4f2e",
    "Red": "#c0392b",
    "Pink": "#e91e8c",
    "Orange": "#e67e22",
    "Yellow": "#f1c40f",
    "Green": "#27ae60",
    "Blue": "#2980b9",
    "Purple": "#8e44ad",
    "Multi": None,
    "Variegated": None,
    "Neon": None,
}


def _color_family_to_hex(color_family_name: str | None) -> str | None:
    if not color_family_name:
        return None
    if color_family_name in _COLOR_FAMILY_HEX:
        return _COLOR_FAMILY_HEX[color_family_name]
    lower = color_family_name.lower()
    for key, val in _COLOR_FAMILY_HEX.items():
        if key.lower() == lower:
            return val
    return None


# ---------------------------------------------------------------------------
# Stash sync
# ---------------------------------------------------------------------------


async def sync_stash(user_id: uuid.UUID, db: AsyncSession) -> dict:
    """Sync user's Ravelry stash into local Yarn records.

    Returns {synced: int, unchanged: bool, last_synced_at: str}.
    Uses ETag caching — 304 means no changes; only last_synced_at is updated.

    Ravelry stash is an entry point only — yarns are created/updated but
    skeins are never synced (managed in WeftMark independently).
    Removal policy: losing the Ravelry stash tag (out_of_stash=True) does not
    archive the yarn; it stays visible until the user explicitly archives or
    deletes it.
    """

    cred = await get_credential(user_id, db)
    if cred is None:
        raise ValueError("No Ravelry credential found for user")

    token = await _get_valid_token(cred, db)

    async with RavelryClient.from_oauth_token(token) as client:
        parsed, new_etag, raw = await client.stash.list(
            username=cred.ravelry_username,
            etag=cred.stash_etag,
        )

    if parsed is None:  # 304 Not Modified
        now = datetime.now(timezone.utc)
        cred.stash_last_synced_at = now
        await db.commit()
        return {"synced": 0, "unchanged": True, "last_synced_at": now}

    stash_entries: list[dict] = raw.get("stash", [])
    synced_ids: set[int] = set()
    upsert_count = 0

    for entry in stash_entries:
        stash_id: int = entry["id"]
        synced_ids.add(stash_id)

        yarn_data = entry.get("yarn") or {}
        company = yarn_data.get("yarn_company") or {}
        weight_info = yarn_data.get("yarn_weight") or {}

        brand = company.get("name") or "Unknown"
        name = yarn_data.get("name") or entry.get("name") or "Unknown"
        color_name = entry.get("colorway_name")
        weight_category = _map_weight(weight_info.get("name"))
        fiber_content = yarn_data.get("fiber_content")
        ravelry_yarn_id: int | None = yarn_data.get("id") or None
        permalink: str | None = yarn_data.get("permalink") or None
        discontinued: bool = bool(yarn_data.get("discontinued") or False)
        machine_washable: bool | None = yarn_data.get("machine_washable")
        yarn_company_url: str | None = company.get("url") or None

        yarn_photos: list[dict] = yarn_data.get("photos") or []
        stash_photos: list[dict] = entry.get("photos") or []
        photo_candidates = yarn_photos if yarn_photos else stash_photos
        photo_url: str | None = None
        thumbnail_url: str | None = None
        if photo_candidates:
            sorted_photos = sorted(photo_candidates, key=lambda p: p.get("sort_order") or 999)
            first = sorted_photos[0]
            photo_url = first.get("medium_url") or first.get("small_url") or first.get("square_url")
            thumbnail_url = first.get("square_url") or first.get("thumbnail_url") or first.get("small_url")

        color_family = entry.get("color_family_name") or (
            (yarn_data.get("personal_attributes") or {}).get("color_family_name")
        )
        color_hex_guess = _color_family_to_hex(color_family)
        unit_yardage_raw = yarn_data.get("yardage")
        unit_yardage = Decimal(str(unit_yardage_raw)) if unit_yardage_raw else None

        existing: Yarn | None = await db.scalar(
            select(Yarn).where(
                Yarn.owner_id == user_id,
                Yarn.ravelry_stash_id == stash_id,
                Yarn.deleted_at.is_(None),
            )
        )

        if existing:
            existing.brand = brand
            existing.name = name
            existing.color_name = color_name
            existing.weight_category = weight_category
            existing.fiber_content = fiber_content
            existing.unit_yardage = unit_yardage
            if ravelry_yarn_id:
                existing.ravelry_yarn_id = ravelry_yarn_id
            if photo_url:
                existing.ravelry_photo_url = photo_url
            if thumbnail_url:
                existing.ravelry_thumbnail_url = thumbnail_url
            if permalink:
                existing.ravelry_permalink = permalink
            existing.ravelry_discontinued = discontinued
            if machine_washable is not None:
                existing.ravelry_machine_washable = machine_washable
            if yarn_company_url:
                existing.ravelry_yarn_company_url = yarn_company_url
            if existing.color_hex is None and color_hex_guess:
                existing.color_hex = color_hex_guess
            if existing.out_of_stash:
                existing.out_of_stash = False
        else:
            existing = Yarn(
                owner_id=user_id,
                brand=brand,
                name=name,
                color_name=color_name,
                color_hex=color_hex_guess,
                weight_category=weight_category,
                fiber_content=fiber_content,
                unit_yardage=unit_yardage,
                ravelry_stash_id=stash_id,
                ravelry_yarn_id=ravelry_yarn_id,
                ravelry_photo_url=photo_url,
                ravelry_thumbnail_url=thumbnail_url,
                ravelry_permalink=permalink,
                ravelry_discontinued=discontinued,
                ravelry_machine_washable=machine_washable,
                ravelry_yarn_company_url=yarn_company_url,
            )
            db.add(existing)
            await db.flush()

        upsert_count += 1

    # Archive yarns removed from Ravelry stash — never hard-delete
    all_ravelry_yarns = await db.scalars(
        select(Yarn).where(
            Yarn.owner_id == user_id,
            Yarn.ravelry_stash_id.is_not(None),
            Yarn.deleted_at.is_(None),
            Yarn.out_of_stash.is_(False),
        )
    )
    for yarn in all_ravelry_yarns.all():
        if yarn.ravelry_stash_id not in synced_ids:
            yarn.out_of_stash = True

    # Backfill photos for yarns missing generic photo or colorway photo.
    # stash/list embeds an empty photos array, so we fetch yarn detail separately.
    yarns_needing_backfill = (
        await db.scalars(
            select(Yarn).where(
                Yarn.owner_id == user_id,
                Yarn.ravelry_yarn_id.is_not(None),
                Yarn.ravelry_photo_url.is_(None),
                Yarn.deleted_at.is_(None),
            )
        )
    ).all()

    if yarns_needing_backfill:
        sem = asyncio.Semaphore(4)

        async def _fill_photo(yarn: Yarn) -> None:
            async with sem:
                try:
                    raw = await _basic_auth_get(f"/yarns/{yarn.ravelry_yarn_id}.json")
                    yarn_node = raw.get("yarn") or {}
                    photos = yarn_node.get("photos") or []
                    if photos:
                        sorted_photos = sorted(photos, key=lambda p: p.get("sort_order") or 999)
                        first = sorted_photos[0]
                        yarn.ravelry_photo_url = (
                            first.get("medium_url") or first.get("small_url") or first.get("square_url")
                        )
                        yarn.ravelry_thumbnail_url = (
                            first.get("square_url") or first.get("thumbnail_url") or first.get("small_url")
                        )
                except Exception:
                    pass

        await asyncio.gather(*[_fill_photo(y) for y in yarns_needing_backfill])

    now = datetime.now(timezone.utc)
    cred.stash_etag = new_etag
    cred.stash_last_synced_at = now
    await db.commit()

    logger.info("Ravelry stash synced for user %s: %d entries", user_id, upsert_count)
    return {"synced": upsert_count, "unchanged": False, "last_synced_at": now}
