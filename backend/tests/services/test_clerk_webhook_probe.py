"""Tests for app.services.clerk_webhook_probe."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.services.clerk_webhook_probe as probe_module
from app.services.clerk_webhook_probe import run_webhook_probe, signal_probe


def _mock_settings(
    *,
    base_url: str = "https://example.com",
    secret: str = "whsec_test",
    timeout: int = 5,
    api_url: str = "https://api.example.com",
):
    return MagicMock(
        webhook_base_url=base_url,
        clerk_webhook_secret=secret,
        clerk_webhook_probe_timeout_s=timeout,
        api_url=api_url,
    )


@pytest.fixture(autouse=True)
def reset_probe_state():
    """Ensure module-level asyncio state is clean between tests."""
    probe_module._pending_event = None
    probe_module._probe_lock = None
    yield
    probe_module._pending_event = None
    probe_module._probe_lock = None


# ---------------------------------------------------------------------------
# signal_probe
# ---------------------------------------------------------------------------


class TestSignalProbe:
    def test_noop_when_no_pending_event(self):
        probe_module._pending_event = None
        signal_probe()  # must not raise

    def test_sets_event_when_pending(self):
        event = asyncio.Event()
        probe_module._pending_event = event
        signal_probe()
        assert event.is_set()


# ---------------------------------------------------------------------------
# run_webhook_probe — config guard paths (no network)
# ---------------------------------------------------------------------------


class TestRunWebhookProbeConfig:
    async def test_error_when_no_webhook_secret(self, monkeypatch):
        monkeypatch.setattr(probe_module, "get_settings", lambda: _mock_settings(secret=""))
        result = await run_webhook_probe()
        assert result.status == "error"
        assert "CLERK_WEBHOOK_SECRET" in result.message


# ---------------------------------------------------------------------------
# run_webhook_probe — network paths (mock httpx + Webhook.sign)
# ---------------------------------------------------------------------------


def _patched_client(*, status_code: int = 200, post_side_effect=None):
    """Return a context-manager mock for httpx.AsyncClient."""
    mock_response = MagicMock()
    mock_response.status_code = status_code

    mock_client = MagicMock()
    if post_side_effect:
        mock_client.post = AsyncMock(side_effect=post_side_effect)
    else:
        mock_client.post = AsyncMock(return_value=mock_response)

    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=mock_client)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


class TestRunWebhookProbeNetwork:
    @pytest.fixture(autouse=True)
    def patch_sign(self):
        with patch("app.services.clerk_webhook_probe.Webhook") as MockWebhook:
            MockWebhook.return_value.sign.return_value = "v1,fakesig"
            yield MockWebhook

    async def test_success_when_probe_event_signalled(self, monkeypatch):
        monkeypatch.setattr(probe_module, "get_settings", lambda: _mock_settings())

        async def post_and_signal(*_args, **_kwargs):
            asyncio.create_task(_signal_soon())
            return MagicMock(status_code=200)

        with patch("httpx.AsyncClient", return_value=_patched_client(post_side_effect=post_and_signal)):
            result = await run_webhook_probe()

        assert result.status == "ok"
        assert result.latency_ms is not None

    async def test_error_on_timeout(self, monkeypatch):
        monkeypatch.setattr(probe_module, "get_settings", lambda: _mock_settings(timeout=0))
        # POST succeeds but nobody signals the event → timeout
        with patch("httpx.AsyncClient", return_value=_patched_client(status_code=200)):
            result = await run_webhook_probe()

        assert result.status == "error"
        assert "not received" in result.message

    async def test_error_on_non_200_status(self, monkeypatch):
        monkeypatch.setattr(probe_module, "get_settings", lambda: _mock_settings())
        with patch("httpx.AsyncClient", return_value=_patched_client(status_code=500)):
            result = await run_webhook_probe()

        assert result.status == "error"
        assert "500" in result.message

    async def test_error_on_http_timeout(self, monkeypatch):
        import httpx

        monkeypatch.setattr(probe_module, "get_settings", lambda: _mock_settings())
        with patch(
            "httpx.AsyncClient",
            return_value=_patched_client(post_side_effect=httpx.TimeoutException("timed out")),
        ):
            result = await run_webhook_probe()

        assert result.status == "error"
        assert "timed out" in result.message.lower()

    async def test_error_on_connection_error(self, monkeypatch):
        monkeypatch.setattr(probe_module, "get_settings", lambda: _mock_settings())
        with patch(
            "httpx.AsyncClient",
            return_value=_patched_client(post_side_effect=OSError("connection refused")),
        ):
            result = await run_webhook_probe()

        assert result.status == "error"
        assert "POST failed" in result.message

    async def test_webhook_url_constructed_from_base_url(self, monkeypatch):
        monkeypatch.setattr(probe_module, "get_settings", lambda: _mock_settings(base_url="https://api.example.com/"))
        calls: list[str] = []

        async def capture_url(url, *_a, **_kw):
            calls.append(url)
            return MagicMock(status_code=200)

        with patch("httpx.AsyncClient", return_value=_patched_client(post_side_effect=capture_url)):
            await run_webhook_probe()

        assert calls and calls[0] == "https://api.example.com/auth/clerk/webhook"

    async def test_webhook_url_falls_back_to_api_url(self, monkeypatch):
        monkeypatch.setattr(
            probe_module,
            "get_settings",
            lambda: _mock_settings(base_url="", api_url="https://fallback.example.com/"),
        )
        calls: list[str] = []

        async def capture_url(url, *_a, **_kw):
            calls.append(url)
            return MagicMock(status_code=200)

        with patch("httpx.AsyncClient", return_value=_patched_client(post_side_effect=capture_url)):
            await run_webhook_probe()

        assert calls and calls[0] == "https://fallback.example.com/auth/clerk/webhook"


# ---------------------------------------------------------------------------
# Helper coroutine
# ---------------------------------------------------------------------------


async def _signal_soon() -> None:
    await asyncio.sleep(0)
    signal_probe()
