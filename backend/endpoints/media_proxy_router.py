"""Proxy scraper thumbnails so their credentialed URLs never reach a browser.

See utils/media_proxy for the why. The token is Fernet-encrypted with the app
secret, so only a URL the server itself wrapped can ever be fetched here - a
client cannot mint a token for an arbitrary address, and the fetch still goes
through the SSRF guard. Like the signed savestate-thumbnail route, this is a
plain (unauthenticated) GET because an <img> carries no Authorization header;
the unforgeable token is the capability, and it stands for exactly one public
scraper thumbnail.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from utils.http import fetch_media_bytes
from utils.media_proxy import resolve_proxy_url

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/media", tags=["media"])

_HDRS = {"User-Agent": "GamesDownloader/3.0"}
_MAX_BYTES = 25 * 1024 * 1024   # a scraper thumbnail/clip; never a bulk transfer


@router.get("/proxy/{token}")
async def media_proxy(token: str) -> Response:
    real = resolve_proxy_url(f"/api/media/proxy/{token}")
    if not real or not real.lower().startswith(("http://", "https://")):
        raise HTTPException(status_code=404, detail="Not found")
    try:
        content, ctype = await fetch_media_bytes(real, headers=_HDRS, timeout=20)
    except Exception:
        # Guard block, dead scraper URL, network error - all become a plain 404;
        # the credentialed URL is never surfaced in the response.
        raise HTTPException(status_code=404, detail="Not found")
    if len(content) > _MAX_BYTES:
        # This route is unauthenticated; refuse to relay something huge.
        raise HTTPException(status_code=404, detail="Not found")
    # This is a thumbnail proxy: only ever hand back image/video bytes, never let
    # a browser sniff a scraper's response into something executable, and never
    # render SVG (script-bearing) inline from our own origin. text/html or SVG
    # (a login wall, an error page) becomes an opaque download, not a page.
    mime = (ctype.split(";")[0].strip() or "image/jpeg").lower()
    if mime == "image/svg+xml" or not (mime.startswith("image/") or mime.startswith("video/")):
        mime = "application/octet-stream"
    return Response(
        content=content,
        media_type=mime,
        headers={
            "Cache-Control": "private, max-age=3600",
            "X-Content-Type-Options": "nosniff",
        },
    )
