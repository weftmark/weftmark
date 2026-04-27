import uuid
from datetime import datetime, timedelta, timezone

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.invite import Invite
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

    async def test_grants_admin(self, admin_client: AsyncClient, db_session: AsyncSession):
        other = await self._create_other_user(db_session)
        resp = await admin_client.patch(f"/api/admin/users/{other.id}", json={"is_admin": True})
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
