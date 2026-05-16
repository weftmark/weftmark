"""Post-migration backfill orchestrator.

Dispatched automatically via the worker_ready signal in celery_app.py whenever a
worker starts. Each registered backfill declares:

  - a human-readable name
  - a SQL condition that returns the count of rows still needing backfill
  - the Celery task to dispatch when that count is > 0

Running this task on a fully up-to-date database is always a no-op — every
backfill checks its own null condition before dispatching.

Duplicate-dispatch guard: a Redis key (SETNX + TTL) prevents multiple workers
starting simultaneously from all dispatching the same backfill. The key expires
after DISPATCH_LOCK_TTL_S seconds so that a Redis flush or a legitimate
subsequent deploy can still trigger a re-run.
"""

from __future__ import annotations

import logging

import redis as _redis
from celery import Task

from app.celery_app import celery_app

log = logging.getLogger(__name__)

# How long the Redis dispatch-lock key lives. After this window, a re-dispatch
# is allowed (e.g. after a Redis flush or a second deploy on the same day).
DISPATCH_LOCK_TTL_S = 3600  # 1 hour

_REDIS_KEY_PREFIX = "weftmark:post_migrate:"


# ---------------------------------------------------------------------------
# Backfill registry
# ---------------------------------------------------------------------------
# Each entry is a dict with:
#   name        — unique slug; used as the Redis lock key suffix and in logs
#   description — human-readable description for log messages
#   condition   — SQL fragment returning a count of rows that still need work;
#                 if count > 0 the backfill is dispatched
#   dispatch    — callable that dispatches the Celery task and returns the task result
#
# To add a new backfill: append an entry here. No other files need changing.
# ---------------------------------------------------------------------------


def _backfill_registry() -> list[dict]:
    from app.tasks.preview import backfill_all_drawdown_previews, backfill_all_project_drawdown_previews
    from app.tasks.reparse import reparse_all_drafts

    return [
        {
            "name": "reparse_drafts",
            "description": "Backfill wif_colors, wif_measurements, warp_color_stats, weft_color_stats on drafts",
            "condition": (
                "SELECT COUNT(*) FROM drafts WHERE wif_colors IS NULL AND wif_path IS NOT NULL AND deleted_at IS NULL"
            ),
            "dispatch": lambda: reparse_all_drafts.delay(),
        },
        {
            "name": "drawdown_preview",
            "description": "Pre-render drawdown_preview PNG for drafts missing it",
            "condition": (
                "SELECT COUNT(*) FROM drafts"
                " WHERE drawdown_preview_path IS NULL AND wif_path IS NOT NULL AND deleted_at IS NULL"
            ),
            "dispatch": lambda: backfill_all_drawdown_previews.delay(),
        },
        {
            "name": "project_drawdown_preview",
            "description": "Pre-render drawdown_preview PNG for projects missing it",
            "condition": ("SELECT COUNT(*) FROM projects WHERE drawdown_preview_path IS NULL AND deleted_at IS NULL"),
            "dispatch": lambda: backfill_all_project_drawdown_previews.delay(),
        },
    ]


# ---------------------------------------------------------------------------
# Task
# ---------------------------------------------------------------------------


@celery_app.task(
    bind=True,
    max_retries=0,
    soft_time_limit=60,
    time_limit=90,
    name="app.tasks.post_migrate.run_post_migrate_backfills",
)
def run_post_migrate_backfills(self: Task) -> dict:
    """Check all registered post-migration backfills and dispatch any that are needed."""
    return _run()


def _run() -> dict:
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import Session

    from app.config import get_settings

    settings = get_settings()
    engine = create_engine(settings.database_url_sync)
    dispatched: list[str] = []
    skipped: list[str] = []

    try:
        client = _redis.from_url(settings.redis_url, socket_connect_timeout=2)
        try:
            registry = _backfill_registry()
            with Session(engine) as db:
                for entry in registry:
                    name: str = entry["name"]
                    redis_key = f"{_REDIS_KEY_PREFIX}{name}"

                    null_count: int = db.execute(text(entry["condition"])).scalar() or 0
                    if null_count == 0:
                        skipped.append(f"{name}:no_null_rows")
                        log.debug("post_migrate_skip name=%s reason=no_null_rows", name)
                        continue

                    # Atomic SETNX: only the first worker through this window wins.
                    acquired = client.set(redis_key, "1", nx=True, ex=DISPATCH_LOCK_TTL_S)
                    if not acquired:
                        skipped.append(f"{name}:lock_held")
                        log.info("post_migrate_skip name=%s reason=lock_held null_rows=%d", name, null_count)
                        continue

                    try:
                        entry["dispatch"]()
                        dispatched.append(f"{name}(null_rows={null_count})")
                        log.info(
                            "post_migrate_dispatch name=%s null_rows=%d description=%r",
                            name,
                            null_count,
                            entry["description"],
                        )
                    except Exception:
                        # Release the lock so the next worker can retry.
                        client.delete(redis_key)
                        log.exception("post_migrate_dispatch_error name=%s", name)
        finally:
            client.close()
    finally:
        engine.dispose()

    result = {"dispatched": dispatched, "skipped": skipped}
    log.info("post_migrate_backfills_complete dispatched=%d skipped=%d", len(dispatched), len(skipped))
    return result
