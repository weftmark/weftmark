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
