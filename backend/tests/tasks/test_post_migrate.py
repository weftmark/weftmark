"""Tests for app.tasks.post_migrate.

The task is called via _run() directly (bypassing Celery plumbing).
DB interactions use the test database via the _use_test_db fixture.
Redis calls are monkeypatched so no real Redis instance is needed.
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock, patch

import pytest

_PG_TEST_DB = "test_weaving_site"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _use_test_db(monkeypatch, db_available):
    import os

    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "postgres_db", _PG_TEST_DB)
    monkeypatch.setattr(settings, "postgres_dsn", "")
    monkeypatch.setattr(settings, "postgres_dsn_direct", "")
    monkeypatch.setattr(settings, "postgres_host", os.getenv("POSTGRES_HOST", "localhost"))
    monkeypatch.setattr(settings, "postgres_port", int(os.getenv("POSTGRES_PORT", "5433")))


@pytest.fixture
def mock_redis():
    """Return a mock Redis client that always acquires the SETNX lock."""
    client = MagicMock()
    client.set.return_value = True  # SETNX succeeds — lock acquired
    client.close.return_value = None
    return client


@pytest.fixture
def mock_redis_locked():
    """Return a mock Redis client where the SETNX lock is already held."""
    client = MagicMock()
    client.set.return_value = None  # SETNX fails — lock not acquired
    client.close.return_value = None
    return client


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run(redis_client=None):
    """Call _run() with a patched Redis client."""
    from app.tasks.post_migrate import _run as post_migrate_run

    if redis_client is None:
        redis_client = MagicMock()
        redis_client.set.return_value = True

    with patch("app.tasks.post_migrate._redis") as mock_redis_module:
        mock_redis_module.from_url.return_value = redis_client
        return post_migrate_run()


async def _seed_draft(db_session, owner_id, *, wif_colors=None, deleted=False):
    """Insert a draft row and commit.

    When wif_colors is None, the column is omitted from the INSERT so PostgreSQL
    stores SQL NULL — not the JSON 'null'::jsonb that SQLAlchemy's JSONB type
    produces when Python None is passed explicitly (none_as_null defaults to False).
    The backfill condition checks `wif_colors IS NULL`, which only matches SQL NULL.
    """
    from sqlalchemy import text

    uid = str(uuid.uuid4())
    if wif_colors is None:
        # Omit wif_colors → SQL NULL default; include deleted_at when needed
        _bool_defaults = "FALSE, FALSE, FALSE, FALSE, FALSE, FALSE, FALSE, FALSE"
        _jsonb_defaults = "'[]'::jsonb, '[]'::jsonb, '[]'::jsonb"
        _bool_cols = (
            "has_threading, has_tieup, has_treadling, has_liftplan, has_color_palette, "
            "liftplan_generated, warp_length_overridden, is_shared"
        )
        _jsonb_cols = "lint_warnings, lint_errors, tags"
        if deleted:
            sql = text(
                "INSERT INTO drafts "
                f"(id, owner_id, name, wif_filename, wif_path, {_bool_cols}, {_jsonb_cols}, "
                "deleted_at, created_at, updated_at) "
                f"VALUES (:id, :owner, :name, :wif_fn, :wif_path, {_bool_defaults}, {_jsonb_defaults}, "
                "NOW(), NOW(), NOW())"
            )
        else:
            sql = text(
                "INSERT INTO drafts "
                f"(id, owner_id, name, wif_filename, wif_path, {_bool_cols}, {_jsonb_cols}, "
                "created_at, updated_at) "
                f"VALUES (:id, :owner, :name, :wif_fn, :wif_path, {_bool_defaults}, {_jsonb_defaults}, "
                "NOW(), NOW())"
            )
        await db_session.execute(
            sql,
            {
                "id": str(uuid.uuid4()),
                "owner": str(owner_id),
                "name": f"test-{uid}",
                "wif_fn": "test.wif",
                "wif_path": f"drafts/{uid}.wif",
            },
        )
    else:
        from app.models.draft import Draft

        d = Draft(
            id=uuid.uuid4(),
            owner_id=owner_id,
            name=f"test-{uid}",
            wif_filename="test.wif",
            wif_path=f"drafts/{uid}.wif",
            wif_colors=wif_colors,
        )
        if deleted:
            from datetime import datetime, timezone

            d.deleted_at = datetime.now(timezone.utc)
        db_session.add(d)
    await db_session.commit()


_REPARSE_CONDITION = (
    "SELECT COUNT(*) FROM drafts WHERE wif_colors IS NULL AND wif_path IS NOT NULL AND deleted_at IS NULL"
)


def _reparse_registry_entry(dispatch_fn):
    return {
        "name": "reparse_drafts",
        "description": "test",
        "condition": _REPARSE_CONDITION,
        "dispatch": dispatch_fn,
    }


# ---------------------------------------------------------------------------
# No null rows — nothing to dispatch
# ---------------------------------------------------------------------------


class TestNoNullRows:
    def test_skips_all_when_table_empty(self):
        """With no drafts in the DB, draft backfill is skipped."""
        with patch("app.tasks.post_migrate._backfill_registry") as mock_registry:
            mock_registry.return_value = [_reparse_registry_entry(lambda: None)]
            result = _run()
        assert result["dispatched"] == []
        assert any("no_null_rows" in s for s in result["skipped"])

    async def test_skips_when_all_drafts_have_wif_colors(self, db_session, test_user):
        """Drafts that already have wif_colors set are not counted."""
        await _seed_draft(db_session, test_user.id, wif_colors=[1, 2, 3])

        with patch("app.tasks.post_migrate._backfill_registry") as mock_registry:
            mock_registry.return_value = [_reparse_registry_entry(lambda: None)]
            result = _run()
        assert result["dispatched"] == []
        assert any("no_null_rows" in s for s in result["skipped"])


# ---------------------------------------------------------------------------
# Null rows present — backfill should dispatch
# ---------------------------------------------------------------------------


class TestNullRowsPresent:
    async def test_dispatches_reparse_when_wif_colors_null(self, db_session, test_user, mock_redis):
        """A draft with wif_path but null wif_colors triggers reparse_all_drafts dispatch."""
        await _seed_draft(db_session, test_user.id, wif_colors=None)

        dispatched_tasks: list[str] = []
        with patch("app.tasks.post_migrate._backfill_registry") as mock_registry:
            mock_registry.return_value = [
                _reparse_registry_entry(lambda: dispatched_tasks.append("reparse_all_drafts"))
            ]
            result = _run(mock_redis)

        assert len(result["dispatched"]) == 1
        assert "reparse_drafts" in result["dispatched"][0]
        assert result["dispatched"][0].endswith("(null_rows=1)")

    async def test_deleted_drafts_not_counted(self, db_session, test_user):
        """Soft-deleted drafts with null wif_colors must not trigger dispatch."""
        await _seed_draft(db_session, test_user.id, wif_colors=None, deleted=True)

        with patch("app.tasks.post_migrate._backfill_registry") as mock_registry:
            mock_registry.return_value = [_reparse_registry_entry(lambda: None)]
            result = _run()
        assert result["dispatched"] == []
        assert any("no_null_rows" in s for s in result["skipped"])


# ---------------------------------------------------------------------------
# Redis lock held — duplicate dispatch prevention
# ---------------------------------------------------------------------------


class TestRedisLockHeld:
    async def test_skips_when_lock_already_held(self, db_session, test_user, mock_redis_locked):
        """If Redis lock is held (another worker already dispatched), skip without dispatching."""
        await _seed_draft(db_session, test_user.id, wif_colors=None)

        dispatched: list[str] = []
        with patch("app.tasks.post_migrate._backfill_registry") as mock_registry:
            mock_registry.return_value = [_reparse_registry_entry(lambda: dispatched.append("called"))]
            result = _run(mock_redis_locked)

        assert result["dispatched"] == []
        assert dispatched == []
        assert any("lock_held" in s for s in result["skipped"])

    async def test_lock_released_on_dispatch_error(self, db_session, test_user, mock_redis):
        """If dispatch raises, the Redis lock is released so the next worker can retry."""
        await _seed_draft(db_session, test_user.id, wif_colors=None)

        with patch("app.tasks.post_migrate._backfill_registry") as mock_registry:
            mock_registry.return_value = [
                _reparse_registry_entry(lambda: (_ for _ in ()).throw(RuntimeError("broker down")))
            ]
            result = _run(mock_redis)

        mock_redis.delete.assert_called_once()
        assert result["dispatched"] == []


# ---------------------------------------------------------------------------
# Return structure
# ---------------------------------------------------------------------------


class TestReturnStructure:
    def test_returns_dispatched_and_skipped_keys(self):
        result = _run()
        assert "dispatched" in result
        assert "skipped" in result
        assert isinstance(result["dispatched"], list)
        assert isinstance(result["skipped"], list)


# ---------------------------------------------------------------------------
# New fingerprint backfill entries (#983)
#
# Uses the mocked-registry mechanism (like every test above) for dispatch
# behavior — it's entry-agnostic and already proven generic. What's NOT
# already covered is whether the two new entries' raw SQL condition strings
# and task names are actually correct (a typo in a column name isn't caught
# by mypy/ruff) — verified by running the real _backfill_registry()'s
# condition SQL directly against the test DB, without ever dispatching.
# ---------------------------------------------------------------------------


class TestFingerprintRegistryEntries:
    def test_registry_includes_both_new_entries(self):
        from app.tasks.post_migrate import _backfill_registry

        registry = _backfill_registry()
        by_name = {e["name"]: e for e in registry}
        assert "draft_fingerprints" in by_name
        assert by_name["draft_fingerprints"]["task_name"] == "app.tasks.reparse.backfill_draft_fingerprints"
        assert "drawdown_fingerprint" in by_name
        assert (
            by_name["drawdown_fingerprint"]["task_name"] == "app.tasks.fingerprint.backfill_all_drawdown_fingerprints"
        )

    async def test_draft_fingerprints_condition_zero_when_empty(self, db_session):
        from sqlalchemy import text

        from app.tasks.post_migrate import _backfill_registry

        entry = next(e for e in _backfill_registry() if e["name"] == "draft_fingerprints")
        count = await db_session.scalar(text(entry["condition"]))
        assert count == 0

    async def test_draft_fingerprints_condition_counts_unfingerprinted_draft(self, db_session, test_user):
        from sqlalchemy import text

        from app.models.draft import Draft
        from app.tasks.post_migrate import _backfill_registry

        draft = Draft(
            id=uuid.uuid4(),
            owner_id=test_user.id,
            name="Needs fingerprint",
            wif_filename="test.wif",
            wif_path="drafts/needs-fp.wif",
        )
        db_session.add(draft)
        await db_session.commit()

        entry = next(e for e in _backfill_registry() if e["name"] == "draft_fingerprints")
        count = await db_session.scalar(text(entry["condition"]))
        assert count == 1

        draft.threading_fingerprint = "a" * 64
        await db_session.commit()
        count_after = await db_session.scalar(text(entry["condition"]))
        assert count_after == 0

    async def test_drawdown_fingerprint_condition_zero_when_empty(self, db_session):
        from sqlalchemy import text

        from app.tasks.post_migrate import _backfill_registry

        entry = next(e for e in _backfill_registry() if e["name"] == "drawdown_fingerprint")
        count = await db_session.scalar(text(entry["condition"]))
        assert count == 0

    async def test_drawdown_fingerprint_condition_counts_unfingerprinted_draft(self, db_session, test_user):
        from sqlalchemy import text

        from app.models.draft import Draft
        from app.tasks.post_migrate import _backfill_registry

        draft = Draft(
            id=uuid.uuid4(),
            owner_id=test_user.id,
            name="Needs drawdown fingerprint",
            wif_filename="test.wif",
            wif_path="drafts/needs-drawdown-fp.wif",
        )
        db_session.add(draft)
        await db_session.commit()

        entry = next(e for e in _backfill_registry() if e["name"] == "drawdown_fingerprint")
        count = await db_session.scalar(text(entry["condition"]))
        assert count == 1

        draft.drawdown_fingerprint = "b" * 64
        await db_session.commit()
        count_after = await db_session.scalar(text(entry["condition"]))
        assert count_after == 0


# ---------------------------------------------------------------------------
# record_queued on successful dispatch — pre-existing branch (_run lines
# ~176-188) that no test in this file exercised before: every dispatch lambda
# above returns None, so `result is not None and hasattr(result, "id")` was
# never true. A real Celery .delay() call returns an AsyncResult with .id.
# ---------------------------------------------------------------------------


class TestRecordQueuedOnDispatch:
    async def test_record_queued_called_when_dispatch_returns_task_result(self, db_session, test_user, mock_redis):
        await _seed_draft(db_session, test_user.id, wif_colors=None)

        fake_result = MagicMock()
        fake_result.id = "fake-task-id-123"

        with (
            patch("app.tasks.post_migrate._backfill_registry") as mock_registry,
            patch("app.services.task_history.record_queued") as mock_record_queued,
        ):
            mock_registry.return_value = [_reparse_registry_entry(lambda: fake_result)]
            result = _run(mock_redis)

        assert len(result["dispatched"]) == 1
        mock_record_queued.assert_called_once()
        assert mock_record_queued.call_args.args[1] == "fake-task-id-123"

    async def test_record_queued_failure_does_not_block_dispatch(self, db_session, test_user, mock_redis):
        """record_queued failures are caught and swallowed — a broken task-history
        write must never prevent the backfill dispatch itself from succeeding."""
        await _seed_draft(db_session, test_user.id, wif_colors=None)

        fake_result = MagicMock()
        fake_result.id = "fake-task-id-456"

        with (
            patch("app.tasks.post_migrate._backfill_registry") as mock_registry,
            patch("app.services.task_history.record_queued", side_effect=RuntimeError("db down")),
        ):
            mock_registry.return_value = [_reparse_registry_entry(lambda: fake_result)]
            result = _run(mock_redis)

        assert len(result["dispatched"]) == 1

    async def test_result_without_id_attribute_skips_record_queued(self, db_session, test_user, mock_redis):
        """A dispatch lambda returning a plain non-Celery value (e.g. None, like
        every other test in this file) must not attempt to call record_queued."""
        await _seed_draft(db_session, test_user.id, wif_colors=None)

        with (
            patch("app.tasks.post_migrate._backfill_registry") as mock_registry,
            patch("app.services.task_history.record_queued") as mock_record_queued,
        ):
            mock_registry.return_value = [_reparse_registry_entry(lambda: None)]
            result = _run(mock_redis)

        assert len(result["dispatched"]) == 1
        mock_record_queued.assert_not_called()


# ---------------------------------------------------------------------------
# TestCeleryWrapper — cover the run_post_migrate_backfills -> _run() delegation
# ---------------------------------------------------------------------------


class TestCeleryWrapper:
    def test_run_post_migrate_backfills_delegates(self):
        from app.tasks.post_migrate import run_post_migrate_backfills

        task_mock = MagicMock()
        with patch("app.tasks.post_migrate._run", return_value={"dispatched": [], "skipped": []}):
            result = run_post_migrate_backfills.run.__func__(task_mock)

        assert result == {"dispatched": [], "skipped": []}
