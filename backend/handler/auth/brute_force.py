"""Redis-based brute-force login protection.

Config keys stored in config_handler (DB):
  bf_enabled        bool (default True)
  bf_max_attempts   int  (default 5)
  bf_window_seconds int  (default 300  - 5-min sliding window for counting)
  bf_ban_seconds    int  (default 900  - 15-min ban after threshold exceeded)
  bf_whitelist      str  (comma-separated IPs to never block, default "")

Real-IP extraction priority (safe against header spoofing):
  1. CF-Connecting-IP  - set by Cloudflare, client cannot forge it end-to-end
  2. X-Real-IP         - set by nginx/traefik on the proxy host
  3. X-Forwarded-For   - leftmost entry, ONLY trusted when the direct TCP
                         connection comes from a private/LAN network (i.e. a
                         local reverse proxy).  If someone connects directly
                         from a public IP they could inject this header, so
                         we fall through to the TCP peer in that case.
  4. request.client.host - always the actual TCP connection peer
"""
from __future__ import annotations

import ipaddress
import logging

import redis.asyncio as aioredis

from config import REDIS_URL

logger = logging.getLogger(__name__)

# Module-level Redis client (lazy init)
_redis: aioredis.Redis | None = None

def _get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(REDIS_URL, decode_responses=True)
    return _redis

_ATT_PREFIX = "gd:bf:att:"   # key: gd:bf:att:{ip}  value: count (TTL = window)
_BAN_PREFIX = "gd:bf:ban:"   # key: gd:bf:ban:{ip}  value: "1"  (TTL = ban_seconds)

# Atomically increment attempt counter and set TTL on first attempt.
# Prevents a race where two concurrent requests both see count==1 and one
# of them skips the expire call, leaving the key without a TTL.
_LUA_INCR_EXPIRE = """
local count = redis.call('incr', KEYS[1])
if count == 1 then
  redis.call('expire', KEYS[1], tonumber(ARGV[1]))
end
return count
"""


def _is_private(ip_str: str) -> bool:
    """Return True for loopback, RFC-1918, link-local, and other non-routable addresses."""
    try:
        addr = ipaddress.ip_address(ip_str)
        return addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_unspecified
    except ValueError:
        return True  # treat malformed IPs as untrusted / private


def _ip_in_range(ip_str: str, network_str: str) -> bool:
    """Return True if ip_str falls within network_str (single IP or CIDR)."""
    try:
        addr = ipaddress.ip_address(ip_str)
        net  = ipaddress.ip_network(network_str, strict=False)
        return addr in net
    except ValueError:
        return False


def _client_ip(request, trusted_proxies: list[str] | None = None) -> str:
    """
    Extract the real client IP safely.

    Priority chain (see module docstring for rationale):
      1. CF-Connecting-IP  - Cloudflare; cannot be spoofed by end-user
      2. X-Real-IP         - nginx / haproxy / traefik single-hop header
      3. X-Forwarded-For (leftmost) - only when direct TCP peer is trusted:
            a) explicitly listed in trusted_proxies config, OR
            b) is a private/LAN address (legacy default behaviour)
      4. request.client.host - raw TCP connection, always available
    """
    # 1. Cloudflare
    cf = (request.headers.get("CF-Connecting-IP") or "").strip()
    if cf:
        return cf

    # 2. nginx / haproxy / traefik
    real = (request.headers.get("X-Real-IP") or "").strip()
    if real:
        return real

    # 3. X-Forwarded-For - safe ONLY when the connecting peer is trusted
    direct = (request.client.host if request.client else "") or ""
    if direct:
        tp = trusted_proxies or []
        peer_trusted = _is_private(direct) or any(_ip_in_range(direct, t) for t in tp)
        if peer_trusted:
            xff = (request.headers.get("X-Forwarded-For") or "").strip()
            if xff:
                leftmost = xff.split(",")[0].strip()
                if leftmost:
                    return leftmost

    # 4. Fallback: raw TCP peer (proxy IP or direct client)
    return direct or "unknown"


async def _get_config() -> dict:
    """Load brute-force config from config_handler (lazy import to avoid circular)."""
    from handler.config.config_handler import config_handler
    raw_proxies = (await config_handler.get("trusted_proxies") or "").strip()
    trusted = [p.strip() for p in raw_proxies.split(",") if p.strip()] if raw_proxies else []
    return {
        "enabled":         await config_handler.get_bool("bf_enabled", default=True),
        "max_attempts":    int(await config_handler.get("bf_max_attempts") or 5),
        "window_seconds":  int(await config_handler.get("bf_window_seconds") or 300),
        "ban_seconds":     int(await config_handler.get("bf_ban_seconds") or 900),
        "whitelist":       [e.strip() for e in (await config_handler.get("bf_whitelist") or "").split(",") if e.strip()],
        "trusted_proxies": trusted,   # IPs/CIDRs explicitly configured as proxies
    }


async def check_ip(request) -> tuple[bool, int]:
    """Return (is_blocked, remaining_seconds). Call before processing login."""
    cfg = await _get_config()
    if not cfg["enabled"]:
        return False, 0
    ip = _client_ip(request, cfg["trusted_proxies"])
    if ip in cfg["whitelist"] or ip == "127.0.0.1":
        return False, 0
    r = _get_redis()
    ttl = await r.ttl(f"{_BAN_PREFIX}{ip}")
    if ttl > 0:
        return True, ttl
    return False, 0


async def record_failure(request) -> None:
    """Record a failed login attempt. Bans IP if threshold exceeded."""
    cfg = await _get_config()
    if not cfg["enabled"]:
        return
    ip = _client_ip(request, cfg["trusted_proxies"])
    if ip in cfg["whitelist"] or ip == "127.0.0.1":
        return
    r = _get_redis()
    att_key = f"{_ATT_PREFIX}{ip}"
    count = await r.eval(_LUA_INCR_EXPIRE, 1, att_key, cfg["window_seconds"])
    if count >= cfg["max_attempts"]:
        await r.setex(f"{_BAN_PREFIX}{ip}", cfg["ban_seconds"], "1")
        await r.delete(att_key)
        logger.warning("Brute-force: IP %s banned for %ds after %d failures", ip, cfg["ban_seconds"], count)
        from handler.email.alerts import maybe_alert
        from utils.async_utils import fire_task
        fire_task(maybe_alert("brute_force", None, ip))


async def record_success(request) -> None:
    """Clear failed attempts on successful login."""
    cfg = await _get_config()
    if not cfg["enabled"]:
        return
    ip = _client_ip(request, cfg["trusted_proxies"])
    r = _get_redis()
    await r.delete(f"{_ATT_PREFIX}{ip}")


async def unban_ip(ip: str) -> bool:
    """Admin action: manually unban an IP. Returns True if was banned."""
    r = _get_redis()
    deleted = await r.delete(f"{_BAN_PREFIX}{ip}", f"{_ATT_PREFIX}{ip}")
    return deleted > 0


async def get_banned_ips() -> list[dict]:
    """Return list of currently banned IPs with remaining TTL."""
    r = _get_redis()
    keys = await r.keys(f"{_BAN_PREFIX}*")
    result = []
    for key in keys:
        ttl = await r.ttl(key)
        if ttl > 0:
            ip = key[len(_BAN_PREFIX):]
            result.append({"ip": ip, "remaining_seconds": ttl})
    return sorted(result, key=lambda x: x["remaining_seconds"], reverse=True)


_RATE_PREFIX = "gd:rl:"   # key: gd:rl:{prefix}:{ip}  value: count (TTL = window)


async def rate_limit(
    request,
    limit: int,
    window: int,
    key_prefix: str,
) -> None:
    """Fixed-window rate limiter keyed by client IP.

    Raises HTTP 429 when the caller's IP has exceeded *limit* requests within
    the last *window* seconds.  Whitelisted IPs and loopback are always exempt.
    """
    from fastapi import HTTPException

    cfg = await _get_config()
    ip = _client_ip(request, cfg["trusted_proxies"])
    if ip in cfg["whitelist"] or ip == "127.0.0.1":
        return

    r = _get_redis()
    key = f"{_RATE_PREFIX}{key_prefix}:{ip}"
    count = await r.eval(_LUA_INCR_EXPIRE, 1, key, window)
    if count > limit:
        ttl = await r.ttl(key)
        raise HTTPException(
            status_code=429,
            detail=f"Too many requests. Try again in {max(ttl, 1)}s.",
        )
