"""Tests for app.tasks.export._build_export, _safe_filename, and _readme.

create_async_engine and async_sessionmaker are patched so the task uses
the test db_session instead of opening its own connection.
asyncio.to_thread is patched to prevent real storage writes.
"""

import io
import json
import uuid
import zipfile
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from celery.exceptions import SoftTimeLimitExceeded
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.collection import Collection
from app.models.draft import Draft
from app.models.loom import Loom
from app.models.project import Project, ProjectPhoto
from app.models.user import User
from app.models.user_export import UserExportRequest
from app.models.yarn import Yarn
from app.tasks.export import EXPORT_TTL_DAYS, _build_export, _readme, _safe_filename

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _session_factory(db: AsyncSession):
    """Return an async_sessionmaker-compatible callable that yields db."""

    class _Ctx:
        async def __aenter__(self):
            return db

        async def __aexit__(self, *args):
            pass  # no-op; test stub requires no cleanup

    class _Factory:
        def __call__(self):
            return _Ctx()

    return _Factory()


async def _make_user(db: AsyncSession) -> User:
    user = User(
        email=f"export-{uuid.uuid4().hex[:6]}@test.com",
        display_name="Export User",
        oidc_sub=f"export-sub-{uuid.uuid4().hex}",
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def _make_request(db: AsyncSession, user_id: uuid.UUID) -> UserExportRequest:
    req = UserExportRequest(
        user_id=user_id,
        requested_at=datetime.now(timezone.utc),
        status="pending",
    )
    db.add(req)
    await db.commit()
    await db.refresh(req)
    return req


async def _make_draft(db: AsyncSession, owner_id: uuid.UUID, name: str = "Test Draft") -> Draft:
    draft = Draft(owner_id=owner_id, name=name, wif_filename="test.wif", wif_path="wifs/test.wif")
    db.add(draft)
    await db.flush()
    return draft


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_db(db_session: AsyncSession):
    fake_engine = MagicMock()
    fake_engine.dispose = AsyncMock()
    with (
        patch("app.tasks.export.create_async_engine", return_value=fake_engine),
        patch("app.tasks.export.async_sessionmaker", return_value=_session_factory(db_session)),
    ):
        yield


@pytest.fixture()
def mock_storage():
    with (
        patch("app.services.storage.aread_file", new_callable=AsyncMock, return_value=b"fake-file-data"),
        patch("asyncio.to_thread", new_callable=AsyncMock),
    ):
        yield


@pytest.fixture()
def mock_email():
    with patch("app.services.email.send_export_ready", new_callable=AsyncMock):
        yield


# ---------------------------------------------------------------------------
# TestSafeFilename — pure function
# ---------------------------------------------------------------------------


class TestSafeFilename:
    def test_normal_name_passes_through(self):
        assert _safe_filename("My Draft") == "My Draft"

    def test_dangerous_chars_replaced(self):
        result = _safe_filename('foo<>:"/\\|?*bar')
        assert "<" not in result
        assert ">" not in result
        assert '"' not in result
        assert "/" not in result
        assert "\\" not in result

    def test_truncates_long_name(self):
        assert len(_safe_filename("a" * 100)) <= 80

    def test_empty_returns_untitled(self):
        assert _safe_filename("") == "untitled"

    def test_control_chars_replaced(self):
        assert "\x00" not in _safe_filename("foo\x00bar")
        assert "\x1f" not in _safe_filename("foo\x1fbar")

    def test_strips_leading_dots(self):
        result = _safe_filename("..name")
        assert not result.startswith(".")

    def test_strips_leading_underscores(self):
        result = _safe_filename("__name")
        assert not result.startswith("_")


# ---------------------------------------------------------------------------
# TestReadme — pure function
# ---------------------------------------------------------------------------


class TestReadme:
    def _user(self, name="Alice", email="alice@test.com"):
        u = MagicMock()
        u.display_name = name
        u.email = email
        return u

    def test_contains_display_name(self):
        assert "Alice" in _readme(self._user(), "2026-05-24")

    def test_contains_email(self):
        assert "alice@test.com" in _readme(self._user(), "2026-05-24")

    def test_contains_date(self):
        assert "2026-05-24" in _readme(self._user(), "2026-05-24")

    def test_mentions_ttl_days(self):
        assert str(EXPORT_TTL_DAYS) in _readme(self._user(), "2026-05-24")

    def test_lists_expected_sections(self):
        text = _readme(self._user(), "2026-05-24")
        for section in ("drafts/", "data/profile.json", "data/drafts.json", "data/yarn.json"):
            assert section in text


# ---------------------------------------------------------------------------
# TestBuildExportSkipPaths
# ---------------------------------------------------------------------------


class TestBuildExportSkipPaths:
    async def test_request_not_found_returns_cleanly(self, db_session, mock_db, mock_storage, mock_email):
        user = await _make_user(db_session)
        await _build_export(user.id, uuid.uuid4())  # unknown request_id — must not raise

    async def test_user_not_found_sets_failed(self, db_session, mock_db, mock_storage, mock_email):
        user = await _make_user(db_session)
        req = await _make_request(db_session, user.id)

        await _build_export(uuid.uuid4(), req.id)  # unknown user_id

        await db_session.refresh(req)
        assert req.status == "failed"
        assert req.error == "User not found"


# ---------------------------------------------------------------------------
# TestBuildExportHappyPath
# ---------------------------------------------------------------------------


class TestBuildExportHappyPath:
    async def test_sets_status_complete(self, db_session, mock_db, mock_storage, mock_email):
        user = await _make_user(db_session)
        req = await _make_request(db_session, user.id)

        await _build_export(user.id, req.id)

        await db_session.refresh(req)
        assert req.status == "complete"

    async def test_sets_archive_path(self, db_session, mock_db, mock_storage, mock_email):
        user = await _make_user(db_session)
        req = await _make_request(db_session, user.id)

        await _build_export(user.id, req.id)

        await db_session.refresh(req)
        assert req.archive_path == f"exports/{user.id}/{req.id}.zip"

    async def test_sets_archive_size(self, db_session, mock_db, mock_storage, mock_email):
        user = await _make_user(db_session)
        req = await _make_request(db_session, user.id)

        await _build_export(user.id, req.id)

        await db_session.refresh(req)
        assert req.archive_size_bytes is not None
        assert req.archive_size_bytes > 0

    async def test_sets_expires_at(self, db_session, mock_db, mock_storage, mock_email):
        user = await _make_user(db_session)
        req = await _make_request(db_session, user.id)

        await _build_export(user.id, req.id)

        await db_session.refresh(req)
        assert req.expires_at is not None

    async def test_zip_contains_required_json_files(self, db_session, mock_db, mock_email):
        user = await _make_user(db_session)
        req = await _make_request(db_session, user.id)

        zip_bytes: list[bytes] = []

        async def capture(fn, *args):  # NOSONAR: must be async to patch asyncio.to_thread
            zip_bytes.append(args[1])

        with (
            patch("asyncio.to_thread", side_effect=capture),
            patch("app.services.storage.aread_file", new_callable=AsyncMock, return_value=b""),
        ):
            await _build_export(user.id, req.id)

        assert zip_bytes, "to_thread was never called — ZIP was never uploaded"
        zf = zipfile.ZipFile(io.BytesIO(zip_bytes[0]))
        names = zf.namelist()
        for expected in (
            "profile.json",
            "drafts.json",
            "projects.json",
            "yarn.json",
            "looms.json",
            "collections.json",
            "README.txt",
        ):
            assert any(expected in n for n in names), f"{expected} missing from archive"

    async def test_zip_includes_wif_file_for_draft(self, db_session, mock_db, mock_email):
        user = await _make_user(db_session)
        await _make_draft(db_session, user.id, "My Twill")
        await db_session.commit()
        req = await _make_request(db_session, user.id)

        zip_bytes: list[bytes] = []

        async def capture(fn, *args):  # NOSONAR: must be async to patch asyncio.to_thread
            zip_bytes.append(args[1])

        with (
            patch("asyncio.to_thread", side_effect=capture),
            patch("app.services.storage.aread_file", new_callable=AsyncMock, return_value=b"[WIF]"),
        ):
            await _build_export(user.id, req.id)

        zf = zipfile.ZipFile(io.BytesIO(zip_bytes[0]))
        assert any(".wif" in n for n in zf.namelist())

    async def test_draft_json_includes_id_and_name(self, db_session, mock_db, mock_email):
        user = await _make_user(db_session)
        draft = await _make_draft(db_session, user.id, "Twill Check")
        await db_session.commit()
        req = await _make_request(db_session, user.id)

        zip_bytes: list[bytes] = []

        async def capture(fn, *args):  # NOSONAR: must be async to patch asyncio.to_thread
            zip_bytes.append(args[1])

        with (
            patch("asyncio.to_thread", side_effect=capture),
            patch("app.services.storage.aread_file", new_callable=AsyncMock, return_value=b""),
        ):
            await _build_export(user.id, req.id)

        zf = zipfile.ZipFile(io.BytesIO(zip_bytes[0]))
        drafts_entry = next(n for n in zf.namelist() if "drafts.json" in n)
        drafts = json.loads(zf.read(drafts_entry))
        assert len(drafts) == 1
        assert drafts[0]["name"] == "Twill Check"
        assert drafts[0]["id"] == str(draft.id)

    async def test_project_status_and_name_in_json(self, db_session, mock_db, mock_storage, mock_email):
        user = await _make_user(db_session)
        draft = await _make_draft(db_session, user.id)
        project = Project(
            owner_id=user.id,
            draft_id=draft.id,
            name="Spring Scarf",
            project_type="treadle",
            total_picks=200,
            status="completed",
        )
        db_session.add(project)
        await db_session.commit()
        req = await _make_request(db_session, user.id)

        await _build_export(user.id, req.id)

        await db_session.refresh(req)
        assert req.status == "complete"

    async def test_yarn_included_in_export(self, db_session, mock_db, mock_storage, mock_email):
        user = await _make_user(db_session)
        yarn = Yarn(
            owner_id=user.id,
            brand="Malabrigo",
            name="Rios",
            color_name="Lettuce",
            weight_category="worsted",
        )
        db_session.add(yarn)
        await db_session.commit()
        req = await _make_request(db_session, user.id)

        await _build_export(user.id, req.id)

        await db_session.refresh(req)
        assert req.status == "complete"

    async def test_loom_name_formatted_as_manufacturer_and_model(self, db_session, mock_db, mock_email):
        user = await _make_user(db_session)
        loom = Loom(
            owner_id=user.id,
            loom_type="floor",
            manufacturer="Ashford",
            model_name="Table Loom",
        )
        db_session.add(loom)
        await db_session.commit()
        req = await _make_request(db_session, user.id)

        zip_bytes: list[bytes] = []

        async def capture(fn, *args):  # NOSONAR: must be async to patch asyncio.to_thread
            zip_bytes.append(args[1])

        with (
            patch("asyncio.to_thread", side_effect=capture),
            patch("app.services.storage.aread_file", new_callable=AsyncMock, return_value=b""),
        ):
            await _build_export(user.id, req.id)

        zf = zipfile.ZipFile(io.BytesIO(zip_bytes[0]))
        looms_entry = next(n for n in zf.namelist() if "looms.json" in n)
        looms = json.loads(zf.read(looms_entry))
        assert looms[0]["name"] == "Ashford Table Loom"

    async def test_collection_included_in_export(self, db_session, mock_db, mock_storage, mock_email):
        user = await _make_user(db_session)
        db_session.add(Collection(owner_id=user.id, name="Favorites"))
        await db_session.commit()
        req = await _make_request(db_session, user.id)

        await _build_export(user.id, req.id)

        await db_session.refresh(req)
        assert req.status == "complete"

    async def test_deleted_draft_excluded_from_json(self, db_session, mock_db, mock_email):
        user = await _make_user(db_session)
        draft = await _make_draft(db_session, user.id, "Deleted Draft")
        draft.soft_delete()
        await db_session.commit()
        req = await _make_request(db_session, user.id)

        zip_bytes: list[bytes] = []

        async def capture(fn, *args):  # NOSONAR: must be async to patch asyncio.to_thread
            zip_bytes.append(args[1])

        with (
            patch("asyncio.to_thread", side_effect=capture),
            patch("app.services.storage.aread_file", new_callable=AsyncMock, return_value=b""),
        ):
            await _build_export(user.id, req.id)

        zf = zipfile.ZipFile(io.BytesIO(zip_bytes[0]))
        drafts_entry = next(n for n in zf.namelist() if "drafts.json" in n)
        drafts = json.loads(zf.read(drafts_entry))
        assert all(d["id"] != str(draft.id) for d in drafts)

    async def test_only_exports_requesting_users_data(self, db_session, mock_db, mock_storage, mock_email):
        user_a = await _make_user(db_session)
        user_b = await _make_user(db_session)
        db_session.add(Yarn(owner_id=user_b.id, brand="B", name="Other yarn"))
        await db_session.commit()
        req = await _make_request(db_session, user_a.id)

        await _build_export(user_a.id, req.id)

        await db_session.refresh(req)
        assert req.status == "complete"


# ---------------------------------------------------------------------------
# TestBuildExportErrorPaths
# ---------------------------------------------------------------------------


class TestBuildExportErrorPaths:
    async def test_wif_storage_failure_skipped(self, db_session, mock_db, mock_email):
        user = await _make_user(db_session)
        await _make_draft(db_session, user.id, "Bad WIF")
        await db_session.commit()
        req = await _make_request(db_session, user.id)

        with (
            patch(
                "app.services.storage.aread_file",
                new_callable=AsyncMock,
                side_effect=FileNotFoundError("gone"),
            ),
            patch("asyncio.to_thread", new_callable=AsyncMock),
        ):
            await _build_export(user.id, req.id)

        await db_session.refresh(req)
        assert req.status == "complete"

    async def test_photo_storage_failure_skipped(self, db_session, mock_db, mock_email):
        user = await _make_user(db_session)
        draft = await _make_draft(db_session, user.id)
        project = Project(
            owner_id=user.id,
            draft_id=draft.id,
            name="Photo Project",
            project_type="treadle",
            total_picks=10,
        )
        db_session.add(project)
        await db_session.flush()
        db_session.add(ProjectPhoto(project_id=project.id, file_path="photos/p.jpg", filename="p.jpg"))
        await db_session.commit()
        req = await _make_request(db_session, user.id)

        with (
            patch(
                "app.services.storage.aread_file",
                new_callable=AsyncMock,
                side_effect=FileNotFoundError("gone"),
            ),
            patch("asyncio.to_thread", new_callable=AsyncMock),
        ):
            await _build_export(user.id, req.id)

        await db_session.refresh(req)
        assert req.status == "complete"

    async def test_soft_time_limit_sets_failed_and_reraises(self, db_session, mock_db, mock_email):
        user = await _make_user(db_session)
        req = await _make_request(db_session, user.id)

        with (
            patch("app.services.storage.aread_file", new_callable=AsyncMock, return_value=b""),
            patch("asyncio.to_thread", new_callable=AsyncMock, side_effect=SoftTimeLimitExceeded()),
        ):
            with pytest.raises(SoftTimeLimitExceeded):
                await _build_export(user.id, req.id)

        await db_session.refresh(req)
        assert req.status == "failed"
        assert req.error == "Task timed out"

    async def test_generic_exception_sets_failed(self, db_session, mock_db, mock_email):
        user = await _make_user(db_session)
        req = await _make_request(db_session, user.id)

        with (
            patch("app.services.storage.aread_file", new_callable=AsyncMock, return_value=b""),
            patch("asyncio.to_thread", new_callable=AsyncMock, side_effect=RuntimeError("upload failed")),
        ):
            await _build_export(user.id, req.id)

        await db_session.refresh(req)
        assert req.status == "failed"
        assert "upload failed" in req.error

    async def test_email_failure_swallowed_status_still_complete(self, db_session, mock_db, mock_storage):
        user = await _make_user(db_session)
        req = await _make_request(db_session, user.id)

        with patch(
            "app.services.email.send_export_ready",
            new_callable=AsyncMock,
            side_effect=Exception("smtp down"),
        ):
            await _build_export(user.id, req.id)

        await db_session.refresh(req)
        assert req.status == "complete"
