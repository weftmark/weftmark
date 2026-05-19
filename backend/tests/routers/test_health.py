import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient

import app.routers.health as health_module
from app.routers.health import ReadinessResponse, ReadinessService, _build_readiness_from_results, set_readiness
from app.version import VERSION


@pytest.fixture(autouse=True)
def reset_health_state():
    """Restore module-level caches and task between tests."""
    original_detailed = health_module._detailed_cache
    original_readiness = health_module._readiness_cache
    original_task = health_module._detailed_task
    original_open_event = health_module._open_health_event_id
    original_last_alert = health_module._last_alert_status
    original_email_cache = health_module._superuser_email_cache
    original_failures = health_module._consecutive_failures
    yield
    # Cancel any task created during the test before restoring
    if health_module._detailed_task is not None and health_module._detailed_task is not original_task:
        health_module._detailed_task.cancel()
    health_module._detailed_cache = original_detailed
    health_module._readiness_cache = original_readiness
    health_module._detailed_task = original_task
    health_module._open_health_event_id = original_open_event
    health_module._last_alert_status = original_last_alert
    health_module._superuser_email_cache = original_email_cache
    health_module._consecutive_failures = original_failures


class TestHealth:
    async def test_returns_200(self, client: AsyncClient):
        resp = await client.get("/api/health")
        assert resp.status_code == 200

    async def test_status_is_ok(self, client: AsyncClient):
        resp = await client.get("/api/health")
        assert resp.json()["status"] == "ok"

    async def test_returns_version(self, client: AsyncClient):
        resp = await client.get("/api/health")
        assert resp.json()["version"] == VERSION

    async def test_response_schema(self, client: AsyncClient):
        resp = await client.get("/api/health")
        body = resp.json()
        assert "status" in body
        assert "version" in body


class TestHealthReady:
    async def test_returns_503_when_cache_empty(self, client: AsyncClient):
        health_module._readiness_cache = None
        resp = await client.get("/api/health/ready")
        assert resp.status_code == 503
        assert resp.json()["status"] == "starting"

    async def test_returns_200_when_ok(self, client: AsyncClient):
        health_module._readiness_cache = ReadinessResponse(status="ok", services=[])
        resp = await client.get("/api/health/ready")
        assert resp.status_code == 200

    async def test_returns_503_when_error(self, client: AsyncClient):
        health_module._readiness_cache = ReadinessResponse(
            status="error",
            services=[ReadinessService(name="postgres", ok=False, critical=True)],
        )
        resp = await client.get("/api/health/ready")
        assert resp.status_code == 503

    async def test_returns_200_when_degraded(self, client: AsyncClient):
        health_module._readiness_cache = ReadinessResponse(
            status="degraded",
            services=[ReadinessService(name="SMTP", ok=False, critical=False)],
        )
        resp = await client.get("/api/health/ready")
        assert resp.status_code == 200


class TestHealthDetailed:
    async def test_returns_200_with_starting_when_cache_empty(self, client: AsyncClient):
        health_module._detailed_cache = None
        resp = await client.get("/api/health/detailed")
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
        resp = await client.get("/api/health/detailed")
        assert resp.status_code == 200

    async def test_returns_cached_status(self, client: AsyncClient):
        health_module._detailed_cache = ReadinessResponse(
            status="degraded",
            services=[ReadinessService(name="Clerk Webhook", ok=False, critical=False, message="timeout")],
            checked_at="2026-01-01T00:00:00+00:00",
        )
        body = (await client.get("/api/health/detailed")).json()
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
        body = (await client.get("/api/health/detailed")).json()
        names = [s["name"] for s in body["services"]]
        assert "PostgreSQL" in names
        assert "Clerk Webhook" in names

    async def test_detailed_returns_200_even_when_degraded(self, client: AsyncClient):
        health_module._detailed_cache = ReadinessResponse(status="degraded", services=[])
        resp = await client.get("/api/health/detailed")
        assert resp.status_code == 200

    async def test_detailed_returns_200_even_when_error(self, client: AsyncClient):
        health_module._detailed_cache = ReadinessResponse(
            status="error",
            services=[ReadinessService(name="PostgreSQL", ok=False, critical=True)],
        )
        resp = await client.get("/api/health/detailed")
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


# ---------------------------------------------------------------------------
# TestSetReadiness — set_readiness helper
# ---------------------------------------------------------------------------


class TestSetReadiness:
    def test_sets_cache(self):
        health_module._readiness_cache = None
        r = ReadinessResponse(status="ok", services=[])
        set_readiness(r)
        assert health_module._readiness_cache is r

    def test_overwrites_existing(self):
        health_module._readiness_cache = ReadinessResponse(status="error", services=[])
        r = ReadinessResponse(status="ok", services=[])
        set_readiness(r)
        assert health_module._readiness_cache.status == "ok"


# ---------------------------------------------------------------------------
# TestGetWorkerVersion — _get_worker_version Redis helper
# ---------------------------------------------------------------------------


class TestGetWorkerVersion:
    async def test_returns_none_when_redis_unavailable(self):
        from app.routers.health import _get_worker_version

        with patch("redis.asyncio.from_url", side_effect=Exception("connection refused")):
            result = await _get_worker_version()
        assert result is None

    async def test_returns_decoded_value_when_key_exists(self):
        from app.routers.health import _get_worker_version

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=b"0.170.0")
        mock_client.aclose = AsyncMock()

        with patch("redis.asyncio.from_url", return_value=mock_client):
            result = await _get_worker_version()

        assert result == "0.170.0"

    async def test_returns_none_when_key_missing(self):
        from app.routers.health import _get_worker_version

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=None)
        mock_client.aclose = AsyncMock()

        with patch("redis.asyncio.from_url", return_value=mock_client):
            result = await _get_worker_version()

        assert result is None

    async def test_health_endpoint_includes_worker_version(self, client: AsyncClient):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=b"1.2.3")
        mock_client.aclose = AsyncMock()

        with patch("redis.asyncio.from_url", return_value=mock_client):
            resp = await client.get("/api/health")

        assert resp.status_code == 200
        assert resp.json()["worker_version"] == "1.2.3"

    async def test_health_endpoint_worker_version_none_on_error(self, client: AsyncClient):
        with patch("redis.asyncio.from_url", side_effect=Exception("down")):
            resp = await client.get("/api/health")

        assert resp.status_code == 200
        assert resp.json()["worker_version"] is None


# ---------------------------------------------------------------------------
# TestRefreshSuperuserEmailCache
# ---------------------------------------------------------------------------


class TestRefreshSuperuserEmailCache:
    async def test_populates_cache(self, db_session, superuser_user):
        from app.routers.health import _refresh_superuser_email_cache

        health_module._superuser_email_cache = []

        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=db_session)
        ctx.__aexit__ = AsyncMock(return_value=False)
        with patch("app.database.AsyncSessionLocal", return_value=ctx):
            await _refresh_superuser_email_cache()

        assert superuser_user.email in health_module._superuser_email_cache

    async def test_swallows_exceptions(self):
        from app.routers.health import _refresh_superuser_email_cache

        with patch("app.database.AsyncSessionLocal", side_effect=Exception("db down")):
            await _refresh_superuser_email_cache()  # must not raise


# ---------------------------------------------------------------------------
# TestDispatchHealthAlert
# ---------------------------------------------------------------------------


class TestDispatchHealthAlert:
    async def test_no_op_when_alerts_disabled(self):
        from app.routers.health import _dispatch_health_alert

        result = ReadinessResponse(status="error", services=[ReadinessService(name="PG", ok=False, critical=True)])

        with patch("app.routers.health.get_settings") as mock_settings:
            mock_settings.return_value.stack_alert_emails_enabled = False
            with patch("app.services.email.send_health_degraded_alert", new_callable=AsyncMock) as mock_email:
                await _dispatch_health_alert(result, is_recovery=False)

        mock_email.assert_not_called()

    async def test_no_op_when_email_cache_empty(self):
        from app.routers.health import _dispatch_health_alert

        health_module._superuser_email_cache = []
        result = ReadinessResponse(status="error", services=[])

        with patch("app.routers.health.get_settings") as mock_settings:
            mock_settings.return_value.stack_alert_emails_enabled = True
            mock_settings.return_value.app_env = "test"
            mock_settings.return_value.app_base_url = "http://localhost"
            mock_settings.return_value.frontend_url = "http://localhost"
            await _dispatch_health_alert(result, is_recovery=False)

    async def test_swallows_email_exception(self):
        from app.routers.health import _dispatch_health_alert

        health_module._superuser_email_cache = ["admin@test.com"]
        result = ReadinessResponse(status="error", services=[])

        with patch("app.routers.health.get_settings") as mock_settings:
            mock_settings.return_value.stack_alert_emails_enabled = True
            mock_settings.return_value.app_env = "test"
            mock_settings.return_value.app_base_url = "http://localhost"
            mock_settings.return_value.frontend_url = "http://localhost"
            with patch(
                "app.services.email.send_health_degraded_alert",
                new_callable=AsyncMock,
                side_effect=Exception("smtp down"),
            ):
                await _dispatch_health_alert(result, is_recovery=False)  # must not raise

    async def test_calls_recovery_email_when_is_recovery(self):
        from app.routers.health import _dispatch_health_alert

        health_module._superuser_email_cache = ["admin@test.com"]
        result = ReadinessResponse(status="ok", services=[])

        with patch("app.routers.health.get_settings") as mock_settings:
            mock_settings.return_value.stack_alert_emails_enabled = True
            mock_settings.return_value.app_env = "test"
            mock_settings.return_value.app_base_url = "http://localhost"
            mock_settings.return_value.frontend_url = "http://localhost"
            with patch("app.services.email.send_health_recovered_alert", new_callable=AsyncMock) as mock_recovery:
                with patch("app.services.email.send_health_degraded_alert", new_callable=AsyncMock):
                    await _dispatch_health_alert(result, is_recovery=True)

        mock_recovery.assert_called_once()


# ---------------------------------------------------------------------------
# TestRecordHealthTransition
# ---------------------------------------------------------------------------


class TestRecordHealthTransition:
    async def test_no_op_when_status_unchanged(self):
        from app.routers.health import _record_health_transition

        result = ReadinessResponse(status="ok", services=[])
        # Same status → early return before any DB access; must not raise
        await _record_health_transition("ok", result)

    async def test_swallows_db_exception(self):
        from app.routers.health import _record_health_transition

        result = ReadinessResponse(status="error", services=[ReadinessService(name="PG", ok=False, critical=True)])
        with patch("app.database.AsyncSessionLocal", side_effect=Exception("db down")):
            await _record_health_transition("ok", result)  # must not raise


# ---------------------------------------------------------------------------
# TestRunStartupProbes
# ---------------------------------------------------------------------------


class TestRunStartupProbes:
    async def test_returns_readiness_response(self):
        from app.routers.health import run_startup_probes

        ok_result = MagicMock()
        ok_result.service = "PostgreSQL"
        ok_result.status = "ok"
        ok_result.message = "ok"
        ok_result.checks = []

        ctx = MagicMock()
        mock_db = AsyncMock()
        ctx.__aenter__ = AsyncMock(return_value=mock_db)
        ctx.__aexit__ = AsyncMock(return_value=False)
        with patch("app.database.AsyncSessionLocal", return_value=ctx):
            with patch("app.routers.admin._probe_postgres", return_value=ok_result):
                with patch("app.routers.admin._probe_s3", return_value=ok_result):
                    with patch("app.routers.admin._probe_clerk", return_value=ok_result):
                        with patch("app.routers.admin._probe_smtp", return_value=ok_result):
                            with patch("app.routers.admin._probe_config", return_value=ok_result):
                                result = await run_startup_probes()

        assert isinstance(result, ReadinessResponse)

    async def test_returns_error_on_db_connect_failure(self):
        from app.routers.health import run_startup_probes

        with patch("app.database.AsyncSessionLocal", side_effect=Exception("connection refused")):
            result = await run_startup_probes()

        assert result.status == "error"


# ---------------------------------------------------------------------------
# TestRunDetailedProbes — _run_detailed_probes
# ---------------------------------------------------------------------------


class TestRunDetailedProbes:
    async def test_returns_readiness_response_when_all_ok(self):
        from app.routers.health import _run_detailed_probes

        ok_result = MagicMock()
        ok_result.service = "PostgreSQL"
        ok_result.status = "ok"
        ok_result.message = "All good"
        ok_result.checks = []

        ctx = MagicMock()
        mock_db = AsyncMock()
        ctx.__aenter__ = AsyncMock(return_value=mock_db)
        ctx.__aexit__ = AsyncMock(return_value=False)

        with patch("app.database.AsyncSessionLocal", return_value=ctx):
            with patch("app.routers.admin._probe_postgres", new_callable=AsyncMock, return_value=ok_result):
                with patch("app.routers.admin._probe_s3", new_callable=AsyncMock, return_value=ok_result):
                    with patch("app.routers.admin._probe_clerk", new_callable=AsyncMock, return_value=ok_result):
                        with patch("app.routers.admin._probe_smtp", new_callable=AsyncMock, return_value=ok_result):
                            with patch(
                                "app.routers.admin._probe_config", new_callable=AsyncMock, return_value=ok_result
                            ):
                                with patch(
                                    "app.services.clerk_webhook_probe.run_webhook_probe",
                                    new_callable=AsyncMock,
                                    return_value=None,
                                ):
                                    result = await _run_detailed_probes()

        assert isinstance(result, ReadinessResponse)

    async def test_returns_error_on_db_exception(self):
        from app.routers.health import _run_detailed_probes

        with patch("app.database.AsyncSessionLocal", side_effect=Exception("db down")):
            result = await _run_detailed_probes()

        assert result.status == "error"
        assert result.services[0].ok is False


# ---------------------------------------------------------------------------
# TestRecordHealthTransitionDBPaths — DB write paths
# ---------------------------------------------------------------------------


class TestRecordHealthTransitionDBPaths:
    def _make_db_ctx(self, mock_db: AsyncMock):
        ctx = MagicMock()
        ctx.__aenter__ = AsyncMock(return_value=mock_db)
        ctx.__aexit__ = AsyncMock(return_value=False)
        return ctx

    async def test_opens_event_when_going_to_error(self):
        from app.routers.health import _record_health_transition

        health_module._open_health_event_id = None
        result = ReadinessResponse(
            status="error",
            services=[ReadinessService(name="PG", ok=False, critical=True)],
        )

        mock_evt = MagicMock()
        mock_evt.id = uuid.uuid4()

        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        with patch("app.database.AsyncSessionLocal", return_value=self._make_db_ctx(mock_db)):
            with patch(
                "app.services.server_events.write_event", new_callable=AsyncMock, return_value=mock_evt
            ) as mock_write:
                await _record_health_transition("ok", result)

        mock_write.assert_called_once()
        assert health_module._open_health_event_id == mock_evt.id

    async def test_opens_event_when_going_to_degraded(self):
        from app.routers.health import _record_health_transition

        health_module._open_health_event_id = None
        result = ReadinessResponse(
            status="degraded",
            services=[ReadinessService(name="S3", ok=False, critical=False)],
        )

        mock_evt = MagicMock()
        mock_evt.id = uuid.uuid4()

        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_db.refresh = AsyncMock()

        with patch("app.database.AsyncSessionLocal", return_value=self._make_db_ctx(mock_db)):
            with patch("app.services.server_events.write_event", new_callable=AsyncMock, return_value=mock_evt):
                await _record_health_transition("ok", result)

        assert health_module._open_health_event_id == mock_evt.id

    async def test_closes_event_on_recovery(self):
        from app.routers.health import _record_health_transition

        event_id = uuid.uuid4()
        health_module._open_health_event_id = event_id
        result = ReadinessResponse(status="ok", services=[])

        mock_evt = MagicMock()
        mock_evt.status = "open"

        mock_db = AsyncMock()
        mock_db.scalar = AsyncMock(return_value=mock_evt)
        mock_db.commit = AsyncMock()

        with patch("app.database.AsyncSessionLocal", return_value=self._make_db_ctx(mock_db)):
            with patch("app.services.server_events.close_event", new_callable=AsyncMock) as mock_close:
                await _record_health_transition("error", result)

        mock_close.assert_called_once()
        assert health_module._open_health_event_id is None

    async def test_recovery_clears_id_even_when_event_not_found(self):
        from app.routers.health import _record_health_transition

        health_module._open_health_event_id = uuid.uuid4()
        result = ReadinessResponse(status="ok", services=[])

        mock_db = AsyncMock()
        mock_db.scalar = AsyncMock(return_value=None)
        mock_db.commit = AsyncMock()

        with patch("app.database.AsyncSessionLocal", return_value=self._make_db_ctx(mock_db)):
            with patch("app.services.server_events.close_event", new_callable=AsyncMock) as mock_close:
                await _record_health_transition("error", result)

        mock_close.assert_not_called()
        assert health_module._open_health_event_id is None

    async def test_already_closed_event_not_closed_again(self):
        from app.routers.health import _record_health_transition

        health_module._open_health_event_id = uuid.uuid4()
        result = ReadinessResponse(status="ok", services=[])

        mock_evt = MagicMock()
        mock_evt.status = "closed"

        mock_db = AsyncMock()
        mock_db.scalar = AsyncMock(return_value=mock_evt)
        mock_db.commit = AsyncMock()

        with patch("app.database.AsyncSessionLocal", return_value=self._make_db_ctx(mock_db)):
            with patch("app.services.server_events.close_event", new_callable=AsyncMock) as mock_close:
                await _record_health_transition("error", result)

        mock_close.assert_not_called()


# ---------------------------------------------------------------------------
# TestStartStopDetailedRefresh — lifecycle helpers
# ---------------------------------------------------------------------------


class TestStartStopDetailedRefresh:
    def test_start_creates_background_task(self):
        from app.routers.health import start_detailed_refresh

        health_module._detailed_task = None
        mock_task = MagicMock()
        with patch("app.routers.health.asyncio") as mock_asyncio:
            mock_asyncio.create_task.return_value = mock_task
            start_detailed_refresh()

        mock_asyncio.create_task.assert_called_once()
        assert health_module._detailed_task is mock_task

    def test_start_sets_initial_status(self):
        from app.routers.health import start_detailed_refresh

        health_module._last_alert_status = None
        with patch("app.routers.health.asyncio") as mock_asyncio:
            mock_asyncio.create_task.return_value = MagicMock()
            start_detailed_refresh(initial_status="ok")

        assert health_module._last_alert_status == "ok"

    def test_start_without_initial_status_leaves_it_unchanged(self):
        from app.routers.health import start_detailed_refresh

        health_module._last_alert_status = "degraded"
        with patch("app.routers.health.asyncio") as mock_asyncio:
            mock_asyncio.create_task.return_value = MagicMock()
            start_detailed_refresh()

        assert health_module._last_alert_status == "degraded"

    def test_stop_cancels_task_and_clears_reference(self):
        from app.routers.health import stop_detailed_refresh

        mock_task = MagicMock()
        mock_task.cancel = MagicMock()
        health_module._detailed_task = mock_task

        stop_detailed_refresh()

        mock_task.cancel.assert_called_once()
        assert health_module._detailed_task is None

    def test_stop_noop_when_no_task(self):
        from app.routers.health import stop_detailed_refresh

        health_module._detailed_task = None
        stop_detailed_refresh()  # must not raise


# ---------------------------------------------------------------------------
# TestDetailedRefreshLoop — _detailed_refresh_loop single-iteration paths
# ---------------------------------------------------------------------------


class TestDetailedRefreshLoop:
    """Run exactly one iteration of the loop by making the end-of-loop sleep raise CancelledError."""

    def _make_fake_sleep(self, cancel_on: int = 2):
        calls = [0]

        async def fake_sleep(_):
            calls[0] += 1
            if calls[0] >= cancel_on:
                raise asyncio.CancelledError()

        return fake_sleep

    async def test_ok_result_resets_failure_counter_and_updates_cache(self):
        from app.routers.health import _detailed_refresh_loop

        result = ReadinessResponse(
            status="ok",
            services=[ReadinessService(name="PostgreSQL", ok=True, critical=True)],
        )
        health_module._consecutive_failures = 5
        health_module._last_alert_status = None

        with patch("app.routers.health.asyncio.sleep", side_effect=self._make_fake_sleep()):
            with patch("app.routers.health._run_detailed_probes", new_callable=AsyncMock, return_value=result):
                with patch("app.routers.health._refresh_superuser_email_cache", new_callable=AsyncMock):
                    with patch("app.routers.health._record_health_transition", new_callable=AsyncMock):
                        with pytest.raises(asyncio.CancelledError):
                            await _detailed_refresh_loop()

        assert health_module._consecutive_failures == 0
        assert health_module._detailed_cache is result
        assert health_module._last_alert_status == "ok"

    async def test_first_non_ok_increments_counter_but_does_not_surface(self):
        from app.routers.health import _detailed_refresh_loop

        result = ReadinessResponse(
            status="error",
            services=[ReadinessService(name="PostgreSQL", ok=False, critical=True)],
        )
        health_module._consecutive_failures = 0

        # On first non-ok the loop does an extra sleep(_FAILURE_RETRY_GAP_S) then `continue`,
        # so the end-of-loop sleep is never reached — CancelledError comes from call 2.
        with patch("app.routers.health.asyncio.sleep", side_effect=self._make_fake_sleep(2)):
            with patch("app.routers.health._run_detailed_probes", new_callable=AsyncMock, return_value=result):
                with patch("app.routers.health._refresh_superuser_email_cache", new_callable=AsyncMock):
                    with patch("app.routers.health._record_health_transition", new_callable=AsyncMock) as mock_record:
                        with pytest.raises(asyncio.CancelledError):
                            await _detailed_refresh_loop()

        assert health_module._consecutive_failures == 1
        mock_record.assert_not_called()  # not surfaced yet

    async def test_confirmed_failure_surfaces_and_updates_cache(self):
        from app.routers.health import _detailed_refresh_loop

        result = ReadinessResponse(
            status="error",
            services=[ReadinessService(name="PostgreSQL", ok=False, critical=True)],
        )
        # Already at the threshold — next non-ok gets surfaced
        health_module._consecutive_failures = 3
        health_module._last_alert_status = None

        with patch("app.routers.health.asyncio.sleep", side_effect=self._make_fake_sleep()):
            with patch("app.routers.health._run_detailed_probes", new_callable=AsyncMock, return_value=result):
                with patch("app.routers.health._refresh_superuser_email_cache", new_callable=AsyncMock):
                    with patch("app.routers.health._record_health_transition", new_callable=AsyncMock) as mock_record:
                        with pytest.raises(asyncio.CancelledError):
                            await _detailed_refresh_loop()

        mock_record.assert_called_once()
        assert health_module._detailed_cache is result

    async def test_status_change_triggers_alert_task(self):
        from app.routers.health import _detailed_refresh_loop

        result = ReadinessResponse(
            status="error",
            services=[ReadinessService(name="PostgreSQL", ok=False, critical=True)],
        )
        health_module._consecutive_failures = 3
        health_module._last_alert_status = "ok"  # transition from ok → error

        with patch("app.routers.health.asyncio.sleep", side_effect=self._make_fake_sleep()):
            with patch("app.routers.health._run_detailed_probes", new_callable=AsyncMock, return_value=result):
                with patch("app.routers.health._refresh_superuser_email_cache", new_callable=AsyncMock):
                    with patch("app.routers.health._record_health_transition", new_callable=AsyncMock):
                        with patch("app.routers.health.asyncio.create_task") as mock_create_task:
                            with pytest.raises(asyncio.CancelledError):
                                await _detailed_refresh_loop()

        mock_create_task.assert_called_once()
        assert health_module._last_alert_status == "error"

    async def test_recovery_triggers_alert_task(self):
        from app.routers.health import _detailed_refresh_loop

        result = ReadinessResponse(status="ok", services=[])
        health_module._consecutive_failures = 0
        health_module._last_alert_status = "error"  # transition from error → ok

        with patch("app.routers.health.asyncio.sleep", side_effect=self._make_fake_sleep()):
            with patch("app.routers.health._run_detailed_probes", new_callable=AsyncMock, return_value=result):
                with patch("app.routers.health._refresh_superuser_email_cache", new_callable=AsyncMock):
                    with patch("app.routers.health._record_health_transition", new_callable=AsyncMock):
                        with patch("app.routers.health.asyncio.create_task") as mock_create_task:
                            with pytest.raises(asyncio.CancelledError):
                                await _detailed_refresh_loop()

        mock_create_task.assert_called_once()

    async def test_loop_catches_probe_exception_and_continues(self):
        from app.routers.health import _detailed_refresh_loop

        # Probe raises → except Exception catches it → end-of-loop sleep raises CancelledError
        with patch("app.routers.health.asyncio.sleep", side_effect=self._make_fake_sleep()):
            with patch(
                "app.routers.health._run_detailed_probes",
                new_callable=AsyncMock,
                side_effect=RuntimeError("probe failed"),
            ):
                with pytest.raises(asyncio.CancelledError):
                    await _detailed_refresh_loop()
