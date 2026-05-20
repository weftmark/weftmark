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


@pytest.fixture()
def mock_redis():
    """Return a mock Redis client that always acquires the SETNX lock."""
    client = MagicMock()
    client.set.return_value = True  # SETNX succeeds — lock acquired
    client.close.return_value = None
    return client


@pytest.fixture()
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
