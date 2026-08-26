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

  X-XSS-Protection is deliberately NOT sent.
      The header is withdrawn. Every browser that still honours it does so
      with an auditor that was itself exploitable: it could be steered into
      suppressing legitimate script, and its filtering introduced side
      channels that leaked cross-origin content. "Costs nothing to send" was
      the old reason for keeping it, and it was wrong. The Content-Security
      Policy below is what actually stops injected script here.

  Content-Security-Policy
      script-src is locked to 'self' (no 'unsafe-inline'/'unsafe-eval') so an
      injected <script> (from a game title/description, username or scraper
      metadata) cannot execute.  style-src keeps 'unsafe-inline' on purpose -
      theme plugins inject inline <style> and the admin installs them knowingly.
      The /player, /emulatorjs and /vamigaweb routes are exempted (both
      emulators need unrestricted JS + SharedArrayBuffer via COOP/COEP).
      connect-src is 'self' only: socket.io talks to its own origin, so no
      wildcard ws:/wss: (which would allow exfiltration to any host) is needed.
      img-src drops http: (no mixed content) - all scraper media is served
      locally; https: is kept for plugin themes that reference remote images.

  Strict-Transport-Security
      Sent only when the client connection is HTTPS (X-Forwarded-Proto), so a
      plain-HTTP self-hosted deployment is never affected.
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
        # HSTS: only when the real client connection is HTTPS. Uvicorn runs
        # without --proxy-headers, so TLS-terminating proxies are detected via
        # X-Forwarded-Proto. Plain-HTTP deployments never receive this header.
        if request.headers.get("x-forwarded-proto", request.url.scheme) == "https":
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000"
            )
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
        # /vamigaweb is the second emulator (Amiga WHDLoad); it is framed by the
        # player, so it needs the same treatment or the frame is blocked.
        if (
            request.url.path.startswith("/player")
            or request.url.path.startswith("/emulatorjs")
            or request.url.path.startswith("/vamigaweb")
        ):
            response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
            response.headers["Cross-Origin-Embedder-Policy"] = "credentialless"
            return response
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; "
            "script-src 'self' 'wasm-unsafe-eval' blob:; "
            # No font hosts. Every family the app and both shipped themes use
            # is served from /fonts, so a stylesheet or a font file from
            # anywhere else is now refused rather than fetched. Until 1.0.31
            # these two lines named fonts.googleapis.com and fonts.gstatic.com,
            # because the themes still asked Google for Orbitron, Rajdhani and
            # Inter on every page load - which handed a third party each user's
            # address, browser and current page.
            "style-src 'self' 'unsafe-inline'; "
            "font-src 'self'; "
            "img-src 'self' data: https:; "
            "connect-src 'self'; "
            # https: mirrors img-src - plugin store entries may showcase webm
            # clips next to screenshots, and themes may stream remote video
            "media-src 'self' blob: https:; "
            "worker-src 'self' blob:; "
            # YouTube allowed for the trailer embeds (game detail / home
            # players). frame-src governs what WE may embed, so this does not
            # loosen who may frame the app (that stays frame-ancestors/XFO).
            "frame-src 'self' https://www.youtube.com https://www.youtube-nocookie.com"
        )
        return response
