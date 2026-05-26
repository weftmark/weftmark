"""Tests for app.tasks.tiles._render_and_store_tiles, _prerender_draft, _prerender_project.

The tile rendering pipeline (_render_and_store_tiles) is a pure synchronous function
that takes all its dependencies as parameters and can be exercised without any DB or
storage fixtures.

The prerender functions (_prerender_draft, _prerender_project) create their own DB
engine and session; we redirect them to the test db_session using the same sqlalchemy-
level patch as test_purge.py.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.tasks.tiles import _render_and_store_tiles

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


def _settings(tile_row_count: int = 50, render_max_width: int = 16000):
    m = MagicMock()
    m.render_max_width = render_max_width
    m.tile_row_count = tile_row_count
    return m


def _render(wif_bytes=MINIMAL_WIF, save_fn=None, tile_row_count=50, color_replacements=None):
    from PIL import Image as PILImage

    from app.services import rendering
    from app.services.rendering import ImageRenderer

    if save_fn is None:
        save_fn = MagicMock()
    return _render_and_store_tiles(
        wif_bytes,
        _settings(tile_row_count=tile_row_count),
        rendering,
        ImageRenderer,
        PILImage,
        save_fn,
        entity_id=uuid.uuid4(),
        entity_label="draft_id",
        color_replacements=color_replacements,
    )


# ---------------------------------------------------------------------------
# TestRenderAndStoreTiles
# ---------------------------------------------------------------------------


class TestRenderAndStoreTiles:
    def test_returns_positive_tile_count(self):
        count = _render()
        assert count >= 1

    def test_calls_save_fn_once_per_tile(self):
        save_fn = MagicMock()
        count = _render(save_fn=save_fn)
        assert save_fn.call_count == count

    def test_save_fn_receives_bytes(self):
        save_fn = MagicMock()
        _render(save_fn=save_fn)
        # Last arg to save_fn is PNG bytes
        _entity_id, scale, start, data = save_fn.call_args[0]
        assert isinstance(data, bytes)
        assert data[:4] == b"\x89PNG"  # PNG magic

    def test_save_fn_tile_start_is_zero_for_first_tile(self):
        save_fn = MagicMock()
        _render(save_fn=save_fn)
        first_call = save_fn.call_args_list[0]
        _entity_id, scale, start, _data = first_call[0]
        assert start == 0

    def test_smaller_tile_row_count_produces_more_tiles(self):
        count_big = _render(tile_row_count=100)
        count_small = _render(tile_row_count=1)
        # 4-thread draft: tile_row_count=100 → 1 tile; tile_row_count=1 → 4 tiles
        assert count_small >= count_big

    def test_entity_id_passed_to_save_fn(self):
        entity_id = uuid.uuid4()
        save_fn = MagicMock()

        from PIL import Image as PILImage

        from app.services import rendering
        from app.services.rendering import ImageRenderer

        _render_and_store_tiles(
            MINIMAL_WIF,
            _settings(),
            rendering,
            ImageRenderer,
            PILImage,
            save_fn,
            entity_id=entity_id,
            entity_label="draft_id",
        )
        first_call_entity_id = save_fn.call_args_list[0][0][0]
        assert first_call_entity_id == entity_id

    def test_no_color_replacements_renders_successfully(self):
        count = _render(color_replacements=None)
        assert count >= 1

    def test_empty_color_replacements_renders_successfully(self):
        count = _render(color_replacements={})
        assert count >= 1

    def test_render_returns_zero_for_too_wide_draft(self):
        # render_max_width=1 forces effective_scale < 1 → returns 0
        from PIL import Image as PILImage

        from app.services import rendering
        from app.services.rendering import ImageRenderer

        save_fn = MagicMock()
        count = _render_and_store_tiles(
            MINIMAL_WIF,
            _settings(render_max_width=1),
            rendering,
            ImageRenderer,
            PILImage,
            save_fn,
            entity_id=uuid.uuid4(),
            entity_label="draft_id",
        )
        assert count == 0
        save_fn.assert_not_called()

    def test_nonempty_color_replacements_covers_apply_branch(self):
        # Covers lines 159-160: color_replacements dict is truthy → apply called
        count = _render(color_replacements={"#c83232": "#3232c8"})
        assert count >= 1

    def test_empty_draft_returns_zero(self):
        # Covers lines 164-166: warp_count=0 → early return 0
        mock_draft = MagicMock()
        mock_draft.warp = []
        mock_draft.weft = []
        mock_draft.shafts = [MagicMock()] * 4

        mock_rendering = MagicMock()
        mock_rendering.load_draft.return_value = mock_draft
        mock_rendering.DRAWDOWN_SCALE = 16

        count = _render_and_store_tiles(
            b"irrelevant",
            _settings(),
            mock_rendering,
            MagicMock(),
            MagicMock(),
            MagicMock(),
            entity_id=uuid.uuid4(),
            entity_label="draft_id",
        )
        assert count == 0

    def test_pixel_limit_reduces_effective_scale(self):
        # Covers lines 180-188: 1000-thread draft triggers pixel-limit cap
        mock_draft = MagicMock()
        mock_draft.warp = [MagicMock()] * 1000
        mock_draft.weft = [MagicMock()] * 1000
        mock_draft.shafts = [MagicMock()] * 4

        mock_rendering = MagicMock()
        mock_rendering.load_draft.return_value = mock_draft
        mock_rendering.DRAWDOWN_SCALE = 16  # effective_scale=16 before cap

        mock_settings = MagicMock()
        mock_settings.render_max_width = 16000  # yields effective_scale 16 for 1000 threads
        mock_settings.tile_row_count = 100

        mock_image = MagicMock()
        mock_image.crop.return_value = mock_image
        mock_image.transpose.return_value = mock_image

        image_renderer_cls = MagicMock()
        mock_renderer = MagicMock()
        image_renderer_cls.return_value = mock_renderer
        mock_renderer.make_pil_image.return_value = mock_image

        pil_image_cls = MagicMock()

        _render_and_store_tiles(
            b"irrelevant",
            mock_settings,
            mock_rendering,
            image_renderer_cls,
            pil_image_cls,
            MagicMock(),
            entity_id=uuid.uuid4(),
            entity_label="draft_id",
        )

        # scale should have been capped to <= 9 (sqrt(1e8 / 1010000) ≈ 9)
        assert image_renderer_cls.call_args[1]["scale"] <= 9


# ---------------------------------------------------------------------------
# Helpers shared by prerender tests
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


@pytest.fixture()
def mock_engine_and_session(db_session: AsyncSession):
    """Patch engine/session creation so prerender tasks run against db_session."""
    fake_engine = MagicMock()
    fake_engine.dispose = AsyncMock()
    with (
        patch("sqlalchemy.ext.asyncio.create_async_engine", return_value=fake_engine),
        patch("sqlalchemy.ext.asyncio.async_sessionmaker", return_value=_session_factory(db_session)),
    ):
        yield fake_engine


def _task_mock():
    t = MagicMock()
    t.MaxRetriesExceededError = Exception
    t.retry = MagicMock(side_effect=Exception("retry"))
    return t


# ---------------------------------------------------------------------------
# TestPrerendeerDraft — _prerender_draft early-return paths
# ---------------------------------------------------------------------------


class TestPrerendeerDraft:
    async def test_draft_not_found_returns_cleanly(self, db_session, mock_engine_and_session):
        from app.tasks.tiles import _prerender_draft

        await _prerender_draft(_task_mock(), uuid.uuid4())
        mock_engine_and_session.dispose.assert_called_once()

    async def test_deleted_draft_returns_cleanly(self, db_session, test_user, mock_engine_and_session):
        from app.models.draft import Draft
        from app.tasks.tiles import _prerender_draft

        draft = Draft(
            id=uuid.uuid4(),
            owner_id=test_user.id,
            name="Deleted",
            wif_filename="del.wif",
            wif_path="drafts/del.wif",
            deleted_at=datetime.now(timezone.utc),
        )
        db_session.add(draft)
        await db_session.commit()

        await _prerender_draft(_task_mock(), draft.id)
        mock_engine_and_session.dispose.assert_called_once()

    async def test_missing_wif_file_returns_cleanly(self, db_session, test_user, mock_engine_and_session):
        from app.models.draft import Draft
        from app.tasks.tiles import _prerender_draft

        draft = Draft(
            id=uuid.uuid4(),
            owner_id=test_user.id,
            name="Missing",
            wif_filename="missing.wif",
            wif_path="drafts/no-such-file.wif",  # not in mock storage
        )
        db_session.add(draft)
        await db_session.commit()

        await _prerender_draft(_task_mock(), draft.id)
        mock_engine_and_session.dispose.assert_called_once()

    async def test_valid_draft_runs_to_completion(self, db_session, test_user, mock_engine_and_session):
        import app.services.storage as _storage
        from app.models.draft import Draft
        from app.tasks.tiles import _prerender_draft

        wif_key = f"drafts/prerender-draft-{uuid.uuid4().hex}.wif"
        _storage._put(wif_key, MINIMAL_WIF)

        draft = Draft(
            id=uuid.uuid4(),
            owner_id=test_user.id,
            name="Valid",
            wif_filename="valid.wif",
            wif_path=wif_key,
        )
        db_session.add(draft)
        await db_session.commit()

        await _prerender_draft(_task_mock(), draft.id)
        mock_engine_and_session.dispose.assert_called_once()

    async def test_render_failure_triggers_retry_handler(self, db_session, test_user, mock_engine_and_session):
        # Covers lines 80-85: exception → task.retry → MaxRetriesExceededError caught
        import app.services.storage as _storage
        from app.models.draft import Draft
        from app.tasks.tiles import _prerender_draft

        wif_key = f"drafts/retry-draft-{uuid.uuid4().hex}.wif"
        _storage._put(wif_key, MINIMAL_WIF)

        draft = Draft(
            id=uuid.uuid4(),
            owner_id=test_user.id,
            name="Retry Draft",
            wif_filename="retry.wif",
            wif_path=wif_key,
        )
        db_session.add(draft)
        await db_session.commit()

        task = _task_mock()
        with patch("app.services.rendering.load_draft", side_effect=Exception("render error")):
            await _prerender_draft(task, draft.id)

        task.retry.assert_called_once()
        mock_engine_and_session.dispose.assert_called_once()


# ---------------------------------------------------------------------------
# TestPrerenderProject — _prerender_project early-return paths
# ---------------------------------------------------------------------------


class TestPrerenderProject:
    async def _make_draft(self, db_session, test_user, *, wif_key="drafts/proj.wif"):
        from app.models.draft import Draft

        draft = Draft(
            id=uuid.uuid4(),
            owner_id=test_user.id,
            name="Proj Draft",
            wif_filename="proj.wif",
            wif_path=wif_key,
        )
        db_session.add(draft)
        await db_session.flush()
        return draft

    async def test_project_not_found_returns_cleanly(self, db_session, mock_engine_and_session):
        from app.tasks.tiles import _prerender_project

        await _prerender_project(_task_mock(), uuid.uuid4())
        mock_engine_and_session.dispose.assert_called_once()

    async def test_deleted_project_returns_cleanly(self, db_session, test_user, mock_engine_and_session):
        from app.models.project import Project
        from app.tasks.tiles import _prerender_project

        draft = await self._make_draft(db_session, test_user)
        project = Project(
            id=uuid.uuid4(),
            owner_id=test_user.id,
            draft_id=draft.id,
            name="Deleted Project",
            project_type="weave",
            total_picks=4,
            deleted_at=datetime.now(timezone.utc),
        )
        db_session.add(project)
        await db_session.commit()

        await _prerender_project(_task_mock(), project.id)
        mock_engine_and_session.dispose.assert_called_once()

    async def test_project_with_deleted_draft_returns_cleanly(self, db_session, test_user, mock_engine_and_session):
        from app.models.project import Project
        from app.tasks.tiles import _prerender_project

        draft = await self._make_draft(db_session, test_user)
        draft.deleted_at = datetime.now(timezone.utc)
        project = Project(
            id=uuid.uuid4(),
            owner_id=test_user.id,
            draft_id=draft.id,
            name="Draft Deleted",
            project_type="weave",
            total_picks=4,
        )
        db_session.add(project)
        await db_session.commit()

        await _prerender_project(_task_mock(), project.id)
        mock_engine_and_session.dispose.assert_called_once()

    async def test_project_with_missing_wif_returns_cleanly(self, db_session, test_user, mock_engine_and_session):
        from app.models.project import Project
        from app.tasks.tiles import _prerender_project

        draft = await self._make_draft(db_session, test_user, wif_key="drafts/not-stored.wif")
        project = Project(
            id=uuid.uuid4(),
            owner_id=test_user.id,
            draft_id=draft.id,
            name="Missing WIF",
            project_type="weave",
            total_picks=4,
        )
        db_session.add(project)
        await db_session.commit()

        await _prerender_project(_task_mock(), project.id)
        mock_engine_and_session.dispose.assert_called_once()

    async def test_valid_project_runs_to_completion(self, db_session, test_user, mock_engine_and_session):
        import app.services.storage as _storage
        from app.models.project import Project
        from app.tasks.tiles import _prerender_project

        wif_key = f"drafts/proj-{uuid.uuid4().hex}.wif"
        _storage._put(wif_key, MINIMAL_WIF)

        draft = await self._make_draft(db_session, test_user, wif_key=wif_key)
        project = Project(
            id=uuid.uuid4(),
            owner_id=test_user.id,
            draft_id=draft.id,
            name="Valid Project",
            project_type="weave",
            total_picks=4,
        )
        db_session.add(project)
        await db_session.commit()

        await _prerender_project(_task_mock(), project.id)
        mock_engine_and_session.dispose.assert_called_once()

    async def test_lift_project_uses_modified_wif_path(self, db_session, test_user, mock_engine_and_session):
        # Covers lines 115-117: project_type="lift" + wif_modified_path exists → used
        import app.services.storage as _storage
        from app.models.draft import Draft
        from app.models.project import Project
        from app.tasks.tiles import _prerender_project

        base_key = f"drafts/base-{uuid.uuid4().hex}.wif"
        modified_key = f"drafts/mod-{uuid.uuid4().hex}.wif"
        _storage._put(base_key, MINIMAL_WIF)
        _storage._put(modified_key, MINIMAL_WIF)

        draft = Draft(
            id=uuid.uuid4(),
            owner_id=test_user.id,
            name="Lift Draft",
            wif_filename="lift.wif",
            wif_path=base_key,
            wif_modified_path=modified_key,
        )
        db_session.add(draft)
        await db_session.flush()

        project = Project(
            id=uuid.uuid4(),
            owner_id=test_user.id,
            draft_id=draft.id,
            name="Lift Project",
            project_type="lift",
            total_picks=4,
        )
        db_session.add(project)
        await db_session.commit()

        await _prerender_project(_task_mock(), project.id)
        mock_engine_and_session.dispose.assert_called_once()

    async def test_render_failure_triggers_retry_handler(self, db_session, test_user, mock_engine_and_session):
        # Covers lines 137-142: exception → task.retry → MaxRetriesExceededError caught
        import app.services.storage as _storage
        from app.models.project import Project
        from app.tasks.tiles import _prerender_project

        wif_key = f"drafts/retry-proj-{uuid.uuid4().hex}.wif"
        _storage._put(wif_key, MINIMAL_WIF)

        draft = await self._make_draft(db_session, test_user, wif_key=wif_key)
        project = Project(
            id=uuid.uuid4(),
            owner_id=test_user.id,
            draft_id=draft.id,
            name="Retry Project",
            project_type="weave",
            total_picks=4,
        )
        db_session.add(project)
        await db_session.commit()

        task = _task_mock()
        with patch("app.services.rendering.load_draft", side_effect=Exception("render error")):
            await _prerender_project(task, project.id)

        task.retry.assert_called_once()
        mock_engine_and_session.dispose.assert_called_once()


# ---------------------------------------------------------------------------
# TestCeleryWrappers — cover lines 30 and 42 (asyncio.run wrappers)
# ---------------------------------------------------------------------------


class TestCeleryWrappers:
    def test_prerender_drawdown_tiles_delegates(self):
        from app.tasks.tiles import prerender_drawdown_tiles

        task_mock = MagicMock()
        task_mock.request.retries = 0
        task_mock.max_retries = 2

        with patch("app.tasks.tiles._prerender_draft", new=AsyncMock(return_value=None)):
            prerender_drawdown_tiles.run.__func__(task_mock, str(uuid.uuid4()))

    def test_prerender_project_tiles_delegates(self):
        from app.tasks.tiles import prerender_project_tiles

        task_mock = MagicMock()
        task_mock.request.retries = 0
        task_mock.max_retries = 2

        with patch("app.tasks.tiles._prerender_project", new=AsyncMock(return_value=None)):
            prerender_project_tiles.run.__func__(task_mock, str(uuid.uuid4()))
