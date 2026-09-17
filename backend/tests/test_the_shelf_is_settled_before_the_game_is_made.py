"""Two places where a visibility rule was applied to the wrong thing.

THE STOREFRONT. `get_home_meta` is a projection - a `select` of thirteen named
columns, so what comes back is a `Row`, not a `LibraryGame`. The visibility
filter added to that list reads its answers with `getattr`, and a Row has no
attribute called `in_default_library`, so every one of those rows answered
"not in the default library, and no membership either" and was dropped.

The shortcut in `Visibility.filter` hides it from an administrator with nothing
switched off, which is the usual way it is looked at. Everybody else got a home
page with no top-rated rail, no genre tiles, no trailers and a game count of
zero. The fix is two more columns in the projection, not a change to the rule:
the rule is right, it was being asked about an object that could not answer.

THE GAME THAT WAS ALREADY MADE. `create_library_game` writes the row, fires the
plugin event, and only then works out which shelf was asked for and whether the
caller may put anything on it. A refusal at that point is a 404 for a game that
exists: the caller cannot see it, so they cannot fix it or remove it, the slug
is taken for good - retrying makes `title-1`, then `title-2` - and a plugin has
already been told about a game the answer says was never created.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from handler.auth.scopes import Scope

ME = 5


# ── The storefront projection ────────────────────────────────────────────────

@pytest_asyncio.fixture
async def library(monkeypatch):
    from models.library import Library, LibraryMembership
    from models.library_file import LibraryFile
    from models.library_game import LibraryGame

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(LibraryGame.__table__.create)
        await conn.run_sync(LibraryFile.__table__.create)
        await conn.run_sync(Library.__table__.create)
        await conn.run_sync(LibraryMembership.__table__.create)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    import handler.database.session as session_mod
    monkeypatch.setattr(session_mod, "async_session_factory", maker)

    async with maker() as session:
        for i in (1, 2):
            session.add(LibraryGame(
                id=i, title=f"Game {i}", slug=f"game-{i}", source="custom",
                is_active=True, in_default_library=True, rating=90))
        await session.commit()
    yield maker
    await engine.dispose()


@pytest.mark.asyncio
async def test_the_projection_carries_what_the_visibility_rule_reads(library):
    from handler.database.library_handler import LibraryHandler

    async with library() as session:
        rows = await LibraryHandler().get_home_meta(session=session)

    assert rows, "projekcja nie zwrocila nic - test nie bada tego, co mysli"
    for row in rows:
        assert getattr(row, "in_default_library", None) is not None, (
            "wiersz projekcji nie niesie `in_default_library`, wiec regula "
            "widocznosci czyta domyslke i wyrzuca KAZDA gre"
        )
        assert getattr(row, "is_active", None) is not None


@pytest.mark.asyncio
async def test_an_ordinary_account_still_sees_the_storefront_rows(library):
    """The pair, run rather than read: the projection and the rule together.

    An administrator with nothing switched off takes a shortcut in `filter` and
    never noticed. Everybody else got an empty home page.
    """
    from handler.database.library_handler import LibraryHandler
    from handler.library.visibility import Visibility

    async with library() as session:
        rows = await LibraryHandler().get_home_meta(session=session)

    seen = Visibility(is_admin=False).filter(rows, {})
    assert len(seen) == len(rows), (
        "filtr widocznosci kasuje cala liste `meta_rows`: brak szyny "
        "najlepiej ocenianych, kafli gatunkow, zwiastunow i licznika gier"
    )


@pytest.mark.asyncio
async def test_an_admin_with_a_closed_library_sees_them_too(library):
    """The other half of the same bug. The admin shortcut is skipped as soon as
    anything is switched off, and then the admin lost the rows as well."""
    from handler.database.library_handler import LibraryHandler
    from handler.library.visibility import Visibility

    async with library() as session:
        rows = await LibraryHandler().get_home_meta(session=session)

    seen = Visibility(is_admin=True, closed_library_ids={99}).filter(rows, {})
    assert len(seen) == len(rows)


@pytest.mark.asyncio
async def test_a_hidden_default_library_still_hides_them(library):
    """The rule has to go on working. Making the rows readable must not make
    them unconditionally visible."""
    from handler.database.library_handler import LibraryHandler
    from handler.library.visibility import Visibility

    async with library() as session:
        rows = await LibraryHandler().get_home_meta(session=session)

    seen = Visibility(is_admin=False, hidden_library_ids=set(),
                      default_library_hidden=True).filter(rows, {})
    assert seen == [], "ukryta domyslna biblioteka mimo to pokazuje swoje gry"


# ── The game that was already made ───────────────────────────────────────────

@pytest.fixture
def create(monkeypatch):
    from endpoints.library import library_router as R

    made: list = []

    async def _by_slug(_slug):
        return None

    async def _create(game):
        made.append(game)
        game.id = 1
        return game

    async def _update(game, data):
        for k, v in data.items():
            setattr(game, k, v)
        return game

    async def _target(_slug):
        return SimpleNamespace(id=3, slug="closed", kind="custom_lib")

    async def _no_access(_user, _target):
        return False

    async def _memberships(*a, **k):
        return None

    monkeypatch.setattr(R._lib, "get_by_slug", _by_slug)
    monkeypatch.setattr(R._lib, "create", _create)
    monkeypatch.setattr(R._lib, "update", _update)
    from handler.database.library_registry_handler import library_registry_handler
    monkeypatch.setattr(library_registry_handler, "get_by_slug", _target)
    monkeypatch.setattr(library_registry_handler, "user_can_access", _no_access)
    monkeypatch.setattr(library_registry_handler, "set_memberships", _memberships)

    fired: list = []
    from plugins import events as _events
    monkeypatch.setattr(_events, "game_added", lambda g: fired.append(g))
    return R, made, fired


def _body(library_slug):
    from endpoints.library.library_router import GameCreateBody
    return GameCreateBody(title="Nowa gra", library=library_slug)


def _request():
    return SimpleNamespace(state=SimpleNamespace(
        user=SimpleNamespace(id=ME, username="u"),
        scopes={Scope.LIBRARY_UPLOAD}))


@pytest.mark.asyncio
async def test_a_refused_shelf_leaves_no_game_behind(create):
    from fastapi import HTTPException

    R, made, fired = create

    with pytest.raises(HTTPException) as refused:
        await R.create_library_game(_request(), _body("closed"))

    assert refused.value.status_code == 404
    assert made == [], (
        "gra powstala, a odpowiedz mowi 404 - wolajacy jej nie widzi, wiec nie "
        "poprawi jej ani nie skasuje, a sluga zostaje zajeta na stale"
    )
    assert fired == [], (
        "wtyczka dostala zdarzenie o grze, ktorej wedlug odpowiedzi nie ma"
    )


@pytest.mark.asyncio
async def test_an_allowed_shelf_still_gets_its_game(create, monkeypatch):
    """The legal case, and the ordinary one."""
    from handler.database.library_registry_handler import library_registry_handler

    R, made, fired = create

    async def _yes(_user, _target):
        return True

    monkeypatch.setattr(library_registry_handler, "user_can_access", _yes)

    out = await R.create_library_game(_request(), _body("open"))

    assert len(made) == 1 and out["title"] == "Nowa gra"
    assert fired, "wtyczka nie dowiedziala sie o nowej grze"
    assert made[0].in_default_library is False, (
        "gra dodana na wlasna polke zostala takze w domyslnej bibliotece"
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("slug", ["games", None])
async def test_an_open_default_library_still_gets_its_game(create, monkeypatch, slug):
    """The default library used to be exempt from the question by name. It is
    asked like any other now, because it can be switched off and restricted
    (test_a_switched_off_games_library_takes_no_new_games) - and when it is
    open, which is nearly always, the game is made and stays in it."""
    from handler.database.library_registry_handler import library_registry_handler

    R, made, fired = create

    async def _games(_slug):
        return SimpleNamespace(id=2, slug="games", kind="custom")

    async def _open(_user, _target):
        return True

    monkeypatch.setattr(library_registry_handler, "get_by_slug", _games)
    monkeypatch.setattr(library_registry_handler, "user_can_access", _open)

    out = await R.create_library_game(_request(), _body(slug))

    assert len(made) == 1 and out["title"] == "Nowa gra"
    assert made[0].in_default_library is not False, (
        "gra z domyslnej biblioteki wypadla z domyslnej biblioteki"
    )
