import asyncio
from unittest.mock import MagicMock

import pytest
from httpx import AsyncClient

import app.routers.health as health_module
from app.routers.health import ReadinessResponse, ReadinessService, _build_readiness_from_results
from app.version import VERSION


@pytest.fixture(autouse=True)
def reset_health_state():
    """Restore module-level caches and task between tests."""
    original_detailed = health_module._detailed_cache
    original_readiness = health_module._readiness_cache
    original_task = health_module._detailed_task
    yield
    # Cancel any task created during the test before restoring
    if health_module._detailed_task is not None and health_module._detailed_task is not original_task:
        health_module._detailed_task.cancel()
    health_module._detailed_cache = original_detailed
    health_module._readiness_cache = original_readiness
    health_module._detailed_task = original_task


class TestHealth:
    async def test_returns_200(self, client: AsyncClient):
        resp = await client.get("/health")
        assert resp.status_code == 200

    async def test_status_is_ok(self, client: AsyncClient):
        resp = await client.get("/health")
        assert resp.json()["status"] == "ok"

    async def test_returns_version(self, client: AsyncClient):
        resp = await client.get("/health")
        assert resp.json()["version"] == VERSION

    async def test_response_schema(self, client: AsyncClient):
        resp = await client.get("/health")
        body = resp.json()
        assert "status" in body
        assert "version" in body


class TestHealthReady:
    async def test_returns_503_when_cache_empty(self, client: AsyncClient):
        health_module._readiness_cache = None
        resp = await client.get("/health/ready")
        assert resp.status_code == 503
        assert resp.json()["status"] == "starting"

    async def test_returns_200_when_ok(self, client: AsyncClient):
        health_module._readiness_cache = ReadinessResponse(status="ok", services=[])
        resp = await client.get("/health/ready")
        assert resp.status_code == 200

    async def test_returns_503_when_error(self, client: AsyncClient):
        health_module._readiness_cache = ReadinessResponse(
            status="error",
            services=[ReadinessService(name="postgres", ok=False, critical=True)],
        )
        resp = await client.get("/health/ready")
        assert resp.status_code == 503

    async def test_returns_200_when_degraded(self, client: AsyncClient):
        health_module._readiness_cache = ReadinessResponse(
            status="degraded",
            services=[ReadinessService(name="SMTP", ok=False, critical=False)],
        )
        resp = await client.get("/health/ready")
        assert resp.status_code == 200


class TestHealthDetailed:
    async def test_returns_200_with_starting_when_cache_empty(self, client: AsyncClient):
        health_module._detailed_cache = None
        resp = await client.get("/health/detailed")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "starting"
        assert "next_check_at" in body
        assert body["next_check_at"] is not None

    async def test_returns_200_when_cache_populated(self, client: AsyncClient):
        health_module._detailed_cache = ReadinessResponse(
            status="ok",
            services=[ReadinessService(name="PostgreSQL", ok=True, critical=True)],
            checked_at="2026-01-01T00:00:00+00:00",
        )
        resp = await client.get("/health/detailed")
        assert resp.status_code == 200

    async def test_returns_cached_status(self, client: AsyncClient):
        health_module._detailed_cache = ReadinessResponse(
            status="degraded",
            services=[ReadinessService(name="Clerk Webhook", ok=False, critical=False, message="timeout")],
            checked_at="2026-01-01T00:00:00+00:00",
        )
        body = (await client.get("/health/detailed")).json()
        assert body["status"] == "degraded"
        assert body["checked_at"] == "2026-01-01T00:00:00+00:00"

    async def test_response_includes_services(self, client: AsyncClient):
        health_module._detailed_cache = ReadinessResponse(
            status="ok",
            services=[
                ReadinessService(name="PostgreSQL", ok=True, critical=True),
                ReadinessService(name="Clerk Webhook", ok=True, critical=False),
            ],
            checked_at="2026-01-01T00:00:00+00:00",
        )
        body = (await client.get("/health/detailed")).json()
        names = [s["name"] for s in body["services"]]
        assert "PostgreSQL" in names
        assert "Clerk Webhook" in names

    async def test_detailed_returns_200_even_when_degraded(self, client: AsyncClient):
        health_module._detailed_cache = ReadinessResponse(status="degraded", services=[])
        resp = await client.get("/health/detailed")
        assert resp.status_code == 200

    async def test_detailed_returns_200_even_when_error(self, client: AsyncClient):
        health_module._detailed_cache = ReadinessResponse(
            status="error",
            services=[ReadinessService(name="PostgreSQL", ok=False, critical=True)],
        )
        resp = await client.get("/health/detailed")
        assert resp.status_code == 200


class TestDetailedRefreshLifecycle:
    async def test_start_creates_task(self, monkeypatch):
        async def idle():
            pass

        monkeypatch.setattr(health_module, "_detailed_refresh_loop", idle)
        health_module._detailed_task = None
        health_module.start_detailed_refresh()
        assert health_module._detailed_task is not None

    async def test_stop_cancels_task(self):
        health_module._detailed_task = asyncio.create_task(asyncio.sleep(100))
        health_module.stop_detailed_refresh()
        assert health_module._detailed_task is None

    async def test_stop_noop_when_no_task(self):
        health_module._detailed_task = None
        health_module.stop_detailed_refresh()
        assert health_module._detailed_task is None


class TestBuildReadinessFromResults:
    def _make_service_result(self, service: str, status: str = "ok", checks=None):
        r = MagicMock()
        r.service = service
        r.status = status
        r.message = f"{service} {status}"
        r.checks = checks or []
        return r

    def test_all_ok_returns_ok(self):
        results = [self._make_service_result("PostgreSQL"), self._make_service_result("S3")]
        result = _build_readiness_from_results(results, webhook_result=None, checked_at="2026-01-01T00:00:00+00:00")
        assert result.status == "ok"

    def test_critical_failure_returns_error(self):
        results = [self._make_service_result("PostgreSQL", status="error")]
        result = _build_readiness_from_results(results, webhook_result=None, checked_at="2026-01-01T00:00:00+00:00")
        assert result.status == "error"

    def test_non_critical_failure_returns_degraded(self):
        results = [
            self._make_service_result("PostgreSQL"),
            self._make_service_result("SMTP", status="error"),
        ]
        result = _build_readiness_from_results(results, webhook_result=None, checked_at="2026-01-01T00:00:00+00:00")
        assert result.status == "degraded"

    def test_exception_in_results_counts_as_hard_failure(self):
        results = [RuntimeError("db exploded")]
        result = _build_readiness_from_results(results, webhook_result=None, checked_at="2026-01-01T00:00:00+00:00")
        assert result.status == "error"

    def test_webhook_ok_included_in_services(self):
        wh = MagicMock()
        wh.status = "ok"
        wh.message = "232ms"
        result = _build_readiness_from_results([], webhook_result=wh, checked_at="2026-01-01T00:00:00+00:00")
        names = [s.name for s in result.services]
        assert "Clerk Webhook" in names

    def test_webhook_error_sets_degraded(self):
        wh = MagicMock()
        wh.status = "error"
        wh.message = "timeout"
        result = _build_readiness_from_results([], webhook_result=wh, checked_at="2026-01-01T00:00:00+00:00")
        assert result.status == "degraded"

    def test_webhook_skipped_treated_as_ok(self):
        wh = MagicMock()
        wh.status = "skipped"
        wh.message = "no base url"
        result = _build_readiness_from_results([], webhook_result=wh, checked_at="2026-01-01T00:00:00+00:00")
        webhook_svc = next(s for s in result.services if s.name == "Clerk Webhook")
        assert webhook_svc.ok is True

    def test_none_webhook_not_included(self):
        results = [self._make_service_result("PostgreSQL")]
        result = _build_readiness_from_results(results, webhook_result=None, checked_at="2026-01-01T00:00:00+00:00")
        names = [s.name for s in result.services]
        assert "Clerk Webhook" not in names

    def test_checked_at_propagated(self):
        result = _build_readiness_from_results([], webhook_result=None, checked_at="2026-05-01T12:00:00+00:00")
        assert result.checked_at == "2026-05-01T12:00:00+00:00"

    def test_first_failed_check_message_used_as_detail(self):
        failed_check = MagicMock()
        failed_check.status = "error"
        failed_check.message = "permission denied"
        svc = self._make_service_result("S3", status="error", checks=[failed_check])
        result = _build_readiness_from_results([svc], webhook_result=None, checked_at="2026-01-01T00:00:00+00:00")
        s3_svc = next(s for s in result.services if s.name == "S3")
        assert s3_svc.detail == "permission denied"

    def test_services_list_populated(self):
        results = [
            self._make_service_result("PostgreSQL"),
            self._make_service_result("S3"),
            self._make_service_result("Clerk"),
            self._make_service_result("SMTP"),
        ]
        result = _build_readiness_from_results(results, webhook_result=None, checked_at="2026-01-01T00:00:00+00:00")
        assert len(result.services) == 4
