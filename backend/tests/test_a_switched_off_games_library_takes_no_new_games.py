"""The built-in Games library takes no new games while it is switched off.

Found by the 1.0.34 audit (#5). Both ways a new game is filed onto a shelf asked
whether the caller may reach that shelf - and both skipped the question for the
built-in Games library, by name:

    _assert_shelf_allowed      torrent routes   `if not target or target == "games": return`
    create_library_game        POST /games      `if target_slug and target_slug != "games":`

The comment beside the first said nobody is on an allowlist for Games, which was
true when it was written. Since then Games can be switched off ("off is off",
for administrators too) and made restricted like any other library. So an
uploader could still queue a torrent, or create a game and upload into it, onto
a shelf nobody can see: charged to their quota, invisible to everybody.

The fix is to stop treating the name as an exemption and ask the same rule of
the Games row that every other library gets. The legal case - an enabled,
public Games library, where nearly every upload goes - has to keep working, and
is tested first.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from handler.auth.scopes import Scope
from models.library import Library, UserLibraryAccess


def _uploader(uid=5):
    from models.user import Role
    return SimpleNamespace(id=uid, role=Role.UPLOADER, username="gdtest")


def _admin():
    from models.user import Role
    return SimpleNamespace(id=1, role=Role.ADMIN, username="admin")


@pytest_asyncio.fixture
async def games(monkeypatch):
    """A real Games row behind the real access rule. `set` changes it."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    async with engine.begin() as conn:
        for table in (Library, UserLibraryAccess):
            await conn.run_sync(table.__table__.create)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        session.add(Library(id=2, slug="games", name="Games", kind="custom",
                            storage_folder="CUSTOM", enabled=True, visibility="public",
                            is_builtin=True))
        await session.commit()

    import importlib

    import handler.database.session as session_mod
    monkeypatch.setattr(session_mod, "async_session_factory", maker)
    for mod in ("decorators.database", "handler.database.library_registry_handler"):
        m = importlib.import_module(mod)
        if hasattr(m, "async_session_factory"):
            monkeypatch.setattr(m, "async_session_factory", maker)

    async def _set(*, enabled=True, visibility="public", allow=()):
        from sqlalchemy import delete, update
        async with maker() as session:
            await session.execute(update(Library).where(Library.id == 2)
                                  .values(enabled=enabled, visibility=visibility))
            await session.execute(delete(UserLibraryAccess))
            for uid in allow:
                session.add(UserLibraryAccess(user_id=uid, library_id=2))
            await session.commit()

    yield SimpleNamespace(set=_set)
    await engine.dispose()


SHELF = [None, "", "games"]


# ── Torrents ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.parametrize("slug", SHELF)
async def test_an_open_games_library_still_takes_a_torrent(games, slug):
    from endpoints.torrent.torrent_router import _assert_shelf_allowed

    await _assert_shelf_allowed(_uploader(), slug)


@pytest.mark.asyncio
@pytest.mark.parametrize("slug", SHELF)
@pytest.mark.parametrize("who", [_uploader, _admin], ids=["uploader", "admin"])
async def test_a_switched_off_games_library_takes_no_torrent(games, slug, who):
    from endpoints.torrent.torrent_router import _assert_shelf_allowed

    await games.set(enabled=False)
    with pytest.raises(HTTPException) as refusal:
        await _assert_shelf_allowed(who(), slug)
    assert refusal.value.status_code == 404, (
        "torrent laduje w wylaczonej bibliotece Games, ktorej nikt nie zobaczy"
    )


@pytest.mark.asyncio
async def test_a_database_without_the_games_row_yet_is_not_closed(games, monkeypatch):
    """The row is seeded on every boot. Before that, nothing has been switched
    off, and "no library called games" would be a refusal about nothing."""
    from endpoints.torrent.torrent_router import _assert_shelf_allowed
    from handler.database.library_registry_handler import library_registry_handler

    async def _nothing(_slug):
        return None

    monkeypatch.setattr(library_registry_handler, "get_by_slug", _nothing)
    await _assert_shelf_allowed(_uploader(), None)
    with pytest.raises(HTTPException):
        await _assert_shelf_allowed(_uploader(), "kids")


@pytest.mark.asyncio
async def test_a_restricted_games_library_takes_a_torrent_only_from_its_list(games):
    from endpoints.torrent.torrent_router import _assert_shelf_allowed

    await games.set(visibility="restricted", allow=(5,))
    await _assert_shelf_allowed(_uploader(5), "games")
    with pytest.raises(HTTPException):
        await _assert_shelf_allowed(_uploader(6), None)


# ── A new game ───────────────────────────────────────────────────────────────

@pytest.fixture
def creating(monkeypatch):
    """Stops the route at the first write, which is all these tests need to know."""
    from endpoints.library import library_router as L

    state = SimpleNamespace(created=[])

    class _Stop(Exception):
        pass

    async def _no_slug(_slug):
        return None

    async def _create(game):
        state.created.append(game)
        raise _Stop()

    monkeypatch.setattr(L._lib, "get_by_slug", _no_slug)
    monkeypatch.setattr(L._lib, "create", _create)
    state.Stop = _Stop
    state.L = L
    return state


async def _create_game(creating, user, library):
    request = SimpleNamespace(state=SimpleNamespace(user=user, scopes={Scope.LIBRARY_UPLOAD}))
    body = creating.L.GameCreateBody(title="Doom", library=library)
    return await creating.L.create_library_game.__wrapped__(request, body)


@pytest.mark.asyncio
@pytest.mark.parametrize("slug", SHELF)
async def test_an_open_games_library_still_takes_a_new_game(games, creating, slug):
    with pytest.raises(creating.Stop):
        await _create_game(creating, _uploader(), slug)
    assert len(creating.created) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("slug", SHELF)
async def test_a_switched_off_games_library_takes_no_new_game(games, creating, slug):
    await games.set(enabled=False)
    with pytest.raises(HTTPException) as refusal:
        await _create_game(creating, _uploader(), slug)
    assert refusal.value.status_code == 404
    assert creating.created == [], (
        "gra powstala w wylaczonej bibliotece Games - wgranie do niej liczy sie do "
        "limitu, a nikt jej nie zobaczy"
    )
