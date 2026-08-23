"""The emulation routes must answer to the emulation permission.

Every /api/roms route was declared against LIBRARY_READ or LIBRARY_WRITE, which
made both permission checkboxes wrong in opposite directions:

  "Emulation access" off revokes ROMS_* and PLATFORMS_*. No ROM route asked for
  those, so unchecking it did nothing whatsoever - the shelf, the ROM detail,
  the download, the saves and the scraper all stayed open.

  "GamesDownloader access" off revokes LIBRARY_READ, which every ROM route did
  ask for. So taking someone off the Games library also took away Emulation,
  while the navigation kept offering it and every click 403'd.

Saves and savestates carried the same declarations and the same two failures.

Nobody loses access to what they were meant to have: every role, down to USER,
already carries ROMS_READ and PLATFORMS_READ. The only people affected are the
ones an admin had already tried to block and, until now, had not.
"""
from __future__ import annotations

import models.library_file  # noqa: F401 - configures the LibraryGame.files mapper
from endpoints.roms.roms_router import router as roms_router
from endpoints.roms.savestate_router import router as savestate_router
from handler.auth.scopes import (
    ADMIN_SCOPES,
    EDITOR_SCOPES,
    USER_SCOPES,
    Scope,
    apply_permission_overrides,
)

EMULATION_SCOPES = {
    Scope.ROMS_READ, Scope.ROMS_WRITE,
    Scope.PLATFORMS_READ, Scope.PLATFORMS_WRITE,
}
READ_ONLY = {Scope.ROMS_READ, Scope.PLATFORMS_READ}


def guarded_routes() -> list[tuple[str, set[Scope]]]:
    """Every emulation route that declares any scope, as ("GET /path", scopes).

    The savestate thumbnail route declares none on purpose - it renders in a
    plain <img> tag, which cannot carry a token - so it is not here.
    """
    out = []
    for router in (roms_router, savestate_router):
        for route in router.routes:
            scopes = set(getattr(route.endpoint, "required_scopes", ()))
            if scopes:
                verb = "/".join(sorted(route.methods - {"HEAD", "OPTIONS"}))
                out.append((f"{verb} {route.path}", scopes))
    return out


def can_reach(held: set[Scope], required: set[Scope]) -> bool:
    """protected_route requires every declared scope, not any of them."""
    return required.issubset(held)


# ── How the routes are declared ──────────────────────────────────────────────

def test_the_routes_were_found():
    """A guard on the guard: an import that quietly produced nothing would make
    every assertion below vacuously true."""
    assert len(guarded_routes()) > 40


def test_no_emulation_route_is_gated_on_library_read():
    """The exact defect. LIBRARY_READ is the Games library's permission."""
    offenders = [r for r, s in guarded_routes() if Scope.LIBRARY_READ in s]
    assert offenders == [], f"still gated on the Games permission: {offenders}"


def test_every_emulation_route_asks_for_an_emulation_scope():
    offenders = [r for r, s in guarded_routes() if not (s & EMULATION_SCOPES)]
    assert offenders == [], f"no emulation scope required: {offenders}"


# ── What the permission checkboxes now do ────────────────────────────────────

def test_turning_off_emulation_access_closes_every_emulation_route():
    blocked = apply_permission_overrides({"access_emulation": False}, USER_SCOPES)
    open_still = [r for r, s in guarded_routes() if can_reach(blocked, s)]
    assert open_still == [], f"reachable after emulation was revoked: {open_still}"


def test_turning_off_games_access_leaves_the_emulator_alone():
    """The other half: an operator removing someone from the Games library was
    silently taking the emulator away too."""
    user = apply_permission_overrides({"access_gamesdownloader": False}, USER_SCOPES)
    reads = [(r, s) for r, s in guarded_routes() if s <= READ_ONLY]
    assert reads, "expected some read-only emulation routes"
    lost = [r for r, s in reads if not can_reach(user, s)]
    assert lost == [], f"lost along with the Games library: {lost}"


# ── The capability matrix that existed before, preserved ─────────────────────

def test_an_ordinary_user_can_still_browse_and_play():
    user = set(USER_SCOPES)
    denied = [r for r, s in guarded_routes() if s <= READ_ONLY and not can_reach(user, s)]
    assert denied == [], denied


def test_an_ordinary_user_still_cannot_write():
    user = set(USER_SCOPES)
    writes = [
        (r, s) for r, s in guarded_routes()
        if s & {Scope.LIBRARY_WRITE, Scope.ROMS_WRITE,
                Scope.PLATFORMS_WRITE, Scope.LIBRARY_UPLOAD}
    ]
    assert writes, "expected some write routes"
    reachable = [r for r, s in writes if can_reach(user, s)]
    assert reachable == [], f"an ordinary user could write: {reachable}"


def test_an_editor_keeps_editing_rom_metadata():
    """Editors could edit ROM metadata before this change and still can. Those
    routes pair the editor's own scope with ROMS_READ, so the emulation switch
    governs the capability instead of the capability moving to admins."""
    editor = set(EDITOR_SCOPES)
    assert can_reach(editor, {Scope.LIBRARY_WRITE, Scope.ROMS_READ})


def test_an_editor_no_longer_starts_a_library_wide_scan_or_scrape():
    """Those create platforms and burn the ScreenScraper quota for the whole
    server; they were reachable with LIBRARY_WRITE alone."""
    editor = set(EDITOR_SCOPES)
    assert not can_reach(editor, {Scope.PLATFORMS_WRITE})
    assert not can_reach(editor, {Scope.ROMS_WRITE})


def test_an_admin_reaches_everything():
    admin = set(ADMIN_SCOPES)
    denied = [r for r, s in guarded_routes() if not can_reach(admin, s)]
    assert denied == [], denied
