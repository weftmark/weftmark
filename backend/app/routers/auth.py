"""Authentication via Clerk.

Routes:
  POST /auth/clerk/webhook  — Clerk webhook: user.created / user.deleted
  POST /auth/logout         — no-op (Clerk manages sessions client-side)
  GET  /auth/me             — return current user profile

Invite management (admin only):
  POST   /auth/invite         — create invite + pre-create User record + send email
  GET    /auth/invites         — list all invites
  DELETE /auth/invite/{id}    — revoke invite + soft-delete pre-created User

User creation flow:
  1. Admin creates an invite (with role) for an email address.
  2. A User record is pre-created in the DB with clerk_user_id=None and the intended role.
  3. Invitee receives an email with the WeftMark sign-up URL.
  4. Invitee signs up via Clerk (Google, email, etc.).
  5. Clerk fires user.created webhook.
  6. Webhook finds the pre-created User by email (clerk_user_id IS NULL), attaches the
     Clerk ID, marks it active, and consumes the invite.
  7. If no pre-created User exists: creates a PendingSignup instead.

The seed CLI follows the same pattern: it pre-creates User records with the correct
roles before creating Clerk accounts, so the webhook just attaches.
"""

import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.deps import get_current_user, get_db, require_admin
from app.models.invite import Invite
from app.models.pending_signup import PendingSignup
from app.models.user import User
from app.services.audit import write_audit_log
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
        if event_type == "webhook.test":
            from app.services.clerk_webhook_probe import signal_probe

            signal_probe()
            log.debug("Webhook probe test event received and signalled")
        elif event_type == "user.created":
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

    # Find a pre-created User record (from an invite or the seed CLI).
    user = await db.scalar(
        select(User).where(User.email == email, User.clerk_user_id.is_(None), User.deleted_at.is_(None))
    )

    if user is None:
        # No pre-created record — treat as an unsolicited signup (pending review).
        log.warning(
            "Clerk user.created for %s (%s) — no pre-created User found; creating PendingSignup",
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

    # Attach the Clerk ID and update the display name from Clerk's data.
    user.clerk_user_id = clerk_user_id
    user.display_name = display_name
    await db.commit()

    # Consume the associated invite (audit trail; may already be consumed by seed CLI).
    await _consume_invite(db, email)

    await set_user_metadata(
        clerk_user_id,
        {"status": "active", "is_admin": user.is_admin, "is_superuser": user.is_superuser},
    )
    log.info("Attached Clerk user %s to pre-created User for %s", clerk_user_id, email)


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
    if user is None:
        return

    if user.deletion_state is not None:
        # Admin-initiated deletion already in progress — Celery task handles cleanup.
        log.info(
            "webhook_user_deleted clerk_user_id=%s deletion_state=%s — deletion already in progress",
            clerk_user_id,
            user.deletion_state,
        )
        return

    # Unexpected Clerk-side deletion (e.g. deleted via Clerk dashboard).
    # Null the clerk_user_id so the record is detached, and flag for admin review.
    user.clerk_errored = True
    user.is_active = False
    user.clerk_user_id = None
    await write_audit_log(db, event_type="user.clerk_errored", target_user_id=user.id, target_email=user.email)
    await db.commit()
    log.warning(
        "webhook_user_deleted_unexpected clerk_user_id=%s user_id=%s — flagged as clerk_errored",
        clerk_user_id,
        user.id,
    )


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
    role: str = "user"
    expires_days: int | None = None


class InviteResponse(BaseModel):
    id: uuid.UUID
    email: str
    role: str
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
    from app.models.invite import INVITE_ROLES

    if body.role not in INVITE_ROLES:
        raise HTTPException(status_code=422, detail=f"role must be one of: {', '.join(INVITE_ROLES)}")

    if body.role == "admin" and not admin.is_superuser:
        raise HTTPException(status_code=403, detail="Only superusers can invite admins")

    expires_days = body.expires_days or settings.invite_expiry_days_default

    # Block re-inviting an already-active user.
    active_user = await db.scalar(
        select(User).where(User.email == body.email, User.clerk_user_id.is_not(None), User.deleted_at.is_(None))
    )
    if active_user is not None:
        raise HTTPException(status_code=409, detail="A user with this email already exists")

    # Block inviting an email that has a pending self-signup — admin should approve it instead.
    pending_signup = await db.scalar(select(PendingSignup).where(PendingSignup.email == body.email))
    if pending_signup is not None:
        raise HTTPException(
            status_code=409,
            detail={
                "reason": "pending_signup_exists",
                "pending_signup_id": str(pending_signup.id),
                "message": "This email already has a pending signup request.",
            },
        )

    # Reuse an existing unclaimed User record (even if soft-deleted by a prior revoke) or create one.
    pre_user = await db.scalar(select(User).where(User.email == body.email, User.clerk_user_id.is_(None)))
    if pre_user is not None:
        pre_user.is_admin = body.role == "admin"
        pre_user.is_superuser = False
        pre_user.deleted_at = None
    else:
        pre_user = User(
            email=body.email,
            display_name=body.email,  # updated from Clerk data when the webhook fires
            is_admin=body.role == "admin",
            is_superuser=False,
            ai_training_consent=True,
        )
        db.add(pre_user)
    await db.flush()

    token = secrets.token_urlsafe(32)
    invite = Invite(
        email=body.email,
        token=token,
        role=body.role,
        expires_at=datetime.now(timezone.utc) + timedelta(days=expires_days),
        created_by_id=admin.id,
        user_id=pre_user.id,
    )
    db.add(invite)
    await write_audit_log(db, event_type="invite.created", actor=admin, target_email=body.email)
    await db.commit()
    await db.refresh(invite)

    raw_name = (admin.display_name or "").strip()
    first_name = raw_name.split()[0] if raw_name else ""
    admin_name = first_name or "A WeftMark admin"
    await send_invite_email(body.email, token, expires_days, admin_name=admin_name)
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
    admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> None:
    from datetime import datetime as _dt

    invite = await db.scalar(select(Invite).where(Invite.id == invite_id))
    if invite is None:
        raise HTTPException(status_code=404, detail="Invite not found")
    if invite.accepted_at is not None:
        raise HTTPException(status_code=400, detail="Invite already accepted")
    invite.revoked_at = _dt.now(timezone.utc)

    # Soft-delete the pre-created User if it hasn't been claimed yet.
    if invite.user_id is not None:
        pre_user = await db.get(User, invite.user_id)
        if pre_user is not None and pre_user.clerk_user_id is None:
            pre_user.deleted_at = _dt.now(timezone.utc)

    await write_audit_log(db, event_type="invite.revoked", actor=admin, target_email=invite.email)
    await db.commit()
