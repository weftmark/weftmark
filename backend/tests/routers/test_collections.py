"""Tests for the /api/collections router."""

import uuid
from datetime import datetime, timezone

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.collection import Collection, CollectionDraft, CollectionProject
from app.models.draft import Draft
from app.models.project import Project
from app.models.user import User

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _insert_collection(
    db: AsyncSession,
    owner: User,
    *,
    name: str = "My Collection",
    description: str | None = None,
    tags: list[str] | None = None,
) -> Collection:
    c = Collection(
        owner_id=owner.id,
        name=name,
        description=description,
        tags=tags or [],
    )
    db.add(c)
    await db.commit()
    await db.refresh(c)
    return c


async def _insert_draft(db: AsyncSession, owner: User) -> Draft:
    d = Draft(
        owner_id=owner.id,
        name="Test Draft",
        wif_filename="test.wif",
        wif_path=f"drafts/{uuid.uuid4()}/test.wif",
        lint_warnings=[],
        lint_errors=[],
    )
    db.add(d)
    await db.commit()
    await db.refresh(d)
    return d


async def _insert_project(db: AsyncSession, owner: User, draft: Draft) -> Project:
    p = Project(
        owner_id=owner.id,
        name="Test Project",
        project_type="treadle",
        status="active",
    )
    db.add(p)
    await db.commit()
    await db.refresh(p)
    return p


# ---------------------------------------------------------------------------
# POST /api/collections — create
# ---------------------------------------------------------------------------


class TestCreateCollection:
    async def test_returns_201(self, auth_client: AsyncClient):
        resp = await auth_client.post("/api/collections", json={"name": "Spring Scarves"})
        assert resp.status_code == 201

    async def test_returns_expected_fields(self, auth_client: AsyncClient):
        resp = await auth_client.post(
            "/api/collections",
            json={"name": "Spring Scarves", "description": "Experiments", "tags": ["spring", "scarves"]},
        )
        data = resp.json()
        assert data["name"] == "Spring Scarves"
        assert data["description"] == "Experiments"
        assert data["tags"] == ["spring", "scarves"]
        assert data["draft_count"] == 0
        assert data["project_count"] == 0
        assert "id" in data

    async def test_tags_default_empty(self, auth_client: AsyncClient):
        resp = await auth_client.post("/api/collections", json={"name": "No Tags"})
        assert resp.json()["tags"] == []

    async def test_name_required(self, auth_client: AsyncClient):
        resp = await auth_client.post("/api/collections", json={})
        assert resp.status_code == 422

    async def test_unauthenticated_returns_401(self, client: AsyncClient):
        resp = await client.post("/api/collections", json={"name": "X"})
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/collections — list
# ---------------------------------------------------------------------------


class TestListCollections:
    async def test_returns_200(self, auth_client: AsyncClient):
        resp = await auth_client.get("/api/collections")
        assert resp.status_code == 200

    async def test_returns_own_collections(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        await _insert_collection(db_session, test_user, name="Alpha")
        await _insert_collection(db_session, test_user, name="Beta")
        data = (await auth_client.get("/api/collections")).json()
        names = [c["name"] for c in data]
        assert "Alpha" in names
        assert "Beta" in names

    async def test_excludes_other_users_collections(
        self, auth_client: AsyncClient, db_session: AsyncSession, admin_user: User
    ):
        await _insert_collection(db_session, admin_user, name="Other User")
        data = (await auth_client.get("/api/collections")).json()
        assert not any(c["name"] == "Other User" for c in data)

    async def test_excludes_deleted_collections(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        c = await _insert_collection(db_session, test_user, name="Deleted")
        c.soft_delete()
        await db_session.commit()
        data = (await auth_client.get("/api/collections")).json()
        assert not any(col["name"] == "Deleted" for col in data)

    async def test_unauthenticated_returns_401(self, client: AsyncClient):
        resp = await client.get("/api/collections")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/collections/{id} — detail
# ---------------------------------------------------------------------------


class TestGetCollection:
    async def test_returns_200(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        c = await _insert_collection(db_session, test_user)
        resp = await auth_client.get(f"/api/collections/{c.id}")
        assert resp.status_code == 200

    async def test_returns_fields(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        c = await _insert_collection(db_session, test_user, name="Detail Test", tags=["foo"])
        data = (await auth_client.get(f"/api/collections/{c.id}")).json()
        assert data["name"] == "Detail Test"
        assert data["tags"] == ["foo"]
        assert "drafts" in data
        assert "projects" in data

    async def test_includes_draft_members(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        c = await _insert_collection(db_session, test_user)
        d = await _insert_draft(db_session, test_user)
        link = CollectionDraft(collection_id=c.id, draft_id=d.id, added_at=datetime.now(timezone.utc))
        db_session.add(link)
        await db_session.commit()
        data = (await auth_client.get(f"/api/collections/{c.id}")).json()
        assert any(item["id"] == str(d.id) for item in data["drafts"])

    async def test_includes_project_members(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        c = await _insert_collection(db_session, test_user)
        d = await _insert_draft(db_session, test_user)
        p = await _insert_project(db_session, test_user, d)
        link = CollectionProject(collection_id=c.id, project_id=p.id, added_at=datetime.now(timezone.utc))
        db_session.add(link)
        await db_session.commit()
        data = (await auth_client.get(f"/api/collections/{c.id}")).json()
        assert any(item["id"] == str(p.id) for item in data["projects"])

    async def test_other_users_collection_returns_404(
        self, auth_client: AsyncClient, db_session: AsyncSession, admin_user: User
    ):
        c = await _insert_collection(db_session, admin_user)
        resp = await auth_client.get(f"/api/collections/{c.id}")
        assert resp.status_code == 404

    async def test_nonexistent_returns_404(self, auth_client: AsyncClient):
        resp = await auth_client.get(f"/api/collections/{uuid.uuid4()}")
        assert resp.status_code == 404

    async def test_unauthenticated_returns_401(self, client: AsyncClient):
        resp = await client.get(f"/api/collections/{uuid.uuid4()}")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# PATCH /api/collections/{id} — update
# ---------------------------------------------------------------------------


class TestUpdateCollection:
    async def test_returns_200(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        c = await _insert_collection(db_session, test_user)
        resp = await auth_client.patch(f"/api/collections/{c.id}", json={"name": "Renamed"})
        assert resp.status_code == 200

    async def test_updates_name(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        c = await _insert_collection(db_session, test_user)
        data = (await auth_client.patch(f"/api/collections/{c.id}", json={"name": "Renamed"})).json()
        assert data["name"] == "Renamed"

    async def test_updates_tags(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        c = await _insert_collection(db_session, test_user)
        data = (await auth_client.patch(f"/api/collections/{c.id}", json={"tags": ["a", "b"]})).json()
        assert data["tags"] == ["a", "b"]

    async def test_other_users_collection_returns_404(
        self, auth_client: AsyncClient, db_session: AsyncSession, admin_user: User
    ):
        c = await _insert_collection(db_session, admin_user)
        resp = await auth_client.patch(f"/api/collections/{c.id}", json={"name": "X"})
        assert resp.status_code == 404

    async def test_unauthenticated_returns_401(self, client: AsyncClient):
        resp = await client.patch(f"/api/collections/{uuid.uuid4()}", json={"name": "X"})
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# DELETE /api/collections/{id} — soft delete
# ---------------------------------------------------------------------------


class TestDeleteCollection:
    async def test_returns_204(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        c = await _insert_collection(db_session, test_user)
        resp = await auth_client.delete(f"/api/collections/{c.id}")
        assert resp.status_code == 204

    async def test_sets_deleted_at(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        c = await _insert_collection(db_session, test_user)
        await auth_client.delete(f"/api/collections/{c.id}")
        await db_session.refresh(c)
        assert c.deleted_at is not None

    async def test_other_users_collection_returns_404(
        self, auth_client: AsyncClient, db_session: AsyncSession, admin_user: User
    ):
        c = await _insert_collection(db_session, admin_user)
        resp = await auth_client.delete(f"/api/collections/{c.id}")
        assert resp.status_code == 404

    async def test_unauthenticated_returns_401(self, client: AsyncClient):
        resp = await client.delete(f"/api/collections/{uuid.uuid4()}")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /api/collections/{id}/drafts — add draft
# ---------------------------------------------------------------------------


class TestAddDraft:
    async def test_returns_204(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        c = await _insert_collection(db_session, test_user)
        d = await _insert_draft(db_session, test_user)
        resp = await auth_client.post(f"/api/collections/{c.id}/drafts", json={"draft_id": str(d.id)})
        assert resp.status_code == 204

    async def test_draft_appears_in_detail(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        c = await _insert_collection(db_session, test_user)
        d = await _insert_draft(db_session, test_user)
        await auth_client.post(f"/api/collections/{c.id}/drafts", json={"draft_id": str(d.id)})
        data = (await auth_client.get(f"/api/collections/{c.id}")).json()
        assert any(item["id"] == str(d.id) for item in data["drafts"])

    async def test_duplicate_returns_409(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        c = await _insert_collection(db_session, test_user)
        d = await _insert_draft(db_session, test_user)
        await auth_client.post(f"/api/collections/{c.id}/drafts", json={"draft_id": str(d.id)})
        resp = await auth_client.post(f"/api/collections/{c.id}/drafts", json={"draft_id": str(d.id)})
        assert resp.status_code == 409

    async def test_other_users_draft_returns_404(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User, admin_user: User
    ):
        c = await _insert_collection(db_session, test_user)
        d = await _insert_draft(db_session, admin_user)
        resp = await auth_client.post(f"/api/collections/{c.id}/drafts", json={"draft_id": str(d.id)})
        assert resp.status_code == 404

    async def test_other_users_collection_returns_404(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User, admin_user: User
    ):
        c = await _insert_collection(db_session, admin_user)
        d = await _insert_draft(db_session, test_user)
        resp = await auth_client.post(f"/api/collections/{c.id}/drafts", json={"draft_id": str(d.id)})
        assert resp.status_code == 404

    async def test_unauthenticated_returns_401(self, client: AsyncClient):
        resp = await client.post(f"/api/collections/{uuid.uuid4()}/drafts", json={"draft_id": str(uuid.uuid4())})
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# DELETE /api/collections/{id}/drafts/{draft_id} — remove draft
# ---------------------------------------------------------------------------


class TestRemoveDraft:
    async def test_returns_204(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        c = await _insert_collection(db_session, test_user)
        d = await _insert_draft(db_session, test_user)
        await auth_client.post(f"/api/collections/{c.id}/drafts", json={"draft_id": str(d.id)})
        resp = await auth_client.delete(f"/api/collections/{c.id}/drafts/{d.id}")
        assert resp.status_code == 204

    async def test_draft_no_longer_in_detail(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        c = await _insert_collection(db_session, test_user)
        d = await _insert_draft(db_session, test_user)
        await auth_client.post(f"/api/collections/{c.id}/drafts", json={"draft_id": str(d.id)})
        await auth_client.delete(f"/api/collections/{c.id}/drafts/{d.id}")
        data = (await auth_client.get(f"/api/collections/{c.id}")).json()
        assert not any(item["id"] == str(d.id) for item in data["drafts"])

    async def test_not_member_returns_404(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        c = await _insert_collection(db_session, test_user)
        resp = await auth_client.delete(f"/api/collections/{c.id}/drafts/{uuid.uuid4()}")
        assert resp.status_code == 404

    async def test_unauthenticated_returns_401(self, client: AsyncClient):
        resp = await client.delete(f"/api/collections/{uuid.uuid4()}/drafts/{uuid.uuid4()}")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /api/collections/{id}/projects — add project
# ---------------------------------------------------------------------------


class TestAddProject:
    async def test_returns_204(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        c = await _insert_collection(db_session, test_user)
        d = await _insert_draft(db_session, test_user)
        p = await _insert_project(db_session, test_user, d)
        resp = await auth_client.post(f"/api/collections/{c.id}/projects", json={"project_id": str(p.id)})
        assert resp.status_code == 204

    async def test_project_appears_in_detail(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        c = await _insert_collection(db_session, test_user)
        d = await _insert_draft(db_session, test_user)
        p = await _insert_project(db_session, test_user, d)
        await auth_client.post(f"/api/collections/{c.id}/projects", json={"project_id": str(p.id)})
        data = (await auth_client.get(f"/api/collections/{c.id}")).json()
        assert any(item["id"] == str(p.id) for item in data["projects"])

    async def test_duplicate_returns_409(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        c = await _insert_collection(db_session, test_user)
        d = await _insert_draft(db_session, test_user)
        p = await _insert_project(db_session, test_user, d)
        await auth_client.post(f"/api/collections/{c.id}/projects", json={"project_id": str(p.id)})
        resp = await auth_client.post(f"/api/collections/{c.id}/projects", json={"project_id": str(p.id)})
        assert resp.status_code == 409

    async def test_other_users_project_returns_404(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User, admin_user: User
    ):
        c = await _insert_collection(db_session, test_user)
        d = await _insert_draft(db_session, admin_user)
        p = await _insert_project(db_session, admin_user, d)
        resp = await auth_client.post(f"/api/collections/{c.id}/projects", json={"project_id": str(p.id)})
        assert resp.status_code == 404

    async def test_unauthenticated_returns_401(self, client: AsyncClient):
        resp = await client.post(f"/api/collections/{uuid.uuid4()}/projects", json={"project_id": str(uuid.uuid4())})
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# DELETE /api/collections/{id}/projects/{project_id} — remove project
# ---------------------------------------------------------------------------


class TestRemoveProject:
    async def test_returns_204(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        c = await _insert_collection(db_session, test_user)
        d = await _insert_draft(db_session, test_user)
        p = await _insert_project(db_session, test_user, d)
        await auth_client.post(f"/api/collections/{c.id}/projects", json={"project_id": str(p.id)})
        resp = await auth_client.delete(f"/api/collections/{c.id}/projects/{p.id}")
        assert resp.status_code == 204

    async def test_project_no_longer_in_detail(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        c = await _insert_collection(db_session, test_user)
        d = await _insert_draft(db_session, test_user)
        p = await _insert_project(db_session, test_user, d)
        await auth_client.post(f"/api/collections/{c.id}/projects", json={"project_id": str(p.id)})
        await auth_client.delete(f"/api/collections/{c.id}/projects/{p.id}")
        data = (await auth_client.get(f"/api/collections/{c.id}")).json()
        assert not any(item["id"] == str(p.id) for item in data["projects"])

    async def test_not_member_returns_404(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        c = await _insert_collection(db_session, test_user)
        resp = await auth_client.delete(f"/api/collections/{c.id}/projects/{uuid.uuid4()}")
        assert resp.status_code == 404

    async def test_unauthenticated_returns_401(self, client: AsyncClient):
        resp = await client.delete(f"/api/collections/{uuid.uuid4()}/projects/{uuid.uuid4()}")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/collections — membership counts in list
# ---------------------------------------------------------------------------


class TestCollectionCounts:
    async def test_draft_count_reflects_members(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        c = await _insert_collection(db_session, test_user)
        d1 = await _insert_draft(db_session, test_user)
        d2 = await _insert_draft(db_session, test_user)
        await auth_client.post(f"/api/collections/{c.id}/drafts", json={"draft_id": str(d1.id)})
        await auth_client.post(f"/api/collections/{c.id}/drafts", json={"draft_id": str(d2.id)})
        data = (await auth_client.get("/api/collections")).json()
        match = next(col for col in data if col["id"] == str(c.id))
        assert match["draft_count"] == 2

    async def test_project_count_reflects_members(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        c = await _insert_collection(db_session, test_user)
        d = await _insert_draft(db_session, test_user)
        p = await _insert_project(db_session, test_user, d)
        await auth_client.post(f"/api/collections/{c.id}/projects", json={"project_id": str(p.id)})
        data = (await auth_client.get("/api/collections")).json()
        match = next(col for col in data if col["id"] == str(c.id))
        assert match["project_count"] == 1
