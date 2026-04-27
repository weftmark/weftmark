import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.invite import Invite
from app.models.user import User


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

    async def test_returns_is_superuser_false(self, auth_client: AsyncClient):
        resp = await auth_client.get("/auth/me")
        assert resp.json()["is_superuser"] is False

    async def test_superuser_returns_is_superuser_true(self, superuser_client: AsyncClient):
        resp = await superuser_client.get("/auth/me")
        assert resp.json()["is_superuser"] is True


class TestLogout:
    async def test_returns_200(self, auth_client: AsyncClient):
        resp = await auth_client.post("/auth/logout")
        assert resp.status_code == 200

    async def test_clears_session_cookie(self, auth_client: AsyncClient):
        resp = await auth_client.post("/auth/logout")
        assert resp.json()["status"] == "logged_out"


class TestGetCurrentUser:
    """Tests the real get_current_user dependency via raw_client (no override).

    With Clerk JWT auth, get_current_user requires a valid Bearer token.
    Without one it returns 401.

    verify_session_token is patched to return None (failed verification) so
    tests don't depend on a real Clerk publishable key or network access.
    """

    @pytest.fixture(autouse=True)
    def _mock_clerk(self, monkeypatch):
        from app.config import get_settings

        monkeypatch.setattr(get_settings(), "clerk_publishable_key", "pk_test_dGVzdA")
        with patch("app.deps.verify_session_token", return_value=None):
            yield

    async def test_missing_auth_header_returns_401(self, raw_client: AsyncClient):
        resp = await raw_client.get("/auth/me")
        assert resp.status_code == 401

    async def test_invalid_bearer_token_returns_401(self, raw_client: AsyncClient):
        resp = await raw_client.get("/auth/me", headers={"Authorization": "Bearer invalid.token.here"})
        assert resp.status_code == 401

    async def test_non_bearer_auth_returns_401(self, raw_client: AsyncClient):
        resp = await raw_client.get("/auth/me", headers={"Authorization": "Basic dXNlcjpwYXNz"})
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


# ---------------------------------------------------------------------------
# POST /auth/invite  (admin only)
# ---------------------------------------------------------------------------


class TestCreateInvite:
    @pytest.fixture(autouse=True)
    def mock_email(self):
        with patch("app.routers.auth.send_invite_email", new_callable=AsyncMock) as m:
            yield m

    async def test_returns_201(self, admin_client: AsyncClient):
        resp = await admin_client.post("/auth/invite", json={"email": "new@example.com"})
        assert resp.status_code == 201

    async def test_returns_invite_fields(self, admin_client: AsyncClient):
        resp = await admin_client.post("/auth/invite", json={"email": "new@example.com"})
        data = resp.json()
        assert data["email"] == "new@example.com"
        assert "id" in data
        assert "token" not in data  # token not exposed in response
        assert data["accepted_at"] is None
        assert data["revoked_at"] is None

    async def test_persists_to_db(self, admin_client: AsyncClient, db_session: AsyncSession):
        resp = await admin_client.post("/auth/invite", json={"email": "stored@example.com"})
        invite_id = uuid.UUID(resp.json()["id"])
        invite = await db_session.scalar(select(Invite).where(Invite.id == invite_id))
        assert invite is not None
        assert invite.email == "stored@example.com"

    async def test_sends_invite_email(self, admin_client: AsyncClient, mock_email: AsyncMock):
        await admin_client.post("/auth/invite", json={"email": "emailed@example.com"})
        mock_email.assert_called_once()
        call_args = mock_email.call_args[0]
        assert call_args[0] == "emailed@example.com"

    async def test_custom_expiry_days(self, admin_client: AsyncClient, db_session: AsyncSession):
        resp = await admin_client.post("/auth/invite", json={"email": "exp@example.com", "expires_days": 30})
        invite_id = uuid.UUID(resp.json()["id"])
        invite = await db_session.scalar(select(Invite).where(Invite.id == invite_id))
        delta = invite.expires_at - datetime.now(timezone.utc)
        assert 29 * 86400 < delta.total_seconds() <= 30 * 86400

    async def test_non_admin_returns_403(self, auth_client: AsyncClient):
        resp = await auth_client.post("/auth/invite", json={"email": "blocked@example.com"})
        assert resp.status_code == 403

    async def test_unauthenticated_returns_401(self, client: AsyncClient):
        resp = await client.post("/auth/invite", json={"email": "anon@example.com"})
        assert resp.status_code == 401

    async def test_invalid_email_returns_422(self, admin_client: AsyncClient):
        resp = await admin_client.post("/auth/invite", json={"email": "not-an-email"})
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /auth/invites  (admin only)
# ---------------------------------------------------------------------------


class TestListInvites:
    @pytest.fixture(autouse=True)
    def mock_email(self):
        with patch("app.routers.auth.send_invite_email", new_callable=AsyncMock):
            yield

    async def test_returns_200(self, admin_client: AsyncClient):
        resp = await admin_client.get("/auth/invites")
        assert resp.status_code == 200

    async def test_empty_list_when_no_invites(self, admin_client: AsyncClient):
        resp = await admin_client.get("/auth/invites")
        assert resp.json() == []

    async def test_returns_created_invites(self, admin_client: AsyncClient):
        await admin_client.post("/auth/invite", json={"email": "a@example.com"})
        await admin_client.post("/auth/invite", json={"email": "b@example.com"})
        resp = await admin_client.get("/auth/invites")
        assert len(resp.json()) == 2

    async def test_non_admin_returns_403(self, auth_client: AsyncClient):
        resp = await auth_client.get("/auth/invites")
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# DELETE /auth/invite/{invite_id}  (admin only)
# ---------------------------------------------------------------------------


class TestRevokeInvite:
    async def _create_invite_db(
        self, db_session: AsyncSession, admin_user: User, email: str = "revoke@example.com"
    ) -> Invite:
        invite = Invite(
            email=email,
            token="tok-" + email,
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
            created_by_id=admin_user.id,
        )
        db_session.add(invite)
        await db_session.commit()
        await db_session.refresh(invite)
        return invite

    async def test_returns_204(self, admin_client: AsyncClient, db_session: AsyncSession, admin_user: User):
        invite = await self._create_invite_db(db_session, admin_user)
        resp = await admin_client.delete(f"/auth/invite/{invite.id}")
        assert resp.status_code == 204

    async def test_sets_revoked_at(self, admin_client: AsyncClient, db_session: AsyncSession, admin_user: User):
        invite = await self._create_invite_db(db_session, admin_user)
        await admin_client.delete(f"/auth/invite/{invite.id}")
        await db_session.refresh(invite)
        assert invite.revoked_at is not None

    async def test_nonexistent_returns_404(self, admin_client: AsyncClient):
        resp = await admin_client.delete(f"/auth/invite/{uuid.uuid4()}")
        assert resp.status_code == 404

    async def test_already_accepted_returns_400(
        self, admin_client: AsyncClient, db_session: AsyncSession, admin_user: User
    ):
        invite = await self._create_invite_db(db_session, admin_user, email="accepted@example.com")
        invite.accepted_at = datetime.now(timezone.utc)
        await db_session.commit()
        resp = await admin_client.delete(f"/auth/invite/{invite.id}")
        assert resp.status_code == 400

    async def test_non_admin_returns_403(self, auth_client: AsyncClient, db_session: AsyncSession, admin_user: User):
        invite = await self._create_invite_db(db_session, admin_user)
        resp = await auth_client.delete(f"/auth/invite/{invite.id}")
        assert resp.status_code == 403

    async def test_unauthenticated_returns_401(self, client: AsyncClient, db_session: AsyncSession, admin_user: User):
        invite = await self._create_invite_db(db_session, admin_user)
        resp = await client.delete(f"/auth/invite/{invite.id}")
        assert resp.status_code == 401
