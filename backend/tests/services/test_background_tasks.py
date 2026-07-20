"""Tests for app.services.background_tasks."""

import asyncio

import pytest

from app.services.background_tasks import _background_tasks, fire_and_forget


async def test_fire_and_forget_returns_task_and_runs_coro():
    ran = False

    async def _coro():
        nonlocal ran
        ran = True

    task = fire_and_forget(_coro())
    assert isinstance(task, asyncio.Task)

    await task

    assert ran is True


async def test_fire_and_forget_holds_strong_reference_until_done():
    async def _coro():
        await asyncio.sleep(0)

    task = fire_and_forget(_coro())

    assert task in _background_tasks

    await task

    assert task not in _background_tasks


async def test_fire_and_forget_discards_on_exception():
    async def _coro():
        raise ValueError("boom")

    task = fire_and_forget(_coro())

    with pytest.raises(ValueError, match="boom"):
        await task

    assert task not in _background_tasks
