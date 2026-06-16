"""Unit tests for SecurityHeadersMiddleware (middleware.security_headers).

Locks in the v1.0.6 hardening:
- script-src must NOT contain 'unsafe-inline' or 'unsafe-eval'
- style-src MUST keep 'unsafe-inline' (theme plugins inject inline <style>)
- HSTS only when the client connection is HTTPS (X-Forwarded-Proto)
- /player and /emulatorjs are exempt from CSP (EmulatorJS needs unrestricted JS)
"""
from __future__ import annotations

from starlette.applications import Starlette
from starlette.responses import HTMLResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from middleware.security_headers import SecurityHeadersMiddleware


def _build_app() -> Starlette:
    async def index(request):
        return HTMLResponse("<h1>hi</h1>")

    async def player(request):
        return HTMLResponse("<h1>player</h1>")

    routes = [
        Route("/", index),
        Route("/player.html", player),
    ]
    app = Starlette(routes=routes)
    app.add_middleware(SecurityHeadersMiddleware)
    return app


client = TestClient(_build_app())


def _directive(csp: str, name: str) -> str:
    for part in csp.split(";"):
        part = part.strip()
        if part == name or part.startswith(name + " "):
            return part
    return ""


def test_script_src_has_no_unsafe_inline_or_eval():
    csp = client.get("/").headers["content-security-policy"]
    script_src = _directive(csp, "script-src")
    assert script_src, "script-src directive missing"
    assert "'unsafe-inline'" not in script_src
    assert "'unsafe-eval'" not in script_src
    assert "'self'" in script_src


def test_style_src_keeps_unsafe_inline_for_theme_plugins():
    csp = client.get("/").headers["content-security-policy"]
    style_src = _directive(csp, "style-src")
    assert "'unsafe-inline'" in style_src


def test_hsts_absent_on_plain_http():
    r = client.get("/")
    assert "strict-transport-security" not in r.headers


def test_hsts_present_when_forwarded_proto_https():
    r = client.get("/", headers={"X-Forwarded-Proto": "https"})
    assert r.headers.get("strict-transport-security") == "max-age=31536000"


def test_player_route_is_csp_exempt():
    r = client.get("/player.html")
    assert "content-security-policy" not in r.headers
    assert r.headers.get("cross-origin-opener-policy") == "same-origin"


def test_baseline_headers_present():
    h = client.get("/").headers
    assert h.get("x-content-type-options") == "nosniff"
    assert h.get("x-frame-options") == "SAMEORIGIN"
