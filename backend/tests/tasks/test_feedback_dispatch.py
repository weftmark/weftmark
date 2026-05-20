"""Tests for app.tasks.feedback_dispatch async inner functions.

_dispatch, _retry_failed, and _purge_deleted are tested by calling them
directly (bypassing the Celery task wrapper) with CeleryAsyncSession
redirected to the test db_session.
"""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest


def _ago(**kwargs) -> datetime:
    return datetime.now(timezone.utc) - timedelta(**kwargs)


def _session_ctx(db_session):
    """Return an async context manager that yields db_session."""

    class _Ctx:
        async def __aenter__(self):
            return db_session

        async def __aexit__(self, *args):
            pass

    class _Factory:
        def __call__(self):
            return _Ctx()

    return _Factory()


# ---------------------------------------------------------------------------
# _retry_failed — no-token early exit path
# ---------------------------------------------------------------------------


class TestRetryFailedNoToken:
    @pytest.mark.asyncio
    async def test_returns_no_token_reason_when_token_missing(self, monkeypatch):
        from app.config import get_settings
        from app.tasks.feedback_dispatch import _retry_failed

        monkeypatch.setattr(get_settings(), "github_feedback_token", "")

        with patch("app.database.CeleryAsyncSession", _session_ctx(None)):
            result = await _retry_failed(limit=20)

        assert result.get("reason") == "no_token"
        assert result["dispatched"] == 0

    @pytest.mark.asyncio
    async def test_no_dispatches_when_token_missing(self, monkeypatch):
        from app.config import get_settings
        from app.tasks.feedback_dispatch import _retry_failed

        monkeypatch.setattr(get_settings(), "github_feedback_token", "")

        mock_dispatch = MagicMock()
        with patch("app.tasks.feedback_dispatch.dispatch_feedback", mock_dispatch):
            await _retry_failed(limit=20)

        mock_dispatch.delay.assert_not_called()


# ---------------------------------------------------------------------------
# _purge_deleted — deletes soft-deleted feedback past retention window
# ---------------------------------------------------------------------------


class TestPurgeDeleted:
    @pytest.mark.asyncio
    async def test_returns_deleted_key(self, db_session):
        from app.tasks.feedback_dispatch import _purge_deleted

        with patch("app.database.CeleryAsyncSession", _session_ctx(db_session)):
            result = await _purge_deleted(retention_days=7)

        assert "deleted" in result
        assert isinstance(result["deleted"], int)

    @pytest.mark.asyncio
    async def test_zero_when_nothing_deleted(self, db_session):
        from app.tasks.feedback_dispatch import _purge_deleted

        with patch("app.database.CeleryAsyncSession", _session_ctx(db_session)):
            result = await _purge_deleted(retention_days=7)

        assert result["deleted"] == 0

    @pytest.mark.asyncio
    async def test_hard_deletes_old_soft_deleted_feedback(self, db_session, test_user):
        from sqlalchemy import select

        from app.models.feedback import UserFeedback
        from app.tasks.feedback_dispatch import _purge_deleted

        old_deleted = UserFeedback(
            id=uuid.uuid4(),
            user_id=test_user.id,
            submission_type="bug",
            body="old deleted feedback",
            deleted_at=_ago(days=30),
        )
        db_session.add(old_deleted)
        await db_session.commit()

        with patch("app.database.CeleryAsyncSession", _session_ctx(db_session)):
            result = await _purge_deleted(retention_days=7)

        assert result["deleted"] >= 1

        remaining = (await db_session.scalars(select(UserFeedback))).all()
        assert all(str(f.id) != str(old_deleted.id) for f in remaining)

    @pytest.mark.asyncio
    async def test_keeps_recently_soft_deleted_feedback(self, db_session, test_user):
        from sqlalchemy import select

        from app.models.feedback import UserFeedback
        from app.tasks.feedback_dispatch import _purge_deleted

        recent_deleted = UserFeedback(
            id=uuid.uuid4(),
            user_id=test_user.id,
            submission_type="bug",
            body="recently deleted feedback",
            deleted_at=_ago(days=1),
        )
        db_session.add(recent_deleted)
        await db_session.commit()

        with patch("app.database.CeleryAsyncSession", _session_ctx(db_session)):
            result = await _purge_deleted(retention_days=7)

        assert result["deleted"] == 0

        remaining = (await db_session.scalars(select(UserFeedback))).all()
        assert any(str(f.id) == str(recent_deleted.id) for f in remaining)

    @pytest.mark.asyncio
    async def test_keeps_non_deleted_feedback(self, db_session, test_user):
        from sqlalchemy import select

        from app.models.feedback import UserFeedback
        from app.tasks.feedback_dispatch import _purge_deleted

        active = UserFeedback(
            id=uuid.uuid4(),
            user_id=test_user.id,
            submission_type="feature",
            body="active feedback",
        )
        db_session.add(active)
        await db_session.commit()

        with patch("app.database.CeleryAsyncSession", _session_ctx(db_session)):
            result = await _purge_deleted(retention_days=7)

        assert result["deleted"] == 0

        remaining = (await db_session.scalars(select(UserFeedback))).all()
        assert any(str(f.id) == str(active.id) for f in remaining)


# ---------------------------------------------------------------------------
# _retry_failed — with-token path (dispatches for failed/stale feedback)
# ---------------------------------------------------------------------------


class TestRetryFailedWithToken:
    @pytest.mark.asyncio
    async def test_dispatches_for_failed_feedback(self, db_session, test_user, monkeypatch):
        from app.config import get_settings
        from app.models.feedback import UserFeedback
        from app.tasks.feedback_dispatch import _retry_failed

        monkeypatch.setattr(get_settings(), "github_feedback_token", "ghp_faketoken")

        failed_fb = UserFeedback(
            id=uuid.uuid4(),
            user_id=test_user.id,
            submission_type="bug",
            body="failed feedback",
            dispatch_status="failed",
        )
        db_session.add(failed_fb)
        await db_session.commit()

        mock_dispatch = MagicMock()
        mock_dispatch.delay.return_value = MagicMock(id="task-123")

        with (
            patch("app.database.CeleryAsyncSession", _session_ctx(db_session)),
            patch("app.tasks.feedback_dispatch.dispatch_feedback", mock_dispatch),
            patch("app.services.task_history.record_queued"),
        ):
            result = await _retry_failed(limit=20)

        assert result["dispatched"] >= 1
        mock_dispatch.delay.assert_called()

    @pytest.mark.asyncio
    async def test_respects_limit(self, db_session, test_user, monkeypatch):
        from app.config import get_settings
        from app.models.feedback import UserFeedback
        from app.tasks.feedback_dispatch import _retry_failed

        monkeypatch.setattr(get_settings(), "github_feedback_token", "ghp_faketoken")

        for _ in range(5):
            fb = UserFeedback(
                id=uuid.uuid4(),
                user_id=test_user.id,
                submission_type="bug",
                body="failed feedback",
                dispatch_status="failed",
            )
            db_session.add(fb)
        await db_session.commit()

        mock_dispatch = MagicMock()
        mock_dispatch.delay.return_value = MagicMock(id="task-123")

        with (
            patch("app.database.CeleryAsyncSession", _session_ctx(db_session)),
            patch("app.tasks.feedback_dispatch.dispatch_feedback", mock_dispatch),
            patch("app.services.task_history.record_queued"),
        ):
            result = await _retry_failed(limit=2)

        assert result["dispatched"] == 2
        assert mock_dispatch.delay.call_count == 2

    @pytest.mark.asyncio
    async def test_skips_pending_recent_feedback(self, db_session, test_user, monkeypatch):
        from app.config import get_settings
        from app.models.feedback import UserFeedback
        from app.tasks.feedback_dispatch import _retry_failed

        monkeypatch.setattr(get_settings(), "github_feedback_token", "ghp_faketoken")

        recent_pending = UserFeedback(
            id=uuid.uuid4(),
            user_id=test_user.id,
            submission_type="bug",
            body="recent pending",
            dispatch_status="pending",
        )
        db_session.add(recent_pending)
        await db_session.commit()

        mock_dispatch = MagicMock()
        mock_dispatch.delay.return_value = MagicMock(id="task-123")

        with (
            patch("app.database.CeleryAsyncSession", _session_ctx(db_session)),
            patch("app.tasks.feedback_dispatch.dispatch_feedback", mock_dispatch),
            patch("app.services.task_history.record_queued"),
        ):
            result = await _retry_failed(limit=20)

        # recent pending (< 10 min old) should be skipped
        assert result["dispatched"] == 0
        mock_dispatch.delay.assert_not_called()
