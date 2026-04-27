"""
OIDC authentication flow (multi-provider):

  /auth/login?provider=X  → redirect to provider authorization endpoint
  /auth/callback          → GET  — exchange code, resolve identity, set session cookie (Google et al.)
  /auth/callback          → POST — same, for Apple's form_post response mode
  /auth/logout            → clear session cookie
  /auth/me                → return current user info
  /auth/providers         → list enabled OIDC providers

Identity resolution order on each login:
  1. (provider, provider_sub) in user_identities → existing user
  2. users.oidc_sub == provider_sub — legacy fallback for users that existed before migration
  3. users.email == email — cross-provider linking (same email at a new provider)
  4. New user — invite required unless bootstrap

Invite flow:
  /auth/invite       POST   (admin) create invite + send email
  /auth/invites      GET    (admin) list invites
  /auth/invite/{id}  DELETE (admin) revoke invite
  /register?token=X  handled by frontend → redirects to /auth/login?invite_token=X

Bootstrap rule: if zero users exist, the first OIDC registrant is granted admin with no invite.
"""

import json
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
import jwt
from fastapi import APIRouter, Cookie, Depends, Form, HTTPException, Query
from fastapi.responses import JSONResponse, RedirectResponse
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from jwt import PyJWKSet
from jwt.exceptions import PyJWTError as JWTError
from pydantic import BaseModel, EmailStr
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.deps import get_current_user, get_db, require_admin
from app.models.invite import Invite
from app.models.user import User
from app.models.user_identity import UserIdentity
from app.services.email import send_invite_email

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()

_ALGORITHM = "HS256"
_SESSION_COOKIE = "session"
_STATE_COOKIE = "oidc_state"
_INVITE_COOKIE = "oidc_invite"
_STATE_MAX_AGE = 600  # 10 minutes

_signer = URLSafeTimedSerializer(settings.app_secret_key)

# Provider metadata keyed by provider name — populated on startup via load_oidc_metadata()
_oidc_metadata: dict[str, dict[str, Any]] = {}


async def load_oidc_metadata() -> None:
    import logging

    log = logging.getLogger(__name__)
    providers = settings.active_providers
    if not providers:
        log.warning("No OIDC providers configured — auth disabled")
        return
    for name, cfg in providers.items():
        discovery_url = cfg["discovery_url"].rstrip("/") + "/.well-known/openid-configuration"
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(discovery_url, timeout=10)
                resp.raise_for_status()
                _oidc_metadata[name] = resp.json()
                log.info("Loaded OIDC metadata for provider '%s'", name)
        except Exception as exc:
            log.warning(
                "Could not load OIDC metadata for provider '%s' from %s: %s — "
                "auth routes will return 503 until resolved",
                name,
                discovery_url,
                exc,
            )


# ---------------------------------------------------------------------------
# JWT helpers
# ---------------------------------------------------------------------------


def create_session_token(user_id: uuid.UUID, email: str, is_admin: bool) -> str:
    payload = {
        "sub": str(user_id),
        "email": email,
        "is_admin": is_admin,
        "exp": datetime.now(timezone.utc) + timedelta(days=7),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, settings.app_secret_key, algorithm=_ALGORITHM)


def decode_session_token(token: str) -> dict[str, Any] | None:
    try:
        return jwt.decode(token, settings.app_secret_key, algorithms=[_ALGORITHM])
    except JWTError:
        return None


# ---------------------------------------------------------------------------
# Provider list
# ---------------------------------------------------------------------------


@router.get("/providers")
async def list_providers() -> list[str]:
    """Return names of configured and reachable OIDC providers."""
    return list(_oidc_metadata.keys())


# ---------------------------------------------------------------------------
# OIDC login initiation
# ---------------------------------------------------------------------------


@router.get("/login")
async def login(
    provider: str = Query(default="google"),
    invite_token: str | None = Query(default=None),
) -> RedirectResponse:
    if provider not in _oidc_metadata:
        raise HTTPException(status_code=503, detail=f"Provider '{provider}' not configured")

    meta = _oidc_metadata[provider]
    cfg = settings.active_providers[provider]

    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    signed_state = _signer.dumps({"state": state, "nonce": nonce, "provider": provider})

    params: dict[str, str] = {
        "response_type": "code",
        "client_id": cfg["client_id"],
        "redirect_uri": cfg["redirect_uri"],
        "scope": "openid name email" if provider == "apple" else "openid email profile",
        "state": state,
        "nonce": nonce,
    }
    if provider == "apple":
        # Apple requires form_post so user name is delivered in the callback body
        params["response_mode"] = "form_post"

    url = meta["authorization_endpoint"] + "?" + "&".join(f"{k}={v}" for k, v in params.items())

    response = RedirectResponse(url=url, status_code=302)
    response.set_cookie(_STATE_COOKIE, signed_state, max_age=_STATE_MAX_AGE, httponly=True, samesite="lax")
    if invite_token:
        signed_invite = _signer.dumps(invite_token)
        response.set_cookie(_INVITE_COOKIE, signed_invite, max_age=_STATE_MAX_AGE, httponly=True, samesite="lax")
    return response


# ---------------------------------------------------------------------------
# OIDC callback
# GET  — standard query-param redirect (Google et al.)
# POST — Apple form_post (body contains code + state + optional user JSON)
# ---------------------------------------------------------------------------


@router.get("/callback")
async def callback_get(
    code: str = Query(),
    state: str = Query(),
    oidc_state: str | None = Cookie(default=None),
    oidc_invite: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    return await _handle_callback(code=code, state=state, oidc_state=oidc_state, oidc_invite=oidc_invite, db=db)


@router.post("/callback")
async def callback_post(
    code: str = Form(),
    state: str = Form(),
    user: str | None = Form(default=None),  # Apple sends user JSON on first login only
    oidc_state: str | None = Cookie(default=None),
    oidc_invite: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    apple_user_data: dict[str, Any] | None = None
    if user:
        try:
            apple_user_data = json.loads(user)
        except (json.JSONDecodeError, TypeError):
            pass
    return await _handle_callback(
        code=code,
        state=state,
        oidc_state=oidc_state,
        oidc_invite=oidc_invite,
        db=db,
        extra_user_data=apple_user_data,
    )


async def _handle_callback(
    code: str,
    state: str,
    oidc_state: str | None,
    oidc_invite: str | None,
    db: AsyncSession,
    extra_user_data: dict[str, Any] | None = None,
) -> RedirectResponse:
    if not oidc_state:
        raise HTTPException(status_code=400, detail="Missing OIDC state cookie")
    try:
        signed_data = _signer.loads(oidc_state, max_age=_STATE_MAX_AGE)
    except (SignatureExpired, BadSignature):
        raise HTTPException(status_code=400, detail="Invalid or expired OIDC state")
    if signed_data["state"] != state:
        raise HTTPException(status_code=400, detail="State mismatch")

    nonce = signed_data["nonce"]
    # Pre-migration sessions lack "provider" — default to google for backward compat
    provider = signed_data.get("provider", "google")

    if provider not in _oidc_metadata:
        raise HTTPException(status_code=503, detail=f"Provider '{provider}' metadata unavailable")
    meta = _oidc_metadata[provider]
    cfg = settings.active_providers[provider]

    invite_token: str | None = None
    if oidc_invite:
        try:
            invite_token = _signer.loads(oidc_invite, max_age=_STATE_MAX_AGE)
        except (SignatureExpired, BadSignature):
            invite_token = None

    # Exchange code for tokens
    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            meta["token_endpoint"],
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": cfg["redirect_uri"],
                "client_id": cfg["client_id"],
                "client_secret": cfg["client_secret"],
            },
        )
        token_resp.raise_for_status()
        token_data = token_resp.json()

    # Decode and verify ID token
    id_token = token_data["id_token"]
    async with httpx.AsyncClient() as client:
        jwks_resp = await client.get(meta["jwks_uri"])
        jwks_resp.raise_for_status()
        jwks_data = jwks_resp.json()

    try:
        header = jwt.get_unverified_header(id_token)
        jwk_set = PyJWKSet.from_dict(jwks_data)
        kid = header.get("kid")
        signing_key = next((k for k in jwk_set.keys if not kid or k.key_id == kid), None)
        if signing_key is None:
            raise HTTPException(status_code=400, detail="No matching JWKS key found")
        claims = jwt.decode(
            id_token,
            signing_key.key,
            algorithms=["RS256", "ES256"],
            audience=cfg["client_id"],
            options={"verify_at_hash": False},
        )
    except JWTError as exc:
        raise HTTPException(status_code=400, detail=f"ID token invalid: {exc}")

    if claims.get("nonce") != nonce:
        raise HTTPException(status_code=400, detail="Nonce mismatch")

    provider_sub = claims["sub"]
    email = claims.get("email", "")

    # Apple sends user name only on the first login (in the form body)
    if extra_user_data and (name_data := extra_user_data.get("name")):
        first = name_data.get("firstName", "")
        last = name_data.get("lastName", "")
        display_name = f"{first} {last}".strip() or email
    else:
        display_name = claims.get("name") or claims.get("preferred_username") or email

    # Identity resolution
    resolved = await _resolve_identity(db, provider, provider_sub, email)

    if resolved is not None:
        if resolved.is_deleted or not resolved.is_active:
            raise HTTPException(status_code=403, detail="Account suspended")
        db_user = resolved
    else:
        user_count = await db.scalar(select(func.count()).select_from(User))
        is_first_user = user_count == 0

        if not is_first_user:
            invite = await _consume_invite(db, email, invite_token)
            if invite is None:
                response = RedirectResponse(
                    url=f"{settings.frontend_url}/login?error=invite_required",
                    status_code=302,
                )
                _clear_oidc_cookies(response)
                return response

        db_user = User(
            email=email,
            display_name=display_name,
            oidc_sub=provider_sub,
            is_admin=is_first_user,
        )
        db.add(db_user)
        await db.flush()  # populate db_user.id before creating identity row

    await _ensure_identity(db, db_user.id, provider, provider_sub, email)
    await db.commit()
    await db.refresh(db_user)

    session_token = create_session_token(db_user.id, db_user.email, db_user.is_admin)
    response = RedirectResponse(url=settings.frontend_url, status_code=302)
    response.set_cookie(
        _SESSION_COOKIE,
        session_token,
        httponly=True,
        samesite="lax",
        max_age=60 * 60 * 24 * 7,
    )
    _clear_oidc_cookies(response)
    return response


async def _resolve_identity(db: AsyncSession, provider: str, provider_sub: str, email: str) -> User | None:
    """Resolve an OIDC (provider, sub) pair to a User via three fallback strategies."""
    # 1. Check user_identities table (primary path post-migration)
    identity = await db.scalar(
        select(UserIdentity).where(
            UserIdentity.provider == provider,
            UserIdentity.provider_sub == provider_sub,
        )
    )
    if identity:
        return await db.get(User, identity.user_id)

    # 2. Legacy fallback: users.oidc_sub (users that existed before 0015 migration)
    user = await db.scalar(select(User).where(User.oidc_sub == provider_sub, User.deleted_at.is_(None)))
    if user:
        return user

    # 3. Cross-provider email linking (same verified email at a second provider)
    if email:
        user = await db.scalar(select(User).where(User.email == email, User.deleted_at.is_(None)))
        if user:
            return user

    return None


async def _ensure_identity(db: AsyncSession, user_id: uuid.UUID, provider: str, provider_sub: str, email: str) -> None:
    """Insert a user_identities row if this (provider, sub) pair isn't already tracked."""
    existing = await db.scalar(
        select(UserIdentity).where(
            UserIdentity.provider == provider,
            UserIdentity.provider_sub == provider_sub,
        )
    )
    if not existing:
        db.add(
            UserIdentity(
                user_id=user_id,
                provider=provider,
                provider_sub=provider_sub,
                email=email or None,
            )
        )


async def _consume_invite(db: AsyncSession, email: str, token: str | None) -> Invite | None:
    if not token:
        return None
    invite = await db.scalar(select(Invite).where(Invite.token == token, Invite.email == email))
    if invite is None or not invite.is_valid:
        return None
    invite.accepted_at = datetime.now(timezone.utc)
    await db.commit()
    return invite


def _clear_oidc_cookies(response: RedirectResponse) -> None:
    response.delete_cookie(_STATE_COOKIE)
    response.delete_cookie(_INVITE_COOKIE)


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------


@router.post("/logout")
async def logout() -> JSONResponse:
    response = JSONResponse({"status": "logged_out"})
    response.delete_cookie(_SESSION_COOKIE)
    return response


# ---------------------------------------------------------------------------
# Current user
# ---------------------------------------------------------------------------


class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    display_name: str
    is_admin: bool
    theme: str
    activity_theme: str | None
    idle_timeout_minutes: int
    measurement_system: str
    ai_training_consent: bool
    eula_accepted_version: str | None
    current_eula_version: str

    model_config = {"from_attributes": True}


@router.get("/me", response_model=UserResponse)
async def me(current_user: User = Depends(get_current_user)) -> UserResponse:
    from app.routers.users import CURRENT_EULA_VERSION

    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        display_name=current_user.display_name,
        is_admin=current_user.is_admin,
        theme=current_user.theme,
        activity_theme=current_user.activity_theme,
        idle_timeout_minutes=current_user.idle_timeout_minutes,
        measurement_system=current_user.measurement_system,
        ai_training_consent=current_user.ai_training_consent,
        eula_accepted_version=current_user.eula_accepted_version,
        current_eula_version=CURRENT_EULA_VERSION,
    )


# ---------------------------------------------------------------------------
# Invite management (admin only)
# ---------------------------------------------------------------------------


class InviteRequest(BaseModel):
    email: EmailStr
    expires_days: int | None = None


class InviteResponse(BaseModel):
    id: uuid.UUID
    email: str
    expires_at: datetime
    accepted_at: datetime | None
    revoked_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


@router.post("/invite", response_model=InviteResponse, status_code=201)
async def create_invite(
    body: InviteRequest,
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> Invite:
    expires_days = body.expires_days or settings.invite_expiry_days_default
    token = secrets.token_urlsafe(32)
    invite = Invite(
        email=body.email,
        token=token,
        expires_at=datetime.now(timezone.utc) + timedelta(days=expires_days),
        created_by_id=admin.id,
    )
    db.add(invite)
    await db.commit()
    await db.refresh(invite)

    await send_invite_email(body.email, token, expires_days)
    return invite


@router.get("/invites", response_model=list[InviteResponse])
async def list_invites(
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> list[Invite]:
    result = await db.scalars(select(Invite).order_by(Invite.created_at.desc()))
    return list(result.all())


@router.delete("/invite/{invite_id}", status_code=204)
async def revoke_invite(
    invite_id: uuid.UUID,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> None:
    invite = await db.scalar(select(Invite).where(Invite.id == invite_id))
    if invite is None:
        raise HTTPException(status_code=404, detail="Invite not found")
    if invite.accepted_at is not None:
        raise HTTPException(status_code=400, detail="Invite already accepted")
    invite.revoked_at = datetime.now(timezone.utc)
    await db.commit()
