"""
Tests for app.services.email.

aiosmtplib.send is mocked with AsyncMock so no real SMTP connection is made.
Settings are patched per-test via monkeypatch to keep tests independent of
the local .env file.
"""

from unittest.mock import AsyncMock, patch

import pytest

from app.services.email import (
    send_account_approved_email,
    send_account_denied_email,
    send_approval_confirmation_to_admins,
    send_invite_email,
    send_pending_signup_notification,
    send_signup_received_email,
    send_test_email,
)


def _decoded_body(msg) -> str:
    """Return all MIME body parts as a single decoded string."""
    return " ".join(p.get_payload(decode=True).decode("utf-8") for p in msg.get_payload())


def _plain_body(msg) -> str:
    """Return the plain-text MIME part decoded as a string."""
    part = next(p for p in msg.get_payload() if p.get_content_type() == "text/plain")
    return part.get_payload(decode=True).decode("utf-8")


def _html_body(msg) -> str:
    """Return the HTML MIME part decoded as a string."""
    part = next(p for p in msg.get_payload() if p.get_content_type() == "text/html")
    return part.get_payload(decode=True).decode("utf-8")


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
    "app_env": "test",
}


@pytest.fixture(autouse=True)
def _patch_settings(monkeypatch):
    from app.config import get_settings

    settings = get_settings()
    for attr, value in SETTINGS_OVERRIDES.items():
        monkeypatch.setattr(settings, attr, value)


# ---------------------------------------------------------------------------
# Helper: call send_invite_email with a mock SMTP sender
# ---------------------------------------------------------------------------


async def _send_invite(to="user@test.com", token="tok123", days=7):
    mock_send = AsyncMock()
    with patch("app.services.email.aiosmtplib.send", mock_send):
        await send_invite_email(to, token, days)
    return mock_send


# ---------------------------------------------------------------------------
# SMTP transport
# ---------------------------------------------------------------------------


class TestSmtpTransport:
    async def test_send_called_once(self):
        mock = await _send_invite()
        mock.assert_called_once()

    async def test_smtp_hostname(self):
        mock = await _send_invite()
        _, kwargs = mock.call_args
        assert kwargs["hostname"] == "smtp.example.com"

    async def test_smtp_port(self):
        mock = await _send_invite()
        _, kwargs = mock.call_args
        assert kwargs["port"] == 587

    async def test_smtp_username(self):
        mock = await _send_invite()
        _, kwargs = mock.call_args
        assert kwargs["username"] == "smtpuser"

    async def test_smtp_password(self):
        mock = await _send_invite()
        _, kwargs = mock.call_args
        assert kwargs["password"] == "smtppass"

    async def test_start_tls_enabled(self):
        mock = await _send_invite()
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
# Invite plain text body
# ---------------------------------------------------------------------------


class TestPlainTextBody:
    async def _plain(self, token="abc", days=7, to="u@t.com"):
        mock_send = AsyncMock()
        with patch("app.services.email.aiosmtplib.send", mock_send):
            await send_invite_email(to, token, days)
        msg, *_ = mock_send.call_args.args
        return _plain_body(msg)

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


# ---------------------------------------------------------------------------
# Invite HTML body
# ---------------------------------------------------------------------------


class TestHtmlBody:
    async def _html(self, token="abc", days=7):
        mock_send = AsyncMock()
        with patch("app.services.email.aiosmtplib.send", mock_send):
            await send_invite_email("u@t.com", token, days)
        msg, *_ = mock_send.call_args.args
        return _html_body(msg)

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
        return _plain_body(msg)

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


# ---------------------------------------------------------------------------
# Template rendering
# ---------------------------------------------------------------------------


class TestTemplateRendering:
    def test_render_returns_txt_and_html(self):
        from app.services.email import _render

        txt, html = _render(
            "account_approved",
            display_name="Alice",
            login_url="http://example.com/login",
        )
        assert "Alice" in txt
        assert "Alice" in html
        assert "Test Site" in txt
        assert "Test Site" in html

    def test_render_substitutes_all_placeholders(self):
        from app.services.email import _render

        txt, _ = _render("account_denied", display_name="Bob")
        assert "Bob" in txt
        assert "{" not in txt

    def test_render_includes_base_footer(self):
        from app.services.email import _render

        txt, html = _render("account_approved", display_name="X", login_url="http://example.com/login")
        assert "example.com" in txt
        assert "example.com" in html

    def test_render_invite_template(self):
        from app.services.email import _render

        txt, html = _render(
            "invite",
            invite_url="http://example.com/register?token=abc",
            expires_days=7,
        )
        assert "http://example.com/register?token=abc" in txt
        assert "http://example.com/register?token=abc" in html
        assert "7" in txt

    def test_render_test_email_template(self):
        from app.services.email import _render

        txt, html = _render("test_email")
        assert "Test Site" in txt
        assert "Test Site" in html


# ---------------------------------------------------------------------------
# send_test_email
# ---------------------------------------------------------------------------


class TestSendTestEmail:
    async def _call(self, to="admin@test.com"):
        mock_send = AsyncMock()
        with patch("app.services.email.aiosmtplib.send", mock_send):
            await send_test_email(to)
        return mock_send

    async def test_send_called_once(self):
        mock = await self._call()
        mock.assert_called_once()

    async def test_recipient_is_to_email(self):
        mock = await self._call(to="specific@test.com")
        msg, *_ = mock.call_args.args
        assert "specific@test.com" in msg["To"]

    async def test_subject_mentions_site_name(self):
        mock = await self._call()
        msg, *_ = mock.call_args.args
        assert "Test Site" in msg["Subject"]

    async def test_subject_mentions_smtp(self):
        mock = await self._call()
        msg, *_ = mock.call_args.args
        assert "SMTP" in msg["Subject"] or "Test" in msg["Subject"]

    async def test_body_confirms_delivery(self):
        mock = await self._call()
        msg, *_ = mock.call_args.args
        combined = _decoded_body(msg)
        assert "test" in combined.lower()
        assert "Test Site" in combined


# ---------------------------------------------------------------------------
# send_pending_signup_notification
# ---------------------------------------------------------------------------


class TestSendPendingSignupNotification:
    async def _call(self, admin_emails=None, display_name="Alice", email="alice@test.com"):
        if admin_emails is None:
            admin_emails = ["admin@example.com"]
        mock_send = AsyncMock()
        with patch("app.services.email.aiosmtplib.send", mock_send):
            await send_pending_signup_notification(admin_emails, display_name, email)
        return mock_send

    async def test_send_called_once(self):
        mock = await self._call()
        mock.assert_called_once()

    async def test_recipients_include_admin(self):
        mock = await self._call(admin_emails=["a@test.com", "b@test.com"])
        msg, *_ = mock.call_args.args
        assert "a@test.com" in msg["To"]
        assert "b@test.com" in msg["To"]

    async def test_subject_mentions_signup(self):
        mock = await self._call()
        msg, *_ = mock.call_args.args
        assert "sign" in msg["Subject"].lower() or "approval" in msg["Subject"].lower()

    async def test_body_contains_display_name(self):
        mock = await self._call(display_name="Weaver Jane")
        msg, *_ = mock.call_args.args
        combined = _decoded_body(msg)
        assert "Weaver Jane" in combined


# ---------------------------------------------------------------------------
# send_signup_received_email
# ---------------------------------------------------------------------------


class TestSendSignupReceivedEmail:
    async def _call(self, to="user@test.com", display_name="Bob"):
        mock_send = AsyncMock()
        with patch("app.services.email.aiosmtplib.send", mock_send):
            await send_signup_received_email(to, display_name)
        return mock_send

    async def test_send_called_once(self):
        mock = await self._call()
        mock.assert_called_once()

    async def test_recipient_is_user(self):
        mock = await self._call(to="specific@test.com")
        msg, *_ = mock.call_args.args
        assert "specific@test.com" in msg["To"]

    async def test_body_contains_display_name(self):
        mock = await self._call(display_name="Carol Weaver")
        msg, *_ = mock.call_args.args
        combined = _decoded_body(msg)
        assert "Carol Weaver" in combined


# ---------------------------------------------------------------------------
# send_account_approved_email
# ---------------------------------------------------------------------------


class TestSendAccountApprovedEmail:
    async def _call(self, to="user@test.com", display_name="Dave"):
        mock_send = AsyncMock()
        with patch("app.services.email.aiosmtplib.send", mock_send):
            await send_account_approved_email(to, display_name)
        return mock_send

    async def test_send_called_once(self):
        mock = await self._call()
        mock.assert_called_once()

    async def test_recipient_is_user(self):
        mock = await self._call(to="dave@test.com")
        msg, *_ = mock.call_args.args
        assert "dave@test.com" in msg["To"]

    async def test_subject_mentions_account(self):
        mock = await self._call()
        msg, *_ = mock.call_args.args
        assert (
            "account" in msg["Subject"].lower()
            or "approved" in msg["Subject"].lower()
            or "ready" in msg["Subject"].lower()
        )

    async def test_body_contains_login_url(self):
        mock = await self._call()
        msg, *_ = mock.call_args.args
        combined = _decoded_body(msg)
        assert "login" in combined.lower() or "sign" in combined.lower()


# ---------------------------------------------------------------------------
# send_account_denied_email
# ---------------------------------------------------------------------------


class TestSendAccountDeniedEmail:
    async def _call(self, to="user@test.com", display_name="Eve"):
        mock_send = AsyncMock()
        with patch("app.services.email.aiosmtplib.send", mock_send):
            await send_account_denied_email(to, display_name)
        return mock_send

    async def test_send_called_once(self):
        mock = await self._call()
        mock.assert_called_once()

    async def test_recipient_is_user(self):
        mock = await self._call(to="eve@test.com")
        msg, *_ = mock.call_args.args
        assert "eve@test.com" in msg["To"]

    async def test_body_contains_display_name(self):
        mock = await self._call(display_name="Eve Woven")
        msg, *_ = mock.call_args.args
        combined = _decoded_body(msg)
        assert "Eve Woven" in combined


# ---------------------------------------------------------------------------
# send_approval_confirmation_to_admins
# ---------------------------------------------------------------------------


class TestSendApprovalConfirmationToAdmins:
    async def _call(self, admin_emails=None, display_name="Frank", email="frank@test.com", approved_by="Admin A"):
        if admin_emails is None:
            admin_emails = ["admin@example.com"]
        mock_send = AsyncMock()
        with patch("app.services.email.aiosmtplib.send", mock_send):
            await send_approval_confirmation_to_admins(admin_emails, display_name, email, approved_by)
        return mock_send

    async def test_send_called_once(self):
        mock = await self._call()
        mock.assert_called_once()

    async def test_recipients_include_all_admins(self):
        mock = await self._call(admin_emails=["x@test.com", "y@test.com"])
        msg, *_ = mock.call_args.args
        assert "x@test.com" in msg["To"]
        assert "y@test.com" in msg["To"]

    async def test_subject_contains_user_name(self):
        mock = await self._call(display_name="Frank Loom")
        msg, *_ = mock.call_args.args
        assert "Frank Loom" in msg["Subject"]

    async def test_body_contains_approved_by(self):
        mock = await self._call(approved_by="Super Admin")
        msg, *_ = mock.call_args.args
        combined = _decoded_body(msg)
        assert "Super Admin" in combined
