"""Tests for app.tasks.feedback_dispatch._dispatch and _send_emails."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.tasks.feedback_dispatch import _dispatch, _send_emails

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _celery_session_ctx(db_session):
    """Return a CeleryAsyncSession-compatible factory that yields db_session."""

    class _Ctx:
        async def __aenter__(self):
            return db_session

        async def __aexit__(self, *args):
            pass

    class _Factory:
        def __call__(self):
            return _Ctx()

    return _Factory()


def _task_mock(retries: int = 0):
    t = MagicMock()
    t.request = MagicMock()
    t.request.retries = retries
    t.max_retries = 3
    return t


def _settings_mock(github_token="fake-github-token"):  # noqa: S6418
    m = MagicMock()
    m.github_feedback_token = github_token
    m.github_feedback_repo = "owner/repo"
    return m


# ---------------------------------------------------------------------------
# TestDispatchNoToken — skips when no token configured
# ---------------------------------------------------------------------------


class TestDispatchNoToken:
    async def test_no_token_returns_skipped(self, db_session):
        from app.models.feedback import UserFeedback

        row = UserFeedback(id=uuid.uuid4(), submission_type="feedback", body="Hello!")
        db_session.add(row)
        await db_session.commit()

        with (
            patch("app.database.CeleryAsyncSession", _celery_session_ctx(db_session)),
            patch("app.config.get_settings", return_value=_settings_mock(github_token=None)),
        ):
            result = await _dispatch(_task_mock(), str(row.id))

        assert result["status"] == "skipped"

    async def test_no_token_sets_skipped_status_in_db(self, db_session):
        from app.models.feedback import UserFeedback

        row = UserFeedback(id=uuid.uuid4(), submission_type="feedback", body="Hello!")
        db_session.add(row)
        await db_session.commit()

        with (
            patch("app.database.CeleryAsyncSession", _celery_session_ctx(db_session)),
            patch("app.config.get_settings", return_value=_settings_mock(github_token=None)),
        ):
            await _dispatch(_task_mock(), str(row.id))

        await db_session.refresh(row)
        assert row.dispatch_status == "skipped"

    async def test_no_token_row_not_in_db_still_returns_skipped(self, db_session):
        with (
            patch("app.database.CeleryAsyncSession", _celery_session_ctx(db_session)),
            patch("app.config.get_settings", return_value=_settings_mock(github_token=None)),
        ):
            result = await _dispatch(_task_mock(), str(uuid.uuid4()))

        assert result["status"] == "skipped"


# ---------------------------------------------------------------------------
# TestDispatchNotFound — row missing from DB
# ---------------------------------------------------------------------------


class TestDispatchNotFound:
    async def test_returns_not_found_when_row_absent(self, db_session):
        with (
            patch("app.database.CeleryAsyncSession", _celery_session_ctx(db_session)),
            patch("app.config.get_settings", return_value=_settings_mock()),
        ):
            result = await _dispatch(_task_mock(), str(uuid.uuid4()))

        assert result["status"] == "not_found"


# ---------------------------------------------------------------------------
# TestDispatchSuccess — happy path
# ---------------------------------------------------------------------------


class TestDispatchSuccess:
    async def _feedback_row(self, db_session):
        from app.models.feedback import UserFeedback

        row = UserFeedback(id=uuid.uuid4(), submission_type="feedback", body="Test body")
        db_session.add(row)
        await db_session.commit()
        return row

    async def test_sets_dispatch_status_sent(self, db_session):
        row = await self._feedback_row(db_session)
        expected_url = "https://github.com/owner/repo/discussions/1"

        with (
            patch("app.database.CeleryAsyncSession", _celery_session_ctx(db_session)),
            patch("app.config.get_settings", return_value=_settings_mock()),
            patch("app.services.github_discussions.create_discussion", new=AsyncMock(return_value=expected_url)),
            patch("app.tasks.feedback_dispatch._send_emails", new=AsyncMock()),
        ):
            result = await _dispatch(_task_mock(), str(row.id))

        assert result["status"] == "sent"
        await db_session.refresh(row)
        assert row.dispatch_status == "sent"

    async def test_returns_discussion_url(self, db_session):
        row = await self._feedback_row(db_session)
        expected_url = "https://github.com/owner/repo/discussions/99"

        with (
            patch("app.database.CeleryAsyncSession", _celery_session_ctx(db_session)),
            patch("app.config.get_settings", return_value=_settings_mock()),
            patch("app.services.github_discussions.create_discussion", new=AsyncMock(return_value=expected_url)),
            patch("app.tasks.feedback_dispatch._send_emails", new=AsyncMock()),
        ):
            result = await _dispatch(_task_mock(), str(row.id))

        assert result["url"] == expected_url

    async def test_stores_discussion_url_in_db(self, db_session):
        row = await self._feedback_row(db_session)
        expected_url = "https://github.com/discussions/42"

        with (
            patch("app.database.CeleryAsyncSession", _celery_session_ctx(db_session)),
            patch("app.config.get_settings", return_value=_settings_mock()),
            patch("app.services.github_discussions.create_discussion", new=AsyncMock(return_value=expected_url)),
            patch("app.tasks.feedback_dispatch._send_emails", new=AsyncMock()),
        ):
            await _dispatch(_task_mock(), str(row.id))

        await db_session.refresh(row)
        assert row.github_discussion_url == expected_url


# ---------------------------------------------------------------------------
# TestDispatchFailure — exception in create_discussion
# ---------------------------------------------------------------------------


class TestDispatchFailure:
    async def _feedback_row(self, db_session):
        from app.models.feedback import UserFeedback

        row = UserFeedback(id=uuid.uuid4(), submission_type="feedback", body="Test")
        db_session.add(row)
        await db_session.commit()
        return row

    async def test_sets_dispatch_status_failed_on_exception(self, db_session):
        row = await self._feedback_row(db_session)

        task = _task_mock()
        task.retry = MagicMock(return_value=RuntimeError("retry scheduled"))

        with (
            patch("app.database.CeleryAsyncSession", _celery_session_ctx(db_session)),
            patch("app.config.get_settings", return_value=_settings_mock()),
            patch(
                "app.services.github_discussions.create_discussion",
                new=AsyncMock(side_effect=RuntimeError("API error")),
            ),
        ):
            with pytest.raises(RuntimeError):
                await _dispatch(task, str(row.id))

        await db_session.refresh(row)
        assert row.dispatch_status == "failed"

    async def test_stores_error_message_on_failure(self, db_session):
        row = await self._feedback_row(db_session)

        task = _task_mock()
        task.retry = MagicMock(return_value=RuntimeError("retry"))

        with (
            patch("app.database.CeleryAsyncSession", _celery_session_ctx(db_session)),
            patch("app.config.get_settings", return_value=_settings_mock()),
            patch(
                "app.services.github_discussions.create_discussion",
                new=AsyncMock(side_effect=RuntimeError("API error")),
            ),
        ):
            with pytest.raises(RuntimeError):
                await _dispatch(task, str(row.id))

        await db_session.refresh(row)
        assert row.dispatch_error is not None

    async def test_calls_task_retry_on_exception(self, db_session):
        row = await self._feedback_row(db_session)

        task = _task_mock(retries=0)
        task.retry = MagicMock(return_value=RuntimeError("retry"))

        with (
            patch("app.database.CeleryAsyncSession", _celery_session_ctx(db_session)),
            patch("app.config.get_settings", return_value=_settings_mock()),
            patch(
                "app.services.github_discussions.create_discussion",
                new=AsyncMock(side_effect=RuntimeError("API error")),
            ),
        ):
            with pytest.raises(RuntimeError):
                await _dispatch(task, str(row.id))

        task.retry.assert_called_once()


# ---------------------------------------------------------------------------
# TestSendEmails — _send_emails helper
# ---------------------------------------------------------------------------


class TestSendEmails:
    async def _feedback_row(self, db_session, *, user_id=None, is_anonymous=False):
        from app.models.feedback import UserFeedback

        row = UserFeedback(
            id=uuid.uuid4(),
            submission_type="feedback",
            body="Hello",
            is_anonymous=is_anonymous,
            user_id=user_id,
        )
        db_session.add(row)
        await db_session.commit()
        return row

    async def test_calls_admin_alert_when_admins_exist(self, db_session, admin_user):
        row = await self._feedback_row(db_session)

        with (
            patch("app.database.CeleryAsyncSession", _celery_session_ctx(db_session)),
            patch("app.services.email.send_feedback_admin_alert", new=AsyncMock()) as mock_alert,
            patch("app.services.email.send_feedback_user_confirmation", new=AsyncMock()),
        ):
            await _send_emails(str(row.id), "https://github.com/d/1", _settings_mock())

        mock_alert.assert_called_once()

    async def test_no_admin_alert_when_no_admins(self, db_session, test_user):
        row = await self._feedback_row(db_session)

        with (
            patch("app.database.CeleryAsyncSession", _celery_session_ctx(db_session)),
            patch("app.services.email.send_feedback_admin_alert", new=AsyncMock()) as mock_alert,
            patch("app.services.email.send_feedback_user_confirmation", new=AsyncMock()),
        ):
            await _send_emails(str(row.id), "https://github.com/d/1", _settings_mock())

        mock_alert.assert_not_called()

    async def test_sends_user_confirmation_for_non_anonymous_user(self, db_session, test_user):
        row = await self._feedback_row(db_session, user_id=test_user.id, is_anonymous=False)

        with (
            patch("app.database.CeleryAsyncSession", _celery_session_ctx(db_session)),
            patch("app.services.email.send_feedback_admin_alert", new=AsyncMock()),
            patch("app.services.email.send_feedback_user_confirmation", new=AsyncMock()) as mock_confirm,
        ):
            await _send_emails(str(row.id), "https://github.com/d/1", _settings_mock())

        mock_confirm.assert_called_once()

    async def test_skips_user_confirmation_for_anonymous(self, db_session, test_user):
        row = await self._feedback_row(db_session, user_id=test_user.id, is_anonymous=True)

        with (
            patch("app.database.CeleryAsyncSession", _celery_session_ctx(db_session)),
            patch("app.services.email.send_feedback_admin_alert", new=AsyncMock()),
            patch("app.services.email.send_feedback_user_confirmation", new=AsyncMock()) as mock_confirm,
        ):
            await _send_emails(str(row.id), "https://github.com/d/1", _settings_mock())

        mock_confirm.assert_not_called()

    async def test_skips_confirmation_when_no_user_id(self, db_session):
        row = await self._feedback_row(db_session, user_id=None, is_anonymous=False)

        with (
            patch("app.database.CeleryAsyncSession", _celery_session_ctx(db_session)),
            patch("app.services.email.send_feedback_admin_alert", new=AsyncMock()),
            patch("app.services.email.send_feedback_user_confirmation", new=AsyncMock()) as mock_confirm,
        ):
            await _send_emails(str(row.id), "https://github.com/d/1", _settings_mock())

        mock_confirm.assert_not_called()

    async def test_returns_silently_when_row_not_found(self, db_session):
        with (
            patch("app.database.CeleryAsyncSession", _celery_session_ctx(db_session)),
            patch("app.services.email.send_feedback_admin_alert", new=AsyncMock()),
            patch("app.services.email.send_feedback_user_confirmation", new=AsyncMock()),
        ):
            await _send_emails(str(uuid.uuid4()), "https://github.com/d/1", _settings_mock())
