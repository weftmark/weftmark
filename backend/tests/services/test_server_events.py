"""Tests for app.services.server_events helpers."""

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.server_events import (
    ET_HEALTH_CHECK,
    ET_SHUTDOWN,
    ET_STARTUP,
    SEV_INFO,
    STATUS_CLOSED,
    STATUS_OPEN,
    close_event,
    close_open_events,
    get_open_event,
    write_event,
)


class TestWriteEvent:
    async def test_write_creates_row(self, db_session: AsyncSession):
        evt = await write_event(db_session, event_type=ET_STARTUP, severity=SEV_INFO)
        await db_session.commit()
        assert evt.id is not None

    async def test_write_defaults_to_open(self, db_session: AsyncSession):
        evt = await write_event(db_session, event_type=ET_STARTUP, severity=SEV_INFO)
        await db_session.commit()
        assert evt.status == STATUS_OPEN

    async def test_write_accepts_closed_status(self, db_session: AsyncSession):
        evt = await write_event(db_session, event_type=ET_STARTUP, severity=SEV_INFO, status=STATUS_CLOSED)
        await db_session.commit()
        assert evt.status == STATUS_CLOSED

    async def test_write_persists_message(self, db_session: AsyncSession):
        evt = await write_event(db_session, event_type=ET_HEALTH_CHECK, severity=SEV_INFO, message="Daily check")
        await db_session.commit()
        assert evt.message == "Daily check"

    async def test_write_persists_details(self, db_session: AsyncSession):
        evt = await write_event(
            db_session,
            event_type=ET_HEALTH_CHECK,
            severity=SEV_INFO,
            details={"probe_status": "ok"},
        )
        await db_session.commit()
        assert evt.details == {"probe_status": "ok"}

    async def test_write_sets_app_version(self, db_session: AsyncSession):
        evt = await write_event(db_session, event_type=ET_STARTUP, severity=SEV_INFO)
        await db_session.commit()
        assert evt.app_version  # non-empty string

    async def test_write_accepts_custom_started_at(self, db_session: AsyncSession):
        ts = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        evt = await write_event(db_session, event_type=ET_STARTUP, severity=SEV_INFO, started_at=ts)
        await db_session.commit()
        assert evt.started_at == ts


class TestCloseEvent:
    async def test_close_sets_ended_at(self, db_session: AsyncSession):
        evt = await write_event(db_session, event_type=ET_STARTUP, severity=SEV_INFO)
        await db_session.flush()
        await close_event(db_session, evt)
        await db_session.commit()
        assert evt.ended_at is not None

    async def test_close_sets_status_closed(self, db_session: AsyncSession):
        evt = await write_event(db_session, event_type=ET_STARTUP, severity=SEV_INFO)
        await db_session.flush()
        await close_event(db_session, evt)
        await db_session.commit()
        assert evt.status == STATUS_CLOSED

    async def test_close_computes_elapsed_ms(self, db_session: AsyncSession):
        evt = await write_event(db_session, event_type=ET_STARTUP, severity=SEV_INFO)
        await db_session.flush()
        await close_event(db_session, evt)
        await db_session.commit()
        assert evt.elapsed_ms is not None
        assert evt.elapsed_ms >= 0


class TestCloseOpenEvents:
    async def test_closes_all_open_events(self, db_session: AsyncSession):
        await write_event(db_session, event_type=ET_STARTUP, severity=SEV_INFO)
        await write_event(db_session, event_type=ET_HEALTH_CHECK, severity=SEV_INFO)
        await db_session.flush()

        closed_count = await close_open_events(db_session)
        await db_session.commit()
        assert closed_count == 2

    async def test_skips_already_closed_events(self, db_session: AsyncSession):
        await write_event(db_session, event_type=ET_STARTUP, severity=SEV_INFO, status=STATUS_CLOSED)
        await write_event(db_session, event_type=ET_HEALTH_CHECK, severity=SEV_INFO)
        await db_session.flush()

        closed_count = await close_open_events(db_session)
        await db_session.commit()
        assert closed_count == 1

    async def test_filter_by_event_type(self, db_session: AsyncSession):
        await write_event(db_session, event_type=ET_STARTUP, severity=SEV_INFO)
        await write_event(db_session, event_type=ET_HEALTH_CHECK, severity=SEV_INFO)
        await db_session.flush()

        closed_count = await close_open_events(db_session, event_types=[ET_STARTUP])
        await db_session.commit()
        assert closed_count == 1

    async def test_returns_zero_when_none_open(self, db_session: AsyncSession):
        closed_count = await close_open_events(db_session)
        assert closed_count == 0


class TestGetOpenEvent:
    async def test_returns_open_event(self, db_session: AsyncSession):
        evt = await write_event(db_session, event_type=ET_STARTUP, severity=SEV_INFO)
        await db_session.flush()

        found = await get_open_event(db_session, ET_STARTUP)
        assert found is not None
        assert found.id == evt.id

    async def test_returns_none_when_no_open_event(self, db_session: AsyncSession):
        await write_event(db_session, event_type=ET_STARTUP, severity=SEV_INFO, status=STATUS_CLOSED)
        await db_session.flush()

        found = await get_open_event(db_session, ET_STARTUP)
        assert found is None

    async def test_returns_none_for_different_type(self, db_session: AsyncSession):
        await write_event(db_session, event_type=ET_STARTUP, severity=SEV_INFO)
        await db_session.flush()

        found = await get_open_event(db_session, ET_SHUTDOWN)
        assert found is None
