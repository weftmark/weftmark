"""Tests for POST /webhooks/clerk.

The handler is shared with /auth/clerk/webhook via _handle_clerk_webhook — these
tests verify the new path is routed correctly and applies the same signature
verification logic.  Full event-handling scenarios are covered by the existing
auth and webhook-probe tests.
"""

from httpx import AsyncClient


class TestClerkWebhookPath:
    async def test_rejects_missing_secret_config(self, client: AsyncClient, monkeypatch):
        """Returns 500 when CLERK_WEBHOOK_SECRET is not configured."""
        import app.routers.auth as auth_module

        monkeypatch.setattr(auth_module, "settings", type("S", (), {"clerk_webhook_secret": ""})())
        resp = await client.post(
            "/webhooks/clerk",
            content=b"{}",
            headers={"content-type": "application/json"},
        )
        assert resp.status_code == 500

    async def test_rejects_invalid_signature(self, client: AsyncClient, monkeypatch):
        """Returns 400 for a request with a missing or invalid Svix signature."""
        import app.routers.auth as auth_module

        monkeypatch.setattr(auth_module, "settings", type("S", (), {"clerk_webhook_secret": "whsec_test"})())
        resp = await client.post(
            "/webhooks/clerk",
            content=b'{"type":"user.created","data":{}}',
            headers={"content-type": "application/json"},
        )
        assert resp.status_code == 400

    async def test_route_exists(self, client: AsyncClient):
        """Endpoint is registered — does not 404."""
        resp = await client.post("/webhooks/clerk", content=b"{}")
        assert resp.status_code != 404
