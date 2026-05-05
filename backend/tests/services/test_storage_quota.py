"""Tests for app.services.storage_quota."""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from app.services.storage_quota import MAX_USER_STORAGE_BYTES, check_storage_quota


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
