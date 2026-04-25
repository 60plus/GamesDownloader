"""Shared async helpers."""
from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)


def fire_task(coro) -> asyncio.Task:
    """Schedule a background coroutine and log any exception it raises."""
    task = asyncio.create_task(coro)
    task.add_done_callback(_log_task_exception)
    return task


def _log_task_exception(task: asyncio.Task) -> None:
    if task.cancelled():
        return
    exc = task.exception()
    if exc:
        logger.warning("Background task failed: %s", exc)
