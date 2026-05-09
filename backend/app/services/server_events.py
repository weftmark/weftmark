"""Helpers for writing and closing ServerEvent rows."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.server_event import ServerEvent
from app.version import VERSION

# ── event_type constants ──────────────────────────────────────────────────────
ET_STARTUP = "stack.startup"
ET_SHUTDOWN = "stack.shutdown"
ET_HEALTH_DEGRADED = "health.degraded"
ET_HEALTH_ERROR = "health.error"
ET_HEALTH_CHECK = "health.check"

# ── severity constants ────────────────────────────────────────────────────────
SEV_INFO = "info"
SEV_WARN = "warn"
SEV_ERROR = "error"

# ── status constants ──────────────────────────────────────────────────────────
STATUS_OPEN = "open"
STATUS_CLOSED = "closed"


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def write_event(
    db: AsyncSession,
    event_type: str,
    severity: str,
    status: str = STATUS_OPEN,
    message: str | None = None,
    details: dict | None = None,
    started_at: datetime | None = None,
) -> ServerEvent:
    evt = ServerEvent(
        event_type=event_type,
        severity=severity,
        status=status,
        started_at=started_at or _now(),
        app_version=VERSION,
        message=message,
        details=details,
    )
    db.add(evt)
    await db.flush()
    return evt


async def close_event(db: AsyncSession, event: ServerEvent) -> None:
    now = _now()
    event.ended_at = now
    elapsed = now - event.started_at
    event.elapsed_ms = int(elapsed.total_seconds() * 1000)
    event.status = STATUS_CLOSED
    await db.flush()


async def close_open_events(db: AsyncSession, event_types: list[str] | None = None) -> int:
    """Close any open events matching the given types (all open types if None).

    Returns the number of events closed. Called at startup to clean up
    events left open by an unclean shutdown.
    """
    stmt = select(ServerEvent).where(ServerEvent.status == STATUS_OPEN)
    if event_types:
        stmt = stmt.where(ServerEvent.event_type.in_(event_types))
    result = await db.execute(stmt)
    events = result.scalars().all()
    for evt in events:
        await close_event(db, evt)
    return len(events)


async def get_open_event(db: AsyncSession, event_type: str) -> ServerEvent | None:
    """Return the most recent open event of the given type, or None."""
    stmt = (
        select(ServerEvent)
        .where(ServerEvent.event_type == event_type, ServerEvent.status == STATUS_OPEN)
        .order_by(ServerEvent.started_at.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()
