"""Tests for app.tasks.maintenance Celery tasks.

Tasks are called via .run.__func__(mock_self, ...) — the unbound function
with an explicit mock task as self, matching the email_task test pattern.
DB-dependent tests seed data async then verify the sync task reads it correctly.
"""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_PG_TEST_DB = "test_weaving_site"


@pytest.fixture(autouse=True)
def _use_test_db(monkeypatch):
    """Point tasks' sync engine at the test DB instead of the app DB."""
    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "postgres_db", _PG_TEST_DB)
    monkeypatch.setattr(settings, "postgres_dsn", "")
    monkeypatch.setattr(settings, "postgres_dsn_direct", "")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_task() -> MagicMock:
    t = MagicMock()
    t.request = MagicMock()
    t.request.retries = 0
    t.max_retries = 0
    return t


def _ago(**kwargs) -> datetime:
    return datetime.now(timezone.utc) - timedelta(**kwargs)


# ---------------------------------------------------------------------------
# worker_heartbeat
# ---------------------------------------------------------------------------


class TestWorkerHeartbeat:
    def test_returns_ok_true(self):
        from app.tasks.maintenance import worker_heartbeat

        result = worker_heartbeat.run.__func__(_make_task())
        assert result["ok"] is True

    def test_returns_iso_timestamp(self):
        from app.tasks.maintenance import worker_heartbeat

        result = worker_heartbeat.run.__func__(_make_task())
        ts = result["ts"]
        assert "T" in ts
        datetime.fromisoformat(ts)

    def test_completes_quickly(self):
        import time

        from app.tasks.maintenance import worker_heartbeat

        start = time.monotonic()
        worker_heartbeat.run.__func__(_make_task())
        assert time.monotonic() - start < 0.1


# ---------------------------------------------------------------------------
# dismiss_stale_signups
# ---------------------------------------------------------------------------


class TestDismissStaleSignups:
    def test_returns_dismissed_key(self):
        from app.tasks.maintenance import dismiss_stale_signups

        result = dismiss_stale_signups.run.__func__(_make_task(), days=30)
        assert "dismissed" in result
        assert isinstance(result["dismissed"], int)

    def test_zero_when_nothing_old(self):
        from app.tasks.maintenance import dismiss_stale_signups

        result = dismiss_stale_signups.run.__func__(_make_task(), days=9999)
        assert result["dismissed"] == 0

    @pytest.mark.asyncio
    async def test_old_signup_dismissed(self, db_session):
        from sqlalchemy import select

        from app.models.pending_signup import PendingSignup
        from app.tasks.maintenance import dismiss_stale_signups

        old = PendingSignup(
            id=uuid.uuid4(),
            clerk_user_id="stale_clerk_id",
            email="stale@test.com",
            display_name="Stale User",
        )
        old.created_at = _ago(days=60)
        db_session.add(old)
        await db_session.commit()

        result = dismiss_stale_signups.run.__func__(_make_task(), days=30)
        assert result["dismissed"] >= 1

        remaining = (await db_session.scalars(select(PendingSignup))).all()
        assert all(r.clerk_user_id != "stale_clerk_id" for r in remaining)

    @pytest.mark.asyncio
    async def test_recent_signup_preserved(self, db_session):
        from sqlalchemy import select

        from app.models.pending_signup import PendingSignup
        from app.tasks.maintenance import dismiss_stale_signups

        recent = PendingSignup(
            id=uuid.uuid4(),
            clerk_user_id="fresh_clerk_id",
            email="fresh@test.com",
            display_name="Fresh User",
        )
        db_session.add(recent)
        await db_session.commit()

        dismiss_stale_signups.run.__func__(_make_task(), days=30)

        remaining = (await db_session.scalars(select(PendingSignup))).all()
        assert any(r.clerk_user_id == "fresh_clerk_id" for r in remaining)


# ---------------------------------------------------------------------------
# prune_expired_invites
# ---------------------------------------------------------------------------


class TestPruneExpiredInvites:
    def test_returns_pruned_key(self):
        from app.tasks.maintenance import prune_expired_invites

        result = prune_expired_invites.run.__func__(_make_task(), retention_days=90)
        assert "pruned" in result
        assert isinstance(result["pruned"], int)

    def test_zero_when_nothing_to_prune(self):
        from app.tasks.maintenance import prune_expired_invites

        result = prune_expired_invites.run.__func__(_make_task(), retention_days=9999)
        assert result["pruned"] == 0


# ---------------------------------------------------------------------------
# prune_audit_log
# ---------------------------------------------------------------------------


class TestPruneAuditLog:
    def test_returns_deleted_key(self):
        from app.tasks.maintenance import prune_audit_log

        result = prune_audit_log.run.__func__(_make_task(), retention_days=90)
        assert "deleted" in result
        assert isinstance(result["deleted"], int)

    def test_zero_when_nothing_old(self):
        from app.tasks.maintenance import prune_audit_log

        result = prune_audit_log.run.__func__(_make_task(), retention_days=9999)
        assert result["deleted"] == 0

    @pytest.mark.asyncio
    async def test_security_events_exempt(self, db_session):
        from sqlalchemy import select

        from app.models.audit_log import AuditLog
        from app.tasks.maintenance import prune_audit_log

        exempt_types = ("user.banned", "user.deleted", "user.elevated")
        for event_type in exempt_types:
            entry = AuditLog(id=uuid.uuid4(), event_type=event_type, created_at=_ago(days=365))
            db_session.add(entry)
        prunable = AuditLog(id=uuid.uuid4(), event_type="user.login", created_at=_ago(days=365))
        db_session.add(prunable)
        await db_session.commit()

        prune_audit_log.run.__func__(_make_task(), retention_days=1)

        remaining = (await db_session.scalars(select(AuditLog))).all()
        remaining_types = {r.event_type for r in remaining}
        for et in exempt_types:
            assert et in remaining_types
        assert "user.login" not in remaining_types

    @pytest.mark.asyncio
    async def test_non_exempt_old_entries_deleted(self, db_session):
        from sqlalchemy import select

        from app.models.audit_log import AuditLog
        from app.tasks.maintenance import prune_audit_log

        entry = AuditLog(id=uuid.uuid4(), event_type="draft.created", created_at=_ago(days=180))
        db_session.add(entry)
        await db_session.commit()

        result = prune_audit_log.run.__func__(_make_task(), retention_days=30)
        assert result["deleted"] >= 1

        remaining = (await db_session.scalars(select(AuditLog))).all()
        assert all(r.event_type != "draft.created" for r in remaining)


# ---------------------------------------------------------------------------
# retry_failed_previews
# ---------------------------------------------------------------------------


class TestRetryFailedPreviews:
    def test_returns_retried_key(self):
        from app.tasks.maintenance import retry_failed_previews

        result = retry_failed_previews.run.__func__(_make_task(), limit=50)
        assert "retried" in result
        assert isinstance(result["retried"], int)

    def test_zero_when_no_missing_previews(self):
        from app.tasks.maintenance import retry_failed_previews

        result = retry_failed_previews.run.__func__(_make_task(), limit=50)
        assert result["retried"] == 0

    @pytest.mark.asyncio
    async def test_dispatches_for_missing_preview(self, db_session, test_user):
        from app.models.draft import Draft
        from app.tasks.maintenance import retry_failed_previews

        d = Draft(
            id=uuid.uuid4(),
            owner_id=test_user.id,
            name="No Preview",
            wif_filename="test.wif",
            wif_path=f"uploads/{uuid.uuid4()}.wif",
            drawdown_preview_path=None,
        )
        d.created_at = _ago(minutes=30)
        db_session.add(d)
        await db_session.commit()

        with patch("app.tasks.preview.generate_drawdown_preview") as mock_preview:
            mock_preview.delay = MagicMock()
            result = retry_failed_previews.run.__func__(_make_task(), limit=50)

        assert result["retried"] >= 1
        mock_preview.delay.assert_called()

    @pytest.mark.asyncio
    async def test_respects_limit(self, db_session, test_user):
        from app.models.draft import Draft
        from app.tasks.maintenance import retry_failed_previews

        for i in range(5):
            d = Draft(
                id=uuid.uuid4(),
                owner_id=test_user.id,
                name=f"Draft {i}",
                wif_filename="test.wif",
                wif_path=f"uploads/{uuid.uuid4()}.wif",
                drawdown_preview_path=None,
            )
            d.created_at = _ago(minutes=30)
            db_session.add(d)
        await db_session.commit()

        with patch("app.tasks.preview.generate_drawdown_preview") as mock_preview:
            mock_preview.delay = MagicMock()
            result = retry_failed_previews.run.__func__(_make_task(), limit=2)

        assert result["retried"] == 2

    @pytest.mark.asyncio
    async def test_skips_recent_uploads(self, db_session, test_user):
        from app.models.draft import Draft
        from app.tasks.maintenance import retry_failed_previews

        recent = Draft(
            id=uuid.uuid4(),
            owner_id=test_user.id,
            name="Just Uploaded",
            wif_filename="test.wif",
            wif_path=f"uploads/{uuid.uuid4()}.wif",
            drawdown_preview_path=None,
        )
        recent.created_at = _ago(minutes=2)
        db_session.add(recent)
        await db_session.commit()

        with patch("app.tasks.preview.generate_drawdown_preview") as mock_preview:
            mock_preview.delay = MagicMock()
            result = retry_failed_previews.run.__func__(_make_task(), limit=50)

        mock_preview.delay.assert_not_called()
        assert result["retried"] == 0

    @pytest.mark.asyncio
    async def test_skips_soft_deleted_drafts(self, db_session, test_user):
        from app.models.draft import Draft
        from app.tasks.maintenance import retry_failed_previews  # noqa: F811

        deleted = Draft(
            id=uuid.uuid4(),
            owner_id=test_user.id,
            name="Deleted Draft",
            wif_filename="test.wif",
            wif_path=f"uploads/{uuid.uuid4()}.wif",
            drawdown_preview_path=None,
        )
        deleted.created_at = _ago(minutes=30)
        deleted.deleted_at = _ago(minutes=20)
        db_session.add(deleted)
        await db_session.commit()

        with patch("app.tasks.preview.generate_drawdown_preview") as mock_preview:
            mock_preview.delay = MagicMock()
            result = retry_failed_previews.run.__func__(_make_task(), limit=50)

        mock_preview.delay.assert_not_called()
        assert result["retried"] == 0


# ---------------------------------------------------------------------------
# check_credential_expiry
# ---------------------------------------------------------------------------


def _cred(db, *, expires_in_days: int | None, last_alerted_hours_ago: float | None = None):
    from datetime import date, timedelta

    from app.models.credential_expiry import CredentialExpiry

    now = datetime.now(timezone.utc)
    expires_on = (date.today() + timedelta(days=expires_in_days)) if expires_in_days is not None else None
    last_alerted_at = (now - timedelta(hours=last_alerted_hours_ago)) if last_alerted_hours_ago is not None else None
    c = CredentialExpiry(
        id=uuid.uuid4(),
        name="Test Cred",
        resource="smtp",
        expires_on=expires_on,
        last_alerted_at=last_alerted_at,
    )
    db.add(c)
    return c


class TestCheckCredentialExpiry:
    @pytest.mark.asyncio
    async def test_no_credentials_returns_zero(self, db_session):
        from app.tasks.maintenance import check_credential_expiry

        with patch("app.tasks.maintenance._send_credential_alerts") as mock_send:
            result = check_credential_expiry.run.__func__(_make_task())

        assert result["alerted"] == 0
        mock_send.assert_not_called()

    @pytest.mark.asyncio
    async def test_credential_beyond_30_days_skipped(self, db_session):
        from app.tasks.maintenance import check_credential_expiry

        _cred(db_session, expires_in_days=60)
        await db_session.commit()

        with patch("app.tasks.maintenance._send_credential_alerts") as mock_send:
            result = check_credential_expiry.run.__func__(_make_task())

        assert result["alerted"] == 0
        assert result["skipped"] >= 1
        mock_send.assert_not_called()

    @pytest.mark.asyncio
    async def test_credential_at_25_days_alerts_first_time(self, db_session):
        from app.tasks.maintenance import check_credential_expiry

        _cred(db_session, expires_in_days=25, last_alerted_hours_ago=None)
        await db_session.commit()

        with patch("app.tasks.maintenance._send_credential_alerts") as mock_send:
            mock_send.return_value = None
            result = check_credential_expiry.run.__func__(_make_task())

        assert result["alerted"] >= 1

    @pytest.mark.asyncio
    async def test_credential_at_5_days_alerts(self, db_session):
        from app.tasks.maintenance import check_credential_expiry

        _cred(db_session, expires_in_days=5, last_alerted_hours_ago=None)
        await db_session.commit()

        with patch("app.tasks.maintenance._send_credential_alerts") as mock_send:
            mock_send.return_value = None
            result = check_credential_expiry.run.__func__(_make_task())

        assert result["alerted"] >= 1

    @pytest.mark.asyncio
    async def test_weekly_dedup_skips_within_7_days(self, db_session):
        from app.tasks.maintenance import check_credential_expiry

        _cred(db_session, expires_in_days=20, last_alerted_hours_ago=72)
        await db_session.commit()

        with patch("app.tasks.maintenance._send_credential_alerts") as mock_send:
            result = check_credential_expiry.run.__func__(_make_task())

        assert result["alerted"] == 0
        assert result["skipped"] >= 1
        mock_send.assert_not_called()

    @pytest.mark.asyncio
    async def test_daily_dedup_skips_within_24h(self, db_session):
        from app.tasks.maintenance import check_credential_expiry

        _cred(db_session, expires_in_days=3, last_alerted_hours_ago=12)
        await db_session.commit()

        with patch("app.tasks.maintenance._send_credential_alerts") as mock_send:
            result = check_credential_expiry.run.__func__(_make_task())

        assert result["alerted"] == 0
        mock_send.assert_not_called()

    @pytest.mark.asyncio
    async def test_overdue_credential_alerts(self, db_session):
        from app.tasks.maintenance import check_credential_expiry

        _cred(db_session, expires_in_days=-5, last_alerted_hours_ago=None)
        await db_session.commit()

        with patch("app.tasks.maintenance._send_credential_alerts") as mock_send:
            mock_send.return_value = None
            result = check_credential_expiry.run.__func__(_make_task())

        assert result["alerted"] >= 1

    @pytest.mark.asyncio
    async def test_last_alerted_at_updated_after_alert(self, db_session):
        from app.tasks.maintenance import check_credential_expiry

        cred = _cred(db_session, expires_in_days=5, last_alerted_hours_ago=None)
        await db_session.commit()

        with patch("app.tasks.maintenance._send_credential_alerts") as mock_send:
            mock_send.return_value = None
            check_credential_expiry.run.__func__(_make_task())

        await db_session.refresh(cred)
        assert cred.last_alerted_at is not None

    @pytest.mark.asyncio
    async def test_no_expiry_credential_skipped(self, db_session):
        from app.tasks.maintenance import check_credential_expiry

        _cred(db_session, expires_in_days=None)
        await db_session.commit()

        with patch("app.tasks.maintenance._send_credential_alerts") as mock_send:
            result = check_credential_expiry.run.__func__(_make_task())

        assert result["alerted"] == 0
        mock_send.assert_not_called()
