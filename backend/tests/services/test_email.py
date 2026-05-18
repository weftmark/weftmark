"""
Tests for app.services.email.

send_email.delay is mocked so no real Celery worker or SMTP connection is needed.
Settings are patched per-test via monkeypatch.

SMTP transport and MIME construction are tested in tests/tasks/test_email_task.py.
"""

from unittest.mock import MagicMock, patch

import pytest

from app.services.email import (
    _digest_cve_html,
    _digest_cve_txt,
    _digest_s3_html,
    _digest_s3_txt,
    _format_uptime,
    send_account_approved_email,
    send_account_denied_email,
    send_admin_digest_email,
    send_approval_confirmation_to_admins,
    send_credential_expiring_admin,
    send_credential_expiring_superuser,
    send_deletion_completed_admin,
    send_deletion_created_admin,
    send_deletion_stalled_superuser,
    send_feedback_admin_alert,
    send_feedback_user_confirmation,
    send_health_degraded_alert,
    send_health_recovered_alert,
    send_invite_email,
    send_pending_signup_notification,
    send_signup_received_email,
    send_stack_shutdown_alert,
    send_stack_startup_alert,
    send_test_email,
)

# ---------------------------------------------------------------------------
# Fixture: deterministic settings
# ---------------------------------------------------------------------------

SETTINGS_OVERRIDES = {
    "frontend_url": "http://example.com",
    "app_name": "Test Site",
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
# Helper: enqueue an invite and return the delay mock
# ---------------------------------------------------------------------------


async def _send_invite(to="user@test.com", token="tok123", days=7):
    mock_delay = MagicMock()
    with patch("app.tasks.email_task.send_email.delay", mock_delay):
        await send_invite_email(to, token, days)
    return mock_delay


def _kwargs(mock_delay: MagicMock) -> dict:
    """Return the keyword arguments passed to send_email.delay."""
    return mock_delay.call_args.kwargs


# ---------------------------------------------------------------------------
# Enqueue behaviour
# ---------------------------------------------------------------------------


class TestEnqueueBehaviour:
    async def test_delay_called_once(self):
        mock = await _send_invite()
        mock.assert_called_once()

    async def test_delay_called_with_to(self):
        mock = await _send_invite(to="recipient@test.com")
        assert "recipient@test.com" in _kwargs(mock)["to"]

    async def test_delay_called_with_subject(self):
        mock = await _send_invite()
        assert _kwargs(mock)["subject"]

    async def test_delay_called_with_txt(self):
        mock = await _send_invite()
        assert _kwargs(mock)["txt"]

    async def test_delay_called_with_html(self):
        mock = await _send_invite()
        assert _kwargs(mock)["html"]

    async def test_delay_called_with_queued_at(self):
        mock = await _send_invite()
        assert _kwargs(mock)["queued_at"]


# ---------------------------------------------------------------------------
# Invite plain text body
# ---------------------------------------------------------------------------


class TestPlainTextBody:
    async def _plain(self, token="abc", days=7, to="u@t.com"):
        mock_delay = MagicMock()
        with patch("app.tasks.email_task.send_email.delay", mock_delay):
            await send_invite_email(to, token, days)
        return _kwargs(mock_delay)["txt"]

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
        mock_delay = MagicMock()
        with patch("app.tasks.email_task.send_email.delay", mock_delay):
            await send_invite_email("u@t.com", token, days)
        return _kwargs(mock_delay)["html"]

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
        from app.config import get_settings

        get_settings().frontend_url = frontend_url
        mock_delay = MagicMock()
        with patch("app.tasks.email_task.send_email.delay", mock_delay):
            await send_invite_email("u@t.com", token, 7)
        return _kwargs(mock_delay)["txt"]

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
            admin_name="A weftmark admin",
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
        mock_delay = MagicMock()
        with patch("app.tasks.email_task.send_email.delay", mock_delay):
            await send_test_email(to)
        return mock_delay

    async def test_delay_called_once(self):
        mock = await self._call()
        mock.assert_called_once()

    async def test_recipient_is_to_email(self):
        mock = await self._call(to="specific@test.com")
        assert "specific@test.com" in _kwargs(mock)["to"]

    async def test_subject_mentions_site_name(self):
        mock = await self._call()
        assert "Test Site" in _kwargs(mock)["subject"]

    async def test_subject_mentions_smtp(self):
        mock = await self._call()
        assert "SMTP" in _kwargs(mock)["subject"] or "Test" in _kwargs(mock)["subject"]

    async def test_body_confirms_delivery(self):
        mock = await self._call()
        combined = _kwargs(mock)["txt"] + " " + _kwargs(mock)["html"]
        assert "test" in combined.lower()
        assert "Test Site" in combined


# ---------------------------------------------------------------------------
# send_pending_signup_notification
# ---------------------------------------------------------------------------


class TestSendPendingSignupNotification:
    async def _call(self, admin_emails=None, display_name="Alice", email="alice@test.com"):
        if admin_emails is None:
            admin_emails = ["admin@example.com"]
        mock_delay = MagicMock()
        with patch("app.tasks.email_task.send_email.delay", mock_delay):
            await send_pending_signup_notification(admin_emails, display_name, email)
        return mock_delay

    async def test_delay_called_once(self):
        mock = await self._call()
        mock.assert_called_once()

    async def test_recipients_include_admin(self):
        mock = await self._call(admin_emails=["a@test.com", "b@test.com"])
        to = _kwargs(mock)["to"]
        assert "a@test.com" in to
        assert "b@test.com" in to

    async def test_subject_mentions_signup(self):
        mock = await self._call()
        subj = _kwargs(mock)["subject"].lower()
        assert "sign" in subj or "approval" in subj

    async def test_body_contains_display_name(self):
        mock = await self._call(display_name="Weaver Jane")
        combined = _kwargs(mock)["txt"] + " " + _kwargs(mock)["html"]
        assert "Weaver Jane" in combined


# ---------------------------------------------------------------------------
# send_signup_received_email
# ---------------------------------------------------------------------------


class TestSendSignupReceivedEmail:
    async def _call(self, to="user@test.com", display_name="Bob"):
        mock_delay = MagicMock()
        with patch("app.tasks.email_task.send_email.delay", mock_delay):
            await send_signup_received_email(to, display_name)
        return mock_delay

    async def test_delay_called_once(self):
        mock = await self._call()
        mock.assert_called_once()

    async def test_recipient_is_user(self):
        mock = await self._call(to="specific@test.com")
        assert "specific@test.com" in _kwargs(mock)["to"]

    async def test_body_contains_display_name(self):
        mock = await self._call(display_name="Carol Weaver")
        combined = _kwargs(mock)["txt"] + " " + _kwargs(mock)["html"]
        assert "Carol Weaver" in combined


# ---------------------------------------------------------------------------
# send_account_approved_email
# ---------------------------------------------------------------------------


class TestSendAccountApprovedEmail:
    async def _call(self, to="user@test.com", display_name="Dave"):
        mock_delay = MagicMock()
        with patch("app.tasks.email_task.send_email.delay", mock_delay):
            await send_account_approved_email(to, display_name)
        return mock_delay

    async def test_delay_called_once(self):
        mock = await self._call()
        mock.assert_called_once()

    async def test_recipient_is_user(self):
        mock = await self._call(to="dave@test.com")
        assert "dave@test.com" in _kwargs(mock)["to"]

    async def test_subject_mentions_account(self):
        mock = await self._call()
        subj = _kwargs(mock)["subject"].lower()
        assert "account" in subj or "approved" in subj or "ready" in subj

    async def test_body_contains_login_url(self):
        mock = await self._call()
        combined = _kwargs(mock)["txt"] + " " + _kwargs(mock)["html"]
        assert "login" in combined.lower() or "sign" in combined.lower()


# ---------------------------------------------------------------------------
# send_account_denied_email
# ---------------------------------------------------------------------------


class TestSendAccountDeniedEmail:
    async def _call(self, to="user@test.com", display_name="Eve"):
        mock_delay = MagicMock()
        with patch("app.tasks.email_task.send_email.delay", mock_delay):
            await send_account_denied_email(to, display_name)
        return mock_delay

    async def test_delay_called_once(self):
        mock = await self._call()
        mock.assert_called_once()

    async def test_recipient_is_user(self):
        mock = await self._call(to="eve@test.com")
        assert "eve@test.com" in _kwargs(mock)["to"]

    async def test_body_contains_display_name(self):
        mock = await self._call(display_name="Eve Woven")
        combined = _kwargs(mock)["txt"] + " " + _kwargs(mock)["html"]
        assert "Eve Woven" in combined


# ---------------------------------------------------------------------------
# send_approval_confirmation_to_admins
# ---------------------------------------------------------------------------


class TestSendApprovalConfirmationToAdmins:
    async def _call(self, admin_emails=None, display_name="Frank", email="frank@test.com", approved_by="Admin A"):
        if admin_emails is None:
            admin_emails = ["admin@example.com"]
        mock_delay = MagicMock()
        with patch("app.tasks.email_task.send_email.delay", mock_delay):
            await send_approval_confirmation_to_admins(admin_emails, display_name, email, approved_by)
        return mock_delay

    async def test_delay_called_once(self):
        mock = await self._call()
        mock.assert_called_once()

    async def test_recipients_include_all_admins(self):
        mock = await self._call(admin_emails=["x@test.com", "y@test.com"])
        to = _kwargs(mock)["to"]
        assert "x@test.com" in to
        assert "y@test.com" in to

    async def test_subject_contains_user_name(self):
        mock = await self._call(display_name="Frank Loom")
        assert "Frank Loom" in _kwargs(mock)["subject"]

    async def test_body_contains_approved_by(self):
        mock = await self._call(approved_by="Super Admin")
        combined = _kwargs(mock)["txt"] + " " + _kwargs(mock)["html"]
        assert "Super Admin" in combined


# ---------------------------------------------------------------------------
# send_stack_startup_alert
# ---------------------------------------------------------------------------

_STARTUP_PROBE_ROWS = [
    ("PostgreSQL", True, ""),
    ("S3", True, ""),
    ("Clerk", True, ""),
    ("SMTP", False, "connection refused"),
]


class TestSendStackStartupAlert:
    async def _call(
        self,
        emails=None,
        env="dev",
        app_base_url="http://localhost:3000",
        version="1.2.3",
        worker_version="1.2.3",
        probe_status="ok",
        probe_rows=None,
        timestamp="2026-01-01T00:00:00Z",
    ):
        if emails is None:
            emails = ["su@test.com"]
        if probe_rows is None:
            probe_rows = [("PostgreSQL", True, ""), ("Redis", True, "")]
        mock_delay = MagicMock()
        with patch("app.tasks.email_task.send_email.delay", mock_delay):
            await send_stack_startup_alert(
                superuser_emails=emails,
                env=env,
                app_base_url=app_base_url,
                version=version,
                worker_version=worker_version,
                probe_status=probe_status,
                probe_rows=probe_rows,
                timestamp=timestamp,
            )
        return mock_delay

    async def test_delay_called_once(self):
        mock = await self._call()
        mock.assert_called_once()

    async def test_recipients_include_all_superusers(self):
        mock = await self._call(emails=["a@test.com", "b@test.com"])
        to = _kwargs(mock)["to"]
        assert "a@test.com" in to
        assert "b@test.com" in to

    async def test_subject_contains_env(self):
        mock = await self._call(env="prod")
        assert "prod" in _kwargs(mock)["subject"].lower()

    async def test_subject_contains_started_on_success(self):
        mock = await self._call(probe_status="ok")
        assert "start" in _kwargs(mock)["subject"].lower()

    async def test_subject_contains_warnings_on_probe_failure(self):
        mock = await self._call(probe_status="degraded")
        subj = _kwargs(mock)["subject"].lower()
        assert "warn" in subj or "degrad" in subj or "fail" in subj

    async def test_subject_contains_timestamp(self):
        mock = await self._call(timestamp="2026-05-07T12:00:00Z")
        subj = _kwargs(mock)["subject"]
        assert "2026-05-07" in subj or "12:00" in subj

    async def test_body_contains_version(self):
        mock = await self._call(version="9.8.7")
        combined = _kwargs(mock)["txt"] + " " + _kwargs(mock)["html"]
        assert "9.8.7" in combined

    async def test_body_contains_worker_version(self):
        mock = await self._call(worker_version="9.8.7-w")
        combined = _kwargs(mock)["txt"] + " " + _kwargs(mock)["html"]
        assert "9.8.7-w" in combined

    async def test_body_contains_admin_url(self):
        mock = await self._call(app_base_url="http://weftmark.example.com")
        combined = _kwargs(mock)["txt"] + " " + _kwargs(mock)["html"]
        assert "weftmark.example.com" in combined

    async def test_body_contains_probe_service_name(self):
        mock = await self._call(probe_rows=[("PostgreSQL", True, ""), ("SMTP", False, "timeout")])
        combined = _kwargs(mock)["txt"] + " " + _kwargs(mock)["html"]
        assert "PostgreSQL" in combined

    async def test_body_contains_probe_failure_detail(self):
        mock = await self._call(probe_rows=[("SMTP", False, "connection refused")])
        combined = _kwargs(mock)["txt"] + " " + _kwargs(mock)["html"]
        assert "connection refused" in combined

    async def test_no_delay_when_smtp_unconfigured(self, monkeypatch):
        from app.config import get_settings

        monkeypatch.setattr(get_settings(), "smtp_user", "")
        mock_delay = MagicMock()
        with patch("app.tasks.email_task.send_email.delay", mock_delay):
            await send_stack_startup_alert(
                superuser_emails=["su@test.com"],
                env="dev",
                app_base_url="http://localhost:3000",
                version="1.0.0",
                worker_version=None,
                probe_status="ok",
                probe_rows=[],
                timestamp="2026-01-01T00:00:00Z",
            )
        mock_delay.assert_not_called()

    async def test_no_delay_when_no_recipients(self):
        mock_delay = MagicMock()
        with patch("app.tasks.email_task.send_email.delay", mock_delay):
            await send_stack_startup_alert(
                superuser_emails=[],
                env="dev",
                app_base_url="http://localhost:3000",
                version="1.0.0",
                worker_version=None,
                probe_status="ok",
                probe_rows=[],
                timestamp="2026-01-01T00:00:00Z",
            )
        mock_delay.assert_not_called()

    async def test_worker_version_none_renders_cleanly(self):
        mock = await self._call(worker_version=None)
        combined = _kwargs(mock)["txt"] + " " + _kwargs(mock)["html"]
        assert "{" not in combined


# ---------------------------------------------------------------------------
# send_stack_shutdown_alert
# ---------------------------------------------------------------------------


class TestSendStackShutdownAlert:
    async def _call(
        self,
        emails=None,
        env="dev",
        app_base_url="http://localhost:3000",
        version="1.0.0",
        uptime_seconds=3661.0,
        timestamp="2026-01-01T01:01:01Z",
    ):
        if emails is None:
            emails = ["su@test.com"]
        mock_delay = MagicMock()
        with patch("app.tasks.email_task.send_email.delay", mock_delay):
            await send_stack_shutdown_alert(
                superuser_emails=emails,
                env=env,
                app_base_url=app_base_url,
                version=version,
                uptime_seconds=uptime_seconds,
                timestamp=timestamp,
            )
        return mock_delay

    async def test_delay_called_once(self):
        mock = await self._call()
        mock.assert_called_once()

    async def test_recipients_include_all_superusers(self):
        mock = await self._call(emails=["x@test.com", "y@test.com"])
        to = _kwargs(mock)["to"]
        assert "x@test.com" in to
        assert "y@test.com" in to

    async def test_subject_contains_env(self):
        mock = await self._call(env="prod")
        assert "prod" in _kwargs(mock)["subject"].lower()

    async def test_subject_contains_stopped(self):
        mock = await self._call()
        subj = _kwargs(mock)["subject"].lower()
        assert "stop" in subj or "shut" in subj

    async def test_subject_contains_timestamp(self):
        mock = await self._call(timestamp="2026-05-07T23:59:00Z")
        subj = _kwargs(mock)["subject"]
        assert "2026-05-07" in subj or "23:59" in subj

    async def test_body_contains_version(self):
        mock = await self._call(version="5.4.3")
        combined = _kwargs(mock)["txt"] + " " + _kwargs(mock)["html"]
        assert "5.4.3" in combined

    async def test_body_contains_uptime(self):
        mock = await self._call(uptime_seconds=3661.0)
        combined = _kwargs(mock)["txt"] + " " + _kwargs(mock)["html"]
        assert "1h" in combined or "3661" in combined or "1:01" in combined

    async def test_body_contains_admin_url(self):
        mock = await self._call(app_base_url="http://weftmark.example.com")
        combined = _kwargs(mock)["txt"] + " " + _kwargs(mock)["html"]
        assert "weftmark.example.com" in combined

    async def test_no_delay_when_smtp_unconfigured(self, monkeypatch):
        from app.config import get_settings

        monkeypatch.setattr(get_settings(), "smtp_user", "")
        mock_delay = MagicMock()
        with patch("app.tasks.email_task.send_email.delay", mock_delay):
            await send_stack_shutdown_alert(
                superuser_emails=["su@test.com"],
                env="dev",
                app_base_url="http://localhost:3000",
                version="1.0.0",
                uptime_seconds=100.0,
                timestamp="2026-01-01T00:00:00Z",
            )
        mock_delay.assert_not_called()

    async def test_no_delay_when_no_recipients(self):
        mock_delay = MagicMock()
        with patch("app.tasks.email_task.send_email.delay", mock_delay):
            await send_stack_shutdown_alert(
                superuser_emails=[],
                env="dev",
                app_base_url="http://localhost:3000",
                version="1.0.0",
                uptime_seconds=100.0,
                timestamp="2026-01-01T00:00:00Z",
            )
        mock_delay.assert_not_called()

    async def test_body_has_no_unfilled_placeholders(self):
        mock = await self._call()
        combined = _kwargs(mock)["txt"] + " " + _kwargs(mock)["html"]
        assert "{" not in combined


# ---------------------------------------------------------------------------
# send_health_degraded_alert
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestSendHealthDegradedAlert:
    async def _call(
        self,
        emails=None,
        env="production",
        app_base_url="http://weftmark.example.com",
        version="1.0.0",
        probe_rows=None,
        status="degraded",
        timestamp="2026-01-01T00:00:00Z",
    ):
        if emails is None:
            emails = ["su@test.com"]
        if probe_rows is None:
            probe_rows = [("PostgreSQL", True, ""), ("SMTP", False, "connection refused")]
        mock_delay = MagicMock()
        with patch("app.tasks.email_task.send_email.delay", mock_delay):
            await send_health_degraded_alert(
                superuser_emails=emails,
                env=env,
                app_base_url=app_base_url,
                version=version,
                probe_rows=probe_rows,
                status=status,
                timestamp=timestamp,
            )
        return mock_delay

    async def test_delay_called_once(self):
        mock = await self._call()
        mock.assert_called_once()

    async def test_recipients_correct(self):
        mock = await self._call(emails=["a@test.com", "b@test.com"])
        to = _kwargs(mock)["to"]
        assert "a@test.com" in to
        assert "b@test.com" in to

    async def test_subject_contains_env(self):
        mock = await self._call(env="production")
        assert "production" in _kwargs(mock)["subject"].lower()

    async def test_subject_contains_degraded_or_health(self):
        mock = await self._call(status="degraded")
        subj = _kwargs(mock)["subject"].lower()
        assert "degraded" in subj or "health" in subj

    async def test_subject_error_status(self):
        mock = await self._call(status="error")
        subj = _kwargs(mock)["subject"].lower()
        assert "error" in subj or "health" in subj

    async def test_subject_contains_timestamp(self):
        mock = await self._call(timestamp="2026-05-08T12:00:00Z")
        subj = _kwargs(mock)["subject"]
        assert "2026-05-08" in subj or "12:00" in subj

    async def test_body_contains_failed_service(self):
        mock = await self._call(probe_rows=[("SMTP", False, "connection refused")])
        combined = _kwargs(mock)["txt"] + " " + _kwargs(mock)["html"]
        assert "SMTP" in combined

    async def test_body_contains_failure_detail(self):
        mock = await self._call(probe_rows=[("SMTP", False, "connection refused")])
        combined = _kwargs(mock)["txt"] + " " + _kwargs(mock)["html"]
        assert "connection refused" in combined

    async def test_body_contains_admin_url(self):
        mock = await self._call(app_base_url="http://weftmark.example.com")
        combined = _kwargs(mock)["txt"] + " " + _kwargs(mock)["html"]
        assert "weftmark.example.com" in combined

    async def test_body_contains_version(self):
        mock = await self._call(version="9.8.7")
        combined = _kwargs(mock)["txt"] + " " + _kwargs(mock)["html"]
        assert "9.8.7" in combined

    async def test_no_delay_when_smtp_unconfigured(self, monkeypatch):
        from app.config import get_settings

        monkeypatch.setattr(get_settings(), "smtp_user", "")
        mock_delay = MagicMock()
        with patch("app.tasks.email_task.send_email.delay", mock_delay):
            await send_health_degraded_alert(
                superuser_emails=["su@test.com"],
                env="production",
                app_base_url="http://localhost:3000",
                version="1.0.0",
                probe_rows=[],
                status="degraded",
                timestamp="2026-01-01T00:00:00Z",
            )
        mock_delay.assert_not_called()

    async def test_no_delay_when_no_recipients(self):
        mock_delay = MagicMock()
        with patch("app.tasks.email_task.send_email.delay", mock_delay):
            await send_health_degraded_alert(
                superuser_emails=[],
                env="production",
                app_base_url="http://localhost:3000",
                version="1.0.0",
                probe_rows=[],
                status="degraded",
                timestamp="2026-01-01T00:00:00Z",
            )
        mock_delay.assert_not_called()

    async def test_body_has_no_unfilled_placeholders(self):
        mock = await self._call()
        combined = _kwargs(mock)["txt"] + " " + _kwargs(mock)["html"]
        assert "{" not in combined


# ---------------------------------------------------------------------------
# send_health_recovered_alert
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestSendHealthRecoveredAlert:
    async def _call(
        self,
        emails=None,
        env="production",
        app_base_url="http://weftmark.example.com",
        version="1.0.0",
        timestamp="2026-01-01T00:00:00Z",
    ):
        if emails is None:
            emails = ["su@test.com"]
        mock_delay = MagicMock()
        with patch("app.tasks.email_task.send_email.delay", mock_delay):
            await send_health_recovered_alert(
                superuser_emails=emails,
                env=env,
                app_base_url=app_base_url,
                version=version,
                timestamp=timestamp,
            )
        return mock_delay

    async def test_delay_called_once(self):
        mock = await self._call()
        mock.assert_called_once()

    async def test_recipients_correct(self):
        mock = await self._call(emails=["a@test.com", "b@test.com"])
        to = _kwargs(mock)["to"]
        assert "a@test.com" in to
        assert "b@test.com" in to

    async def test_subject_contains_env(self):
        mock = await self._call(env="production")
        assert "production" in _kwargs(mock)["subject"].lower()

    async def test_subject_contains_recovered(self):
        mock = await self._call()
        assert "recover" in _kwargs(mock)["subject"].lower()

    async def test_body_contains_admin_url(self):
        mock = await self._call(app_base_url="http://weftmark.example.com")
        combined = _kwargs(mock)["txt"] + " " + _kwargs(mock)["html"]
        assert "weftmark.example.com" in combined

    async def test_body_contains_version(self):
        mock = await self._call(version="9.8.7")
        combined = _kwargs(mock)["txt"] + " " + _kwargs(mock)["html"]
        assert "9.8.7" in combined

    async def test_no_delay_when_smtp_unconfigured(self, monkeypatch):
        from app.config import get_settings

        monkeypatch.setattr(get_settings(), "smtp_user", "")
        mock_delay = MagicMock()
        with patch("app.tasks.email_task.send_email.delay", mock_delay):
            await send_health_recovered_alert(
                superuser_emails=["su@test.com"],
                env="production",
                app_base_url="http://localhost:3000",
                version="1.0.0",
                timestamp="2026-01-01T00:00:00Z",
            )
        mock_delay.assert_not_called()

    async def test_no_delay_when_no_recipients(self):
        mock_delay = MagicMock()
        with patch("app.tasks.email_task.send_email.delay", mock_delay):
            await send_health_recovered_alert(
                superuser_emails=[],
                env="production",
                app_base_url="http://localhost:3000",
                version="1.0.0",
                timestamp="2026-01-01T00:00:00Z",
            )
        mock_delay.assert_not_called()

    async def test_body_has_no_unfilled_placeholders(self):
        mock = await self._call()
        combined = _kwargs(mock)["txt"] + " " + _kwargs(mock)["html"]
        assert "{" not in combined


# ---------------------------------------------------------------------------
# _format_uptime
# ---------------------------------------------------------------------------


class TestFormatUptime:
    def test_seconds_only(self):
        assert _format_uptime(45) == "45s"

    def test_minutes_and_seconds(self):
        result = _format_uptime(90)
        assert "m" in result
        assert "s" in result

    def test_hours_minutes_seconds(self):
        result = _format_uptime(3661)
        assert "h" in result
        assert "m" in result

    def test_zero(self):
        assert _format_uptime(0) == "0s"

    def test_exactly_one_hour(self):
        assert _format_uptime(3600) == "1h 00m 00s"

    def test_exactly_one_minute(self):
        assert _format_uptime(60) == "1m 00s"


# ---------------------------------------------------------------------------
# _digest_cve_txt / _digest_cve_html
# ---------------------------------------------------------------------------


class TestDigestCveTxt:
    def test_none_returns_no_data(self):
        assert _digest_cve_txt(None, None) == "No scan data available"

    def test_zero_findings(self):
        result = _digest_cve_txt(0, None)
        assert "0" in result

    def test_one_finding_singular(self):
        result = _digest_cve_txt(1, None)
        assert "finding" in result
        assert "findings" not in result

    def test_multiple_findings_plural(self):
        result = _digest_cve_txt(5, None)
        assert "findings" in result

    def test_scanned_at_included(self):
        result = _digest_cve_txt(3, "2026-05-01T00:00:00")
        assert "2026-05-01" in result

    def test_scanned_at_none_not_present(self):
        result = _digest_cve_txt(2, None)
        assert "scanned" not in result


class TestDigestCveHtml:
    def test_none_returns_no_data_html(self):
        result = _digest_cve_html(None, None)
        assert "No scan data" in result

    def test_zero_findings_green(self):
        result = _digest_cve_html(0, None)
        assert "#16a34a" in result

    def test_nonzero_findings_red(self):
        result = _digest_cve_html(3, None)
        assert "#dc2626" in result

    def test_scanned_at_included(self):
        result = _digest_cve_html(1, "2026-05-01T00:00:00")
        assert "2026-05-01" in result


# ---------------------------------------------------------------------------
# _digest_s3_txt / _digest_s3_html
# ---------------------------------------------------------------------------


class TestDigestS3Txt:
    def test_none_returns_no_data(self):
        assert _digest_s3_txt(None, None) == "No scan data available"

    def test_zero_orphaned(self):
        result = _digest_s3_txt(0, None)
        assert "0" in result

    def test_one_orphaned_singular(self):
        result = _digest_s3_txt(1, None)
        assert "orphaned file" in result
        assert "files" not in result

    def test_multiple_orphaned_plural(self):
        result = _digest_s3_txt(4, None)
        assert "files" in result

    def test_scanned_at_included(self):
        result = _digest_s3_txt(2, "2026-04-01T00:00:00")
        assert "2026-04-01" in result


class TestDigestS3Html:
    def test_none_returns_no_data_html(self):
        result = _digest_s3_html(None, None)
        assert "No scan data" in result

    def test_zero_orphaned_green(self):
        result = _digest_s3_html(0, None)
        assert "#16a34a" in result

    def test_nonzero_orphaned_red(self):
        result = _digest_s3_html(5, None)
        assert "#dc2626" in result


# ---------------------------------------------------------------------------
# send_deletion_created_admin
# ---------------------------------------------------------------------------


class TestSendDeletionCreatedAdmin:
    async def _call(self, admin_emails=None, display_name="Alice", email="alice@test.com"):
        if admin_emails is None:
            admin_emails = ["admin@example.com"]
        mock_delay = MagicMock()
        with patch("app.tasks.email_task.send_email.delay", mock_delay):
            await send_deletion_created_admin(admin_emails, display_name, email)
        return mock_delay

    async def test_delay_called_once(self):
        mock = await self._call()
        mock.assert_called_once()

    async def test_subject_contains_display_name(self):
        mock = await self._call(display_name="Alice Loom")
        assert "Alice Loom" in _kwargs(mock)["subject"]

    async def test_body_contains_email(self):
        mock = await self._call(email="delete@test.com")
        combined = _kwargs(mock)["txt"] + " " + _kwargs(mock)["html"]
        assert "delete@test.com" in combined

    async def test_body_has_no_unfilled_placeholders(self):
        mock = await self._call()
        combined = _kwargs(mock)["txt"] + " " + _kwargs(mock)["html"]
        assert "{" not in combined


# ---------------------------------------------------------------------------
# send_deletion_completed_admin
# ---------------------------------------------------------------------------


class TestSendDeletionCompletedAdmin:
    async def _call(self, admin_emails=None, display_name="Bob", email="bob@test.com"):
        if admin_emails is None:
            admin_emails = ["admin@example.com"]
        mock_delay = MagicMock()
        with patch("app.tasks.email_task.send_email.delay", mock_delay):
            await send_deletion_completed_admin(admin_emails, display_name, email)
        return mock_delay

    async def test_delay_called_once(self):
        mock = await self._call()
        mock.assert_called_once()

    async def test_subject_contains_display_name(self):
        mock = await self._call(display_name="Bob Weave")
        assert "Bob Weave" in _kwargs(mock)["subject"]

    async def test_body_has_no_unfilled_placeholders(self):
        mock = await self._call()
        combined = _kwargs(mock)["txt"] + " " + _kwargs(mock)["html"]
        assert "{" not in combined


# ---------------------------------------------------------------------------
# send_deletion_stalled_superuser
# ---------------------------------------------------------------------------


class TestSendDeletionStalledSuperuser:
    async def _call(
        self,
        superuser_emails=None,
        display_name="Carol",
        email="carol@test.com",
        user_id="usr_abc123",
    ):
        if superuser_emails is None:
            superuser_emails = ["su@example.com"]
        mock_delay = MagicMock()
        with patch("app.tasks.email_task.send_email.delay", mock_delay):
            await send_deletion_stalled_superuser(superuser_emails, display_name, email, user_id)
        return mock_delay

    async def test_delay_called_once(self):
        mock = await self._call()
        mock.assert_called_once()

    async def test_subject_contains_display_name(self):
        mock = await self._call(display_name="Carol Yarn")
        assert "Carol Yarn" in _kwargs(mock)["subject"]

    async def test_body_contains_user_id(self):
        mock = await self._call(user_id="usr_xyz789")
        combined = _kwargs(mock)["txt"] + " " + _kwargs(mock)["html"]
        assert "usr_xyz789" in combined

    async def test_body_has_no_unfilled_placeholders(self):
        mock = await self._call()
        combined = _kwargs(mock)["txt"] + " " + _kwargs(mock)["html"]
        assert "{" not in combined


# ---------------------------------------------------------------------------
# send_credential_expiring_superuser
# ---------------------------------------------------------------------------


class TestSendCredentialExpiringSuperuser:
    async def _call(
        self,
        emails=None,
        credential_name="SMTP Password",
        resource="SMTP2Go",
        days_remaining=5,
        expires_on="2026-06-01",
    ):
        if emails is None:
            emails = ["su@example.com"]
        mock_delay = MagicMock()
        with patch("app.tasks.email_task.send_email.delay", mock_delay):
            await send_credential_expiring_superuser(emails, credential_name, resource, days_remaining, expires_on)
        return mock_delay

    async def test_delay_called_once(self):
        mock = await self._call()
        mock.assert_called_once()

    async def test_no_delay_when_smtp_unconfigured(self, monkeypatch):
        from app.config import get_settings

        monkeypatch.setattr(get_settings(), "smtp_user", "")
        mock_delay = MagicMock()
        with patch("app.tasks.email_task.send_email.delay", mock_delay):
            await send_credential_expiring_superuser(["su@example.com"], "k", "r", 5, "2026-06-01")
        mock_delay.assert_not_called()

    async def test_no_delay_when_no_recipients(self):
        mock_delay = MagicMock()
        with patch("app.tasks.email_task.send_email.delay", mock_delay):
            await send_credential_expiring_superuser([], "k", "r", 5, "2026-06-01")
        mock_delay.assert_not_called()

    async def test_subject_contains_credential_name(self):
        mock = await self._call(credential_name="API Key")
        assert "API Key" in _kwargs(mock)["subject"]

    async def test_subject_singular_day(self):
        mock = await self._call(days_remaining=1)
        assert "day" in _kwargs(mock)["subject"]
        assert "days" not in _kwargs(mock)["subject"]

    async def test_subject_plural_days(self):
        mock = await self._call(days_remaining=7)
        assert "days" in _kwargs(mock)["subject"]

    async def test_body_has_no_unfilled_placeholders(self):
        mock = await self._call()
        combined = _kwargs(mock)["txt"] + " " + _kwargs(mock)["html"]
        assert "{" not in combined


# ---------------------------------------------------------------------------
# send_credential_expiring_admin
# ---------------------------------------------------------------------------


class TestSendCredentialExpiringAdmin:
    async def _call(
        self,
        emails=None,
        credential_name="R2 Token",
        resource="Cloudflare R2",
        days_remaining=14,
        expires_on="2026-07-01",
    ):
        if emails is None:
            emails = ["admin@example.com"]
        mock_delay = MagicMock()
        with patch("app.tasks.email_task.send_email.delay", mock_delay):
            await send_credential_expiring_admin(emails, credential_name, resource, days_remaining, expires_on)
        return mock_delay

    async def test_delay_called_once(self):
        mock = await self._call()
        mock.assert_called_once()

    async def test_no_delay_when_smtp_unconfigured(self, monkeypatch):
        from app.config import get_settings

        monkeypatch.setattr(get_settings(), "smtp_user", "")
        mock_delay = MagicMock()
        with patch("app.tasks.email_task.send_email.delay", mock_delay):
            await send_credential_expiring_admin(["a@example.com"], "k", "r", 14, "2026-07-01")
        mock_delay.assert_not_called()

    async def test_no_delay_when_no_recipients(self):
        mock_delay = MagicMock()
        with patch("app.tasks.email_task.send_email.delay", mock_delay):
            await send_credential_expiring_admin([], "k", "r", 14, "2026-07-01")
        mock_delay.assert_not_called()

    async def test_body_contains_credential_name(self):
        mock = await self._call(credential_name="R2 Token")
        combined = _kwargs(mock)["txt"] + " " + _kwargs(mock)["html"]
        assert "R2 Token" in combined

    async def test_body_has_no_unfilled_placeholders(self):
        mock = await self._call()
        combined = _kwargs(mock)["txt"] + " " + _kwargs(mock)["html"]
        assert "{" not in combined


# ---------------------------------------------------------------------------
# send_feedback_user_confirmation
# ---------------------------------------------------------------------------


class TestSendFeedbackUserConfirmation:
    async def _call(self, to="user@test.com", type_label="bug report", discussion_url="https://github.com/d/1"):
        mock_delay = MagicMock()
        with patch("app.tasks.email_task.send_email.delay", mock_delay):
            await send_feedback_user_confirmation(to, type_label, discussion_url)
        return mock_delay

    async def test_delay_called_once(self):
        mock = await self._call()
        mock.assert_called_once()

    async def test_recipient_is_user(self):
        mock = await self._call(to="specific@test.com")
        assert "specific@test.com" in _kwargs(mock)["to"]

    async def test_subject_contains_type_label(self):
        mock = await self._call(type_label="feature request")
        assert "feature request" in _kwargs(mock)["subject"]

    async def test_body_contains_discussion_url(self):
        mock = await self._call(discussion_url="https://github.com/discussions/42")
        combined = _kwargs(mock)["txt"] + " " + _kwargs(mock)["html"]
        assert "https://github.com/discussions/42" in combined

    async def test_body_has_no_unfilled_placeholders(self):
        mock = await self._call()
        combined = _kwargs(mock)["txt"] + " " + _kwargs(mock)["html"]
        assert "{" not in combined


# ---------------------------------------------------------------------------
# send_feedback_admin_alert
# ---------------------------------------------------------------------------


class TestSendFeedbackAdminAlert:
    async def _call(
        self,
        admin_emails=None,
        type_label="bug report",
        discussion_url="https://github.com/d/1",
        subject=None,
    ):
        if admin_emails is None:
            admin_emails = ["admin@example.com"]
        mock_delay = MagicMock()
        with patch("app.tasks.email_task.send_email.delay", mock_delay):
            await send_feedback_admin_alert(admin_emails, type_label, discussion_url, subject)
        return mock_delay

    async def test_delay_called_once(self):
        mock = await self._call()
        mock.assert_called_once()

    async def test_no_delay_when_smtp_unconfigured(self, monkeypatch):
        from app.config import get_settings

        monkeypatch.setattr(get_settings(), "smtp_user", "")
        mock_delay = MagicMock()
        with patch("app.tasks.email_task.send_email.delay", mock_delay):
            await send_feedback_admin_alert(["a@example.com"], "bug", "https://g.com/1", None)
        mock_delay.assert_not_called()

    async def test_no_delay_when_no_recipients(self):
        mock_delay = MagicMock()
        with patch("app.tasks.email_task.send_email.delay", mock_delay):
            await send_feedback_admin_alert([], "bug", "https://g.com/1", None)
        mock_delay.assert_not_called()

    async def test_subject_email_contains_type_label(self):
        mock = await self._call(type_label="feature request")
        assert "feature request" in _kwargs(mock)["subject"]

    async def test_body_with_subject_contains_it(self):
        mock = await self._call(subject="Dark mode please")
        combined = _kwargs(mock)["txt"] + " " + _kwargs(mock)["html"]
        assert "Dark mode please" in combined

    async def test_body_without_subject_has_no_unfilled_placeholders(self):
        mock = await self._call(subject=None)
        combined = _kwargs(mock)["txt"] + " " + _kwargs(mock)["html"]
        assert "{" not in combined


# ---------------------------------------------------------------------------
# send_admin_digest_email
# ---------------------------------------------------------------------------


class TestSendAdminDigestEmail:
    async def _call(
        self,
        admin_emails=None,
        week_start="2026-05-11",
        week_end="2026-05-17",
        new_users=3,
        pending_signups=1,
        new_drafts=10,
        new_projects=5,
        new_looms=2,
        storage_str="1.2 GB",
        storage_delta_str="+50 MB",
        cve_finding_count=0,
        cve_scanned_at="2026-05-17T02:00:00",
        s3_orphaned_count=0,
        s3_scanned_at="2026-05-17T03:00:00",
    ):
        if admin_emails is None:
            admin_emails = ["admin@example.com"]
        mock_delay = MagicMock()
        with patch("app.tasks.email_task.send_email.delay", mock_delay):
            await send_admin_digest_email(
                admin_emails=admin_emails,
                week_start=week_start,
                week_end=week_end,
                new_users=new_users,
                pending_signups=pending_signups,
                new_drafts=new_drafts,
                new_projects=new_projects,
                new_looms=new_looms,
                storage_str=storage_str,
                storage_delta_str=storage_delta_str,
                cve_finding_count=cve_finding_count,
                cve_scanned_at=cve_scanned_at,
                s3_orphaned_count=s3_orphaned_count,
                s3_scanned_at=s3_scanned_at,
            )
        return mock_delay

    async def test_delay_called_once(self):
        mock = await self._call()
        mock.assert_called_once()

    async def test_no_delay_when_smtp_unconfigured(self, monkeypatch):
        from app.config import get_settings

        monkeypatch.setattr(get_settings(), "smtp_user", "")
        mock_delay = MagicMock()
        with patch("app.tasks.email_task.send_email.delay", mock_delay):
            await send_admin_digest_email(
                admin_emails=["a@example.com"],
                week_start="2026-05-11",
                week_end="2026-05-17",
                new_users=0,
                pending_signups=0,
                new_drafts=0,
                new_projects=0,
                new_looms=0,
                storage_str="0 B",
                storage_delta_str=None,
                cve_finding_count=None,
                cve_scanned_at=None,
                s3_orphaned_count=None,
                s3_scanned_at=None,
            )
        mock_delay.assert_not_called()

    async def test_no_delay_when_no_recipients(self):
        mock_delay = MagicMock()
        with patch("app.tasks.email_task.send_email.delay", mock_delay):
            await send_admin_digest_email(
                admin_emails=[],
                week_start="2026-05-11",
                week_end="2026-05-17",
                new_users=0,
                pending_signups=0,
                new_drafts=0,
                new_projects=0,
                new_looms=0,
                storage_str="0 B",
                storage_delta_str=None,
                cve_finding_count=None,
                cve_scanned_at=None,
                s3_orphaned_count=None,
                s3_scanned_at=None,
            )
        mock_delay.assert_not_called()

    async def test_subject_contains_week_range(self):
        mock = await self._call(week_start="2026-05-11", week_end="2026-05-17")
        subj = _kwargs(mock)["subject"]
        assert "2026-05-11" in subj
        assert "2026-05-17" in subj

    async def test_body_contains_storage_str(self):
        mock = await self._call(storage_str="2.4 GB")
        combined = _kwargs(mock)["txt"] + " " + _kwargs(mock)["html"]
        assert "2.4 GB" in combined

    async def test_body_contains_storage_delta(self):
        mock = await self._call(storage_delta_str="+100 MB")
        combined = _kwargs(mock)["txt"] + " " + _kwargs(mock)["html"]
        assert "+100 MB" in combined

    async def test_body_no_delta_shows_first_run_indicator(self):
        mock = await self._call(storage_delta_str=None)
        combined = _kwargs(mock)["txt"] + " " + _kwargs(mock)["html"]
        assert "—" in combined or "First run" in combined or "no prior" in combined.lower()

    async def test_body_cve_none_shows_no_data(self):
        mock = await self._call(cve_finding_count=None, cve_scanned_at=None)
        combined = _kwargs(mock)["txt"] + " " + _kwargs(mock)["html"]
        assert "No scan data" in combined

    async def test_body_has_no_unfilled_placeholders(self):
        mock = await self._call()
        combined = _kwargs(mock)["txt"] + " " + _kwargs(mock)["html"]
        assert "{" not in combined


# ---------------------------------------------------------------------------
# DEV environment banner (_send branch)
# ---------------------------------------------------------------------------


class TestDevEnvironmentBanner:
    async def test_dev_prefix_added_to_subject(self, monkeypatch):
        from app.config import get_settings

        monkeypatch.setattr(get_settings(), "app_env", "dev")
        mock_delay = MagicMock()
        with patch("app.tasks.email_task.send_email.delay", mock_delay):
            await send_test_email("a@test.com")
        subj = _kwargs(mock_delay)["subject"]
        assert subj.startswith("[DEV]")

    async def test_dev_banner_added_to_txt(self, monkeypatch):
        from app.config import get_settings

        monkeypatch.setattr(get_settings(), "app_env", "dev")
        mock_delay = MagicMock()
        with patch("app.tasks.email_task.send_email.delay", mock_delay):
            await send_test_email("a@test.com")
        txt = _kwargs(mock_delay)["txt"]
        assert "DEV ENVIRONMENT" in txt

    async def test_non_dev_removes_dev_banner_comment(self, monkeypatch):
        from app.config import get_settings

        monkeypatch.setattr(get_settings(), "app_env", "test")
        mock_delay = MagicMock()
        with patch("app.tasks.email_task.send_email.delay", mock_delay):
            await send_test_email("a@test.com")
        html = _kwargs(mock_delay)["html"]
        assert "<!-- DEV_BANNER -->" not in html
