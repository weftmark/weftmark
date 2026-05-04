from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity import Activity, ActivityStep
from app.models.audit_log import AuditLog
from app.models.draft import Draft
from app.models.user import User
from app.models.user_identity import UserIdentity
from app.models.yarn import Skein, Yarn
from tests.conftest import SEEDED_EULA_VERSION

# ---------------------------------------------------------------------------
# GET /api/users/me
# ---------------------------------------------------------------------------


class TestGetSettings:
    async def test_returns_200(self, auth_client: AsyncClient):
        resp = await auth_client.get("/api/users/me")
        assert resp.status_code == 200

    async def test_returns_expected_fields(self, auth_client: AsyncClient, test_user: User):
        resp = await auth_client.get("/api/users/me")
        data = resp.json()
        assert data["email"] == test_user.email
        assert data["display_name"] == test_user.display_name
        assert "theme" in data
        assert "activity_theme" in data
        assert "measurement_system" in data
        assert "ai_training_consent" in data
        assert "eula_accepted_version" in data
        assert data["current_eula_version"] == SEEDED_EULA_VERSION

    async def test_unauthenticated_returns_401(self, client: AsyncClient):
        resp = await client.get("/api/users/me")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# PATCH /api/users/me
# ---------------------------------------------------------------------------


class TestUpdateSettings:
    async def test_update_display_name(self, auth_client: AsyncClient):
        resp = await auth_client.patch("/api/users/me", json={"display_name": "New Name"})
        assert resp.status_code == 200
        assert resp.json()["display_name"] == "New Name"

    async def test_update_theme_dark(self, auth_client: AsyncClient):
        resp = await auth_client.patch("/api/users/me", json={"theme": "dark"})
        assert resp.status_code == 200
        assert resp.json()["theme"] == "dark"

    async def test_update_theme_light(self, auth_client: AsyncClient):
        resp = await auth_client.patch("/api/users/me", json={"theme": "light"})
        assert resp.status_code == 200
        assert resp.json()["theme"] == "light"

    async def test_invalid_theme_returns_422(self, auth_client: AsyncClient):
        resp = await auth_client.patch("/api/users/me", json={"theme": "rainbow"})
        assert resp.status_code == 422

    async def test_update_activity_theme(self, auth_client: AsyncClient):
        resp = await auth_client.patch("/api/users/me", json={"activity_theme": "compact"})
        assert resp.status_code == 200
        assert resp.json()["activity_theme"] == "compact"

    async def test_invalid_activity_theme_returns_422(self, auth_client: AsyncClient):
        resp = await auth_client.patch("/api/users/me", json={"activity_theme": "neon"})
        assert resp.status_code == 422

    async def test_update_measurement_system_imperial(self, auth_client: AsyncClient):
        resp = await auth_client.patch("/api/users/me", json={"measurement_system": "imperial"})
        assert resp.status_code == 200
        assert resp.json()["measurement_system"] == "imperial"

    async def test_invalid_measurement_system_returns_422(self, auth_client: AsyncClient):
        resp = await auth_client.patch("/api/users/me", json={"measurement_system": "furlongs"})
        assert resp.status_code == 422

    async def test_update_idle_timeout(self, auth_client: AsyncClient):
        resp = await auth_client.patch("/api/users/me", json={"idle_timeout_minutes": 60})
        assert resp.status_code == 200
        assert resp.json()["idle_timeout_minutes"] == 60

    async def test_invalid_idle_timeout_returns_422(self, auth_client: AsyncClient):
        resp = await auth_client.patch("/api/users/me", json={"idle_timeout_minutes": 45})
        assert resp.status_code == 422

    async def test_update_ai_training_consent_true(self, auth_client: AsyncClient):
        resp = await auth_client.patch("/api/users/me", json={"ai_training_consent": True})
        assert resp.status_code == 200
        assert resp.json()["ai_training_consent"] is True

    async def test_update_ai_training_consent_false(self, auth_client: AsyncClient):
        resp = await auth_client.patch("/api/users/me", json={"ai_training_consent": False})
        assert resp.status_code == 200
        assert resp.json()["ai_training_consent"] is False

    async def test_empty_display_name_returns_422(self, auth_client: AsyncClient):
        resp = await auth_client.patch("/api/users/me", json={"display_name": "   "})
        assert resp.status_code == 422

    async def test_unauthenticated_returns_401(self, client: AsyncClient):
        resp = await client.patch("/api/users/me", json={"theme": "dark"})
        assert resp.status_code == 401

    async def test_persists_to_db(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        await auth_client.patch("/api/users/me", json={"theme": "dark"})
        await db_session.refresh(test_user)
        assert test_user.theme == "dark"


# ---------------------------------------------------------------------------
# DELETE /api/users/me
# ---------------------------------------------------------------------------


class TestDeleteAccount:
    async def test_wrong_confirm_string_returns_422(self, auth_client: AsyncClient):
        resp = await auth_client.request("DELETE", "/api/users/me", json={"confirm": "yes please"})
        assert resp.status_code == 422

    async def test_correct_confirm_returns_204(self, auth_client: AsyncClient):
        resp = await auth_client.request("DELETE", "/api/users/me", json={"confirm": "DELETE MY ACCOUNT"})
        assert resp.status_code == 204

    async def test_user_removed_from_db(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        user_id = test_user.id
        await auth_client.request("DELETE", "/api/users/me", json={"confirm": "DELETE MY ACCOUNT"})
        result = await db_session.scalar(select(User).where(User.id == user_id))
        assert result is None

    async def test_unauthenticated_returns_401(self, client: AsyncClient):
        resp = await client.request("DELETE", "/api/users/me", json={"confirm": "DELETE MY ACCOUNT"})
        assert resp.status_code == 401

    async def test_deletes_user_identities(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        identity = UserIdentity(
            user_id=test_user.id,
            provider="google",
            provider_sub="sub-abc-123",
        )
        db_session.add(identity)
        await db_session.commit()

        await auth_client.request("DELETE", "/api/users/me", json={"confirm": "DELETE MY ACCOUNT"})
        result = await db_session.scalar(select(UserIdentity).where(UserIdentity.user_id == test_user.id))
        assert result is None

    async def test_deletes_drafts(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = Draft(
            owner_id=test_user.id,
            name="Test Draft",
            wif_filename="test.wif",
            wif_path="projects/test/original.wif",
        )
        db_session.add(draft)
        await db_session.commit()

        await auth_client.request("DELETE", "/api/users/me", json={"confirm": "DELETE MY ACCOUNT"})
        result = await db_session.scalar(select(Draft).where(Draft.owner_id == test_user.id))
        assert result is None

    async def test_deletes_activities_and_steps(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        draft = Draft(
            owner_id=test_user.id,
            name="P",
            wif_filename="x.wif",
            wif_path="projects/x/original.wif",
        )
        db_session.add(draft)
        await db_session.flush()

        activity = Activity(
            owner_id=test_user.id,
            draft_id=draft.id,
            name="Test Activity",
            activity_type="treadle",
            status="active",
            current_pick=1,
            total_picks=100,
        )
        db_session.add(activity)
        await db_session.flush()

        step = ActivityStep(
            activity_id=activity.id,
            event_type="advance",
            from_pick=1,
            to_pick=2,
        )
        db_session.add(step)
        await db_session.commit()

        activity_id = activity.id
        await auth_client.request("DELETE", "/api/users/me", json={"confirm": "DELETE MY ACCOUNT"})

        assert await db_session.scalar(select(Activity).where(Activity.id == activity_id)) is None
        assert await db_session.scalar(select(ActivityStep).where(ActivityStep.activity_id == activity_id)) is None

    async def test_deletes_yarn_and_skeins(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        yarn = Yarn(
            owner_id=test_user.id,
            brand="Ashford",
            name="Merino",
        )
        db_session.add(yarn)
        await db_session.flush()

        skein = Skein(yarn_id=yarn.id, status="available")
        db_session.add(skein)
        await db_session.commit()

        yarn_id = yarn.id
        await auth_client.request("DELETE", "/api/users/me", json={"confirm": "DELETE MY ACCOUNT"})

        assert await db_session.scalar(select(Yarn).where(Yarn.id == yarn_id)) is None
        assert await db_session.scalar(select(Skein).where(Skein.yarn_id == yarn_id)) is None


# ---------------------------------------------------------------------------
# POST /api/users/me/eula
# ---------------------------------------------------------------------------


class TestAcceptEula:
    async def test_returns_200(self, auth_client: AsyncClient):
        resp = await auth_client.post("/api/users/me/eula", json={"version": SEEDED_EULA_VERSION})
        assert resp.status_code == 200

    async def test_sets_accepted_version_on_user(
        self, auth_client: AsyncClient, test_user: User, db_session: AsyncSession
    ):
        await auth_client.post("/api/users/me/eula", json={"version": SEEDED_EULA_VERSION})
        await db_session.refresh(test_user)
        assert test_user.eula_accepted_version == SEEDED_EULA_VERSION
        assert test_user.eula_accepted_at is not None

    async def test_writes_audit_log_entry(self, auth_client: AsyncClient, test_user: User, db_session: AsyncSession):
        await auth_client.post("/api/users/me/eula", json={"version": SEEDED_EULA_VERSION})
        entry = await db_session.scalar(
            select(AuditLog).where(
                AuditLog.actor_email == test_user.email,
                AuditLog.event_type == "eula.accepted",
            )
        )
        assert entry is not None
        assert entry.details == {"version": SEEDED_EULA_VERSION}

    async def test_each_acceptance_produces_separate_audit_entry(
        self, auth_client: AsyncClient, test_user: User, db_session: AsyncSession
    ):
        await auth_client.post("/api/users/me/eula", json={"version": SEEDED_EULA_VERSION})
        await auth_client.post("/api/users/me/eula", json={"version": SEEDED_EULA_VERSION})
        entries = list(
            await db_session.scalars(
                select(AuditLog).where(
                    AuditLog.actor_email == test_user.email,
                    AuditLog.event_type == "eula.accepted",
                )
            )
        )
        assert len(entries) == 2

    async def test_version_mismatch_returns_422(self, auth_client: AsyncClient):
        resp = await auth_client.post("/api/users/me/eula", json={"version": "0.0"})
        assert resp.status_code == 422

    async def test_unauthenticated_returns_401(self, raw_client: AsyncClient):
        resp = await raw_client.post("/api/users/me/eula", json={"version": SEEDED_EULA_VERSION})
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/users/me/data-export
# ---------------------------------------------------------------------------


class TestDataExport:
    async def test_returns_200(self, auth_client: AsyncClient):
        resp = await auth_client.get("/api/users/me/data-export")
        assert resp.status_code == 200

    async def test_returns_not_implemented_status(self, auth_client: AsyncClient):
        data = (await auth_client.get("/api/users/me/data-export")).json()
        assert data["status"] == "not_implemented"
        assert data["milestone"] == "2"

    async def test_unauthenticated_returns_401(self, client: AsyncClient):
        resp = await client.get("/api/users/me/data-export")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# /auth/me — verify new fields are present after migration
# ---------------------------------------------------------------------------


class TestAuthMeNewFields:
    async def test_includes_eula_fields(self, auth_client: AsyncClient):
        data = (await auth_client.get("/auth/me")).json()
        assert "eula_accepted_version" in data
        assert "current_eula_version" in data
        assert data["current_eula_version"] == SEEDED_EULA_VERSION

    async def test_includes_measurement_system(self, auth_client: AsyncClient):
        data = (await auth_client.get("/auth/me")).json()
        assert "measurement_system" in data

    async def test_includes_activity_theme(self, auth_client: AsyncClient):
        data = (await auth_client.get("/auth/me")).json()
        assert "activity_theme" in data

    async def test_includes_ai_training_consent(self, auth_client: AsyncClient):
        data = (await auth_client.get("/auth/me")).json()
        assert "ai_training_consent" in data


# ---------------------------------------------------------------------------
# GET /api/eula/current
# ---------------------------------------------------------------------------


class TestGetCurrentEula:
    async def test_returns_200_unauthenticated(self, client: AsyncClient):
        resp = await client.get("/api/eula/current")
        assert resp.status_code == 200

    async def test_returns_version(self, client: AsyncClient):
        data = (await client.get("/api/eula/current")).json()
        assert data["version"] == SEEDED_EULA_VERSION

    async def test_returns_body_html(self, client: AsyncClient):
        data = (await client.get("/api/eula/current")).json()
        assert "body_html" in data
        assert len(data["body_html"]) > 0

    async def test_returns_effective_date(self, client: AsyncClient):
        data = (await client.get("/api/eula/current")).json()
        assert "effective_date" in data
