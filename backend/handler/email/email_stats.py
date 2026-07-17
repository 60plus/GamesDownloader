"""Lightweight Redis counters for outbound email volume.

Surfaced on the admin dashboard ("emails sent"). Incremented at the single send
choke point - smtp_sender.send_email - so every mail the app dispatches (digest,
alerts, security report, recently-added, password reset) is counted in one place
without touching any call site. Read back as an all-time total, a rolling 30-day
sum and a per-day series for the dashboard sparkline.

Best-effort by design: every function swallows its own errors, so a Redis hiccup
can neither block an email from going out nor break the dashboard.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import redis.asyncio as aioredis

from config import REDIS_URL

_redis: aioredis.Redis | None = None


def _get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(REDIS_URL, decode_responses=True)
    return _redis


_TOTAL = "gd:stats:email:total"        # all-time counter, no TTL
_DAY = "gd:stats:email:day:"           # + %Y%m%d, per-day counter
_DAY_TTL = 60 * 60 * 24 * 40           # keep daily buckets ~40 days (covers 30d window)


async def record_email_sent(n: int = 1) -> None:
    """Count `n` outbound messages (recipients). Called after a successful send."""
    if n <= 0:
        return
    try:
        r = _get_redis()
        await r.incrby(_TOTAL, n)
        key = _DAY + datetime.utcnow().strftime("%Y%m%d")
        await r.incrby(key, n)
        await r.expire(key, _DAY_TTL)
    except Exception:
        pass


async def get_email_stats(start_date, end_date) -> dict:
    """All-time total, sum inside [start_date, end_date] (inclusive), and a
    contiguous per-day series across that span (oldest first) for the dashboard
    sparkline. `start_date`/`end_date` are datetime.date. Email is bucketed by
    calendar day only, so sub-day windows (e.g. 24h) collapse to 1-2 daily bars."""
    out: dict = {"total": 0, "in_range": 0, "series": []}
    try:
        r = _get_redis()
        span = (end_date - start_date).days + 1
        span = max(1, min(span, 120))
        dates = [start_date + timedelta(days=i) for i in range(span)]
        keys = [_DAY + d.strftime("%Y%m%d") for d in dates]
        vals = await r.mget(keys)
        nums = [int(v or 0) for v in vals]
        out["total"] = int(await r.get(_TOTAL) or 0)
        out["in_range"] = sum(nums)
        out["series"] = [{"date": dates[i].strftime("%m-%d"), "count": nums[i]} for i in range(span)]
    except Exception:
        pass
    return out
