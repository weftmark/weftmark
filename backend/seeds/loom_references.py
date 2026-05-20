"""CLI wrapper — seeds loom_references from loom-data-master.json.

Usage (from repo root):
    docker exec weaving_site_backend python seeds/loom_references.py
    docker exec weftmark-dev_backend python seeds/loom_references.py

Idempotent — upserts on (brand, model_name). Safe to re-run.
Core logic lives in app.services.loom_seed so the Celery task can import it.
"""

from __future__ import annotations

import asyncio
import logging
import sys


async def main() -> None:
    from app.services.loom_seed import seed

    result = await seed()
    print(f"Seed complete: {result['inserted']} inserted, {result['updated']} updated, {result['skipped']} skipped")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    asyncio.run(main())
