"""An upload counts against the account that made it, not against a game's owner.

The quota is a sum over the games an account OWNS, which is right for a game it
also uploaded and wrong for every other way a file can land on one. Two of them
were reachable:

  - `POST /library/games/{game_id}/upload` never asked whether the caller owns
    the game. An uploader who owns nothing has `used_bytes` of zero for ever;
    they pick any game id they can see - `GET /library/games` is a read
    everybody has - and push files into it all day at no cost, while the account
    that does own it is pushed over its limit by uploads it never made.

  - A catalogue entry downloaded a second time reuses the LibraryGame the FIRST
    account created, on purpose, because it is the same game. The bytes then
    hang off somebody else's game and are counted against them.

So the file records who brought it, and the sum reads that in preference to the
game's owner. Falling back to the game keeps every row that already exists
counted exactly as it is counted today, rather than making a release quietly
hand everybody's quota back. And the manual upload asks whose game it is, which
also keeps the delete rule honest: bytes you are charged for sit on a game you
can clear up.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from handler.auth.scopes import Scope
from handler.library.ownership import can_upload_into_game
from models.library_file import LibraryFile
from models.library_game import LibraryGame

ALICE = 3
BOB = 7

UPLOADER = {Scope.LIBRARY_UPLOAD}
ADMIN = {Scope.LIBRARY_UPLOAD, Scope.LIBRARY_ADMIN}


# ── Whose game may be uploaded into ──────────────────────────────────────────

def _game(owner):
    return SimpleNamespace(id=1, published_by=owner)


def test_an_uploader_may_add_to_their_own_game():
    assert can_upload_into_game(UPLOADER, BOB, _game(BOB))


def test_an_uploader_may_not_add_to_somebody_elses():
    assert not can_upload_into_game(UPLOADER, BOB, _game(ALICE))


def test_an_uploader_may_not_add_to_a_game_nobody_owns():
    """Torrent-registered and scanner-registered games have no owner. Reading
    that as "mine" would open every one of them."""
    assert not can_upload_into_game(UPLOADER, BOB, _game(None))


def test_an_administrator_may_add_to_any_game():
    assert can_upload_into_game(ADMIN, 1, _game(ALICE))


def test_both_upload_routes_ask():
    import io
    import pathlib

    source = io.open(
        pathlib.Path(__file__).resolve().parent.parent
        / "endpoints" / "library" / "upload_router.py", encoding="utf-8").read()
    for route in ('"/games/{game_id}/upload"', '"/games/{game_id}/upload-url"'):
        at = source.index(route)
        rest = source[at:]
        # To the next decorator, or to the end of the file for the last route.
        nxt = rest.find("\n@", 10)
        body = rest if nxt < 0 else rest[:nxt]
        assert "assert_can_upload_into" in body, (
            f"trasa {route} nie pyta, czyja to gra"
        )


# ── What the sum reads ───────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def db(monkeypatch):
    """A real database behind the real `used_bytes`, which opens its own."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(LibraryGame.__table__.create)
        await conn.run_sync(LibraryFile.__table__.create)
        from models.rom import Rom
        from models.rom_platform import RomPlatform
        await conn.run_sync(RomPlatform.__table__.create)
        await conn.run_sync(Rom.__table__.create)
        # The listing names the shelf each game sits on, so a fixture without
        # this table tests the sum and skips everything the list does.
        from models.library import Library, LibraryMembership
        await conn.run_sync(Library.__table__.create)
        await conn.run_sync(LibraryMembership.__table__.create)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    import handler.database.session as session_mod
    monkeypatch.setattr(session_mod, "async_session_factory", maker)
    from handler.library import quota
    monkeypatch.setattr(quota, "async_session_factory", maker, raising=False)

    async with maker() as session:
        # Alice's game, and a file she uploaded into it.
        session.add(LibraryGame(id=1, title="Hers", slug="hers", source="custom",
                                is_active=True, published_by=ALICE))
        session.add(LibraryFile(id=1, library_game_id=1, filename="a.zip",
                                file_path="games/CUSTOM/Hers/a.zip", source="custom",
                                size_bytes=100, published_by=ALICE))
        # A file BOB brought into the same game - a second build of a catalogue
        # entry, which deliberately reuses the game the first account created.
        session.add(LibraryFile(id=2, library_game_id=1, filename="b.zip",
                                file_path="games/CUSTOM/Hers/b.zip", source="custom",
                                size_bytes=500, published_by=BOB))
        # And a file from before this column existed: nobody recorded on it.
        session.add(LibraryFile(id=3, library_game_id=1, filename="old.zip",
                                file_path="games/CUSTOM/Hers/old.zip", source="custom",
                                size_bytes=7, published_by=None))
        await session.commit()
    yield maker
    await engine.dispose()


@pytest.mark.asyncio
async def test_a_file_counts_against_whoever_brought_it(db):
    from handler.library import quota

    assert await quota.used_bytes(BOB) == 500, (
        "bajty wgrane przez bob-a licza sie komus innemu, wiec bob nie ma limitu"
    )


@pytest.mark.asyncio
async def test_the_games_owner_is_not_charged_for_somebody_elses_upload(db):
    from handler.library import quota

    # Her own file, plus the one with nobody recorded on it - which falls back
    # to the game, so nothing that already exists stops being counted.
    assert await quota.used_bytes(ALICE) == 107


@pytest.mark.asyncio
async def test_an_account_with_nothing_is_still_zero(db):
    from handler.library import quota

    assert await quota.used_bytes(99) == 0



# ── The bar and the list underneath it ───────────────────────────────────────
#
# `used_bytes` reads the owner of the FILE; `owned_games` - the list a person
# and an administrator actually look at - was left reading the owner of the
# GAME, and summed every file hanging off it. Three routes hand both figures
# out together and all three promise in writing that they agree.
#
# On the shape above, Bob's bar said 500 and his list said nothing at all,
# while Alice's bar said 107 and her single row said 607.

@pytest.mark.asyncio
async def test_the_list_shows_the_game_the_bar_is_charging_for(db):
    from handler.library import quota

    rows = await quota.owned_games(BOB)
    assert [r["id"] for r in rows] == [1], (
        "pasek liczy bob-owi bajty w grze, ktorej jego lista nie pokazuje wcale"
    )


@pytest.mark.asyncio
async def test_the_row_totals_what_that_account_is_charged(db):
    from handler.library import quota

    rows = await quota.owned_games(BOB)
    assert sum(r["size_bytes"] for r in rows) == await quota.used_bytes(BOB)


@pytest.mark.asyncio
async def test_the_owner_of_the_game_is_not_shown_somebody_elses_bytes(db):
    """Her row used to add Bob's 500 to her own 107."""
    from handler.library import quota

    rows = await quota.owned_games(ALICE)
    assert [(r["id"], r["size_bytes"]) for r in rows] == [(1, 107)]
    assert sum(r["size_bytes"] for r in rows) == await quota.used_bytes(ALICE)


@pytest.mark.asyncio
async def test_the_row_counts_only_the_files_that_account_is_charged_for(db):
    from handler.library import quota

    rows = await quota.owned_games(BOB)
    assert rows[0]["file_count"] == 1, "wiersz liczy pliki, ktorych to konto nie wnioslo"


@pytest.mark.asyncio
async def test_a_game_with_no_files_left_is_still_listed(db):
    """The caution that was already there. A game whose files are all gone is
    exactly the wreckage somebody opens this list to clear away, and the join
    that picks the counted files must not drop it."""
    from handler.library import quota

    async with db() as session:
        session.add(LibraryGame(id=2, title="Empty", slug="empty", source="custom",
                                is_active=True, published_by=BOB))
        await session.commit()

    rows = await quota.owned_games(BOB)
    assert 2 in [r["id"] for r in rows]
    assert next(r for r in rows if r["id"] == 2)["size_bytes"] == 0


@pytest.mark.asyncio
async def test_a_row_says_whether_this_account_may_clear_it_away(db):
    """A game Bob is charged for but does not own cannot be deleted by him -
    the delete rule reads the game's owner, and deleting it would take Alice's
    files with it. The row has to say so, or the screen draws a button whose
    only outcome is a 403."""
    from handler.library import quota

    bob = await quota.owned_games(BOB)
    assert bob[0]["can_delete"] is False
    alice = await quota.owned_games(ALICE)
    assert alice[0]["can_delete"] is True

# ── What a selection comes to ────────────────────────────────────────────────

GB = 1024 ** 3


def _asset(name, size):
    return {"name": name, "size": size, "url": f"http://x/{name}", "os": "windows"}


def test_three_builds_that_each_fit_are_refused_when_together_they_do_not():
    """The defect, stated. Windows, Mac and Linux at 4 GB each, 5 GB left: every
    one of them passed the per-build test, so one click queued 12 GB."""
    from handler.library.catalog_sync_handler import refuse_if_over_budget

    assets = [_asset(n, 4 * GB) for n in ("win", "mac", "linux")]
    with pytest.raises(ValueError, match="come to"):
        refuse_if_over_budget(assets, 5 * GB)


def test_a_selection_that_fits_is_still_queued():
    """The other half. A rule that refused everything would break the store."""
    from handler.library.catalog_sync_handler import refuse_if_over_budget

    refuse_if_over_budget([_asset("win", 2 * GB), _asset("mac", 2 * GB)], 5 * GB)


def test_a_selection_that_fits_exactly_is_allowed():
    from handler.library.catalog_sync_handler import refuse_if_over_budget

    refuse_if_over_budget([_asset("win", 3 * GB), _asset("mac", 2 * GB)], 5 * GB)


def test_one_build_too_big_is_still_named_on_its_own():
    """"These come to too much" is unhelpful when one of them could never have
    fitted, so that case keeps its own message."""
    from handler.library.catalog_sync_handler import refuse_if_over_budget

    with pytest.raises(ValueError, match="larger than the upload limit"):
        refuse_if_over_budget([_asset("huge", 9 * GB)], 5 * GB)


def test_a_build_of_unknown_size_does_not_block_the_rest():
    """The store does not always publish a size. Counting it as the whole
    allowance would refuse downloads that are perfectly fine; the per-job
    ceiling stops it as the bytes arrive instead."""
    from handler.library.catalog_sync_handler import refuse_if_over_budget

    refuse_if_over_budget([_asset("unknown", 0), _asset("win", 4 * GB)], 5 * GB)


# ── A claim gives the uploader their space back ──────────────────────────────
#
# `claim_writes` moves one column, on the game. That was enough while the quota
# was a sum over owned GAMES - three docstrings still say so, and say the space
# comes back on the next read with no counter to adjust. Once a file could carry
# an owner of its own, a file stamped with the old owner stopped following the
# game: after a claim the uploader was still charged for it AND had nothing left
# in their list to remove, so they could neither upload nor clear up.

@pytest_asyncio.fixture
async def claimable(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(LibraryGame.__table__.create)
        await conn.run_sync(LibraryFile.__table__.create)
        from models.rom import Rom
        from models.rom_platform import RomPlatform
        await conn.run_sync(RomPlatform.__table__.create)
        await conn.run_sync(Rom.__table__.create)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async with maker() as session:
        session.add(LibraryGame(id=1, title="Theirs", slug="theirs", source="custom",
                                is_active=True, published_by=BOB))
        # Bob's own upload, stamped with his name.
        session.add(LibraryFile(id=1, library_game_id=1, filename="b.zip",
                                file_path="games/CUSTOM/Theirs/b.zip", source="custom",
                                size_bytes=900, published_by=BOB))
        # A build somebody else put on the same game - a second account pulling
        # the same catalogue entry, which lands here on purpose.
        session.add(LibraryFile(id=2, library_game_id=1, filename="a.zip",
                                file_path="games/CUSTOM/Theirs/a.zip", source="custom",
                                size_bytes=100, published_by=ALICE))
        await session.commit()

    import importlib
    import handler.database.session as session_mod
    monkeypatch.setattr(session_mod, "async_session_factory", maker)
    for mod in ("decorators.database", "handler.library.quota"):
        m = importlib.import_module(mod)
        if hasattr(m, "async_session_factory"):
            monkeypatch.setattr(m, "async_session_factory", maker)
    yield maker
    await engine.dispose()


@pytest.mark.asyncio
async def test_a_claim_hands_the_uploader_their_quota_back(claimable):
    from handler.database.library_handler import LibraryHandler
    from handler.library import quota

    assert await quota.used_bytes(BOB) == 900, "test nie odtwarza stanu wyjsciowego"

    async with claimable() as session:
        game = await session.get(LibraryGame, 1)
        game.published_by = 1                    # an administrator claims it
        await session.commit()
    await LibraryHandler().release_files_of(1, BOB)

    assert await quota.used_bytes(BOB) == 0, (
        "po przejeciu uploader nadal placi za bajty, ktorych nie moze usunac"
    )


@pytest.mark.asyncio
async def test_somebody_elses_file_on_that_game_stays_theirs(claimable):
    """The case the column was added for. Alice's build does not become the
    administrator's just because the game changed hands."""
    from handler.database.library_handler import LibraryHandler
    from handler.library import quota

    await LibraryHandler().release_files_of(1, BOB)
    assert await quota.used_bytes(ALICE) == 100


@pytest.mark.asyncio
async def test_releasing_for_nobody_changes_nothing(claimable):
    """A game that had no owner has no files to hand over."""
    from handler.database.library_handler import LibraryHandler

    assert await LibraryHandler().release_files_of(1, None) == 0


@pytest.mark.parametrize("route", ["claim_library_game", "claim_library_games"])
def test_both_claim_routes_hand_the_files_over(route):
    import io
    import pathlib

    backend = pathlib.Path(__file__).resolve().parent.parent
    source = io.open(backend / "endpoints" / "library" / "library_router.py",
                     encoding="utf-8").read()
    at = source.index(f"async def {route}(")
    body = source[at:source.index("\n@", at)]
    assert "release_files_of" in body, (
        f"{route} przenosi tylko gre, wiec limit uploadera sie nie zwalnia"
    )


# ── And the refusal says what was refused ────────────────────────────────────

def test_the_upload_refusal_talks_about_adding_not_removing():
    """One rule guards two different acts now. An uploader adding a file to
    somebody else's game was told they may not REMOVE it - an answer to a
    question nobody asked, leaving them no idea what was actually refused."""
    from fastapi import HTTPException

    from handler.library.ownership import assert_can_upload_into

    request = SimpleNamespace(state=SimpleNamespace(
        user=SimpleNamespace(id=BOB), scopes=UPLOADER))
    with pytest.raises(HTTPException) as raised:
        assert_can_upload_into(request, _game(ALICE))

    detail = str(raised.value.detail).lower()
    assert "add" in detail, f"komunikat nie mowi, o co chodzilo: {detail}"
    assert "remove" not in detail, f"komunikat nadal mowi o usuwaniu: {detail}"


def test_the_delete_refusals_still_talk_about_removing():
    """The other callers really are about removal, so their wording stays."""
    from fastapi import HTTPException

    from handler.library.ownership import assert_can_delete

    request = SimpleNamespace(state=SimpleNamespace(
        user=SimpleNamespace(id=BOB), scopes=UPLOADER))
    with pytest.raises(HTTPException) as raised:
        assert_can_delete(request, _game(ALICE))
    assert "remove" in str(raised.value.detail).lower()
