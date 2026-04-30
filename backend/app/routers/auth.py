"""Authentication via Clerk.

Routes:
  POST /auth/clerk/webhook  — Clerk webhook: user.created / user.deleted
  POST /auth/logout         — no-op (Clerk manages sessions client-side)
  GET  /auth/me             — return current user profile

Invite management (admin only):
  POST   /auth/invite         — create invite + send email
  GET    /auth/invites         — list all invites
  DELETE /auth/invite/{id}    — revoke invite

User creation flow:
  1. Admin creates an invite for an email address.
  2. Invitee receives an email with the WeftMark sign-up URL.
  3. Invitee signs up via Clerk (Google, email, etc.).
  4. Clerk fires user.created webhook.
  5. Webhook checks for a valid invite (or first-user bootstrap).
  6. If valid: creates User record in our DB, consumes invite.
  7. If invalid: no DB record created — user gets 401 from all API routes.
"""

import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.deps import get_current_user, get_db, require_admin
from app.models.invite import Invite
from app.models.pending_signup import PendingSignup
from app.models.user import User
from app.services.clerk import set_user_metadata
from app.services.email import send_invite_email, send_pending_signup_notification, send_signup_received_email

log = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()


# ---------------------------------------------------------------------------
# Clerk webhook
# ---------------------------------------------------------------------------


@router.post("/clerk/webhook", status_code=200)
async def clerk_webhook(request: Request, db: AsyncSession = Depends(get_db)) -> dict:
    """Receive and process Clerk user lifecycle events."""
    from svix.webhooks import Webhook, WebhookVerificationError

    payload = await request.body()
    headers = dict(request.headers)

    if not settings.clerk_webhook_secret:
        log.error("CLERK_WEBHOOK_SECRET not configured — rejecting webhook")
        raise HTTPException(status_code=500, detail="Webhook not configured")

    try:
        wh = Webhook(settings.clerk_webhook_secret)
        event = wh.verify(payload, headers)
    except WebhookVerificationError:
        log.info("webhook_rejected reason=invalid_signature")
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    event_type = event.get("type")
    data = event.get("data", {})
    clerk_user_id = data.get("id", "unknown")

    log.info("webhook_received event_type=%s clerk_user_id=%s", event_type, clerk_user_id)

    try:
        if event_type == "user.created":
            await _handle_user_created(db, data)
        elif event_type == "user.updated":
            await _handle_user_updated(db, data)
        elif event_type == "user.deleted":
            await _handle_user_deleted(db, data)
        else:
            log.info("webhook_ignored event_type=%s", event_type)
    except Exception:
        log.exception("webhook_processing_failed event_type=%s clerk_user_id=%s", event_type, clerk_user_id)
        raise

    log.info("webhook_processed event_type=%s clerk_user_id=%s", event_type, clerk_user_id)
    return {"status": "ok"}


async def _handle_user_created(db: AsyncSession, data: dict) -> None:
    clerk_user_id: str = data["id"]
    email_addresses: list[dict] = data.get("email_addresses", [])
    primary_id: str | None = data.get("primary_email_address_id")

    primary = next(
        (e for e in email_addresses if e["id"] == primary_id),
        email_addresses[0] if email_addresses else None,
    )
    email = primary["email_address"] if primary else ""

    first_name = (data.get("first_name") or "").strip()
    last_name = (data.get("last_name") or "").strip()
    display_name = f"{first_name} {last_name}".strip() or email

    user_count = await db.scalar(select(func.count()).select_from(User))
    is_first_user = user_count == 0

    if not is_first_user:
        invite = await _consume_invite(db, email)
        if invite is None:
            log.warning(
                "Clerk user.created for %s (%s) — no valid invite found; skipping DB record",
                clerk_user_id,
                email,
            )
            existing = await db.scalar(select(PendingSignup).where(PendingSignup.clerk_user_id == clerk_user_id))
            if existing is None:
                db.add(PendingSignup(clerk_user_id=clerk_user_id, email=email, display_name=display_name))
                await db.commit()
                await set_user_metadata(clerk_user_id, {"status": "pending_signup", "is_admin": False})
                admin_emails = list(
                    await db.scalars(select(User.email).where(User.is_admin.is_(True), User.deleted_at.is_(None)))
                )
                try:
                    await send_signup_received_email(email, display_name)
                except Exception:
                    log.exception("Failed to send signup received email to %s", email)
                if admin_emails:
                    try:
                        await send_pending_signup_notification(admin_emails, display_name, email)
                    except Exception:
                        log.exception("Failed to send pending signup notification to admins")
            return

    user = User(
        email=email,
        display_name=display_name,
        clerk_user_id=clerk_user_id,
        is_admin=is_first_user,
        is_superuser=is_first_user,
        ai_training_consent=True,
    )
    db.add(user)
    await db.commit()
    await set_user_metadata(
        clerk_user_id, {"status": "active", "is_admin": is_first_user, "is_superuser": is_first_user}
    )
    log.info("Created User record for Clerk user %s (%s)", clerk_user_id, email)


async def _handle_user_updated(db: AsyncSession, data: dict) -> None:
    clerk_user_id: str = data["id"]
    user = await db.scalar(select(User).where(User.clerk_user_id == clerk_user_id, User.deleted_at.is_(None)))
    if user is None:
        return

    email_addresses: list[dict] = data.get("email_addresses", [])
    primary_id: str | None = data.get("primary_email_address_id")
    primary = next(
        (e for e in email_addresses if e["id"] == primary_id),
        email_addresses[0] if email_addresses else None,
    )
    if primary:
        user.email = primary["email_address"]

    first_name = (data.get("first_name") or "").strip()
    last_name = (data.get("last_name") or "").strip()
    display_name = f"{first_name} {last_name}".strip()
    if display_name:
        user.display_name = display_name

    await db.commit()
    log.info("Updated User record for Clerk user %s", clerk_user_id)


async def _handle_user_deleted(db: AsyncSession, data: dict) -> None:
    clerk_user_id: str = data["id"]
    user = await db.scalar(select(User).where(User.clerk_user_id == clerk_user_id, User.deleted_at.is_(None)))
    if user:
        user.soft_delete()
        await db.commit()
        log.info("Soft-deleted User record for Clerk user %s", clerk_user_id)


async def _consume_invite(db: AsyncSession, email: str) -> Invite | None:
    invite = await db.scalar(
        select(Invite).where(
            Invite.email == email,
            Invite.accepted_at.is_(None),
            Invite.revoked_at.is_(None),
            Invite.expires_at > datetime.now(timezone.utc),
        )
    )
    if invite is None:
        return None
    invite.accepted_at = datetime.now(timezone.utc)
    await db.commit()
    return invite


# ---------------------------------------------------------------------------
# Logout
# ---------------------------------------------------------------------------


@router.post("/logout")
async def logout() -> JSONResponse:
    """No-op — Clerk manages sessions client-side via signOut()."""
    return JSONResponse({"status": "logged_out"})


# ---------------------------------------------------------------------------
# Current user
# ---------------------------------------------------------------------------


class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    display_name: str
    is_admin: bool
    is_superuser: bool
    theme: str
    activity_theme: str | None
    idle_timeout_minutes: int
    measurement_system: str
    ai_training_consent: bool
    eula_accepted_version: str | None
    current_eula_version: str
    storage_used_bytes: int
    storage_quota_bytes: int

    model_config = {"from_attributes": True}


@router.get("/me", response_model=UserResponse)
async def me(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> UserResponse:
    from app.routers.users import get_current_eula_version
    from app.services.storage_quota import MAX_USER_STORAGE_BYTES, get_user_storage_used

    current_eula_version = await get_current_eula_version(db)
    storage_used = await get_user_storage_used(current_user.id, db)
    return UserResponse(
        id=current_user.id,
        email=current_user.email,
        display_name=current_user.display_name,
        is_admin=current_user.is_admin,
        is_superuser=current_user.is_superuser,
        theme=current_user.theme,
        activity_theme=current_user.activity_theme,
        idle_timeout_minutes=current_user.idle_timeout_minutes,
        measurement_system=current_user.measurement_system,
        ai_training_consent=current_user.ai_training_consent,
        eula_accepted_version=current_user.eula_accepted_version,
        current_eula_version=current_eula_version,
        storage_used_bytes=storage_used,
        storage_quota_bytes=MAX_USER_STORAGE_BYTES,
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
    result = await db.scalars(select(Invite).order_by(Invite.created_at.desc()).limit(50))
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
