"""Tests for app.services.storage_quota."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.services.storage_quota import MAX_USER_STORAGE_BYTES, _s3_head, check_storage_quota, get_user_files_report


class TestCheckStorageQuota:
    async def test_raises_when_quota_exceeded(self):
        user_id = uuid.uuid4()
        with patch(
            "app.services.storage_quota.get_user_storage_used",
            new=AsyncMock(return_value=MAX_USER_STORAGE_BYTES),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await check_storage_quota(user_id, db=None, incoming_bytes=1)
        assert exc_info.value.status_code == 400
        assert "Storage limit reached" in exc_info.value.detail
        assert "500 MB" in exc_info.value.detail

    async def test_passes_when_within_quota(self):
        user_id = uuid.uuid4()
        with patch(
            "app.services.storage_quota.get_user_storage_used",
            new=AsyncMock(return_value=0),
        ):
            await check_storage_quota(user_id, db=None, incoming_bytes=1024)

    async def test_passes_at_exact_limit(self):
        user_id = uuid.uuid4()
        with patch(
            "app.services.storage_quota.get_user_storage_used",
            new=AsyncMock(return_value=MAX_USER_STORAGE_BYTES),
        ):
            await check_storage_quota(user_id, db=None, incoming_bytes=0)

    async def test_raises_with_correct_mb_in_message(self):
        user_id = uuid.uuid4()
        used_bytes = 300 * 1024 * 1024  # 300 MB
        with patch(
            "app.services.storage_quota.get_user_storage_used",
            new=AsyncMock(return_value=used_bytes),
        ):
            with pytest.raises(HTTPException) as exc_info:
                await check_storage_quota(user_id, db=None, incoming_bytes=MAX_USER_STORAGE_BYTES)
        assert "300 MB" in exc_info.value.detail


# ---------------------------------------------------------------------------
# _s3_head — local filesystem backend
# ---------------------------------------------------------------------------


class TestS3HeadLocalBackend:
    def test_missing_key_returns_false(self, tmp_path, monkeypatch):
        from app.config import get_settings

        monkeypatch.setattr(get_settings(), "storage_backend", "local")
        monkeypatch.setattr(get_settings(), "upload_dir", str(tmp_path))
        exists, size = _s3_head("drafts/nonexistent.wif")
        assert exists is False
        assert size is None

    def test_existing_key_returns_true_with_size(self, tmp_path, monkeypatch):
        from app.config import get_settings

        monkeypatch.setattr(get_settings(), "storage_backend", "local")
        monkeypatch.setattr(get_settings(), "upload_dir", str(tmp_path))
        (tmp_path / "test.wif").write_bytes(b"hello")
        exists, size = _s3_head("test.wif")
        assert exists is True
        assert size == 5


class TestS3HeadS3Backend:
    def test_existing_key_returns_true(self, monkeypatch):
        from app.config import get_settings

        monkeypatch.setattr(get_settings(), "storage_backend", "s3")
        monkeypatch.setattr(get_settings(), "s3_bucket_name", "test-bucket")
        mock_client = MagicMock()
        mock_client.head_object.return_value = {"ContentLength": 1024}
        with patch("app.services.storage._s3", return_value=mock_client):
            exists, size = _s3_head("drafts/file.wif")
        assert exists is True
        assert size == 1024

    def test_missing_key_returns_false(self, monkeypatch):
        from botocore.exceptions import ClientError

        from app.config import get_settings

        monkeypatch.setattr(get_settings(), "storage_backend", "s3")
        monkeypatch.setattr(get_settings(), "s3_bucket_name", "test-bucket")
        mock_client = MagicMock()
        mock_client.head_object.side_effect = ClientError({"Error": {"Code": "404"}}, "HeadObject")
        with patch("app.services.storage._s3", return_value=mock_client):
            exists, size = _s3_head("drafts/missing.wif")
        assert exists is False
        assert size is None


# ---------------------------------------------------------------------------
# get_user_files_report — optional path branches
# ---------------------------------------------------------------------------


class TestGetUserFilesReport:
    @pytest.mark.asyncio
    async def test_returns_empty_for_user_with_no_files(self, db_session, test_user):
        result = await get_user_files_report(db_session, test_user.id)
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_draft_wif_modified_path_included(self, db_session, test_user):
        import app.services.storage as storage
        from app.models.draft import Draft

        draft = Draft(
            id=uuid.uuid4(),
            owner_id=test_user.id,
            name="Test Draft",
            wif_filename="test.wif",
            wif_path=storage.save_wif(uuid.uuid4(), "test.wif", b"[WIF]"),
            wif_modified_path=storage.save_wif(uuid.uuid4(), "test_modified.wif", b"[WIF]"),
        )
        db_session.add(draft)
        await db_session.commit()

        result = await get_user_files_report(db_session, test_user.id)
        types = [f["entity_type"] for f in result]
        assert "draft_wif_modified" in types

    @pytest.mark.asyncio
    async def test_draft_preview_path_included(self, db_session, test_user):
        import app.services.storage as storage
        from app.models.draft import Draft

        draft = Draft(
            id=uuid.uuid4(),
            owner_id=test_user.id,
            name="Test Draft 2",
            wif_filename="test.wif",
            wif_path=storage.save_wif(uuid.uuid4(), "test.wif", b"[WIF]"),
            preview_path="previews/fake_preview.svg",
            drawdown_preview_path="drawdown-previews/fake.png",
        )
        db_session.add(draft)
        await db_session.commit()

        result = await get_user_files_report(db_session, test_user.id)
        types = [f["entity_type"] for f in result]
        assert "draft_preview" in types
        assert "draft_drawdown_preview" in types

    @pytest.mark.asyncio
    async def test_verify_s3_true_populates_s3_fields(self, db_session, test_user):
        import app.services.storage as storage
        from app.models.draft import Draft

        draft = Draft(
            id=uuid.uuid4(),
            owner_id=test_user.id,
            name="Verify Draft",
            wif_filename="test.wif",
            wif_path=storage.save_wif(uuid.uuid4(), "test.wif", b"[WIF]"),
        )
        db_session.add(draft)
        await db_session.commit()

        with patch("app.services.storage_quota._s3_head", return_value=(True, 42)):
            result = await get_user_files_report(db_session, test_user.id, verify_s3=True)

        assert len(result) >= 1
        for f in result:
            assert f["s3_verified"] is True
            assert f["exists_in_s3"] is True
            assert f["size_bytes"] == 42

    @pytest.mark.asyncio
    async def test_verify_s3_missing_file_marks_not_existing(self, db_session, test_user):
        import app.services.storage as storage
        from app.models.draft import Draft

        draft = Draft(
            id=uuid.uuid4(),
            owner_id=test_user.id,
            name="Missing Verify Draft",
            wif_filename="test.wif",
            wif_path=storage.save_wif(uuid.uuid4(), "test.wif", b"[WIF]"),
        )
        db_session.add(draft)
        await db_session.commit()

        with patch("app.services.storage_quota._s3_head", return_value=(False, None)):
            result = await get_user_files_report(db_session, test_user.id, verify_s3=True)

        assert len(result) >= 1
        for f in result:
            assert f["s3_verified"] is True
            assert f["exists_in_s3"] is False
