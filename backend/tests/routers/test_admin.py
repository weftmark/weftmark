import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.draft import Draft
from app.models.invite import Invite
from app.models.pending_signup import PendingSignup
from app.models.project import Project, ProjectPhoto
from app.models.user import User
from tests.conftest import SEEDED_EULA_VERSION

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

    async def test_counts_include_drafts(self, admin_client: AsyncClient, db_session: AsyncSession, admin_user: User):
        draft = Draft(
            owner_id=admin_user.id,
            name="Admin Draft",
            wif_filename="test.wif",
            wif_path="drafts/test/original.wif",
        )
        db_session.add(draft)
        await db_session.commit()

        resp = await admin_client.get("/api/admin/users")
        user_data = next(u for u in resp.json() if u["email"] == admin_user.email)
        assert user_data["counts"]["drafts"] >= 1

    async def test_counts_include_storage_bytes(self, admin_client: AsyncClient, admin_user: User):
        resp = await admin_client.get("/api/admin/users")
        user_data = next(u for u in resp.json() if u["email"] == admin_user.email)
        assert "storage_bytes" in user_data["counts"]
        assert isinstance(user_data["counts"]["storage_bytes"], int)

    async def test_storage_bytes_reflects_project_photos(
        self, admin_client: AsyncClient, db_session: AsyncSession, admin_user: User
    ):
        draft = Draft(
            owner_id=admin_user.id,
            name="Storage Test Draft",
            wif_filename="s.wif",
            wif_path="s.wif",
        )
        db_session.add(draft)
        await db_session.flush()
        project = Project(
            owner_id=admin_user.id,
            draft_id=draft.id,
            name="Storage Test Project",
            project_type="treadle",
            status="active",
            total_picks=100,
        )
        db_session.add(project)
        await db_session.flush()
        photo = ProjectPhoto(
            project_id=project.id,
            file_path="projects/test/photo.jpg",
            filename="photo.jpg",
            file_size_bytes=512_000,
            display_order=1,
        )
        db_session.add(photo)
        await db_session.commit()

        resp = await admin_client.get("/api/admin/users")
        user_data = next(u for u in resp.json() if u["email"] == admin_user.email)
        assert user_data["counts"]["storage_bytes"] >= 512_000

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

    async def test_deactivate_admin_returns_422(self, superuser_client: AsyncClient, db_session: AsyncSession):
        other = User(
            email="admin-to-deactivate@test.com",
            display_name="Admin To Deactivate",
            oidc_sub="admin-deactivate-sub",
            is_admin=True,
        )
        db_session.add(other)
        await db_session.commit()
        resp = await superuser_client.patch(f"/api/admin/users/{other.id}", json={"is_active": False})
        assert resp.status_code == 422

    async def test_deactivate_after_admin_removal_succeeds(
        self, superuser_client: AsyncClient, db_session: AsyncSession
    ):
        other = User(
            email="demoted@test.com",
            display_name="Demoted User",
            oidc_sub="demoted-sub",
            is_admin=True,
        )
        db_session.add(other)
        await db_session.commit()
        # Demote first
        await superuser_client.patch(f"/api/admin/users/{other.id}", json={"is_admin": False})
        # Now deactivate should succeed
        resp = await superuser_client.patch(f"/api/admin/users/{other.id}", json={"is_active": False})
        assert resp.status_code == 200
        assert resp.json()["is_active"] is False


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
        assert "total_drafts" in data
        assert "total_projects" in data
        assert "total_looms" in data
        assert "total_yarn" in data
        assert "pending_invites" in data
        assert "total_storage_bytes" in data

    async def test_total_storage_bytes_reflects_photos(
        self, admin_client: AsyncClient, db_session: AsyncSession, admin_user: User
    ):
        before = (await admin_client.get("/api/admin/stats")).json()["total_storage_bytes"]
        draft = Draft(
            owner_id=admin_user.id,
            name="Stats Storage Draft",
            wif_filename="s.wif",
            wif_path="s.wif",
        )
        db_session.add(draft)
        await db_session.flush()
        project = Project(
            owner_id=admin_user.id,
            draft_id=draft.id,
            name="Stats Storage Project",
            project_type="treadle",
            status="active",
            total_picks=100,
        )
        db_session.add(project)
        await db_session.flush()
        db_session.add(
            ProjectPhoto(
                project_id=project.id,
                file_path="projects/stats/photo.jpg",
                filename="photo.jpg",
                file_size_bytes=1_048_576,
                display_order=1,
            )
        )
        await db_session.commit()

        after = (await admin_client.get("/api/admin/stats")).json()["total_storage_bytes"]
        assert after >= before + 1_048_576

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
        assert "redis_server" in data
        assert "celery" in data
        assert "postgres" in data
        assert "backend_packages" in data
        assert isinstance(data["backend_packages"], dict)

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

    async def test_admin_user_returns_422(self, admin_client: AsyncClient, db_session: AsyncSession):
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
        assert resp.status_code == 422

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

    async def test_new_user_ai_training_consent_defaults_true(
        self, admin_client: AsyncClient, db_session: AsyncSession
    ):
        signup = await self._create_signup(db_session, "consent")
        await admin_client.post(f"/api/admin/pending-signups/{signup.id}/approve")
        user = await db_session.scalar(select(User).where(User.clerk_user_id == signup.clerk_user_id))
        assert user.ai_training_consent is True

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
        draft = Draft(
            owner_id=target.id,
            name="Target Draft",
            wif_filename="test.wif",
            wif_path="drafts/test/original.wif",
        )
        db_session.add(draft)
        await db_session.commit()

        resp = await superuser_client.post(
            f"/api/admin/users/{target.id}/elevate-to-superuser", json={"confirm_delete_content": False}
        )
        assert resp.status_code == 409
        detail = resp.json()["detail"]
        assert detail["code"] == "has_content"
        assert detail["summary"]["drafts"] >= 1

    async def test_has_content_with_confirm_returns_200(self, superuser_client: AsyncClient, db_session: AsyncSession):
        target = await self._create_admin_target(db_session)
        draft = Draft(
            owner_id=target.id,
            name="Target Draft 2",
            wif_filename="test2.wif",
            wif_path="drafts/test2/original.wif",
        )
        db_session.add(draft)
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
        assert data["version"] == SEEDED_EULA_VERSION

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


# ---------------------------------------------------------------------------
# GET /api/admin/reconcile  (superuser only)
# ---------------------------------------------------------------------------


class TestGetReconcileReport:
    @pytest.fixture(autouse=True)
    def mock_list_clerk_users(self):
        with patch(
            "app.routers.admin.list_clerk_users",
            new_callable=AsyncMock,
            return_value=[
                {"id": "clerk_abc", "email": "clerk_only@test.com", "display_name": "Clerk Only"},
                {"id": "clerk_shared", "email": "shared@test.com", "display_name": "Shared"},
            ],
        ):
            yield

    async def test_returns_200(self, superuser_client: AsyncClient):
        resp = await superuser_client.get("/api/admin/reconcile")
        assert resp.status_code == 200

    async def test_clerk_only_excludes_db_users(self, superuser_client: AsyncClient, db_session: AsyncSession):
        user = User(email="shared@test.com", display_name="Shared", clerk_user_id="clerk_shared")
        db_session.add(user)
        await db_session.commit()

        data = (await superuser_client.get("/api/admin/reconcile")).json()
        clerk_ids = [u["clerk_user_id"] for u in data["clerk_only"]]
        assert "clerk_shared" not in clerk_ids
        assert "clerk_abc" in clerk_ids

    async def test_clerk_only_excludes_pending_signups(self, superuser_client: AsyncClient, db_session: AsyncSession):
        signup = PendingSignup(clerk_user_id="clerk_abc", email="clerk_only@test.com", display_name="Clerk Only")
        db_session.add(signup)
        await db_session.commit()

        data = (await superuser_client.get("/api/admin/reconcile")).json()
        clerk_ids = [u["clerk_user_id"] for u in data["clerk_only"]]
        assert "clerk_abc" not in clerk_ids

    async def test_db_only_lists_orphaned_users(self, superuser_client: AsyncClient, db_session: AsyncSession):
        orphan = User(email="orphan@test.com", display_name="Orphan", clerk_user_id="clerk_gone_999")
        db_session.add(orphan)
        await db_session.commit()

        data = (await superuser_client.get("/api/admin/reconcile")).json()
        db_emails = [u["email"] for u in data["db_only"]]
        assert "orphan@test.com" in db_emails

    async def test_non_superuser_returns_403(self, admin_client: AsyncClient):
        resp = await admin_client.get("/api/admin/reconcile")
        assert resp.status_code == 403

    async def test_unauthenticated_returns_401(self, client: AsyncClient):
        resp = await client.get("/api/admin/reconcile")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /api/admin/reconcile/backfill/{clerk_user_id}  (superuser only)
# ---------------------------------------------------------------------------


class TestBackfillClerkUser:
    @pytest.fixture(autouse=True)
    def mock_clerk_and_metadata(self):
        with (
            patch(
                "app.routers.admin.get_clerk_user",
                new_callable=AsyncMock,
                return_value={
                    "id": "clerk_backfill_001",
                    "email": "backfill@test.com",
                    "display_name": "Backfill User",
                },
            ),
            patch("app.routers.admin.set_user_metadata", new_callable=AsyncMock),
        ):
            yield

    async def test_returns_201(self, superuser_client: AsyncClient):
        resp = await superuser_client.post("/api/admin/reconcile/backfill/clerk_backfill_001")
        assert resp.status_code == 201

    async def test_creates_user_in_db(self, superuser_client: AsyncClient, db_session: AsyncSession):
        await superuser_client.post("/api/admin/reconcile/backfill/clerk_backfill_001")
        user = await db_session.scalar(
            select(User).where(User.clerk_user_id == "clerk_backfill_001", User.deleted_at.is_(None))
        )
        assert user is not None
        assert user.email == "backfill@test.com"
        assert user.is_active is True

    async def test_returns_created_status(self, superuser_client: AsyncClient):
        data = (await superuser_client.post("/api/admin/reconcile/backfill/clerk_backfill_001")).json()
        assert data["status"] == "created"
        assert data["email"] == "backfill@test.com"

    async def test_attaches_to_pre_created_user(self, superuser_client: AsyncClient, db_session: AsyncSession):
        pre = User(email="backfill@test.com", display_name="Pre User", clerk_user_id=None)
        db_session.add(pre)
        await db_session.commit()
        await db_session.refresh(pre)

        data = (await superuser_client.post("/api/admin/reconcile/backfill/clerk_backfill_001")).json()
        assert data["status"] == "attached"
        assert data["user_id"] == str(pre.id)

    async def test_conflict_if_user_already_exists(self, superuser_client: AsyncClient, db_session: AsyncSession):
        user = User(email="backfill@test.com", display_name="Existing", clerk_user_id="clerk_backfill_001")
        db_session.add(user)
        await db_session.commit()

        resp = await superuser_client.post("/api/admin/reconcile/backfill/clerk_backfill_001")
        assert resp.status_code == 409

    async def test_not_found_if_clerk_user_missing(self, superuser_client: AsyncClient):
        with patch("app.routers.admin.get_clerk_user", new_callable=AsyncMock, return_value=None):
            resp = await superuser_client.post("/api/admin/reconcile/backfill/clerk_gone")
        assert resp.status_code == 404

    async def test_admin_role_sets_is_admin(self, superuser_client: AsyncClient, db_session: AsyncSession):
        await superuser_client.post("/api/admin/reconcile/backfill/clerk_backfill_001", json={"role": "admin"})
        user = await db_session.scalar(
            select(User).where(User.clerk_user_id == "clerk_backfill_001", User.deleted_at.is_(None))
        )
        assert user is not None
        assert user.is_admin is True

    async def test_non_superuser_returns_403(self, admin_client: AsyncClient):
        resp = await admin_client.post("/api/admin/reconcile/backfill/clerk_backfill_001")
        assert resp.status_code == 403

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


# ---------------------------------------------------------------------------
# GET /api/admin/services
# ---------------------------------------------------------------------------


class TestAdminServices:
    @pytest.fixture(autouse=True)
    def mock_external_probes(self):
        from app.routers.admin import ServiceCheckResult

        ok = lambda svc, n: ServiceCheckResult(  # noqa: E731
            service=svc, status="ok", message=f"{n}/{n} checks passed", checks=[]
        )
        with (
            patch("app.routers.admin._probe_s3", new_callable=AsyncMock, return_value=ok("S3", 3)),
            patch("app.routers.admin._probe_clerk", new_callable=AsyncMock, return_value=ok("Clerk", 4)),
            patch("app.routers.admin._probe_smtp", new_callable=AsyncMock, return_value=ok("SMTP", 4)),
        ):
            yield

    async def test_returns_200(self, admin_client: AsyncClient):
        resp = await admin_client.get("/api/admin/services")
        assert resp.status_code == 200

    async def test_returns_six_services(self, admin_client: AsyncClient):
        data = (await admin_client.get("/api/admin/services")).json()
        assert len(data) == 6
        names = {s["service"] for s in data}
        assert names == {"PostgreSQL", "S3", "Clerk", "SMTP", "Clerk Webhook", "Configuration"}

    async def test_webhook_service_includes_url(self, admin_client: AsyncClient):
        data = (await admin_client.get("/api/admin/services")).json()
        wh = next(s for s in data if s["service"] == "Clerk Webhook")
        assert "url" in wh["meta"]
        assert wh["meta"]["url"].endswith("/webhooks/clerk")

    async def test_webhook_service_cf_disabled_by_default(self, admin_client: AsyncClient):
        data = (await admin_client.get("/api/admin/services")).json()
        wh = next(s for s in data if s["service"] == "Clerk Webhook")
        cf_check = next((c for c in wh["checks"] if c["name"] == "cf_access"), None)
        assert cf_check is not None
        assert cf_check["message"] == "Disabled"

    async def test_each_result_has_expected_fields(self, admin_client: AsyncClient):
        data = (await admin_client.get("/api/admin/services")).json()
        for s in data:
            assert "service" in s
            assert "status" in s
            assert "message" in s
            assert "checks" in s

    async def test_postgres_probe_passes_against_test_db(self, admin_client: AsyncClient):
        data = (await admin_client.get("/api/admin/services")).json()
        pg = next(s for s in data if s["service"] == "PostgreSQL")
        assert pg["status"] == "ok"

    async def test_non_admin_returns_403(self, auth_client: AsyncClient):
        resp = await auth_client.get("/api/admin/services")
        assert resp.status_code == 403

    async def test_unauthenticated_returns_401(self, raw_client: AsyncClient):
        resp = await raw_client.get("/api/admin/services")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /api/admin/test-email
# ---------------------------------------------------------------------------


class TestSendTestEmail:
    @pytest.fixture(autouse=True)
    def mock_email(self):
        with patch("app.routers.admin.send_test_email", new_callable=AsyncMock) as m:
            yield m

    async def test_returns_200(self, admin_client: AsyncClient):
        resp = await admin_client.post("/api/admin/test-email")
        assert resp.status_code == 200

    async def test_returns_status_and_to(self, admin_client: AsyncClient, admin_user: User):
        data = (await admin_client.post("/api/admin/test-email")).json()
        assert data["status"] == "sent"
        assert data["to"] == admin_user.email

    async def test_calls_send_test_email_with_admin_email(
        self, admin_client: AsyncClient, admin_user: User, mock_email: AsyncMock
    ):
        await admin_client.post("/api/admin/test-email")
        mock_email.assert_called_once_with(admin_user.email)

    async def test_non_admin_returns_403(self, auth_client: AsyncClient):
        resp = await auth_client.post("/api/admin/test-email")
        assert resp.status_code == 403

    async def test_unauthenticated_returns_401(self, raw_client: AsyncClient):
        resp = await raw_client.post("/api/admin/test-email")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /api/admin/users/{user_id}/delete
# ---------------------------------------------------------------------------


class TestDeleteUser:
    @pytest.fixture(autouse=True)
    def mock_deletion_service(self):
        with patch("app.services.deletion.initiate_user_deletion", new_callable=AsyncMock) as m:
            yield m

    async def _create_target(self, db_session: AsyncSession) -> User:
        user = User(
            email=f"del-target-{uuid.uuid4().hex[:6]}@test.com",
            display_name="Delete Target",
            oidc_sub=f"del-sub-{uuid.uuid4().hex}",
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)
        return user

    async def test_returns_202(self, superuser_client: AsyncClient, db_session: AsyncSession):
        target = await self._create_target(db_session)
        resp = await superuser_client.post(f"/api/admin/users/{target.id}/delete", json={"confirm": "DELETE USER"})
        assert resp.status_code == 202

    async def test_returns_pending_status_and_user_id(self, superuser_client: AsyncClient, db_session: AsyncSession):
        target = await self._create_target(db_session)
        resp = await superuser_client.post(f"/api/admin/users/{target.id}/delete", json={"confirm": "DELETE USER"})
        data = resp.json()
        assert data["status"] == "pending"
        assert data["user_id"] == str(target.id)

    async def test_wrong_confirm_returns_422(self, superuser_client: AsyncClient, db_session: AsyncSession):
        target = await self._create_target(db_session)
        resp = await superuser_client.post(f"/api/admin/users/{target.id}/delete", json={"confirm": "WRONG STRING"})
        assert resp.status_code == 422

    async def test_empty_confirm_returns_422(self, superuser_client: AsyncClient, db_session: AsyncSession):
        target = await self._create_target(db_session)
        resp = await superuser_client.post(f"/api/admin/users/{target.id}/delete", json={"confirm": ""})
        assert resp.status_code == 422

    async def test_nonexistent_user_returns_404(self, superuser_client: AsyncClient):
        resp = await superuser_client.post(f"/api/admin/users/{uuid.uuid4()}/delete", json={"confirm": "DELETE USER"})
        assert resp.status_code == 404

    async def test_self_delete_returns_400(self, superuser_client: AsyncClient, superuser_user: User):
        resp = await superuser_client.post(
            f"/api/admin/users/{superuser_user.id}/delete", json={"confirm": "DELETE USER"}
        )
        assert resp.status_code == 400

    async def test_already_pending_returns_409(self, superuser_client: AsyncClient, db_session: AsyncSession):
        target = await self._create_target(db_session)
        target.deletion_state = "pending"
        await db_session.commit()
        resp = await superuser_client.post(f"/api/admin/users/{target.id}/delete", json={"confirm": "DELETE USER"})
        assert resp.status_code == 409

    async def test_already_in_progress_returns_409(self, superuser_client: AsyncClient, db_session: AsyncSession):
        target = await self._create_target(db_session)
        target.deletion_state = "in_progress"
        await db_session.commit()
        resp = await superuser_client.post(f"/api/admin/users/{target.id}/delete", json={"confirm": "DELETE USER"})
        assert resp.status_code == 409

    async def test_non_superuser_returns_403(self, admin_client: AsyncClient, db_session: AsyncSession):
        target = await self._create_target(db_session)
        resp = await admin_client.post(f"/api/admin/users/{target.id}/delete", json={"confirm": "DELETE USER"})
        assert resp.status_code == 403

    async def test_unauthenticated_returns_401(self, raw_client: AsyncClient, db_session: AsyncSession):
        target = await self._create_target(db_session)
        resp = await raw_client.post(f"/api/admin/users/{target.id}/delete", json={"confirm": "DELETE USER"})
        assert resp.status_code == 401

    async def test_calls_initiate_user_deletion(
        self,
        superuser_client: AsyncClient,
        db_session: AsyncSession,
        mock_deletion_service: AsyncMock,
    ):
        target = await self._create_target(db_session)
        await superuser_client.post(f"/api/admin/users/{target.id}/delete", json={"confirm": "DELETE USER"})
        mock_deletion_service.assert_called_once()


# ---------------------------------------------------------------------------
# GET /api/admin/scheduled-tasks
# ---------------------------------------------------------------------------


class TestListScheduledTasks:
    async def test_returns_200(self, superuser_client: AsyncClient):
        resp = await superuser_client.get("/api/admin/scheduled-tasks")
        assert resp.status_code == 200

    async def test_returns_list(self, superuser_client: AsyncClient):
        resp = await superuser_client.get("/api/admin/scheduled-tasks")
        data = resp.json()
        assert isinstance(data, list)

    async def test_includes_cve_scan(self, superuser_client: AsyncClient):
        resp = await superuser_client.get("/api/admin/scheduled-tasks")
        names = [t["name"] for t in resp.json()]
        assert "cve_scan" in names

    async def test_task_has_required_fields(self, superuser_client: AsyncClient):
        resp = await superuser_client.get("/api/admin/scheduled-tasks")
        task = next(t for t in resp.json() if t["name"] == "cve_scan")
        assert "name" in task
        assert "display_name" in task
        assert "description" in task
        assert "enabled" in task
        assert "cron" in task
        assert "next_runs" in task

    async def test_next_runs_has_three_entries(self, superuser_client: AsyncClient):
        resp = await superuser_client.get("/api/admin/scheduled-tasks")
        task = next(t for t in resp.json() if t["name"] == "cve_scan")
        assert len(task["next_runs"]) == 3

    async def test_cve_scan_disabled_by_default(self, superuser_client: AsyncClient):
        resp = await superuser_client.get("/api/admin/scheduled-tasks")
        task = next(t for t in resp.json() if t["name"] == "cve_scan")
        assert task["enabled"] is False

    async def test_non_superuser_returns_403(self, admin_client: AsyncClient):
        resp = await admin_client.get("/api/admin/scheduled-tasks")
        assert resp.status_code == 403

    async def test_unauthenticated_returns_401(self, client: AsyncClient):
        resp = await client.get("/api/admin/scheduled-tasks")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# PATCH /api/admin/scheduled-tasks/{name}
# ---------------------------------------------------------------------------


class TestPatchScheduledTask:
    async def test_enable_task(self, superuser_client: AsyncClient):
        resp = await superuser_client.patch("/api/admin/scheduled-tasks/cve_scan", json={"enabled": True})
        assert resp.status_code == 200
        assert resp.json()["enabled"] is True

    async def test_disable_task(self, superuser_client: AsyncClient):
        await superuser_client.patch("/api/admin/scheduled-tasks/cve_scan", json={"enabled": True})
        resp = await superuser_client.patch("/api/admin/scheduled-tasks/cve_scan", json={"enabled": False})
        assert resp.status_code == 200
        assert resp.json()["enabled"] is False

    async def test_update_cron(self, superuser_client: AsyncClient):
        resp = await superuser_client.patch("/api/admin/scheduled-tasks/cve_scan", json={"cron": "0 6 * * *"})
        assert resp.status_code == 200
        assert resp.json()["cron"] == "0 6 * * *"

    async def test_update_persists(self, superuser_client: AsyncClient, db_session: AsyncSession):
        await superuser_client.patch(
            "/api/admin/scheduled-tasks/cve_scan",
            json={"enabled": True, "cron": "0 12 * * 1"},
        )
        from sqlalchemy import select

        from app.models.scheduled_task import ScheduledTask

        row = await db_session.scalar(select(ScheduledTask).where(ScheduledTask.name == "cve_scan"))
        assert row is not None
        assert row.enabled is True
        assert row.cron == "0 12 * * 1"

    async def test_invalid_cron_returns_422(self, superuser_client: AsyncClient):
        resp = await superuser_client.patch("/api/admin/scheduled-tasks/cve_scan", json={"cron": "not a cron"})
        assert resp.status_code == 422

    async def test_unknown_task_returns_404(self, superuser_client: AsyncClient):
        resp = await superuser_client.patch("/api/admin/scheduled-tasks/nonexistent_task", json={"enabled": True})
        assert resp.status_code == 404

    async def test_non_superuser_returns_403(self, admin_client: AsyncClient):
        resp = await admin_client.patch("/api/admin/scheduled-tasks/cve_scan", json={"enabled": True})
        assert resp.status_code == 403

    async def test_unauthenticated_returns_401(self, client: AsyncClient):
        resp = await client.patch("/api/admin/scheduled-tasks/cve_scan", json={"enabled": True})
        assert resp.status_code == 401

    async def test_response_includes_next_runs(self, superuser_client: AsyncClient):
        resp = await superuser_client.patch("/api/admin/scheduled-tasks/cve_scan", json={"cron": "0 2 * * *"})
        assert len(resp.json()["next_runs"]) == 3

    async def test_partial_update_preserves_other_fields(self, superuser_client: AsyncClient):
        await superuser_client.patch("/api/admin/scheduled-tasks/cve_scan", json={"cron": "0 3 * * *"})
        resp = await superuser_client.patch("/api/admin/scheduled-tasks/cve_scan", json={"enabled": True})
        assert resp.json()["cron"] == "0 3 * * *"
        assert resp.json()["enabled"] is True


# ---------------------------------------------------------------------------
# GET /api/admin/project-steps
# ---------------------------------------------------------------------------


class TestAdminProjectSteps:
    async def _insert_project(self, db: AsyncSession, owner: User) -> Project:
        import uuid as _uuid

        from app.models.draft import Draft as _Draft

        draft = _Draft(
            id=_uuid.uuid4(),
            owner_id=owner.id,
            name="Step Log Test Draft",
            wif_filename="t.wif",
            wif_path="drafts/t.wif",
            has_treadling=True,
            has_liftplan=True,
            num_shafts=4,
            num_treadles=4,
            weft_threads=2,
        )
        db.add(draft)
        project = Project(
            owner_id=owner.id,
            draft_id=draft.id,
            name="Step Log Test Project",
            project_type="treadle",
            status="active",
            current_pick=3,
            total_picks=10,
        )
        db.add(project)
        await db.commit()
        return project

    async def test_returns_200(self, admin_client: AsyncClient, db_session: AsyncSession, admin_user: User):
        project = await self._insert_project(db_session, admin_user)
        resp = await admin_client.get(f"/api/admin/project-steps?project_id={project.id}")
        assert resp.status_code == 200

    async def test_returns_steps_for_project(
        self, admin_client: AsyncClient, db_session: AsyncSession, admin_user: User
    ):
        from app.models.project import ProjectStep

        project = await self._insert_project(db_session, admin_user)
        db_session.add_all(
            [
                ProjectStep(project_id=project.id, event_type="advance", from_pick=1, to_pick=2, dwell_ms=5_000),
                ProjectStep(project_id=project.id, event_type="advance", from_pick=2, to_pick=3, dwell_ms=6_000),
            ]
        )
        await db_session.commit()

        resp = await admin_client.get(f"/api/admin/project-steps?project_id={project.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["event_type"] in ("advance", "reverse")
        assert "dwell_ms" in data[0]
        assert "created_at" in data[0]

    async def test_most_recent_first(self, admin_client: AsyncClient, db_session: AsyncSession, admin_user: User):
        from datetime import datetime, timedelta, timezone

        from app.models.project import ProjectStep

        project = await self._insert_project(db_session, admin_user)
        now = datetime.now(timezone.utc)
        db_session.add_all(
            [
                ProjectStep(
                    project_id=project.id,
                    event_type="advance",
                    from_pick=1,
                    to_pick=2,
                    dwell_ms=5_000,
                    created_at=now - timedelta(seconds=10),
                ),
                ProjectStep(
                    project_id=project.id,
                    event_type="advance",
                    from_pick=2,
                    to_pick=3,
                    dwell_ms=6_000,
                    created_at=now,
                ),
            ]
        )
        await db_session.commit()

        resp = await admin_client.get(f"/api/admin/project-steps?project_id={project.id}")
        data = resp.json()
        assert data[0]["to_pick"] == 3  # most recent first

    async def test_missing_project_id_returns_422(self, admin_client: AsyncClient):
        resp = await admin_client.get("/api/admin/project-steps")
        assert resp.status_code == 422

    async def test_non_admin_returns_403(self, auth_client: AsyncClient, db_session: AsyncSession, admin_user: User):
        project = await self._insert_project(db_session, admin_user)
        resp = await auth_client.get(f"/api/admin/project-steps?project_id={project.id}")
        assert resp.status_code == 403

    async def test_unauthenticated_returns_401(self, client: AsyncClient, db_session: AsyncSession, admin_user: User):
        project = await self._insert_project(db_session, admin_user)
        resp = await client.get(f"/api/admin/project-steps?project_id={project.id}")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/admin/audit-log
# ---------------------------------------------------------------------------


class TestAuditLog:
    async def test_returns_200(self, admin_client: AsyncClient):
        resp = await admin_client.get("/api/admin/audit-log")
        assert resp.status_code == 200

    async def test_response_structure(self, admin_client: AsyncClient):
        data = (await admin_client.get("/api/admin/audit-log")).json()
        assert "items" in data
        assert "total" in data
        assert "page" in data
        assert "page_size" in data
        assert "pages" in data

    async def test_filter_by_event_type(self, admin_client: AsyncClient):
        resp = await admin_client.get("/api/admin/audit-log?event_type=user.banned")
        assert resp.status_code == 200

    async def test_filter_by_q(self, admin_client: AsyncClient):
        resp = await admin_client.get("/api/admin/audit-log?q=admin")
        assert resp.status_code == 200

    async def test_custom_page_size(self, admin_client: AsyncClient):
        data = (await admin_client.get("/api/admin/audit-log?page=1&page_size=10")).json()
        assert data["page"] == 1
        assert data["page_size"] == 10

    async def test_non_admin_returns_403(self, auth_client: AsyncClient):
        resp = await auth_client.get("/api/admin/audit-log")
        assert resp.status_code == 403

    async def test_unauthenticated_returns_401(self, raw_client: AsyncClient):
        resp = await raw_client.get("/api/admin/audit-log")
        assert resp.status_code == 401

    async def test_entries_have_expected_fields(
        self, admin_client: AsyncClient, db_session: AsyncSession, admin_user: User
    ):
        from app.services.audit import write_audit_log

        await write_audit_log(db_session, event_type="test.event", actor=admin_user)
        await db_session.commit()

        data = (await admin_client.get("/api/admin/audit-log")).json()
        if data["items"]:
            entry = data["items"][0]
            for field in ("id", "event_type", "created_at"):
                assert field in entry


# ---------------------------------------------------------------------------
# GET /api/admin/server-events
# ---------------------------------------------------------------------------


class TestServerEvents:
    async def test_returns_200(self, admin_client: AsyncClient):
        resp = await admin_client.get("/api/admin/server-events")
        assert resp.status_code == 200

    async def test_response_structure(self, admin_client: AsyncClient):
        data = (await admin_client.get("/api/admin/server-events")).json()
        assert "items" in data
        assert "total" in data
        assert "pages" in data

    async def test_filter_by_event_type(self, admin_client: AsyncClient):
        resp = await admin_client.get("/api/admin/server-events?event_type=backup.start")
        assert resp.status_code == 200

    async def test_non_admin_returns_403(self, auth_client: AsyncClient):
        resp = await auth_client.get("/api/admin/server-events")
        assert resp.status_code == 403

    async def test_unauthenticated_returns_401(self, raw_client: AsyncClient):
        resp = await raw_client.get("/api/admin/server-events")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET/POST/PATCH/DELETE /api/admin/credentials
# ---------------------------------------------------------------------------


class TestCredentials:
    async def test_list_returns_200(self, admin_client: AsyncClient):
        resp = await admin_client.get("/api/admin/credentials")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    async def test_list_non_admin_returns_403(self, auth_client: AsyncClient):
        resp = await auth_client.get("/api/admin/credentials")
        assert resp.status_code == 403

    async def test_create_credential_returns_201(self, superuser_client: AsyncClient, superuser_user: User):
        payload = {"name": "Test SMTP Key", "resource": "smtp", "notes": "expires soon"}
        resp = await superuser_client.post("/api/admin/credentials", json=payload)
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "Test SMTP Key"
        assert data["resource"] == "smtp"
        assert "id" in data
        assert "days_remaining" in data

    async def test_create_invalid_resource_returns_422(self, superuser_client: AsyncClient, superuser_user: User):
        payload = {"name": "Bad Key", "resource": "invalid_resource"}
        resp = await superuser_client.post("/api/admin/credentials", json=payload)
        assert resp.status_code == 422

    async def test_create_requires_superuser(self, admin_client: AsyncClient, admin_user: User):
        resp = await admin_client.post("/api/admin/credentials", json={"name": "X", "resource": "s3"})
        assert resp.status_code == 403

    async def test_patch_credential(self, superuser_client: AsyncClient, superuser_user: User):
        create_resp = await superuser_client.post(
            "/api/admin/credentials", json={"name": "Patchable", "resource": "clerk"}
        )
        cred_id = create_resp.json()["id"]
        resp = await superuser_client.patch(f"/api/admin/credentials/{cred_id}", json={"name": "Updated Name"})
        assert resp.status_code == 200
        assert resp.json()["name"] == "Updated Name"

    async def test_patch_invalid_resource_returns_422(self, superuser_client: AsyncClient, superuser_user: User):
        create_resp = await superuser_client.post("/api/admin/credentials", json={"name": "PatchBad", "resource": "s3"})
        cred_id = create_resp.json()["id"]
        resp = await superuser_client.patch(f"/api/admin/credentials/{cred_id}", json={"resource": "bad_resource"})
        assert resp.status_code == 422

    async def test_patch_nonexistent_returns_404(self, superuser_client: AsyncClient, superuser_user: User):
        resp = await superuser_client.patch(f"/api/admin/credentials/{uuid.uuid4()}", json={"name": "X"})
        assert resp.status_code == 404

    async def test_delete_credential_returns_204(self, superuser_client: AsyncClient, superuser_user: User):
        create_resp = await superuser_client.post(
            "/api/admin/credentials", json={"name": "Deletable", "resource": "postgres"}
        )
        cred_id = create_resp.json()["id"]
        resp = await superuser_client.delete(f"/api/admin/credentials/{cred_id}")
        assert resp.status_code == 204

    async def test_delete_nonexistent_returns_404(self, superuser_client: AsyncClient, superuser_user: User):
        resp = await superuser_client.delete(f"/api/admin/credentials/{uuid.uuid4()}")
        assert resp.status_code == 404

    async def test_delete_requires_superuser(self, admin_client: AsyncClient, admin_user: User):
        resp = await admin_client.delete(f"/api/admin/credentials/{uuid.uuid4()}")
        assert resp.status_code == 403

    async def test_credential_with_expires_on_has_days_remaining(
        self, superuser_client: AsyncClient, superuser_user: User
    ):
        from datetime import date, timedelta

        future = (date.today() + timedelta(days=30)).isoformat()
        resp = await superuser_client.post(
            "/api/admin/credentials", json={"name": "Expiring", "resource": "app", "expires_on": future}
        )
        assert resp.status_code == 201
        assert resp.json()["days_remaining"] is not None
        assert resp.json()["days_remaining"] >= 29


# ---------------------------------------------------------------------------
# GET/DELETE /api/admin/project-slugs
# ---------------------------------------------------------------------------


class TestProjectSlugs:
    async def _create_shared_project(self, db: AsyncSession, owner: User) -> "Project":
        from app.models.draft import Draft

        draft = Draft(
            owner_id=owner.id,
            name="Slug Test Draft",
            wif_filename="slug.wif",
            wif_path="drafts/slug.wif",
        )
        db.add(draft)
        await db.flush()
        proj = Project(
            owner_id=owner.id,
            draft_id=draft.id,
            name="Slug Test Project",
            project_type="treadle",
            total_picks=10,
            share_slug=f"slug-{uuid.uuid4().hex[:8]}",
            share_visibility="public",
        )
        db.add(proj)
        await db.commit()
        await db.refresh(proj)
        return proj

    async def test_list_returns_200(self, admin_client: AsyncClient, admin_user: User):
        resp = await admin_client.get("/api/admin/project-slugs")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    async def test_list_includes_shared_project(
        self, admin_client: AsyncClient, db_session: AsyncSession, admin_user: User
    ):
        proj = await self._create_shared_project(db_session, admin_user)
        resp = await admin_client.get("/api/admin/project-slugs")
        slugs = [r["slug"] for r in resp.json()]
        assert proj.share_slug in slugs

    async def test_list_non_admin_returns_403(self, auth_client: AsyncClient):
        resp = await auth_client.get("/api/admin/project-slugs")
        assert resp.status_code == 403

    async def test_revoke_slug_returns_204(self, admin_client: AsyncClient, db_session: AsyncSession, admin_user: User):
        proj = await self._create_shared_project(db_session, admin_user)
        resp = await admin_client.delete(f"/api/admin/project-slugs/{proj.share_slug}")
        assert resp.status_code == 204

    async def test_revoke_clears_slug_and_visibility(
        self, admin_client: AsyncClient, db_session: AsyncSession, admin_user: User
    ):
        proj = await self._create_shared_project(db_session, admin_user)
        slug = proj.share_slug
        await admin_client.delete(f"/api/admin/project-slugs/{slug}")
        await db_session.refresh(proj)
        assert proj.share_slug is None
        assert proj.share_visibility == "private"

    async def test_revoke_nonexistent_slug_returns_404(self, admin_client: AsyncClient, admin_user: User):
        resp = await admin_client.delete("/api/admin/project-slugs/nonexistent-slug-xyz")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/admin/task-history and POST /api/admin/tasks/{task_id}/revoke
# ---------------------------------------------------------------------------


class TestTaskHistory:
    async def test_returns_200(self, superuser_client: AsyncClient):
        resp = await superuser_client.get("/api/admin/task-history")
        assert resp.status_code == 200

    async def test_response_structure(self, superuser_client: AsyncClient):
        data = (await superuser_client.get("/api/admin/task-history")).json()
        assert "items" in data
        assert "total" in data
        assert "pages" in data

    async def test_non_superuser_returns_403(self, admin_client: AsyncClient):
        resp = await admin_client.get("/api/admin/task-history")
        assert resp.status_code == 403

    async def test_unauthenticated_returns_401(self, client: AsyncClient):
        resp = await client.get("/api/admin/task-history")
        assert resp.status_code == 401


class TestRevokeTask:
    async def test_returns_200_and_revoked_status(self, superuser_client: AsyncClient):
        fake_task_id = str(uuid.uuid4())
        with (
            patch("app.celery_app.celery_app") as mock_celery,
            patch("app.services.task_history.record_completed", return_value=None),
        ):
            mock_celery.control.revoke = MagicMock()
            resp = await superuser_client.post(f"/api/admin/tasks/{fake_task_id}/revoke")
        assert resp.status_code == 200
        assert resp.json()["status"] == "revoked"

    async def test_non_superuser_returns_403(self, admin_client: AsyncClient):
        resp = await admin_client.post(f"/api/admin/tasks/{uuid.uuid4()}/revoke")
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# POST /api/admin/purge-soft-deleted
# ---------------------------------------------------------------------------


class TestPurgeSoftDeleted:
    async def test_returns_200_and_queued_status(self, superuser_client: AsyncClient):
        with (
            patch("app.tasks.purge.purge_soft_deleted_records") as mock_task,
            patch("app.services.task_history.record_queued", return_value=None),
        ):
            mock_task.delay.return_value = MagicMock(id="fake-task-id")
            resp = await superuser_client.post("/api/admin/purge-soft-deleted")
        assert resp.status_code == 200
        assert resp.json()["status"] == "queued"

    async def test_non_superuser_returns_403(self, admin_client: AsyncClient):
        resp = await admin_client.post("/api/admin/purge-soft-deleted")
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /api/admin/worker-status
# ---------------------------------------------------------------------------


class TestWorkerStatus:
    async def test_returns_200(self, superuser_client: AsyncClient):
        with patch("app.celery_app.celery_app") as mock_celery:
            inspector = MagicMock()
            inspector.active.return_value = {}
            inspector.reserved.return_value = {}
            inspector.stats.return_value = {}
            mock_celery.control.inspect.return_value = inspector
            resp = await superuser_client.get("/api/admin/worker-status")
        assert resp.status_code == 200

    async def test_response_has_workers_and_queues(self, superuser_client: AsyncClient):
        with patch("app.celery_app.celery_app") as mock_celery:
            inspector = MagicMock()
            inspector.active.return_value = {}
            inspector.reserved.return_value = {}
            inspector.stats.return_value = {}
            mock_celery.control.inspect.return_value = inspector
            data = (await superuser_client.get("/api/admin/worker-status")).json()
        assert "workers" in data
        assert "queues" in data
        assert "api_version" in data

    async def test_no_workers_returns_offline_entry(self, superuser_client: AsyncClient):
        with patch("app.celery_app.celery_app") as mock_celery:
            inspector = MagicMock()
            inspector.active.return_value = {}
            inspector.reserved.return_value = {}
            inspector.stats.return_value = {}
            mock_celery.control.inspect.return_value = inspector
            data = (await superuser_client.get("/api/admin/worker-status")).json()
        assert any(w["status"] == "offline" for w in data["workers"])

    async def test_non_superuser_returns_403(self, admin_client: AsyncClient):
        resp = await admin_client.get("/api/admin/worker-status")
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# POST /api/admin/s3-audit/scan and GET /api/admin/s3-audit/task/{task_id}
# ---------------------------------------------------------------------------


class TestS3Audit:
    async def test_scan_returns_202_with_task_id(self, superuser_client: AsyncClient, superuser_user: User):
        with (
            patch("app.tasks.s3_audit.run_s3_orphan_scan") as mock_task,
            patch("app.services.task_history.record_queued", return_value=None),
        ):
            mock_task.delay.return_value = MagicMock(id="s3-task-abc")
            resp = await superuser_client.post("/api/admin/s3-audit/scan")
        assert resp.status_code == 202
        assert resp.json()["task_id"] == "s3-task-abc"

    async def test_scan_requires_superuser(self, admin_client: AsyncClient):
        resp = await admin_client.post("/api/admin/s3-audit/scan")
        assert resp.status_code == 403

    async def test_task_pending_state(self, superuser_client: AsyncClient, superuser_user: User):
        with patch("celery.result.AsyncResult") as mock_result_cls:
            mock_result_cls.return_value.state = "PENDING"
            resp = await superuser_client.get("/api/admin/s3-audit/task/fake-task-id")
        assert resp.status_code == 200
        assert resp.json()["status"] == "pending"

    async def test_task_running_state(self, superuser_client: AsyncClient, superuser_user: User):
        with patch("celery.result.AsyncResult") as mock_result_cls:
            mock_result_cls.return_value.state = "STARTED"
            resp = await superuser_client.get("/api/admin/s3-audit/task/fake-task-id")
        assert resp.json()["status"] == "running"

    async def test_task_failed_state(self, superuser_client: AsyncClient, superuser_user: User):
        with patch("celery.result.AsyncResult") as mock_result_cls:
            mock_result_cls.return_value.state = "FAILURE"
            mock_result_cls.return_value.result = RuntimeError("s3 gone")
            resp = await superuser_client.get("/api/admin/s3-audit/task/fake-task-id")
        assert resp.json()["status"] == "failed"

    async def test_summary_returns_200(self, superuser_client: AsyncClient, superuser_user: User):
        with patch("redis.from_url") as mock_from_url:
            mock_client = MagicMock()
            mock_from_url.return_value = mock_client
            mock_client.get.return_value = None
            resp = await superuser_client.get("/api/admin/s3-audit/summary")
        assert resp.status_code == 200

    async def test_summary_requires_superuser(self, admin_client: AsyncClient):
        resp = await admin_client.get("/api/admin/s3-audit/summary")
        assert resp.status_code == 403

    async def test_cleanup_returns_deleted_count(self, superuser_client: AsyncClient, superuser_user: User):
        with patch("app.services.storage._delete", MagicMock()):
            resp = await superuser_client.post(
                "/api/admin/s3-audit/cleanup", json={"keys": ["orphan/file1.jpg", "orphan/file2.jpg"]}
            )
        assert resp.status_code == 200
        assert resp.json()["deleted"] == 2

    async def test_cleanup_empty_keys_returns_zero(self, superuser_client: AsyncClient, superuser_user: User):
        resp = await superuser_client.post("/api/admin/s3-audit/cleanup", json={"keys": []})
        assert resp.status_code == 200
        assert resp.json()["deleted"] == 0


# ---------------------------------------------------------------------------
# POST /api/admin/cve-scan/start and GET /api/admin/cve-scan/task/{task_id}
# ---------------------------------------------------------------------------


class TestCveScan:
    async def test_start_returns_202_with_task_id(self, superuser_client: AsyncClient, superuser_user: User):
        with (
            patch("app.tasks.cve_scan.run_cve_scan") as mock_task,
            patch("app.services.task_history.record_queued", return_value=None),
        ):
            mock_task.delay.return_value = MagicMock(id="cve-task-abc")
            resp = await superuser_client.post("/api/admin/cve-scan/start", json={"frontend_deps": {}})
        assert resp.status_code == 202
        assert resp.json()["task_id"] == "cve-task-abc"

    async def test_start_requires_superuser(self, admin_client: AsyncClient):
        resp = await admin_client.post("/api/admin/cve-scan/start", json={"frontend_deps": {}})
        assert resp.status_code == 403

    async def test_task_pending_state(self, superuser_client: AsyncClient, superuser_user: User):
        with patch("celery.result.AsyncResult") as mock_result_cls:
            mock_result_cls.return_value.state = "PENDING"
            resp = await superuser_client.get("/api/admin/cve-scan/task/fake-cve-id")
        assert resp.json()["status"] == "pending"

    async def test_task_running_state(self, superuser_client: AsyncClient, superuser_user: User):
        with patch("celery.result.AsyncResult") as mock_result_cls:
            mock_result_cls.return_value.state = "STARTED"
            resp = await superuser_client.get("/api/admin/cve-scan/task/fake-cve-id")
        assert resp.json()["status"] == "running"

    async def test_summary_returns_200(self, superuser_client: AsyncClient, superuser_user: User):
        with patch("redis.from_url") as mock_from_url:
            mock_client = MagicMock()
            mock_from_url.return_value = mock_client
            mock_client.get.return_value = None
            resp = await superuser_client.get("/api/admin/cve-scan/summary")
        assert resp.status_code == 200

    async def test_summary_requires_superuser(self, admin_client: AsyncClient):
        resp = await admin_client.get("/api/admin/cve-scan/summary")
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# GET /api/admin/soft-delete-queue
# ---------------------------------------------------------------------------


class TestSoftDeleteQueue:
    async def test_requires_superuser(self, admin_client: AsyncClient):
        resp = await admin_client.get("/api/admin/soft-delete-queue")
        assert resp.status_code == 403

    async def test_requires_auth(self, client: AsyncClient):
        resp = await client.get("/api/admin/soft-delete-queue")
        assert resp.status_code == 401

    async def test_empty_queue_returns_zeros(self, superuser_client: AsyncClient, superuser_user: User):
        resp = await superuser_client.get("/api/admin/soft-delete-queue")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ready_to_purge"]["total"] == 0
        assert data["in_retention_window"]["total"] == 0
        assert data["retention_days"] > 0
        assert "cutoff" in data

    async def test_counts_ready_to_purge(
        self,
        superuser_client: AsyncClient,
        superuser_user: User,
        db_session: AsyncSession,
        test_user: User,
    ):
        old_cutoff = datetime.now(timezone.utc) - timedelta(days=400)
        draft = Draft(
            owner_id=test_user.id,
            name="Old draft",
            wif_filename="old.wif",
            wif_path="drafts/old.wif",
            deleted_at=old_cutoff,
        )
        db_session.add(draft)
        await db_session.commit()

        resp = await superuser_client.get("/api/admin/soft-delete-queue")
        assert resp.status_code == 200
        data = resp.json()
        assert data["ready_to_purge"]["drafts"] >= 1
        assert data["ready_to_purge"]["total"] >= 1
        assert data["in_retention_window"]["drafts"] == 0

    async def test_counts_in_retention_window(
        self,
        superuser_client: AsyncClient,
        superuser_user: User,
        db_session: AsyncSession,
        test_user: User,
    ):
        recent = datetime.now(timezone.utc) - timedelta(days=5)
        draft = Draft(
            owner_id=test_user.id,
            name="Recent draft",
            wif_filename="recent.wif",
            wif_path="drafts/recent.wif",
            deleted_at=recent,
        )
        db_session.add(draft)
        await db_session.commit()

        resp = await superuser_client.get("/api/admin/soft-delete-queue")
        assert resp.status_code == 200
        data = resp.json()
        assert data["in_retention_window"]["drafts"] >= 1
        assert data["in_retention_window"]["total"] >= 1
        assert data["ready_to_purge"]["drafts"] == 0

    async def test_non_deleted_records_not_counted(
        self,
        superuser_client: AsyncClient,
        superuser_user: User,
        db_session: AsyncSession,
        test_user: User,
    ):
        draft = Draft(
            owner_id=test_user.id,
            name="Active draft",
            wif_filename="active.wif",
            wif_path="drafts/active.wif",
        )
        db_session.add(draft)
        await db_session.commit()

        resp = await superuser_client.get("/api/admin/soft-delete-queue")
        data = resp.json()
        assert data["ready_to_purge"]["total"] == 0
        assert data["in_retention_window"]["total"] == 0


# ---------------------------------------------------------------------------
# GET /api/admin/deletion-queue
# ---------------------------------------------------------------------------


class TestDeletionQueue:
    async def test_requires_superuser(self, admin_client: AsyncClient):
        resp = await admin_client.get("/api/admin/deletion-queue")
        assert resp.status_code == 403

    async def test_requires_auth(self, client: AsyncClient):
        resp = await client.get("/api/admin/deletion-queue")
        assert resp.status_code == 401

    async def test_empty_when_no_deletions(self, superuser_client: AsyncClient, superuser_user: User):
        resp = await superuser_client.get("/api/admin/deletion-queue")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_returns_users_in_deletion_pipeline(
        self,
        superuser_client: AsyncClient,
        superuser_user: User,
        db_session: AsyncSession,
        test_user: User,
    ):
        test_user.deletion_state = "pending"
        test_user.deletion_initiated_at = datetime.now(timezone.utc)
        db_session.add(test_user)
        await db_session.commit()

        resp = await superuser_client.get("/api/admin/deletion-queue")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["deletion_state"] == "pending"
        assert data[0]["email"] == test_user.email

    async def test_excludes_users_without_deletion_state(
        self,
        superuser_client: AsyncClient,
        superuser_user: User,
        db_session: AsyncSession,
        test_user: User,
    ):
        assert test_user.deletion_state is None
        resp = await superuser_client.get("/api/admin/deletion-queue")
        assert resp.json() == []

    async def test_ordered_by_initiated_at_desc(
        self,
        superuser_client: AsyncClient,
        superuser_user: User,
        db_session: AsyncSession,
        test_user: User,
        admin_user: User,
    ):
        now = datetime.now(timezone.utc)
        test_user.deletion_state = "pending"
        test_user.deletion_initiated_at = now - timedelta(hours=2)
        admin_user.deletion_state = "in_progress"
        admin_user.deletion_initiated_at = now
        db_session.add_all([test_user, admin_user])
        await db_session.commit()

        resp = await superuser_client.get("/api/admin/deletion-queue")
        data = resp.json()
        assert len(data) == 2
        assert data[0]["deletion_state"] == "in_progress"
        assert data[1]["deletion_state"] == "pending"

    async def test_stalled_state_included(
        self,
        superuser_client: AsyncClient,
        superuser_user: User,
        db_session: AsyncSession,
        test_user: User,
    ):
        test_user.deletion_state = "stalled"
        test_user.deletion_initiated_at = datetime.now(timezone.utc)
        db_session.add(test_user)
        await db_session.commit()

        resp = await superuser_client.get("/api/admin/deletion-queue")
        data = resp.json()
        assert len(data) == 1
        assert data[0]["deletion_state"] == "stalled"


class TestSandbox:
    async def test_sentry_test_returns_captured(self, superuser_client: AsyncClient, superuser_user: User):
        resp = await superuser_client.post("/api/admin/sandbox/sentry-test")
        assert resp.status_code == 200
        data = resp.json()
        assert data["captured"] is True
        assert "event_id" in data

    async def test_sentry_test_requires_superuser(self, admin_client: AsyncClient):
        resp = await admin_client.post("/api/admin/sandbox/sentry-test")
        assert resp.status_code == 403

    async def test_sentry_test_requires_auth(self, client: AsyncClient):
        resp = await client.post("/api/admin/sandbox/sentry-test")
        assert resp.status_code in (401, 403)
