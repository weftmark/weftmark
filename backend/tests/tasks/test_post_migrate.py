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


# ---------------------------------------------------------------------------
# No null rows — nothing to dispatch
# ---------------------------------------------------------------------------


class TestNoNullRows:
    def test_skips_all_when_table_empty(self):
        """With no drafts in the DB at all, backfill is skipped."""
        result = _run()
        assert result["dispatched"] == []
        assert any("no_null_rows" in s for s in result["skipped"])

    def test_skips_when_all_drafts_have_wif_colors(self, db_session):
        """Drafts that already have wif_colors set are not counted."""
        import asyncio

        from sqlalchemy import text

        async def seed():
            await db_session.execute(
                text(
                    "INSERT INTO drafts (id, owner_id, name, slug, wif_path, wif_colors, created_at, updated_at) "
                    "VALUES (:id, :owner, 'test', 'test', 'drafts/test.wif', '[1]'::jsonb, NOW(), NOW())"
                ),
                {"id": str(uuid.uuid4()), "owner": str(uuid.uuid4())},
            )
            await db_session.commit()

        asyncio.get_event_loop().run_until_complete(seed())

        result = _run()
        assert result["dispatched"] == []
        assert any("no_null_rows" in s for s in result["skipped"])


# ---------------------------------------------------------------------------
# Null rows present — backfill should dispatch
# ---------------------------------------------------------------------------


class TestNullRowsPresent:
    def test_dispatches_reparse_when_wif_colors_null(self, db_session, mock_redis):
        """A draft with wif_path but null wif_colors triggers reparse_all_drafts dispatch."""
        import asyncio

        from sqlalchemy import text

        async def seed():
            await db_session.execute(
                text(
                    "INSERT INTO drafts (id, owner_id, name, slug, wif_path, wif_colors, created_at, updated_at) "
                    "VALUES (:id, :owner, 'test', 'test', 'drafts/test.wif', NULL, NOW(), NOW())"
                ),
                {"id": str(uuid.uuid4()), "owner": str(uuid.uuid4())},
            )
            await db_session.commit()

        asyncio.get_event_loop().run_until_complete(seed())

        dispatched_tasks = []
        with patch("app.tasks.post_migrate.reparse_all_drafts") as mock_task:
            mock_task.delay.side_effect = lambda: dispatched_tasks.append("reparse_all_drafts")

            with patch("app.tasks.post_migrate._backfill_registry") as mock_registry:
                mock_registry.return_value = [
                    {
                        "name": "reparse_drafts",
                        "description": "test",
                        "condition": (
                            "SELECT COUNT(*) FROM drafts "
                            "WHERE wif_colors IS NULL AND wif_path IS NOT NULL AND deleted_at IS NULL"
                        ),
                        "dispatch": lambda: mock_task.delay(),
                    }
                ]

                result = _run(mock_redis)

        assert len(result["dispatched"]) == 1
        assert "reparse_drafts" in result["dispatched"][0]
        assert result["dispatched"][0].endswith("(null_rows=1)")

    def test_deleted_drafts_not_counted(self, db_session, mock_redis):
        """Soft-deleted drafts with null wif_colors must not trigger dispatch."""
        import asyncio

        from sqlalchemy import text

        async def seed():
            await db_session.execute(
                text(
                    "INSERT INTO drafts "
                    "(id, owner_id, name, slug, wif_path, wif_colors, deleted_at, created_at, updated_at) "
                    "VALUES (:id, :owner, 'deleted', 'deleted', 'drafts/d.wif', NULL, NOW(), NOW(), NOW())"
                ),
                {"id": str(uuid.uuid4()), "owner": str(uuid.uuid4())},
            )
            await db_session.commit()

        asyncio.get_event_loop().run_until_complete(seed())

        result = _run()
        assert result["dispatched"] == []
        assert any("no_null_rows" in s for s in result["skipped"])

    def test_drafts_without_wif_path_not_counted(self, db_session):
        """Drafts with no wif_path (upload failed) must not trigger dispatch."""
        import asyncio

        from sqlalchemy import text

        async def seed():
            await db_session.execute(
                text(
                    "INSERT INTO drafts (id, owner_id, name, slug, wif_path, wif_colors, created_at, updated_at) "
                    "VALUES (:id, :owner, 'nowif', 'nowif', NULL, NULL, NOW(), NOW())"
                ),
                {"id": str(uuid.uuid4()), "owner": str(uuid.uuid4())},
            )
            await db_session.commit()

        asyncio.get_event_loop().run_until_complete(seed())

        result = _run()
        assert result["dispatched"] == []


# ---------------------------------------------------------------------------
# Redis lock held — duplicate dispatch prevention
# ---------------------------------------------------------------------------


class TestRedisLockHeld:
    def test_skips_when_lock_already_held(self, db_session, mock_redis_locked):
        """If Redis lock is held (another worker already dispatched), skip without dispatching."""
        import asyncio

        from sqlalchemy import text

        async def seed():
            await db_session.execute(
                text(
                    "INSERT INTO drafts (id, owner_id, name, slug, wif_path, wif_colors, created_at, updated_at) "
                    "VALUES (:id, :owner, 'test', 'test', 'drafts/test.wif', NULL, NOW(), NOW())"
                ),
                {"id": str(uuid.uuid4()), "owner": str(uuid.uuid4())},
            )
            await db_session.commit()

        asyncio.get_event_loop().run_until_complete(seed())

        with patch("app.tasks.post_migrate._backfill_registry") as mock_registry:
            dispatched = []
            mock_registry.return_value = [
                {
                    "name": "reparse_drafts",
                    "description": "test",
                    "condition": (
                        "SELECT COUNT(*) FROM drafts "
                        "WHERE wif_colors IS NULL AND wif_path IS NOT NULL AND deleted_at IS NULL"
                    ),
                    "dispatch": lambda: dispatched.append("called"),
                }
            ]
            result = _run(mock_redis_locked)

        assert result["dispatched"] == []
        assert dispatched == []
        assert any("lock_held" in s for s in result["skipped"])

    def test_lock_released_on_dispatch_error(self, db_session, mock_redis):
        """If dispatch raises, the Redis lock is released so the next worker can retry."""
        import asyncio

        from sqlalchemy import text

        async def seed():
            await db_session.execute(
                text(
                    "INSERT INTO drafts (id, owner_id, name, slug, wif_path, wif_colors, created_at, updated_at) "
                    "VALUES (:id, :owner, 'test', 'test', 'drafts/test.wif', NULL, NOW(), NOW())"
                ),
                {"id": str(uuid.uuid4()), "owner": str(uuid.uuid4())},
            )
            await db_session.commit()

        asyncio.get_event_loop().run_until_complete(seed())

        with patch("app.tasks.post_migrate._backfill_registry") as mock_registry:
            mock_registry.return_value = [
                {
                    "name": "reparse_drafts",
                    "description": "test",
                    "condition": (
                        "SELECT COUNT(*) FROM drafts "
                        "WHERE wif_colors IS NULL AND wif_path IS NOT NULL AND deleted_at IS NULL"
                    ),
                    "dispatch": lambda: (_ for _ in ()).throw(RuntimeError("broker down")),
                }
            ]
            result = _run(mock_redis)

        # Lock must have been released
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
