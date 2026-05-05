"""Tests for POST /api/logs (client log relay)."""

from httpx import AsyncClient


class TestClientLogs:
    async def test_single_info_event(self, client: AsyncClient):
        resp = await client.post(
            "/api/logs",
            json=[{"level": "info", "message": "page loaded"}],
        )
        assert resp.status_code == 204

    async def test_event_with_context(self, client: AsyncClient):
        resp = await client.post(
            "/api/logs",
            json=[{"level": "error", "message": "fetch failed", "context": {"route": "/dashboard", "status": 500}}],
        )
        assert resp.status_code == 204

    async def test_multiple_events(self, client: AsyncClient):
        resp = await client.post(
            "/api/logs",
            json=[
                {"level": "debug", "message": "component mounted"},
                {"level": "warning", "message": "slow query"},
            ],
        )
        assert resp.status_code == 204

    async def test_empty_list(self, client: AsyncClient):
        resp = await client.post("/api/logs", json=[])
        assert resp.status_code == 204

    async def test_no_auth_required(self, client: AsyncClient):
        resp = await client.post(
            "/api/logs",
            json=[{"level": "info", "message": "unauthenticated event"}],
        )
        assert resp.status_code != 401
        assert resp.status_code != 403

    async def test_x_real_ip_header_accepted(self, client: AsyncClient):
        resp = await client.post(
            "/api/logs",
            headers={"X-Real-IP": "203.0.113.5"},
            json=[{"level": "info", "message": "event with real ip"}],
        )
        assert resp.status_code == 204
