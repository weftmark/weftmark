"""Celery tasks for reference data seeding.

seed_loom_references — called by post_migrate backfill when loom_references is empty.
Idempotent: the underlying seed() upserts on (brand, model_name), so re-running
on a populated table updates existing rows and inserts any new ones.
"""

from __future__ import annotations

import asyncio
import logging

from celery import Task

from app.celery_app import celery_app

log = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    max_retries=0,
    soft_time_limit=120,
    time_limit=180,
    name="app.tasks.seeds.seed_loom_references",
)
def seed_loom_references(self: Task) -> dict:
    """Seed loom_references from loom-data-master.json."""
    return asyncio.run(_seed())


async def _seed() -> dict:
    from seeds.loom_references import seed

    result = await seed()
    log.info(
        "seed_loom_references inserted=%d updated=%d skipped=%d",
        result.get("inserted", 0),
        result.get("updated", 0),
        result.get("skipped", 0),
    )
    return result
