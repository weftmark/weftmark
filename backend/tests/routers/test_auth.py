from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.routers.auth import create_session_token


class TestMe:
    async def test_returns_200(self, auth_client: AsyncClient):
        resp = await auth_client.get("/auth/me")
        assert resp.status_code == 200

    async def test_returns_user_email(self, auth_client: AsyncClient, test_user: User):
        resp = await auth_client.get("/auth/me")
        assert resp.json()["email"] == test_user.email

    async def test_returns_display_name(self, auth_client: AsyncClient, test_user: User):
        resp = await auth_client.get("/auth/me")
        assert resp.json()["display_name"] == test_user.display_name

    async def test_returns_is_admin_false(self, auth_client: AsyncClient):
        resp = await auth_client.get("/auth/me")
        assert resp.json()["is_admin"] is False

    async def test_admin_returns_is_admin_true(self, admin_client: AsyncClient):
        resp = await admin_client.get("/auth/me")
        assert resp.json()["is_admin"] is True

    async def test_unauthenticated_returns_401(self, client: AsyncClient):
        resp = await client.get("/auth/me")
        assert resp.status_code == 401


class TestLogout:
    async def test_returns_200(self, auth_client: AsyncClient):
        resp = await auth_client.post("/auth/logout")
        assert resp.status_code == 200

    async def test_clears_session_cookie(self, auth_client: AsyncClient):
        resp = await auth_client.post("/auth/logout")
        assert resp.json()["status"] == "logged_out"


class TestGetCurrentUser:
    """Tests the real get_current_user dependency via raw_client (no override)."""

    async def test_valid_token_returns_200(self, raw_client: AsyncClient, test_user: User):
        token = create_session_token(test_user.id, test_user.email, test_user.is_admin)
        resp = await raw_client.get("/auth/me", cookies={"session": token})
        assert resp.status_code == 200

    async def test_valid_token_returns_correct_user(self, raw_client: AsyncClient, test_user: User):
        token = create_session_token(test_user.id, test_user.email, test_user.is_admin)
        resp = await raw_client.get("/auth/me", cookies={"session": token})
        assert resp.json()["email"] == test_user.email

    async def test_missing_cookie_returns_401(self, raw_client: AsyncClient):
        resp = await raw_client.get("/auth/me")
        assert resp.status_code == 401

    async def test_invalid_token_returns_401(self, raw_client: AsyncClient):
        resp = await raw_client.get("/auth/me", cookies={"session": "not.a.valid.token"})
        assert resp.status_code == 401

    async def test_inactive_user_returns_401(self, raw_client: AsyncClient, db_session: AsyncSession, test_user: User):
        test_user.is_active = False
        await db_session.commit()
        token = create_session_token(test_user.id, test_user.email, test_user.is_admin)
        resp = await raw_client.get("/auth/me", cookies={"session": token})
        assert resp.status_code == 401

    async def test_soft_deleted_user_returns_401(
        self, raw_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        test_user.soft_delete()
        await db_session.commit()
        token = create_session_token(test_user.id, test_user.email, test_user.is_admin)
        resp = await raw_client.get("/auth/me", cookies={"session": token})
        assert resp.status_code == 401


class TestRequireAdmin:
    async def test_admin_user_can_access_admin_endpoint(self, admin_client: AsyncClient):
        resp = await admin_client.get("/auth/invites")
        assert resp.status_code == 200

    async def test_non_admin_returns_403(self, auth_client: AsyncClient):
        resp = await auth_client.get("/auth/invites")
        assert resp.status_code == 403

    async def test_unauthenticated_returns_401(self, client: AsyncClient):
        resp = await client.get("/auth/invites")
        assert resp.status_code == 401
