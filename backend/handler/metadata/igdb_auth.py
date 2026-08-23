"""One Twitch app token for everything that talks to IGDB.

Thirteen places asked Twitch for a token. Twelve of them asked again on every
single request, so a metadata search cost two round trips instead of one and
the token endpoint saw far more traffic than it needed to. Only the ROM
handler kept what it was given.

The token is cached per client id and reused until a minute before it expires.
Saving new credentials calls forget_token(), so a corrected key takes effect at
once rather than an hour later.

Credential checks in Settings and Setup deliberately do not come through here:
they are asking Twitch whether a key the admin just typed is real, and a cached
answer for a different key would defeat the point.
"""

from __future__ import annotations

import logging
import time

import httpx

logger = logging.getLogger(__name__)

TOKEN_URL = "https://id.twitch.tv/oauth2/token"

# client_id -> (token, unix time it stops being usable)
_cache: dict[str, tuple[str, float]] = {}


async def get_token(client_id: str | None, client_secret: str | None) -> str:
    """A usable Twitch app token, or an empty string.

    Empty covers every reason there is no token - no credentials configured,
    Twitch refusing them, the network being down - because every caller treats
    all of those the same way: skip IGDB this time.
    """
    if not client_id or not client_secret:
        return ""

    now = time.time()
    cached = _cache.get(client_id)
    if cached and cached[1] > now + 60:
        return cached[0]

    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(TOKEN_URL, params={
                "client_id":     client_id,
                "client_secret": client_secret,
                "grant_type":    "client_credentials",
            })
    except Exception as exc:
        logger.warning("[IGDB] could not reach Twitch for a token: %s", exc)
        return ""

    if r.status_code != 200:
        logger.warning("[IGDB] Twitch refused the token request: HTTP %d", r.status_code)
        return ""

    try:
        data = r.json()
    except Exception:
        logger.warning("[IGDB] Twitch answered with something that is not JSON")
        return ""

    token = data.get("access_token") or ""
    if token:
        _cache[client_id] = (token, now + float(data.get("expires_in", 3600)))
    return token


async def igdb_headers(client_id: str | None, client_secret: str | None) -> dict[str, str] | None:
    """Headers ready for an IGDB call, or None when there is no usable token."""
    token = await get_token(client_id, client_secret)
    if not token:
        return None
    return {"Client-ID": client_id or "", "Authorization": f"Bearer {token}"}


def forget_token(client_id: str | None = None) -> None:
    """Drop a cached token so the next call fetches a fresh one."""
    if client_id:
        _cache.pop(client_id, None)
    else:
        _cache.clear()
