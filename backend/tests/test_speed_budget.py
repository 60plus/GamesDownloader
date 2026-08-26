"""The download speed limit is shared, so it is actually a limit.

It used to be applied per stream: each response generator slept for its own
chunk against the configured rate with no idea another transfer existed. A user
capped at five megabytes a second who opened four downloads got twenty. Two
separate readings of the codebase found this independently, which is a fair
sign of how invisible it was.

The assertions here are about elapsed time, because that is the only thing that
distinguishes a shared budget from four private ones. They are deliberately
loose at the top end - a slow machine may take longer - and precise at the
bottom, since finishing *too quickly* is the failure being guarded against.
"""
from __future__ import annotations

import asyncio
import time

import pytest

from utils.throttle import SpeedBucket, _buckets, bucket_for, effective_chunk_size

KB = 1024


async def _drain(bucket: SpeedBucket) -> None:
    """Spend the initial fill, so what follows is measured from empty.

    A token bucket starts full on purpose: a short transfer should not be made
    to wait for a budget nobody has used. That burst would otherwise disguise
    the timings below.
    """
    await bucket.take(bucket.rate_kbps * KB)


@pytest.mark.asyncio
async def test_two_transfers_on_one_budget_share_it():
    """The whole point. Two streams at a 10 KB/s cap move 10 KB in a second.

    Before this, each stream slept against the full rate, so the pair would
    have moved 20 KB in that second and the configured limit would have been
    decoration.
    """
    bucket = SpeedBucket(10)
    await _drain(bucket)

    started = time.monotonic()
    await asyncio.gather(bucket.take(5 * KB), bucket.take(5 * KB))
    elapsed = time.monotonic() - started

    assert elapsed >= 0.85, "finished too fast: the two transfers did not share"
    assert elapsed < 3.0


@pytest.mark.asyncio
async def test_separate_budgets_do_not_compete():
    """One user's downloads must not be slowed by another's."""
    first, second = SpeedBucket(10), SpeedBucket(10)
    await _drain(first)
    await _drain(second)

    started = time.monotonic()
    await asyncio.gather(first.take(10 * KB), second.take(10 * KB))
    elapsed = time.monotonic() - started

    # A second each, run side by side. Sharing would have made it two.
    assert elapsed < 1.7, "the two budgets appear to be queueing behind each other"


@pytest.mark.asyncio
async def test_no_limit_means_no_waiting():
    bucket = SpeedBucket(0)
    started = time.monotonic()
    for _ in range(50):
        await bucket.take(8 * 1024 * 1024)
    assert time.monotonic() - started < 0.5


@pytest.mark.asyncio
async def test_a_chunk_larger_than_the_whole_budget_still_completes():
    """Guards a hang, not a slowdown.

    The bucket only ever fills to its capacity, so asking for more than a
    second of budget would wait for a level it could never reach. That is not
    hypothetical: it happens the moment an administrator lowers the limit while
    a transfer is running and a chunk already in flight is suddenly oversized.
    """
    bucket = SpeedBucket(10)
    await _drain(bucket)
    await asyncio.wait_for(bucket.take(11 * KB), timeout=5)


@pytest.mark.asyncio
async def test_lowering_the_limit_reaches_transfers_already_running():
    bucket = bucket_for("user:tester", 100)
    assert bucket_for("user:tester", 25) is bucket, "the budget was not shared"
    assert bucket.rate_kbps == 25


@pytest.mark.asyncio
async def test_one_transfer_waiting_does_not_stop_the_others():
    """It used to sleep holding the lock, so it did.

    Every other transfer on the budget was shut out for the whole of one
    transfer's wait - and a wait can run into minutes once the limit is lowered
    under a chunk size that was decided at the old rate. The point of a shared
    budget is that they share it, not that they queue behind whoever asked
    first.
    """
    bucket = SpeedBucket(1)          # 1 KB/s
    await _drain(bucket)

    big = asyncio.create_task(bucket.take(1 * KB))     # about a second of budget
    await asyncio.sleep(0.05)

    started = time.monotonic()
    await asyncio.wait_for(bucket.take(16), timeout=1.0)
    small_took = time.monotonic() - started

    assert small_took < 0.5, "a small read queued behind a large one's whole wait"
    assert not big.done(), "the large read should still be waiting"
    await asyncio.wait_for(big, timeout=5)


@pytest.mark.asyncio
async def test_lifting_the_limit_releases_what_is_already_waiting():
    """The way out of a mistake in Settings.

    The rate was read once, before the lock was taken, so a transfer that had
    already worked out its wait slept through any change to it. Setting the
    limit back to unlimited did nothing for the transfers it had stopped, which
    is the moment somebody most needs it to.
    """
    bucket = SpeedBucket(1)
    await _drain(bucket)

    waiting = asyncio.create_task(bucket.take(10 * KB))   # ten seconds of budget
    await asyncio.sleep(0.05)
    assert not waiting.done()

    bucket.rate_kbps = 0                                  # no limit
    started = time.monotonic()
    await asyncio.wait_for(waiting, timeout=2)
    assert time.monotonic() - started < 1.0, "it slept through the change"


@pytest.mark.asyncio
async def test_a_paused_download_keeps_its_budget():
    """A parked generator draws nothing and looks abandoned.

    `touched` only moves when bytes are taken. A download the client has
    stopped reading takes none, so after fifteen minutes its bucket looked idle,
    was swept, and the resumed transfer got a second budget of its own - two
    budgets for one connection, alongside everything else on the same key.
    """
    _buckets.clear()
    paused = bucket_for("user:paused", 10)
    paused.hold()
    paused.touched = time.monotonic() - 3600
    for n in range(40):
        stale = bucket_for(f"token:{n}", 10)
        stale.touched = time.monotonic() - 3600

    bucket_for("user:live", 10)

    assert "user:paused" in _buckets, "a bucket somebody is holding was swept"
    assert bucket_for("user:paused", 10) is paused

    # And once nobody is holding it, it is forgotten like any other. The sweep
    # only runs when the table is crowded, so the crowd has to be rebuilt: the
    # first one cleared it out.
    paused.release()
    paused.touched = time.monotonic() - 3600
    for n in range(40, 80):
        stale = bucket_for(f"token:{n}", 10)
        stale.touched = time.monotonic() - 3600
    bucket_for("user:live", 10)
    assert "user:paused" not in _buckets


@pytest.mark.asyncio
async def test_a_budget_nobody_has_used_is_eventually_forgotten():
    """Users are few, but every share link is a new key and uptime is months."""
    _buckets.clear()
    for n in range(40):
        stale = bucket_for(f"token:{n}", 10)
        stale.touched = time.monotonic() - 3600     # an hour idle
    bucket_for("user:live", 10)
    assert len(_buckets) < 40
    assert "user:live" in _buckets


def test_chunk_size_still_tracks_the_rate():
    # Unchanged behaviour, asserted because the bucket now depends on chunks
    # being roughly half a second of data for its waits to stay smooth.
    assert effective_chunk_size(0) == 512 * KB
    assert effective_chunk_size(100) == 50 * KB
    assert effective_chunk_size(1) == 4 * KB          # clamped at the bottom
    assert effective_chunk_size(10_000) == 512 * KB   # and at the top


@pytest.mark.asyncio
async def test_a_large_chunk_is_not_starved_by_small_ones():
    """The budget has to reach every transfer on it, not just the small ones.

    take() used to wait for the whole amount to be free at once, which on a busy
    budget never happens: anything smaller keeps drawing the bucket down and the
    level the large one is waiting for never arrives. Watched for ten seconds at
    a megabyte a second, a transfer asking for half a megabyte beside ones
    asking for four kilobytes had sent nothing at all.

    Chunk sizes differ because each transfer fixes its own from the rate that
    was configured when it started, so lowering the limit in Settings leaves
    several sizes running side by side. The large one is not the greedy one; it
    is usually the one that has been going longest.

    The assertion is that it finishes at all, not that it finishes quickly. The
    first version of this test allowed five seconds for half a megabyte, which
    is ten times what it needs and still failed once on a machine that happened
    to be building a container image at the time. A test that goes red when the
    room is noisy teaches people to run it again, which is the opposite of what
    a test is for. The defect it guards was not slowness, it was never - so the
    amount is small enough to be quick and the allowance large enough that only
    never can trip it.
    """
    bucket = SpeedBucket(1024)                     # 1 MB/s
    await _drain(bucket)

    running = True

    async def nibble():
        while running:
            await bucket.take(4 * KB)

    small = [asyncio.create_task(nibble()) for _ in range(2)]
    await asyncio.sleep(0.05)                      # let them get a hold on it

    started = time.monotonic()
    try:
        # 64 KB of a shared megabyte: a sixteenth of a second's budget, so even
        # sharing it with two others this is a fraction of a second's work.
        await asyncio.wait_for(bucket.take(64 * KB), timeout=30)
    finally:
        running = False
        for task in small:
            task.cancel()
    took = time.monotonic() - started

    assert took < 25, f"the large chunk waited {took:.1f}s behind the small ones"
