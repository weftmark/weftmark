import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.invite import Invite
from app.models.pending_signup import PendingSignup
from app.models.project import Project
from app.models.user import User

# ---------------------------------------------------------------------------
# GET /api/admin/users
# ---------------------------------------------------------------------------


class TestListAdminUsers:
    async def test_returns_200(self, admin_client: AsyncClient):
        resp = await admin_client.get("/api/admin/users")
        assert resp.status_code == 200

    async def test_returns_list(self, admin_client: AsyncClient, admin_user: User):
        resp = await admin_client.get("/api/admin/users")
        data = resp.json()
        assert isinstance(data, list)
        assert any(u["email"] == admin_user.email for u in data)

    async def test_returns_expected_user_fields(self, admin_client: AsyncClient, admin_user: User):
        resp = await admin_client.get("/api/admin/users")
        user_data = next(u for u in resp.json() if u["email"] == admin_user.email)
        assert "id" in user_data
        assert "email" in user_data
        assert "is_admin" in user_data
        assert "is_active" in user_data
        assert "counts" in user_data

    async def test_counts_include_projects(self, admin_client: AsyncClient, db_session: AsyncSession, admin_user: User):
        project = Project(
            owner_id=admin_user.id,
            name="Admin Project",
            wif_filename="test.wif",
            wif_path="projects/test/original.wif",
        )
        db_session.add(project)
        await db_session.commit()

        resp = await admin_client.get("/api/admin/users")
        user_data = next(u for u in resp.json() if u["email"] == admin_user.email)
        assert user_data["counts"]["projects"] >= 1

    async def test_does_not_return_deleted_users(self, admin_client: AsyncClient, db_session: AsyncSession):
        deleted_user = User(
            email="deleted@example.com",
            display_name="Deleted",
            oidc_sub="deleted-sub",
        )
        db_session.add(deleted_user)
        await db_session.flush()
        deleted_user.soft_delete()
        await db_session.commit()

        resp = await admin_client.get("/api/admin/users")
        assert all(u["email"] != "deleted@example.com" for u in resp.json())

    async def test_non_admin_returns_403(self, auth_client: AsyncClient):
        resp = await auth_client.get("/api/admin/users")
        assert resp.status_code == 403

    async def test_unauthenticated_returns_401(self, raw_client: AsyncClient):
        resp = await raw_client.get("/api/admin/users")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# PATCH /api/admin/users/{user_id}
# ---------------------------------------------------------------------------


class TestPatchAdminUser:
    async def _create_other_user(self, db_session: AsyncSession) -> User:
        other = User(
            email="other@admin-test.com",
            display_name="Other User",
            oidc_sub="other-admin-sub",
        )
        db_session.add(other)
        await db_session.commit()
        await db_session.refresh(other)
        return other

    async def test_returns_200(self, admin_client: AsyncClient, db_session: AsyncSession):
        other = await self._create_other_user(db_session)
        resp = await admin_client.patch(f"/api/admin/users/{other.id}", json={"is_active": False})
        assert resp.status_code == 200

    async def test_deactivates_user(self, admin_client: AsyncClient, db_session: AsyncSession):
        other = await self._create_other_user(db_session)
        resp = await admin_client.patch(f"/api/admin/users/{other.id}", json={"is_active": False})
        assert resp.json()["is_active"] is False

    async def test_grants_admin(self, superuser_client: AsyncClient, db_session: AsyncSession):
        other = await self._create_other_user(db_session)
        resp = await superuser_client.patch(f"/api/admin/users/{other.id}", json={"is_admin": True})
        assert resp.json()["is_admin"] is True

    async def test_returns_user_with_counts(self, admin_client: AsyncClient, db_session: AsyncSession):
        other = await self._create_other_user(db_session)
        resp = await admin_client.patch(f"/api/admin/users/{other.id}", json={"is_active": True})
        assert "counts" in resp.json()

    async def test_cannot_modify_own_account_returns_400(self, admin_client: AsyncClient, admin_user: User):
        resp = await admin_client.patch(f"/api/admin/users/{admin_user.id}", json={"is_active": False})
        assert resp.status_code == 400

    async def test_nonexistent_user_returns_404(self, admin_client: AsyncClient):
        resp = await admin_client.patch(f"/api/admin/users/{uuid.uuid4()}", json={"is_active": False})
        assert resp.status_code == 404

    async def test_non_admin_returns_403(self, auth_client: AsyncClient, db_session: AsyncSession):
        other = await self._create_other_user(db_session)
        resp = await auth_client.patch(f"/api/admin/users/{other.id}", json={"is_active": False})
        assert resp.status_code == 403

    async def test_unauthenticated_returns_401(self, raw_client: AsyncClient, db_session: AsyncSession):
        other = await self._create_other_user(db_session)
        resp = await raw_client.patch(f"/api/admin/users/{other.id}", json={"is_active": False})
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/admin/stats
# ---------------------------------------------------------------------------


class TestAdminStats:
    async def test_returns_200(self, admin_client: AsyncClient):
        resp = await admin_client.get("/api/admin/stats")
        assert resp.status_code == 200

    async def test_returns_expected_fields(self, admin_client: AsyncClient):
        data = (await admin_client.get("/api/admin/stats")).json()
        assert "total_users" in data
        assert "active_users" in data
        assert "active_7d" in data
        assert "active_30d" in data
        assert "active_90d" in data
        assert "total_projects" in data
        assert "total_activities" in data
        assert "total_looms" in data
        assert "total_yarn" in data
        assert "pending_invites" in data

    async def test_total_users_increments(self, admin_client: AsyncClient, db_session: AsyncSession, admin_user: User):
        before = (await admin_client.get("/api/admin/stats")).json()["total_users"]
        new_user = User(email="stat@test.com", display_name="Stat User", oidc_sub="stat-sub")
        db_session.add(new_user)
        await db_session.commit()
        after = (await admin_client.get("/api/admin/stats")).json()["total_users"]
        assert after == before + 1

    async def test_pending_invites_increments(
        self, admin_client: AsyncClient, db_session: AsyncSession, admin_user: User
    ):
        before = (await admin_client.get("/api/admin/stats")).json()["pending_invites"]
        invite = Invite(
            email="stats-invite@test.com",
            token="stats-tok",
            expires_at=datetime.now(timezone.utc) + timedelta(days=7),
            created_by_id=admin_user.id,
        )
        db_session.add(invite)
        await db_session.commit()
        after = (await admin_client.get("/api/admin/stats")).json()["pending_invites"]
        assert after == before + 1

    async def test_non_admin_returns_403(self, auth_client: AsyncClient):
        resp = await auth_client.get("/api/admin/stats")
        assert resp.status_code == 403

    async def test_unauthenticated_returns_401(self, raw_client: AsyncClient):
        resp = await raw_client.get("/api/admin/stats")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/admin/health
# ---------------------------------------------------------------------------


class TestAdminHealth:
    async def test_returns_200(self, admin_client: AsyncClient):
        resp = await admin_client.get("/api/admin/health")
        assert resp.status_code == 200

    async def test_returns_expected_fields(self, admin_client: AsyncClient):
        data = (await admin_client.get("/api/admin/health")).json()
        assert "cpu_percent" in data
        assert "memory_percent" in data
        assert "memory_used_mb" in data
        assert "memory_total_mb" in data
        assert "db_ping_ms" in data
        assert "uptime_seconds" in data

    async def test_db_ping_is_positive(self, admin_client: AsyncClient):
        data = (await admin_client.get("/api/admin/health")).json()
        assert data["db_ping_ms"] >= 0

    async def test_uptime_is_positive(self, admin_client: AsyncClient):
        data = (await admin_client.get("/api/admin/health")).json()
        assert data["uptime_seconds"] >= 0

    async def test_non_admin_returns_403(self, auth_client: AsyncClient):
        resp = await auth_client.get("/api/admin/health")
        assert resp.status_code == 403

    async def test_unauthenticated_returns_401(self, raw_client: AsyncClient):
        resp = await raw_client.get("/api/admin/health")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/admin/versions
# ---------------------------------------------------------------------------


class TestAdminVersions:
    async def test_returns_200(self, admin_client: AsyncClient):
        resp = await admin_client.get("/api/admin/versions")
        assert resp.status_code == 200

    async def test_returns_expected_fields(self, admin_client: AsyncClient):
        data = (await admin_client.get("/api/admin/versions")).json()
        assert "app" in data
        assert "python" in data
        assert "fastapi" in data
        assert "sqlalchemy" in data
        assert "alembic" in data
        assert "boto3" in data

    async def test_app_version_is_string(self, admin_client: AsyncClient):
        data = (await admin_client.get("/api/admin/versions")).json()
        assert isinstance(data["app"], str)
        assert len(data["app"]) > 0

    async def test_non_admin_returns_403(self, auth_client: AsyncClient):
        resp = await auth_client.get("/api/admin/versions")
        assert resp.status_code == 403

    async def test_unauthenticated_returns_401(self, raw_client: AsyncClient):
        resp = await raw_client.get("/api/admin/versions")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# PATCH /api/admin/users/{user_id} — superuser role enforcement
# ---------------------------------------------------------------------------


class TestPatchUserSuperuserEnforcement:
    async def _create_target(self, db_session: AsyncSession, **kwargs) -> User:
        user = User(
            email=f"target-{uuid.uuid4().hex[:6]}@test.com",
            display_name="Target User",
            oidc_sub=f"target-sub-{uuid.uuid4().hex}",
            **kwargs,
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)
        return user

    async def test_admin_cannot_grant_admin_returns_403(self, admin_client: AsyncClient, db_session: AsyncSession):
        target = await self._create_target(db_session)
        resp = await admin_client.patch(f"/api/admin/users/{target.id}", json={"is_admin": True})
        assert resp.status_code == 403

    async def test_admin_cannot_set_superuser_returns_403(self, admin_client: AsyncClient, db_session: AsyncSession):
        target = await self._create_target(db_session)
        resp = await admin_client.patch(f"/api/admin/users/{target.id}", json={"is_superuser": True})
        assert resp.status_code == 403

    async def test_superuser_can_grant_admin(self, superuser_client: AsyncClient, db_session: AsyncSession):
        target = await self._create_target(db_session)
        resp = await superuser_client.patch(f"/api/admin/users/{target.id}", json={"is_admin": True})
        assert resp.status_code == 200
        assert resp.json()["is_admin"] is True

    async def test_cannot_remove_admin_from_superuser_returns_400(
        self, superuser_client: AsyncClient, db_session: AsyncSession
    ):
        target = await self._create_target(db_session, is_admin=True, is_superuser=True)
        resp = await superuser_client.patch(f"/api/admin/users/{target.id}", json={"is_admin": False})
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# POST /api/admin/users/{user_id}/ban
# ---------------------------------------------------------------------------


class TestBanUser:
    @pytest.fixture(autouse=True)
    def mock_clerk(self):
        with (
            patch("app.routers.admin.ban_clerk_user", new_callable=AsyncMock),
            patch("app.routers.admin.set_user_metadata", new_callable=AsyncMock),
        ):
            yield

    async def _create_bannable_user(self, db_session: AsyncSession) -> User:
        user = User(
            email="bannable@test.com",
            display_name="Bannable User",
            oidc_sub="bannable-sub",
            clerk_user_id="clerk_bannable_001",
            is_admin=False,
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)
        return user

    async def test_returns_200(self, admin_client: AsyncClient, db_session: AsyncSession):
        user = await self._create_bannable_user(db_session)
        resp = await admin_client.post(f"/api/admin/users/{user.id}/ban")
        assert resp.status_code == 200

    async def test_marks_user_banned(self, admin_client: AsyncClient, db_session: AsyncSession):
        user = await self._create_bannable_user(db_session)
        resp = await admin_client.post(f"/api/admin/users/{user.id}/ban")
        assert resp.json()["clerk_banned"] is True

    async def test_deactivates_user(self, admin_client: AsyncClient, db_session: AsyncSession):
        user = await self._create_bannable_user(db_session)
        resp = await admin_client.post(f"/api/admin/users/{user.id}/ban")
        assert resp.json()["is_active"] is False

    async def test_no_clerk_id_returns_400(self, admin_client: AsyncClient, db_session: AsyncSession):
        user = User(
            email="no-clerk@test.com",
            display_name="No Clerk",
            oidc_sub="no-clerk-sub",
            clerk_user_id=None,
        )
        db_session.add(user)
        await db_session.commit()
        resp = await admin_client.post(f"/api/admin/users/{user.id}/ban")
        assert resp.status_code == 400

    async def test_admin_user_returns_400(self, admin_client: AsyncClient, db_session: AsyncSession):
        user = User(
            email="other-admin@test.com",
            display_name="Other Admin",
            oidc_sub="other-admin-sub",
            clerk_user_id="clerk_other_admin",
            is_admin=True,
        )
        db_session.add(user)
        await db_session.commit()
        resp = await admin_client.post(f"/api/admin/users/{user.id}/ban")
        assert resp.status_code == 400

    async def test_nonexistent_returns_404(self, admin_client: AsyncClient):
        resp = await admin_client.post(f"/api/admin/users/{uuid.uuid4()}/ban")
        assert resp.status_code == 404

    async def test_non_admin_returns_403(self, auth_client: AsyncClient, db_session: AsyncSession):
        user = await self._create_bannable_user(db_session)
        resp = await auth_client.post(f"/api/admin/users/{user.id}/ban")
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# POST /api/admin/users/{user_id}/unban
# ---------------------------------------------------------------------------


class TestUnbanUser:
    @pytest.fixture(autouse=True)
    def mock_clerk(self):
        with (
            patch("app.routers.admin.unban_clerk_user", new_callable=AsyncMock),
            patch("app.routers.admin.set_user_metadata", new_callable=AsyncMock),
        ):
            yield

    async def _create_banned_user(self, db_session: AsyncSession) -> User:
        user = User(
            email="banned@test.com",
            display_name="Banned User",
            oidc_sub="banned-sub",
            clerk_user_id="clerk_banned_001",
            clerk_banned=True,
            is_active=False,
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)
        return user

    async def test_returns_200(self, admin_client: AsyncClient, db_session: AsyncSession):
        user = await self._create_banned_user(db_session)
        resp = await admin_client.post(f"/api/admin/users/{user.id}/unban")
        assert resp.status_code == 200

    async def test_clears_banned_flag(self, admin_client: AsyncClient, db_session: AsyncSession):
        user = await self._create_banned_user(db_session)
        resp = await admin_client.post(f"/api/admin/users/{user.id}/unban")
        assert resp.json()["clerk_banned"] is False

    async def test_reactivates_user(self, admin_client: AsyncClient, db_session: AsyncSession):
        user = await self._create_banned_user(db_session)
        resp = await admin_client.post(f"/api/admin/users/{user.id}/unban")
        assert resp.json()["is_active"] is True

    async def test_no_clerk_id_returns_400(self, admin_client: AsyncClient, db_session: AsyncSession):
        user = User(
            email="no-clerk-unban@test.com",
            display_name="No Clerk Unban",
            oidc_sub="no-clerk-unban-sub",
            clerk_user_id=None,
        )
        db_session.add(user)
        await db_session.commit()
        resp = await admin_client.post(f"/api/admin/users/{user.id}/unban")
        assert resp.status_code == 400

    async def test_nonexistent_returns_404(self, admin_client: AsyncClient):
        resp = await admin_client.post(f"/api/admin/users/{uuid.uuid4()}/unban")
        assert resp.status_code == 404

    async def test_non_admin_returns_403(self, auth_client: AsyncClient, db_session: AsyncSession):
        user = await self._create_banned_user(db_session)
        resp = await auth_client.post(f"/api/admin/users/{user.id}/unban")
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /api/admin/pending-signups
# ---------------------------------------------------------------------------


class TestListPendingSignups:
    async def test_returns_200(self, admin_client: AsyncClient):
        resp = await admin_client.get("/api/admin/pending-signups")
        assert resp.status_code == 200

    async def test_returns_empty_list_when_none(self, admin_client: AsyncClient):
        resp = await admin_client.get("/api/admin/pending-signups")
        assert resp.json() == []

    async def test_returns_existing_signups(self, admin_client: AsyncClient, db_session: AsyncSession):
        signup = PendingSignup(
            clerk_user_id="clerk_pending_001",
            email="pending@test.com",
            display_name="Pending User",
        )
        db_session.add(signup)
        await db_session.commit()
        resp = await admin_client.get("/api/admin/pending-signups")
        data = resp.json()
        assert len(data) == 1
        assert data[0]["email"] == "pending@test.com"

    async def test_returns_expected_fields(self, admin_client: AsyncClient, db_session: AsyncSession):
        signup = PendingSignup(
            clerk_user_id="clerk_pending_fields",
            email="fields@test.com",
            display_name="Fields User",
        )
        db_session.add(signup)
        await db_session.commit()
        data = (await admin_client.get("/api/admin/pending-signups")).json()
        record = next(r for r in data if r["email"] == "fields@test.com")
        assert "id" in record
        assert "clerk_user_id" in record
        assert "display_name" in record
        assert "created_at" in record

    async def test_non_admin_returns_403(self, auth_client: AsyncClient):
        resp = await auth_client.get("/api/admin/pending-signups")
        assert resp.status_code == 403

    async def test_unauthenticated_returns_401(self, raw_client: AsyncClient):
        resp = await raw_client.get("/api/admin/pending-signups")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /api/admin/pending-signups/{id}/approve
# ---------------------------------------------------------------------------


class TestApprovePendingSignup:
    @pytest.fixture(autouse=True)
    def mock_clerk_and_email(self):
        with (
            patch("app.routers.admin.set_user_metadata", new_callable=AsyncMock),
            patch("app.routers.admin.send_account_approved_email", new_callable=AsyncMock),
            patch("app.routers.admin.send_approval_confirmation_to_admins", new_callable=AsyncMock),
        ):
            yield

    async def _create_signup(self, db_session: AsyncSession, suffix: str = "001") -> PendingSignup:
        signup = PendingSignup(
            clerk_user_id=f"clerk_approve_{suffix}",
            email=f"approve_{suffix}@test.com",
            display_name=f"Approve User {suffix}",
        )
        db_session.add(signup)
        await db_session.commit()
        await db_session.refresh(signup)
        return signup

    async def test_returns_201(self, admin_client: AsyncClient, db_session: AsyncSession):
        signup = await self._create_signup(db_session, "201")
        resp = await admin_client.post(f"/api/admin/pending-signups/{signup.id}/approve")
        assert resp.status_code == 201

    async def test_creates_user_in_db(self, admin_client: AsyncClient, db_session: AsyncSession):
        signup = await self._create_signup(db_session, "create")
        await admin_client.post(f"/api/admin/pending-signups/{signup.id}/approve")
        user = await db_session.scalar(
            select(User).where(User.clerk_user_id == signup.clerk_user_id, User.deleted_at.is_(None))
        )
        assert user is not None
        assert user.email == signup.email

    async def test_deletes_signup_record(self, admin_client: AsyncClient, db_session: AsyncSession):
        signup = await self._create_signup(db_session, "delete")
        signup_id = signup.id
        await admin_client.post(f"/api/admin/pending-signups/{signup_id}/approve")
        remaining = await db_session.scalar(select(PendingSignup).where(PendingSignup.id == signup_id))
        assert remaining is None

    async def test_sets_approved_by(self, admin_client: AsyncClient, db_session: AsyncSession, admin_user: User):
        signup = await self._create_signup(db_session, "approvedby")
        await admin_client.post(f"/api/admin/pending-signups/{signup.id}/approve")
        user = await db_session.scalar(select(User).where(User.clerk_user_id == signup.clerk_user_id))
        assert user.approved_by_email == admin_user.email

    async def test_nonexistent_returns_404(self, admin_client: AsyncClient):
        resp = await admin_client.post(f"/api/admin/pending-signups/{uuid.uuid4()}/approve")
        assert resp.status_code == 404

    async def test_non_admin_returns_403(self, auth_client: AsyncClient, db_session: AsyncSession):
        signup = await self._create_signup(db_session, "403")
        resp = await auth_client.post(f"/api/admin/pending-signups/{signup.id}/approve")
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# DELETE /api/admin/pending-signups/{id}  (dismiss)
# ---------------------------------------------------------------------------


class TestDismissPendingSignup:
    @pytest.fixture(autouse=True)
    def mock_clerk_and_email(self):
        with (
            patch("app.routers.admin.set_user_metadata", new_callable=AsyncMock),
            patch("app.routers.admin.send_account_denied_email", new_callable=AsyncMock),
        ):
            yield

    async def _create_signup(self, db_session: AsyncSession, suffix: str = "001") -> PendingSignup:
        signup = PendingSignup(
            clerk_user_id=f"clerk_dismiss_{suffix}",
            email=f"dismiss_{suffix}@test.com",
            display_name=f"Dismiss User {suffix}",
        )
        db_session.add(signup)
        await db_session.commit()
        await db_session.refresh(signup)
        return signup

    async def test_returns_204(self, admin_client: AsyncClient, db_session: AsyncSession):
        signup = await self._create_signup(db_session, "204")
        resp = await admin_client.delete(f"/api/admin/pending-signups/{signup.id}")
        assert resp.status_code == 204

    async def test_deletes_signup_record(self, admin_client: AsyncClient, db_session: AsyncSession):
        signup = await self._create_signup(db_session, "del")
        signup_id = signup.id
        await admin_client.delete(f"/api/admin/pending-signups/{signup_id}")
        remaining = await db_session.scalar(select(PendingSignup).where(PendingSignup.id == signup_id))
        assert remaining is None

    async def test_nonexistent_returns_404(self, admin_client: AsyncClient):
        resp = await admin_client.delete(f"/api/admin/pending-signups/{uuid.uuid4()}")
        assert resp.status_code == 404

    async def test_non_admin_returns_403(self, auth_client: AsyncClient, db_session: AsyncSession):
        signup = await self._create_signup(db_session, "403")
        resp = await auth_client.delete(f"/api/admin/pending-signups/{signup.id}")
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# POST /api/admin/pending-signups/{id}/ban
# ---------------------------------------------------------------------------


class TestBanPendingSignup:
    @pytest.fixture(autouse=True)
    def mock_clerk_and_email(self):
        with (
            patch("app.routers.admin.ban_clerk_user", new_callable=AsyncMock),
            patch("app.routers.admin.set_user_metadata", new_callable=AsyncMock),
            patch("app.routers.admin.send_account_denied_email", new_callable=AsyncMock),
        ):
            yield

    async def _create_signup(self, db_session: AsyncSession, suffix: str = "001") -> PendingSignup:
        signup = PendingSignup(
            clerk_user_id=f"clerk_ban_signup_{suffix}",
            email=f"ban_signup_{suffix}@test.com",
            display_name=f"Ban Signup User {suffix}",
        )
        db_session.add(signup)
        await db_session.commit()
        await db_session.refresh(signup)
        return signup

    async def test_returns_204(self, admin_client: AsyncClient, db_session: AsyncSession):
        signup = await self._create_signup(db_session, "204")
        resp = await admin_client.post(f"/api/admin/pending-signups/{signup.id}/ban")
        assert resp.status_code == 204

    async def test_deletes_signup_record(self, admin_client: AsyncClient, db_session: AsyncSession):
        signup = await self._create_signup(db_session, "del")
        signup_id = signup.id
        await admin_client.post(f"/api/admin/pending-signups/{signup_id}/ban")
        remaining = await db_session.scalar(select(PendingSignup).where(PendingSignup.id == signup_id))
        assert remaining is None

    async def test_nonexistent_returns_404(self, admin_client: AsyncClient):
        resp = await admin_client.post(f"/api/admin/pending-signups/{uuid.uuid4()}/ban")
        assert resp.status_code == 404

    async def test_non_admin_returns_403(self, auth_client: AsyncClient, db_session: AsyncSession):
        signup = await self._create_signup(db_session, "403")
        resp = await auth_client.post(f"/api/admin/pending-signups/{signup.id}/ban")
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# POST /api/admin/users/{user_id}/elevate-to-superuser
# ---------------------------------------------------------------------------


class TestElevateToSuperuser:
    @pytest.fixture(autouse=True)
    def mock_clerk(self):
        with patch("app.routers.admin.set_user_metadata", new_callable=AsyncMock):
            yield

    async def _create_admin_target(self, db_session: AsyncSession) -> User:
        user = User(
            email=f"elevate-target-{uuid.uuid4().hex[:6]}@test.com",
            display_name="Elevate Target",
            oidc_sub=f"elevate-sub-{uuid.uuid4().hex}",
            clerk_user_id=f"clerk_elevate_{uuid.uuid4().hex[:8]}",
            is_admin=True,
            is_superuser=False,
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)
        return user

    async def test_returns_200_no_content(self, superuser_client: AsyncClient, db_session: AsyncSession):
        target = await self._create_admin_target(db_session)
        resp = await superuser_client.post(
            f"/api/admin/users/{target.id}/elevate-to-superuser", json={"confirm_delete_content": False}
        )
        assert resp.status_code == 200

    async def test_sets_is_superuser(self, superuser_client: AsyncClient, db_session: AsyncSession):
        target = await self._create_admin_target(db_session)
        await superuser_client.post(
            f"/api/admin/users/{target.id}/elevate-to-superuser", json={"confirm_delete_content": False}
        )
        await db_session.refresh(target)
        assert target.is_superuser is True

    async def test_has_content_without_confirm_returns_409(
        self, superuser_client: AsyncClient, db_session: AsyncSession
    ):
        target = await self._create_admin_target(db_session)
        project = Project(
            owner_id=target.id,
            name="Target Project",
            wif_filename="test.wif",
            wif_path="projects/test/original.wif",
        )
        db_session.add(project)
        await db_session.commit()

        resp = await superuser_client.post(
            f"/api/admin/users/{target.id}/elevate-to-superuser", json={"confirm_delete_content": False}
        )
        assert resp.status_code == 409
        detail = resp.json()["detail"]
        assert detail["code"] == "has_content"
        assert detail["summary"]["projects"] >= 1

    async def test_has_content_with_confirm_returns_200(self, superuser_client: AsyncClient, db_session: AsyncSession):
        target = await self._create_admin_target(db_session)
        project = Project(
            owner_id=target.id,
            name="Target Project 2",
            wif_filename="test2.wif",
            wif_path="projects/test2/original.wif",
        )
        db_session.add(project)
        await db_session.commit()

        resp = await superuser_client.post(
            f"/api/admin/users/{target.id}/elevate-to-superuser", json={"confirm_delete_content": True}
        )
        assert resp.status_code == 200

    async def test_non_superuser_returns_403(self, admin_client: AsyncClient, db_session: AsyncSession):
        target = await self._create_admin_target(db_session)
        resp = await admin_client.post(
            f"/api/admin/users/{target.id}/elevate-to-superuser", json={"confirm_delete_content": False}
        )
        assert resp.status_code == 403

    async def test_nonexistent_returns_404(self, superuser_client: AsyncClient):
        resp = await superuser_client.post(
            f"/api/admin/users/{uuid.uuid4()}/elevate-to-superuser", json={"confirm_delete_content": False}
        )
        assert resp.status_code == 404

    async def test_non_admin_target_returns_400(self, superuser_client: AsyncClient, db_session: AsyncSession):
        target = User(
            email=f"plain-user-{uuid.uuid4().hex[:6]}@test.com",
            display_name="Plain User",
            oidc_sub=f"plain-sub-{uuid.uuid4().hex}",
            is_admin=False,
        )
        db_session.add(target)
        await db_session.commit()
        resp = await superuser_client.post(
            f"/api/admin/users/{target.id}/elevate-to-superuser", json={"confirm_delete_content": False}
        )
        assert resp.status_code == 400

    async def test_already_superuser_returns_400(self, superuser_client: AsyncClient, db_session: AsyncSession):
        target = User(
            email=f"already-super-{uuid.uuid4().hex[:6]}@test.com",
            display_name="Already Super",
            oidc_sub=f"already-super-sub-{uuid.uuid4().hex}",
            is_admin=True,
            is_superuser=True,
        )
        db_session.add(target)
        await db_session.commit()
        resp = await superuser_client.post(
            f"/api/admin/users/{target.id}/elevate-to-superuser", json={"confirm_delete_content": False}
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# GET /api/admin/eula  (superuser only)
# ---------------------------------------------------------------------------


class TestGetAdminEula:
    async def test_returns_200(self, superuser_client: AsyncClient):
        resp = await superuser_client.get("/api/admin/eula")
        assert resp.status_code == 200

    async def test_returns_current_version(self, superuser_client: AsyncClient):
        data = (await superuser_client.get("/api/admin/eula")).json()
        assert data["version"] == "0.3"

    async def test_returns_body_html(self, superuser_client: AsyncClient):
        data = (await superuser_client.get("/api/admin/eula")).json()
        assert "body_html" in data
        assert len(data["body_html"]) > 0

    async def test_non_superuser_returns_403(self, admin_client: AsyncClient):
        resp = await admin_client.get("/api/admin/eula")
        assert resp.status_code == 403

    async def test_unauthenticated_returns_401(self, client: AsyncClient):
        resp = await client.get("/api/admin/eula")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /api/admin/eula  (superuser only)
# ---------------------------------------------------------------------------


class TestCreateEulaVersion:
    async def test_returns_201(self, superuser_client: AsyncClient):
        resp = await superuser_client.post(
            "/api/admin/eula",
            json={"version": "1.0", "body_html": "<p>New terms</p>"},
        )
        assert resp.status_code == 201

    async def test_returns_version_fields(self, superuser_client: AsyncClient):
        resp = await superuser_client.post(
            "/api/admin/eula",
            json={"version": "1.1", "body_html": "<p>v1.1</p>"},
        )
        data = resp.json()
        assert data["version"] == "1.1"
        assert "id" in data
        assert "effective_date" in data
        assert "created_at" in data

    async def test_duplicate_version_returns_409(self, superuser_client: AsyncClient):
        await superuser_client.post("/api/admin/eula", json={"version": "2.0", "body_html": "<p>v2</p>"})
        resp = await superuser_client.post("/api/admin/eula", json={"version": "2.0", "body_html": "<p>dup</p>"})
        assert resp.status_code == 409

    async def test_new_version_becomes_current(self, superuser_client: AsyncClient, client: AsyncClient):
        await superuser_client.post(
            "/api/admin/eula",
            json={
                "version": "9.9",
                "body_html": "<p>latest</p>",
                "effective_date": "2099-01-01T00:00:00+00:00",
            },
        )
        current = (await client.get("/api/eula/current")).json()
        assert current["version"] == "9.9"

    async def test_non_superuser_returns_403(self, admin_client: AsyncClient):
        resp = await admin_client.post("/api/admin/eula", json={"version": "1.2", "body_html": "<p>x</p>"})
        assert resp.status_code == 403

    async def test_unauthenticated_returns_401(self, client: AsyncClient):
        resp = await client.post("/api/admin/eula", json={"version": "1.3", "body_html": "<p>x</p>"})
        assert resp.status_code == 401
