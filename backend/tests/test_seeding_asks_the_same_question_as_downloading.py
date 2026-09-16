"""Seeding handed out files the account was not allowed to download.

The three `/api/torrents/seed/*` routes take a `file_id` or a `game_id` and go
straight to the disk: generate a .torrent, hand it back, and tell Transmission
to start serving those bytes to whoever asks. Nothing in between asked whether
this account may have that file.

The download route two files away asks. `_assert_file_visible` exists precisely
because its two callers each had their own copy of the check and neither knew
about restricted libraries, so a file could be streamed out of a library its
recipient was not on. Seeding is the same act with more reach: it does not just
send the file to one caller, it puts the server to work serving it, and hands
back a .torrent that keeps working after the account is gone.

WHAT IS NOT THE PROBLEM, and must not be "fixed": these routes sit at
LIBRARY_DOWNLOAD rather than behind an administrative scope, and that is
deliberate and recorded - `USER_LEVEL_BY_DESIGN` in test_library_scopes.py lists
both of them by name. Seeding is something an ordinary account is supposed to be
able to do. The missing question is not "which scope" but "which files", and
that is a per-library answer the visibility rules already know.

404 rather than 403, to match the download route: telling somebody they may not
have a thing also tells them it exists.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException


class _Db:
    def __init__(self, objects):
        self._objects = objects

    async def get(self, model, key):
        return self._objects.get((model.__name__, key))

    async def execute(self, *_a, **_k):
        return SimpleNamespace(
            scalars=lambda: SimpleNamespace(all=lambda: []),
            scalar_one_or_none=lambda: None,
        )

    async def commit(self):
        return None

    def add(self, _obj):
        return None


class _Factory:
    def __init__(self, objects):
        self._objects = objects

    def __call__(self):
        return self

    async def __aenter__(self):
        return _Db(self._objects)

    async def __aexit__(self, *_a):
        return False


@pytest.fixture
def gate(monkeypatch):
    """Visibility answers no by default; each test says when it answers yes."""
    from handler.database import session as S
    from handler.library import visibility as V

    # The gate looks the game up itself, so without this it reaches for MariaDB
    # and the test fails on a connection rather than on what it is about.
    monkeypatch.setattr(S, "async_session_factory",
                        _Factory({("LibraryGame", 42): SimpleNamespace(id=42)}))

    state = SimpleNamespace(allowed=False, asked=[])

    class _Vis:
        def allows(self, game, membership):
            state.asked.append(getattr(game, "id", None))
            return state.allowed

    async def _visibility_for(_user):
        return _Vis()

    async def _membership_map(ids):
        return {i: None for i in ids}

    monkeypatch.setattr(V, "visibility_for", _visibility_for)
    monkeypatch.setattr(V, "membership_map", _membership_map)
    return state


@pytest.mark.asyncio
async def test_a_file_from_a_library_this_account_cannot_see_is_refused(gate):
    from endpoints.torrent import torrent_router as R

    with pytest.raises(HTTPException) as refusal:
        await R._assert_game_visible(SimpleNamespace(id=3), 42)

    assert refusal.value.status_code == 404, (
        "odmowa mowi 403, wiec potwierdza istnienie pliku komus, kto nie ma go "
        "widziec"
    )
    assert gate.asked == [42], "regula widocznosci nie zostala nawet zapytana"


@pytest.mark.asyncio
async def test_a_file_this_account_may_have_goes_through(gate):
    """THE LEGAL CASE. Seeding is something an ordinary account is meant to do,
    and this is a gate: it can refuse somebody entitled just as easily as it
    can stop somebody who is not."""
    from endpoints.torrent import torrent_router as R

    gate.allowed = True
    await R._assert_game_visible(SimpleNamespace(id=3), 42)


@pytest.mark.asyncio
async def test_an_unauthenticated_caller_is_not_let_through(gate):
    from endpoints.torrent import torrent_router as R

    gate.allowed = True
    with pytest.raises(HTTPException):
        await R._assert_game_visible(None, 42)


# ── Each of the three routes has to actually ask ─────────────────────────────
#
# Behavioural rather than a search for the call: the gate is replaced with one
# that always refuses, and a route that does not consult it simply will not
# raise. A test that grepped for the function name would pass on an import.

@pytest.fixture
def routes(monkeypatch):
    from handler.database import session as S
    from models.library_file import LibraryFile
    from models.library_game import LibraryGame

    lf = SimpleNamespace(id=7, library_game_id=42, is_available=True,
                         file_path="games/x/gra.bin", size_bytes=10)
    game = SimpleNamespace(id=42, title="Gra")
    monkeypatch.setattr(S, "async_session_factory", _Factory({
        ("LibraryFile", 7): lf, ("LibraryGame", 42): game,
    }))
    # Referenced so the model names above stay honest if either is renamed.
    assert LibraryFile.__name__ == "LibraryFile" and LibraryGame.__name__ == "LibraryGame"

    from endpoints.torrent import torrent_router as R

    async def _refuse(_user, _game_id):
        raise HTTPException(status_code=404, detail="File not available")

    monkeypatch.setattr(R, "_assert_game_visible", _refuse)

    from handler.auth.scopes import Scope
    request = SimpleNamespace(state=SimpleNamespace(
        user=SimpleNamespace(id=3, username="gdtest"),
        scopes={Scope.LIBRARY_DOWNLOAD}))
    return SimpleNamespace(module=R, request=request)


@pytest.mark.asyncio
async def test_the_single_file_seed_route_asks(routes):
    with pytest.raises(HTTPException) as refusal:
        await routes.module.generate_seed_torrent(routes.request, 7)
    assert refusal.value.status_code == 404


@pytest.mark.asyncio
async def test_the_whole_game_seed_route_asks(routes):
    from endpoints.torrent.torrent_router import SeedGameBody

    with pytest.raises(HTTPException) as refusal:
        await routes.module.generate_game_torrent(routes.request, 42, SeedGameBody())
    assert refusal.value.status_code == 404


@pytest.mark.asyncio
async def test_the_seed_status_route_asks(routes):
    """It answers whether a file is being seeded, how big it is and how much has
    gone out. That is information about a file, and it was readable for any
    account that could guess an id."""
    with pytest.raises(HTTPException) as refusal:
        await routes.module.seed_status(routes.request, 7)
    assert refusal.value.status_code == 404
