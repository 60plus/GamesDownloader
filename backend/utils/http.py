"""Shared async HTTP client - single httpx.AsyncClient for the whole app.

Usage:
    from utils.http import http_client
    resp = await http_client.get("https://api.gog.com/...")
"""

from __future__ import annotations

import httpx

_client: httpx.AsyncClient | None = None

DEFAULT_TIMEOUT = httpx.Timeout(connect=10, read=30, write=10, pool=10)
DEFAULT_HEADERS = {
    "User-Agent": "GamesDownloaderV3/1.0",
    "Accept": "application/json",
}


async def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            timeout=DEFAULT_TIMEOUT,
            headers=DEFAULT_HEADERS,
            follow_redirects=True,
        )
    return _client


async def close_client() -> None:
    global _client
    if _client and not _client.is_closed:
        await _client.aclose()
        _client = None
