"""Tests for the DB-backed and OAuth-setup Ravelry endpoints (#963).

Covers /status, /connection (disconnect), /authorize, and the OAuth
/callback success path — previously untested despite the well-covered
stash-push (#903) and sync-stash (#1063) endpoints in this same router.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models.ravelry import RavelryCredential, RavelryOAuthState
from app.models.user import User

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_credential(user: User, **overrides) -> RavelryCredential:
    defaults = {
        "id": uuid.uuid4(),
        "user_id": user.id,
        "ravelry_username": "testweaver",
        "access_token": "fake-token",
        "refresh_token": None,
        "expires_at": None,
    }
    defaults.update(overrides)
    return RavelryCredential(**defaults)


# ---------------------------------------------------------------------------
# TestStatus
# ---------------------------------------------------------------------------


class TestStatus:
    async def test_returns_not_connected_without_credential(self, auth_client: AsyncClient):
        resp = await auth_client.get("/api/ravelry/status")
        assert resp.status_code == 200
        body = resp.json()
        assert body["connected"] is False
        assert body["ravelry_username"] is None
        assert body["last_synced_at"] is None

    async def test_returns_connected_with_username_and_last_synced(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        synced_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        cred = _make_credential(test_user, ravelry_username="weaverjane", stash_last_synced_at=synced_at)
        db_session.add(cred)
        await db_session.commit()

        resp = await auth_client.get("/api/ravelry/status")

        assert resp.status_code == 200
        body = resp.json()
        assert body["connected"] is True
        assert body["ravelry_username"] == "weaverjane"
        assert body["last_synced_at"] is not None

    async def test_only_reflects_current_user_credential(
        self, auth_client: AsyncClient, db_session: AsyncSession, admin_user: User
    ):
        """A credential belonging to a different user must not leak into this user's status."""
        cred = _make_credential(admin_user, ravelry_username="someone-else")
        db_session.add(cred)
        await db_session.commit()

        resp = await auth_client.get("/api/ravelry/status")

        assert resp.status_code == 200
        assert resp.json()["connected"] is False

    async def test_requires_authentication(self, client: AsyncClient):
        resp = await client.get("/api/ravelry/status")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# TestDisconnect
# ---------------------------------------------------------------------------


class TestDisconnect:
    async def test_returns_404_without_credential(self, auth_client: AsyncClient):
        resp = await auth_client.delete("/api/ravelry/connection")
        assert resp.status_code == 404

    async def test_deletes_existing_credential(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        cred = _make_credential(test_user)
        db_session.add(cred)
        await db_session.commit()
        cred_id = cred.id

        resp = await auth_client.delete("/api/ravelry/connection")

        assert resp.status_code == 204
        remaining = await db_session.scalar(select(RavelryCredential).where(RavelryCredential.id == cred_id))
        assert remaining is None

    async def test_only_deletes_current_users_credential(
        self, auth_client: AsyncClient, db_session: AsyncSession, admin_user: User
    ):
        other_cred = _make_credential(admin_user)
        db_session.add(other_cred)
        await db_session.commit()
        other_id = other_cred.id

        resp = await auth_client.delete("/api/ravelry/connection")

        assert resp.status_code == 404
        still_there = await db_session.scalar(select(RavelryCredential).where(RavelryCredential.id == other_id))
        assert still_there is not None

    async def test_requires_authentication(self, client: AsyncClient):
        resp = await client.delete("/api/ravelry/connection")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# TestAuthorize
# ---------------------------------------------------------------------------


class TestAuthorize:
    async def test_returns_503_when_oauth_not_configured(self, auth_client: AsyncClient, monkeypatch):
        monkeypatch.setattr(get_settings(), "ravelry_oauth_client_id", "")
        resp = await auth_client.get("/api/ravelry/authorize")
        assert resp.status_code == 503

    async def test_returns_authorization_url_when_configured(self, auth_client: AsyncClient, monkeypatch):
        monkeypatch.setattr(get_settings(), "ravelry_oauth_client_id", "test-client-id")
        with patch(
            "app.routers.ravelry.svc.create_oauth_state",
            new=AsyncMock(return_value=("state-abc", "https://www.ravelry.com/oauth2/auth?state=state-abc")),
        ) as mock_create:
            resp = await auth_client.get("/api/ravelry/authorize")

        assert resp.status_code == 200
        assert resp.json()["url"] == "https://www.ravelry.com/oauth2/auth?state=state-abc"
        mock_create.assert_called_once()

    async def test_requires_authentication(self, client: AsyncClient, monkeypatch):
        monkeypatch.setattr(get_settings(), "ravelry_oauth_client_id", "test-client-id")
        resp = await client.get("/api/ravelry/authorize")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# TestOAuthCallbackSuccess
# ---------------------------------------------------------------------------


class TestOAuthCallbackSuccess:
    async def test_exchanges_code_and_saves_credential_then_redirects_connected(
        self, client: AsyncClient, test_user: User
    ):
        state_record = RavelryOAuthState(
            state="valid-state",
            user_id=test_user.id,
            code_verifier="",
            created_at=datetime.now(timezone.utc),
        )
        token_data = {"access_token": "new-token", "refresh_token": "refresh-me"}

        with (
            patch("app.routers.ravelry.svc.consume_oauth_state", new=AsyncMock(return_value=state_record)),
            patch("app.routers.ravelry.svc.exchange_code", new=AsyncMock(return_value=token_data)) as mock_exchange,
            patch("app.routers.ravelry.svc.save_credential", new=AsyncMock()) as mock_save,
        ):
            resp = await client.get(
                "/api/ravelry/callback",
                params={"state": "valid-state", "code": "auth-code-123"},
                follow_redirects=False,
            )

        assert resp.status_code in (302, 307)
        assert "ravelry=connected" in resp.headers["location"]
        mock_exchange.assert_called_once_with("auth-code-123")
        mock_save.assert_called_once()
        assert mock_save.call_args.args[0] == test_user.id
        assert mock_save.call_args.args[1] == token_data

    async def test_token_exchange_failure_redirects_with_error(self, client: AsyncClient, test_user: User):
        state_record = RavelryOAuthState(
            state="valid-state",
            user_id=test_user.id,
            code_verifier="",
            created_at=datetime.now(timezone.utc),
        )

        with (
            patch("app.routers.ravelry.svc.consume_oauth_state", new=AsyncMock(return_value=state_record)),
            patch(
                "app.routers.ravelry.svc.exchange_code",
                new=AsyncMock(side_effect=RuntimeError("Ravelry token endpoint down")),
            ),
        ):
            resp = await client.get(
                "/api/ravelry/callback",
                params={"state": "valid-state", "code": "auth-code-123"},
                follow_redirects=False,
            )

        assert resp.status_code in (302, 307)
        assert "ravelry=error" in resp.headers["location"]
        assert "reason=token_exchange" in resp.headers["location"]
