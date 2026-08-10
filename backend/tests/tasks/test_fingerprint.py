"""Tests for app.tasks.fingerprint async inner functions.

Mirrors tests/tasks/test_preview.py's structure — both tasks create their own
DB engine, redirected to db_session via the same sqlalchemy-level patch.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.tasks.fingerprint import _backfill_all_drawdown_fingerprints, _compute_drawdown_fingerprint

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


@pytest.fixture
def mock_engine_and_session(db_session: AsyncSession):
    fake_engine = MagicMock()
    fake_engine.dispose = AsyncMock()
    with (
        patch("app.tasks.fingerprint.create_async_engine", return_value=fake_engine),
        patch("app.tasks.fingerprint.async_sessionmaker", return_value=_session_factory(db_session)),
    ):
        yield fake_engine


# ---------------------------------------------------------------------------
# TestComputeDrawdownFingerprint
# ---------------------------------------------------------------------------


class TestComputeDrawdownFingerprint:
    async def _make_draft(self, db_session, test_user, wif_path=None, deleted=False):
        from app.models.draft import Draft

        draft = Draft(
            id=uuid.uuid4(),
            owner_id=test_user.id,
            name="Fingerprint Draft",
            wif_filename="test.wif",
            wif_path=wif_path or "drafts/test.wif",
        )
        if deleted:
            draft.deleted_at = datetime.now(timezone.utc)
        db_session.add(draft)
        await db_session.commit()
        return draft

    async def test_draft_not_found_returns_cleanly(self, db_session, mock_engine_and_session):
        await _compute_drawdown_fingerprint(_task_mock(), uuid.uuid4())

    async def test_deleted_draft_returns_cleanly(self, db_session, test_user, mock_engine_and_session):
        draft = await self._make_draft(db_session, test_user, deleted=True)
        await _compute_drawdown_fingerprint(_task_mock(), draft.id)

    async def test_wif_not_in_storage_returns_cleanly(
        self, db_session, test_user, mock_engine_and_session, mock_storage
    ):
        draft = await self._make_draft(db_session, test_user, wif_path="drafts/missing.wif")
        await _compute_drawdown_fingerprint(_task_mock(), draft.id)

    async def test_valid_draft_sets_drawdown_fingerprint(
        self, db_session, test_user, mock_engine_and_session, mock_storage
    ):
        draft = await self._make_draft(db_session, test_user, wif_path="drafts/valid.wif")
        mock_storage["drafts/valid.wif"] = MINIMAL_WIF

        await _compute_drawdown_fingerprint(_task_mock(), draft.id)

        await db_session.refresh(draft)
        assert draft.drawdown_fingerprint is not None

    async def test_engine_disposed_on_success(self, db_session, test_user, mock_engine_and_session, mock_storage):
        draft = await self._make_draft(db_session, test_user, wif_path="drafts/disp.wif")
        mock_storage["drafts/disp.wif"] = MINIMAL_WIF

        await _compute_drawdown_fingerprint(_task_mock(), draft.id)

        mock_engine_and_session.dispose.assert_called_once()

    async def test_engine_disposed_on_missing_draft(self, db_session, mock_engine_and_session):
        await _compute_drawdown_fingerprint(_task_mock(), uuid.uuid4())
        mock_engine_and_session.dispose.assert_called_once()

    async def test_rendering_error_retries(self, db_session, test_user, mock_engine_and_session, mock_storage):
        draft = await self._make_draft(db_session, test_user, wif_path="drafts/err.wif")
        mock_storage["drafts/err.wif"] = MINIMAL_WIF

        task = _task_mock(retries=0, max_retries=2)

        with patch("app.services.fingerprints.compute_drawdown_fingerprint", side_effect=RuntimeError("render fail")):
            await _compute_drawdown_fingerprint(task, draft.id)

        task.retry.assert_called_once()

    async def test_rendering_error_at_max_retries_does_not_raise(
        self, db_session, test_user, mock_engine_and_session, mock_storage
    ):
        draft = await self._make_draft(db_session, test_user, wif_path="drafts/max.wif")
        mock_storage["drafts/max.wif"] = MINIMAL_WIF

        task = _task_mock(retries=2, max_retries=2)
        task.MaxRetriesExceededError = Exception

        with patch("app.services.fingerprints.compute_drawdown_fingerprint", side_effect=RuntimeError("fail")):
            await _compute_drawdown_fingerprint(task, draft.id)  # must not raise


# ---------------------------------------------------------------------------
# TestBackfillAllDrawdownFingerprints
# ---------------------------------------------------------------------------


class TestBackfillAllDrawdownFingerprints:
    async def test_empty_database_returns_zeros(self, db_session, mock_engine_and_session):
        result = await _backfill_all_drawdown_fingerprints()
        assert result == {"dispatched": 0, "skipped": 0}

    async def test_engine_disposed(self, db_session, mock_engine_and_session):
        await _backfill_all_drawdown_fingerprints()
        mock_engine_and_session.dispose.assert_called_once()

    async def test_draft_missing_wif_file_is_skipped(self, db_session, test_user, mock_engine_and_session):
        from app.models.draft import Draft

        draft = Draft(
            id=uuid.uuid4(),
            owner_id=test_user.id,
            name="No WIF on disk",
            wif_filename="missing.wif",
            wif_path="drafts/not-there.wif",
        )
        db_session.add(draft)
        await db_session.commit()

        result = await _backfill_all_drawdown_fingerprints()
        assert result["skipped"] == 1
        assert result["dispatched"] == 0

    async def test_draft_with_valid_wif_is_dispatched(
        self, db_session, test_user, mock_engine_and_session, mock_storage
    ):
        from app.models.draft import Draft

        wif_key = f"drafts/backfill-{uuid.uuid4().hex}.wif"
        mock_storage[wif_key] = MINIMAL_WIF

        draft = Draft(
            id=uuid.uuid4(),
            owner_id=test_user.id,
            name="Backfill Me",
            wif_filename="valid.wif",
            wif_path=wif_key,
        )
        db_session.add(draft)
        await db_session.commit()

        with patch("app.tasks.fingerprint.compute_draft_drawdown_fingerprint") as mock_task:
            result = await _backfill_all_drawdown_fingerprints()

        assert result["dispatched"] == 1
        assert result["skipped"] == 0
        mock_task.delay.assert_called_once_with(str(draft.id))

    async def test_draft_already_fingerprinted_is_excluded(
        self, db_session, test_user, mock_engine_and_session, mock_storage
    ):
        from app.models.draft import Draft

        wif_key = f"drafts/done-{uuid.uuid4().hex}.wif"
        mock_storage[wif_key] = MINIMAL_WIF

        draft = Draft(
            id=uuid.uuid4(),
            owner_id=test_user.id,
            name="Already Done",
            wif_filename="done.wif",
            wif_path=wif_key,
            drawdown_fingerprint="a" * 64,
        )
        db_session.add(draft)
        await db_session.commit()

        result = await _backfill_all_drawdown_fingerprints()
        assert result["dispatched"] == 0
        assert result["skipped"] == 0

    async def test_deleted_draft_excluded(self, db_session, test_user, mock_engine_and_session, mock_storage):
        from app.models.draft import Draft

        wif_key = f"drafts/deleted-{uuid.uuid4().hex}.wif"
        mock_storage[wif_key] = MINIMAL_WIF

        draft = Draft(
            id=uuid.uuid4(),
            owner_id=test_user.id,
            name="Deleted",
            wif_filename="deleted.wif",
            wif_path=wif_key,
            deleted_at=datetime.now(timezone.utc),
        )
        db_session.add(draft)
        await db_session.commit()

        result = await _backfill_all_drawdown_fingerprints()
        assert result["dispatched"] == 0
        assert result["skipped"] == 0


# ---------------------------------------------------------------------------
# TestCeleryWrappers — cover the asyncio.run wrapper lines
# ---------------------------------------------------------------------------


class TestCeleryWrappers:
    def test_compute_draft_drawdown_fingerprint_delegates(self):
        from app.tasks.fingerprint import compute_draft_drawdown_fingerprint

        task_mock = MagicMock()
        with patch("app.tasks.fingerprint._compute_drawdown_fingerprint", new=AsyncMock(return_value=None)):
            compute_draft_drawdown_fingerprint.run.__func__(task_mock, str(uuid.uuid4()))

    def test_backfill_all_drawdown_fingerprints_delegates(self):
        from app.tasks.fingerprint import backfill_all_drawdown_fingerprints

        task_mock = MagicMock()
        with patch(
            "app.tasks.fingerprint._backfill_all_drawdown_fingerprints",
            new=AsyncMock(return_value={"dispatched": 0, "skipped": 0}),
        ):
            result = backfill_all_drawdown_fingerprints.run.__func__(task_mock)

        assert result == {"dispatched": 0, "skipped": 0}
