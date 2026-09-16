"""Who the ROM scan indicator is for: the accounts that put things in the library.

An administrator and an uploader are the two roles that can add a game or a ROM,
so they are the two that have a reason to watch a scan register it. An uploader
cannot START one - that is PLATFORMS_WRITE - but an upload kicks one off by
itself, and watching it is the only way to know when what they just added has
appeared.

Everybody else has no reason to see it, and worse than no reason: the progress
events go to named rooms, so a client outside them draws a bar from the status
call and then sits on the same platform for the rest of the session, with a Stop
button beside it answering "Missing scopes".

Three things have to agree or the bar freezes again: who the events are sent to,
who the status call admits, and who the composable draws for. The Stop button is
the odd one out on purpose - stopping is an administrator's, so an uploader
watches without a button rather than with one that refuses them.
"""

from __future__ import annotations

import io
import pathlib
import re

import pytest
from fastapi import HTTPException

BACKEND = pathlib.Path(__file__).resolve().parent.parent
FRONTEND = BACKEND.parent / "frontend" / "src"


def _read(path: pathlib.Path) -> str:
    if not path.exists():
        pytest.fail(f"brak {path} - test nie ma czego sprawdzic")
    return io.open(path, encoding="utf-8").read()


# ── Who the events reach ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_progress_and_completion_reach_both_roles(monkeypatch):
    from handler.filesystem import rom_scanner as scanner

    sent: list = []

    async def _emit(event, data, **kw):
        sent.append((event, kw.get("to_role"), tuple(kw.get("to_roles") or ()),
                     kw.get("room")))

    import handler.socket_handler as sh
    monkeypatch.setattr(sh, "emit_event", _emit)

    scanner.reset_scan_progress()
    scanner.begin_scan_progress(platform_total=1)
    await scanner._emit_scan_progress(force=True)
    await scanner._announce_scan_finished({"roms_found": 0})

    names = {e for e, _r, _rs, _room in sent}
    assert names == {"roms:scan_progress", "roms:scan_complete"}, (
        f"skaner wyslal {names}, a nie oba zdarzenia"
    )
    # A ROOM named for a capability, not a pair of role names. Role rooms are
    # blind to `_PERM_REVOKE`: an uploader whose upload chip is switched off
    # keeps the role and loses the scope, so it stayed in `role:uploader` and
    # went on being sent progress the status route refuses it - a bar on screen
    # that could never be filled. Who belongs in the room is decided in
    # socket_handler.scan_watcher_room, from effective scopes, and pinned in
    # test_events_reach_the_right_sockets.py.
    from handler.filesystem.rom_scanner import _SCAN_WATCHERS_ROOM
    for event, to_role, to_roles, room in sent:
        assert to_role is None, f"{event} nadal celuje w jedna role"
        assert not to_roles, f"{event} nadal celuje w role zamiast w pokoj"
        assert room == _SCAN_WATCHERS_ROOM, (
            f"{event} idzie do {room!r}, a nie do pokoju obserwatorow skanu"
        )


@pytest.mark.asyncio
async def test_an_event_for_two_rooms_reaches_both(monkeypatch):
    """The targeting itself, not just what the scanner asks for. Each client
    joins exactly one role room, so two roles is two emits."""
    import handler.socket_handler as sh

    rooms: list = []

    class _Sio:
        async def emit(self, _event, _data, room=None):
            rooms.append(room)

    monkeypatch.setattr(sh, "sio", _Sio())
    await sh.emit_event("x", {}, to_roles=("admin", "uploader"))
    assert rooms == ["role:admin", "role:uploader"]


@pytest.mark.asyncio
async def test_the_older_ways_of_addressing_still_work(monkeypatch):
    """Everything else in the app uses to_user, to_role or a broadcast."""
    import handler.socket_handler as sh

    rooms: list = []

    class _Sio:
        async def emit(self, _event, _data, room=None):
            rooms.append(room)

    monkeypatch.setattr(sh, "sio", _Sio())
    await sh.emit_event("x", {}, to_role="admin")
    await sh.emit_event("x", {}, to_user=7)
    await sh.emit_event("x", {})
    assert rooms == ["role:admin", "user:7", None]


# ── Who the status call admits ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_the_status_call_admits_exactly_who_gets_the_events():
    """A status call narrower than the events hides the bar from somebody who
    is being sent progress; wider, and it seeds a bar for somebody who is not.
    Both ways round, that is a frozen line on screen.

    Asked of the handler rather than of the decorator line, because the answer
    stopped fitting on one: "may upload, or else may run a scan" is not a thing
    `protected_route` can say - it requires every scope it is given - so the
    route declares the emulation permission and the sentence is settled inside.
    """
    from endpoints.roms import roms_router as R
    from handler.auth.scopes import Scope
    from types import SimpleNamespace

    async def _admitted(scopes) -> bool:
        request = SimpleNamespace(state=SimpleNamespace(
            user=SimpleNamespace(id=1, role="admin"), scopes=set(scopes)))
        try:
            await R.scan_status(request)
            return True
        except HTTPException as e:
            assert e.status_code == 403, f"odmowa kodem {e.status_code}"
            return False

    # The uploader, who is sent the events and cannot start a scan.
    assert await _admitted({Scope.LIBRARY_UPLOAD, Scope.ROMS_READ})
    # An ordinary player, who is sent nothing.
    assert not await _admitted({Scope.ROMS_READ})
    # And the case this was reopened for: an administrator whose Games access
    # has been switched off keeps every emulation permission, so the Start and
    # Stop buttons on either side of the bar still work - while the status call
    # behind the bar itself answered 403, because it asked for a GAMES
    # permission in order to describe an emulation job.
    assert await _admitted({Scope.ROMS_READ, Scope.PLATFORMS_WRITE})


def test_the_status_call_is_not_gated_on_a_games_permission():
    """The declaration itself. ROMS_READ is what an account with emulation
    switched off loses, and it is the only thing this route may insist on
    before the sentence above gets to speak."""
    source = _read(BACKEND / "endpoints" / "roms" / "roms_router.py")
    at = source.index('@protected_route(router.get, "/scan/status"')
    line = source[at:source.index("\n", at)]
    scopes = set(re.findall(r"Scopes\.(\w+)", line))
    assert scopes == {"ROMS_READ"}, (
        f"status skanu deklaruje {scopes} - kazde uprawnienie ze strony Gier "
        "zamyka pasek adminowi, ktory nadal moze skan uruchomic i zatrzymac"
    )


def test_seeing_what_a_deletion_takes_matches_being_able_to_perform_it():
    """The same crossed wire on the pair beside it.

    The ROM delete button is drawn for an administrator by role. The preview
    behind it and the deletion itself both asked for a Games permission, while
    the rule INSIDE them - can_delete_rom - names ROMS_WRITE as the
    administrator's. So an administrator with Games switched off was offered a
    button whose only possible answer was 403, twice over.
    """
    source = _read(BACKEND / "endpoints" / "roms" / "roms_router.py")
    for route in ('@protected_route(router.get, "/{rom_id}/removal"',
                  '@protected_route(router.delete, "/{rom_id}"'):
        at = source.index(route)
        line = source[at:source.index("\n", at)]
        scopes = set(re.findall(r"Scopes\.(\w+)", line))
        assert "LIBRARY_UPLOAD" not in scopes, (
            f"{route} zada uprawnienia ze strony Gier, a regula w srodku "
            "(can_delete_rom) mowi: ROMS_WRITE albo wlasciciel"
        )
        assert "ROMS_READ" in scopes, f"{route} nie zamyka sie razem z emulacja"


def test_stopping_is_still_an_administrators():
    """The one thing an uploader does not get. Watching is not stopping."""
    source = _read(BACKEND / "endpoints" / "roms" / "roms_router.py")
    for route in ('@protected_route(router.post, "/scan"',
                  '@protected_route(router.post, "/scan/stop"'):
        at = source.index(route)
        assert "PLATFORMS_WRITE" in source[at:source.index("\n", at)]


# ── Who the composable draws for ─────────────────────────────────────────────

def test_the_indicator_is_drawn_for_both_roles():
    source = _read(FRONTEND / "composables" / "useRomScan.ts")
    assert "canWatchScan" in source, (
        "wskaznik nie pyta, kto patrzy, wiec zamarza kazdemu poza tymi dwoma"
    )


def test_the_stop_button_is_drawn_only_for_who_can_press_it():
    """An uploader sees the progress and no button, rather than a button that
    answers "Missing scopes" for the rest of the session."""
    source = _read(FRONTEND / "composables" / "useRomScan.ts")
    assert "canStopScan" in source, "brak osobnej odpowiedzi na 'czy moge zatrzymac'"
    for view in ("layouts/ClassicLayout.vue", "views/emulation/EmulationHome.vue",
                 "views/emulation/EmulationLibrary.vue"):
        text = _read(FRONTEND / view)
        assert "canStop" in text, f"{view} pokazuje Stop wszystkim, ktorzy widza pasek"


def test_the_rule_lives_in_one_place():
    """Three views draw this. The question of who may watch is answered in the
    composable they share, not copied into each of them."""
    source = _read(FRONTEND / "composables" / "useRomScan.ts")
    assert "useAuthStore" in source
    for view in ("layouts/ClassicLayout.vue", "views/emulation/EmulationHome.vue",
                 "views/emulation/EmulationLibrary.vue"):
        text = _read(FRONTEND / view)
        assert 'role === "uploader"' not in text and "role === 'uploader'" not in text, (
            f"{view} ma wlasna kopie reguly, wiec trzy widoki moga sie roznic"
        )
