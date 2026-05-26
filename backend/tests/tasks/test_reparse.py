"""Tests for app.tasks.reparse._reparse_all."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

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


@pytest.fixture()
def mock_engine_and_session(db_session: AsyncSession):
    fake_engine = MagicMock()
    fake_engine.dispose = AsyncMock()
    with (
        patch("app.tasks.reparse.create_async_engine", return_value=fake_engine),
        patch("app.tasks.reparse.async_sessionmaker", return_value=_session_factory(db_session)),
    ):
        yield fake_engine


# ---------------------------------------------------------------------------
# TestReparseAll
# ---------------------------------------------------------------------------


class TestReparseAll:
    async def test_returns_expected_keys(self, db_session, mock_engine_and_session):
        from app.tasks.reparse import _reparse_all

        result = await _reparse_all()
        assert "updated" in result
        assert "skipped" in result
        assert "errors" in result

    async def test_empty_database_returns_zeros(self, db_session, mock_engine_and_session):
        from app.tasks.reparse import _reparse_all

        result = await _reparse_all()
        assert result["updated"] == 0
        assert result["skipped"] == 0
        assert result["errors"] == 0

    async def test_engine_disposed(self, db_session, mock_engine_and_session):
        from app.tasks.reparse import _reparse_all

        await _reparse_all()
        mock_engine_and_session.dispose.assert_called_once()

    async def test_draft_without_wif_path_is_skipped(self, db_session, test_user, mock_engine_and_session):
        from app.models.draft import Draft
        from app.tasks.reparse import _reparse_all

        # wif_path is NOT NULL in the schema; use a non-existing path so
        # file_exists() returns False and the draft is counted as skipped.
        draft = Draft(
            id=uuid.uuid4(),
            owner_id=test_user.id,
            name="No WIF",
            wif_filename="nope.wif",
            wif_path="drafts/nope-not-here.wif",
        )
        db_session.add(draft)
        await db_session.commit()

        result = await _reparse_all()
        assert result["skipped"] >= 1
        assert result["updated"] == 0

    async def test_draft_with_wif_path_but_file_missing_is_skipped(
        self, db_session, test_user, mock_engine_and_session
    ):
        from app.models.draft import Draft
        from app.tasks.reparse import _reparse_all

        draft = Draft(
            id=uuid.uuid4(),
            owner_id=test_user.id,
            name="Missing File",
            wif_filename="missing.wif",
            wif_path="drafts/no-such-file.wif",
        )
        db_session.add(draft)
        await db_session.commit()

        result = await _reparse_all()
        assert result["skipped"] >= 1
        assert result["updated"] == 0

    async def test_draft_with_valid_wif_is_updated(self, db_session, test_user, mock_engine_and_session):
        import app.services.storage as _storage
        from app.models.draft import Draft
        from app.tasks.reparse import _reparse_all

        wif_key = f"drafts/reparse-{uuid.uuid4().hex}.wif"
        _storage._put(wif_key, MINIMAL_WIF)

        draft = Draft(
            id=uuid.uuid4(),
            owner_id=test_user.id,
            name="Valid WIF",
            wif_filename="valid.wif",
            wif_path=wif_key,
        )
        db_session.add(draft)
        await db_session.commit()

        result = await _reparse_all()
        assert result["updated"] >= 1
        assert result["skipped"] == 0

    async def test_deleted_draft_excluded(self, db_session, test_user, mock_engine_and_session):
        import app.services.storage as _storage
        from app.models.draft import Draft
        from app.tasks.reparse import _reparse_all

        wif_key = f"drafts/deleted-{uuid.uuid4().hex}.wif"
        _storage._put(wif_key, MINIMAL_WIF)

        draft = Draft(
            id=uuid.uuid4(),
            owner_id=test_user.id,
            name="Deleted Draft",
            wif_filename="deleted.wif",
            wif_path=wif_key,
            deleted_at=datetime.now(timezone.utc),
        )
        db_session.add(draft)
        await db_session.commit()

        result = await _reparse_all()
        # Deleted drafts are excluded by the WHERE clause
        assert result["updated"] == 0
        assert result["skipped"] == 0


# ---------------------------------------------------------------------------
# TestCeleryWrapper — cover line 23 (asyncio.run wrapper)
# ---------------------------------------------------------------------------


class TestCeleryWrapper:
    def test_reparse_all_drafts_delegates(self):
        from app.tasks.reparse import reparse_all_drafts

        task_mock = MagicMock()

        with patch(
            "app.tasks.reparse._reparse_all",
            new=AsyncMock(return_value={"updated": 0, "skipped": 0, "errors": 0}),
        ):
            result = reparse_all_drafts.run.__func__(task_mock)

        assert result["errors"] == 0


# ---------------------------------------------------------------------------
# TestReparseErrors — cover lines 68-70 (exception handler per-draft)
# ---------------------------------------------------------------------------


class TestReparseErrors:
    async def test_parse_error_counted_not_raised(self, db_session, test_user, mock_engine_and_session):
        import app.services.storage as _storage
        from app.models.draft import Draft
        from app.tasks.reparse import _reparse_all

        wif_key = f"drafts/bad-{uuid.uuid4().hex}.wif"
        _storage._put(wif_key, b"[WIF]\ncorrupted=garbage")

        draft = Draft(
            id=uuid.uuid4(),
            owner_id=test_user.id,
            name="Bad WIF",
            wif_filename="bad.wif",
            wif_path=wif_key,
        )
        db_session.add(draft)
        await db_session.commit()

        with patch("app.services.wif_parser.extract_measurements", side_effect=Exception("parse failed")):
            result = await _reparse_all()

        assert result["errors"] >= 1
        assert result["updated"] == 0
