"""Tests for app.services.smtp_health — TCP probe and circuit-breaker logic."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import app.services.smtp_health as smtp_health


@pytest.fixture(autouse=True)
def _reset():
    """Reset circuit-breaker state before every test."""
    smtp_health.reset()
    yield
    smtp_health.reset()


# ---------------------------------------------------------------------------
# TCP probe unit tests
# ---------------------------------------------------------------------------


class TestTcpProbe:
    async def test_success_returns_true_and_message(self):
        mock_reader = MagicMock()
        mock_writer = MagicMock()
        mock_writer.wait_closed = AsyncMock()

        with patch("asyncio.open_connection", return_value=(mock_reader, mock_writer)):
            ok, msg = await smtp_health._tcp_probe("smtp.example.com", 587)

        assert ok is True
        assert "smtp.example.com" in msg
        assert "587" in msg

    async def test_timeout_returns_false(self):
        with patch("asyncio.open_connection", side_effect=asyncio.TimeoutError):
            ok, msg = await smtp_health._tcp_probe("smtp.example.com", 587)

        assert ok is False
        assert "timed out" in msg.lower()

    async def test_oserror_returns_false(self):
        with patch("asyncio.open_connection", side_effect=OSError("Connection refused")):
            ok, msg = await smtp_health._tcp_probe("smtp.example.com", 587)

        assert ok is False
        assert "Connection refused" in msg

    async def test_writer_closed_on_success(self):
        mock_reader = MagicMock()
        mock_writer = MagicMock()
        mock_writer.wait_closed = AsyncMock()

        with patch("asyncio.open_connection", return_value=(mock_reader, mock_writer)):
            await smtp_health._tcp_probe("smtp.example.com", 587)

        mock_writer.close.assert_called_once()
        mock_writer.wait_closed.assert_called_once()


# ---------------------------------------------------------------------------
# Circuit-breaker logic via check()
# ---------------------------------------------------------------------------


class TestCircuitBreaker:
    async def test_success_returns_ok(self):
        mock_reader = MagicMock()
        mock_writer = MagicMock()
        mock_writer.wait_closed = AsyncMock()

        with patch("asyncio.open_connection", return_value=(mock_reader, mock_writer)):
            ok, msg = await smtp_health.check("smtp.example.com", 587)

        assert ok is True

    async def test_failure_sets_backoff(self):
        with patch("asyncio.open_connection", side_effect=OSError("refused")):
            ok, _ = await smtp_health.check("smtp.example.com", 587)

        assert ok is False
        assert smtp_health._in_backoff is True

    async def test_backoff_returns_cached_without_probing(self):
        # First call — fail, enter backoff
        with patch("asyncio.open_connection", side_effect=OSError("refused")):
            await smtp_health.check("smtp.example.com", 587)

        # Second call — should NOT open a new connection
        with patch("asyncio.open_connection", side_effect=AssertionError("should not probe")) as mock_conn:
            ok, msg = await smtp_health.check("smtp.example.com", 587)
            mock_conn.assert_not_called()

        assert ok is False
        assert "cached" in msg

    async def test_backoff_retries_after_window(self):
        # First call — fail, enter backoff
        with patch("asyncio.open_connection", side_effect=OSError("refused")):
            await smtp_health.check("smtp.example.com", 587)

        # Wind the clock past BACKOFF_SECONDS
        past = datetime.now(timezone.utc) - timedelta(seconds=smtp_health.BACKOFF_SECONDS + 1)
        smtp_health._last_checked_at = past

        # Second call — should attempt a fresh probe (and succeed this time)
        mock_reader = MagicMock()
        mock_writer = MagicMock()
        mock_writer.wait_closed = AsyncMock()

        with patch("asyncio.open_connection", return_value=(mock_reader, mock_writer)):
            ok, msg = await smtp_health.check("smtp.example.com", 587)

        assert ok is True
        assert "cached" not in msg

    async def test_success_resets_backoff(self):
        # Enter backoff
        with patch("asyncio.open_connection", side_effect=OSError("refused")):
            await smtp_health.check("smtp.example.com", 587)

        assert smtp_health._in_backoff is True

        # Expire backoff window and probe successfully
        smtp_health._last_checked_at = datetime.now(timezone.utc) - timedelta(seconds=smtp_health.BACKOFF_SECONDS + 1)
        mock_reader = MagicMock()
        mock_writer = MagicMock()
        mock_writer.wait_closed = AsyncMock()

        with patch("asyncio.open_connection", return_value=(mock_reader, mock_writer)):
            ok, _ = await smtp_health.check("smtp.example.com", 587)

        assert ok is True
        assert smtp_health._in_backoff is False

    async def test_no_backoff_on_first_call_without_prior_failure(self):
        """Fresh state: first call always probes live even if _in_backoff were somehow True."""
        smtp_health.reset()
        assert smtp_health._in_backoff is False
        assert smtp_health._last_checked_at is None

        mock_reader = MagicMock()
        mock_writer = MagicMock()
        mock_writer.wait_closed = AsyncMock()

        with patch("asyncio.open_connection", return_value=(mock_reader, mock_writer)):
            ok, _ = await smtp_health.check("smtp.example.com", 587)

        assert ok is True

    async def test_cached_message_includes_retry_countdown(self):
        with patch("asyncio.open_connection", side_effect=OSError("refused")):
            await smtp_health.check("smtp.example.com", 587)

        _, msg = await smtp_health.check("smtp.example.com", 587)
        assert "retry in" in msg
        assert "cached" in msg


# ---------------------------------------------------------------------------
# reset() helper
# ---------------------------------------------------------------------------


class TestReset:
    async def test_reset_clears_state(self):
        with patch("asyncio.open_connection", side_effect=OSError("refused")):
            await smtp_health.check("smtp.example.com", 587)

        smtp_health.reset()

        assert smtp_health._last_ok is None
        assert smtp_health._last_message == ""
        assert smtp_health._last_checked_at is None
        assert smtp_health._in_backoff is False
