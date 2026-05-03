"""Tests for GET /dev/status."""

from datetime import datetime, timezone

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.seed_run import SeedRun


class TestDevStatus:
    async def test_returns_200(self, client: AsyncClient):
        resp = await client.get("/dev/status")
        assert resp.status_code == 200

    async def test_last_seed_is_null_when_no_run(self, client: AsyncClient):
        resp = await client.get("/dev/status")
        assert resp.json()["last_seed"] is None

    async def test_last_seed_returned_after_seed_run(self, client: AsyncClient, db_session: AsyncSession):
        ran_at = datetime(2026, 5, 1, 12, 0, 0, tzinfo=timezone.utc)
        db_session.add(SeedRun(id=1, ran_at=ran_at))
        await db_session.commit()

        resp = await client.get("/dev/status")
        assert resp.status_code == 200
        assert resp.json()["last_seed"] == ran_at.isoformat()

    async def test_last_seed_updates_on_reseed(self, client: AsyncClient, db_session: AsyncSession):
        first = datetime(2026, 4, 1, 0, 0, 0, tzinfo=timezone.utc)
        second = datetime(2026, 5, 1, 0, 0, 0, tzinfo=timezone.utc)

        db_session.add(SeedRun(id=1, ran_at=first))
        await db_session.commit()

        await db_session.merge(SeedRun(id=1, ran_at=second))
        await db_session.commit()

        resp = await client.get("/dev/status")
        assert resp.json()["last_seed"] == second.isoformat()
