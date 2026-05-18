"""Tests for app.services.task_history."""

import json
import time
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from app.services.task_history import (
    HISTORY_MAX,
    HISTORY_META_PREFIX,
    HISTORY_ZSET_KEY,
    _iso,
    get_history,
    record_completed,
    record_queued,
    record_started,
)


def _mock_settings(redis_url="redis://localhost:6379/0"):
    return MagicMock(redis_url=redis_url)


def _mock_redis(*, get_return=None):
    client = MagicMock()
    client.get.return_value = get_return
    return client


class TestIso:
    def test_returns_none_for_none(self):
        assert _iso(None) is None

    def test_returns_isoformat_string(self):
        ts = 1_700_000_000.0
        result = _iso(ts)
        assert isinstance(result, str)
        dt = datetime.fromisoformat(result)
        assert dt.tzinfo is not None

    def test_utc_timezone(self):
        ts = 1_700_000_000.0
        result = _iso(ts)
        dt = datetime.fromisoformat(result)
        assert dt.tzinfo == timezone.utc or "UTC" in str(dt.tzinfo) or "+00:00" in result


class TestRecordQueued:
    def test_sets_meta_key(self):
        settings = _mock_settings()
        client = _mock_redis()
        task_id = str(uuid.uuid4())

        with patch("app.services.task_history._client", return_value=client):
            record_queued(settings, task_id, "my.task", "caller")

        client.set.assert_called_once()
        key_arg = client.set.call_args[0][0]
        assert key_arg == f"{HISTORY_META_PREFIX}{task_id}"

    def test_adds_to_zset(self):
        settings = _mock_settings()
        client = _mock_redis()
        task_id = str(uuid.uuid4())

        with patch("app.services.task_history._client", return_value=client):
            record_queued(settings, task_id, "my.task", "caller")

        client.zadd.assert_called_once()
        zset_key = client.zadd.call_args[0][0]
        assert zset_key == HISTORY_ZSET_KEY

    def test_trims_to_history_max(self):
        settings = _mock_settings()
        client = _mock_redis()

        with patch("app.services.task_history._client", return_value=client):
            record_queued(settings, str(uuid.uuid4()), "my.task", "caller")

        client.zremrangebyrank.assert_called_once_with(HISTORY_ZSET_KEY, 0, -(HISTORY_MAX + 1))

    def test_closes_connection(self):
        settings = _mock_settings()
        client = _mock_redis()

        with patch("app.services.task_history._client", return_value=client):
            record_queued(settings, str(uuid.uuid4()), "my.task", "caller")

        client.close.assert_called_once()

    def test_silently_swallows_redis_error(self):
        settings = _mock_settings()
        client = _mock_redis()
        client.set.side_effect = ConnectionError("redis down")

        with patch("app.services.task_history._client", return_value=client):
            record_queued(settings, str(uuid.uuid4()), "my.task", "caller")  # must not raise

    def test_meta_payload_structure(self):
        settings = _mock_settings()
        client = _mock_redis()
        task_id = str(uuid.uuid4())

        with patch("app.services.task_history._client", return_value=client):
            record_queued(settings, task_id, "my.task", "my_caller")

        raw = client.set.call_args[0][1]
        meta = json.loads(raw)
        assert meta["task_id"] == task_id
        assert meta["name"] == "my.task"
        assert meta["caller"] == "my_caller"
        assert meta["state"] == "queued"
        assert meta["started_at"] is None
        assert meta["completed_at"] is None
        assert meta["error"] is None


class TestRecordStarted:
    def test_updates_state_when_key_exists(self):
        settings = _mock_settings()
        task_id = str(uuid.uuid4())
        existing = json.dumps(
            {
                "task_id": task_id,
                "name": "t",
                "caller": "c",
                "state": "queued",
                "queued_at": time.time(),
                "started_at": None,
                "completed_at": None,
                "error": None,
            }
        )
        client = _mock_redis(get_return=existing.encode())

        with patch("app.services.task_history._client", return_value=client):
            record_started(settings, task_id)

        client.set.assert_called_once()
        raw = client.set.call_args[0][1]
        meta = json.loads(raw)
        assert meta["state"] == "running"
        assert meta["started_at"] is not None

    def test_noop_when_key_missing(self):
        settings = _mock_settings()
        client = _mock_redis(get_return=None)

        with patch("app.services.task_history._client", return_value=client):
            record_started(settings, str(uuid.uuid4()))

        client.set.assert_not_called()

    def test_silently_swallows_error(self):
        settings = _mock_settings()
        client = _mock_redis()
        client.get.side_effect = ConnectionError("redis down")

        with patch("app.services.task_history._client", return_value=client):
            record_started(settings, str(uuid.uuid4()))  # must not raise


class TestRecordCompleted:
    def _existing_meta(self, task_id: str) -> bytes:
        return json.dumps(
            {
                "task_id": task_id,
                "name": "t",
                "caller": "c",
                "state": "running",
                "queued_at": time.time(),
                "started_at": time.time(),
                "completed_at": None,
                "error": None,
            }
        ).encode()

    def test_updates_state_to_success(self):
        settings = _mock_settings()
        task_id = str(uuid.uuid4())
        client = _mock_redis(get_return=self._existing_meta(task_id))

        with patch("app.services.task_history._client", return_value=client):
            record_completed(settings, task_id, "success")

        raw = client.set.call_args[0][1]
        meta = json.loads(raw)
        assert meta["state"] == "success"
        assert meta["completed_at"] is not None

    def test_records_error_message(self):
        settings = _mock_settings()
        task_id = str(uuid.uuid4())
        client = _mock_redis(get_return=self._existing_meta(task_id))

        with patch("app.services.task_history._client", return_value=client):
            record_completed(settings, task_id, "failure", error="boom")

        raw = client.set.call_args[0][1]
        meta = json.loads(raw)
        assert meta["state"] == "failure"
        assert meta["error"] == "boom"

    def test_truncates_long_error(self):
        settings = _mock_settings()
        task_id = str(uuid.uuid4())
        client = _mock_redis(get_return=self._existing_meta(task_id))
        long_error = "x" * 600

        with patch("app.services.task_history._client", return_value=client):
            record_completed(settings, task_id, "failure", error=long_error)

        raw = client.set.call_args[0][1]
        meta = json.loads(raw)
        assert len(meta["error"]) == 500

    def test_noop_when_key_missing(self):
        settings = _mock_settings()
        client = _mock_redis(get_return=None)

        with patch("app.services.task_history._client", return_value=client):
            record_completed(settings, str(uuid.uuid4()), "success")

        client.set.assert_not_called()

    def test_silently_swallows_error(self):
        settings = _mock_settings()
        client = _mock_redis()
        client.get.side_effect = ConnectionError("redis down")

        with patch("app.services.task_history._client", return_value=client):
            record_completed(settings, str(uuid.uuid4()), "success")  # must not raise


class TestGetHistory:
    def test_returns_items_list_and_total(self):
        settings = _mock_settings()
        task_id = str(uuid.uuid4())
        meta = json.dumps({"task_id": task_id, "state": "success"})
        client = _mock_redis()
        client.zcard.return_value = 1
        client.zrevrange.return_value = [task_id.encode()]
        client.get.return_value = meta.encode()

        with patch("app.services.task_history._client", return_value=client):
            items, total = get_history(settings)

        assert total == 1
        assert len(items) == 1
        assert items[0]["task_id"] == task_id

    def test_handles_bytes_task_ids(self):
        settings = _mock_settings()
        task_id = str(uuid.uuid4())
        meta = json.dumps({"task_id": task_id, "state": "success"})
        client = _mock_redis()
        client.zcard.return_value = 1
        client.zrevrange.return_value = [task_id.encode()]
        client.get.return_value = meta.encode()

        with patch("app.services.task_history._client", return_value=client):
            items, total = get_history(settings)

        assert items[0]["task_id"] == task_id

    def test_skips_missing_meta(self):
        settings = _mock_settings()
        client = _mock_redis()
        client.zcard.return_value = 1
        client.zrevrange.return_value = [b"missing-id"]
        client.get.return_value = None

        with patch("app.services.task_history._client", return_value=client):
            items, total = get_history(settings)

        assert items == []

    def test_returns_empty_on_error(self):
        settings = _mock_settings()
        client = _mock_redis()
        client.zcard.side_effect = ConnectionError("redis down")

        with patch("app.services.task_history._client", return_value=client):
            items, total = get_history(settings)

        assert items == []
        assert total == 0

    def test_pagination_uses_page_and_size(self):
        settings = _mock_settings()
        client = _mock_redis()
        client.zcard.return_value = 50
        client.zrevrange.return_value = []

        with patch("app.services.task_history._client", return_value=client):
            get_history(settings, page=2, page_size=10)

        client.zrevrange.assert_called_once_with(HISTORY_ZSET_KEY, 10, 19)
