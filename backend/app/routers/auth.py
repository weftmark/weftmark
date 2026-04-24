"""
OIDC authentication flow:

  /auth/login        → redirect to provider authorization endpoint
  /auth/callback     → exchange code, upsert user, set session cookie, redirect to frontend
  /auth/logout       → clear session cookie
  /auth/me           → return current user info

Invite flow:
  /auth/invite       POST   (admin) create invite + send email
  /auth/invites      GET    (admin) list invites
  /auth/invite/{id}  DELETE (admin) revoke invite
  /register?token=X  handled by frontend → redirects to /auth/login?invite_token=X

Bootstrap rule: if zero users exist, the first OIDC registrant is granted admin with no invite.
"""

import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
import jwt
from fastapi import APIRouter, Cookie, Depends, HTTPException, Query
from fastapi.responses import JSONResponse, RedirectResponse
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from jwt.exceptions import PyJWTError as JWTError
from pydantic import BaseModel, EmailStr
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.deps import get_current_user, get_db, require_admin
from app.models.invite import Invite
from app.models.user import User
from app.services.email import send_invite_email

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()

_ALGORITHM = "HS256"
_SESSION_COOKIE = "session"
_STATE_COOKIE = "oidc_state"
_INVITE_COOKIE = "oidc_invite"
_STATE_MAX_AGE = 600  # 10 minutes

_signer = URLSafeTimedSerializer(settings.app_secret_key)

# OIDC provider metadata — populated on startup via load_oidc_metadata()
_oidc_metadata: dict[str, Any] = {}


async def load_oidc_metadata() -> None:
    if not settings.oidc_discovery_url:
        import logging

        logging.getLogger(__name__).warning("OIDC_DISCOVERY_URL not set — auth disabled")
        return
    discovery_url = settings.oidc_discovery_url.rstrip("/") + "/.well-known/openid-configuration"
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(discovery_url, timeout=10)
            resp.raise_for_status()
            _oidc_metadata.update(resp.json())
    except Exception as exc:
        import logging

        logging.getLogger(__name__).warning(
            "Could not load OIDC metadata from %s: %s — auth routes will return 503 until resolved",
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
# OIDC login initiation
# ---------------------------------------------------------------------------


@router.get("/login")
async def login(invite_token: str | None = Query(default=None)) -> RedirectResponse:
    if not _oidc_metadata:
        raise HTTPException(status_code=503, detail="OIDC provider not configured")

    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    signed_state = _signer.dumps({"state": state, "nonce": nonce})

    authorization_endpoint = _oidc_metadata["authorization_endpoint"]
    if settings.oidc_public_base_url:
        from urllib.parse import urlparse, urlunparse

        parsed = urlparse(authorization_endpoint)
        public = urlparse(settings.oidc_public_base_url)
        authorization_endpoint = urlunparse(parsed._replace(scheme=public.scheme, netloc=public.netloc))

    params = {
        "response_type": "code",
        "client_id": settings.oidc_client_id,
        "redirect_uri": settings.oidc_redirect_uri,
        "scope": "openid email profile",
        "state": state,
        "nonce": nonce,
    }
    url = authorization_endpoint + "?" + "&".join(f"{k}={v}" for k, v in params.items())

    response = RedirectResponse(url=url, status_code=302)
    response.set_cookie(_STATE_COOKIE, signed_state, max_age=_STATE_MAX_AGE, httponly=True, samesite="lax")
    if invite_token:
        signed_invite = _signer.dumps(invite_token)
        response.set_cookie(_INVITE_COOKIE, signed_invite, max_age=_STATE_MAX_AGE, httponly=True, samesite="lax")
    return response


# ---------------------------------------------------------------------------
# OIDC callback
# ---------------------------------------------------------------------------


@router.get("/callback")
async def callback(
    code: str = Query(),
    state: str = Query(),
    oidc_state: str | None = Cookie(default=None),
    oidc_invite: str | None = Cookie(default=None),
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    # Validate state
    if not oidc_state:
        raise HTTPException(status_code=400, detail="Missing OIDC state cookie")
    try:
        signed_data = _signer.loads(oidc_state, max_age=_STATE_MAX_AGE)
    except (SignatureExpired, BadSignature):
        raise HTTPException(status_code=400, detail="Invalid or expired OIDC state")
    if signed_data["state"] != state:
        raise HTTPException(status_code=400, detail="State mismatch")
    nonce = signed_data["nonce"]

    # Parse invite token if present
    invite_token: str | None = None
    if oidc_invite:
        try:
            invite_token = _signer.loads(oidc_invite, max_age=_STATE_MAX_AGE)
        except (SignatureExpired, BadSignature):
            invite_token = None

    # Exchange code for tokens
    async with httpx.AsyncClient() as client:
        token_resp = await client.post(
            _oidc_metadata["token_endpoint"],
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": settings.oidc_redirect_uri,
                "client_id": settings.oidc_client_id,
                "client_secret": settings.oidc_client_secret,
            },
        )
        token_resp.raise_for_status()
        token_data = token_resp.json()

    # Decode and verify ID token
    id_token = token_data["id_token"]
    jwks_uri = _oidc_metadata["jwks_uri"]
    async with httpx.AsyncClient() as client:
        jwks_resp = await client.get(jwks_uri)
        jwks = jwks_resp.json()

    try:
        claims = jwt.decode(
            id_token,
            jwks,
            algorithms=["RS256", "ES256"],
            audience=settings.oidc_client_id,
            options={"verify_at_hash": False},
        )
    except JWTError as exc:
        raise HTTPException(status_code=400, detail=f"ID token invalid: {exc}")

    if claims.get("nonce") != nonce:
        raise HTTPException(status_code=400, detail="Nonce mismatch")

    oidc_sub = claims["sub"]
    email = claims.get("email", "")
    display_name = claims.get("name") or claims.get("preferred_username") or email

    # Check for existing user
    existing = await db.scalar(select(User).where(User.oidc_sub == oidc_sub))

    if existing:
        if existing.is_deleted or not existing.is_active:
            raise HTTPException(status_code=403, detail="Account suspended")
        user = existing
    else:
        # New user — require invite unless this is the first user (bootstrap)
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

        user = User(
            email=email,
            display_name=display_name,
            oidc_sub=oidc_sub,
            is_admin=is_first_user,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)

    session_token = create_session_token(user.id, user.email, user.is_admin)
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
    idle_timeout_minutes: int

    model_config = {"from_attributes": True}


@router.get("/me", response_model=UserResponse)
async def me(current_user: User = Depends(get_current_user)) -> User:
    return current_user


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
