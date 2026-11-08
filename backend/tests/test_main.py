"""Tests for app.main lifespan startup."""

from unittest.mock import AsyncMock, patch

import pytest

from app.main import app, lifespan
from app.routers.health import ReadinessResponse


class TestLifespanStartup:
    async def test_fires_background_tasks_and_starts_detailed_refresh(self):
        readiness = ReadinessResponse(status="ok", services=[])

        with (
            patch("app.routers.health.run_startup_probes", new_callable=AsyncMock, return_value=readiness),
            patch("app.routers.health.set_readiness") as mock_set_readiness,
            patch("app.routers.health.start_detailed_refresh") as mock_start_refresh,
            patch("app.routers.health.stop_detailed_refresh"),
            patch("app.routers.yarn.warm_yarn_properties_cache", new_callable=AsyncMock),
            patch("app.routers.yarn.refresh_yarn_properties_loop", new_callable=AsyncMock),
            patch("app.services.background_tasks.fire_and_forget") as mock_fire,
        ):
            async with lifespan(app):
                pass

        mock_set_readiness.assert_called_once_with(readiness)
        mock_start_refresh.assert_called_once_with(initial_status="ok")
        assert mock_fire.call_count == 4


class TestMainWorkerVersionHelper:
    """app.main._get_worker_version_for_alert — used in the stack startup alert."""

    @pytest.mark.parametrize("stored, expected", [(b"0.216.10", "0.216.10"), ("0.216.11", "0.216.11"), (None, None)])
    async def test_decodes_bytes_and_passes_str(self, stored, expected):
        from app.main import _get_worker_version_for_alert as _get_worker_version

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=stored)
        mock_client.aclose = AsyncMock()
        with patch("redis.asyncio.from_url", return_value=mock_client):
            assert await _get_worker_version() == expected

    async def test_returns_none_when_redis_unavailable(self):
        from app.main import _get_worker_version_for_alert as _get_worker_version

        with patch("redis.asyncio.from_url", side_effect=Exception("connection refused")):
            assert await _get_worker_version() is None
