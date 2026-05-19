"""Tests for tags on drafts and projects (#781)."""

import io
import uuid
from unittest.mock import MagicMock

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.draft import Draft
from app.models.project import Project
from app.models.user import User


@pytest.fixture(autouse=True)
def _mock_draft_tasks(monkeypatch):
    monkeypatch.setattr("app.routers.drafts.generate_drawdown_preview", MagicMock())
    monkeypatch.setattr("app.routers.drafts.prerender_drawdown_tiles", MagicMock())


@pytest.fixture(autouse=True)
def _mock_project_tasks(monkeypatch):
    monkeypatch.setattr("app.routers.projects.generate_drawdown_preview", MagicMock())
    monkeypatch.setattr("app.routers.projects.prerender_project_tiles", MagicMock())
    monkeypatch.setattr("app.routers.projects.generate_project_drawdown_preview", MagicMock())
    monkeypatch.setattr("app.routers.projects.generate_project_drawdown_svg", MagicMock())


_WIF = b"""[WIF]
Version=1.1
[CONTENTS]
THREADING=true
TIEUP=true
TREADLING=true
[WEAVING]
Shafts=4
Treadles=4
Rising Shed=true
[WARP]
Threads=4
[WEFT]
Threads=4
[THREADING]
1=1
2=2
3=3
4=4
[TIEUP]
1=1
2=2
3=3
4=4
[TREADLING]
1=1
2=2
3=3
4=4
"""


async def _insert_draft(db: AsyncSession, owner: User, *, tags: list[str] | None = None) -> Draft:
    import app.services.storage as storage

    draft_id = uuid.uuid4()
    wif_key = storage.save_wif(draft_id, "test.wif", _WIF)
    d = Draft(
        id=draft_id,
        owner_id=owner.id,
        name="Test Draft",
        wif_filename="test.wif",
        wif_path=wif_key,
        has_treadling=True,
        num_shafts=4,
        num_treadles=4,
        weft_threads=4,
        tags=tags or [],
    )
    db.add(d)
    await db.commit()
    return d


async def _insert_project(db: AsyncSession, owner: User, draft: Draft, *, tags: list[str] | None = None) -> Project:
    p = Project(
        owner_id=owner.id,
        draft_id=draft.id,
        name="Test Project",
        project_type="treadle",
        status="created",
        total_picks=100,
        tags=tags or [],
    )
    db.add(p)
    await db.commit()
    return p


# ---------------------------------------------------------------------------
# Draft tags — upload
# ---------------------------------------------------------------------------


class TestDraftUploadTags:
    async def test_upload_with_tags_stores_them(self, auth_client: AsyncClient):
        resp = await auth_client.post(
            "/api/drafts",
            data={"name": "Tagged Draft", "tags": '["twill", "cotton"]'},
            files={"wif_file": ("test.wif", io.BytesIO(_WIF), "text/plain")},
        )
        assert resp.status_code == 201
        assert resp.json()["tags"] == ["twill", "cotton"]

    async def test_upload_without_tags_defaults_empty(self, auth_client: AsyncClient):
        resp = await auth_client.post(
            "/api/drafts",
            data={"name": "Plain Draft"},
            files={"wif_file": ("test.wif", io.BytesIO(_WIF), "text/plain")},
        )
        assert resp.status_code == 201
        assert resp.json()["tags"] == []

    async def test_tags_appear_in_list(self, auth_client: AsyncClient):
        await auth_client.post(
            "/api/drafts",
            data={"name": "Tagged", "tags": '["twill"]'},
            files={"wif_file": ("test.wif", io.BytesIO(_WIF), "text/plain")},
        )
        data = (await auth_client.get("/api/drafts")).json()
        assert data[0]["tags"] == ["twill"]


# ---------------------------------------------------------------------------
# Draft tags — PATCH
# ---------------------------------------------------------------------------


class TestPatchDraftTags:
    async def test_update_tags(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        d = await _insert_draft(db_session, test_user)
        resp = await auth_client.patch(f"/api/drafts/{d.id}", json={"tags": ["lace", "silk"]})
        assert resp.status_code == 200
        assert resp.json()["tags"] == ["lace", "silk"]

    async def test_clear_tags(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        d = await _insert_draft(db_session, test_user, tags=["twill"])
        resp = await auth_client.patch(f"/api/drafts/{d.id}", json={"tags": []})
        assert resp.status_code == 200
        assert resp.json()["tags"] == []

    async def test_update_name_and_tags_together(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        d = await _insert_draft(db_session, test_user)
        resp = await auth_client.patch(f"/api/drafts/{d.id}", json={"name": "Renamed", "tags": ["gift"]})
        assert resp.status_code == 200
        assert resp.json()["name"] == "Renamed"
        assert resp.json()["tags"] == ["gift"]

    async def test_other_users_draft_returns_404(
        self, auth_client: AsyncClient, db_session: AsyncSession, admin_user: User
    ):
        d = await _insert_draft(db_session, admin_user)
        resp = await auth_client.patch(f"/api/drafts/{d.id}", json={"tags": ["x"]})
        assert resp.status_code == 404

    async def test_nonexistent_draft_returns_404(self, auth_client: AsyncClient):
        resp = await auth_client.patch(f"/api/drafts/{uuid.uuid4()}", json={"tags": ["x"]})
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Draft tags — filter
# ---------------------------------------------------------------------------


class TestFilterDraftsByTag:
    async def test_filter_returns_matching_draft(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        await _insert_draft(db_session, test_user, tags=["twill"])
        await _insert_draft(db_session, test_user, tags=["plain"])
        resp = await auth_client.get("/api/drafts?tags=twill")
        data = resp.json()
        assert len(data) == 1
        assert data[0]["tags"] == ["twill"]

    async def test_filter_multiple_tags_returns_any_match(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        await _insert_draft(db_session, test_user, tags=["twill"])
        await _insert_draft(db_session, test_user, tags=["plain"])
        await _insert_draft(db_session, test_user, tags=["lace"])
        resp = await auth_client.get("/api/drafts?tags=twill&tags=lace")
        data = resp.json()
        assert len(data) == 2

    async def test_no_filter_returns_all(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        await _insert_draft(db_session, test_user, tags=["twill"])
        await _insert_draft(db_session, test_user, tags=["plain"])
        data = (await auth_client.get("/api/drafts")).json()
        assert len(data) == 2

    async def test_filter_no_match_returns_empty(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        await _insert_draft(db_session, test_user, tags=["twill"])
        data = (await auth_client.get("/api/drafts?tags=lace")).json()
        assert data == []


# ---------------------------------------------------------------------------
# Project tags — create
# ---------------------------------------------------------------------------


class TestCreateProjectTags:
    async def test_create_with_tags(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        d = await _insert_draft(db_session, test_user)
        resp = await auth_client.post(
            "/api/projects",
            json={
                "name": "Tagged Project",
                "draft_id": str(d.id),
                "project_type": "treadle",
                "tags": ["wip", "cotton"],
            },
        )
        assert resp.status_code == 201
        assert resp.json()["tags"] == ["wip", "cotton"]

    async def test_create_without_tags_defaults_empty(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        d = await _insert_draft(db_session, test_user)
        resp = await auth_client.post(
            "/api/projects",
            json={"name": "Plain Project", "draft_id": str(d.id), "project_type": "treadle"},
        )
        assert resp.status_code == 201
        assert resp.json()["tags"] == []


# ---------------------------------------------------------------------------
# Project tags — PATCH
# ---------------------------------------------------------------------------


class TestPatchProjectTags:
    async def test_update_tags(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        d = await _insert_draft(db_session, test_user)
        p = await _insert_project(db_session, test_user, d)
        resp = await auth_client.patch(f"/api/projects/{p.id}", json={"tags": ["gift", "wool"]})
        assert resp.status_code == 200
        assert resp.json()["tags"] == ["gift", "wool"]

    async def test_clear_tags(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        d = await _insert_draft(db_session, test_user)
        p = await _insert_project(db_session, test_user, d, tags=["wip"])
        resp = await auth_client.patch(f"/api/projects/{p.id}", json={"tags": []})
        assert resp.status_code == 200
        assert resp.json()["tags"] == []

    async def test_tags_in_list_response(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        d = await _insert_draft(db_session, test_user)
        await _insert_project(db_session, test_user, d, tags=["gift"])
        data = (await auth_client.get("/api/projects")).json()
        assert data[0]["tags"] == ["gift"]


# ---------------------------------------------------------------------------
# Project tags — filter
# ---------------------------------------------------------------------------


class TestFilterProjectsByTag:
    async def test_filter_returns_matching(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        d = await _insert_draft(db_session, test_user)
        await _insert_project(db_session, test_user, d, tags=["wip"])
        await _insert_project(db_session, test_user, d, tags=["done"])
        resp = await auth_client.get("/api/projects?tags=wip")
        data = resp.json()
        assert len(data) == 1
        assert data[0]["tags"] == ["wip"]

    async def test_filter_multiple_tags_any_match(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        d = await _insert_draft(db_session, test_user)
        await _insert_project(db_session, test_user, d, tags=["wip"])
        await _insert_project(db_session, test_user, d, tags=["done"])
        await _insert_project(db_session, test_user, d, tags=["gift"])
        resp = await auth_client.get("/api/projects?tags=wip&tags=gift")
        data = resp.json()
        assert len(data) == 2

    async def test_no_filter_returns_all(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        d = await _insert_draft(db_session, test_user)
        await _insert_project(db_session, test_user, d, tags=["wip"])
        await _insert_project(db_session, test_user, d, tags=["done"])
        data = (await auth_client.get("/api/projects")).json()
        assert len(data) == 2
