"""Disabling a library has to close it, not just take it out of the menu.

The settings screen says, in as many words, that disabling a library "hides it
for everyone and blocks its pages". The first half was true and the second was
not: the listing route and the per-game route both ask whether the library is
RESTRICTED and never whether it is enabled, so

    GET /library/games?library=pc-ports
    GET /library/games/412

answered normally for a library the admin had switched off. The interface
redirects away from /lib/<slug>, which is a redirect and not a rule - anything
that talks to the API instead sees the shelf.

Two gates decide this, and they are deliberately separate: one resolves a
library for the browse listing, the other resolves a game for the detail page,
the file list and the download token. The module header of visibility.py records
what happened the last time those two disagreed - a user kept off a restricted
library got an empty listing and could still fetch every game in it by id, and
ids are sequential. So the two are tested here against the same matrix rather
than one at a time.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from models.library import Library, LibraryMembership, UserLibraryAccess
from models.library_file import LibraryFile  # noqa: F401 - LibraryGame maps to it
from models.library_game import LibraryGame
from models.user_game_access import UserGameAccess

ADMIN = SimpleNamespace(id=1, role=SimpleNamespace(name="ADMIN"))


def _user(uid=5):
    from models.user import Role
    return SimpleNamespace(id=uid, role=Role.USER)


def _admin():
    from models.user import Role
    return SimpleNamespace(id=1, role=Role.ADMIN)


# slug -> (enabled, visibility). Every combination that decides an answer.
SHELVES = {
    "open":              (True,  "public"),
    "open-but-off":      (False, "public"),
    "restricted-on":     (True,  "restricted"),
    "restricted-off":    (False, "restricted"),
}


@pytest_asyncio.fixture
async def db(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    async with engine.begin() as conn:
        for table in (Library, LibraryGame, LibraryMembership, UserLibraryAccess,
                      UserGameAccess):
            await conn.run_sync(table.__table__.create)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async with maker() as session:
        for i, (slug, (enabled, vis)) in enumerate(SHELVES.items(), start=10):
            session.add(Library(id=i, slug=slug, name=slug, kind="custom_lib",
                                storage_folder=slug, enabled=enabled, visibility=vis))
            session.add(LibraryGame(id=i, title=slug, slug=slug, source="custom",
                                    is_active=True, in_default_library=False))
            session.add(LibraryMembership(library_game_id=i, library_id=i))
        # On the allowlist for both restricted shelves, so the only thing left
        # to decide the "off" one is whether it is enabled.
        session.add(UserLibraryAccess(user_id=5, library_id=12))
        session.add(UserLibraryAccess(user_id=5, library_id=13))
        await session.commit()

    # Every handler method here is wrapped in @begin_session, which opens its
    # own session from the name the decorator module imported - so that is the
    # one to move, not only the module it came from.
    import importlib

    import handler.database.session as session_mod
    monkeypatch.setattr(session_mod, "async_session_factory", maker)
    for mod in ("decorators.database",
                "handler.library.visibility",
                "handler.database.library_registry_handler",
                "handler.database.library_handler"):
        m = importlib.import_module(mod)
        if hasattr(m, "async_session_factory"):
            monkeypatch.setattr(m, "async_session_factory", maker)
    yield maker
    await engine.dispose()


async def _listing_allows(slug: str, user) -> bool:
    """The gate the browse listing uses."""
    from handler.database.library_registry_handler import library_registry_handler

    lib = await library_registry_handler.get_by_slug(slug)
    assert lib is not None, slug
    return await library_registry_handler.user_can_access(user, lib)


async def _detail_allows(slug: str, user) -> bool:
    """The gate the game detail, the file list and the download token use."""
    from handler.library.visibility import membership_map, visibility_for
    from handler.database.library_handler import LibraryHandler

    lib_id = list(SHELVES).index(slug) + 10
    game = SimpleNamespace(id=lib_id, is_active=True, in_default_library=False)
    vis = await visibility_for(user)
    del LibraryHandler  # only imported to prove the module loads in this fixture
    return vis.allows(game, (await membership_map([game.id])).get(game.id))


@pytest.mark.parametrize("slug,expected", [
    ("open", True),
    ("open-but-off", False),
    ("restricted-on", True),
    ("restricted-off", False),
])
@pytest.mark.asyncio
async def test_the_browse_listing_closes_a_disabled_shelf(db, slug, expected):
    assert await _listing_allows(slug, _user()) is expected, (
        f"{slug}: przegladanie odpowiada inaczej, niz mowi ekran ustawien"
    )


@pytest.mark.parametrize("slug,expected", [
    ("open", True),
    ("open-but-off", False),
    ("restricted-on", True),
    ("restricted-off", False),
])
@pytest.mark.asyncio
async def test_the_game_routes_close_it_too(db, slug, expected):
    """The half that leaks by id when the two gates disagree."""
    assert await _detail_allows(slug, _user()) is expected, (
        f"{slug}: pojedyncza gra odpowiada inaczej niz listowanie"
    )


@pytest.mark.parametrize("slug", list(SHELVES))
@pytest.mark.asyncio
async def test_the_two_gates_never_disagree(db, slug):
    """Stated once, as the property. A user kept out of a listing who can still
    fetch the games by id is the defect this module was written for."""
    user = _user()
    assert await _listing_allows(slug, user) == await _detail_allows(slug, user)


@pytest.mark.parametrize("slug,expected", [
    ("open", True),
    ("open-but-off", False),
    ("restricted-on", True),
    ("restricted-off", False),
])
@pytest.mark.asyncio
async def test_switched_off_is_switched_off_for_an_administrator_too(db, slug, expected):
    """The owner's rule, in his words: if something is off, it is off - no
    difference between an administrator, a user, or anybody else.

    This is the one place in the codebase where an admin does not bypass, and it
    is deliberate. Restricted still bypasses: `restricted-on` is a shelf an
    admin can read without being on the allowlist, exactly as before. What does
    not bypass is the switch.

    The way back is not through here. Settings > Libraries reads /libraries/all,
    which does not go through either gate, so the switch can always be flipped
    again."""
    admin = _admin()
    assert await _listing_allows(slug, admin) is expected
    assert await _detail_allows(slug, admin) is expected


@pytest.mark.parametrize("slug", list(SHELVES))
@pytest.mark.asyncio
async def test_the_two_gates_agree_for_an_administrator_as_well(db, slug):
    admin = _admin()
    assert await _listing_allows(slug, admin) == await _detail_allows(slug, admin)


@pytest.mark.asyncio
async def test_an_administrator_still_reads_a_restricted_shelf_they_are_not_on(db):
    """Nothing here narrows the bypass that is not about the switch. An admin
    reads a restricted library without an allowlist row, as everywhere else."""
    assert await _listing_allows("restricted-on", _admin()) is True
    # And a plain user without a row does not - the rule is still there.
    assert await _listing_allows("restricted-on", _user(uid=99)) is False


@pytest.mark.asyncio
async def test_the_switch_can_always_be_flipped_back(db):
    """The escape hatch, asserted rather than assumed: the admin management
    listing is a different route and answers for a disabled library."""
    from handler.database.library_registry_handler import library_registry_handler

    libs = await library_registry_handler.get_all()
    assert {lib.slug for lib in libs} == set(SHELVES), (
        "get_all pomija wylaczone, wiec nie da sie ich juz wlaczyc z powrotem"
    )


# ── The game routes ask the same question as the file routes ─────────────────
#
# `_check_user_can_access` is the gate for GET /library/games/{id} and its file
# list. It returned early for an administrator, before building a Visibility at
# all - so the one rule administrators do not bypass was not applied there,
# while `_assert_file_visible` further down did apply it. A disabled library
# therefore answered a game and its whole file list to an administrator and then
# refused every download with a bare 404: a screen offering files nothing would
# hand over.

@pytest.mark.asyncio
async def test_the_game_gate_closes_a_disabled_library_for_an_admin_too(db, monkeypatch):
    from fastapi import HTTPException
    from types import SimpleNamespace as NS

    from endpoints.library import library_router as R

    request = NS(state=NS(user=_admin()))
    game = NS(id=11, is_active=True, in_default_library=False)   # only in "open-but-off"

    with pytest.raises(HTTPException) as raised:
        await R._check_user_can_access(request, game)
    assert raised.value.status_code == 404


@pytest.mark.asyncio
async def test_the_game_gate_still_lets_an_admin_at_an_ordinary_game(db):
    from types import SimpleNamespace as NS

    from endpoints.library import library_router as R

    request = NS(state=NS(user=_admin()))
    game = NS(id=10, is_active=True, in_default_library=False)   # in "open"
    await R._check_user_can_access(request, game)                # no raise


@pytest.mark.asyncio
async def test_an_admin_still_reaches_an_unpublished_game(db):
    """They manage those. `allows` lets an administrator past `is_active`, which
    is what the early return used to do."""
    from types import SimpleNamespace as NS

    from endpoints.library import library_router as R

    request = NS(state=NS(user=_admin()))
    await R._check_user_can_access(
        request, NS(id=10, is_active=False, in_default_library=False))


@pytest.mark.asyncio
async def test_the_gate_and_the_file_gate_agree(db):
    """The pair this defect was: two gates for the same question, one obeying
    the rule and one not."""
    from types import SimpleNamespace as NS

    from endpoints.library import library_router as R
    from handler.library.visibility import membership_map, visibility_for

    admin = _admin()
    for game_id, expected in ((10, True), (11, False)):
        game = NS(id=game_id, is_active=True, in_default_library=False)
        vis = await visibility_for(admin)
        file_gate = vis.allows(game, (await membership_map([game_id])).get(game_id))
        try:
            await R._check_user_can_access(NS(state=NS(user=admin)), game)
            game_gate = True
        except Exception:
            game_gate = False
        assert game_gate == file_gate == expected, f"gra {game_id}"
