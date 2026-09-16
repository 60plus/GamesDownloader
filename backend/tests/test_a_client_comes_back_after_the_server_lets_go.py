"""Two ways the client made a temporary refusal permanent.

THE SOCKET. `connect()` guards on the object existing rather than on it being
connected, which is right for socket.io's own reconnection - it reattaches the
same instance and a second call would build a duplicate. But a disconnect the
SERVER initiates is final for that instance: socket.io does not reconnect after
`io server disconnect`. The object stayed in the store, so every later
`connect()` returned immediately, and the client was deaf until a 401 happened
to rebuild it or somebody reloaded the page. `connect()` is called once, on
layout mount.

That was a corner case while the server never dropped anybody. It is routine
now: an account is dropped whenever its permissions change, it is switched off,
its password is reset, or a session is revoked - and the whole point of dropping
it is that the client should come back and be told which rooms it belongs in
NOW.

THE SCAN INDICATOR. `refresh()` catches a 403 and, along with tidying the bar
away, unsubscribes from the scan events and throws the unsubscribe function
away. Nothing subscribes again for the life of the component, and in the Classic
layout that component is mounted for the whole session. So one refusal - a
permission revoked in the middle of a scan, or an address dropping off the
allow-list - left that account with no scan indicator at all until it reloaded
the page, including after the permission came back.

The subscription costs nothing: who receives the events is decided by the server
from the room the socket is in.
"""

from __future__ import annotations

import io
import pathlib

import pytest

FRONTEND = pathlib.Path(__file__).resolve().parent.parent.parent / "frontend"


def _read(rel: str) -> str:
    path = FRONTEND / rel
    if not path.is_file():
        pytest.skip("frontend tree not present")
    return io.open(path, encoding="utf-8").read()


# ── The socket ───────────────────────────────────────────────────────────────

def _disconnect_handler() -> str:
    """The body of the `disconnect` listener.

    Sliced on the listener rather than on the words "io server disconnect",
    which now also appear in the comment above it - the first-occurrence trap
    that this whole audit round keeps turning up, hit here on the first try.
    """
    body = _read("src/stores/socket.ts")
    at = body.index('socket.value.on("disconnect"')
    return body[at:body.index("\n    });", at)]


def test_the_store_notices_a_server_side_disconnect():
    handler = _disconnect_handler()
    assert '"io server disconnect"' in handler or "'io server disconnect'" in handler, (
        "sklep nie rozpoznaje zrzutu ZE STRONY SERWERA, a to jedyny rodzaj "
        "rozlaczenia, po ktorym socket.io nie wraca sam - obiekt zostaje w "
        "sklepie i kazde pozniejsze connect() jest pusta instrukcja"
    )


def test_it_lets_go_of_the_dead_instance():
    """`connect()` returns early while the object is there, so the object has to
    go or nothing can ever rebuild it."""
    handler = _disconnect_handler()
    assert "socket.value = null" in handler or "reconnectWithFreshToken" in handler, (
        "martwy obiekt gniazda zostaje w sklepie na zawsze"
    )


def test_an_ordinary_drop_is_left_to_the_library():
    """Transport hiccups are socket.io's job and it does it well. Tearing the
    instance down on those would throw away its backoff and its buffered
    handlers for no reason."""
    handler = _disconnect_handler()
    assert "reason" in handler.split("=>")[0], (
        "obsluga rozlaczenia nie oglada nawet powodu"
    )
    assert 'reason !== "io server disconnect"' in handler, (
        "sklep rozbiera gniazdo przy KAZDYM rozlaczeniu, nie tylko przy zrzucie "
        "z serwera"
    )


def test_the_guard_on_connect_is_still_there():
    """The reason the early return exists: socket.io reattaches the same
    instance, so a second connect() would leave an orphan with a duplicate
    listener set."""
    body = _read("src/stores/socket.ts")
    at = body.index("function connect()")
    assert "if (socket.value) return;" in body[at:at + 600]


# ── The scan indicator ───────────────────────────────────────────────────────

def _refusal_branch() -> str:
    body = _read("src/composables/useRomScan.ts")
    at = body.index("if (status === 403)")
    return body[at:body.index("\n    }", at)]


def test_a_refusal_does_not_cancel_the_subscription():
    branch = _refusal_branch()
    assert "off?.()" not in branch and "off = null" not in branch, (
        "jedno 403 odpina wskaznik skanu na stale - w ClassicLayout ten "
        "komponent stoi zamontowany cala sesje, wiec nawet po przywroceniu "
        "uprawnienia nie ma jak wrocic bez przeladowania strony"
    )


def test_a_refusal_still_takes_the_bar_down():
    """The half that was right: a bar that can never be filled has to go, and
    the reason must not disappear into an empty catch."""
    branch = _refusal_branch()
    assert "stopWatchdog()" in branch, "straznik chodzi dalej mimo odmowy"
    assert 'phase.value = "idle"' in branch, "pasek zostaje na ekranie"
