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

    async def test_accepts_valid_signature(self, client: AsyncClient, monkeypatch):
        """A correctly signed event is parsed and acknowledged.

        Regression guard for svix 2.x, where Webhook.verify() returns None
        instead of the decoded payload — the handler must parse the body itself.
        """
        import base64
        import json
        from datetime import datetime, timezone

        from svix.webhooks import Webhook

        import app.routers.auth as auth_module

        secret = "whsec_" + base64.b64encode(b"weftmark-test-webhook-secret!").decode()
        monkeypatch.setattr(auth_module, "settings", type("S", (), {"clerk_webhook_secret": secret})())

        msg_id = "msg_test_valid_signature"
        ts = datetime.now(timezone.utc)
        body = json.dumps({"type": "test.unhandled_event", "data": {"id": "user_test_123"}})
        signature = Webhook(secret).sign(msg_id, ts, body)

        resp = await client.post(
            "/webhooks/clerk",
            content=body.encode(),
            headers={
                "content-type": "application/json",
                "svix-id": msg_id,
                "svix-timestamp": str(int(ts.timestamp())),
                "svix-signature": signature,
            },
        )
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}

    async def test_rejects_signed_non_json_body(self, client: AsyncClient, monkeypatch):
        """A correctly signed body that isn't a JSON object is rejected with 400, not 500."""
        import base64
        from datetime import datetime, timezone

        from svix.webhooks import Webhook

        import app.routers.auth as auth_module

        secret = "whsec_" + base64.b64encode(b"weftmark-test-webhook-secret!").decode()
        monkeypatch.setattr(auth_module, "settings", type("S", (), {"clerk_webhook_secret": secret})())

        msg_id = "msg_test_non_json"
        ts = datetime.now(timezone.utc)
        body = "[1, 2, 3]"
        signature = Webhook(secret).sign(msg_id, ts, body)

        resp = await client.post(
            "/webhooks/clerk",
            content=body.encode(),
            headers={
                "content-type": "application/json",
                "svix-id": msg_id,
                "svix-timestamp": str(int(ts.timestamp())),
                "svix-signature": signature,
            },
        )
        assert resp.status_code == 400
