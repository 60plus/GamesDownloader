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

    async def vamigaweb(request):
        return HTMLResponse("<h1>vAmigaWeb</h1>")

    routes = [
        Route("/", index),
        Route("/player.html", player),
        Route("/vamigaweb/index.html", vamigaweb),
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


def test_vamigaweb_route_is_csp_exempt():
    # The player frames this page, so it needs the same exemption and the same
    # cross-origin isolation headers, or the frame never loads.
    r = client.get("/vamigaweb/index.html")
    assert "content-security-policy" not in r.headers
    assert r.headers.get("cross-origin-opener-policy") == "same-origin"
    assert r.headers.get("cross-origin-embedder-policy") == "credentialless"


def test_baseline_headers_present():
    h = client.get("/").headers
    assert h.get("x-content-type-options") == "nosniff"
    assert h.get("x-frame-options") == "SAMEORIGIN"


# ── Fonts are served from here, so the policy names no font hosts ────────────
#
# Until 1.0.31 style-src named fonts.googleapis.com and font-src named
# fonts.gstatic.com, because both shipped themes asked Google for Orbitron,
# Rajdhani and Inter on every page load - which handed a third party each
# user's address, browser and the page they were on. The families are now
# stored under frontend/public/fonts and the two hosts are gone, so a
# stylesheet or a font file from anywhere else is refused rather than fetched.

def test_no_external_font_host_is_allowed():
    csp = client.get("/").headers["content-security-policy"]
    for directive in ("style-src", "font-src"):
        value = _directive(csp, directive)
        assert value, f"{directive} directive missing"
        assert "fonts.googleapis.com" not in value, directive
        assert "fonts.gstatic.com" not in value, directive
        assert "http" not in value, f"{directive} still names an outside host: {value}"


def test_font_src_is_self_only():
    assert _directive(client.get("/").headers["content-security-policy"], "font-src") \
        == "font-src 'self'"


def test_nothing_in_the_app_still_asks_google_for_a_font():
    """The policy and the code have to agree. A leftover @import would not be
    a broken build - it would be a font that silently never loads."""
    import pathlib

    root = pathlib.Path(__file__).resolve().parent.parent.parent
    # A comment may name the hosts - explaining why they are gone is the point
    # of the comment. Only a line that would actually reach out counts.
    comment = ("#", "//", "/*", "*")
    offenders = []
    for pattern in ("backend/**/*.py", "frontend/src/**/*.ts",
                    "frontend/src/**/*.vue", "frontend/src/**/*.css"):
        for path in root.glob(pattern):
            if path.parent.name == "tests":
                continue
            for number, line in enumerate(
                path.read_text(encoding="utf-8", errors="ignore").splitlines(), 1
            ):
                stripped = line.strip()
                if stripped.startswith(comment):
                    continue
                if "fonts.googleapis.com" in line or "fonts.gstatic.com" in line:
                    offenders.append(f"{path.relative_to(root)}:{number}")
    assert offenders == [], f"still fetching fonts from Google: {offenders}"


def test_every_font_the_themes_name_is_actually_stored():
    """A theme points its `font` at /fonts/<name>.css. If the file is not
    there, the theme loses its typeface and nothing says so."""
    import pathlib

    fonts = pathlib.Path(__file__).resolve().parent.parent.parent / "frontend" / "public" / "fonts"
    for sheet in ("inter.css", "rajdhani.css", "orbitron.css"):
        path = fonts / sheet
        assert path.is_file(), f"{sheet} is missing"
        for line in path.read_text(encoding="utf-8").splitlines():
            if "url(/fonts/" in line:
                name = line.split("url(/fonts/")[1].split(")")[0]
                assert (fonts / name).is_file(), f"{sheet} points at missing {name}"
