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


def _make_draft(owner_id, *, wif_colors=None, deleted=False):
    """Build an unsaved Draft ORM instance for seeding."""
    from app.models.draft import Draft

    uid = str(uuid.uuid4())
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
    return d


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
        """With no drafts in the DB at all, backfill is skipped."""
        result = _run()
        assert result["dispatched"] == []
        assert any("no_null_rows" in s for s in result["skipped"])

    async def test_skips_when_all_drafts_have_wif_colors(self, db_session, test_user):
        """Drafts that already have wif_colors set are not counted."""
        d = _make_draft(test_user.id, wif_colors=[1, 2, 3])
        db_session.add(d)
        await db_session.commit()

        result = _run()
        assert result["dispatched"] == []
        assert any("no_null_rows" in s for s in result["skipped"])


# ---------------------------------------------------------------------------
# Null rows present — backfill should dispatch
# ---------------------------------------------------------------------------


class TestNullRowsPresent:
    async def test_dispatches_reparse_when_wif_colors_null(self, db_session, test_user, mock_redis):
        """A draft with wif_path but null wif_colors triggers reparse_all_drafts dispatch."""
        d = _make_draft(test_user.id, wif_colors=None)
        db_session.add(d)
        await db_session.commit()

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
        d = _make_draft(test_user.id, wif_colors=None, deleted=True)
        db_session.add(d)
        await db_session.commit()

        result = _run()
        assert result["dispatched"] == []
        assert any("no_null_rows" in s for s in result["skipped"])


# ---------------------------------------------------------------------------
# Redis lock held — duplicate dispatch prevention
# ---------------------------------------------------------------------------


class TestRedisLockHeld:
    async def test_skips_when_lock_already_held(self, db_session, test_user, mock_redis_locked):
        """If Redis lock is held (another worker already dispatched), skip without dispatching."""
        d = _make_draft(test_user.id, wif_colors=None)
        db_session.add(d)
        await db_session.commit()

        dispatched: list[str] = []
        with patch("app.tasks.post_migrate._backfill_registry") as mock_registry:
            mock_registry.return_value = [_reparse_registry_entry(lambda: dispatched.append("called"))]
            result = _run(mock_redis_locked)

        assert result["dispatched"] == []
        assert dispatched == []
        assert any("lock_held" in s for s in result["skipped"])

    async def test_lock_released_on_dispatch_error(self, db_session, test_user, mock_redis):
        """If dispatch raises, the Redis lock is released so the next worker can retry."""
        d = _make_draft(test_user.id, wif_colors=None)
        db_session.add(d)
        await db_session.commit()

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
