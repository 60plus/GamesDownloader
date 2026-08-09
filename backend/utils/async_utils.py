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


# Bound the fan-out of media downloads during scraping. The default number is
# deliberately small so a burst of screenshots can never open more connections
# to a rate-limited source (ScreenScraper counts simultaneous requests) than a
# careful human would.
DEFAULT_MEDIA_CONCURRENCY = 4


async def gather_bounded(coros: list, *, parallel: bool, limit: int = DEFAULT_MEDIA_CONCURRENCY) -> list:
    """Await *coros* and return their results in the original order.

    parallel=False awaits them strictly one at a time - byte-for-byte the old
    sequential behaviour, and the cautious choice for a rate-limited API.
    parallel=True runs them concurrently but never more than *limit* at once, so
    a fan-out of many downloads cannot flood the source.

    The coroutines are expected to swallow their own errors (return a sentinel
    like None on failure); this helper does not catch, so an exception from one
    coroutine surfaces to the caller exactly as a bare ``await`` would.
    """
    if not coros:
        return []
    if not parallel:
        return [await c for c in coros]
    sem = asyncio.Semaphore(max(1, limit))

    async def _guard(c):
        async with sem:
            return await c

    return await asyncio.gather(*[_guard(c) for c in coros])
