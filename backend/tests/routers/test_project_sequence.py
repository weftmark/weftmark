"""Tests for project sequence management endpoints.

Covers:
  POST   /{project_id}/sequence          — add_sequence_entry
  PATCH  /{project_id}/sequence/{seq_id} — update_sequence_entry
  DELETE /{project_id}/sequence/{seq_id} — remove_sequence_entry
  POST   /{project_id}/sequence/reorder  — reorder_sequence
  POST   /{project_id}/sequence/{seq_id}/activate — activate_sequence_entry
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.draft import Draft
from app.models.project import Project, ProjectDraft
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _insert_draft(db_session: AsyncSession, owner: User) -> Draft:
    import app.services.storage as storage

    draft_id = uuid.uuid4()
    wif_key = storage.save_wif(draft_id, "test.wif", b"[WIF]\nVersion=1.1\n")
    draft = Draft(
        id=draft_id,
        owner_id=owner.id,
        name="Seq Test Draft",
        wif_filename="test.wif",
        wif_path=wif_key,
        has_treadling=True,
        has_liftplan=True,
        num_shafts=4,
        num_treadles=2,
        weft_threads=4,
    )
    db_session.add(draft)
    await db_session.commit()
    return draft


async def _insert_project(
    db_session: AsyncSession,
    owner: User,
    *,
    status: str = "created",
) -> Project:
    project = Project(
        owner_id=owner.id,
        name="Seq Test Project",
        status=status,
    )
    db_session.add(project)
    await db_session.commit()
    return project


async def _add_entry(
    db_session: AsyncSession,
    project: Project,
    draft: Draft,
    *,
    position: int | None = None,
    repeats: int = 1,
) -> ProjectDraft:
    if position is None:
        existing = (
            await db_session.scalars(
                select(ProjectDraft)
                .where(ProjectDraft.project_id == project.id)
                .order_by(ProjectDraft.position.desc())
                .limit(1)
            )
        ).first()
        position = (existing.position + 1) if existing else 1

    entry = ProjectDraft(
        project_id=project.id,
        draft_id=draft.id,
        position=position,
        repeats=repeats,
        current_pick=0,
    )
    db_session.add(entry)
    await db_session.commit()
    return entry


# ---------------------------------------------------------------------------
# TestAddSequenceEntry — POST /{project_id}/sequence
# ---------------------------------------------------------------------------


class TestAddSequenceEntry:
    async def test_returns_201(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_project(db_session, test_user)
        resp = await auth_client.post(f"/api/projects/{project.id}/sequence", json={"draft_id": str(draft.id)})
        assert resp.status_code == 201

    async def test_entry_appears_in_sequence(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_project(db_session, test_user)
        body = (await auth_client.post(f"/api/projects/{project.id}/sequence", json={"draft_id": str(draft.id)})).json()
        assert len(body["draft_sequence"]) == 1
        assert body["draft_sequence"][0]["draft_id"] == str(draft.id)

    async def test_position_starts_at_1(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_project(db_session, test_user)
        body = (await auth_client.post(f"/api/projects/{project.id}/sequence", json={"draft_id": str(draft.id)})).json()
        assert body["draft_sequence"][0]["position"] == 1

    async def test_second_entry_gets_position_2(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_project(db_session, test_user)
        await auth_client.post(f"/api/projects/{project.id}/sequence", json={"draft_id": str(draft.id)})
        body = (await auth_client.post(f"/api/projects/{project.id}/sequence", json={"draft_id": str(draft.id)})).json()
        positions = [e["position"] for e in body["draft_sequence"]]
        assert positions == [1, 2]

    async def test_repeats_stored(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_project(db_session, test_user)
        body = (
            await auth_client.post(
                f"/api/projects/{project.id}/sequence", json={"draft_id": str(draft.id), "repeats": 3}
            )
        ).json()
        assert body["draft_sequence"][0]["repeats"] == 3

    async def test_repeats_defaults_to_1(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_project(db_session, test_user)
        body = (await auth_client.post(f"/api/projects/{project.id}/sequence", json={"draft_id": str(draft.id)})).json()
        assert body["draft_sequence"][0]["repeats"] == 1

    async def test_zero_repeats_returns_400(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_project(db_session, test_user)
        resp = await auth_client.post(
            f"/api/projects/{project.id}/sequence", json={"draft_id": str(draft.id), "repeats": 0}
        )
        assert resp.status_code == 400

    async def test_active_project_returns_400(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_project(db_session, test_user, status="active")
        resp = await auth_client.post(f"/api/projects/{project.id}/sequence", json={"draft_id": str(draft.id)})
        assert resp.status_code == 400

    async def test_unknown_draft_returns_404(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        project = await _insert_project(db_session, test_user)
        resp = await auth_client.post(f"/api/projects/{project.id}/sequence", json={"draft_id": str(uuid.uuid4())})
        assert resp.status_code == 404

    async def test_unknown_project_returns_404(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        draft = await _insert_draft(db_session, test_user)
        resp = await auth_client.post(f"/api/projects/{uuid.uuid4()}/sequence", json={"draft_id": str(draft.id)})
        assert resp.status_code == 404

    async def test_unauthenticated_returns_401(self, client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_project(db_session, test_user)
        resp = await client.post(f"/api/projects/{project.id}/sequence", json={"draft_id": str(draft.id)})
        assert resp.status_code == 401

    async def test_dispatches_preview_when_no_preview(
        self,
        auth_client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        from unittest.mock import patch

        draft = await _insert_draft(db_session, test_user)
        assert draft.drawdown_preview_path is None
        project = await _insert_project(db_session, test_user)

        with patch("app.routers.projects.generate_drawdown_preview") as mock_task:
            await auth_client.post(f"/api/projects/{project.id}/sequence", json={"draft_id": str(draft.id)})
            mock_task.delay.assert_called_once_with(str(draft.id))

    async def test_skips_preview_when_already_exists(
        self,
        auth_client: AsyncClient,
        db_session: AsyncSession,
        test_user: User,
    ):
        from unittest.mock import patch

        draft = await _insert_draft(db_session, test_user)
        draft.drawdown_preview_path = "project-previews/existing.png"
        await db_session.commit()
        project = await _insert_project(db_session, test_user)

        with patch("app.tasks.preview.generate_drawdown_preview.delay") as mock_delay:
            await auth_client.post(f"/api/projects/{project.id}/sequence", json={"draft_id": str(draft.id)})
            mock_delay.assert_not_called()


# ---------------------------------------------------------------------------
# TestUpdateSequenceEntry — PATCH /{project_id}/sequence/{seq_id}
# ---------------------------------------------------------------------------


class TestUpdateSequenceEntry:
    async def test_updates_repeats(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_project(db_session, test_user)
        entry = await _add_entry(db_session, project, draft, repeats=1)
        body = (await auth_client.patch(f"/api/projects/{project.id}/sequence/{entry.id}", json={"repeats": 5})).json()
        seq = next(e for e in body["draft_sequence"] if e["id"] == str(entry.id))
        assert seq["repeats"] == 5

    async def test_zero_repeats_returns_400(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_project(db_session, test_user)
        entry = await _add_entry(db_session, project, draft)
        resp = await auth_client.patch(f"/api/projects/{project.id}/sequence/{entry.id}", json={"repeats": 0})
        assert resp.status_code == 400

    async def test_unknown_entry_returns_404(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        project = await _insert_project(db_session, test_user)
        resp = await auth_client.patch(f"/api/projects/{project.id}/sequence/{uuid.uuid4()}", json={"repeats": 2})
        assert resp.status_code == 404

    async def test_unauthenticated_returns_401(self, client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_project(db_session, test_user)
        entry = await _add_entry(db_session, project, draft)
        resp = await client.patch(f"/api/projects/{project.id}/sequence/{entry.id}", json={"repeats": 2})
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# TestRemoveSequenceEntry — DELETE /{project_id}/sequence/{seq_id}
# ---------------------------------------------------------------------------


class TestRemoveSequenceEntry:
    async def test_returns_200(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_project(db_session, test_user)
        entry = await _add_entry(db_session, project, draft)
        resp = await auth_client.delete(f"/api/projects/{project.id}/sequence/{entry.id}")
        assert resp.status_code == 200

    async def test_entry_removed_from_sequence(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_project(db_session, test_user)
        entry = await _add_entry(db_session, project, draft)
        body = (await auth_client.delete(f"/api/projects/{project.id}/sequence/{entry.id}")).json()
        assert len(body["draft_sequence"]) == 0

    async def test_positions_renumbered_after_remove(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_project(db_session, test_user)
        _e1 = await _add_entry(db_session, project, draft)
        e2 = await _add_entry(db_session, project, draft)
        _e3 = await _add_entry(db_session, project, draft)

        # Remove the middle entry — remaining should be 1, 2
        body = (await auth_client.delete(f"/api/projects/{project.id}/sequence/{e2.id}")).json()
        positions = sorted(e["position"] for e in body["draft_sequence"])
        assert positions == [1, 2]

    async def test_active_project_returns_400(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_project(db_session, test_user, status="active")
        entry = await _add_entry(db_session, project, draft)
        resp = await auth_client.delete(f"/api/projects/{project.id}/sequence/{entry.id}")
        assert resp.status_code == 400

    async def test_unknown_entry_returns_404(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        project = await _insert_project(db_session, test_user)
        resp = await auth_client.delete(f"/api/projects/{project.id}/sequence/{uuid.uuid4()}")
        assert resp.status_code == 404

    async def test_unauthenticated_returns_401(self, client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_project(db_session, test_user)
        entry = await _add_entry(db_session, project, draft)
        resp = await client.delete(f"/api/projects/{project.id}/sequence/{entry.id}")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# TestReorderSequence — POST /{project_id}/sequence/reorder
# ---------------------------------------------------------------------------


class TestReorderSequence:
    async def test_reorders_entries(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_project(db_session, test_user)
        e1 = await _add_entry(db_session, project, draft)
        e2 = await _add_entry(db_session, project, draft)
        e3 = await _add_entry(db_session, project, draft)

        # Reverse order: 3, 2, 1
        body = (
            await auth_client.post(
                f"/api/projects/{project.id}/sequence/reorder",
                json={"ordered_ids": [str(e3.id), str(e2.id), str(e1.id)]},
            )
        ).json()
        seq = {e["id"]: e["position"] for e in body["draft_sequence"]}
        assert seq[str(e3.id)] == 1
        assert seq[str(e2.id)] == 2
        assert seq[str(e1.id)] == 3

    async def test_missing_entry_in_order_returns_400(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_project(db_session, test_user)
        e1 = await _add_entry(db_session, project, draft)
        await _add_entry(db_session, project, draft)

        # Only include one of the two entries
        resp = await auth_client.post(
            f"/api/projects/{project.id}/sequence/reorder",
            json={"ordered_ids": [str(e1.id)]},
        )
        assert resp.status_code == 400

    async def test_active_project_returns_400(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_project(db_session, test_user, status="active")
        entry = await _add_entry(db_session, project, draft)
        resp = await auth_client.post(
            f"/api/projects/{project.id}/sequence/reorder",
            json={"ordered_ids": [str(entry.id)]},
        )
        assert resp.status_code == 400

    async def test_unauthenticated_returns_401(self, client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_project(db_session, test_user)
        entry = await _add_entry(db_session, project, draft)
        resp = await client.post(f"/api/projects/{project.id}/sequence/reorder", json={"ordered_ids": [str(entry.id)]})
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# TestActivateSequenceEntry — POST /{project_id}/sequence/{seq_id}/activate
# ---------------------------------------------------------------------------


class TestActivateSequenceEntry:
    async def test_sets_current_position(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_project(db_session, test_user, status="active")
        _e1 = await _add_entry(db_session, project, draft)
        e2 = await _add_entry(db_session, project, draft)

        body = (await auth_client.post(f"/api/projects/{project.id}/sequence/{e2.id}/activate")).json()
        assert body["current_position"] == 2

    async def test_activate_unknown_entry_returns_404(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        project = await _insert_project(db_session, test_user, status="active")
        resp = await auth_client.post(f"/api/projects/{project.id}/sequence/{uuid.uuid4()}/activate")
        assert resp.status_code == 404

    async def test_inactive_project_returns_400(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_project(db_session, test_user, status="completed")
        entry = await _add_entry(db_session, project, draft)
        resp = await auth_client.post(f"/api/projects/{project.id}/sequence/{entry.id}/activate")
        assert resp.status_code == 400

    async def test_unauthenticated_returns_401(self, client: AsyncClient, db_session: AsyncSession, test_user: User):
        draft = await _insert_draft(db_session, test_user)
        project = await _insert_project(db_session, test_user, status="active")
        entry = await _add_entry(db_session, project, draft)
        resp = await client.post(f"/api/projects/{project.id}/sequence/{entry.id}/activate")
        assert resp.status_code == 401
