"""Tests for app.tasks.s3_audit._do_scan and _store_s3_summary."""

import json
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.tasks.s3_audit import S3_AUDIT_SUMMARY_KEY, _do_scan, _store_s3_summary

# ---------------------------------------------------------------------------
# Helpers for redirecting DB engine/session to test db_session
# ---------------------------------------------------------------------------


def _session_factory(db: AsyncSession):
    class _Ctx:
        async def __aenter__(self):
            return db

        async def __aexit__(self, *args):
            pass  # no cleanup needed

    class _Factory:
        def __call__(self, *args, **kwargs):
            return _Ctx()

    return _Factory()


@pytest.fixture()
def mock_engine_and_session(db_session: AsyncSession):
    fake_engine = MagicMock()
    fake_engine.dispose = AsyncMock()
    with (
        patch("sqlalchemy.ext.asyncio.create_async_engine", return_value=fake_engine),
        patch("sqlalchemy.ext.asyncio.async_sessionmaker", return_value=_session_factory(db_session)),
    ):
        yield fake_engine


# ---------------------------------------------------------------------------
# TestDoScanNotApplicable — non-S3 backend takes the fast early-return path
# ---------------------------------------------------------------------------


class TestDoScanNotApplicable:
    async def test_returns_not_applicable_flag(self):
        mock_settings = MagicMock()
        mock_settings.storage_backend = "local"
        mock_settings.redis_url = "redis://localhost:6379/0"

        with (
            patch("app.config.get_settings", return_value=mock_settings),
            patch("redis.from_url", return_value=MagicMock()),
        ):
            result = await _do_scan()

        assert result["not_applicable"] is True

    async def test_returns_zero_counts(self):
        mock_settings = MagicMock()
        mock_settings.storage_backend = "local"
        mock_settings.redis_url = "redis://localhost:6379/0"

        with (
            patch("app.config.get_settings", return_value=mock_settings),
            patch("redis.from_url", return_value=MagicMock()),
        ):
            result = await _do_scan()

        assert result["orphaned_count"] == 0
        assert result["total_s3_keys"] == 0
        assert result["total_db_paths"] == 0

    async def test_returns_expected_keys(self):
        mock_settings = MagicMock()
        mock_settings.storage_backend = "local"
        mock_settings.redis_url = "redis://localhost:6379/0"

        with (
            patch("app.config.get_settings", return_value=mock_settings),
            patch("redis.from_url", return_value=MagicMock()),
        ):
            result = await _do_scan()

        for key in ("total_s3_keys", "total_db_paths", "orphaned_count", "orphaned_files", "not_applicable"):
            assert key in result

    async def test_stores_summary_to_redis(self):
        mock_settings = MagicMock()
        mock_settings.storage_backend = "local"
        mock_settings.redis_url = "redis://localhost:6379/0"

        mock_client = MagicMock()
        with (
            patch("app.config.get_settings", return_value=mock_settings),
            patch("redis.from_url", return_value=mock_client),
        ):
            await _do_scan()

        mock_client.set.assert_called_once()
        _key, stored_json = mock_client.set.call_args[0]
        stored = json.loads(stored_json)
        assert stored["not_applicable"] is True


# ---------------------------------------------------------------------------
# TestStoreSummary — _store_s3_summary Redis writes
# ---------------------------------------------------------------------------


class TestStoreSummary:
    def test_writes_to_correct_redis_key(self):
        mock_settings = MagicMock()
        mock_settings.redis_url = "redis://localhost:6379/0"
        mock_client = MagicMock()

        with patch("redis.from_url", return_value=mock_client):
            _store_s3_summary(mock_settings, 5)

        mock_client.set.assert_called_once()
        key = mock_client.set.call_args[0][0]
        assert key == S3_AUDIT_SUMMARY_KEY

    def test_stores_orphaned_count(self):
        mock_settings = MagicMock()
        mock_settings.redis_url = "redis://localhost:6379/0"
        mock_client = MagicMock()

        with patch("redis.from_url", return_value=mock_client):
            _store_s3_summary(mock_settings, 7)

        _key, value = mock_client.set.call_args[0]
        data = json.loads(value)
        assert data["orphaned_count"] == 7

    def test_stores_not_applicable_flag(self):
        mock_settings = MagicMock()
        mock_settings.redis_url = "redis://localhost:6379/0"
        mock_client = MagicMock()

        with patch("redis.from_url", return_value=mock_client):
            _store_s3_summary(mock_settings, 0, not_applicable=True)

        _key, value = mock_client.set.call_args[0]
        data = json.loads(value)
        assert data["not_applicable"] is True

    def test_stores_scanned_at_timestamp(self):
        mock_settings = MagicMock()
        mock_settings.redis_url = "redis://localhost:6379/0"
        mock_client = MagicMock()

        with patch("redis.from_url", return_value=mock_client):
            _store_s3_summary(mock_settings, 3)

        _key, value = mock_client.set.call_args[0]
        data = json.loads(value)
        assert "scanned_at" in data

    def test_swallows_redis_exception(self):
        mock_settings = MagicMock()
        mock_settings.redis_url = "redis://localhost:6379/0"

        with patch("redis.from_url", side_effect=Exception("redis down")):
            _store_s3_summary(mock_settings, 0)  # must not raise

    def test_closes_redis_client(self):
        mock_settings = MagicMock()
        mock_settings.redis_url = "redis://localhost:6379/0"
        mock_client = MagicMock()

        with patch("redis.from_url", return_value=mock_client):
            _store_s3_summary(mock_settings, 0)

        mock_client.close.assert_called_once()


# ---------------------------------------------------------------------------
# TestDoScanS3Path — full boto3 S3 scan path (storage_backend=s3)
# ---------------------------------------------------------------------------


def _s3_settings(**overrides):
    s = MagicMock()
    s.storage_backend = "s3"
    s.s3_bucket_name = "test-bucket"
    s.s3_endpoint_url = "https://s3.example.com"
    s.s3_access_key_id = "AKID"
    s.s3_secret_access_key = "secret"
    s.s3_region = "us-east-1"
    s.redis_url = "redis://localhost:6379/0"
    for k, v in overrides.items():
        setattr(s, k, v)
    return s


def _mock_s3(pages: list[dict]):
    paginator = MagicMock()
    paginator.paginate.return_value = iter(pages)
    client = MagicMock()
    client.get_paginator.return_value = paginator
    return client


class TestDoScanS3Path:
    async def test_returns_not_applicable_false(self, db_session, mock_engine_and_session):
        s3 = _mock_s3([{"Contents": []}])
        with (
            patch("app.config.get_settings", return_value=_s3_settings()),
            patch("boto3.client", return_value=s3),
            patch("redis.from_url", return_value=MagicMock()),
        ):
            result = await _do_scan()

        assert result["not_applicable"] is False

    async def test_returns_expected_keys(self, db_session, mock_engine_and_session):
        s3 = _mock_s3([{"Contents": []}])
        with (
            patch("app.config.get_settings", return_value=_s3_settings()),
            patch("boto3.client", return_value=s3),
            patch("redis.from_url", return_value=MagicMock()),
        ):
            result = await _do_scan()

        for key in ("total_s3_keys", "total_db_paths", "orphaned_count", "orphaned_files", "not_applicable"):
            assert key in result

    async def test_empty_bucket_produces_zero_orphans(self, db_session, mock_engine_and_session):
        s3 = _mock_s3([{}])  # page with no Contents key
        with (
            patch("app.config.get_settings", return_value=_s3_settings()),
            patch("boto3.client", return_value=s3),
            patch("redis.from_url", return_value=MagicMock()),
        ):
            result = await _do_scan()

        assert result["orphaned_count"] == 0
        assert result["total_s3_keys"] == 0

    async def test_detects_orphaned_file(self, db_session, mock_engine_and_session):
        orphan_key = "drafts/orphaned-file.wif"
        page = {"Contents": [{"Key": orphan_key, "Size": 512, "LastModified": datetime.now(timezone.utc)}]}
        s3 = _mock_s3([page])

        with (
            patch("app.config.get_settings", return_value=_s3_settings()),
            patch("boto3.client", return_value=s3),
            patch("redis.from_url", return_value=MagicMock()),
        ):
            result = await _do_scan()

        assert result["orphaned_count"] >= 1
        assert any(f["key"] == orphan_key for f in result["orphaned_files"])

    async def test_known_db_path_not_orphaned(self, db_session, test_user, mock_engine_and_session):
        import app.services.storage as _storage
        from app.models.draft import Draft

        wif_key = f"drafts/known-{uuid.uuid4().hex}.wif"
        _storage._put(wif_key, b"WIF content")

        draft = Draft(
            id=uuid.uuid4(),
            owner_id=test_user.id,
            name="Known Draft",
            wif_filename="known.wif",
            wif_path=wif_key,
        )
        db_session.add(draft)
        await db_session.commit()

        page = {"Contents": [{"Key": wif_key, "Size": 11, "LastModified": datetime.now(timezone.utc)}]}
        s3 = _mock_s3([page])

        with (
            patch("app.config.get_settings", return_value=_s3_settings()),
            patch("boto3.client", return_value=s3),
            patch("redis.from_url", return_value=MagicMock()),
        ):
            result = await _do_scan()

        assert result["orphaned_count"] == 0
        assert result["total_s3_keys"] == 1

    async def test_calls_store_summary_with_orphan_count(self, db_session, mock_engine_and_session):
        orphan_key = "stale/file.jpg"
        page = {"Contents": [{"Key": orphan_key, "Size": 100, "LastModified": datetime.now(timezone.utc)}]}
        s3 = _mock_s3([page])

        with (
            patch("app.config.get_settings", return_value=_s3_settings()),
            patch("boto3.client", return_value=s3),
            patch("redis.from_url", return_value=MagicMock()) as mock_redis,
        ):
            result = await _do_scan()

        assert result["orphaned_count"] >= 1
        mock_redis.assert_called()

    async def test_disposes_engine(self, db_session, mock_engine_and_session):
        s3 = _mock_s3([{"Contents": []}])
        with (
            patch("app.config.get_settings", return_value=_s3_settings()),
            patch("boto3.client", return_value=s3),
            patch("redis.from_url", return_value=MagicMock()),
        ):
            await _do_scan()

        mock_engine_and_session.dispose.assert_called_once()


# ---------------------------------------------------------------------------
# TestCeleryWrapper — cover line 28 (asyncio.run wrapper)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# TestDoScanS3PathWithAssets — photo/receipt paths collected from DB models
# ---------------------------------------------------------------------------


class TestDoScanS3PathWithAssets:
    async def test_yarn_photo_path_not_orphaned(self, db_session, test_user, mock_engine_and_session):
        # Covers lines 86-87: yarn.photo_path is collected into db_paths
        import app.services.storage as _storage
        from app.models.yarn import Yarn

        photo_key = f"yarn/{uuid.uuid4().hex}/photo.jpg"
        _storage._put(photo_key, b"fake-jpg")

        yarn = Yarn(
            id=uuid.uuid4(),
            owner_id=test_user.id,
            brand="TestBrand",
            name="TestYarn",
            photo_path=photo_key,
        )
        db_session.add(yarn)
        await db_session.commit()

        page = {"Contents": [{"Key": photo_key, "Size": 8, "LastModified": datetime.now(timezone.utc)}]}
        s3 = _mock_s3([page])

        with (
            patch("app.config.get_settings", return_value=_s3_settings()),
            patch("boto3.client", return_value=s3),
            patch("redis.from_url", return_value=MagicMock()),
        ):
            result = await _do_scan()

        assert result["orphaned_count"] == 0

    async def test_loom_photo_path_not_orphaned(self, db_session, test_user, mock_engine_and_session):
        # Covers lines 91-92: loom.photo_path is collected into db_paths
        import app.services.storage as _storage
        from app.models.loom import Loom

        photo_key = f"looms/{uuid.uuid4().hex}/photo.jpg"
        _storage._put(photo_key, b"fake-jpg")

        loom = Loom(
            id=uuid.uuid4(),
            owner_id=test_user.id,
            loom_type="table",
            manufacturer="BrandX",
            model_name="TestLoom",
            photo_path=photo_key,
        )
        db_session.add(loom)
        await db_session.commit()

        page = {"Contents": [{"Key": photo_key, "Size": 8, "LastModified": datetime.now(timezone.utc)}]}
        s3 = _mock_s3([page])

        with (
            patch("app.config.get_settings", return_value=_s3_settings()),
            patch("boto3.client", return_value=s3),
            patch("redis.from_url", return_value=MagicMock()),
        ):
            result = await _do_scan()

        assert result["orphaned_count"] == 0

    async def test_loom_version_photo_path_not_orphaned(self, db_session, test_user, mock_engine_and_session):
        # Covers lines 96-97: loom_version_photo.path is collected into db_paths
        from datetime import date

        import app.services.storage as _storage
        from app.models.loom import Loom, LoomVersion, LoomVersionPhoto

        photo_key = f"loom-version-photos/{uuid.uuid4().hex}/photo.jpg"
        _storage._put(photo_key, b"fake-jpg")

        loom = Loom(
            id=uuid.uuid4(),
            owner_id=test_user.id,
            loom_type="table",
            manufacturer="BrandX",
            model_name="TestLoom2",
        )
        db_session.add(loom)
        await db_session.flush()

        version = LoomVersion(
            id=uuid.uuid4(),
            loom_id=loom.id,
            version_number=1,
            effective_date=date.today(),
        )
        db_session.add(version)
        await db_session.flush()

        vp = LoomVersionPhoto(
            id=uuid.uuid4(),
            loom_version_id=version.id,
            filename="photo.jpg",
            path=photo_key,
        )
        db_session.add(vp)
        await db_session.commit()

        page = {"Contents": [{"Key": photo_key, "Size": 8, "LastModified": datetime.now(timezone.utc)}]}
        s3 = _mock_s3([page])

        with (
            patch("app.config.get_settings", return_value=_s3_settings()),
            patch("boto3.client", return_value=s3),
            patch("redis.from_url", return_value=MagicMock()),
        ):
            result = await _do_scan()

        assert result["orphaned_count"] == 0

    async def test_loom_version_receipt_path_not_orphaned(self, db_session, test_user, mock_engine_and_session):
        # Covers lines 101-102: loom_version_receipt.path is collected into db_paths
        from datetime import date

        import app.services.storage as _storage
        from app.models.loom import Loom, LoomVersion, LoomVersionReceipt

        receipt_key = f"loom-version-receipts/{uuid.uuid4().hex}/receipt.pdf"
        _storage._put(receipt_key, b"fake-pdf")

        loom = Loom(
            id=uuid.uuid4(),
            owner_id=test_user.id,
            loom_type="floor",
            manufacturer="BrandY",
            model_name="FloorLoom",
        )
        db_session.add(loom)
        await db_session.flush()

        version = LoomVersion(
            id=uuid.uuid4(),
            loom_id=loom.id,
            version_number=1,
            effective_date=date.today(),
        )
        db_session.add(version)
        await db_session.flush()

        vr = LoomVersionReceipt(
            id=uuid.uuid4(),
            loom_version_id=version.id,
            filename="receipt.pdf",
            path=receipt_key,
        )
        db_session.add(vr)
        await db_session.commit()

        page = {"Contents": [{"Key": receipt_key, "Size": 8, "LastModified": datetime.now(timezone.utc)}]}
        s3 = _mock_s3([page])

        with (
            patch("app.config.get_settings", return_value=_s3_settings()),
            patch("boto3.client", return_value=s3),
            patch("redis.from_url", return_value=MagicMock()),
        ):
            result = await _do_scan()

        assert result["orphaned_count"] == 0

    async def test_project_photo_path_not_orphaned(self, db_session, test_user, mock_engine_and_session):
        # Covers lines 106-107: project_photo.file_path is collected into db_paths
        import app.services.storage as _storage
        from app.models.draft import Draft
        from app.models.project import Project, ProjectPhoto

        photo_key = f"project-photos/{uuid.uuid4().hex}/photo.jpg"
        _storage._put(photo_key, b"fake-jpg")

        draft = Draft(
            id=uuid.uuid4(),
            owner_id=test_user.id,
            name="PPDraft",
            wif_filename="pp.wif",
            wif_path="drafts/pp.wif",
        )
        db_session.add(draft)
        await db_session.flush()

        project = Project(
            id=uuid.uuid4(),
            owner_id=test_user.id,
            draft_id=draft.id,
            name="PPProject",
            project_type="treadle",
            total_picks=4,
        )
        db_session.add(project)
        await db_session.flush()

        pp = ProjectPhoto(
            id=uuid.uuid4(),
            project_id=project.id,
            file_path=photo_key,
            filename="photo.jpg",
        )
        db_session.add(pp)
        await db_session.commit()

        page = {"Contents": [{"Key": photo_key, "Size": 8, "LastModified": datetime.now(timezone.utc)}]}
        s3 = _mock_s3([page])

        with (
            patch("app.config.get_settings", return_value=_s3_settings()),
            patch("boto3.client", return_value=s3),
            patch("redis.from_url", return_value=MagicMock()),
        ):
            result = await _do_scan()

        assert result["orphaned_count"] == 0


class TestCeleryWrapper:
    def test_run_s3_orphan_scan_delegates(self):
        from app.tasks.s3_audit import run_s3_orphan_scan

        task_mock = MagicMock()

        with patch(
            "app.tasks.s3_audit._do_scan",
            new=AsyncMock(return_value={"orphaned_count": 0, "not_applicable": True}),
        ):
            result = run_s3_orphan_scan.run.__func__(task_mock)

        assert result["orphaned_count"] == 0
