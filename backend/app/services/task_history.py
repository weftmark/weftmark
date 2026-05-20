"""Lightweight Redis-backed task execution history.

Records queued/started/completed events for Celery tasks.
Stores the most recent HISTORY_MAX entries in a Redis sorted set
scored by queued_at timestamp; per-task metadata in individual keys.
All operations are best-effort — failures are silently swallowed so
they never affect the task itself.
"""

import json
import time as _time
from datetime import datetime, timezone

HISTORY_ZSET_KEY = "weftmark:task_history"
HISTORY_META_PREFIX = "weftmark:task_history:meta:"
HISTORY_MAX = 500
META_TTL = 7 * 86400  # 7 days


def _client(settings):
    import redis as _redis

    return _redis.from_url(settings.redis_url, socket_connect_timeout=2)


def record_queued(settings, task_id: str, name: str, caller: str) -> None:
    queued_at = _time.time()
    meta = {
        "task_id": task_id,
        "name": name,
        "caller": caller,
        "state": "queued",
        "queued_at": queued_at,
        "started_at": None,
        "completed_at": None,
        "error": None,
    }
    try:
        client = _client(settings)
        client.set(f"{HISTORY_META_PREFIX}{task_id}", json.dumps(meta), ex=META_TTL)
        client.zadd(HISTORY_ZSET_KEY, {task_id: queued_at})
        client.zremrangebyrank(HISTORY_ZSET_KEY, 0, -(HISTORY_MAX + 1))
        client.close()
    except Exception:
        pass


def record_started(settings, task_id: str) -> None:
    started_at = _time.time()
    try:
        client = _client(settings)
        raw = client.get(f"{HISTORY_META_PREFIX}{task_id}")
        if raw:
            meta = json.loads(raw)
            meta["state"] = "running"
            meta["started_at"] = started_at
            client.set(f"{HISTORY_META_PREFIX}{task_id}", json.dumps(meta), ex=META_TTL)
        client.close()
    except Exception:
        pass


def record_completed(settings, task_id: str, state: str, error: str | None = None) -> None:
    completed_at = _time.time()
    try:
        client = _client(settings)
        raw = client.get(f"{HISTORY_META_PREFIX}{task_id}")
        if raw:
            meta = json.loads(raw)
            meta["state"] = state
            meta["completed_at"] = completed_at
            if error:
                meta["error"] = str(error)[:500]
            client.set(f"{HISTORY_META_PREFIX}{task_id}", json.dumps(meta), ex=META_TTL)
        client.close()
    except Exception:
        pass


def get_history(settings, page: int = 1, page_size: int = 25) -> tuple[list[dict], int]:
    try:
        client = _client(settings)
        total = client.zcard(HISTORY_ZSET_KEY)
        start = (page - 1) * page_size
        end = start + page_size - 1
        task_ids = client.zrevrange(HISTORY_ZSET_KEY, start, end)
        items = []
        for tid in task_ids:
            tid_str = tid.decode() if isinstance(tid, bytes) else tid
            raw = client.get(f"{HISTORY_META_PREFIX}{tid_str}")
            if raw:
                items.append(json.loads(raw))
        client.close()
        return items, int(total)
    except Exception:
        return [], 0


def _iso(ts: float | None) -> str | None:
    if ts is None:
        return None
    return datetime.fromtimestamp(ts, timezone.utc).isoformat()
