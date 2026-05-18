"""Tests for GET /api/system/status."""

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


class TestSystemStatus:
    async def test_returns_200(self, client: AsyncClient):
        resp = await client.get("/api/system/status")
        assert resp.status_code == 200

    async def test_not_initialized_when_no_superuser(self, client: AsyncClient):
        resp = await client.get("/api/system/status")
        assert resp.json() == {"initialized": False}

    async def test_not_initialized_when_only_admin(self, client: AsyncClient, db_session: AsyncSession):
        db_session.add(User(email="admin@example.com", display_name="Admin", is_admin=True, is_superuser=False))
        await db_session.commit()

        resp = await client.get("/api/system/status")
        assert resp.json() == {"initialized": False}

    async def test_initialized_when_superuser_exists(self, client: AsyncClient, db_session: AsyncSession):
        db_session.add(User(email="su@example.com", display_name="Super", is_admin=True, is_superuser=True))
        await db_session.commit()

        resp = await client.get("/api/system/status")
        assert resp.json() == {"initialized": True}

    async def test_no_auth_required(self, client: AsyncClient):
        resp = await client.get("/api/system/status")
        assert resp.status_code != 401
        assert resp.status_code != 403
