"""Unit tests for admin.py service probe functions.

These test the _probe_* helpers directly rather than via the HTTP endpoint,
covering branches that the high-level TestAdminServices tests cannot reach
because they mock the probes out wholesale.
"""

from unittest.mock import AsyncMock, MagicMock, patch

# ---------------------------------------------------------------------------
# _make_result — failed-checks branch (line 177)
# ---------------------------------------------------------------------------


class TestMakeResult:
    def test_ok_when_no_failures(self):
        from app.routers.admin import ServicePermCheck, _make_result

        checks = [
            ServicePermCheck(name="connect", status="ok", message="ok"),
            ServicePermCheck(name="select", status="ok", message="ok"),
        ]
        result = _make_result("TestSvc", checks)
        assert result.status == "ok"
        assert "2/2" in result.message

    def test_error_when_any_failure(self):
        from app.routers.admin import ServicePermCheck, _make_result

        checks = [
            ServicePermCheck(name="connect", status="ok", message="ok"),
            ServicePermCheck(name="select", status="error", message="not granted"),
        ]
        result = _make_result("TestSvc", checks)
        assert result.status == "error"
        assert "failed" in result.message

    def test_message_pluralises_single_failure(self):
        from app.routers.admin import ServicePermCheck, _make_result

        checks = [ServicePermCheck(name="connect", status="error", message="fail")]
        result = _make_result("TestSvc", checks)
        assert "check failed" in result.message
        assert "checks failed" not in result.message

    def test_message_pluralises_multiple_failures(self):
        from app.routers.admin import ServicePermCheck, _make_result

        checks = [
            ServicePermCheck(name="a", status="error", message="fail"),
            ServicePermCheck(name="b", status="error", message="fail"),
        ]
        result = _make_result("TestSvc", checks)
        assert "checks failed" in result.message


# ---------------------------------------------------------------------------
# _pg_conn_meta — DSN vs individual fields (lines 188-203)
# ---------------------------------------------------------------------------


class TestPgConnMeta:
    def test_uses_individual_fields_when_no_dsn(self, monkeypatch):
        from app.config import get_settings
        from app.routers.admin import _pg_conn_meta

        s = get_settings()
        monkeypatch.setattr(s, "postgres_dsn", "")
        monkeypatch.setattr(s, "postgres_host", "myhost")
        monkeypatch.setattr(s, "postgres_db", "mydb")
        monkeypatch.setattr(s, "postgres_user", "myuser")
        monkeypatch.setattr(s, "postgres_port", 5432)
        result = _pg_conn_meta()
        assert result["host"] == "myhost"
        assert result["database"] == "mydb"

    def test_uses_dsn_when_set(self, monkeypatch):
        from app.config import get_settings
        from app.routers.admin import _pg_conn_meta

        s = get_settings()
        monkeypatch.setattr(s, "postgres_dsn", "postgresql://user:pass@pghost:5432/pgdb")
        result = _pg_conn_meta()
        assert result["host"] == "pghost"
        assert result["database"] == "pgdb"

    def test_pooled_mode_detected(self, monkeypatch):
        from app.config import get_settings
        from app.routers.admin import _pg_conn_meta

        s = get_settings()
        monkeypatch.setattr(s, "postgres_dsn", "postgresql://u:p@db-pooler.neon.tech:5432/mydb")
        result = _pg_conn_meta()
        assert "pooled" in result["mode"]

    def test_local_mode_detected(self, monkeypatch):
        from app.config import get_settings
        from app.routers.admin import _pg_conn_meta

        s = get_settings()
        monkeypatch.setattr(s, "postgres_dsn", "")
        monkeypatch.setattr(s, "postgres_host", "localhost")
        result = _pg_conn_meta()
        assert result["mode"] == "local"

    def test_direct_mode_detected(self, monkeypatch):
        from app.config import get_settings
        from app.routers.admin import _pg_conn_meta

        s = get_settings()
        monkeypatch.setattr(s, "postgres_dsn", "")
        monkeypatch.setattr(s, "postgres_host", "pg.example.com")
        result = _pg_conn_meta()
        assert result["mode"] == "direct"


# ---------------------------------------------------------------------------
# _s3_conn_meta — bucket_owner_account_id branch (lines 274-275)
# ---------------------------------------------------------------------------


class TestS3ConnMeta:
    def test_includes_preconfigured_owner(self, monkeypatch):
        from app.config import get_settings
        from app.routers.admin import _s3_conn_meta

        s = get_settings()
        monkeypatch.setattr(s, "storage_backend", "s3")
        monkeypatch.setattr(s, "s3_bucket_owner_account_id", "111122223333")
        monkeypatch.setattr(s, "s3_bucket_name", "my-bucket")
        monkeypatch.setattr(s, "s3_endpoint_url", "https://r2.example.com")
        monkeypatch.setattr(s, "s3_region", "auto")
        monkeypatch.setattr(s, "s3_access_key_id", "key123")
        result = _s3_conn_meta(s)
        assert result["bucket_owner_account_id"] == "111122223333"

    def test_omits_owner_when_not_configured(self, monkeypatch):
        from app.config import get_settings
        from app.routers.admin import _s3_conn_meta

        s = get_settings()
        monkeypatch.setattr(s, "storage_backend", "s3")
        monkeypatch.setattr(s, "s3_bucket_owner_account_id", "")
        result = _s3_conn_meta(s)
        assert "bucket_owner_account_id" not in result


# ---------------------------------------------------------------------------
# _probe_s3 (lines 277-338)
# ---------------------------------------------------------------------------


class TestProbeS3:
    async def test_local_storage_returns_ok(self, monkeypatch):
        from app.config import get_settings
        from app.routers.admin import _probe_s3

        monkeypatch.setattr(get_settings(), "storage_backend", "local")
        result = await _probe_s3()
        assert result.status == "ok"
        assert result.service == "S3"
        assert any("Local storage" in c.message for c in result.checks)

    async def test_s3_no_bucket_name_returns_error(self, monkeypatch):
        from app.config import get_settings
        from app.routers.admin import _probe_s3

        s = get_settings()
        monkeypatch.setattr(s, "storage_backend", "s3")
        monkeypatch.setattr(s, "s3_bucket_name", "")
        result = await _probe_s3()
        assert result.status == "error"
        assert any("S3_BUCKET_NAME" in c.message for c in result.checks)

    async def test_s3_bucket_accessible_all_checks_pass(self, monkeypatch):
        from app.config import get_settings
        from app.routers.admin import _probe_s3

        s = get_settings()
        monkeypatch.setattr(s, "storage_backend", "s3")
        monkeypatch.setattr(s, "s3_bucket_name", "test-bucket")

        mock_s3 = MagicMock()
        mock_s3.head_bucket.return_value = {}
        mock_s3.list_objects_v2.return_value = {"Contents": []}
        mock_s3.put_object.return_value = {}
        mock_s3.delete_object.return_value = {}

        mock_sts = MagicMock()
        mock_sts.get_caller_identity.return_value = {"Account": "123456789012"}

        def _boto3_client(service, **kwargs):
            return mock_sts if service == "sts" else mock_s3

        with patch("boto3.client", side_effect=_boto3_client):
            result = await _probe_s3()

        assert result.status == "ok"
        names = {c.name for c in result.checks}
        assert "bucket_accessible" in names
        assert "write_delete" in names
        assert result.meta.get("bucket_owner_account_id") == "123456789012"

    async def test_s3_bucket_owner_not_supported_when_sts_fails(self, monkeypatch):
        from app.config import get_settings
        from app.routers.admin import _probe_s3

        s = get_settings()
        monkeypatch.setattr(s, "storage_backend", "s3")
        monkeypatch.setattr(s, "s3_bucket_name", "test-bucket")

        mock_s3 = MagicMock()
        mock_s3.head_bucket.return_value = {}
        mock_s3.list_objects_v2.return_value = {"Contents": []}
        mock_s3.put_object.return_value = {}
        mock_s3.delete_object.return_value = {}

        mock_sts = MagicMock()
        mock_sts.get_caller_identity.side_effect = Exception("InvalidClientTokenId")

        def _boto3_client(service, **kwargs):
            return mock_sts if service == "sts" else mock_s3

        with patch("boto3.client", side_effect=_boto3_client):
            result = await _probe_s3()

        assert result.status == "ok"
        assert result.meta.get("bucket_owner_account_id") == "Not supported"

    async def test_s3_bucket_inaccessible_returns_error(self, monkeypatch):
        from app.config import get_settings
        from app.routers.admin import _probe_s3

        s = get_settings()
        monkeypatch.setattr(s, "storage_backend", "s3")
        monkeypatch.setattr(s, "s3_bucket_name", "bad-bucket")

        mock_client = MagicMock()
        mock_client.head_bucket.side_effect = Exception("NoSuchBucket")

        with patch("boto3.client", return_value=mock_client):
            result = await _probe_s3()

        assert result.status == "error"
        ba = next(c for c in result.checks if c.name == "bucket_accessible")
        assert ba.status == "error"

    async def test_s3_timeout_returns_error(self, monkeypatch):
        import asyncio

        from app.config import get_settings
        from app.routers.admin import _probe_s3

        s = get_settings()
        monkeypatch.setattr(s, "storage_backend", "s3")
        monkeypatch.setattr(s, "s3_bucket_name", "test-bucket")

        with patch("asyncio.wait_for", side_effect=asyncio.TimeoutError):
            result = await _probe_s3()

        assert result.status == "error"
        assert any(c.name == "connect" for c in result.checks)

    async def test_s3_preconfigured_owner_not_overwritten_by_sts(self, monkeypatch):
        from app.config import get_settings
        from app.routers.admin import _probe_s3

        s = get_settings()
        monkeypatch.setattr(s, "storage_backend", "s3")
        monkeypatch.setattr(s, "s3_bucket_name", "test-bucket")
        monkeypatch.setattr(s, "s3_bucket_owner_account_id", "111122223333")

        mock_s3 = MagicMock()
        mock_s3.head_bucket.return_value = {}
        mock_s3.list_objects_v2.return_value = {"Contents": []}
        mock_s3.put_object.return_value = {}
        mock_s3.delete_object.return_value = {}

        mock_sts = MagicMock()
        mock_sts.get_caller_identity.return_value = {"Account": "999888777666"}

        def _boto3_client(service, **kwargs):
            return mock_sts if service == "sts" else mock_s3

        with patch("boto3.client", side_effect=_boto3_client):
            result = await _probe_s3()

        # Pre-configured value from settings wins; STS-detected value is not injected
        assert result.meta.get("bucket_owner_account_id") == "111122223333"


# ---------------------------------------------------------------------------
# _probe_clerk (lines 349-405)
# ---------------------------------------------------------------------------


class TestProbeClerk:
    async def test_no_secret_key_shows_error_for_api_auth(self, monkeypatch):
        from app.config import get_settings
        from app.routers.admin import _probe_clerk

        s = get_settings()
        monkeypatch.setattr(s, "clerk_secret_key", "")
        monkeypatch.setattr(s, "clerk_publishable_key", "")
        monkeypatch.setattr(s, "clerk_webhook_secret", "")
        result = await _probe_clerk()
        api_check = next((c for c in result.checks if c.name == "api_auth"), None)
        assert api_check is not None
        assert api_check.status == "error"

    async def test_valid_sk_format_passes_secret_key_check(self, monkeypatch):
        from app.config import get_settings
        from app.routers.admin import _probe_clerk

        s = get_settings()
        monkeypatch.setattr(s, "clerk_secret_key", "sk_test_abcdefghijklmno")
        monkeypatch.setattr(s, "clerk_publishable_key", "pk_test_xyz")
        monkeypatch.setattr(s, "clerk_webhook_secret", "whsec_abc123")

        with patch("httpx.AsyncClient") as mock_cls:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_inst = AsyncMock()
            mock_inst.get = AsyncMock(return_value=mock_resp)
            mock_inst.__aenter__ = AsyncMock(return_value=mock_inst)
            mock_inst.__aexit__ = AsyncMock(return_value=None)
            mock_cls.return_value = mock_inst
            result = await _probe_clerk()

        sk_check = next(c for c in result.checks if c.name == "secret_key")
        assert sk_check.status == "ok"
        api_check = next(c for c in result.checks if c.name == "api_auth")
        assert api_check.status == "ok"

    async def test_clerk_api_returns_non_200_shows_error(self, monkeypatch):
        from app.config import get_settings
        from app.routers.admin import _probe_clerk

        s = get_settings()
        monkeypatch.setattr(s, "clerk_secret_key", "sk_test_xyz")
        monkeypatch.setattr(s, "clerk_publishable_key", "pk_test_abc")
        monkeypatch.setattr(s, "clerk_webhook_secret", "whsec_xxx")

        with patch("httpx.AsyncClient") as mock_cls:
            mock_resp = MagicMock()
            mock_resp.status_code = 401
            mock_inst = AsyncMock()
            mock_inst.get = AsyncMock(return_value=mock_resp)
            mock_inst.__aenter__ = AsyncMock(return_value=mock_inst)
            mock_inst.__aexit__ = AsyncMock(return_value=None)
            mock_cls.return_value = mock_inst
            result = await _probe_clerk()

        api_check = next(c for c in result.checks if c.name == "api_auth")
        assert api_check.status == "error"
        assert "401" in api_check.message

    async def test_clerk_live_key_detected_in_meta(self, monkeypatch):
        from app.config import get_settings
        from app.routers.admin import _probe_clerk

        s = get_settings()
        monkeypatch.setattr(s, "clerk_secret_key", "sk_live_abcdefghijklmno")
        monkeypatch.setattr(s, "clerk_publishable_key", "pk_live_xyz")
        monkeypatch.setattr(s, "clerk_webhook_secret", "whsec_abc")

        with patch("httpx.AsyncClient") as mock_cls:
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            mock_inst = AsyncMock()
            mock_inst.get = AsyncMock(return_value=mock_resp)
            mock_inst.__aenter__ = AsyncMock(return_value=mock_inst)
            mock_inst.__aexit__ = AsyncMock(return_value=None)
            mock_cls.return_value = mock_inst
            result = await _probe_clerk()

        assert result.meta.get("environment") == "live"

    async def test_clerk_timeout_returns_error(self, monkeypatch):
        import httpx

        from app.config import get_settings
        from app.routers.admin import _probe_clerk

        s = get_settings()
        monkeypatch.setattr(s, "clerk_secret_key", "sk_test_xyz")
        monkeypatch.setattr(s, "clerk_publishable_key", "pk_test_abc")
        monkeypatch.setattr(s, "clerk_webhook_secret", "whsec_xxx")

        with patch("httpx.AsyncClient") as mock_cls:
            mock_inst = AsyncMock()
            mock_inst.get = AsyncMock(side_effect=httpx.TimeoutException("timeout"))
            mock_inst.__aenter__ = AsyncMock(return_value=mock_inst)
            mock_inst.__aexit__ = AsyncMock(return_value=None)
            mock_cls.return_value = mock_inst
            result = await _probe_clerk()

        api_check = next(c for c in result.checks if c.name == "api_auth")
        assert api_check.status == "error"
        assert "Timed out" in api_check.message


# ---------------------------------------------------------------------------
# _probe_smtp (lines 917-949)
# ---------------------------------------------------------------------------


class TestProbeSMTP:
    async def test_no_smtp_host_returns_not_configured(self, monkeypatch):
        from app.config import get_settings
        from app.routers.admin import _probe_smtp

        s = get_settings()
        monkeypatch.setattr(s, "smtp_host", "")
        result = await _probe_smtp()
        assert result.status == "error"
        assert any("not configured" in c.message for c in result.checks)

    async def test_missing_smtp_fields_returns_error(self, monkeypatch):
        from app.config import get_settings
        from app.routers.admin import _probe_smtp

        s = get_settings()
        monkeypatch.setattr(s, "smtp_host", "smtp.example.com")
        monkeypatch.setattr(s, "smtp_user", "")
        monkeypatch.setattr(s, "smtp_password", "")
        monkeypatch.setattr(s, "smtp_from_email", "")
        result = await _probe_smtp()
        assert result.status == "error"
        assert any("Missing" in c.message for c in result.checks)

    async def test_smtp_fully_configured_calls_tcp_check(self, monkeypatch):
        from app.config import get_settings
        from app.routers.admin import _probe_smtp

        s = get_settings()
        monkeypatch.setattr(s, "smtp_host", "smtp.example.com")
        monkeypatch.setattr(s, "smtp_port", 587)
        monkeypatch.setattr(s, "smtp_user", "user@example.com")
        monkeypatch.setattr(s, "smtp_password", "pass")
        monkeypatch.setattr(s, "smtp_from_email", "noreply@example.com")

        with patch("app.services.smtp_health.check", new_callable=AsyncMock, return_value=(True, "OK")):
            result = await _probe_smtp()

        tcp = next(c for c in result.checks if c.name == "tcp")
        assert tcp.status == "ok"

    async def test_smtp_tcp_failure_returns_error(self, monkeypatch):
        from app.config import get_settings
        from app.routers.admin import _probe_smtp

        s = get_settings()
        monkeypatch.setattr(s, "smtp_host", "bad-smtp.example.com")
        monkeypatch.setattr(s, "smtp_port", 587)
        monkeypatch.setattr(s, "smtp_user", "user@example.com")
        monkeypatch.setattr(s, "smtp_password", "pass")
        monkeypatch.setattr(s, "smtp_from_email", "noreply@example.com")

        with patch(
            "app.services.smtp_health.check", new_callable=AsyncMock, return_value=(False, "Connection refused")
        ):
            result = await _probe_smtp()

        tcp = next(c for c in result.checks if c.name == "tcp")
        assert tcp.status == "error"


# ---------------------------------------------------------------------------
# _probe_webhook_info — CF Zero Trust enabled path (lines 967, 972-988)
# ---------------------------------------------------------------------------


class TestProbeWebhookInfo:
    def test_cf_disabled_returns_ok_check(self, monkeypatch):
        from app.config import get_settings
        from app.routers.admin import _probe_webhook_info

        s = get_settings()
        monkeypatch.setattr(s, "cf_zero_trust_enabled", False)
        monkeypatch.setattr(s, "clerk_webhook_secret", "whsec_abc")
        result = _probe_webhook_info()
        cf = next(c for c in result.checks if c.name == "cf_access")
        assert cf.message == "Disabled"

    def test_webhook_secret_missing_returns_error(self, monkeypatch):
        from app.config import get_settings
        from app.routers.admin import _probe_webhook_info

        s = get_settings()
        monkeypatch.setattr(s, "cf_zero_trust_enabled", False)
        monkeypatch.setattr(s, "clerk_webhook_secret", "")
        result = _probe_webhook_info()
        secret = next(c for c in result.checks if c.name == "secret")
        assert secret.status == "error"

    def test_cf_enabled_with_credentials_shows_ok(self, monkeypatch):
        from app.config import get_settings
        from app.routers.admin import _probe_webhook_info

        s = get_settings()
        monkeypatch.setattr(s, "clerk_webhook_secret", "whsec_abc")
        monkeypatch.setattr(s, "cf_zero_trust_enabled", True)
        monkeypatch.setattr(s, "cf_access_client_id", "abc.access.example.com")
        monkeypatch.setattr(s, "cf_access_client_secret", "super-long-secret-value")
        result = _probe_webhook_info()
        cf = next(c for c in result.checks if c.name == "cf_access")
        assert cf.status == "ok"
        assert "Enabled" in cf.message

    def test_cf_enabled_missing_client_id_shows_error(self, monkeypatch):
        from app.config import get_settings
        from app.routers.admin import _probe_webhook_info

        s = get_settings()
        monkeypatch.setattr(s, "clerk_webhook_secret", "whsec_abc")
        monkeypatch.setattr(s, "cf_zero_trust_enabled", True)
        monkeypatch.setattr(s, "cf_access_client_id", "")
        monkeypatch.setattr(s, "cf_access_client_secret", "secret")
        result = _probe_webhook_info()
        cid = next(c for c in result.checks if c.name == "cf_client_id")
        assert cid.status == "error"

    def test_cf_enabled_missing_client_secret_shows_error(self, monkeypatch):
        from app.config import get_settings
        from app.routers.admin import _probe_webhook_info

        s = get_settings()
        monkeypatch.setattr(s, "clerk_webhook_secret", "whsec_abc")
        monkeypatch.setattr(s, "cf_zero_trust_enabled", True)
        monkeypatch.setattr(s, "cf_access_client_id", "abc.example.com")
        monkeypatch.setattr(s, "cf_access_client_secret", "")
        result = _probe_webhook_info()
        cs = next(c for c in result.checks if c.name == "cf_client_secret")
        assert cs.status == "error"


# ---------------------------------------------------------------------------
# approve_pending_signup — already_exists branch (lines 1308-1310)
# — pre_created branch (lines 1317-1321)
# — invite revocation (line 1343)
# — email exception handlers (lines 1362-1363, 1370-1371)
# ---------------------------------------------------------------------------


class TestApprovePendingSignupBranches:
    async def _make_signup(self, db_session, clerk_user_id="clerk_test_123", email="test@example.com"):
        from app.models.pending_signup import PendingSignup

        signup = PendingSignup(
            clerk_user_id=clerk_user_id,
            email=email,
            display_name="Test User",
        )
        db_session.add(signup)
        await db_session.commit()
        return signup

    async def test_already_exists_returns_status(self, admin_client, db_session, admin_user):
        import uuid

        from app.models.user import User

        clerk_id = f"clerk_existing_{uuid.uuid4().hex[:8]}"
        email = f"existing-{uuid.uuid4().hex[:8]}@example.com"

        existing_user = User(
            email=email,
            display_name="Existing User",
            clerk_user_id=clerk_id,
            is_admin=False,
        )
        db_session.add(existing_user)
        await db_session.commit()

        signup = await self._make_signup(db_session, clerk_user_id=clerk_id, email=email)

        with (
            patch("app.routers.admin.set_user_metadata", new_callable=AsyncMock),
            patch("app.routers.admin.send_account_approved_email", new_callable=AsyncMock),
            patch("app.routers.admin.send_approval_confirmation_to_admins", new_callable=AsyncMock),
        ):
            resp = await admin_client.post(f"/api/admin/pending-signups/{signup.id}/approve")

        assert resp.status_code in (200, 201)
        assert resp.json()["status"] == "already_exists"

    async def test_pre_created_user_linked_on_approve(self, admin_client, db_session, admin_user):
        import uuid

        from app.models.user import User

        clerk_id = f"clerk_new_{uuid.uuid4().hex[:8]}"
        email = f"pre-{uuid.uuid4().hex[:8]}@example.com"

        pre_created = User(
            email=email,
            display_name="Pre-created",
            clerk_user_id=None,
            is_admin=False,
        )
        db_session.add(pre_created)
        await db_session.commit()

        signup = await self._make_signup(db_session, clerk_user_id=clerk_id, email=email)

        with (
            patch("app.routers.admin.set_user_metadata", new_callable=AsyncMock),
            patch("app.routers.admin.send_account_approved_email", new_callable=AsyncMock),
            patch("app.routers.admin.send_approval_confirmation_to_admins", new_callable=AsyncMock),
        ):
            resp = await admin_client.post(f"/api/admin/pending-signups/{signup.id}/approve")

        assert resp.status_code in (200, 201)
        await db_session.refresh(pre_created)
        assert pre_created.clerk_user_id == clerk_id

    async def test_email_exception_does_not_fail_approval(self, admin_client, db_session, admin_user):
        import uuid

        clerk_id = f"clerk_email_err_{uuid.uuid4().hex[:8]}"
        email = f"email-err-{uuid.uuid4().hex[:8]}@example.com"
        signup = await self._make_signup(db_session, clerk_user_id=clerk_id, email=email)

        with (
            patch("app.routers.admin.set_user_metadata", new_callable=AsyncMock),
            patch("app.routers.admin.send_account_approved_email", side_effect=Exception("SMTP down")),
            patch("app.routers.admin.send_approval_confirmation_to_admins", side_effect=Exception("SMTP down")),
        ):
            resp = await admin_client.post(f"/api/admin/pending-signups/{signup.id}/approve")

        assert resp.status_code in (200, 201)

    async def test_pending_invite_revoked_on_approve(self, admin_client, db_session, admin_user):
        import uuid
        from datetime import datetime as _dt
        from datetime import timedelta, timezone

        from app.models.invite import Invite

        clerk_id = f"clerk_inv_{uuid.uuid4().hex[:8]}"
        email = f"invite-{uuid.uuid4().hex[:8]}@example.com"

        invite = Invite(
            email=email,
            token=f"tok-{uuid.uuid4().hex}",
            expires_at=_dt.now(timezone.utc) + timedelta(days=7),
            created_by_id=admin_user.id,
        )
        db_session.add(invite)
        await db_session.commit()

        signup = await self._make_signup(db_session, clerk_user_id=clerk_id, email=email)

        with (
            patch("app.routers.admin.set_user_metadata", new_callable=AsyncMock),
            patch("app.routers.admin.send_account_approved_email", new_callable=AsyncMock),
            patch("app.routers.admin.send_approval_confirmation_to_admins", new_callable=AsyncMock),
        ):
            await admin_client.post(f"/api/admin/pending-signups/{signup.id}/approve")

        await db_session.refresh(invite)
        assert invite.revoked_at is not None


# ---------------------------------------------------------------------------
# _test_smtp — config connection tester (lines 2858-2878)
# ---------------------------------------------------------------------------


class TestConfigServiceSMTP:
    async def test_missing_credentials_returns_error(self):
        from app.routers.admin import _test_smtp

        result = await _test_smtp({"smtp_user": "", "smtp_password": ""})
        assert result.ok is False
        assert "required" in result.message

    async def test_connect_success_returns_ok(self):

        from app.routers.admin import _test_smtp

        mock_smtp = MagicMock()
        mock_smtp.__enter__ = MagicMock(return_value=mock_smtp)
        mock_smtp.__exit__ = MagicMock(return_value=False)

        with patch("smtplib.SMTP", return_value=mock_smtp):
            result = await _test_smtp(
                {
                    "smtp_host": "smtp.example.com",
                    "smtp_port": "587",
                    "smtp_user": "user@example.com",
                    "smtp_password": "secret",
                }
            )

        assert result.ok is True
        assert "Connected" in result.message

    async def test_connect_failure_returns_error(self):
        from app.routers.admin import _test_smtp

        with patch("smtplib.SMTP", side_effect=ConnectionRefusedError("refused")):
            result = await _test_smtp(
                {
                    "smtp_host": "smtp.example.com",
                    "smtp_port": "587",
                    "smtp_user": "user@example.com",
                    "smtp_password": "secret",
                }
            )

        assert result.ok is False
        assert "refused" in result.message
