"""Tests for project yarn-color linking endpoints."""

import uuid

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.draft import Draft
from app.models.project import Project, ProjectYarnColor
from app.models.user import User
from app.models.yarn import Yarn

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _make_draft(db: AsyncSession, owner_id: uuid.UUID) -> Draft:
    draft = Draft(
        owner_id=owner_id,
        name="Test Draft",
        wif_filename="test.wif",
        wif_path="drafts/test/original.wif",
        drawdown_preview_path="fake/preview.png",
    )
    db.add(draft)
    await db.flush()
    return draft


async def _make_project(db: AsyncSession, owner_id: uuid.UUID, draft_id: uuid.UUID) -> Project:
    project = Project(
        owner_id=owner_id,
        draft_id=draft_id,
        name="Test Project",
        project_type="treadle",
        status="created",
        total_picks=10,
    )
    db.add(project)
    await db.flush()
    return project


async def _make_yarn(db: AsyncSession, owner_id: uuid.UUID, color_hex: str = "#aa3322") -> Yarn:
    yarn = Yarn(
        owner_id=owner_id,
        brand="TestBrand",
        name="TestYarn",
        color_hex=color_hex,
        color_name="rust",
    )
    db.add(yarn)
    await db.flush()
    return yarn


# ---------------------------------------------------------------------------
# PUT /api/projects/{id}/yarn-colors/{color_hex}
# ---------------------------------------------------------------------------


class TestLinkYarnColor:
    async def test_link_creates_record(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _make_draft(db_session, test_user.id)
        project = await _make_project(db_session, test_user.id, draft.id)
        yarn = await _make_yarn(db_session, test_user.id)
        await db_session.commit()

        resp = await auth_client.put(
            f"/api/projects/{project.id}/yarn-colors/%23aa3322",
            json={"yarn_id": str(yarn.id), "color_hex": "#aa3322"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["yarn_id"] == str(yarn.id)
        assert data["color_hex"] == "#aa3322"
        assert data["yarn_name"] == "TestYarn"
        assert data["yarn_brand"] == "TestBrand"

    async def test_link_updates_existing(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _make_draft(db_session, test_user.id)
        project = await _make_project(db_session, test_user.id, draft.id)
        yarn1 = await _make_yarn(db_session, test_user.id, "#111111")
        yarn2 = await _make_yarn(db_session, test_user.id, "#222222")
        await db_session.commit()

        await auth_client.put(
            f"/api/projects/{project.id}/yarn-colors/%23111111",
            json={"yarn_id": str(yarn1.id), "color_hex": "#111111"},
        )
        resp = await auth_client.put(
            f"/api/projects/{project.id}/yarn-colors/%23111111",
            json={"yarn_id": str(yarn2.id), "color_hex": "#111111"},
        )
        assert resp.status_code == 200
        assert resp.json()["yarn_id"] == str(yarn2.id)

    async def test_link_404_yarn_not_found(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _make_draft(db_session, test_user.id)
        project = await _make_project(db_session, test_user.id, draft.id)
        await db_session.commit()

        resp = await auth_client.put(
            f"/api/projects/{project.id}/yarn-colors/%23ffffff",
            json={"yarn_id": str(uuid.uuid4()), "color_hex": "#ffffff"},
        )
        assert resp.status_code == 404

    async def test_link_404_project_not_found(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        yarn = await _make_yarn(db_session, test_user.id)
        await db_session.commit()

        resp = await auth_client.put(
            f"/api/projects/{uuid.uuid4()}/yarn-colors/%23ffffff",
            json={"yarn_id": str(yarn.id), "color_hex": "#ffffff"},
        )
        assert resp.status_code == 404

    async def test_link_rejects_other_users_project(
        self,
        auth_client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
        admin_user: User,
    ):
        draft = await _make_draft(db_session, admin_user.id)
        project = await _make_project(db_session, admin_user.id, draft.id)
        yarn = await _make_yarn(db_session, test_user.id)
        await db_session.commit()

        resp = await auth_client.put(
            f"/api/projects/{project.id}/yarn-colors/%23aa3322",
            json={"yarn_id": str(yarn.id), "color_hex": "#aa3322"},
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /api/projects/{id}/yarn-colors/{color_hex}
# ---------------------------------------------------------------------------


class TestUnlinkYarnColor:
    async def test_unlink_removes_record(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _make_draft(db_session, test_user.id)
        project = await _make_project(db_session, test_user.id, draft.id)
        yarn = await _make_yarn(db_session, test_user.id)
        pyc = ProjectYarnColor(project_id=project.id, yarn_id=yarn.id, color_hex="#aa3322")
        db_session.add(pyc)
        await db_session.commit()

        resp = await auth_client.delete(f"/api/projects/{project.id}/yarn-colors/%23aa3322")
        assert resp.status_code == 204

        row = await db_session.get(ProjectYarnColor, pyc.id)
        assert row is None

    async def test_unlink_404_when_not_linked(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        draft = await _make_draft(db_session, test_user.id)
        project = await _make_project(db_session, test_user.id, draft.id)
        await db_session.commit()

        resp = await auth_client.delete(f"/api/projects/{project.id}/yarn-colors/%23ffffff")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/projects/{id}/yarn-colors
# ---------------------------------------------------------------------------


class TestListProjectYarnColors:
    async def test_list_returns_linked_yarn(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _make_draft(db_session, test_user.id)
        project = await _make_project(db_session, test_user.id, draft.id)
        yarn = await _make_yarn(db_session, test_user.id)
        db_session.add(ProjectYarnColor(project_id=project.id, yarn_id=yarn.id, color_hex="#aa3322"))
        await db_session.commit()

        resp = await auth_client.get(f"/api/projects/{project.id}/yarn-colors")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["color_hex"] == "#aa3322"
        assert data[0]["yarn_name"] == "TestYarn"

    async def test_list_empty_when_none_linked(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        draft = await _make_draft(db_session, test_user.id)
        project = await _make_project(db_session, test_user.id, draft.id)
        await db_session.commit()

        resp = await auth_client.get(f"/api/projects/{project.id}/yarn-colors")
        assert resp.status_code == 200
        assert resp.json() == []


# ---------------------------------------------------------------------------
# GET /api/projects/{id} — yarn_colors inline in ProjectDetail
# ---------------------------------------------------------------------------


class TestProjectDetailIncludesYarnColors:
    async def test_project_detail_has_yarn_colors_field(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        draft = await _make_draft(db_session, test_user.id)
        project = await _make_project(db_session, test_user.id, draft.id)
        await db_session.commit()

        resp = await auth_client.get(f"/api/projects/{project.id}")
        assert resp.status_code == 200
        assert "yarn_colors" in resp.json()
        assert resp.json()["yarn_colors"] == []

    async def test_project_detail_includes_linked_yarn(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        draft = await _make_draft(db_session, test_user.id)
        project = await _make_project(db_session, test_user.id, draft.id)
        yarn = await _make_yarn(db_session, test_user.id)
        db_session.add(ProjectYarnColor(project_id=project.id, yarn_id=yarn.id, color_hex="#aa3322"))
        await db_session.commit()

        resp = await auth_client.get(f"/api/projects/{project.id}")
        assert resp.status_code == 200
        yc = resp.json()["yarn_colors"]
        assert len(yc) == 1
        assert yc[0]["yarn_brand"] == "TestBrand"
        assert yc[0]["color_hex"] == "#aa3322"


# ---------------------------------------------------------------------------
# GET /api/yarn/{id}/projects
# ---------------------------------------------------------------------------


class TestGetYarnProjects:
    async def test_returns_projects_using_yarn(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        draft = await _make_draft(db_session, test_user.id)
        project = await _make_project(db_session, test_user.id, draft.id)
        yarn = await _make_yarn(db_session, test_user.id)
        db_session.add(ProjectYarnColor(project_id=project.id, yarn_id=yarn.id, color_hex="#aa3322"))
        await db_session.commit()

        resp = await auth_client.get(f"/api/yarn/{yarn.id}/projects")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["project_name"] == "Test Project"
        assert data[0]["color_hex"] == "#aa3322"

    async def test_returns_empty_when_not_used(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        yarn = await _make_yarn(db_session, test_user.id)
        await db_session.commit()

        resp = await auth_client.get(f"/api/yarn/{yarn.id}/projects")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_404_for_other_users_yarn(
        self,
        auth_client: AsyncClient,
        db_session: AsyncSession,
        admin_user: User,
    ):
        yarn = await _make_yarn(db_session, admin_user.id)
        await db_session.commit()

        resp = await auth_client.get(f"/api/yarn/{yarn.id}/projects")
        assert resp.status_code == 404
