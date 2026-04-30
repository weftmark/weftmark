"""Audit log helpers."""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog
from app.models.user import User


async def write_audit_log(
    db: AsyncSession,
    *,
    event_type: str,
    actor: User | None = None,
    actor_id: uuid.UUID | None = None,
    actor_email: str | None = None,
    target: User | None = None,
    target_user_id: uuid.UUID | None = None,
    target_email: str | None = None,
    details: dict | None = None,
) -> None:
    """Insert an audit log entry and flush (does not commit — caller commits)."""
    resolved_actor_id = actor.id if actor else actor_id
    resolved_actor_email = actor.email if actor else actor_email
    resolved_target_id = target.id if target else target_user_id
    resolved_target_email = target.email if target else target_email

    entry = AuditLog(
        id=uuid.uuid4(),
        actor_id=resolved_actor_id,
        actor_email=resolved_actor_email,
        event_type=event_type,
        target_user_id=resolved_target_id,
        target_email=resolved_target_email,
        details=details,
    )
    db.add(entry)
    await db.flush()
