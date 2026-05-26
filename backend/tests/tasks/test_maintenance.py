"""Tests for app.tasks.maintenance Celery tasks.

Tasks are called via .run.__func__(mock_self, ...) — the unbound function
with an explicit mock task as self, matching the email_task test pattern.
DB-dependent tests seed data async then verify the sync task reads it correctly.
"""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_PG_TEST_DB = "test_weaving_site"


@pytest.fixture(autouse=True)
def _use_test_db(monkeypatch, db_available):
    """Point tasks' sync engine at the test DB instead of the app DB."""
    import os

    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "postgres_db", _PG_TEST_DB)
    monkeypatch.setattr(settings, "postgres_dsn", "")
    monkeypatch.setattr(settings, "postgres_dsn_direct", "")
    monkeypatch.setattr(settings, "postgres_host", os.getenv("POSTGRES_HOST", "localhost"))
    monkeypatch.setattr(settings, "postgres_port", int(os.getenv("POSTGRES_PORT", "5433")))


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
# backfill_project_drawdown_previews
# ---------------------------------------------------------------------------


class TestBackfillProjectDrawdownPreviews:
    def test_returns_dispatched_key(self):
        from app.tasks.maintenance import backfill_project_drawdown_previews

        result = backfill_project_drawdown_previews.run.__func__(_make_task())
        assert "dispatched" in result
        assert isinstance(result["dispatched"], int)

    def test_zero_when_no_active_projects(self):
        from app.tasks.maintenance import backfill_project_drawdown_previews

        result = backfill_project_drawdown_previews.run.__func__(_make_task())
        assert result["dispatched"] == 0

    @pytest.mark.asyncio
    async def test_dispatches_for_active_project_with_missing_preview(self, db_session, test_user):
        import uuid as _uuid

        import app.services.storage as storage
        from app.models.draft import Draft
        from app.models.project import Project
        from app.tasks.maintenance import backfill_project_drawdown_previews

        draft = Draft(
            id=_uuid.uuid4(),
            owner_id=test_user.id,
            name="No Preview Draft",
            wif_filename="test.wif",
            wif_path=storage.save_wif(_uuid.uuid4(), "test.wif", b"[WIF]"),
            drawdown_preview_path=None,
        )
        db_session.add(draft)
        await db_session.flush()

        project = Project(
            owner_id=test_user.id,
            draft_id=draft.id,
            name="Active Project",
            project_type="treadle",
            status="active",
            current_pick=1,
            total_picks=10,
        )
        db_session.add(project)
        await db_session.commit()

        with patch("app.tasks.preview.generate_drawdown_preview") as mock_preview:
            mock_preview.delay = MagicMock()
            result = backfill_project_drawdown_previews.run.__func__(_make_task())

        assert result["dispatched"] >= 1
        mock_preview.delay.assert_called_once_with(str(draft.id))

    @pytest.mark.asyncio
    async def test_skips_completed_project(self, db_session, test_user):
        import uuid as _uuid

        import app.services.storage as storage
        from app.models.draft import Draft
        from app.models.project import Project
        from app.tasks.maintenance import backfill_project_drawdown_previews

        draft = Draft(
            id=_uuid.uuid4(),
            owner_id=test_user.id,
            name="Draft",
            wif_filename="test.wif",
            wif_path=storage.save_wif(_uuid.uuid4(), "test.wif", b"[WIF]"),
            drawdown_preview_path=None,
        )
        db_session.add(draft)
        await db_session.flush()
        project = Project(
            owner_id=test_user.id,
            draft_id=draft.id,
            name="Completed",
            project_type="treadle",
            status="completed",
            current_pick=10,
            total_picks=10,
        )
        db_session.add(project)
        await db_session.commit()

        with patch("app.tasks.preview.generate_drawdown_preview") as mock_preview:
            mock_preview.delay = MagicMock()
            result = backfill_project_drawdown_previews.run.__func__(_make_task())

        mock_preview.delay.assert_not_called()
        assert result["dispatched"] == 0

    @pytest.mark.asyncio
    async def test_skips_abandoned_project(self, db_session, test_user):
        import uuid as _uuid

        import app.services.storage as storage
        from app.models.draft import Draft
        from app.models.project import Project
        from app.tasks.maintenance import backfill_project_drawdown_previews

        draft = Draft(
            id=_uuid.uuid4(),
            owner_id=test_user.id,
            name="Draft",
            wif_filename="test.wif",
            wif_path=storage.save_wif(_uuid.uuid4(), "test.wif", b"[WIF]"),
            drawdown_preview_path=None,
        )
        db_session.add(draft)
        await db_session.flush()
        project = Project(
            owner_id=test_user.id,
            draft_id=draft.id,
            name="Abandoned",
            project_type="treadle",
            status="abandoned",
            current_pick=1,
            total_picks=10,
        )
        db_session.add(project)
        await db_session.commit()

        with patch("app.tasks.preview.generate_drawdown_preview") as mock_preview:
            mock_preview.delay = MagicMock()
            result = backfill_project_drawdown_previews.run.__func__(_make_task())

        mock_preview.delay.assert_not_called()
        assert result["dispatched"] == 0

    @pytest.mark.asyncio
    async def test_skips_project_with_existing_preview(self, db_session, test_user):
        import uuid as _uuid

        import app.services.storage as storage
        from app.models.draft import Draft
        from app.models.project import Project
        from app.tasks.maintenance import backfill_project_drawdown_previews

        draft = Draft(
            id=_uuid.uuid4(),
            owner_id=test_user.id,
            name="Draft",
            wif_filename="test.wif",
            wif_path=storage.save_wif(_uuid.uuid4(), "test.wif", b"[WIF]"),
            drawdown_preview_path="drawdown-previews/existing.png",
        )
        db_session.add(draft)
        await db_session.flush()
        project = Project(
            owner_id=test_user.id,
            draft_id=draft.id,
            name="Has Preview",
            project_type="treadle",
            status="active",
            current_pick=1,
            total_picks=10,
        )
        db_session.add(project)
        await db_session.commit()

        with patch("app.tasks.preview.generate_drawdown_preview") as mock_preview:
            mock_preview.delay = MagicMock()
            result = backfill_project_drawdown_previews.run.__func__(_make_task())

        mock_preview.delay.assert_not_called()
        assert result["dispatched"] == 0

    @pytest.mark.asyncio
    async def test_deduplicates_same_draft_across_projects(self, db_session, test_user):
        import uuid as _uuid

        import app.services.storage as storage
        from app.models.draft import Draft
        from app.models.project import Project
        from app.tasks.maintenance import backfill_project_drawdown_previews

        draft = Draft(
            id=_uuid.uuid4(),
            owner_id=test_user.id,
            name="Shared Draft",
            wif_filename="test.wif",
            wif_path=storage.save_wif(_uuid.uuid4(), "test.wif", b"[WIF]"),
            drawdown_preview_path=None,
        )
        db_session.add(draft)
        await db_session.flush()

        for i in range(3):
            db_session.add(
                Project(
                    owner_id=test_user.id,
                    draft_id=draft.id,
                    name=f"Project {i}",
                    project_type="treadle",
                    status="active",
                    current_pick=1,
                    total_picks=10,
                )
            )
        await db_session.commit()

        with patch("app.tasks.preview.generate_drawdown_preview") as mock_preview:
            mock_preview.delay = MagicMock()
            result = backfill_project_drawdown_previews.run.__func__(_make_task())

        assert result["dispatched"] == 1
        mock_preview.delay.assert_called_once_with(str(draft.id))

    @pytest.mark.asyncio
    async def test_respects_limit(self, db_session, test_user):
        import uuid as _uuid

        import app.services.storage as storage
        from app.models.draft import Draft
        from app.models.project import Project
        from app.tasks.maintenance import backfill_project_drawdown_previews

        for i in range(5):
            draft = Draft(
                id=_uuid.uuid4(),
                owner_id=test_user.id,
                name=f"Draft {i}",
                wif_filename="test.wif",
                wif_path=storage.save_wif(_uuid.uuid4(), "test.wif", b"[WIF]"),
                drawdown_preview_path=None,
            )
            db_session.add(draft)
            await db_session.flush()
            db_session.add(
                Project(
                    owner_id=test_user.id,
                    draft_id=draft.id,
                    name=f"Project {i}",
                    project_type="treadle",
                    status="active",
                    current_pick=1,
                    total_picks=10,
                )
            )
        await db_session.commit()

        with patch("app.tasks.preview.generate_drawdown_preview") as mock_preview:
            mock_preview.delay = MagicMock()
            result = backfill_project_drawdown_previews.run.__func__(_make_task(), limit=2)

        assert result["dispatched"] == 2
        assert mock_preview.delay.call_count == 2

    @pytest.mark.asyncio
    async def test_skips_soft_deleted_project(self, db_session, test_user):
        import uuid as _uuid

        import app.services.storage as storage
        from app.models.draft import Draft
        from app.models.project import Project
        from app.tasks.maintenance import backfill_project_drawdown_previews

        draft = Draft(
            id=_uuid.uuid4(),
            owner_id=test_user.id,
            name="Draft",
            wif_filename="test.wif",
            wif_path=storage.save_wif(_uuid.uuid4(), "test.wif", b"[WIF]"),
            drawdown_preview_path=None,
        )
        db_session.add(draft)
        await db_session.flush()
        project = Project(
            owner_id=test_user.id,
            draft_id=draft.id,
            name="Deleted",
            project_type="treadle",
            status="active",
            current_pick=1,
            total_picks=10,
        )
        project.deleted_at = _ago(minutes=5)
        db_session.add(project)
        await db_session.commit()

        with patch("app.tasks.preview.generate_drawdown_preview") as mock_preview:
            mock_preview.delay = MagicMock()
            result = backfill_project_drawdown_previews.run.__func__(_make_task())

        mock_preview.delay.assert_not_called()
        assert result["dispatched"] == 0


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

        with patch("app.tasks.maintenance._send_credential_alerts", new_callable=AsyncMock):
            result = check_credential_expiry.run.__func__(_make_task())

        assert result["alerted"] >= 1

    @pytest.mark.asyncio
    async def test_credential_at_5_days_alerts(self, db_session):
        from app.tasks.maintenance import check_credential_expiry

        _cred(db_session, expires_in_days=5, last_alerted_hours_ago=None)
        await db_session.commit()

        with patch("app.tasks.maintenance._send_credential_alerts", new_callable=AsyncMock):
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

        with patch("app.tasks.maintenance._send_credential_alerts", new_callable=AsyncMock):
            result = check_credential_expiry.run.__func__(_make_task())

        assert result["alerted"] >= 1

    @pytest.mark.asyncio
    async def test_last_alerted_at_updated_after_alert(self, db_session):
        from app.tasks.maintenance import check_credential_expiry

        cred = _cred(db_session, expires_in_days=5, last_alerted_hours_ago=None)
        await db_session.commit()

        with patch("app.tasks.maintenance._send_credential_alerts", new_callable=AsyncMock):
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


# ---------------------------------------------------------------------------
# send_admin_digest
# ---------------------------------------------------------------------------


def _make_admin(db, *, is_admin: bool = True, is_active: bool = True):
    from app.models.user import User

    u = User(
        id=uuid.uuid4(),
        email=f"admin-{uuid.uuid4().hex[:8]}@example.test",
        display_name="Admin User",
        is_admin=is_admin,
        is_active=is_active,
    )
    db.add(u)
    return u


class TestSendAdminDigest:
    @pytest.mark.asyncio
    async def test_no_admins_returns_zero(self, db_session):
        from app.tasks.maintenance import send_admin_digest

        with patch("app.tasks.maintenance._send_admin_digest_email", new_callable=AsyncMock) as mock_send:
            with patch("redis.from_url") as mock_redis:
                mock_redis.return_value.get.return_value = None
                result = send_admin_digest.run.__func__(_make_task())

        assert result["sent"] == 0
        mock_send.assert_not_called()

    @pytest.mark.asyncio
    async def test_sends_email_to_active_admins(self, db_session):
        from app.tasks.maintenance import send_admin_digest

        _make_admin(db_session)
        await db_session.commit()

        with patch("app.tasks.maintenance._send_admin_digest_email", new_callable=AsyncMock) as mock_send:
            with patch("redis.from_url") as mock_redis:
                mock_redis.return_value.get.return_value = None
                result = send_admin_digest.run.__func__(_make_task())

        assert result["sent"] == 1
        mock_send.assert_called_once()

    @pytest.mark.asyncio
    async def test_inactive_admin_excluded(self, db_session):
        from app.tasks.maintenance import send_admin_digest

        _make_admin(db_session, is_active=False)
        await db_session.commit()

        with patch("app.tasks.maintenance._send_admin_digest_email", new_callable=AsyncMock) as mock_send:
            with patch("redis.from_url") as mock_redis:
                mock_redis.return_value.get.return_value = None
                result = send_admin_digest.run.__func__(_make_task())

        assert result["sent"] == 0
        mock_send.assert_not_called()

    @pytest.mark.asyncio
    async def test_redis_failure_still_sends_email(self, db_session):
        from app.tasks.maintenance import send_admin_digest

        _make_admin(db_session)
        await db_session.commit()

        with patch("app.tasks.maintenance._send_admin_digest_email", new_callable=AsyncMock) as mock_send:
            with patch("redis.from_url", side_effect=Exception("Redis unavailable")):
                result = send_admin_digest.run.__func__(_make_task())

        assert result["sent"] == 1
        mock_send.assert_called_once()

    @pytest.mark.asyncio
    async def test_storage_delta_computed_from_prior_run(self, db_session):
        import json

        from app.tasks.maintenance import DIGEST_STATE_KEY, send_admin_digest

        _make_admin(db_session)
        await db_session.commit()

        prior_state = json.dumps({"sent_at": "2026-01-01T08:00:00+00:00", "storage_bytes": 1_048_576})

        with patch("app.tasks.maintenance._send_admin_digest_email", new_callable=AsyncMock) as mock_send:
            mock_client = MagicMock()
            mock_client.get.side_effect = lambda key: prior_state.encode() if key == DIGEST_STATE_KEY else None
            with patch("redis.from_url", return_value=mock_client):
                result = send_admin_digest.run.__func__(_make_task())

        assert result["sent"] == 1
        call_kwargs = mock_send.call_args.kwargs
        # storage_delta_str should be set (non-None) since prior baseline exists
        assert call_kwargs["storage_delta_str"] is not None


# ---------------------------------------------------------------------------
# prune_inactive_project_tiles
# ---------------------------------------------------------------------------


class TestPruneInactiveProjectTiles:
    def test_returns_result_keys(self):
        from app.tasks.maintenance import prune_inactive_project_tiles

        with patch("app.services.storage.delete_project_tiles", return_value=0):
            result = prune_inactive_project_tiles.run.__func__(_make_task(), inactive_days=9999)

        assert "pruned_projects" in result
        assert "pruned_tiles" in result
        assert isinstance(result["pruned_projects"], int)
        assert isinstance(result["pruned_tiles"], int)

    def test_zero_when_no_projects(self):
        from app.tasks.maintenance import prune_inactive_project_tiles

        with patch("app.services.storage.delete_project_tiles", return_value=0) as mock_del:
            result = prune_inactive_project_tiles.run.__func__(_make_task(), inactive_days=9999)

        assert result["pruned_projects"] == 0
        assert result["pruned_tiles"] == 0
        mock_del.assert_not_called()

    @pytest.mark.asyncio
    async def test_prunes_inactive_project(self, db_session, test_user):
        import uuid as _uuid

        import app.services.storage as storage
        from app.models.draft import Draft
        from app.models.project import Project
        from app.tasks.maintenance import prune_inactive_project_tiles

        draft = Draft(
            id=_uuid.uuid4(),
            owner_id=test_user.id,
            name="Draft",
            wif_filename="test.wif",
            wif_path=storage.save_wif(_uuid.uuid4(), "test.wif", b"[WIF]"),
        )
        db_session.add(draft)
        await db_session.flush()

        project = Project(
            owner_id=test_user.id,
            draft_id=draft.id,
            name="Stale Project",
            project_type="treadle",
            status="active",
            current_pick=1,
            total_picks=10,
        )
        db_session.add(project)
        await db_session.commit()

        # Backdate updated_at to simulate inactive project
        from sqlalchemy import update as _update

        from app.models.project import Project as _Project

        await db_session.execute(_update(_Project).where(_Project.id == project.id).values(updated_at=_ago(days=20)))
        await db_session.commit()

        with patch("app.services.storage.delete_project_tiles", return_value=5) as mock_del:
            result = prune_inactive_project_tiles.run.__func__(_make_task(), inactive_days=10)

        mock_del.assert_called_once_with(project.id)
        assert result["pruned_projects"] == 1
        assert result["pruned_tiles"] == 5

    @pytest.mark.asyncio
    async def test_keeps_recently_active_project(self, db_session, test_user):
        import uuid as _uuid

        import app.services.storage as storage
        from app.models.draft import Draft
        from app.models.project import Project
        from app.tasks.maintenance import prune_inactive_project_tiles

        draft = Draft(
            id=_uuid.uuid4(),
            owner_id=test_user.id,
            name="Draft",
            wif_filename="test.wif",
            wif_path=storage.save_wif(_uuid.uuid4(), "test.wif", b"[WIF]"),
        )
        db_session.add(draft)
        await db_session.flush()

        project = Project(
            owner_id=test_user.id,
            draft_id=draft.id,
            name="Active Project",
            project_type="treadle",
            status="active",
            current_pick=5,
            total_picks=10,
        )
        db_session.add(project)
        await db_session.commit()
        # updated_at is just now — should NOT be pruned

        with patch("app.services.storage.delete_project_tiles", return_value=0) as mock_del:
            result = prune_inactive_project_tiles.run.__func__(_make_task(), inactive_days=10)

        mock_del.assert_not_called()
        assert result["pruned_projects"] == 0

    @pytest.mark.asyncio
    async def test_prunes_soft_deleted_project(self, db_session, test_user):
        import uuid as _uuid

        import app.services.storage as storage
        from app.models.draft import Draft
        from app.models.project import Project
        from app.tasks.maintenance import prune_inactive_project_tiles

        draft = Draft(
            id=_uuid.uuid4(),
            owner_id=test_user.id,
            name="Draft",
            wif_filename="test.wif",
            wif_path=storage.save_wif(_uuid.uuid4(), "test.wif", b"[WIF]"),
        )
        db_session.add(draft)
        await db_session.flush()

        project = Project(
            owner_id=test_user.id,
            draft_id=draft.id,
            name="Deleted Project",
            project_type="treadle",
            status="active",
            current_pick=1,
            total_picks=10,
        )
        project.deleted_at = _ago(minutes=5)
        db_session.add(project)
        await db_session.commit()

        with patch("app.services.storage.delete_project_tiles", return_value=3) as mock_del:
            result = prune_inactive_project_tiles.run.__func__(_make_task(), inactive_days=9999)

        mock_del.assert_called_once_with(project.id)
        assert result["pruned_projects"] == 1


# ---------------------------------------------------------------------------
# prune_server_event_log
# ---------------------------------------------------------------------------


class TestPruneServerEventLog:
    def test_returns_result_keys(self):
        from app.tasks.maintenance import prune_server_event_log

        result = prune_server_event_log.run.__func__(_make_task(), max_age_days=9999, max_entries=1000)
        assert "deleted_age" in result
        assert "deleted_overflow" in result

    def test_zero_when_nothing_old(self):
        from app.tasks.maintenance import prune_server_event_log

        result = prune_server_event_log.run.__func__(_make_task(), max_age_days=9999, max_entries=9999)
        assert result["deleted_age"] == 0
        assert result["deleted_overflow"] == 0

    @pytest.mark.asyncio
    async def test_deletes_old_events(self, db_session):
        from sqlalchemy import select

        from app.models.server_event import ServerEvent
        from app.tasks.maintenance import prune_server_event_log

        old_evt = ServerEvent(
            event_type="health.check",
            severity="info",
            status="closed",
            started_at=_ago(days=60),
            ended_at=_ago(days=60),
            app_version="0.0.1",
            message="old event",
            details={},
        )
        db_session.add(old_evt)
        await db_session.commit()

        result = prune_server_event_log.run.__func__(_make_task(), max_age_days=30, max_entries=9999)
        assert result["deleted_age"] >= 1

        remaining = (await db_session.scalars(select(ServerEvent))).all()
        assert all(e.message != "old event" for e in remaining)

    @pytest.mark.asyncio
    async def test_keeps_recent_events(self, db_session):
        from sqlalchemy import select

        from app.models.server_event import ServerEvent
        from app.tasks.maintenance import prune_server_event_log

        recent = ServerEvent(
            event_type="health.check",
            severity="info",
            status="closed",
            started_at=_ago(hours=1),
            ended_at=_ago(hours=1),
            app_version="0.0.1",
            message="recent event",
            details={},
        )
        db_session.add(recent)
        await db_session.commit()

        result = prune_server_event_log.run.__func__(_make_task(), max_age_days=30, max_entries=9999)
        assert result["deleted_age"] == 0

        remaining = (await db_session.scalars(select(ServerEvent))).all()
        assert any(e.message == "recent event" for e in remaining)

    @pytest.mark.asyncio
    async def test_overflow_prunes_oldest_first(self, db_session):
        from sqlalchemy import select

        from app.models.server_event import ServerEvent
        from app.tasks.maintenance import prune_server_event_log

        for i in range(5):
            evt = ServerEvent(
                event_type="health.check",
                severity="info",
                status="closed",
                started_at=_ago(hours=5 - i),
                ended_at=_ago(hours=5 - i),
                app_version="0.0.1",
                message=f"overflow_event_{i}",
                details={},
            )
            db_session.add(evt)
        await db_session.commit()

        result = prune_server_event_log.run.__func__(_make_task(), max_age_days=9999, max_entries=3)
        assert result["deleted_overflow"] == 2

        remaining = (await db_session.scalars(select(ServerEvent))).all()
        assert len(remaining) == 3


# ---------------------------------------------------------------------------
# _fmt_bytes and _fmt_delta
# ---------------------------------------------------------------------------


class TestFmtBytes:
    def test_bytes(self):
        from app.tasks.maintenance import _fmt_bytes

        assert _fmt_bytes(500) == "500 B"

    def test_kilobytes(self):
        from app.tasks.maintenance import _fmt_bytes

        assert "KB" in _fmt_bytes(2048)

    def test_megabytes(self):
        from app.tasks.maintenance import _fmt_bytes

        assert "MB" in _fmt_bytes(2 * 1024 * 1024)

    def test_gigabytes(self):
        from app.tasks.maintenance import _fmt_bytes

        assert "GB" in _fmt_bytes(2 * 1024 * 1024 * 1024)


class TestFmtDelta:
    def test_positive_delta(self):
        from app.tasks.maintenance import _fmt_delta

        result = _fmt_delta(1024)
        assert result.startswith("+")

    def test_negative_delta(self):
        from app.tasks.maintenance import _fmt_delta

        result = _fmt_delta(-1024)
        assert result.startswith("-")


# ---------------------------------------------------------------------------
# _send_credential_alerts (the inner async helper)
# ---------------------------------------------------------------------------


class TestSendCredentialAlerts:
    @pytest.mark.asyncio
    async def test_sends_to_superusers_and_admins(self):
        from unittest.mock import AsyncMock, patch

        from app.tasks.maintenance import _send_credential_alerts

        with (
            patch("app.services.email.send_credential_expiring_superuser", new_callable=AsyncMock) as mock_su,
            patch("app.services.email.send_credential_expiring_admin", new_callable=AsyncMock) as mock_adm,
        ):
            await _send_credential_alerts(
                superuser_emails=["su@test.com"],
                admin_emails=["admin@test.com"],
                credential_name="Test Cred",
                resource="test-resource",
                days_remaining=5,
                expires_on="2026-06-01",
            )

        mock_su.assert_called_once()
        mock_adm.assert_called_once()

    @pytest.mark.asyncio
    async def test_passes_correct_credential_name(self):
        from unittest.mock import AsyncMock, patch

        from app.tasks.maintenance import _send_credential_alerts

        with (
            patch("app.services.email.send_credential_expiring_superuser", new_callable=AsyncMock) as mock_su,
            patch("app.services.email.send_credential_expiring_admin", new_callable=AsyncMock),
        ):
            await _send_credential_alerts(
                superuser_emails=["su@test.com"],
                admin_emails=[],
                credential_name="My API Key",
                resource="some-service",
                days_remaining=3,
                expires_on="2026-07-01",
            )
        call_kwargs = mock_su.call_args.kwargs
        assert call_kwargs["credential_name"] == "My API Key"


# ---------------------------------------------------------------------------
# send_admin_digest — Redis-populated CVE/S3 branches
# ---------------------------------------------------------------------------


class TestSendAdminDigestRedisBranches:
    @pytest.mark.asyncio
    async def test_cve_data_from_redis_used(self, db_session):
        import json
        from unittest.mock import AsyncMock, MagicMock, patch

        from app.models.user import User
        from app.tasks.cve_scan import CVE_SUMMARY_KEY
        from app.tasks.maintenance import send_admin_digest

        admin = User(
            id=uuid.uuid4(),
            email=f"admin-{uuid.uuid4().hex[:8]}@example.test",
            display_name="Admin",
            is_admin=True,
            is_active=True,
        )
        db_session.add(admin)
        await db_session.commit()

        cve_data = json.dumps({"finding_count": 3, "scanned_at": "2026-05-18T02:00:00"})

        mock_client = MagicMock()

        def _redis_get(key):
            if key == CVE_SUMMARY_KEY:
                return cve_data.encode()
            return None

        mock_client.get.side_effect = _redis_get

        with (
            patch("app.tasks.maintenance._send_admin_digest_email", new_callable=AsyncMock) as mock_send,
            patch("redis.from_url", return_value=mock_client),
        ):
            result = send_admin_digest.run.__func__(_make_task())

        assert result["sent"] == 1
        call_kwargs = mock_send.call_args.kwargs
        assert call_kwargs["cve_finding_count"] == 3

    @pytest.mark.asyncio
    async def test_s3_data_from_redis_used(self, db_session):
        import json
        from unittest.mock import AsyncMock, MagicMock, patch

        from app.models.user import User
        from app.tasks.maintenance import send_admin_digest
        from app.tasks.s3_audit import S3_AUDIT_SUMMARY_KEY

        admin = User(
            id=uuid.uuid4(),
            email=f"admin-{uuid.uuid4().hex[:8]}@example.test",
            display_name="Admin",
            is_admin=True,
            is_active=True,
        )
        db_session.add(admin)
        await db_session.commit()

        s3_data = json.dumps({"orphaned_count": 5, "scanned_at": "2026-05-18T03:00:00", "not_applicable": False})

        mock_client = MagicMock()

        def _redis_get(key):
            if key == S3_AUDIT_SUMMARY_KEY:
                return s3_data.encode()
            return None

        mock_client.get.side_effect = _redis_get

        with (
            patch("app.tasks.maintenance._send_admin_digest_email", new_callable=AsyncMock) as mock_send,
            patch("redis.from_url", return_value=mock_client),
        ):
            result = send_admin_digest.run.__func__(_make_task())

        assert result["sent"] == 1
        call_kwargs = mock_send.call_args.kwargs
        assert call_kwargs["s3_orphaned_count"] == 5


# ---------------------------------------------------------------------------
# _send_admin_digest_email — async email helper
# ---------------------------------------------------------------------------


class TestSendAdminDigestEmail:
    @pytest.mark.asyncio
    async def test_calls_email_service(self):
        from app.tasks.maintenance import _send_admin_digest_email

        with patch("app.services.email.send_admin_digest_email", new=AsyncMock()) as mock_send:
            await _send_admin_digest_email(
                admin_emails=["admin@test.com"],
                week_start="2026-01-01",
                week_end="2026-01-07",
                new_users=5,
                pending_signups=2,
                new_drafts=10,
                new_projects=3,
                new_looms=1,
                storage_str="1.5 GB",
                storage_delta_str="+100 MB",
                cve_finding_count=0,
                cve_scanned_at=None,
                s3_orphaned_count=None,
                s3_scanned_at=None,
            )

        mock_send.assert_called_once()

    @pytest.mark.asyncio
    async def test_passes_admin_emails_through(self):
        from app.tasks.maintenance import _send_admin_digest_email

        with patch("app.services.email.send_admin_digest_email", new=AsyncMock()) as mock_send:
            await _send_admin_digest_email(
                admin_emails=["a@test.com", "b@test.com"],
                week_start="2026-01-01",
                week_end="2026-01-07",
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

        call_kwargs = mock_send.call_args.kwargs
        assert call_kwargs["admin_emails"] == ["a@test.com", "b@test.com"]


# ---------------------------------------------------------------------------
# expire_project_slugs — revoke expired share slugs
# ---------------------------------------------------------------------------


class TestExpireProjectSlugs:
    def test_returns_revoked_key(self):
        from app.tasks.maintenance import expire_project_slugs

        result = expire_project_slugs.run.__func__(_make_task())
        assert "revoked" in result

    def test_zero_when_no_expired_slugs(self):
        from app.tasks.maintenance import expire_project_slugs

        result = expire_project_slugs.run.__func__(_make_task())
        assert result["revoked"] == 0

    @pytest.mark.asyncio
    async def test_revokes_expired_project_slug(self, db_session, test_user):

        from app.models.draft import Draft
        from app.models.project import Project
        from app.tasks.maintenance import expire_project_slugs

        draft = Draft(
            id=uuid.uuid4(),
            owner_id=test_user.id,
            name="Slug Draft",
            wif_filename="slug.wif",
            wif_path="drafts/slug.wif",
        )
        db_session.add(draft)
        await db_session.flush()

        project = Project(
            id=uuid.uuid4(),
            owner_id=test_user.id,
            draft_id=draft.id,
            name="Shared Project",
            project_type="weave",
            total_picks=4,
            share_slug="test-slug-expired",
            share_visibility="public",
            share_expires_at=_ago(days=1),
        )
        db_session.add(project)
        await db_session.commit()

        result = expire_project_slugs.run.__func__(_make_task())
        assert result["revoked"] >= 1

        await db_session.refresh(project)
        assert project.share_slug is None
        assert project.share_visibility == "private"

    @pytest.mark.asyncio
    async def test_preserves_non_expired_slug(self, db_session, test_user):
        from app.models.draft import Draft
        from app.models.project import Project
        from app.tasks.maintenance import expire_project_slugs

        draft = Draft(
            id=uuid.uuid4(),
            owner_id=test_user.id,
            name="Future Draft",
            wif_filename="future.wif",
            wif_path="drafts/future.wif",
        )
        db_session.add(draft)
        await db_session.flush()

        future_time = datetime.now(timezone.utc) + timedelta(days=7)
        project = Project(
            id=uuid.uuid4(),
            owner_id=test_user.id,
            draft_id=draft.id,
            name="Future Shared",
            project_type="weave",
            total_picks=4,
            share_slug="not-yet-expired",
            share_visibility="public",
            share_expires_at=future_time,
        )
        db_session.add(project)
        await db_session.commit()

        result = expire_project_slugs.run.__func__(_make_task())
        assert result["revoked"] == 0

        await db_session.refresh(project)
        assert project.share_slug == "not-yet-expired"


# ---------------------------------------------------------------------------
# check_credential_expiry — exception handler (lines 426-427)
# ---------------------------------------------------------------------------


class TestCheckCredentialExpiryExceptionHandler:
    @pytest.mark.asyncio
    async def test_exception_in_send_alerts_is_caught(self, db_session):
        from app.tasks.maintenance import check_credential_expiry

        _cred(db_session, expires_in_days=5, last_alerted_hours_ago=None)
        await db_session.commit()

        with patch(
            "app.tasks.maintenance._send_credential_alerts",
            side_effect=Exception("network down"),
        ):
            result = check_credential_expiry.run.__func__(_make_task())

        assert result["alerted"] == 0
        assert "skipped" in result


# ---------------------------------------------------------------------------
# prune_inactive_project_tiles — exception handler (lines 745-746)
# ---------------------------------------------------------------------------


class TestPruneInactiveProjectTilesExceptionHandler:
    @pytest.mark.asyncio
    async def test_storage_exception_is_caught(self, db_session, test_user):
        import uuid as _uuid

        import app.services.storage as storage
        from app.models.draft import Draft
        from app.models.project import Project
        from app.tasks.maintenance import prune_inactive_project_tiles

        draft = Draft(
            id=_uuid.uuid4(),
            owner_id=test_user.id,
            name="Draft",
            wif_filename="test.wif",
            wif_path=storage.save_wif(_uuid.uuid4(), "test.wif", b"[WIF]"),
        )
        db_session.add(draft)
        await db_session.flush()
        project = Project(
            owner_id=test_user.id,
            draft_id=draft.id,
            name="Tile Project",
            project_type="treadle",
            status="active",
            current_pick=1,
            total_picks=10,
        )
        db_session.add(project)
        await db_session.commit()

        from sqlalchemy import update as _update

        from app.models.project import Project as _Project

        await db_session.execute(_update(_Project).where(_Project.id == project.id).values(updated_at=_ago(days=20)))
        await db_session.commit()

        with patch("app.services.storage.delete_project_tiles", side_effect=Exception("S3 error")):
            result = prune_inactive_project_tiles.run.__func__(_make_task(), inactive_days=10)

        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# TestDailyHealthCheck — cover lines 185-286
# ---------------------------------------------------------------------------


def _ok_service(name: str = "postgres"):
    from app.routers.health import ReadinessService

    return ReadinessService(name=name, ok=True, critical=True)


def _ok_response():
    from app.routers.health import ReadinessResponse

    return ReadinessResponse(
        status="ok",
        services=[_ok_service("postgres"), _ok_service("s3"), _ok_service("clerk"), _ok_service("smtp")],
        checked_at="2026-01-01T00:00:00+00:00",
    )


class _MockAsyncSession:
    async def __aenter__(self):
        return MagicMock()

    async def __aexit__(self, *_):
        pass  # no cleanup needed


class TestDailyHealthCheck:
    def _run(self, mock_response):
        from app.tasks.maintenance import daily_health_check

        with (
            patch("app.database.AsyncSessionLocal", return_value=_MockAsyncSession()),
            patch("app.routers.admin._probe_postgres", new=AsyncMock(return_value=_ok_service("postgres"))),
            patch("app.routers.admin._probe_s3", new=AsyncMock(return_value=_ok_service("s3"))),
            patch("app.routers.admin._probe_clerk", new=AsyncMock(return_value=_ok_service("clerk"))),
            patch("app.routers.admin._probe_smtp", new=AsyncMock(return_value=_ok_service("smtp"))),
            patch(
                "app.services.clerk_webhook_probe.run_webhook_probe", new=AsyncMock(return_value=_ok_service("webhook"))
            ),
            patch("app.routers.health._build_readiness_from_results", return_value=mock_response),
        ):
            return daily_health_check.run.__func__(_make_task())

    def test_ok_status_returns_dict(self, db_session):
        result = self._run(_ok_response())
        assert result["status"] == "ok"
        assert result["failed_services"] == []

    def test_returns_failed_services_list(self, db_session):
        from app.routers.health import ReadinessResponse, ReadinessService

        degraded_svc = ReadinessService(name="smtp", ok=False, critical=False)
        degraded_response = ReadinessResponse(
            status="degraded",
            services=[_ok_service("postgres"), degraded_svc],
            checked_at="2026-01-01T00:00:00+00:00",
        )

        with patch("app.services.email.send_health_degraded_alert", new=AsyncMock()):
            result = self._run(degraded_response)

        assert result["status"] == "degraded"
        assert "smtp" in result["failed_services"]

    def test_degraded_no_superusers_no_email_sent(self, db_session):
        from app.routers.health import ReadinessResponse, ReadinessService

        degraded_response = ReadinessResponse(
            status="degraded",
            services=[ReadinessService(name="s3", ok=False, critical=False)],
            checked_at="2026-01-01T00:00:00+00:00",
        )

        mock_send = MagicMock()
        with patch("app.services.email.send_health_degraded_alert", mock_send):
            result = self._run(degraded_response)

        mock_send.assert_not_called()
        assert result["status"] == "degraded"

    def test_run_exception_returns_error_status(self):
        # Covers lines 216-217: exception inside _run() → error ReadinessResponse returned
        from app.tasks.maintenance import daily_health_check

        class _RaisingSession:
            async def __aenter__(self):
                raise RuntimeError("db unavailable")

            async def __aexit__(self, *_):
                pass  # no cleanup needed

        with patch("app.database.AsyncSessionLocal", return_value=_RaisingSession()):
            result = daily_health_check.run.__func__(_make_task())

        assert result["status"] == "error"

    def test_degraded_with_superuser_sends_email(self):
        # Covers lines 267-283: superuser in DB + degraded → email send attempted
        from sqlalchemy import create_engine
        from sqlalchemy.orm import Session

        from app.config import get_settings
        from app.models.user import User
        from app.routers.health import ReadinessResponse, ReadinessService

        settings = get_settings()
        engine = create_engine(settings.database_url_sync)
        superuser_id = uuid.uuid4()
        try:
            with Session(engine) as sync_db:
                su = User(
                    id=superuser_id,
                    clerk_user_id=f"user_su_{superuser_id.hex[:8]}",
                    email="su@example.com",
                    display_name="Test Superuser",
                    is_admin=True,
                    is_superuser=True,
                    is_active=True,
                )
                sync_db.add(su)
                sync_db.commit()

            degraded_response = ReadinessResponse(
                status="degraded",
                services=[ReadinessService(name="s3", ok=False, critical=False)],
                checked_at="2026-01-01T00:00:00+00:00",
            )

            mock_send = AsyncMock()
            with patch("app.services.email.send_health_degraded_alert", mock_send):
                result = self._run(degraded_response)

            mock_send.assert_called_once()
            assert result["status"] == "degraded"
        finally:
            from sqlalchemy import delete as _del

            with Session(engine) as sync_db:
                sync_db.execute(_del(User).where(User.id == superuser_id))
                sync_db.commit()
            engine.dispose()

    def test_degraded_with_superuser_email_exception_is_swallowed(self):
        # Covers lines 282-283: email send raises → exception swallowed, status still returned
        from sqlalchemy import create_engine
        from sqlalchemy.orm import Session

        from app.config import get_settings
        from app.models.user import User
        from app.routers.health import ReadinessResponse, ReadinessService

        settings = get_settings()
        engine = create_engine(settings.database_url_sync)
        superuser_id = uuid.uuid4()
        try:
            with Session(engine) as sync_db:
                su = User(
                    id=superuser_id,
                    clerk_user_id=f"user_su_{superuser_id.hex[:8]}",
                    email="su2@example.com",
                    display_name="Test Superuser 2",
                    is_admin=True,
                    is_superuser=True,
                    is_active=True,
                )
                sync_db.add(su)
                sync_db.commit()

            degraded_response = ReadinessResponse(
                status="degraded",
                services=[ReadinessService(name="s3", ok=False, critical=False)],
                checked_at="2026-01-01T00:00:00+00:00",
            )

            mock_send = AsyncMock(side_effect=RuntimeError("SMTP down"))
            with patch("app.services.email.send_health_degraded_alert", mock_send):
                result = self._run(degraded_response)

            assert result["status"] == "degraded"
        finally:
            from sqlalchemy import delete as _del

            with Session(engine) as sync_db:
                sync_db.execute(_del(User).where(User.id == superuser_id))
                sync_db.commit()
            engine.dispose()
