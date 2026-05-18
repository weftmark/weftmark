"""Tests for app.tasks.scheduler dispatch functions.

Each _dispatch_* function is tested by mocking the Celery task's .delay()
method and record_queued so no real Celery worker or DB connection is needed.
"""

from unittest.mock import MagicMock, patch

from app.tasks.scheduler import (
    DISPATCH_FNS,
    REGISTRY,
    _dispatch_admin_digest,
    _dispatch_audit_log_pruning,
    _dispatch_credential_expiry_check,
    _dispatch_cve_scan,
    _dispatch_daily_health_check,
    _dispatch_feedback_purge,
    _dispatch_feedback_retry,
    _dispatch_heartbeat,
    _dispatch_invite_pruning,
    _dispatch_preview_retry,
    _dispatch_s3_audit,
    _dispatch_server_event_log_pruning,
    _dispatch_stale_signup_dismissal,
    _dispatch_tile_prune,
)


def _fake_settings():
    from app.config import get_settings

    return get_settings()


def _mock_task():
    """Return a mock task object with a mock .delay() that returns a stub result."""
    m = MagicMock()
    m.delay.return_value = MagicMock(id="task-id-123")
    return m


# ---------------------------------------------------------------------------
# REGISTRY sanity
# ---------------------------------------------------------------------------


class TestRegistry:
    def test_all_registry_keys_have_dispatch_fn(self):
        for slug in REGISTRY:
            assert slug in DISPATCH_FNS, f"no dispatch function for registry slug: {slug}"

    def test_all_dispatch_fns_in_registry(self):
        for slug in DISPATCH_FNS:
            assert slug in REGISTRY, f"dispatch function '{slug}' not in REGISTRY"

    def test_each_registry_entry_has_required_fields(self):
        for slug, entry in REGISTRY.items():
            assert "display_name" in entry, slug
            assert "default_cron" in entry, slug
            assert "default_config" in entry, slug


# ---------------------------------------------------------------------------
# _dispatch_cve_scan
# ---------------------------------------------------------------------------


class TestDispatchCveScan:
    def test_calls_delay(self):
        mock_task = _mock_task()
        with (
            patch("app.tasks.cve_scan.run_cve_scan", mock_task),
            patch("app.services.task_history.record_queued"),
        ):
            result = _dispatch_cve_scan(_fake_settings())
        mock_task.delay.assert_called_once()
        assert result is mock_task.delay.return_value

    def test_records_queued(self):
        mock_task = _mock_task()
        with (
            patch("app.tasks.cve_scan.run_cve_scan", mock_task),
            patch("app.services.task_history.record_queued") as mock_rq,
        ):
            _dispatch_cve_scan(_fake_settings())
        mock_rq.assert_called_once()
        args = mock_rq.call_args[0]
        assert "cve_scan" in args[2]


# ---------------------------------------------------------------------------
# _dispatch_s3_audit
# ---------------------------------------------------------------------------


class TestDispatchS3Audit:
    def test_calls_delay(self):
        mock_task = _mock_task()
        with (
            patch("app.tasks.s3_audit.run_s3_orphan_scan", mock_task),
            patch("app.services.task_history.record_queued"),
        ):
            result = _dispatch_s3_audit(_fake_settings())
        mock_task.delay.assert_called_once()
        assert result is mock_task.delay.return_value

    def test_records_queued(self):
        mock_task = _mock_task()
        with (
            patch("app.tasks.s3_audit.run_s3_orphan_scan", mock_task),
            patch("app.services.task_history.record_queued") as mock_rq,
        ):
            _dispatch_s3_audit(_fake_settings())
        mock_rq.assert_called_once()


# ---------------------------------------------------------------------------
# _dispatch_stale_signup_dismissal
# ---------------------------------------------------------------------------


class TestDispatchStaleSignupDismissal:
    def test_calls_delay_with_default_days(self):
        mock_task = _mock_task()
        with (
            patch("app.tasks.maintenance.dismiss_stale_signups", mock_task),
            patch("app.services.task_history.record_queued"),
        ):
            _dispatch_stale_signup_dismissal(_fake_settings(), task=None)
        mock_task.delay.assert_called_once_with(days=30)

    def test_reads_config_days(self):
        mock_task = _mock_task()
        fake_task = MagicMock()
        fake_task.config = {"days": "45"}
        with (
            patch("app.tasks.maintenance.dismiss_stale_signups", mock_task),
            patch("app.services.task_history.record_queued"),
        ):
            _dispatch_stale_signup_dismissal(_fake_settings(), task=fake_task)
        mock_task.delay.assert_called_once_with(days=45)

    def test_records_queued(self):
        mock_task = _mock_task()
        with (
            patch("app.tasks.maintenance.dismiss_stale_signups", mock_task),
            patch("app.services.task_history.record_queued") as mock_rq,
        ):
            _dispatch_stale_signup_dismissal(_fake_settings())
        mock_rq.assert_called_once()


# ---------------------------------------------------------------------------
# _dispatch_invite_pruning
# ---------------------------------------------------------------------------


class TestDispatchInvitePruning:
    def test_calls_delay_with_default_retention(self):
        mock_task = _mock_task()
        with (
            patch("app.tasks.maintenance.prune_expired_invites", mock_task),
            patch("app.services.task_history.record_queued"),
        ):
            _dispatch_invite_pruning(_fake_settings(), task=None)
        mock_task.delay.assert_called_once_with(retention_days=90)

    def test_reads_config_retention_days(self):
        mock_task = _mock_task()
        fake_task = MagicMock()
        fake_task.config = {"retention_days": "60"}
        with (
            patch("app.tasks.maintenance.prune_expired_invites", mock_task),
            patch("app.services.task_history.record_queued"),
        ):
            _dispatch_invite_pruning(_fake_settings(), task=fake_task)
        mock_task.delay.assert_called_once_with(retention_days=60)


# ---------------------------------------------------------------------------
# _dispatch_audit_log_pruning
# ---------------------------------------------------------------------------


class TestDispatchAuditLogPruning:
    def test_calls_delay_with_default_retention(self):
        mock_task = _mock_task()
        with (
            patch("app.tasks.maintenance.prune_audit_log", mock_task),
            patch("app.services.task_history.record_queued"),
        ):
            _dispatch_audit_log_pruning(_fake_settings(), task=None)
        mock_task.delay.assert_called_once_with(retention_days=90)

    def test_reads_config(self):
        mock_task = _mock_task()
        fake_task = MagicMock()
        fake_task.config = {"retention_days": "30"}
        with (
            patch("app.tasks.maintenance.prune_audit_log", mock_task),
            patch("app.services.task_history.record_queued"),
        ):
            _dispatch_audit_log_pruning(_fake_settings(), task=fake_task)
        mock_task.delay.assert_called_once_with(retention_days=30)


# ---------------------------------------------------------------------------
# _dispatch_heartbeat
# ---------------------------------------------------------------------------


class TestDispatchHeartbeat:
    def test_calls_delay(self):
        mock_task = _mock_task()
        with (
            patch("app.tasks.maintenance.worker_heartbeat", mock_task),
            patch("app.services.task_history.record_queued"),
        ):
            result = _dispatch_heartbeat(_fake_settings())
        mock_task.delay.assert_called_once()
        assert result is mock_task.delay.return_value


# ---------------------------------------------------------------------------
# _dispatch_preview_retry
# ---------------------------------------------------------------------------


class TestDispatchPreviewRetry:
    def test_calls_delay_with_default_limit(self):
        mock_task = _mock_task()
        with (
            patch("app.tasks.maintenance.retry_failed_previews", mock_task),
            patch("app.services.task_history.record_queued"),
        ):
            _dispatch_preview_retry(_fake_settings(), task=None)
        mock_task.delay.assert_called_once_with(limit=50)

    def test_reads_config_limit(self):
        mock_task = _mock_task()
        fake_task = MagicMock()
        fake_task.config = {"limit": "25"}
        with (
            patch("app.tasks.maintenance.retry_failed_previews", mock_task),
            patch("app.services.task_history.record_queued"),
        ):
            _dispatch_preview_retry(_fake_settings(), task=fake_task)
        mock_task.delay.assert_called_once_with(limit=25)


# ---------------------------------------------------------------------------
# _dispatch_daily_health_check
# ---------------------------------------------------------------------------


class TestDispatchDailyHealthCheck:
    def test_calls_delay(self):
        mock_task = _mock_task()
        with (
            patch("app.tasks.maintenance.daily_health_check", mock_task),
            patch("app.services.task_history.record_queued"),
        ):
            result = _dispatch_daily_health_check(_fake_settings())
        mock_task.delay.assert_called_once()
        assert result is mock_task.delay.return_value


# ---------------------------------------------------------------------------
# _dispatch_server_event_log_pruning
# ---------------------------------------------------------------------------


class TestDispatchServerEventLogPruning:
    def test_calls_delay_with_defaults(self):
        mock_task = _mock_task()
        with (
            patch("app.tasks.maintenance.prune_server_event_log", mock_task),
            patch("app.services.task_history.record_queued"),
        ):
            _dispatch_server_event_log_pruning(_fake_settings(), task=None)
        mock_task.delay.assert_called_once_with(max_age_days=28, max_entries=1000)

    def test_reads_config(self):
        mock_task = _mock_task()
        fake_task = MagicMock()
        fake_task.config = {"max_age_days": "14", "max_entries": "500"}
        with (
            patch("app.tasks.maintenance.prune_server_event_log", mock_task),
            patch("app.services.task_history.record_queued"),
        ):
            _dispatch_server_event_log_pruning(_fake_settings(), task=fake_task)
        mock_task.delay.assert_called_once_with(max_age_days=14, max_entries=500)


# ---------------------------------------------------------------------------
# _dispatch_credential_expiry_check
# ---------------------------------------------------------------------------


class TestDispatchCredentialExpiryCheck:
    def test_calls_delay(self):
        mock_task = _mock_task()
        with (
            patch("app.tasks.maintenance.check_credential_expiry", mock_task),
            patch("app.services.task_history.record_queued"),
        ):
            result = _dispatch_credential_expiry_check(_fake_settings())
        mock_task.delay.assert_called_once()
        assert result is mock_task.delay.return_value

    def test_records_queued(self):
        mock_task = _mock_task()
        with (
            patch("app.tasks.maintenance.check_credential_expiry", mock_task),
            patch("app.services.task_history.record_queued") as mock_rq,
        ):
            _dispatch_credential_expiry_check(_fake_settings())
        mock_rq.assert_called_once()


# ---------------------------------------------------------------------------
# _dispatch_admin_digest
# ---------------------------------------------------------------------------


class TestDispatchAdminDigest:
    def test_calls_delay(self):
        mock_task = _mock_task()
        with (
            patch("app.tasks.maintenance.send_admin_digest", mock_task),
            patch("app.services.task_history.record_queued"),
        ):
            result = _dispatch_admin_digest(_fake_settings())
        mock_task.delay.assert_called_once()
        assert result is mock_task.delay.return_value


# ---------------------------------------------------------------------------
# _dispatch_tile_prune
# ---------------------------------------------------------------------------


class TestDispatchTilePrune:
    def test_calls_delay_with_default_inactive_days(self):
        mock_task = _mock_task()
        with (
            patch("app.tasks.maintenance.prune_inactive_project_tiles", mock_task),
            patch("app.services.task_history.record_queued"),
        ):
            _dispatch_tile_prune(_fake_settings(), task=None)
        mock_task.delay.assert_called_once_with(inactive_days=10)

    def test_reads_config_inactive_days(self):
        mock_task = _mock_task()
        fake_task = MagicMock()
        fake_task.config = {"inactive_days": "5"}
        with (
            patch("app.tasks.maintenance.prune_inactive_project_tiles", mock_task),
            patch("app.services.task_history.record_queued"),
        ):
            _dispatch_tile_prune(_fake_settings(), task=fake_task)
        mock_task.delay.assert_called_once_with(inactive_days=5)


# ---------------------------------------------------------------------------
# _dispatch_feedback_retry
# ---------------------------------------------------------------------------


class TestDispatchFeedbackRetry:
    def test_calls_delay_with_default_limit(self):
        mock_task = _mock_task()
        with (
            patch("app.tasks.feedback_dispatch.retry_failed_feedback", mock_task),
            patch("app.services.task_history.record_queued"),
        ):
            _dispatch_feedback_retry(_fake_settings(), task=None)
        mock_task.delay.assert_called_once_with(limit=20)

    def test_reads_config_limit(self):
        mock_task = _mock_task()
        fake_task = MagicMock()
        fake_task.config = {"limit": "10"}
        with (
            patch("app.tasks.feedback_dispatch.retry_failed_feedback", mock_task),
            patch("app.services.task_history.record_queued"),
        ):
            _dispatch_feedback_retry(_fake_settings(), task=fake_task)
        mock_task.delay.assert_called_once_with(limit=10)


# ---------------------------------------------------------------------------
# _dispatch_feedback_purge
# ---------------------------------------------------------------------------


class TestDispatchFeedbackPurge:
    def test_calls_delay_with_default_retention(self):
        mock_task = _mock_task()
        with (
            patch("app.tasks.feedback_dispatch.purge_deleted_feedback", mock_task),
            patch("app.services.task_history.record_queued"),
        ):
            _dispatch_feedback_purge(_fake_settings(), task=None)
        mock_task.delay.assert_called_once_with(retention_days=7)

    def test_reads_config_retention_days(self):
        mock_task = _mock_task()
        fake_task = MagicMock()
        fake_task.config = {"retention_days": "14"}
        with (
            patch("app.tasks.feedback_dispatch.purge_deleted_feedback", mock_task),
            patch("app.services.task_history.record_queued"),
        ):
            _dispatch_feedback_purge(_fake_settings(), task=fake_task)
        mock_task.delay.assert_called_once_with(retention_days=14)


# ---------------------------------------------------------------------------
# TestRunScheduledTasks — the main orchestrator task
# ---------------------------------------------------------------------------


def _mock_sync_session(tasks=None):
    db = MagicMock()
    db.scalars.return_value.all.return_value = tasks or []
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=db)
    ctx.__exit__ = MagicMock(return_value=False)
    Session_cls = MagicMock(return_value=ctx)
    engine = MagicMock()
    engine.dispose = MagicMock()
    create_engine = MagicMock(return_value=engine)
    return create_engine, Session_cls, engine, db


class TestRunScheduledTasks:
    def test_runs_cleanly_with_no_tasks(self):
        from app.tasks.scheduler import run_scheduled_tasks

        create_engine, Session_cls, engine, _db = _mock_sync_session([])
        settings = MagicMock()
        settings.database_url_sync = "postgresql://test/test"

        with (
            patch("sqlalchemy.create_engine", create_engine),
            patch("sqlalchemy.orm.Session", Session_cls),
            patch("app.config.get_settings", return_value=settings),
        ):
            run_scheduled_tasks()

        engine.dispose.assert_called_once()

    def test_does_not_raise_when_db_unavailable(self):
        from app.tasks.scheduler import run_scheduled_tasks

        settings = MagicMock()
        settings.database_url_sync = "postgresql://test/test"

        with (
            patch("sqlalchemy.create_engine", side_effect=Exception("db unreachable")),
            patch("app.config.get_settings", return_value=settings),
        ):
            run_scheduled_tasks()  # exception is swallowed

    def test_fires_enabled_task_within_window(self):
        from app.tasks.scheduler import run_scheduled_tasks

        task_obj = MagicMock()
        task_obj.name = "heartbeat"
        task_obj.cron = "* * * * *"  # every minute — always in the 70-sec window

        dispatch_fn = MagicMock()
        create_engine, Session_cls, engine, _db = _mock_sync_session([task_obj])
        settings = MagicMock()
        settings.database_url_sync = "postgresql://test/test"

        with (
            patch("sqlalchemy.create_engine", create_engine),
            patch("sqlalchemy.orm.Session", Session_cls),
            patch("app.config.get_settings", return_value=settings),
            patch("app.tasks.scheduler.DISPATCH_FNS", {"heartbeat": dispatch_fn}),
        ):
            run_scheduled_tasks()

        dispatch_fn.assert_called_once()

    def test_commits_when_tasks_fired(self):
        from app.tasks.scheduler import run_scheduled_tasks

        task_obj = MagicMock()
        task_obj.name = "heartbeat"
        task_obj.cron = "* * * * *"

        dispatch_fn = MagicMock()
        create_engine, Session_cls, engine, db = _mock_sync_session([task_obj])
        settings = MagicMock()
        settings.database_url_sync = "postgresql://test/test"

        with (
            patch("sqlalchemy.create_engine", create_engine),
            patch("sqlalchemy.orm.Session", Session_cls),
            patch("app.config.get_settings", return_value=settings),
            patch("app.tasks.scheduler.DISPATCH_FNS", {"heartbeat": dispatch_fn}),
        ):
            run_scheduled_tasks()

        db.commit.assert_called_once()

    def test_handles_unknown_task_name_gracefully(self):
        from app.tasks.scheduler import run_scheduled_tasks

        task_obj = MagicMock()
        task_obj.name = "unknown_task"
        task_obj.cron = "* * * * *"

        create_engine, Session_cls, engine, _db = _mock_sync_session([task_obj])
        settings = MagicMock()
        settings.database_url_sync = "postgresql://test/test"

        with (
            patch("sqlalchemy.create_engine", create_engine),
            patch("sqlalchemy.orm.Session", Session_cls),
            patch("app.config.get_settings", return_value=settings),
            patch("app.tasks.scheduler.DISPATCH_FNS", {}),
        ):
            run_scheduled_tasks()  # must not raise
