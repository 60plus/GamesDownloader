"""Security response-headers middleware.

Adds a minimal set of defensive HTTP headers to every response:

  X-Content-Type-Options: nosniff
      Prevents MIME-type sniffing - browsers must honour Content-Type.

  X-Frame-Options: SAMEORIGIN
      Blocks the app from being embedded in a cross-origin <iframe>, which
      mitigates clickjacking attacks.

  Referrer-Policy: strict-origin-when-cross-origin
      Sends the full URL only to same-origin targets; cross-origin requests
      receive just the origin (no path/query leakage).

  X-XSS-Protection: 1; mode=block
      Legacy IE/Chrome XSS filter - tells old browsers to block rather than
      sanitise a detected reflection attack.  Modern browsers ignore it but
      it costs nothing to send.
"""
from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("X-XSS-Protection", "1; mode=block")
        # Cache: HTML pages (SPA index.html) must never be cached so deploy
        # picks up new JS/CSS chunk hashes immediately.
        content_type = response.headers.get("content-type", "")
        if "text/html" in content_type:
            response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        # Cache: static resources (covers, screenshots, etc.) - long-lived cache
        elif request.url.path.startswith("/resources/"):
            response.headers.setdefault("Cache-Control", "public, max-age=604800, immutable")
        # Cache: hashed JS/CSS assets - immutable (filename changes on rebuild)
        elif request.url.path.startswith("/assets/"):
            response.headers.setdefault("Cache-Control", "public, max-age=31536000, immutable")
        # Cache: private revalidate-always for authenticated API GET responses.
        # The ETagMiddleware turns matching If-None-Match requests into 304s so
        # the browser still avoids the JSON transfer, while UI changes appear
        # without the previous 30 s staleness window.
        # Skip user endpoint (preferences must always be fresh after save+reload)
        elif request.method == "GET" and request.url.path.startswith("/api/") and "/users/me" not in request.url.path:
            response.headers.setdefault("Cache-Control", "private, max-age=0, must-revalidate")
        # CSP: skip for player.html (EmulatorJS needs unrestricted JS execution)
        # COOP/COEP: enable SharedArrayBuffer for EmulatorJS threads
        if request.url.path.startswith("/player") or request.url.path.startswith("/emulatorjs"):
            response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
            response.headers["Cross-Origin-Embedder-Policy"] = "credentialless"
            return response
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval' 'wasm-unsafe-eval' blob:; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com; "
            "img-src 'self' data: https: http:; "
            "connect-src 'self' ws: wss:; "
            "media-src 'self' blob:; "
            "worker-src 'self' blob:; "
            "frame-src 'self'"
        )
        return response
