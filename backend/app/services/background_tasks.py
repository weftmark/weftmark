"""Fire-and-forget asyncio task helper (SonarCloud python:S7502).

asyncio.create_task() does not keep a strong reference to the returned
Task — without one held somewhere, the event loop is free to garbage
collect the task mid-flight. This module holds that reference until
the task completes.
"""

from __future__ import annotations

import asyncio
from collections.abc import Coroutine
from typing import Any

_background_tasks: set[asyncio.Task] = set()


def fire_and_forget(coro: Coroutine[Any, Any, Any]) -> asyncio.Task:
    task = asyncio.create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return task
