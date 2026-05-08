"""Tests for app.tasks.email_task.send_email Celery task.

Tests the TTL discard logic, staleness banner injection, SMTP transport args,
and retry-on-failure behaviour.  _do_smtp is patched with AsyncMock so no real
SMTP connection is made.  send_email is called directly (bound-task style) by
constructing a mock task instance.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_task(retries: int = 0, max_retries: int = 5) -> MagicMock:
    t = MagicMock()
    t.request = MagicMock()
    t.request.retries = retries
    t.max_retries = max_retries
    return t


def _queued_at(seconds_ago: float = 0.0) -> str:
    return (datetime.now(timezone.utc) - timedelta(seconds=seconds_ago)).isoformat()


_BASE_HTML = "<p>Hello</p><!-- STALENESS_BANNER -->"


# ---------------------------------------------------------------------------
# Fixture: deterministic settings
# ---------------------------------------------------------------------------

SETTINGS_OVERRIDES = {
    "smtp_host": "smtp.example.com",
    "smtp_port": 587,
    "smtp_user": "smtpuser",
    "smtp_password": "smtppass",
    "smtp_from_email": "noreply@example.com",
    "smtp_from_name": "Test Site",
    "email_ttl_hours": 6,
    "email_staleness_warning_minutes": 60,
}


@pytest.fixture(autouse=True)
def _patch_settings(monkeypatch):
    from app.config import get_settings

    settings = get_settings()
    for attr, value in SETTINGS_OVERRIDES.items():
        monkeypatch.setattr(settings, attr, value)


# ---------------------------------------------------------------------------
# TTL discard
# ---------------------------------------------------------------------------


class TestTtlDiscard:
    def _run(self, seconds_ago: float, mock_smtp: AsyncMock | None = None):
        from app.tasks.email_task import send_email

        if mock_smtp is None:
            mock_smtp = AsyncMock()
        task = _make_task()
        with patch("app.tasks.email_task._do_smtp", mock_smtp):
            send_email.run.__func__(
                task,
                to=["x@t.com"],
                subject="hi",
                txt="plain",
                html=_BASE_HTML,
                queued_at=_queued_at(seconds_ago),
            )
        return mock_smtp

    def test_expired_email_not_sent(self):
        mock = self._run(seconds_ago=21601)  # just over 6 h
        mock.assert_not_called()

    def test_fresh_email_is_sent(self):
        mock = self._run(seconds_ago=10)
        mock.assert_called_once()

    def test_just_under_ttl_is_sent(self):
        # 5 minutes under the 6-hour TTL → should send
        mock = self._run(seconds_ago=21300)
        mock.assert_called_once()

    def test_clearly_over_ttl_not_sent(self):
        mock = self._run(seconds_ago=100_000)
        mock.assert_not_called()


# ---------------------------------------------------------------------------
# Staleness banner
# ---------------------------------------------------------------------------


class TestStalenessBanner:
    def _html_sent(self, seconds_ago: float, html: str = _BASE_HTML) -> str:
        from app.tasks.email_task import send_email

        mock_smtp = AsyncMock()
        task = _make_task()
        with patch("app.tasks.email_task._do_smtp", mock_smtp):
            send_email.run.__func__(
                task,
                to=["x@t.com"],
                subject="hi",
                txt="plain",
                html=html,
                queued_at=_queued_at(seconds_ago),
            )
        return mock_smtp.call_args.args[3]  # 4th positional arg is html

    def test_placeholder_always_removed(self):
        html = self._html_sent(seconds_ago=10)
        assert "<!-- STALENESS_BANNER -->" not in html

    def test_fresh_email_no_banner(self):
        html = self._html_sent(seconds_ago=10)
        assert "fef3c7" not in html  # amber background colour from banner

    def test_stale_email_gets_banner(self):
        html = self._html_sent(seconds_ago=3601)  # just over 60 min
        assert "fef3c7" in html

    def test_stale_banner_contains_delay(self):
        html = self._html_sent(seconds_ago=7200)  # 2 h
        assert "2h" in html

    def test_stale_banner_references_queued_at(self):
        html = self._html_sent(seconds_ago=3700)
        assert "queued" in html.lower() or "delivered" in html.lower()

    def test_stale_txt_gets_note(self):
        from app.tasks.email_task import send_email

        mock_smtp = AsyncMock()
        task = _make_task()
        with patch("app.tasks.email_task._do_smtp", mock_smtp):
            send_email.run.__func__(
                task,
                to=["x@t.com"],
                subject="hi",
                txt="original body",
                html=_BASE_HTML,
                queued_at=_queued_at(3601),
            )
        txt_sent = mock_smtp.call_args.args[2]
        assert "NOTE" in txt_sent or "queued" in txt_sent.lower()


# ---------------------------------------------------------------------------
# SMTP invocation args
# ---------------------------------------------------------------------------


class TestSmtpArgs:
    def _mock(self) -> AsyncMock:
        from app.tasks.email_task import send_email

        mock_smtp = AsyncMock()
        task = _make_task()
        with patch("app.tasks.email_task._do_smtp", mock_smtp):
            send_email.run.__func__(
                task,
                to=["r@t.com"],
                subject="subj",
                txt="plain",
                html=_BASE_HTML,
                queued_at=_queued_at(10),
            )
        return mock_smtp

    def test_called_with_to_list(self):
        mock = self._mock()
        assert "r@t.com" in mock.call_args.args[0]

    def test_called_with_subject(self):
        mock = self._mock()
        assert mock.call_args.args[1] == "subj"

    def test_called_with_txt(self):
        mock = self._mock()
        assert mock.call_args.args[2] == "plain"

    def test_called_once(self):
        mock = self._mock()
        mock.assert_called_once()


class TestSmtpTransport:
    """_do_smtp should pass correct SMTP credentials and build a MIME message."""

    def test_smtp_hostname(self):
        import asyncio

        from app.tasks.email_task import _do_smtp

        mock_send = AsyncMock()
        with patch("app.tasks.email_task.aiosmtplib.send", mock_send):
            asyncio.run(_do_smtp(["r@t.com"], "subj", "plain", "<p>html</p>"))
        _, kwargs = mock_send.call_args
        assert kwargs["hostname"] == "smtp.example.com"

    def test_smtp_port(self):
        import asyncio

        from app.tasks.email_task import _do_smtp

        mock_send = AsyncMock()
        with patch("app.tasks.email_task.aiosmtplib.send", mock_send):
            asyncio.run(_do_smtp(["r@t.com"], "subj", "plain", "<p>html</p>"))
        _, kwargs = mock_send.call_args
        assert kwargs["port"] == 587

    def test_smtp_username(self):
        import asyncio

        from app.tasks.email_task import _do_smtp

        mock_send = AsyncMock()
        with patch("app.tasks.email_task.aiosmtplib.send", mock_send):
            asyncio.run(_do_smtp(["r@t.com"], "subj", "plain", "<p>html</p>"))
        _, kwargs = mock_send.call_args
        assert kwargs["username"] == "smtpuser"

    def test_smtp_password(self):
        import asyncio

        from app.tasks.email_task import _do_smtp

        mock_send = AsyncMock()
        with patch("app.tasks.email_task.aiosmtplib.send", mock_send):
            asyncio.run(_do_smtp(["r@t.com"], "subj", "plain", "<p>html</p>"))
        _, kwargs = mock_send.call_args
        assert kwargs["password"] == "smtppass"

    def test_start_tls_enabled(self):
        import asyncio

        from app.tasks.email_task import _do_smtp

        mock_send = AsyncMock()
        with patch("app.tasks.email_task.aiosmtplib.send", mock_send):
            asyncio.run(_do_smtp(["r@t.com"], "subj", "plain", "<p>html</p>"))
        _, kwargs = mock_send.call_args
        assert kwargs["start_tls"] is True

    def test_message_subject_header(self):
        import asyncio

        from app.tasks.email_task import _do_smtp

        mock_send = AsyncMock()
        with patch("app.tasks.email_task.aiosmtplib.send", mock_send):
            asyncio.run(_do_smtp(["r@t.com"], "My Subject", "plain", "<p>html</p>"))
        msg, *_ = mock_send.call_args.args
        assert msg["Subject"] == "My Subject"

    def test_message_to_header(self):
        import asyncio

        from app.tasks.email_task import _do_smtp

        mock_send = AsyncMock()
        with patch("app.tasks.email_task.aiosmtplib.send", mock_send):
            asyncio.run(_do_smtp(["a@t.com", "b@t.com"], "s", "plain", "<p>html</p>"))
        msg, *_ = mock_send.call_args.args
        assert "a@t.com" in msg["To"]
        assert "b@t.com" in msg["To"]

    def test_message_from_header(self):
        import asyncio

        from app.tasks.email_task import _do_smtp

        mock_send = AsyncMock()
        with patch("app.tasks.email_task.aiosmtplib.send", mock_send):
            asyncio.run(_do_smtp(["r@t.com"], "s", "plain", "<p>html</p>"))
        msg, *_ = mock_send.call_args.args
        assert "Test Site" in msg["From"]
        assert "noreply@example.com" in msg["From"]

    def test_message_is_multipart(self):
        import asyncio

        from app.tasks.email_task import _do_smtp

        mock_send = AsyncMock()
        with patch("app.tasks.email_task.aiosmtplib.send", mock_send):
            asyncio.run(_do_smtp(["r@t.com"], "s", "plain", "<p>html</p>"))
        msg, *_ = mock_send.call_args.args
        assert msg.get_content_type() == "multipart/alternative"

    def test_message_has_plain_and_html_parts(self):
        import asyncio

        from app.tasks.email_task import _do_smtp

        mock_send = AsyncMock()
        with patch("app.tasks.email_task.aiosmtplib.send", mock_send):
            asyncio.run(_do_smtp(["r@t.com"], "s", "plain body", "<p>html body</p>"))
        msg, *_ = mock_send.call_args.args
        types = [p.get_content_type() for p in msg.get_payload()]
        assert "text/plain" in types
        assert "text/html" in types


# ---------------------------------------------------------------------------
# Retry on failure
# ---------------------------------------------------------------------------


class TestRetryOnFailure:
    def test_smtp_failure_triggers_retry(self):
        from app.tasks.email_task import send_email

        task = _make_task(retries=0)
        task.retry = MagicMock(side_effect=Exception("retry sentinel"))

        async def _fail(to, subject, txt, html):
            raise ConnectionError("SMTP timeout")

        with patch("app.tasks.email_task._do_smtp", _fail):
            with pytest.raises(Exception, match="retry sentinel"):
                send_email.run.__func__(
                    task,
                    to=["r@t.com"],
                    subject="s",
                    txt="t",
                    html=_BASE_HTML,
                    queued_at=_queued_at(10),
                )
        task.retry.assert_called_once()

    def test_retry_countdown_increases_with_attempts(self):
        from app.tasks.email_task import send_email

        task = _make_task(retries=2)
        countdowns: list = []

        def _capture_retry(**kwargs):
            countdowns.append(kwargs.get("countdown"))
            raise Exception("retry sentinel")

        task.retry = MagicMock(side_effect=_capture_retry)

        async def _fail(to, subject, txt, html):
            raise ConnectionError("timeout")

        with patch("app.tasks.email_task._do_smtp", _fail):
            with pytest.raises(Exception):
                send_email.run.__func__(
                    task,
                    to=["r@t.com"],
                    subject="s",
                    txt="t",
                    html=_BASE_HTML,
                    queued_at=_queued_at(10),
                )
        # retries=2 → countdown = min(60 * 2**2, 1800) = min(240, 1800) = 240
        assert countdowns[0] == 240

    def test_retry_countdown_caps_at_1800(self):
        from app.tasks.email_task import send_email

        task = _make_task(retries=10)  # 60 * 2**10 = 61440 > 1800
        countdowns: list = []

        def _capture_retry(**kwargs):
            countdowns.append(kwargs.get("countdown"))
            raise Exception("retry sentinel")

        task.retry = MagicMock(side_effect=_capture_retry)

        async def _fail(to, subject, txt, html):
            raise ConnectionError("timeout")

        with patch("app.tasks.email_task._do_smtp", _fail):
            with pytest.raises(Exception):
                send_email.run.__func__(
                    task,
                    to=["r@t.com"],
                    subject="s",
                    txt="t",
                    html=_BASE_HTML,
                    queued_at=_queued_at(10),
                )
        assert countdowns[0] == 1800
