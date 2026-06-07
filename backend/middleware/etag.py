"""ETag middleware for authenticated API GET responses.

Replaces the blanket `private, max-age=30` policy with a conditional-GET
strategy:

- For every GET response under /api/ (except endpoints that must always be
  fresh, e.g. /users/me which holds preferences), the middleware computes a
  weak ETag from a hash of the response body.
- If the client sends `If-None-Match: <etag>` and it matches, the server
  responds with `304 Not Modified` and an empty body. Browsers reuse their
  cached copy without paying the JSON transfer cost.
- The Cache-Control header is tightened to `private, max-age=0,
  must-revalidate` so the browser ALWAYS hits the server for fresh data,
  but the 304 path keeps the bandwidth saving.

Skipped:
- non-200 responses (errors must not be cached)
- StreamingResponse / FileResponse (e.g. ROM downloads, exports) - these
  carry no useful ETag and would be expensive to buffer
- bodies larger than _MAX_ETAG_BODY (1 MiB) - rare for list endpoints, the
  cost of buffering an over-sized payload is not worth the saving
- non-GET methods (PUT/POST/DELETE)
"""
from __future__ import annotations

import hashlib
import logging

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response, StreamingResponse

logger = logging.getLogger(__name__)

# 1 MiB - lists this large suggest the caller really wants pagination, and
# buffering the whole body in middleware costs RAM and CPU for the hash.
_MAX_ETAG_BODY = 1024 * 1024

# Endpoints whose response must never be cached - mostly because the client
# saves a setting and reloads expecting the new value back.
_NEVER_CACHE_PREFIXES = (
    "/api/users/me",
    "/api/auth/",
    "/api/setup/",
    "/api/downloads/jobs",   # live download progress
)


class ETagMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method != "GET" or not request.url.path.startswith("/api/"):
            return await call_next(request)
        if any(request.url.path.startswith(p) for p in _NEVER_CACHE_PREFIXES):
            return await call_next(request)

        response = await call_next(request)
        if response.status_code != 200:
            return response

        # Decide whether to skip from the HEADERS, before touching the body
        # iterator. Starlette's BaseHTTPMiddleware hands us an internal
        # _StreamingResponse (NOT a subclass of StreamingResponse), so the
        # isinstance check below is unreliable on its own; and once we start
        # draining body_iterator the bytes cannot be put back. Buffering a file
        # download here used to truncate it at the 1 MiB cap while keeping the
        # original multi-GB Content-Length header, which broke every large
        # library download ("Response content shorter than Content-Length").
        clen = response.headers.get("content-length")
        if clen is not None:
            try:
                if int(clen) > _MAX_ETAG_BODY:
                    return response
            except ValueError:
                return response
        if "attachment" in response.headers.get("content-disposition", "").lower():
            return response
        ctype = (response.headers.get("content-type") or "").lower()
        if ctype.startswith((
            "application/octet-stream", "application/zip", "text/event-stream",
            "video/", "audio/", "image/",
        )):
            return response
        if isinstance(response, StreamingResponse):
            return response

        # Buffer the body (only small JSON/text bodies reach this point).
        body = b""
        try:
            async for chunk in response.body_iterator:
                if isinstance(chunk, str):
                    chunk = chunk.encode("utf-8")
                body += chunk
                if len(body) > _MAX_ETAG_BODY:
                    # Larger than expected and not caught by the header checks:
                    # re-emit the buffered bytes WITHOUT a stale Content-Length
                    # (Response recomputes it) and without an ETag.
                    h = dict(response.headers)
                    h.pop("content-length", None)
                    return Response(
                        content=body,
                        status_code=response.status_code,
                        headers=h,
                        media_type=response.media_type,
                    )
        except Exception:
            logger.warning("ETag middleware: failed to buffer response body", exc_info=True)
            return response

        etag = 'W/"' + hashlib.blake2b(body, digest_size=12).hexdigest() + '"'
        client_etag = request.headers.get("if-none-match")
        # Browsers may send multiple etags joined by commas; treat any match as a hit.
        if client_etag:
            tokens = [t.strip() for t in client_etag.split(",")]
            if etag in tokens or "*" in tokens:
                # 304 must echo the validators and the cache-control directive
                # so the browser can refresh its freshness lifetime correctly.
                headers = {
                    "ETag":          etag,
                    "Cache-Control": "private, max-age=0, must-revalidate",
                }
                # Preserve a few benign headers the upstream set (Vary, etc.).
                for k in ("vary", "content-language"):
                    if k in response.headers:
                        headers[k.title()] = response.headers[k]
                return Response(status_code=304, headers=headers)

        # 200 path: stamp the ETag and a revalidation-mandatory cache directive.
        new_headers = dict(response.headers)
        new_headers["ETag"] = etag
        new_headers["Cache-Control"] = "private, max-age=0, must-revalidate"
        # content-length will be set by Response from the body bytes.
        new_headers.pop("content-length", None)
        return Response(
            content=body,
            status_code=response.status_code,
            headers=new_headers,
            media_type=response.media_type,
        )
