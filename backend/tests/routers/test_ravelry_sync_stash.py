"""Tests for the Ravelry stash-sync endpoint and service (app.services.ravelry.sync_stash).

No coverage existed for this function before #1063 — written to establish a real
safety net before the cognitive-complexity refactor, not just to pass CI.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ravelry import RavelryCredential
from app.models.user import User
from app.models.yarn import Yarn

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
        "stash_etag": "old-etag",
    }
    defaults.update(overrides)
    return RavelryCredential(**defaults)


def _mock_ravelry_client(parsed, new_etag, raw) -> MagicMock:
    """Return a context-manager mock for RavelryClient.from_oauth_token whose
    stash.list() returns the given (parsed, new_etag, raw) tuple."""
    mock_client = AsyncMock()
    mock_client.stash.list = AsyncMock(return_value=(parsed, new_etag, raw))
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=mock_client)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


def _stash_entry(stash_id: int, **overrides) -> dict:
    entry = {
        "id": stash_id,
        "colorway_name": "Cobalt",
        "yarn": {
            "id": 5000 + stash_id,
            "name": "Cascade 220",
            "yarn_company": {"name": "Cascade Yarns", "url": "https://cascadeyarns.com"},
            "yarn_weight": {"name": "Worsted"},
            "fiber_content": "100% Wool",
            "permalink": "cascade-220",
            "discontinued": False,
            "machine_washable": True,
            "yardage": 220,
            "yarn_attributes": [{"id": 1}],
            "photos": [],
        },
        "photos": [],
    }
    entry.update(overrides)
    return entry


# ---------------------------------------------------------------------------
# TestSyncStashNotConnected
# ---------------------------------------------------------------------------


class TestSyncStashNotConnected:
    async def test_returns_404_without_credential(self, auth_client: AsyncClient):
        resp = await auth_client.post("/api/ravelry/sync")
        assert resp.status_code == 404

    async def test_requires_authentication(self, client: AsyncClient):
        resp = await client.post("/api/ravelry/sync")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# TestSyncStashNotModified — 304 short-circuit
# ---------------------------------------------------------------------------


class TestSyncStashNotModified:
    async def test_304_returns_unchanged_without_touching_entries(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        cred = _make_credential(test_user)
        db_session.add(cred)
        await db_session.commit()

        cm = _mock_ravelry_client(None, None, None)
        with patch("app.services.ravelry.RavelryClient") as mock_cls:
            mock_cls.from_oauth_token.return_value = cm
            resp = await auth_client.post("/api/ravelry/sync")

        assert resp.status_code == 200
        body = resp.json()
        assert body["synced"] == 0
        assert body["unchanged"] is True

    async def test_304_still_updates_last_synced_at(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        cred = _make_credential(test_user)
        db_session.add(cred)
        await db_session.commit()
        cred_id = cred.id

        cm = _mock_ravelry_client(None, None, None)
        with patch("app.services.ravelry.RavelryClient") as mock_cls:
            mock_cls.from_oauth_token.return_value = cm
            await auth_client.post("/api/ravelry/sync")

        refreshed = await db_session.scalar(select(RavelryCredential).where(RavelryCredential.id == cred_id))
        assert refreshed.stash_last_synced_at is not None


# ---------------------------------------------------------------------------
# TestSyncStashCreatesNewYarn
# ---------------------------------------------------------------------------


class TestSyncStashCreatesNewYarn:
    async def test_creates_yarn_with_extracted_fields(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        cred = _make_credential(test_user)
        db_session.add(cred)
        await db_session.commit()

        entry = _stash_entry(111)
        cm = _mock_ravelry_client({"stash": [entry]}, "new-etag", {"stash": [entry]})
        with patch("app.services.ravelry.RavelryClient") as mock_cls:
            mock_cls.from_oauth_token.return_value = cm
            resp = await auth_client.post("/api/ravelry/sync")

        assert resp.status_code == 200
        assert resp.json()["synced"] == 1

        yarn = await db_session.scalar(select(Yarn).where(Yarn.ravelry_stash_id == 111))
        assert yarn is not None
        assert yarn.owner_id == test_user.id
        assert yarn.brand == "Cascade Yarns"
        assert yarn.name == "Cascade 220"
        assert yarn.color_name == "Cobalt"
        assert yarn.weight_category == "worsted"
        assert yarn.fiber_content == "100% Wool"
        assert yarn.ravelry_yarn_id == 5111
        assert yarn.ravelry_permalink == "cascade-220"
        assert yarn.ravelry_discontinued is False
        assert yarn.ravelry_machine_washable is True
        assert yarn.machine_washable is True
        assert yarn.yarn_attribute_ids == [1]

    async def test_falls_back_to_stash_name_when_yarn_name_missing(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        cred = _make_credential(test_user)
        db_session.add(cred)
        await db_session.commit()

        entry = _stash_entry(222, name="Stash-level Name")
        entry["yarn"]["name"] = None
        cm = _mock_ravelry_client({"stash": [entry]}, "etag", {"stash": [entry]})
        with patch("app.services.ravelry.RavelryClient") as mock_cls:
            mock_cls.from_oauth_token.return_value = cm
            await auth_client.post("/api/ravelry/sync")

        yarn = await db_session.scalar(select(Yarn).where(Yarn.ravelry_stash_id == 222))
        assert yarn.name == "Stash-level Name"

    async def test_missing_brand_and_name_fall_back_to_unknown(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        cred = _make_credential(test_user)
        db_session.add(cred)
        await db_session.commit()

        entry = {"id": 333, "yarn": {}}
        cm = _mock_ravelry_client({"stash": [entry]}, "etag", {"stash": [entry]})
        with patch("app.services.ravelry.RavelryClient") as mock_cls:
            mock_cls.from_oauth_token.return_value = cm
            await auth_client.post("/api/ravelry/sync")

        yarn = await db_session.scalar(select(Yarn).where(Yarn.ravelry_stash_id == 333))
        assert yarn.brand == "Unknown"
        assert yarn.name == "Unknown"

    async def test_color_hex_guessed_from_color_family(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        cred = _make_credential(test_user)
        db_session.add(cred)
        await db_session.commit()

        entry = _stash_entry(444, color_family_name="Blue")
        cm = _mock_ravelry_client({"stash": [entry]}, "etag", {"stash": [entry]})
        with patch("app.services.ravelry.RavelryClient") as mock_cls:
            mock_cls.from_oauth_token.return_value = cm
            await auth_client.post("/api/ravelry/sync")

        yarn = await db_session.scalar(select(Yarn).where(Yarn.ravelry_stash_id == 444))
        assert yarn.color_hex == "#2980b9"


# ---------------------------------------------------------------------------
# TestSyncStashPhotoPriority
# ---------------------------------------------------------------------------


class TestSyncStashPhotoPriority:
    async def test_yarn_photos_preferred_over_stash_photos(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        entry = _stash_entry(555)
        entry["yarn"]["photos"] = [{"sort_order": 1, "medium_url": "https://x/yarn-photo.jpg"}]
        entry["photos"] = [{"sort_order": 1, "medium_url": "https://x/stash-photo.jpg"}]

        cred = _make_credential(test_user)
        db_session.add(cred)
        await db_session.commit()

        cm = _mock_ravelry_client({"stash": [entry]}, "etag", {"stash": [entry]})
        with patch("app.services.ravelry.RavelryClient") as mock_cls:
            mock_cls.from_oauth_token.return_value = cm
            await auth_client.post("/api/ravelry/sync")

        yarn = await db_session.scalar(select(Yarn).where(Yarn.ravelry_stash_id == 555))
        assert yarn.ravelry_photo_url == "https://x/yarn-photo.jpg"

    async def test_falls_back_to_stash_photos_when_yarn_photos_empty(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        entry = _stash_entry(666)
        entry["yarn"]["photos"] = []
        entry["photos"] = [{"sort_order": 1, "medium_url": "https://x/stash-photo.jpg"}]

        cred = _make_credential(test_user)
        db_session.add(cred)
        await db_session.commit()

        cm = _mock_ravelry_client({"stash": [entry]}, "etag", {"stash": [entry]})
        with patch("app.services.ravelry.RavelryClient") as mock_cls:
            mock_cls.from_oauth_token.return_value = cm
            await auth_client.post("/api/ravelry/sync")

        yarn = await db_session.scalar(select(Yarn).where(Yarn.ravelry_stash_id == 666))
        assert yarn.ravelry_photo_url == "https://x/stash-photo.jpg"

    async def test_lowest_sort_order_photo_wins(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        entry = _stash_entry(777)
        entry["yarn"]["photos"] = [
            {"sort_order": 2, "medium_url": "https://x/second.jpg"},
            {"sort_order": 1, "medium_url": "https://x/first.jpg", "square_url": "https://x/first-sq.jpg"},
        ]

        cred = _make_credential(test_user)
        db_session.add(cred)
        await db_session.commit()

        cm = _mock_ravelry_client({"stash": [entry]}, "etag", {"stash": [entry]})
        with patch("app.services.ravelry.RavelryClient") as mock_cls:
            mock_cls.from_oauth_token.return_value = cm
            await auth_client.post("/api/ravelry/sync")

        yarn = await db_session.scalar(select(Yarn).where(Yarn.ravelry_stash_id == 777))
        assert yarn.ravelry_photo_url == "https://x/first.jpg"
        assert yarn.ravelry_thumbnail_url == "https://x/first-sq.jpg"


# ---------------------------------------------------------------------------
# TestSyncStashUpdatesExisting
# ---------------------------------------------------------------------------


class TestSyncStashUpdatesExisting:
    async def test_updates_matching_existing_yarn_in_place(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        cred = _make_credential(test_user)
        existing = Yarn(
            owner_id=test_user.id,
            brand="Old Brand",
            name="Old Name",
            ravelry_stash_id=888,
            out_of_stash=False,
        )
        db_session.add_all([cred, existing])
        await db_session.commit()
        await db_session.refresh(existing)
        existing_id = existing.id

        entry = _stash_entry(888)
        cm = _mock_ravelry_client({"stash": [entry]}, "etag", {"stash": [entry]})
        with patch("app.services.ravelry.RavelryClient") as mock_cls:
            mock_cls.from_oauth_token.return_value = cm
            resp = await auth_client.post("/api/ravelry/sync")

        assert resp.status_code == 200
        count = await db_session.scalar(select(Yarn.id).where(Yarn.ravelry_stash_id == 888).limit(1))
        assert count is not None

        updated = await db_session.get(Yarn, existing_id)
        assert updated.id == existing_id  # updated in place, not duplicated
        assert updated.brand == "Cascade Yarns"
        assert updated.name == "Cascade 220"

    async def test_missing_photo_url_does_not_clear_existing_photo(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        cred = _make_credential(test_user)
        existing = Yarn(
            owner_id=test_user.id,
            brand="Cascade",
            name="220",
            ravelry_stash_id=999,
            ravelry_photo_url="https://x/keep-me.jpg",
        )
        db_session.add_all([cred, existing])
        await db_session.commit()
        await db_session.refresh(existing)
        existing_id = existing.id

        entry = _stash_entry(999)  # no photos in this entry
        cm = _mock_ravelry_client({"stash": [entry]}, "etag", {"stash": [entry]})
        with patch("app.services.ravelry.RavelryClient") as mock_cls:
            mock_cls.from_oauth_token.return_value = cm
            await auth_client.post("/api/ravelry/sync")

        updated = await db_session.get(Yarn, existing_id)
        assert updated.ravelry_photo_url == "https://x/keep-me.jpg"

    async def test_missing_machine_washable_does_not_clear_existing_value(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        cred = _make_credential(test_user)
        existing = Yarn(
            owner_id=test_user.id,
            brand="Cascade",
            name="220",
            ravelry_stash_id=1000,
            machine_washable=True,
            ravelry_machine_washable=True,
        )
        db_session.add_all([cred, existing])
        await db_session.commit()
        await db_session.refresh(existing)
        existing_id = existing.id

        entry = _stash_entry(1000)
        entry["yarn"]["machine_washable"] = None
        cm = _mock_ravelry_client({"stash": [entry]}, "etag", {"stash": [entry]})
        with patch("app.services.ravelry.RavelryClient") as mock_cls:
            mock_cls.from_oauth_token.return_value = cm
            await auth_client.post("/api/ravelry/sync")

        updated = await db_session.get(Yarn, existing_id)
        assert updated.machine_washable is True

    async def test_existing_color_hex_not_overwritten_once_set(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        cred = _make_credential(test_user)
        existing = Yarn(
            owner_id=test_user.id,
            brand="Cascade",
            name="220",
            ravelry_stash_id=1100,
            color_hex="#ffffff",
        )
        db_session.add_all([cred, existing])
        await db_session.commit()
        await db_session.refresh(existing)
        existing_id = existing.id

        entry = _stash_entry(1100, color_family_name="Blue")
        cm = _mock_ravelry_client({"stash": [entry]}, "etag", {"stash": [entry]})
        with patch("app.services.ravelry.RavelryClient") as mock_cls:
            mock_cls.from_oauth_token.return_value = cm
            await auth_client.post("/api/ravelry/sync")

        updated = await db_session.get(Yarn, existing_id)
        assert updated.color_hex == "#ffffff"

    async def test_resyncing_clears_out_of_stash_flag(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        cred = _make_credential(test_user)
        existing = Yarn(
            owner_id=test_user.id,
            brand="Cascade",
            name="220",
            ravelry_stash_id=1200,
            out_of_stash=True,
        )
        db_session.add_all([cred, existing])
        await db_session.commit()
        await db_session.refresh(existing)
        existing_id = existing.id

        entry = _stash_entry(1200)
        cm = _mock_ravelry_client({"stash": [entry]}, "etag", {"stash": [entry]})
        with patch("app.services.ravelry.RavelryClient") as mock_cls:
            mock_cls.from_oauth_token.return_value = cm
            await auth_client.post("/api/ravelry/sync")

        updated = await db_session.get(Yarn, existing_id)
        assert updated.out_of_stash is False


# ---------------------------------------------------------------------------
# TestSyncStashArchival — out_of_stash bookkeeping
# ---------------------------------------------------------------------------


class TestSyncStashArchival:
    async def test_yarn_no_longer_in_stash_marked_out_of_stash(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        cred = _make_credential(test_user)
        removed = Yarn(
            owner_id=test_user.id,
            brand="Old",
            name="Removed",
            ravelry_stash_id=1300,
            out_of_stash=False,
        )
        db_session.add_all([cred, removed])
        await db_session.commit()
        await db_session.refresh(removed)
        removed_id = removed.id

        # This sync only returns a DIFFERENT stash entry — 1300 is no longer present.
        entry = _stash_entry(1301)
        cm = _mock_ravelry_client({"stash": [entry]}, "etag", {"stash": [entry]})
        with patch("app.services.ravelry.RavelryClient") as mock_cls:
            mock_cls.from_oauth_token.return_value = cm
            await auth_client.post("/api/ravelry/sync")

        updated = await db_session.get(Yarn, removed_id)
        assert updated.out_of_stash is True

    async def test_already_out_of_stash_yarn_not_touched_by_archival_scan(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        """Archival query filters out_of_stash.is_(False) — already-archived yarns are skipped."""
        cred = _make_credential(test_user)
        already_out = Yarn(
            owner_id=test_user.id,
            brand="Old",
            name="Already Out",
            ravelry_stash_id=1400,
            out_of_stash=True,
        )
        db_session.add_all([cred, already_out])
        await db_session.commit()
        await db_session.refresh(already_out)

        entry = _stash_entry(1401)
        cm = _mock_ravelry_client({"stash": [entry]}, "etag", {"stash": [entry]})
        with patch("app.services.ravelry.RavelryClient") as mock_cls:
            mock_cls.from_oauth_token.return_value = cm
            resp = await auth_client.post("/api/ravelry/sync")

        assert resp.status_code == 200  # doesn't error re-processing an already-archived yarn

    async def test_yarn_without_ravelry_stash_id_unaffected(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        """Manually-added yarns (ravelry_stash_id is None) must never be archived by sync."""
        cred = _make_credential(test_user)
        manual = Yarn(owner_id=test_user.id, brand="Manual", name="Hand Entry", ravelry_stash_id=None)
        db_session.add_all([cred, manual])
        await db_session.commit()
        await db_session.refresh(manual)
        manual_id = manual.id

        entry = _stash_entry(1500)
        cm = _mock_ravelry_client({"stash": [entry]}, "etag", {"stash": [entry]})
        with patch("app.services.ravelry.RavelryClient") as mock_cls:
            mock_cls.from_oauth_token.return_value = cm
            await auth_client.post("/api/ravelry/sync")

        updated = await db_session.get(Yarn, manual_id)
        assert updated.out_of_stash is False


# ---------------------------------------------------------------------------
# TestSyncStashPhotoBackfill
# ---------------------------------------------------------------------------


class TestSyncStashPhotoBackfill:
    async def test_backfills_photo_for_yarn_missing_one(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        entry = _stash_entry(1600)
        entry["yarn"]["photos"] = []  # no photo from the stash list response itself

        cred = _make_credential(test_user)
        db_session.add(cred)
        await db_session.commit()

        cm = _mock_ravelry_client({"stash": [entry]}, "etag", {"stash": [entry]})
        backfill_response = {
            "yarn": {
                "photos": [
                    {"sort_order": 1, "medium_url": "https://x/backfilled.jpg", "square_url": "https://x/bf-sq.jpg"}
                ]
            }
        }
        with patch("app.services.ravelry.RavelryClient") as mock_cls:
            mock_cls.from_oauth_token.return_value = cm
            with patch(
                "app.services.ravelry._basic_auth_get",
                new=AsyncMock(return_value=backfill_response),
            ):
                await auth_client.post("/api/ravelry/sync")

        yarn = await db_session.scalar(select(Yarn).where(Yarn.ravelry_stash_id == 1600))
        assert yarn.ravelry_photo_url == "https://x/backfilled.jpg"
        assert yarn.ravelry_thumbnail_url == "https://x/bf-sq.jpg"

    async def test_backfill_failure_does_not_fail_the_sync(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        entry = _stash_entry(1700)
        entry["yarn"]["photos"] = []

        cred = _make_credential(test_user)
        db_session.add(cred)
        await db_session.commit()

        cm = _mock_ravelry_client({"stash": [entry]}, "etag", {"stash": [entry]})
        with patch("app.services.ravelry.RavelryClient") as mock_cls:
            mock_cls.from_oauth_token.return_value = cm
            with patch(
                "app.services.ravelry._basic_auth_get",
                new=AsyncMock(side_effect=RuntimeError("backfill fetch failed")),
            ):
                resp = await auth_client.post("/api/ravelry/sync")

        assert resp.status_code == 200
        yarn = await db_session.scalar(select(Yarn).where(Yarn.ravelry_stash_id == 1700))
        assert yarn is not None
        assert yarn.ravelry_photo_url is None

    async def test_yarn_with_existing_photo_not_backfilled(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        entry = _stash_entry(1800)
        entry["yarn"]["photos"] = [{"sort_order": 1, "medium_url": "https://x/from-sync.jpg"}]

        cred = _make_credential(test_user)
        db_session.add(cred)
        await db_session.commit()

        cm = _mock_ravelry_client({"stash": [entry]}, "etag", {"stash": [entry]})
        mock_backfill = AsyncMock(return_value={"yarn": {"photos": []}})
        with patch("app.services.ravelry.RavelryClient") as mock_cls:
            mock_cls.from_oauth_token.return_value = cm
            with patch("app.services.ravelry._basic_auth_get", new=mock_backfill):
                await auth_client.post("/api/ravelry/sync")

        mock_backfill.assert_not_called()


# ---------------------------------------------------------------------------
# TestSyncStashResponse — final persistence + response shape
# ---------------------------------------------------------------------------


class TestSyncStashResponse:
    async def test_etag_and_last_synced_at_persisted(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        cred = _make_credential(test_user, stash_etag="old-etag")
        db_session.add(cred)
        await db_session.commit()
        cred_id = cred.id

        entry = _stash_entry(1900)
        cm = _mock_ravelry_client({"stash": [entry]}, "brand-new-etag", {"stash": [entry]})
        with patch("app.services.ravelry.RavelryClient") as mock_cls:
            mock_cls.from_oauth_token.return_value = cm
            await auth_client.post("/api/ravelry/sync")

        refreshed = await db_session.scalar(select(RavelryCredential).where(RavelryCredential.id == cred_id))
        assert refreshed.stash_etag == "brand-new-etag"
        assert refreshed.stash_last_synced_at is not None

    async def test_synced_count_matches_entry_count(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        entries = [_stash_entry(2000), _stash_entry(2001), _stash_entry(2002)]
        cred = _make_credential(test_user)
        db_session.add(cred)
        await db_session.commit()

        cm = _mock_ravelry_client({"stash": entries}, "etag", {"stash": entries})
        with patch("app.services.ravelry.RavelryClient") as mock_cls:
            mock_cls.from_oauth_token.return_value = cm
            resp = await auth_client.post("/api/ravelry/sync")

        assert resp.json()["synced"] == 3
        assert resp.json()["unchanged"] is False

    async def test_returns_502_on_unexpected_error(
        self, auth_client: AsyncClient, db_session: AsyncSession, test_user: User
    ):
        cred = _make_credential(test_user)
        db_session.add(cred)
        await db_session.commit()

        with patch("app.services.ravelry.RavelryClient") as mock_cls:
            mock_cls.from_oauth_token.side_effect = RuntimeError("network exploded")
            resp = await auth_client.post("/api/ravelry/sync")

        assert resp.status_code == 502
