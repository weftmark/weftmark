"""Tests for app.tasks.seeds and the loom_references backfill entry in post_migrate."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_PG_TEST_DB = "test_weaving_site"

_MINIMAL_JSON = {
    "looms": [
        {
            "brand": "Ashford",
            "model_name": "SampleLoom",
            "loom_category": "floor",
            "shedding_mechanism": "jack",
        }
    ]
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _use_test_db(monkeypatch, db_available):
    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "postgres_db", _PG_TEST_DB)
    monkeypatch.setattr(settings, "postgres_dsn", "")
    monkeypatch.setattr(settings, "postgres_dsn_direct", "")
    monkeypatch.setattr(settings, "postgres_host", os.getenv("POSTGRES_HOST", "localhost"))
    monkeypatch.setattr(settings, "postgres_port", int(os.getenv("POSTGRES_PORT", "5433")))


@pytest.fixture()
def mock_redis():
    client = MagicMock()
    client.set.return_value = True
    client.close.return_value = None
    return client


@pytest.fixture()
def minimal_json_path(tmp_path) -> Path:
    import json

    p = tmp_path / "loom-data-master.json"
    p.write_text(json.dumps(_MINIMAL_JSON))
    return p


# ---------------------------------------------------------------------------
# _seed() — unit tests (no real DB needed, mock seed())
# ---------------------------------------------------------------------------


class TestSeedTask:
    def test_task_delegates_to_asyncio_run(self):
        """seed_loom_references task calls asyncio.run(_seed()) and returns its result."""
        from app.tasks.seeds import seed_loom_references

        mock_result = {"inserted": 5, "updated": 0, "skipped": 2}
        with patch("app.tasks.seeds.asyncio.run", return_value=mock_result) as mock_run:
            result = seed_loom_references.run()

        assert result == mock_result
        mock_run.assert_called_once()

    async def test_inner_seed_calls_loom_seed_fn(self):
        """_seed() delegates to seeds.loom_references.seed() and returns its result."""
        from app.tasks.seeds import _seed

        mock_result = {"inserted": 3, "updated": 1, "skipped": 0}
        with patch("app.tasks.seeds._seed", return_value=mock_result):
            # Test _seed indirectly via the mocked path — real seed() not called
            from app.tasks.seeds import _seed as fn

            assert fn is not None  # module loads without error

        # Verify _seed returns the seed() result when seed() is mocked
        async def mock_seed():
            return mock_result

        with patch("app.services.loom_seed.seed", mock_seed):
            result = await _seed()

        assert result["inserted"] == 3
        assert result["updated"] == 1


# ---------------------------------------------------------------------------
# post_migrate integration — loom_references condition
# ---------------------------------------------------------------------------


def _run_post_migrate(redis_client=None):
    from app.tasks.post_migrate import _run

    if redis_client is None:
        redis_client = MagicMock()
        redis_client.set.return_value = True

    with patch("app.tasks.post_migrate._redis") as mock_redis_module:
        mock_redis_module.from_url.return_value = redis_client
        return _run()


class TestLoomSeedBackfill:
    def test_dispatches_on_startup(self, mock_redis):
        """Seed task is always dispatched on startup (SELECT 1 condition)."""
        dispatched: list[str] = []

        dispatch_fn = MagicMock(side_effect=lambda: dispatched.append("seed_loom_references"))
        with patch("app.tasks.post_migrate._backfill_registry") as mock_reg:
            mock_reg.return_value = [
                {
                    "name": "seed_loom_references",
                    "description": "seed test",
                    "condition": "SELECT 1",
                    "dispatch": dispatch_fn,
                }
            ]
            result = _run_post_migrate(mock_redis)

        assert len(result["dispatched"]) == 1
        assert "seed_loom_references" in result["dispatched"][0]
        assert "seed_loom_references" in dispatched

    async def test_dispatches_even_when_loom_references_has_rows(self, db_session, mock_redis):
        """Seed is dispatched even when loom_references already has rows — it's an upsert."""
        from sqlalchemy import text

        await db_session.execute(
            text(
                "INSERT INTO loom_references (id, brand, model_name, loom_category, created_at, updated_at) "
                "VALUES (gen_random_uuid(), 'Ashford', 'TestLoom', 'floor', NOW(), NOW())"
            )
        )
        await db_session.commit()

        dispatched: list[str] = []
        dispatch_fn = MagicMock(side_effect=lambda: dispatched.append("seed_loom_references"))
        with patch("app.tasks.post_migrate._backfill_registry") as mock_reg:
            mock_reg.return_value = [
                {
                    "name": "seed_loom_references",
                    "description": "seed test",
                    "condition": "SELECT 1",
                    "dispatch": dispatch_fn,
                }
            ]
            result = _run_post_migrate(mock_redis)

        assert len(result["dispatched"]) == 1
        assert "seed_loom_references" in result["dispatched"][0]
        assert "seed_loom_references" in dispatched
