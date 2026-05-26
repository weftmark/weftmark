"""Tests for Ravelry stash push-back endpoints and service."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ravelry import RavelryCredential
from app.models.user import User
from app.models.yarn import Yarn

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_STASH_CREATE_RESPONSE = {"stash": {"id": 99001, "colorway_name": "Natural"}}


def _make_credential(user: User) -> RavelryCredential:
    return RavelryCredential(
        id=uuid.uuid4(),
        user_id=user.id,
        ravelry_username="testweaver",
        access_token="fake-token",
        refresh_token=None,
        expires_at=None,
    )


def _make_yarn(user: User, **overrides) -> Yarn:
    defaults = {
        "owner_id": user.id,
        "brand": "Cascade",
        "name": "220",
        "ravelry_yarn_id": 42,
        "ravelry_stash_id": None,
        "archived": False,
        "out_of_stash": False,
    }
    defaults.update(overrides)
    return Yarn(**defaults)


def _mock_ravelry_client(response: dict) -> MagicMock:
    """Return a context-manager mock for RavelryClient.from_oauth_token."""
    mock_client = AsyncMock()
    mock_client.stash.create = AsyncMock(return_value=(None, None, response))
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=mock_client)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


# ---------------------------------------------------------------------------
# TestStashPushSingle
# ---------------------------------------------------------------------------


class TestStashPushSingle:
    async def test_happy_path_writes_back_stash_id(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        cred = _make_credential(test_user)
        yarn = _make_yarn(test_user)
        db_session.add_all([cred, yarn])
        await db_session.commit()
        await db_session.refresh(yarn)

        cm = _mock_ravelry_client(_STASH_CREATE_RESPONSE)
        with patch("app.services.ravelry.RavelryClient") as mock_cls:
            mock_cls.from_oauth_token.return_value = cm
            resp = await auth_client.post(f"/api/ravelry/stash-push/{yarn.id}")

        assert resp.status_code == 200
        assert resp.json()["ravelry_stash_id"] == 99001

        await db_session.refresh(yarn)
        assert yarn.ravelry_stash_id == 99001

    async def test_stash_create_called_once(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        cred = _make_credential(test_user)
        yarn = _make_yarn(test_user)
        db_session.add_all([cred, yarn])
        await db_session.commit()
        await db_session.refresh(yarn)

        mock_client = AsyncMock()
        mock_client.stash.create = AsyncMock(return_value=(None, None, _STASH_CREATE_RESPONSE))
        cm = MagicMock()
        cm.__aenter__ = AsyncMock(return_value=mock_client)
        cm.__aexit__ = AsyncMock(return_value=False)

        with patch("app.services.ravelry.RavelryClient") as mock_cls:
            mock_cls.from_oauth_token.return_value = cm
            await auth_client.post(f"/api/ravelry/stash-push/{yarn.id}")

        mock_client.stash.create.assert_called_once()

    async def test_already_synced_returns_422(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        cred = _make_credential(test_user)
        yarn = _make_yarn(test_user, ravelry_stash_id=12345)
        db_session.add_all([cred, yarn])
        await db_session.commit()
        await db_session.refresh(yarn)

        resp = await auth_client.post(f"/api/ravelry/stash-push/{yarn.id}")

        assert resp.status_code == 422

    async def test_tier2_yarn_returns_422(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        cred = _make_credential(test_user)
        yarn = _make_yarn(test_user, ravelry_yarn_id=None)
        db_session.add_all([cred, yarn])
        await db_session.commit()
        await db_session.refresh(yarn)

        resp = await auth_client.post(f"/api/ravelry/stash-push/{yarn.id}")

        assert resp.status_code == 422

    async def test_archived_yarn_returns_422(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        cred = _make_credential(test_user)
        yarn = _make_yarn(test_user, archived=True)
        db_session.add_all([cred, yarn])
        await db_session.commit()
        await db_session.refresh(yarn)

        resp = await auth_client.post(f"/api/ravelry/stash-push/{yarn.id}")

        assert resp.status_code == 422

    async def test_no_credential_returns_404(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        yarn = _make_yarn(test_user)
        db_session.add(yarn)
        await db_session.commit()
        await db_session.refresh(yarn)

        resp = await auth_client.post(f"/api/ravelry/stash-push/{yarn.id}")

        assert resp.status_code == 404

    async def test_unknown_yarn_returns_404(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        cred = _make_credential(test_user)
        db_session.add(cred)
        await db_session.commit()

        resp = await auth_client.post(f"/api/ravelry/stash-push/{uuid.uuid4()}")

        assert resp.status_code == 404

    async def test_requires_authentication(self, client: AsyncClient):
        resp = await client.post(f"/api/ravelry/stash-push/{uuid.uuid4()}")
        assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# TestStashPushBulk
# ---------------------------------------------------------------------------


class TestStashPushBulk:
    async def test_pushes_only_eligible_tier1_yarns(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        cred = _make_credential(test_user)
        eligible = _make_yarn(test_user, name="Eligible")
        already_synced = _make_yarn(test_user, name="Already synced", ravelry_stash_id=111)
        tier2 = _make_yarn(test_user, name="Tier 2", ravelry_yarn_id=None)
        archived = _make_yarn(test_user, name="Archived", archived=True)
        db_session.add_all([cred, eligible, already_synced, tier2, archived])
        await db_session.commit()

        cm = _mock_ravelry_client(_STASH_CREATE_RESPONSE)
        with patch("app.services.ravelry.RavelryClient") as mock_cls:
            mock_cls.from_oauth_token.return_value = cm
            resp = await auth_client.post("/api/ravelry/stash-push/bulk")

        assert resp.status_code == 200
        data = resp.json()
        assert data["pushed"] == 1
        assert data["skipped"] == 0

    async def test_empty_eligible_returns_zero_counts(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        cred = _make_credential(test_user)
        already_synced = _make_yarn(test_user, ravelry_stash_id=222)
        db_session.add_all([cred, already_synced])
        await db_session.commit()

        with patch("app.services.ravelry.RavelryClient") as mock_cls:
            resp = await auth_client.post("/api/ravelry/stash-push/bulk")
            mock_cls.from_oauth_token.assert_not_called()

        assert resp.status_code == 200
        data = resp.json()
        assert data["pushed"] == 0
        assert data["skipped"] == 0

    async def test_no_credential_returns_404(self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User):
        resp = await auth_client.post("/api/ravelry/stash-push/bulk")
        assert resp.status_code == 404

    async def test_requires_authentication(self, client: AsyncClient):
        resp = await client.post("/api/ravelry/stash-push/bulk")
        assert resp.status_code in (401, 403)
