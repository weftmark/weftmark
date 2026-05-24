"""Tests for app.tasks.preview async inner functions.

Each async inner function (_generate_preview, _generate_project_preview,
_generate_project_svg, _backfill_*) creates its own DB engine; we redirect
them to db_session using the same sqlalchemy-level patch as test_purge.py.

The rendering service is mocked so tests are fast and font-independent.
The mock_storage autouse fixture (conftest) handles all storage I/O.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.tasks.preview import (
    _backfill_all_previews,
    _backfill_all_project_previews,
    _backfill_all_project_svgs,
    _generate_preview,
    _generate_project_preview,
    _generate_project_svg,
)

# ---------------------------------------------------------------------------
# Minimal valid WIF used to pre-populate mock_storage
# ---------------------------------------------------------------------------

MINIMAL_WIF = b"""[WIF]
Version=1.1
Date=April 2024
Source Program=TestSuite

[CONTENTS]
THREADING=true
TIEUP=true
TREADLING=true
COLOR TABLE=true
COLOR PALETTE=true

[WEAVING]
Shafts=4
Treadles=4
Rising Shed=true

[WARP]
Threads=4
Units=Inches
Color=1

[WEFT]
Threads=4
Units=Inches
Color=2

[COLOR PALETTE]
Range=0,255
Form=Decimal

[COLOR TABLE]
1=200,50,50
2=50,50,200

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

# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def _session_factory(db: AsyncSession):
    class _Ctx:
        async def __aenter__(self):
            return db

        async def __aexit__(self, *args):
            pass

    class _Factory:
        def __call__(self, *args, **kwargs):
            return _Ctx()

    return _Factory()


def _task_mock(retries: int = 0, max_retries: int = 2):
    t = MagicMock()
    t.request = MagicMock()
    t.request.retries = retries
    t.max_retries = max_retries
    t.MaxRetriesExceededError = Exception
    t.retry = MagicMock(side_effect=Exception("retry"))
    return t


@pytest.fixture()
def mock_engine_and_session(db_session: AsyncSession):
    fake_engine = MagicMock()
    fake_engine.dispose = AsyncMock()
    with (
        patch("app.tasks.preview.create_async_engine", return_value=fake_engine),
        patch("app.tasks.preview.async_sessionmaker", return_value=_session_factory(db_session)),
    ):
        yield fake_engine


@pytest.fixture()
def mock_rendering():
    """Patch the rendering service to avoid real image generation."""
    mock_draft = MagicMock()
    with (
        patch("app.services.rendering.load_draft", return_value=mock_draft),
        patch("app.services.rendering.render_full_draft", return_value=b"PNG_FULL"),
        patch("app.services.rendering.render_drawdown_preview", return_value=(b"PNG_DRAW", 1.0)),
        patch("app.services.rendering.render_drawdown_svg", return_value="<svg/>"),
        patch("app.services.rendering.apply_color_replacements"),
    ):
        yield mock_draft


# ---------------------------------------------------------------------------
# TestGeneratePreview — _generate_preview
# ---------------------------------------------------------------------------


class TestGeneratePreview:
    async def _make_draft(self, db_session, test_user, wif_path=None, deleted=False):
        from app.models.draft import Draft

        draft = Draft(
            id=uuid.uuid4(),
            owner_id=test_user.id,
            name="Preview Draft",
            wif_filename="test.wif",
            wif_path=wif_path or "drafts/test.wif",
        )
        if deleted:
            draft.deleted_at = datetime.now(timezone.utc)
        db_session.add(draft)
        await db_session.commit()
        return draft

    async def test_draft_not_found_returns_cleanly(self, db_session, mock_engine_and_session):
        await _generate_preview(_task_mock(), uuid.uuid4())

    async def test_deleted_draft_returns_cleanly(self, db_session, test_user, mock_engine_and_session):
        draft = await self._make_draft(db_session, test_user, deleted=True)
        await _generate_preview(_task_mock(), draft.id)

    async def test_wif_not_in_storage_returns_cleanly(
        self, db_session, test_user, mock_engine_and_session, mock_storage
    ):
        draft = await self._make_draft(db_session, test_user, wif_path="drafts/missing.wif")
        # mock_storage is empty — file_exists returns False
        await _generate_preview(_task_mock(), draft.id)

    async def test_valid_draft_saves_drawdown_preview(
        self, db_session, test_user, mock_engine_and_session, mock_storage, mock_rendering
    ):
        draft = await self._make_draft(db_session, test_user, wif_path="drafts/valid.wif")
        mock_storage["drafts/valid.wif"] = MINIMAL_WIF

        await _generate_preview(_task_mock(), draft.id)

        await db_session.refresh(draft)
        assert draft.drawdown_preview_path is not None

    async def test_valid_draft_saves_full_preview_when_missing(
        self, db_session, test_user, mock_engine_and_session, mock_storage, mock_rendering
    ):
        draft = await self._make_draft(db_session, test_user, wif_path="drafts/full.wif")
        mock_storage["drafts/full.wif"] = MINIMAL_WIF
        assert draft.preview_path is None

        await _generate_preview(_task_mock(), draft.id)

        await db_session.refresh(draft)
        assert draft.preview_path is not None

    async def test_skips_full_preview_when_already_set(
        self, db_session, test_user, mock_engine_and_session, mock_storage, mock_rendering
    ):
        from app.models.draft import Draft

        draft = Draft(
            id=uuid.uuid4(),
            owner_id=test_user.id,
            name="Existing Preview",
            wif_filename="ep.wif",
            wif_path="drafts/ep.wif",
            preview_path="previews/existing.png",
        )
        db_session.add(draft)
        await db_session.commit()
        mock_storage["drafts/ep.wif"] = MINIMAL_WIF

        with patch("app.services.rendering.render_full_draft") as mock_full:
            await _generate_preview(_task_mock(), draft.id)

        mock_full.assert_not_called()

    async def test_engine_disposed_on_success(
        self, db_session, test_user, mock_engine_and_session, mock_storage, mock_rendering
    ):
        draft = await self._make_draft(db_session, test_user, wif_path="drafts/disp.wif")
        mock_storage["drafts/disp.wif"] = MINIMAL_WIF

        await _generate_preview(_task_mock(), draft.id)

        mock_engine_and_session.dispose.assert_called_once()

    async def test_engine_disposed_on_missing_draft(self, db_session, mock_engine_and_session):
        await _generate_preview(_task_mock(), uuid.uuid4())
        mock_engine_and_session.dispose.assert_called_once()

    async def test_rendering_error_retries(self, db_session, test_user, mock_engine_and_session, mock_storage):
        draft = await self._make_draft(db_session, test_user, wif_path="drafts/err.wif")
        mock_storage["drafts/err.wif"] = MINIMAL_WIF

        task = _task_mock(retries=0, max_retries=2)

        with patch("app.services.rendering.load_draft", side_effect=RuntimeError("render fail")):
            await _generate_preview(task, draft.id)

        task.retry.assert_called_once()

    async def test_rendering_error_at_max_retries_does_not_raise(
        self, db_session, test_user, mock_engine_and_session, mock_storage
    ):
        draft = await self._make_draft(db_session, test_user, wif_path="drafts/max.wif")
        mock_storage["drafts/max.wif"] = MINIMAL_WIF

        task = _task_mock(retries=2, max_retries=2)
        task.MaxRetriesExceededError = Exception

        with patch("app.services.rendering.load_draft", side_effect=RuntimeError("fail")):
            await _generate_preview(task, draft.id)  # must not raise


# ---------------------------------------------------------------------------
# TestBackfillAllPreviews — _backfill_all_previews
# ---------------------------------------------------------------------------


class TestBackfillAllPreviews:
    async def test_returns_result_dict(self, db_session, mock_engine_and_session):
        result = await _backfill_all_previews()
        assert "dispatched" in result
        assert "skipped" in result

    async def test_empty_when_no_drafts(self, db_session, mock_engine_and_session):
        result = await _backfill_all_previews()
        assert result["dispatched"] == 0
        assert result["skipped"] == 0

    async def test_dispatches_for_draft_with_wif(self, db_session, test_user, mock_engine_and_session, mock_storage):
        from app.models.draft import Draft

        draft = Draft(
            id=uuid.uuid4(),
            owner_id=test_user.id,
            name="Backfill Draft",
            wif_filename="bf.wif",
            wif_path="drafts/bf.wif",
        )
        db_session.add(draft)
        await db_session.commit()
        mock_storage["drafts/bf.wif"] = MINIMAL_WIF

        with patch("app.tasks.preview.generate_drawdown_preview") as mock_task:
            result = await _backfill_all_previews()

        assert result["dispatched"] >= 1
        mock_task.delay.assert_called()

    async def test_skips_draft_with_no_wif_in_storage(
        self, db_session, test_user, mock_engine_and_session, mock_storage
    ):
        from app.models.draft import Draft

        draft = Draft(
            id=uuid.uuid4(),
            owner_id=test_user.id,
            name="No Storage WIF",
            wif_filename="ns.wif",
            wif_path="drafts/ns.wif",
        )
        db_session.add(draft)
        await db_session.commit()
        # mock_storage is empty

        with patch("app.tasks.preview.generate_drawdown_preview") as mock_task:
            result = await _backfill_all_previews()

        assert result["skipped"] >= 1
        mock_task.delay.assert_not_called()

    async def test_skips_draft_with_existing_preview(
        self, db_session, test_user, mock_engine_and_session, mock_storage
    ):
        from app.models.draft import Draft

        draft = Draft(
            id=uuid.uuid4(),
            owner_id=test_user.id,
            name="Already Done",
            wif_filename="done.wif",
            wif_path="drafts/done.wif",
            drawdown_preview_path="drafts/done.png",
        )
        db_session.add(draft)
        await db_session.commit()
        mock_storage["drafts/done.wif"] = MINIMAL_WIF

        with patch("app.tasks.preview.generate_drawdown_preview") as mock_task:
            await _backfill_all_previews()

        mock_task.delay.assert_not_called()


# ---------------------------------------------------------------------------
# TestGenerateProjectPreview — _generate_project_preview
# ---------------------------------------------------------------------------


class TestGenerateProjectPreview:
    async def _make_draft(self, db_session, test_user):
        from app.models.draft import Draft

        draft = Draft(
            id=uuid.uuid4(),
            owner_id=test_user.id,
            name="Proj Draft",
            wif_filename="proj.wif",
            wif_path="drafts/proj.wif",
        )
        db_session.add(draft)
        await db_session.flush()
        return draft

    async def _make_project(self, db_session, test_user, draft, deleted=False, **kwargs):
        from app.models.project import Project

        project = Project(
            id=uuid.uuid4(),
            owner_id=test_user.id,
            draft_id=draft.id,
            name="Test Project",
            project_type="treadle",
            total_picks=4,
            **kwargs,
        )
        if deleted:
            project.deleted_at = datetime.now(timezone.utc)
        db_session.add(project)
        await db_session.commit()
        return project

    async def test_project_not_found_returns_cleanly(self, db_session, mock_engine_and_session):
        await _generate_project_preview(_task_mock(), uuid.uuid4())

    async def test_deleted_project_returns_cleanly(self, db_session, test_user, mock_engine_and_session):
        draft = await self._make_draft(db_session, test_user)
        project = await self._make_project(db_session, test_user, draft, deleted=True)
        await _generate_project_preview(_task_mock(), project.id)

    async def test_deleted_draft_returns_cleanly(self, db_session, test_user, mock_engine_and_session):
        from app.models.draft import Draft

        draft = Draft(
            id=uuid.uuid4(),
            owner_id=test_user.id,
            name="Deleted Draft",
            wif_filename="del.wif",
            wif_path="drafts/del.wif",
            deleted_at=datetime.now(timezone.utc),
        )
        db_session.add(draft)
        await db_session.flush()
        project = await self._make_project(db_session, test_user, draft)
        await _generate_project_preview(_task_mock(), project.id)

    async def test_no_wif_in_storage_returns_cleanly(
        self, db_session, test_user, mock_engine_and_session, mock_storage
    ):
        draft = await self._make_draft(db_session, test_user)
        project = await self._make_project(db_session, test_user, draft)
        # mock_storage empty — file_exists returns False
        await _generate_project_preview(_task_mock(), project.id)

    async def test_valid_project_saves_preview(
        self, db_session, test_user, mock_engine_and_session, mock_storage, mock_rendering
    ):
        draft = await self._make_draft(db_session, test_user)
        project = await self._make_project(db_session, test_user, draft)
        mock_storage["drafts/proj.wif"] = MINIMAL_WIF

        await _generate_project_preview(_task_mock(), project.id)

        await db_session.refresh(project)
        assert project.drawdown_preview_path is not None

    async def test_old_preview_deleted_on_success(
        self, db_session, test_user, mock_engine_and_session, mock_storage, mock_rendering
    ):
        draft = await self._make_draft(db_session, test_user)
        old_path = "projects/old-preview.png"
        mock_storage[old_path] = b"OLD"
        project = await self._make_project(db_session, test_user, draft, drawdown_preview_path=old_path)
        mock_storage["drafts/proj.wif"] = MINIMAL_WIF

        await _generate_project_preview(_task_mock(), project.id)

        assert old_path not in mock_storage

    async def test_color_replacements_applied(self, db_session, test_user, mock_engine_and_session, mock_storage):
        draft = await self._make_draft(db_session, test_user)
        project = await self._make_project(db_session, test_user, draft, color_replacements={"#ff0000": "#00ff00"})
        mock_storage["drafts/proj.wif"] = MINIMAL_WIF

        with (
            patch("app.services.rendering.load_draft", return_value=MagicMock()),
            patch("app.services.rendering.apply_color_replacements") as mock_replace,
            patch("app.services.rendering.render_drawdown_preview", return_value=(b"PNG", 1.0)),
        ):
            await _generate_project_preview(_task_mock(), project.id)

        mock_replace.assert_called_once()

    async def test_engine_disposed(self, db_session, test_user, mock_engine_and_session, mock_storage, mock_rendering):
        draft = await self._make_draft(db_session, test_user)
        project = await self._make_project(db_session, test_user, draft)
        mock_storage["drafts/proj.wif"] = MINIMAL_WIF

        await _generate_project_preview(_task_mock(), project.id)

        mock_engine_and_session.dispose.assert_called_once()


# ---------------------------------------------------------------------------
# TestGenerateProjectSVG — _generate_project_svg
# ---------------------------------------------------------------------------


class TestGenerateProjectSVG:
    async def _make_draft(self, db_session, test_user, wif_path="drafts/svg.wif"):
        from app.models.draft import Draft

        draft = Draft(
            id=uuid.uuid4(),
            owner_id=test_user.id,
            name="SVG Draft",
            wif_filename="svg.wif",
            wif_path=wif_path,
        )
        db_session.add(draft)
        await db_session.flush()
        return draft

    async def _make_project(self, db_session, test_user, draft, **kwargs):
        from app.models.project import Project

        project = Project(
            id=uuid.uuid4(),
            owner_id=test_user.id,
            draft_id=draft.id,
            name="SVG Project",
            project_type="treadle",
            total_picks=4,
            **kwargs,
        )
        db_session.add(project)
        await db_session.commit()
        return project

    async def test_project_not_found_returns_cleanly(self, db_session, mock_engine_and_session):
        await _generate_project_svg(_task_mock(), uuid.uuid4())

    async def test_deleted_project_returns_cleanly(self, db_session, test_user, mock_engine_and_session):
        draft = await self._make_draft(db_session, test_user)
        from app.models.project import Project

        project = Project(
            id=uuid.uuid4(),
            owner_id=test_user.id,
            draft_id=draft.id,
            name="Del Project",
            project_type="treadle",
            total_picks=4,
            deleted_at=datetime.now(timezone.utc),
        )
        db_session.add(project)
        await db_session.commit()
        await _generate_project_svg(_task_mock(), project.id)

    async def test_no_wif_in_storage_returns_cleanly(
        self, db_session, test_user, mock_engine_and_session, mock_storage
    ):
        draft = await self._make_draft(db_session, test_user)
        project = await self._make_project(db_session, test_user, draft)
        await _generate_project_svg(_task_mock(), project.id)

    async def test_valid_project_saves_svg(
        self, db_session, test_user, mock_engine_and_session, mock_storage, mock_rendering
    ):
        draft = await self._make_draft(db_session, test_user)
        project = await self._make_project(db_session, test_user, draft)
        mock_storage["drafts/svg.wif"] = MINIMAL_WIF

        await _generate_project_svg(_task_mock(), project.id)

        await db_session.refresh(project)
        assert project.drawdown_svg_path is not None

    async def test_old_svg_deleted_on_success(
        self, db_session, test_user, mock_engine_and_session, mock_storage, mock_rendering
    ):
        draft = await self._make_draft(db_session, test_user)
        old_path = "projects/old.svg"
        mock_storage[old_path] = b"OLD"
        project = await self._make_project(db_session, test_user, draft, drawdown_svg_path=old_path)
        mock_storage["drafts/svg.wif"] = MINIMAL_WIF

        await _generate_project_svg(_task_mock(), project.id)

        assert old_path not in mock_storage

    async def test_engine_disposed(self, db_session, test_user, mock_engine_and_session, mock_storage, mock_rendering):
        draft = await self._make_draft(db_session, test_user)
        project = await self._make_project(db_session, test_user, draft)
        mock_storage["drafts/svg.wif"] = MINIMAL_WIF

        await _generate_project_svg(_task_mock(), project.id)

        mock_engine_and_session.dispose.assert_called_once()


# ---------------------------------------------------------------------------
# TestBackfillAllProjectPreviews — _backfill_all_project_previews
# ---------------------------------------------------------------------------


class TestBackfillAllProjectPreviews:
    async def _make_draft_and_project(self, db_session, test_user, wif_path="drafts/bfp.wif", deleted_draft=False):
        from app.models.draft import Draft
        from app.models.project import Project

        draft = Draft(
            id=uuid.uuid4(),
            owner_id=test_user.id,
            name="BF Project Draft",
            wif_filename="bfp.wif",
            wif_path=wif_path,
            deleted_at=datetime.now(timezone.utc) if deleted_draft else None,
        )
        db_session.add(draft)
        await db_session.flush()

        project = Project(
            id=uuid.uuid4(),
            owner_id=test_user.id,
            draft_id=draft.id,
            name="BF Project",
            project_type="treadle",
            total_picks=4,
        )
        db_session.add(project)
        await db_session.commit()
        return draft, project

    async def test_returns_result_dict(self, db_session, mock_engine_and_session):
        result = await _backfill_all_project_previews()
        assert "dispatched" in result
        assert "skipped" in result

    async def test_dispatches_for_project_with_wif(self, db_session, test_user, mock_engine_and_session, mock_storage):
        draft, project = await self._make_draft_and_project(db_session, test_user)
        mock_storage["drafts/bfp.wif"] = MINIMAL_WIF

        with patch("app.tasks.preview.generate_project_drawdown_preview") as mock_task:
            result = await _backfill_all_project_previews()

        assert result["dispatched"] >= 1
        mock_task.delay.assert_called()

    async def test_skips_project_with_deleted_draft(self, db_session, test_user, mock_engine_and_session, mock_storage):
        draft, project = await self._make_draft_and_project(db_session, test_user, deleted_draft=True)
        mock_storage["drafts/bfp.wif"] = MINIMAL_WIF

        with patch("app.tasks.preview.generate_project_drawdown_preview") as mock_task:
            result = await _backfill_all_project_previews()

        assert result["skipped"] >= 1
        mock_task.delay.assert_not_called()

    async def test_skips_project_with_no_wif(self, db_session, test_user, mock_engine_and_session, mock_storage):
        draft, project = await self._make_draft_and_project(db_session, test_user)
        # storage empty

        with patch("app.tasks.preview.generate_project_drawdown_preview") as mock_task:
            result = await _backfill_all_project_previews()

        assert result["skipped"] >= 1
        mock_task.delay.assert_not_called()


# ---------------------------------------------------------------------------
# TestBackfillAllProjectSVGs — _backfill_all_project_svgs
# ---------------------------------------------------------------------------


class TestBackfillAllProjectSVGs:
    async def _make_draft_and_project(self, db_session, test_user, wif_path="drafts/bfs.wif", deleted_draft=False):
        from app.models.draft import Draft
        from app.models.project import Project

        draft = Draft(
            id=uuid.uuid4(),
            owner_id=test_user.id,
            name="BFS Draft",
            wif_filename="bfs.wif",
            wif_path=wif_path,
            deleted_at=datetime.now(timezone.utc) if deleted_draft else None,
        )
        db_session.add(draft)
        await db_session.flush()

        project = Project(
            id=uuid.uuid4(),
            owner_id=test_user.id,
            draft_id=draft.id,
            name="BFS Project",
            project_type="treadle",
            total_picks=4,
        )
        db_session.add(project)
        await db_session.commit()
        return draft, project

    async def test_returns_result_dict(self, db_session, mock_engine_and_session):
        result = await _backfill_all_project_svgs()
        assert "dispatched" in result
        assert "skipped" in result

    async def test_dispatches_for_project_with_wif(self, db_session, test_user, mock_engine_and_session, mock_storage):
        draft, project = await self._make_draft_and_project(db_session, test_user)
        mock_storage["drafts/bfs.wif"] = MINIMAL_WIF

        with patch("app.tasks.preview.generate_project_drawdown_svg") as mock_task:
            result = await _backfill_all_project_svgs()

        assert result["dispatched"] >= 1
        mock_task.delay.assert_called()

    async def test_skips_project_with_deleted_draft(self, db_session, test_user, mock_engine_and_session, mock_storage):
        draft, project = await self._make_draft_and_project(db_session, test_user, deleted_draft=True)
        mock_storage["drafts/bfs.wif"] = MINIMAL_WIF

        with patch("app.tasks.preview.generate_project_drawdown_svg") as mock_task:
            result = await _backfill_all_project_svgs()

        assert result["skipped"] >= 1
        mock_task.delay.assert_not_called()

    async def test_skips_project_with_no_wif_in_storage(
        self, db_session, test_user, mock_engine_and_session, mock_storage
    ):
        draft, project = await self._make_draft_and_project(db_session, test_user)
        # storage empty

        with patch("app.tasks.preview.generate_project_drawdown_svg") as mock_task:
            result = await _backfill_all_project_svgs()

        assert result["skipped"] >= 1
        mock_task.delay.assert_not_called()

    async def test_skips_project_with_existing_svg(self, db_session, test_user, mock_engine_and_session, mock_storage):
        from app.models.draft import Draft
        from app.models.project import Project

        draft = Draft(
            id=uuid.uuid4(),
            owner_id=test_user.id,
            name="SVG Done",
            wif_filename="svgd.wif",
            wif_path="drafts/svgd.wif",
        )
        db_session.add(draft)
        await db_session.flush()

        project = Project(
            id=uuid.uuid4(),
            owner_id=test_user.id,
            draft_id=draft.id,
            name="SVG Done Project",
            project_type="treadle",
            total_picks=4,
            drawdown_svg_path="projects/existing.svg",
        )
        db_session.add(project)
        await db_session.commit()
        mock_storage["drafts/svgd.wif"] = MINIMAL_WIF

        with patch("app.tasks.preview.generate_project_drawdown_svg") as mock_task:
            await _backfill_all_project_svgs()

        mock_task.delay.assert_not_called()
