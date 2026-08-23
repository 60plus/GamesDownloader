"""Outbound HTTP for URLs that came from somewhere else.

Every request here is aimed at an address a scraper, a catalogue or a plugin
handed us, so each one goes through the SSRF guard and under a byte ceiling.
There is deliberately no shared, unguarded client to reach for.
"""

from __future__ import annotations

import httpx

from utils.net_guard import assert_fetch_allowed, make_request_guard

def loggable_error(e: BaseException) -> str:
    """An exception boiled down to something safe to write into a log.

    httpx puts the whole request URL into the message of an HTTP error, and a
    provider that authenticates through the query string then leaves its secret
    in the log in clear: the IGDB token endpoint is called with client_id and
    client_secret as query parameters, so `str(exc)` from that call carries the
    secret verbatim. Nothing built from the message is safe, so this reports the
    exception type and, for an HTTP error, the status code - never the URL.
    """
    if isinstance(e, httpx.HTTPStatusError):
        return f"HTTP {e.response.status_code}"
    if isinstance(e, httpx.TimeoutException):
        return "timed out"
    if isinstance(e, httpx.RequestError):
        return type(e).__name__
    # A message a provider raised itself is fine; anything from httpx is not.
    return f"{type(e).__name__}: {str(e)[:200]}" if not isinstance(e, httpx.HTTPError) else type(e).__name__


class MediaTooLarge(ValueError):
    """Raised when a media download would exceed its byte ceiling.

    A ValueError so the media handlers' broad `except` already treats it as
    "no artwork this time" rather than propagating.
    """


# No cover, hero, logo or screenshot is this big. The cap exists because the URL
# comes from outside - a scraper, a catalogue - and the response used to be read
# whole into memory before anything checked its size, so a single URL pointing at
# a multi-gigabyte file could take the container down with it.
MAX_MEDIA_BYTES = 64 * 1024 * 1024


async def read_capped(response, max_bytes: int, *, what: str = "media") -> bytes:
    """Collect a streamed body under a ceiling, refusing as the bytes arrive.

    Both halves matter. The declared length turns away an honestly-labelled
    giant before a byte is read; the running total is there for the response
    that lies about its length or declines to state one, and for the one that
    is small on the wire and enormous once httpx has transparently decompressed
    it. Measuring `len(response.content)` instead is a check that runs only
    after the memory has already been spent.
    """
    declared = response.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > max_bytes:
        raise MediaTooLarge(f"{what} is {declared} bytes, over the {max_bytes} limit")
    buf = bytearray()
    async for chunk in response.aiter_bytes(65536):
        buf.extend(chunk)
        if len(buf) > max_bytes:
            raise MediaTooLarge(f"{what} exceeded the {max_bytes} byte limit")
    return bytes(buf)


async def fetch_media_bytes(
    url: str, *, headers: dict | None = None, timeout: float = 20,
    max_bytes: int = MAX_MEDIA_BYTES,
) -> tuple[bytes, str]:
    """Fetch a media asset (cover/hero/logo/icon/screenshot/...) whose URL came
    from an external metadata or scraper provider, through the SSRF guard.

    Blocks URLs that resolve to internal / LAN / cloud-metadata addresses, both
    up front and on every redirect hop (redirect-based SSRF bypass). Scraped
    media URLs should never point at a private address, so private LAN is not
    allowed.

    Returns (content_bytes, content_type). Raises net_guard.UnsafeURLError when
    the URL is blocked (a ValueError, so the media handlers' broad `except`
    catches it and falls back gracefully), or the usual httpx errors on a
    network/HTTP failure.

    A ``/api/media/proxy/<token>`` URL (a scraper thumbnail a client picked and
    handed back to be stored) is transparently decrypted to the real scraper URL
    here, so every server-side media download resolves it without each call site
    having to know about the proxy. A forged/undecodable token raises rather than
    fetching anything.
    """
    from utils.media_proxy import resolve_proxy_url
    resolved = resolve_proxy_url(url)
    if resolved is None:
        from utils.net_guard import UnsafeURLError
        raise UnsafeURLError("unresolvable media proxy token")
    url = resolved
    assert_fetch_allowed(url)
    async with httpx.AsyncClient(
        headers=headers,
        follow_redirects=True,
        timeout=timeout,
        event_hooks={"request": [make_request_guard()]},
    ) as client:
        # Streamed so the ceiling is enforced while the bytes arrive. Reading the
        # whole body first and measuring it afterwards is a check that happens
        # only once the damage is done.
        async with client.stream("GET", url) as resp:
            resp.raise_for_status()
            body = await read_capped(resp, max_bytes)
            return body, resp.headers.get("content-type", "")
