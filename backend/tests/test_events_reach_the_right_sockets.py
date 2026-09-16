"""Who a socket event reaches, and whether the answer survives a revoked chip.

TWO PROBLEMS, ONE ROOT.

Rooms are named after the ROLE the account had at handshake. The permission
system can take a scope away from an account without changing its role -
`_PERM_REVOKE` does exactly that, and the Users screen offers the chips - so
`role:uploader` holds accounts that may no longer upload, and events meant for
"the accounts that put things in the library" reach them. The scan status route
asks about SCOPES, so the same account is drawn a progress bar and refused the
call behind it.

And the URL upload job never asked at all: four `sio.emit` calls with no room,
which socket.io reads as everybody. They carry the game's title, the file name
and the job id, to every logged-in account on the server. The download path had
the same hole and was given `_emit_download`; this one was missed because it
lives in a different file.

The fix is one idea for both: a socket joins a room for what the account may DO,
worked out from its effective scopes the same way the HTTP middleware works them
out. Then the three answers - who gets the events, who the status call admits,
and who the screen draws for - cannot drift apart, because they are the same
question asked once.
"""

from __future__ import annotations

import io
import pathlib

import pytest

BACKEND = pathlib.Path(__file__).resolve().parent.parent


def _source(rel: str) -> str:
    return io.open(BACKEND / rel, encoding="utf-8").read()


# ── The URL upload job stops shouting ────────────────────────────────────────

def test_the_url_upload_job_names_an_audience_for_every_event():
    source = _source("endpoints/library/upload_router.py")
    at = source.index("async def _url_upload_job(")
    body = source[at:source.index("\n@", at)]

    shouted = [
        ln.strip() for ln in body.splitlines()
        if "sio.emit(" in ln and "room=" not in ln
    ]
    assert not shouted, (
        "zdarzenia wgrywania z URL ida rozgloszeniem do KAZDEGO zalogowanego "
        "konta i niosa tytul gry, nazwe pliku i numer zadania: "
        + "; ".join(shouted)
    )


def test_it_uses_the_same_audience_rule_as_the_download_path():
    """Not a second opinion about who may watch a transfer."""
    source = _source("endpoints/library/upload_router.py")
    at = source.index("async def _url_upload_job(")
    body = source[at:source.index("\n@", at)]
    assert "_emit_url_job(" in body, "zadanie nie przechodzi przez wspolny nadawca"
    # ...and the sender borrows the rule rather than restating it.
    assert "_download_audience" in source, (
        "wlasna regula widowni zamiast tej, ktora juz istnieje w sciezce "
        "pobierania - dwie kopie rozjada sie przy pierwszej zmianie"
    )


# ── Rooms follow what an account may do ──────────────────────────────────────

def test_a_socket_joins_a_room_for_what_the_account_may_do():
    source = _source("handler/socket_handler.py")
    at = source.index("async def connect(")
    body = source[at:source.index("\n@sio.event", at)]
    assert "_scope_room" in body or "scopes_for_role" in body, (
        "pokoje nazwane sama rola sa slepe na _PERM_REVOKE: konto z odebranym "
        "chipem zostaje w pokoju swojej roli i dostaje zdarzenia, ktorych "
        "trasa HTTP mu odmawia"
    )


def test_the_room_asks_the_same_question_the_status_route_asks():
    """The pair that has to hold. If these two ever name different scopes, an
    account is sent progress it cannot fetch, or shown nothing while a bar is
    drawn for it."""
    rooms = _source("handler/socket_handler.py")
    route = _source("endpoints/roms/roms_router.py")

    at = route.index("async def scan_status(")
    gate = route[at:route.index("snapshot =", at)]
    for scope in ("LIBRARY_UPLOAD", "PLATFORMS_WRITE"):
        assert scope in gate, f"trasa statusu przestala pytac o {scope}"
        assert scope in rooms, (
            f"pokoj obserwatorow skanu nie pyta o {scope}, wiec rozjezdza sie "
            "z trasa statusu"
        )


def test_the_scanner_sends_progress_to_that_room():
    source = _source("handler/filesystem/rom_scanner.py")
    assert "_SCAN_WATCHERS" in source
    at = source.index("_SCAN_WATCHERS")
    line = source[at:source.index("\n", at + 40)]
    assert "admin" not in line or "scope" in line.lower() or "SCAN_ROOM" in source, (
        "skaner nadal celuje w pokoje rol, wiec konto z odebranym uprawnieniem "
        "dostaje postep skanu"
    )


@pytest.mark.asyncio
async def test_the_room_is_computed_from_effective_scopes(monkeypatch):
    """Measured against the real scope machinery, not asserted about text.

    An uploader with the upload chip switched off keeps the role and loses the
    scope, which is the whole case.
    """
    from handler.auth.scopes import Scope, apply_permission_overrides, scopes_for_role
    from handler.socket_handler import scan_watcher_room
    from models.user import Role

    plain = scopes_for_role(Role.UPLOADER)
    assert Scope.LIBRARY_UPLOAD in plain, "test nie odtwarza roli wgrywajacego"

    # (permissions, base_scopes) - that order, which is easy to get backwards.
    revoked = apply_permission_overrides({"upload": False}, plain)
    assert Scope.LIBRARY_UPLOAD not in revoked, "odebranie chipu nic nie zmienilo"

    assert scan_watcher_room(plain) is not None
    assert scan_watcher_room(revoked) is None, (
        "konto z odebranym uprawnieniem nadal trafia do pokoju obserwatorow"
    )


@pytest.mark.asyncio
async def test_an_administrator_watches_by_being_able_to_run_one():
    """An admin without the Games chip keeps PLATFORMS_WRITE, so it still starts
    and stops scans - and has to keep seeing them."""
    from handler.auth.scopes import Scope, apply_permission_overrides, scopes_for_role
    from handler.socket_handler import scan_watcher_room

    from models.user import Role

    admin = apply_permission_overrides(
        {"access_gamesdownloader": False}, scopes_for_role(Role.ADMIN))
    assert Scope.LIBRARY_UPLOAD not in admin, "test nie odtwarza odznaczonego chipu"
    assert Scope.PLATFORMS_WRITE in admin
    assert scan_watcher_room(admin) is not None


# ── A change of permission reaches the sockets that are already open ─────────
#
# Room membership is worked out at handshake, which is the right place: connect
# reads the account from the database every time. It does mean that a connection
# already open keeps the rooms it joined, so an administrator unticking a chip
# changed nothing for it until the access token ran out - an hour by default.

@pytest.mark.asyncio
async def test_dropping_a_users_sockets_disconnects_exactly_those(monkeypatch):
    import handler.socket_handler as sh

    disconnected: list = []

    class _Manager:
        def get_participants(self, _ns, room):
            return [("sid-a", "/"), ("sid-b", "/")] if room == "user:7" else []

    class _Sio:
        manager = _Manager()

        async def disconnect(self, sid):
            disconnected.append(sid)

    monkeypatch.setattr(sh, "sio", _Sio())
    assert await sh.drop_sockets_for_user(7) == 2
    assert disconnected == ["sid-a", "sid-b"]

    disconnected.clear()
    assert await sh.drop_sockets_for_user(9) == 0
    assert disconnected == []


@pytest.mark.asyncio
async def test_one_stubborn_socket_does_not_keep_the_others(monkeypatch):
    """These are progress lines. A socket that will not close must not stop the
    account's other tabs being brought up to date."""
    import handler.socket_handler as sh

    closed: list = []

    class _Manager:
        def get_participants(self, _ns, _room):
            return [("bad", "/"), ("good", "/")]

    class _Sio:
        manager = _Manager()

        async def disconnect(self, sid):
            if sid == "bad":
                raise RuntimeError("gone")
            closed.append(sid)

    monkeypatch.setattr(sh, "sio", _Sio())
    assert await sh.drop_sockets_for_user(7) == 1
    assert closed == ["good"]


def test_changing_a_permission_drops_that_users_sockets():
    import io as _io
    import pathlib

    backend = pathlib.Path(__file__).resolve().parent.parent
    source = _io.open(backend / "endpoints" / "users.py", encoding="utf-8").read()
    at = source.index("async def update_user(")
    body = source[at:source.index("\n@", at)]

    assert "drop_sockets_for_user(" in body, (
        "zmiana uprawnien nie dotyka otwartych gniazd, wiec konto zostaje w "
        "pokojach swojej starej roli az do wygasniecia tokenu"
    )


def test_an_unrelated_edit_leaves_the_sockets_alone():
    """Renaming somebody must not knock their tabs off the socket."""
    import io as _io
    import pathlib

    backend = pathlib.Path(__file__).resolve().parent.parent
    source = _io.open(backend / "endpoints" / "users.py", encoding="utf-8").read()
    at = source.index("async def update_user(")
    body = source[at:source.index("\n@", at)]

    call = body.index("drop_sockets_for_user(")
    guard = body[:call]
    assert "access_changed(" in guard, (
        "gniazda zrzucane bezwarunkowo - kazda zmiana konta wyrzuca uzytkownika "
        "z polaczenia"
    )
    # What that guard actually decides - the role, the effective scopes and
    # being switched off, but NOT the upload quota, which lives in the same
    # dictionary and changes no room - is tested by running it, in
    # test_cutting_an_account_off_closes_its_socket.py.
