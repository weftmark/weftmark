"""
Tests for app.services.email.

aiosmtplib.send is mocked with AsyncMock so no real SMTP connection is made.
Settings are patched per-test via monkeypatch to keep tests independent of
the local .env file.
"""

import pytest
from unittest.mock import AsyncMock, patch, call
from app.services.email import send_invite_email


# ---------------------------------------------------------------------------
# Fixture: deterministic settings
# ---------------------------------------------------------------------------

SETTINGS_OVERRIDES = {
    "frontend_url": "http://example.com",
    "smtp_from_name": "Test Site",
    "smtp_from_email": "noreply@example.com",
    "smtp_host": "smtp.example.com",
    "smtp_port": 587,
    "smtp_user": "smtpuser",
    "smtp_password": "smtppass",
}


@pytest.fixture(autouse=True)
def _patch_settings(monkeypatch):
    """Override all settings consumed by send_invite_email."""
    from app.config import get_settings
    settings = get_settings()
    for attr, value in SETTINGS_OVERRIDES.items():
        monkeypatch.setattr(settings, attr, value)


# ---------------------------------------------------------------------------
# Helper: run send_invite_email with a mock SMTP sender
# ---------------------------------------------------------------------------

async def _send(to="user@test.com", token="tok123", days=7):
    mock_send = AsyncMock()
    with patch("app.services.email.aiosmtplib.send", mock_send):
        await send_invite_email(to, token, days)
    return mock_send


# ---------------------------------------------------------------------------
# SMTP transport — what aiosmtplib.send receives
# ---------------------------------------------------------------------------

class TestSmtpTransport:
    async def test_send_called_once(self):
        mock = await _send()
        mock.assert_called_once()

    async def test_smtp_hostname(self):
        mock = await _send()
        _, kwargs = mock.call_args
        assert kwargs["hostname"] == "smtp.example.com"

    async def test_smtp_port(self):
        mock = await _send()
        _, kwargs = mock.call_args
        assert kwargs["port"] == 587

    async def test_smtp_username(self):
        mock = await _send()
        _, kwargs = mock.call_args
        assert kwargs["username"] == "smtpuser"

    async def test_smtp_password(self):
        mock = await _send()
        _, kwargs = mock.call_args
        assert kwargs["password"] == "smtppass"

    async def test_start_tls_enabled(self):
        mock = await _send()
        _, kwargs = mock.call_args
        assert kwargs["start_tls"] is True


# ---------------------------------------------------------------------------
# Message headers
# ---------------------------------------------------------------------------

class TestMessageHeaders:
    async def _message(self, **kwargs):
        mock_send = AsyncMock()
        with patch("app.services.email.aiosmtplib.send", mock_send):
            await send_invite_email(**{"to_email": "u@t.com", "invite_token": "t", "expires_days": 7, **kwargs})
        msg, *_ = mock_send.call_args.args
        return msg

    async def test_to_header(self):
        msg = await self._message(to_email="recipient@test.com")
        assert msg["To"] == "recipient@test.com"

    async def test_from_header_includes_name(self):
        msg = await self._message()
        assert "Test Site" in msg["From"]

    async def test_from_header_includes_email(self):
        msg = await self._message()
        assert "noreply@example.com" in msg["From"]

    async def test_subject_includes_site_name(self):
        msg = await self._message()
        assert "Test Site" in msg["Subject"]

    async def test_message_is_multipart(self):
        msg = await self._message()
        assert msg.get_content_type() == "multipart/alternative"

    async def test_has_plain_and_html_parts(self):
        msg = await self._message()
        content_types = [part.get_content_type() for part in msg.get_payload()]
        assert "text/plain" in content_types
        assert "text/html" in content_types


# ---------------------------------------------------------------------------
# Message body content
# ---------------------------------------------------------------------------

class TestPlainTextBody:
    async def _plain(self, token="abc", days=7, to="u@t.com"):
        mock_send = AsyncMock()
        with patch("app.services.email.aiosmtplib.send", mock_send):
            await send_invite_email(to, token, days)
        msg, *_ = mock_send.call_args.args
        return next(p for p in msg.get_payload() if p.get_content_type() == "text/plain").get_payload()

    async def test_contains_invite_url(self):
        body = await self._plain(token="mytoken")
        assert "http://example.com/register?token=mytoken" in body

    async def test_contains_token(self):
        body = await self._plain(token="tok999")
        assert "tok999" in body

    async def test_contains_expiry_days(self):
        body = await self._plain(days=14)
        assert "14" in body

    async def test_contains_site_name(self):
        body = await self._plain()
        assert "Test Site" in body

    async def test_mentions_single_use(self):
        body = await self._plain()
        assert "once" in body.lower()


class TestHtmlBody:
    async def _html(self, token="abc", days=7):
        mock_send = AsyncMock()
        with patch("app.services.email.aiosmtplib.send", mock_send):
            await send_invite_email("u@t.com", token, days)
        msg, *_ = mock_send.call_args.args
        return next(p for p in msg.get_payload() if p.get_content_type() == "text/html").get_payload()

    async def test_contains_invite_url(self):
        html = await self._html(token="htmltoken")
        assert "http://example.com/register?token=htmltoken" in html

    async def test_contains_anchor_tag(self):
        html = await self._html()
        assert "<a href=" in html

    async def test_contains_expiry_days(self):
        html = await self._html(days=3)
        assert "3" in html

    async def test_contains_site_name(self):
        html = await self._html()
        assert "Test Site" in html


# ---------------------------------------------------------------------------
# Invite URL construction
# ---------------------------------------------------------------------------

class TestInviteUrl:
    async def _url_in_plain(self, token, frontend_url="http://example.com"):
        mock_send = AsyncMock()
        from app.config import get_settings
        get_settings().frontend_url = frontend_url
        with patch("app.services.email.aiosmtplib.send", mock_send):
            await send_invite_email("u@t.com", token, 7)
        msg, *_ = mock_send.call_args.args
        return next(p for p in msg.get_payload() if p.get_content_type() == "text/plain").get_payload()

    async def test_token_appended_as_query_param(self):
        body = await self._url_in_plain("secrettoken")
        assert "?token=secrettoken" in body

    async def test_url_uses_frontend_url(self):
        body = await self._url_in_plain("t", frontend_url="http://myapp.local:3000")
        assert "http://myapp.local:3000/register" in body

    async def test_different_tokens_produce_different_urls(self):
        body1 = await self._url_in_plain("aaa")
        body2 = await self._url_in_plain("bbb")
        assert "aaa" in body1
        assert "bbb" in body2
        assert "bbb" not in body1
