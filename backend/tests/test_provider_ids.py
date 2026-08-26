"""The ids that decide where the next scrape looks.

A library game remembers which GOG product, which Steam app and which IGDB
entry it matched. That is the right thing to remember - searching the title
again is slower and free to land on a sequel, a remaster or a demo - but it
means a stored id is not a fact about the game so much as a decision about it,
and the decision was being made on no evidence and could not be revisited.

Both halves are here: an id is only written once it has resolved to something,
and clearing a game's metadata clears them, which puts the way out of a bad
match back where it was.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from endpoints.library.library_router import CLEARED_LIBRARY_FIELDS
from handler.library import library_scrape_handler
from models.library_game import LibraryGame


def _blank_game(**kw):
    """A game with nothing filled in, so every "needs" test in the scraper
    passes and it actually goes looking."""
    base = dict(
        title="Some Game", description=None, description_short=None,
        developer=None, publisher=None, genres=None, features=None,
        os_windows=False, os_mac=False, os_linux=False, release_date=None,
        requirements=None, screenshots=None, meta_ratings=None, languages=None,
        videos=None, rating=None, steam_appid=None, gog_product_id=None,
        igdb_id=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


@pytest.fixture
def steam(monkeypatch):
    """Stand in for the Steam scraper, and record what it was asked."""
    from handler.gog import steam_scraper

    calls = SimpleNamespace(searched=0, detailed=[], details=None)

    async def _search(_title):
        calls.searched += 1
        return 4242

    async def _details(app_id):
        calls.detailed.append(app_id)
        return calls.details

    monkeypatch.setattr(steam_scraper, "search_steam_app", _search)
    monkeypatch.setattr(steam_scraper, "fetch_steam_app_details", _details)
    return calls


@pytest.mark.asyncio
async def test_a_steam_id_that_resolves_to_nothing_is_not_kept(steam):
    """The search found an app, the store had nothing to say about it.

    Saving the id anyway made the guess permanent: the next scrape asks for
    that app by number instead of searching the title, so the search that would
    have corrected it never runs again.
    """
    steam.details = None
    game = _blank_game()

    assert await library_scrape_handler._apply_steam_fallback(game) == []
    assert game.steam_appid is None, "a guess that resolved to nothing was saved"


@pytest.mark.asyncio
async def test_a_steam_id_that_does_resolve_is_kept(steam):
    """Because remembering it is the point: it is what stops the next scrape
    settling on a different game."""
    steam.details = {"description": "A game."}
    game = _blank_game()

    applied = await library_scrape_handler._apply_steam_fallback(game)

    assert game.steam_appid == 4242
    assert any("description" in a for a in applied)


@pytest.mark.asyncio
async def test_an_id_already_stored_is_used_instead_of_searching(steam):
    """Unchanged behaviour, and the reason the id matters at all."""
    steam.details = {"description": "A game."}
    game = _blank_game(steam_appid=99)

    await library_scrape_handler._apply_steam_fallback(game)

    assert steam.searched == 0, "it searched despite already knowing the app"
    assert steam.detailed == [99]


def test_clearing_the_metadata_clears_the_provider_ids():
    """Nothing else could. The edit form does not expose these fields, and
    clearing the metadata listed eighteen names with none of these three among
    them - so a wrong match had no way back at all."""
    for field in ("gog_product_id", "steam_appid", "igdb_id"):
        assert field in CLEARED_LIBRARY_FIELDS


def test_every_field_it_clears_is_a_field_the_game_has():
    """A name with a typo in it would set a new attribute on the object and
    clear nothing, quietly."""
    columns = {c.key for c in LibraryGame.__mapper__.columns}
    unknown = [f for f in CLEARED_LIBRARY_FIELDS if f not in columns]
    assert not unknown, f"clears columns that do not exist: {unknown}"


def test_it_does_not_clear_what_identifies_the_game():
    """Title, slug and where it came from survive: this empties the scraped
    metadata, it does not delete the entry."""
    for kept in ("title", "slug", "source", "is_active", "id"):
        assert kept not in CLEARED_LIBRARY_FIELDS


@pytest.mark.asyncio
async def test_clearing_every_game_clears_what_clearing_one_game_clears(monkeypatch):
    """The two routes have to empty the same fields, and asserting on the tuple
    alone never checked that they did.

    The bulk route carried its own copy of the list written out by hand. The
    provider ids were added to the tuple and never reached the copy, so clearing
    one game let go of its match and clearing every game did not - and the
    library-wide route is the one somebody reaches for precisely when the
    matches have gone wrong across the board. Reading the statement it builds is
    the only way to see the two agree.
    """
    from endpoints.library import library_router

    seen: dict = {}

    class _Session:
        async def execute(self, stmt):
            seen["fields"] = {col.key for col in stmt._values}
            return SimpleNamespace(rowcount=7)

        async def commit(self):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return False

    monkeypatch.setattr("handler.database.session.async_session_factory",
                        lambda: _Session())

    out = await library_router.clear_all_library_metadata.__wrapped__(
        SimpleNamespace(state=SimpleNamespace(user=SimpleNamespace(id=1)))
    )

    assert out["cleared"] == 7
    assert seen["fields"] == set(CLEARED_LIBRARY_FIELDS), (
        "the library-wide clear and the one-game clear no longer empty the same "
        "fields: " + str(set(CLEARED_LIBRARY_FIELDS) ^ seen["fields"])
    )
