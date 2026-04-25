"""Download speed throttle helpers."""
from __future__ import annotations

import asyncio
import json

_DEFAULT_CHUNK = 1024 * 512  # 512 KB - used when no throttle is active


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
    """Sleep long enough so the chunk was sent at most at speed_kbps KB/s."""
    if speed_kbps > 0:
        await asyncio.sleep(chunk_len / (speed_kbps * 1024))
