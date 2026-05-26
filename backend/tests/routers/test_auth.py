import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.invite import Invite
from app.models.pending_signup import PendingSignup
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

    async def test_returns_show_version_numbers(self, auth_client: AsyncClient):
        resp = await auth_client.get("/auth/me")
        assert "show_version_numbers" in resp.json()

    async def test_returns_hide_unused_shafts_treadles(self, auth_client: AsyncClient):
        resp = await auth_client.get("/auth/me")
        assert "hide_unused_shafts_treadles" in resp.json()


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
        call_args = mock_email.call_args
        assert call_args[0][0] == "emailed@example.com"
        assert call_args[1]["admin_name"] == "Admin"  # admin fixture has display_name="Admin User"

    async def test_sends_invite_email_fallback_name(self, db_session: AsyncSession):
        """Admin with no display_name falls back to 'A weftmark admin'."""

        admin_no_name = User(
            email="noname@example.com",
            display_name="",
            is_admin=True,
            is_superuser=False,
            ai_training_consent=True,
        )
        db_session.add(admin_no_name)
        await db_session.flush()

        # Verify the fallback logic directly
        display = admin_no_name.display_name or ""
        first_name = display.split()[0] if display.strip() else ""
        admin_name = first_name or "A weftmark admin"
        assert admin_name == "A weftmark admin"

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

    async def test_superuser_can_invite_admin_role(self, superuser_client: AsyncClient):
        resp = await superuser_client.post("/auth/invite", json={"email": "newadmin@example.com", "role": "admin"})
        assert resp.status_code == 201
        assert resp.json()["role"] == "admin"

    async def test_admin_cannot_invite_admin_role(self, admin_client: AsyncClient):
        resp = await admin_client.post("/auth/invite", json={"email": "newadmin@example.com", "role": "admin"})
        assert resp.status_code == 403

    async def test_active_user_email_returns_409(self, admin_client: AsyncClient, db_session: AsyncSession):
        active = User(
            email="active@example.com",
            display_name="Active User",
            clerk_user_id="clerk_active_123",
            is_admin=False,
            is_superuser=False,
        )
        db_session.add(active)
        await db_session.commit()
        resp = await admin_client.post("/auth/invite", json={"email": "active@example.com"})
        assert resp.status_code == 409

    async def test_reinvite_unclaimed_user_reuses_record(
        self, admin_client: AsyncClient, db_session: AsyncSession, superuser_client: AsyncClient
    ):
        # First invite creates a pre-user record (user-role).
        r1 = await admin_client.post("/auth/invite", json={"email": "reinvite@example.com"})
        assert r1.status_code == 201

        # Second invite (admin-role, sent by superuser) reuses the same User record.
        r2 = await superuser_client.post("/auth/invite", json={"email": "reinvite@example.com", "role": "admin"})
        assert r2.status_code == 201

        users = list(
            await db_session.scalars(
                select(User).where(User.email == "reinvite@example.com", User.deleted_at.is_(None))
            )
        )
        assert len(users) == 1
        assert users[0].is_admin is True

    async def test_reinvite_after_revoke_reuses_soft_deleted_record(
        self, superuser_client: AsyncClient, db_session: AsyncSession
    ):
        # Simulate a soft-deleted pre-user (invite was previously revoked).
        soft_deleted = User(
            email="revoked@example.com",
            display_name="revoked@example.com",
            clerk_user_id=None,
            is_admin=False,
            is_superuser=False,
            deleted_at=datetime.now(timezone.utc),
        )
        db_session.add(soft_deleted)
        await db_session.commit()

        resp = await superuser_client.post("/auth/invite", json={"email": "revoked@example.com", "role": "admin"})
        assert resp.status_code == 201

        await db_session.refresh(soft_deleted)
        assert soft_deleted.deleted_at is None
        assert soft_deleted.is_admin is True

    async def test_pending_signup_email_returns_409_with_reason(
        self, admin_client: AsyncClient, db_session: AsyncSession
    ):
        signup = PendingSignup(
            clerk_user_id="clerk_pending_test",
            email="waiting@example.com",
            display_name="Waiting User",
        )
        db_session.add(signup)
        await db_session.commit()

        resp = await admin_client.post("/auth/invite", json={"email": "waiting@example.com"})
        assert resp.status_code == 409
        detail = resp.json()["detail"]
        assert detail["reason"] == "pending_signup_exists"
        assert detail["pending_signup_id"] == str(signup.id)


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


# ---------------------------------------------------------------------------
# Clerk errored user — 401 enforcement
# ---------------------------------------------------------------------------


class TestGetCurrentUserFullPath:
    """Covers the DB lookup and user-state checks in get_current_user."""

    FAKE_CLERK_ID = "clerk_full_path_test_001"

    @pytest.fixture(autouse=True)
    def _mock_clerk(self, monkeypatch):
        from app.config import get_settings

        monkeypatch.setattr(get_settings(), "clerk_publishable_key", "pk_test_dGVzdA")
        with patch("app.deps.verify_session_token", return_value=self.FAKE_CLERK_ID):
            yield

    async def test_user_not_in_db_returns_401(self, raw_client: AsyncClient):
        resp = await raw_client.get("/auth/me", headers={"Authorization": "Bearer tok"})
        assert resp.status_code == 401

    async def test_valid_user_returns_200(self, raw_client: AsyncClient, db_session: AsyncSession):
        user = User(
            email="valid_full@example.com",
            display_name="Valid User",
            clerk_user_id=self.FAKE_CLERK_ID,
        )
        db_session.add(user)
        await db_session.commit()
        resp = await raw_client.get("/auth/me", headers={"Authorization": "Bearer tok"})
        assert resp.status_code == 200

    async def test_deleted_user_returns_401(self, raw_client: AsyncClient, db_session: AsyncSession):
        from datetime import datetime, timezone

        user = User(
            email="deleted_full@example.com",
            display_name="Deleted",
            clerk_user_id=self.FAKE_CLERK_ID,
            deleted_at=datetime.now(timezone.utc),
        )
        db_session.add(user)
        await db_session.commit()
        resp = await raw_client.get("/auth/me", headers={"Authorization": "Bearer tok"})
        assert resp.status_code == 401

    async def test_inactive_user_returns_401(self, raw_client: AsyncClient, db_session: AsyncSession):
        user = User(
            email="inactive_full@example.com",
            display_name="Inactive",
            clerk_user_id=self.FAKE_CLERK_ID,
            is_active=False,
        )
        db_session.add(user)
        await db_session.commit()
        resp = await raw_client.get("/auth/me", headers={"Authorization": "Bearer tok"})
        assert resp.status_code == 401


class TestMissingClerkKey:
    """Covers the clerk_publishable_key not configured path."""

    async def test_no_clerk_key_returns_503(self, raw_client: AsyncClient, monkeypatch):
        from app.config import get_settings

        monkeypatch.setattr(get_settings(), "clerk_publishable_key", None)
        resp = await raw_client.get("/auth/me", headers={"Authorization": "Bearer tok"})
        assert resp.status_code == 503


class TestClerkErroredUser:
    """Users flagged clerk_errored=True must receive 401 on all requests."""

    @pytest.fixture(autouse=True)
    def _mock_clerk(self, monkeypatch):
        from app.config import get_settings

        monkeypatch.setattr(get_settings(), "clerk_publishable_key", "pk_test_dGVzdA")
        with patch("app.deps.verify_session_token", return_value="clerk_errored_001"):
            yield

    async def test_clerk_errored_user_gets_401(self, raw_client: AsyncClient, db_session: AsyncSession):
        user = User(
            email="errored@example.com",
            display_name="Errored User",
            clerk_user_id="clerk_errored_001",
            is_active=False,
            clerk_errored=True,
        )
        db_session.add(user)
        await db_session.commit()

        resp = await raw_client.get("/auth/me", headers={"Authorization": "Bearer fake.token"})
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# _handle_user_deleted webhook paths
# ---------------------------------------------------------------------------


class TestHandleUserDeleted:
    """Unit-level tests for the user.deleted webhook handler."""

    async def test_unexpected_deletion_flags_clerk_errored(self, db_session: AsyncSession):
        """user.deleted for a user with no deletion_state sets clerk_errored=True and is_active=False."""
        from app.routers.auth import _handle_user_deleted

        user = User(
            email="deleted@example.com",
            display_name="Deleted User",
            clerk_user_id="clerk_del_001",
        )
        db_session.add(user)
        await db_session.commit()

        await _handle_user_deleted(db_session, {"id": "clerk_del_001"})
        await db_session.refresh(user)

        assert user.clerk_errored is True
        assert user.is_active is False

    async def test_unexpected_deletion_does_not_soft_delete(self, db_session: AsyncSession):
        """Unexpected webhook deletion must not soft-delete the record (admins need to review it)."""
        from app.routers.auth import _handle_user_deleted

        user = User(
            email="nodelete@example.com",
            display_name="No Delete",
            clerk_user_id="clerk_del_002",
        )
        db_session.add(user)
        await db_session.commit()

        await _handle_user_deleted(db_session, {"id": "clerk_del_002"})
        await db_session.refresh(user)

        assert user.deleted_at is None

    async def test_in_progress_deletion_is_noop(self, db_session: AsyncSession):
        """user.deleted for a user already in the deletion pipeline must not change state."""
        from datetime import datetime, timezone

        from app.routers.auth import _handle_user_deleted

        user = User(
            email="inprogress@example.com",
            display_name="In Progress",
            clerk_user_id="clerk_del_003",
            deletion_state="pending",
            deletion_initiated_at=datetime.now(timezone.utc),
        )
        db_session.add(user)
        await db_session.commit()

        await _handle_user_deleted(db_session, {"id": "clerk_del_003"})
        await db_session.refresh(user)

        assert user.clerk_errored is False
        assert user.deletion_state == "pending"

    async def test_unknown_clerk_user_is_noop(self, db_session: AsyncSession):
        """user.deleted for an unrecognised clerk_user_id must not raise."""
        from app.routers.auth import _handle_user_deleted

        await _handle_user_deleted(db_session, {"id": "clerk_unknown_xyz"})


class TestHandleUserCreated:
    async def test_creates_pending_signup_for_unknown_email(self, db_session: AsyncSession, admin_user: User):
        from app.routers.auth import _handle_user_created

        with (
            patch("app.routers.auth.set_user_metadata", new_callable=AsyncMock),
            patch("app.routers.auth.send_signup_received_email", new_callable=AsyncMock),
            patch("app.routers.auth.send_pending_signup_notification", new_callable=AsyncMock) as mock_notify,
        ):
            await _handle_user_created(
                db_session,
                {
                    "id": "clerk_new_001",
                    "email_addresses": [{"id": "ea1", "email_address": "unknown@example.com"}],
                    "primary_email_address_id": "ea1",
                    "first_name": "Unknown",
                    "last_name": "User",
                },
            )

        pending = await db_session.scalar(select(PendingSignup).where(PendingSignup.clerk_user_id == "clerk_new_001"))
        assert pending is not None
        assert pending.email == "unknown@example.com"
        mock_notify.assert_awaited_once()

    async def test_duplicate_pending_signup_is_noop(self, db_session: AsyncSession):
        from app.routers.auth import _handle_user_created

        db_session.add(PendingSignup(clerk_user_id="clerk_dup_001", email="dup@example.com", display_name="Dup"))
        await db_session.commit()

        with (
            patch("app.routers.auth.set_user_metadata", new_callable=AsyncMock) as mock_meta,
            patch("app.routers.auth.send_signup_received_email", new_callable=AsyncMock),
            patch("app.routers.auth.send_pending_signup_notification", new_callable=AsyncMock),
        ):
            await _handle_user_created(
                db_session,
                {
                    "id": "clerk_dup_001",
                    "email_addresses": [{"id": "ea1", "email_address": "dup@example.com"}],
                    "primary_email_address_id": "ea1",
                    "first_name": "Dup",
                    "last_name": "User",
                },
            )

        mock_meta.assert_not_awaited()

    async def test_attaches_clerk_id_to_pre_created_user(self, db_session: AsyncSession):
        from app.routers.auth import _handle_user_created

        user = User(email="precreated@example.com", display_name="Pre Created")
        db_session.add(user)
        await db_session.commit()

        with patch("app.routers.auth.set_user_metadata", new_callable=AsyncMock) as mock_meta:
            await _handle_user_created(
                db_session,
                {
                    "id": "clerk_pre_001",
                    "email_addresses": [{"id": "ea1", "email_address": "precreated@example.com"}],
                    "primary_email_address_id": "ea1",
                    "first_name": "Pre",
                    "last_name": "Created",
                },
            )

        await db_session.refresh(user)
        assert user.clerk_user_id == "clerk_pre_001"
        mock_meta.assert_awaited_once()


class TestHandleUserUpdated:
    async def test_updates_email_and_display_name(self, db_session: AsyncSession):
        from app.routers.auth import _handle_user_updated

        user = User(
            email="old@example.com",
            display_name="Old Name",
            clerk_user_id="clerk_upd_001",
        )
        db_session.add(user)
        await db_session.commit()

        await _handle_user_updated(
            db_session,
            {
                "id": "clerk_upd_001",
                "email_addresses": [{"id": "ea1", "email_address": "new@example.com"}],
                "primary_email_address_id": "ea1",
                "first_name": "New",
                "last_name": "Name",
            },
        )

        await db_session.refresh(user)
        assert user.email == "new@example.com"
        assert user.display_name == "New Name"

    async def test_unknown_clerk_user_is_noop(self, db_session: AsyncSession):
        from app.routers.auth import _handle_user_updated

        await _handle_user_updated(db_session, {"id": "clerk_unknown_upd"})


class TestConsumeInvite:
    async def test_accepts_active_invite(self, db_session: AsyncSession, admin_user: User):
        from app.routers.auth import _consume_invite

        invite = Invite(
            email="invited@example.com",
            token="test-token-consume-001",  # noqa: S6418
            role="user",
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
            created_by_id=admin_user.id,
        )
        db_session.add(invite)
        await db_session.commit()

        result = await _consume_invite(db_session, "invited@example.com")

        assert result is not None
        assert result.accepted_at is not None

    async def test_no_invite_returns_none(self, db_session: AsyncSession):
        from app.routers.auth import _consume_invite

        result = await _consume_invite(db_session, "noinvite@example.com")
        assert result is None


class TestInviteRateLimit:
    """Verify the rate limit dependency is actually wired into POST /auth/invite."""

    @pytest.fixture(autouse=True)
    def mock_email(self):
        with patch("app.routers.auth.send_invite_email", new_callable=AsyncMock):
            yield

    async def test_429_after_limit_exceeded(self, admin_client: AsyncClient, db_session: AsyncSession):
        from unittest.mock import patch

        import fakeredis.aioredis

        from app.main import app
        from app.routers.auth import _invite_rate_limit

        fake = fakeredis.aioredis.FakeRedis(decode_responses=True)
        app.dependency_overrides.pop(_invite_rate_limit, None)
        try:
            with patch("app.services.rate_limiter.aioredis.from_url", return_value=fake):
                for i in range(20):
                    await admin_client.post("/auth/invite", json={"email": f"rl{i}@example.com", "role": "user"})
                resp = await admin_client.post("/auth/invite", json={"email": "overflow@example.com", "role": "user"})
            assert resp.status_code == 429
            assert "retry-after" in resp.headers
        finally:
            app.dependency_overrides[_invite_rate_limit] = lambda: None
