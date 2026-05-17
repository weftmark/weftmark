from datetime import date, datetime, timedelta, timezone

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit_log import AuditLog
from app.models.draft import Draft
from app.models.loom import Loom, LoomVersion, LoomVersionPhoto, LoomVersionReceipt
from app.models.project import Project, ProjectPhoto, ProjectStep
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

    async def test_show_version_numbers_defaults_false(self, auth_client: AsyncClient):
        resp = await auth_client.get("/api/users/me")
        assert resp.status_code == 200
        assert resp.json()["show_version_numbers"] is False

    async def test_update_show_version_numbers_false(self, auth_client: AsyncClient):
        resp = await auth_client.patch("/api/users/me", json={"show_version_numbers": False})
        assert resp.status_code == 200
        assert resp.json()["show_version_numbers"] is False

    async def test_update_show_version_numbers_true(self, auth_client: AsyncClient):
        resp = await auth_client.patch("/api/users/me", json={"show_version_numbers": True})
        assert resp.status_code == 200
        assert resp.json()["show_version_numbers"] is True

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

    async def test_revokes_shared_drafts_when_consent_revoked(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        draft = Draft(
            owner_id=test_user.id,
            name="Shared Draft",
            wif_filename="s.wif",
            wif_path="drafts/s/original.wif",
            is_shared=True,
        )
        db_session.add(draft)
        await db_session.commit()

        resp = await auth_client.patch("/api/users/me", json={"ai_training_consent": False})
        assert resp.status_code == 200
        await db_session.refresh(draft)
        assert draft.is_shared is False


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
            wif_path="drafts/test/original.wif",
        )
        db_session.add(draft)
        await db_session.commit()

        await auth_client.request("DELETE", "/api/users/me", json={"confirm": "DELETE MY ACCOUNT"})
        result = await db_session.scalar(select(Draft).where(Draft.owner_id == test_user.id))
        assert result is None

    async def test_deletes_projects_and_steps(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        draft = Draft(
            owner_id=test_user.id,
            name="P",
            wif_filename="x.wif",
            wif_path="drafts/x/original.wif",
        )
        db_session.add(draft)
        await db_session.flush()

        project = Project(
            owner_id=test_user.id,
            draft_id=draft.id,
            name="Test Project",
            project_type="treadle",
            status="active",
            current_pick=1,
            total_picks=100,
        )
        db_session.add(project)
        await db_session.flush()

        step = ProjectStep(
            project_id=project.id,
            event_type="advance",
            from_pick=1,
            to_pick=2,
        )
        db_session.add(step)
        await db_session.commit()

        project_id = project.id
        await auth_client.request("DELETE", "/api/users/me", json={"confirm": "DELETE MY ACCOUNT"})

        assert await db_session.scalar(select(Project).where(Project.id == project_id)) is None
        assert await db_session.scalar(select(ProjectStep).where(ProjectStep.project_id == project_id)) is None

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

    async def test_purges_project_photos(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User, mock_storage: dict
    ):
        draft = Draft(
            owner_id=test_user.id,
            name="D",
            wif_filename="d.wif",
            wif_path="drafts/d/original.wif",
        )
        db_session.add(draft)
        await db_session.flush()

        project = Project(
            owner_id=test_user.id,
            draft_id=draft.id,
            name="P",
            project_type="treadle",
            status="active",
            current_pick=1,
            total_picks=10,
        )
        db_session.add(project)
        await db_session.flush()

        photo_path = f"projects/{project.id}/photo1.jpg"
        mock_storage[photo_path] = b"fake-image"
        photo = ProjectPhoto(project_id=project.id, file_path=photo_path, filename="photo1.jpg")
        db_session.add(photo)
        await db_session.commit()

        await auth_client.request("DELETE", "/api/users/me", json={"confirm": "DELETE MY ACCOUNT"})
        assert photo_path not in mock_storage

    async def test_purges_yarn_photo(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User, mock_storage: dict
    ):
        photo_path = f"yarns/{test_user.id}/photo.jpg"
        mock_storage[photo_path] = b"fake-image"
        yarn = Yarn(owner_id=test_user.id, brand="Brand", name="Yarn", photo_path=photo_path)
        db_session.add(yarn)
        await db_session.commit()

        await auth_client.request("DELETE", "/api/users/me", json={"confirm": "DELETE MY ACCOUNT"})
        assert photo_path not in mock_storage

    async def test_purges_loom_photo_and_version_assets(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User, mock_storage: dict
    ):
        loom_photo = f"looms/{test_user.id}/cover.jpg"
        mock_storage[loom_photo] = b"loom-img"
        loom = Loom(
            owner_id=test_user.id,
            manufacturer="Ashford",
            model_name="Rigid Heddle",
            loom_type="rigid_heddle",
            photo_path=loom_photo,
        )
        db_session.add(loom)
        await db_session.flush()

        version = LoomVersion(
            loom_id=loom.id,
            version_number=1,
            effective_date=date(2024, 1, 1),
        )
        db_session.add(version)
        await db_session.flush()

        vp_path = f"looms/{loom.id}/v1/photo.jpg"
        vr_path = f"looms/{loom.id}/v1/receipt.pdf"
        mock_storage[vp_path] = b"vp"
        mock_storage[vr_path] = b"vr"
        vp = LoomVersionPhoto(loom_version_id=version.id, filename="photo.jpg", path=vp_path)
        vr = LoomVersionReceipt(loom_version_id=version.id, filename="receipt.pdf", path=vr_path)
        db_session.add_all([vp, vr])
        await db_session.commit()

        await auth_client.request("DELETE", "/api/users/me", json={"confirm": "DELETE MY ACCOUNT"})
        assert loom_photo not in mock_storage
        assert vp_path not in mock_storage
        assert vr_path not in mock_storage

    async def test_purges_draft_preview(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User, mock_storage: dict
    ):
        wif_path = "drafts/d2/original.wif"
        preview_path = "drafts/d2/preview.png"
        mock_storage[wif_path] = b"wif-data"
        mock_storage[preview_path] = b"png-data"
        draft = Draft(
            owner_id=test_user.id,
            name="D2",
            wif_filename="d2.wif",
            wif_path=wif_path,
            preview_path=preview_path,
        )
        db_session.add(draft)
        await db_session.commit()

        await auth_client.request("DELETE", "/api/users/me", json={"confirm": "DELETE MY ACCOUNT"})
        assert wif_path not in mock_storage
        assert preview_path not in mock_storage


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


# ---------------------------------------------------------------------------
# GET /api/users/me/activity-heatmap
# ---------------------------------------------------------------------------


class TestActivityHeatmap:
    async def test_returns_200_with_days_key(self, auth_client: AsyncClient):
        resp = await auth_client.get("/api/users/me/activity-heatmap")
        assert resp.status_code == 200
        assert "days" in resp.json()

    async def test_empty_when_no_steps(self, auth_client: AsyncClient):
        resp = await auth_client.get("/api/users/me/activity-heatmap")
        assert resp.json()["days"] == []

    async def test_counts_steps_on_a_day(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = Draft(
            owner_id=test_user.id,
            name="Heatmap Draft",
            wif_filename="h.wif",
            wif_path="drafts/h/original.wif",
        )
        db_session.add(draft)
        await db_session.flush()

        project = Project(
            owner_id=test_user.id,
            draft_id=draft.id,
            name="Heatmap Project",
            project_type="treadle",
            status="active",
            current_pick=1,
            total_picks=10,
        )
        db_session.add(project)
        await db_session.flush()

        today = datetime.now(timezone.utc).replace(hour=12, minute=0, second=0, microsecond=0)
        for _ in range(3):
            db_session.add(
                ProjectStep(
                    project_id=project.id,
                    event_type="advance",
                    from_pick=1,
                    to_pick=2,
                    created_at=today,
                )
            )
        await db_session.commit()

        resp = await auth_client.get("/api/users/me/activity-heatmap")
        days = resp.json()["days"]
        assert len(days) == 1
        assert days[0]["count"] == 3
        assert days[0]["date"] == today.strftime("%Y-%m-%d")

    async def test_multiple_days_returned_separately(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        draft = Draft(
            owner_id=test_user.id,
            name="Multi Draft",
            wif_filename="m.wif",
            wif_path="drafts/m/original.wif",
        )
        db_session.add(draft)
        await db_session.flush()

        project = Project(
            owner_id=test_user.id,
            draft_id=draft.id,
            name="Multi Project",
            project_type="treadle",
            status="active",
            current_pick=1,
            total_picks=10,
        )
        db_session.add(project)
        await db_session.flush()

        now = datetime.now(timezone.utc)
        day1 = now.replace(hour=12, minute=0, second=0, microsecond=0)
        day2 = (now - timedelta(days=1)).replace(hour=12, minute=0, second=0, microsecond=0)
        db_session.add(
            ProjectStep(project_id=project.id, event_type="advance", from_pick=1, to_pick=2, created_at=day1)
        )
        db_session.add(
            ProjectStep(project_id=project.id, event_type="advance", from_pick=2, to_pick=3, created_at=day2)
        )
        db_session.add(
            ProjectStep(project_id=project.id, event_type="advance", from_pick=3, to_pick=4, created_at=day2)
        )
        await db_session.commit()

        resp = await auth_client.get("/api/users/me/activity-heatmap")
        days = {d["date"]: d["count"] for d in resp.json()["days"]}
        assert days[day1.strftime("%Y-%m-%d")] == 1
        assert days[day2.strftime("%Y-%m-%d")] == 2

    async def test_excludes_other_users_steps(
        self, auth_client: AsyncClient, db_session: AsyncSession, admin_user: User
    ):
        draft = Draft(
            owner_id=admin_user.id,
            name="Admin Draft",
            wif_filename="a.wif",
            wif_path="drafts/a/original.wif",
        )
        db_session.add(draft)
        await db_session.flush()

        project = Project(
            owner_id=admin_user.id,
            draft_id=draft.id,
            name="Admin Project",
            project_type="treadle",
            status="active",
            current_pick=1,
            total_picks=10,
        )
        db_session.add(project)
        await db_session.flush()

        db_session.add(
            ProjectStep(
                project_id=project.id,
                event_type="advance",
                from_pick=1,
                to_pick=2,
                created_at=datetime.now(timezone.utc),
            )
        )
        await db_session.commit()

        resp = await auth_client.get("/api/users/me/activity-heatmap")
        assert resp.json()["days"] == []

    async def test_excludes_steps_older_than_366_days(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        draft = Draft(
            owner_id=test_user.id,
            name="Old Draft",
            wif_filename="o.wif",
            wif_path="drafts/o/original.wif",
        )
        db_session.add(draft)
        await db_session.flush()

        project = Project(
            owner_id=test_user.id,
            draft_id=draft.id,
            name="Old Project",
            project_type="treadle",
            status="active",
            current_pick=1,
            total_picks=10,
        )
        db_session.add(project)
        await db_session.flush()

        old_date = datetime.now(timezone.utc) - timedelta(days=400)
        db_session.add(
            ProjectStep(
                project_id=project.id,
                event_type="advance",
                from_pick=1,
                to_pick=2,
                created_at=old_date,
            )
        )
        await db_session.commit()

        resp = await auth_client.get("/api/users/me/activity-heatmap")
        assert resp.json()["days"] == []

    async def test_unauthenticated_returns_401(self, client: AsyncClient):
        resp = await client.get("/api/users/me/activity-heatmap")
        assert resp.status_code == 401

    async def test_returns_earliest_activity_date(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        draft = Draft(owner_id=test_user.id, name="E Draft", wif_filename="e.wif", wif_path="drafts/e/original.wif")
        db_session.add(draft)
        await db_session.flush()
        project = Project(
            owner_id=test_user.id,
            draft_id=draft.id,
            name="E Project",
            project_type="treadle",
            status="active",
            current_pick=1,
            total_picks=10,
        )
        db_session.add(project)
        await db_session.flush()
        step_dt = datetime.now(timezone.utc).replace(hour=12, minute=0, second=0, microsecond=0)
        db_session.add(
            ProjectStep(project_id=project.id, event_type="advance", from_pick=1, to_pick=2, created_at=step_dt)
        )
        await db_session.commit()

        resp = await auth_client.get("/api/users/me/activity-heatmap")
        assert resp.json()["earliest_activity_date"] == step_dt.strftime("%Y-%m-%d")

    async def test_earliest_activity_date_null_when_no_steps(self, auth_client: AsyncClient):
        resp = await auth_client.get("/api/users/me/activity-heatmap")
        assert resp.json()["earliest_activity_date"] is None

    async def test_returns_years_with_activity(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        draft = Draft(owner_id=test_user.id, name="Y Draft", wif_filename="y.wif", wif_path="drafts/y/original.wif")
        db_session.add(draft)
        await db_session.flush()
        project = Project(
            owner_id=test_user.id,
            draft_id=draft.id,
            name="Y Project",
            project_type="treadle",
            status="active",
            current_pick=1,
            total_picks=10,
        )
        db_session.add(project)
        await db_session.flush()
        step_dt = datetime.now(timezone.utc).replace(hour=12, minute=0, second=0, microsecond=0)
        db_session.add(
            ProjectStep(project_id=project.id, event_type="advance", from_pick=1, to_pick=2, created_at=step_dt)
        )
        await db_session.commit()

        resp = await auth_client.get("/api/users/me/activity-heatmap")
        current_year = datetime.now(timezone.utc).year
        assert current_year in resp.json()["years_with_activity"]

    async def test_year_param_filters_to_calendar_year(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        draft = Draft(owner_id=test_user.id, name="YP Draft", wif_filename="yp.wif", wif_path="drafts/yp/original.wif")
        db_session.add(draft)
        await db_session.flush()
        project = Project(
            owner_id=test_user.id,
            draft_id=draft.id,
            name="YP Project",
            project_type="treadle",
            status="active",
            current_pick=1,
            total_picks=10,
        )
        db_session.add(project)
        await db_session.flush()

        this_year = datetime.now(timezone.utc).year
        last_year = this_year - 1
        dt_this = datetime(this_year, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
        dt_last = datetime(last_year, 6, 15, 12, 0, 0, tzinfo=timezone.utc)
        db_session.add(
            ProjectStep(project_id=project.id, event_type="advance", from_pick=1, to_pick=2, created_at=dt_this)
        )
        db_session.add(
            ProjectStep(project_id=project.id, event_type="advance", from_pick=2, to_pick=3, created_at=dt_last)
        )
        await db_session.commit()

        resp = await auth_client.get(f"/api/users/me/activity-heatmap?year={last_year}")
        dates = {d["date"] for d in resp.json()["days"]}
        assert f"{last_year}-06-15" in dates
        assert f"{this_year}-06-15" not in dates

    async def test_days_include_project_list(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = Draft(owner_id=test_user.id, name="PL Draft", wif_filename="pl.wif", wif_path="drafts/pl/original.wif")
        db_session.add(draft)
        await db_session.flush()
        project = Project(
            owner_id=test_user.id,
            draft_id=draft.id,
            name="PL Project",
            project_type="treadle",
            status="active",
            current_pick=1,
            total_picks=10,
        )
        db_session.add(project)
        await db_session.flush()
        step_dt = datetime.now(timezone.utc).replace(hour=12, minute=0, second=0, microsecond=0)
        db_session.add(
            ProjectStep(project_id=project.id, event_type="advance", from_pick=1, to_pick=2, created_at=step_dt)
        )
        await db_session.commit()

        resp = await auth_client.get("/api/users/me/activity-heatmap")
        day = resp.json()["days"][0]
        assert len(day["projects"]) == 1
        assert day["projects"][0]["name"] == "PL Project"
        assert day["projects"][0]["step_count"] == 1
        assert "id" in day["projects"][0]
