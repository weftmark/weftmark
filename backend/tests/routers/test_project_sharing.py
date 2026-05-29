"""Tests for project sharing endpoints.

Covers:
- PATCH /api/projects/{id}/share — create/update share slug
- DELETE /api/projects/{id}/share — revoke
- GET /api/share/projects/{slug} — public read
- GET /api/admin/project-slugs — admin slug report
- DELETE /api/admin/project-slugs/{slug} — admin revoke
"""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.draft import Draft
from app.models.project import Project
from app.models.user import User


@pytest.fixture(autouse=True)
def _mock_preview_tasks(monkeypatch):
    for attr in (
        "generate_drawdown_preview",
        "generate_project_drawdown_preview",
        "generate_project_drawdown_svg",
        "prerender_project_tiles",
    ):
        monkeypatch.setattr(f"app.routers.projects.{attr}", MagicMock())


_WIF = b"""[WIF]
Version=1.1
[CONTENTS]
WARP=true
WEFT=true
THREADING=true
TREADLING=true
LIFTPLAN=true
[WARP]
Threads=2
[WEFT]
Threads=2
[THREADING]
1=1
2=2
[TREADLING]
1=1
2=2
[LIFTPLAN]
1=1
2=2
"""


async def _insert_draft(db: AsyncSession, owner: User) -> Draft:
    import app.services.storage as storage

    draft_id = uuid.uuid4()
    wif_key = storage.save_wif(draft_id, "t.wif", _WIF)
    draft = Draft(
        id=draft_id,
        owner_id=owner.id,
        name="Share Test Draft",
        wif_filename="t.wif",
        wif_path=wif_key,
        has_treadling=True,
        has_liftplan=True,
        num_shafts=2,
        num_treadles=2,
        weft_threads=2,
    )
    db.add(draft)
    await db.commit()
    return draft


async def _insert_project(db: AsyncSession, owner: User, draft: Draft, **kwargs) -> Project:
    from app.models.project import ProjectDraft

    project = Project(
        owner_id=owner.id,
        name=kwargs.get("name", "My Weave"),
        project_type="treadle",
        status=kwargs.get("status", "active"),
        share_slug=kwargs.get("share_slug"),
        share_visibility=kwargs.get("share_visibility", "private"),
        share_expires_at=kwargs.get("share_expires_at"),
    )
    db.add(project)
    await db.flush()
    db.add(ProjectDraft(project_id=project.id, draft_id=draft.id, position=1, repeats=1, current_pick=0))
    await db.commit()
    return project


# ---------------------------------------------------------------------------
# PATCH /api/projects/{id}/share
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_share_slug(auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
    draft = await _insert_draft(db_session, test_user)
    project = await _insert_project(db_session, test_user, draft)

    resp = await auth_client.patch(
        f"/api/projects/{project.id}/share",
        json={"visibility": "link"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["share_visibility"] == "link"
    assert data["share_slug"] is not None
    assert data["share_expires_at"] is None


@pytest.mark.asyncio
async def test_share_with_expiry(auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
    draft = await _insert_draft(db_session, test_user)
    project = await _insert_project(db_session, test_user, draft)
    expires = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()

    resp = await auth_client.patch(
        f"/api/projects/{project.id}/share",
        json={"visibility": "link", "expires_at": expires},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["share_visibility"] == "link"
    assert data["share_expires_at"] is not None


@pytest.mark.asyncio
async def test_share_slug_stable_on_re_patch(auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
    """Slug should not change when expiry is updated on an already-shared project."""
    draft = await _insert_draft(db_session, test_user)
    project = await _insert_project(db_session, test_user, draft)

    r1 = await auth_client.patch(f"/api/projects/{project.id}/share", json={"visibility": "link"})
    assert r1.status_code == 200
    slug1 = r1.json()["share_slug"]

    expires = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    r2 = await auth_client.patch(
        f"/api/projects/{project.id}/share", json={"visibility": "link", "expires_at": expires}
    )
    assert r2.status_code == 200
    slug2 = r2.json()["share_slug"]

    assert slug1 == slug2


@pytest.mark.asyncio
async def test_share_invalid_visibility(auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
    draft = await _insert_draft(db_session, test_user)
    project = await _insert_project(db_session, test_user, draft)

    resp = await auth_client.patch(
        f"/api/projects/{project.id}/share",
        json={"visibility": "private"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_share_other_users_project_forbidden(
    auth_client: AsyncClient, db_session: AsyncSession, admin_user: User
):
    draft = await _insert_draft(db_session, admin_user)
    project = await _insert_project(db_session, admin_user, draft)

    resp = await auth_client.patch(f"/api/projects/{project.id}/share", json={"visibility": "link"})
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /api/projects/{id}/share
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_revoke_share(auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
    draft = await _insert_draft(db_session, test_user)
    project = await _insert_project(db_session, test_user, draft, share_slug="my-slug-abc", share_visibility="link")

    resp = await auth_client.delete(f"/api/projects/{project.id}/share")
    assert resp.status_code == 204

    await db_session.refresh(project)
    assert project.share_slug is None
    assert project.share_visibility == "private"


# ---------------------------------------------------------------------------
# GET /api/share/projects/{slug}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_public_slug_access(client: AsyncClient, db_session: AsyncSession, test_user: User):
    draft = await _insert_draft(db_session, test_user)
    project = await _insert_project(db_session, test_user, draft, share_slug="pub-abc123", share_visibility="link")

    resp = await client.get("/api/share/projects/pub-abc123")
    assert resp.status_code == 200
    data = resp.json()
    assert data["slug"] == "pub-abc123"
    assert data["project_name"] == project.name
    assert data["share_visibility"] == "link"


@pytest.mark.asyncio
async def test_private_slug_returns_404(client: AsyncClient, db_session: AsyncSession, test_user: User):
    draft = await _insert_draft(db_session, test_user)
    await _insert_project(db_session, test_user, draft, share_slug="priv-xyz", share_visibility="private")

    resp = await client.get("/api/share/projects/priv-xyz")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_expired_slug_returns_410(client: AsyncClient, db_session: AsyncSession, test_user: User):
    draft = await _insert_draft(db_session, test_user)
    past = datetime.now(timezone.utc) - timedelta(hours=1)
    await _insert_project(
        db_session,
        test_user,
        draft,
        share_slug="exp-abc",
        share_visibility="link",
        share_expires_at=past,
    )

    resp = await client.get("/api/share/projects/exp-abc")
    assert resp.status_code == 410


@pytest.mark.asyncio
async def test_unknown_slug_returns_404(client: AsyncClient):
    resp = await client.get("/api/share/projects/does-not-exist-xyz")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/admin/project-slugs
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_admin_list_slugs(admin_client: AsyncClient, db_session: AsyncSession, admin_user: User):
    draft = await _insert_draft(db_session, admin_user)
    await _insert_project(db_session, admin_user, draft, share_slug="admin-slug-1", share_visibility="link")

    resp = await admin_client.get("/api/admin/project-slugs")
    assert resp.status_code == 200
    slugs = [r["slug"] for r in resp.json()]
    assert "admin-slug-1" in slugs


@pytest.mark.asyncio
async def test_admin_list_slugs_excludes_private(admin_client: AsyncClient, db_session: AsyncSession, admin_user: User):
    draft = await _insert_draft(db_session, admin_user)
    await _insert_project(db_session, admin_user, draft, share_slug="hidden-slug", share_visibility="private")

    resp = await admin_client.get("/api/admin/project-slugs")
    assert resp.status_code == 200
    slugs = [r["slug"] for r in resp.json()]
    assert "hidden-slug" not in slugs


@pytest.mark.asyncio
async def test_non_admin_cannot_list_slugs(auth_client: AsyncClient):
    resp = await auth_client.get("/api/admin/project-slugs")
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# DELETE /api/admin/project-slugs/{slug}
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_admin_revoke_slug(admin_client: AsyncClient, db_session: AsyncSession, admin_user: User):
    draft = await _insert_draft(db_session, admin_user)
    project = await _insert_project(db_session, admin_user, draft, share_slug="revoke-me", share_visibility="public")

    resp = await admin_client.delete("/api/admin/project-slugs/revoke-me")
    assert resp.status_code == 204

    await db_session.refresh(project)
    assert project.share_slug is None
    assert project.share_visibility == "private"


@pytest.mark.asyncio
async def test_admin_revoke_nonexistent_slug(admin_client: AsyncClient):
    resp = await admin_client.delete("/api/admin/project-slugs/no-such-slug")
    assert resp.status_code == 404
