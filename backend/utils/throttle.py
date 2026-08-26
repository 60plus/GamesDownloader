"""Download speed throttle helpers.

The limit used to be applied per stream: every response generator slept for
its own chunk against the configured rate, with no idea any other transfer
existed. A user capped at five megabytes a second who opened four downloads
therefore got twenty, which is to say the configured limit was not a limit.

What replaces it is one token bucket per budget, shared by every transfer that
belongs to it. The budget is the user, not the server: the settings page offers
a global figure and per-user overrides, and the documentation says a user left
at zero "inherits the global limit" - it is the default value of a personal
cap, not a ceiling on the whole machine. Anonymous share-link downloads have no
user, so each link is its own budget; parallel connections to one link share a
cap, and two different links do not compete.

Buckets live in this process, which is correct for a single worker deployment.
"""
from __future__ import annotations

import asyncio
import json
import time

_DEFAULT_CHUNK = 1024 * 512  # 512 KB - used when no throttle is active

#: A bucket nothing has drawn on for this long is forgotten. Users are few and
#: would be cheap to keep, but share links are not bounded over a long uptime.
_IDLE_BUCKET_SECONDS = 15 * 60

#: How long a transfer waits before looking at the bucket again.
#:
#: The same for everybody, which is the whole point. A wait worked out from how
#: much a caller still needs sounds reasonable and starves the large chunks: the
#: transfer with the most left to do sleeps the longest, wakes the least often,
#: and finds the bucket empty every time because the small ones have been round
#: a hundred times meanwhile.
#:
#: It also has to be short for a second reason. A wait can legitimately run into
#: minutes - half a megabyte at four kilobytes a second is two of them - and a
#: limit lifted during one has to reach it, or the way out of a mistake in
#: Settings is to wait for every transfer in flight to time out.
_RATE_RECHECK_SECONDS = 0.02


async def effective_speed_kbps(username: str | None) -> int:
    """
    Return the effective speed limit in KB/s for a given user.
    0 = no limit.
    Priority: per-user override > global limit > 0 (unlimited)
    """
    from handler.config.config_handler import config_handler

    # Per-user check
    if username:
        raw_users = await config_handler.get("dl_user_speeds")
        if raw_users:
            try:
                limits: dict = json.loads(raw_users)
                user_kbps = limits.get(username)
                if user_kbps is not None and int(user_kbps) > 0:
                    return int(user_kbps)
            except Exception:
                pass

    # Global check
    raw_global = await config_handler.get("dl_speed_global_kbps") or "0"
    try:
        return max(0, int(raw_global))
    except ValueError:
        return 0


def effective_chunk_size(speed_kbps: int) -> int:
    """Return an adaptive chunk size so each sleep is roughly 0.5 s.

    When throttling is off (speed_kbps == 0) the default 512 KB chunk is used
    so large files stream efficiently.  When a limit is active, the chunk is
    sized to represent ~0.5 s of data at the target rate, clamped to
    [4 KB, 512 KB] so we never produce micro-reads or over-size buffers.
    """
    if speed_kbps <= 0:
        return _DEFAULT_CHUNK
    target = int(speed_kbps * 1024 * 0.5)          # bytes for 0.5 s
    return max(4 * 1024, min(_DEFAULT_CHUNK, target))


async def throttle_sleep(chunk_len: int, speed_kbps: int) -> None:
    """Sleep long enough so the chunk was sent at most at speed_kbps KB/s.

    Correct for a single transfer and wrong for several, which is why the
    serving routes use a shared bucket instead. Kept for a caller that really
    does own the whole budget on its own.
    """
    if speed_kbps > 0:
        await asyncio.sleep(chunk_len / (speed_kbps * 1024))


class SpeedBucket:
    """A token bucket shared by every transfer drawing on one budget.

    Refills at the configured rate and hands out what a caller asks for, making
    it wait when the budget is not there yet. Because every transfer on the
    same budget takes from the same tokens, four downloads at a five megabyte
    cap add up to five megabytes rather than twenty.

    The rate can be changed underneath a running transfer, so an adjustment in
    Settings reaches downloads already in flight instead of only the next ones.
    """

    def __init__(self, rate_kbps: int):
        self.rate_kbps = rate_kbps
        self._tokens = float(self._rate_bytes)
        self._stamp = time.monotonic()
        self._lock = asyncio.Lock()
        self.touched = self._stamp
        #: How many transfers are holding this bucket right now. A paused
        #: download draws nothing and looks abandoned, and being swept while it
        #: is parked is how one connection came back as a second budget.
        self.holders = 0

    @property
    def _rate_bytes(self) -> float:
        return max(0, self.rate_kbps) * 1024.0

    def hold(self) -> None:
        self.holders += 1
        self.touched = time.monotonic()

    def release(self) -> None:
        self.holders = max(0, self.holders - 1)
        self.touched = time.monotonic()

    async def take(self, amount: int) -> None:
        """Spend `amount` bytes of the budget, waiting for as much as it takes.

        The waiting happens outside the lock, and the rate is read afresh on
        every pass. Both of those were the other way round, and between them a
        lowered limit stopped every transfer on the budget rather than slowing
        it: the first transfer to ask took the lock, slept for its own wait -
        two minutes, for half a megabyte at four kilobytes a second - and no
        other transfer could so much as look at the bucket meanwhile. Putting
        the limit back up did not help either, because the rate had been read
        before the lock was taken and the sleep was already decided.

        Taken a piece at a time, which is what keeps a large chunk from being
        starved by small ones. Waiting for the whole amount to be available at
        once means never being served while anybody smaller keeps drawing the
        bucket down: at a megabyte a second, a transfer asking for half a
        megabyte beside one asking for four kilobytes sent nothing at all for
        as long as it was watched. Chunk sizes are not uniform - each transfer
        fixes its own at the rate that was configured when it started, so a
        change in Settings leaves several sizes running side by side - and the
        big one is not the greedy one. It is usually the oldest.

        So every pass takes whatever is there. Nobody waits for a level the
        bucket has to reach, everybody moves, and the total handed out in a
        second is still the rate: tokens accrue at the rate and never pile up
        past one second of it.
        """
        if amount <= 0:
            return
        outstanding = float(amount)
        while True:
            async with self._lock:
                rate = self._rate_bytes
                if rate <= 0:
                    # No limit, or the limit was just lifted. Anything waiting
                    # is free to go, which is the point of being able to lift it.
                    self.touched = time.monotonic()
                    return
                now = time.monotonic()
                self._tokens = min(rate, self._tokens + (now - self._stamp) * rate)
                self._stamp = now
                self.touched = now
                if self._tokens > 0:
                    spend = min(self._tokens, outstanding)
                    self._tokens -= spend
                    outstanding -= spend
                    if outstanding <= 0:
                        return
            # Everybody waits the same, however much or little is left to do.
            # See _RATE_RECHECK_SECONDS: this is the half of the fix that the
            # partial spend above does not cover on its own.
            await asyncio.sleep(_RATE_RECHECK_SECONDS)


_buckets: dict[str, SpeedBucket] = {}


def bucket_for(key: str, rate_kbps: int) -> SpeedBucket:
    """The shared bucket for `key`, created on first use.

    Handing the rate in on every call is what lets a change in Settings reach
    transfers that are already running: the bucket is shared, so updating it
    updates them all at once.
    """
    bucket = _buckets.get(key)
    if bucket is None:
        bucket = _buckets[key] = SpeedBucket(rate_kbps)
    else:
        bucket.rate_kbps = rate_kbps
        bucket.touched = time.monotonic()

    # Opportunistic sweep. Users are few, but a share link is a new key every
    # time one is created, and this process can be up for months.
    #
    # A bucket somebody is still holding is never swept, however long it has
    # been since it was drawn on. `touched` only moves when bytes are taken, and
    # a paused download takes none: the generator parks on a yield the client
    # has stopped reading and stays there. After fifteen minutes the bucket
    # looked abandoned, was dropped, and the transfer resumed against a brand
    # new one - so a paused-and-resumed download ran at twice its limit
    # alongside anything else on the same budget.
    if len(_buckets) > 32:
        cutoff = time.monotonic() - _IDLE_BUCKET_SECONDS
        for stale in [
            k for k, b in _buckets.items()
            if b.touched < cutoff and b.holders <= 0 and k != key
        ]:
            _buckets.pop(stale, None)
    return bucket
