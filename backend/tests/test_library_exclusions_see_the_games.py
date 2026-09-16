"""The library side of the exclusions has to look where the games actually are.

A library holds its games one of two ways, and which one depends on the library:
the built-in Games library holds them by the `in_default_library` flag, and a
user-created library holds them through `library_membership`. The listing that
draws the library page has that branch in it, keyed on the slug.

`games_with_paths` was written knowing only about membership. On a real install
that is not a partial answer, it is no answer at all: measured on the running
server, there are 41 games and ZERO membership rows, all 41 carried by the flag.
So the preview reported "nothing already in the library matches" for every
library and every pattern, and the removal button never appeared. A feature that
is a permanent no-op while reporting success is worse than one that is missing.
"""
from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from handler.database.library_registry_handler import library_registry_handler
from models.library import Library, LibraryMembership
from models.library_file import LibraryFile
from models.library_game import LibraryGame


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(Library.__table__.create)
        await conn.run_sync(LibraryGame.__table__.create)
        await conn.run_sync(LibraryFile.__table__.create)
        await conn.run_sync(LibraryMembership.__table__.create)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        session.add(Library(id=2, slug="games", name="Games", kind="custom",
                            storage_folder="CUSTOM"))
        session.add(Library(id=9, slug="kids", name="Kids", kind="custom_lib",
                            storage_folder="KIDS"))
        # Carried by the flag, with no membership row anywhere - which is what
        # every game on the owner's server looks like.
        session.add(LibraryGame(id=1, title="Flagged", slug="flagged",
                                source="custom", is_active=True,
                                in_default_library=True))
        session.add(LibraryFile(id=1, library_game_id=1, filename="thing.exe",
                                file_path="/data/games/CUSTOM/mods/thing.exe",
                                source="custom"))
        # Carried by membership, and NOT in the default library.
        session.add(LibraryGame(id=2, title="Member", slug="member",
                                source="custom", is_active=True,
                                in_default_library=False))
        session.add(LibraryFile(id=2, library_game_id=2, filename="other.exe",
                                file_path="/data/games/KIDS/mods/other.exe",
                                source="custom"))
        session.add(LibraryMembership(library_game_id=2, library_id=9))
        await session.commit()
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_the_builtin_games_library_finds_its_flagged_games(db):
    lib = await db.get(Library, 2)
    rows = await library_registry_handler.games_with_paths(lib, session=db)
    assert [r["title"] for r in rows] == ["Flagged"], (
        "wbudowana biblioteka Games nie widzi swoich gier, wiec podglad zawsze "
        "powie, ze nic nie pasuje"
    )
    assert rows[0]["paths"] == ["/data/games/CUSTOM/mods/thing.exe"]


@pytest.mark.asyncio
async def test_a_user_library_still_finds_its_members(db):
    lib = await db.get(Library, 9)
    rows = await library_registry_handler.games_with_paths(lib, session=db)
    assert [r["title"] for r in rows] == ["Member"]


@pytest.mark.asyncio
async def test_the_two_libraries_do_not_see_each_other(db):
    """The flagged game is not in Kids, and the member is not in the default
    library. A rule that returned both everywhere would make a pattern saved on
    one library remove games from another."""
    games = await library_registry_handler.games_with_paths(
        await db.get(Library, 2), session=db)
    kids = await library_registry_handler.games_with_paths(
        await db.get(Library, 9), session=db)
    assert {r["id"] for r in games} & {r["id"] for r in kids} == set()


def test_the_rule_is_the_one_the_library_page_uses():
    """Both branches key on the same thing. Two rules for "what is in this
    library" is how the settings screen and the library page come to disagree
    about which games exist."""
    import io
    import pathlib

    backend = pathlib.Path(__file__).resolve().parent.parent
    listing = io.open(backend / "endpoints" / "library" / "library_router.py",
                      encoding="utf-8").read()
    # The listing branch: anything that is not "games" goes by membership.
    assert 'library != "games"' in listing

    from handler.database.library_registry_handler import holds_games_by_flag
    assert holds_games_by_flag(type("L", (), {"slug": "games"})())
    assert not holds_games_by_flag(type("L", (), {"slug": "kids"})())


# ── A library that also feeds the default one ────────────────────────────────
#
# Such a library puts every game it scans on both shelves: the in_default_library
# flag AND a membership row. That is one decision expressed twice, and counting
# it as two shelves made every game there score 2 - above the cautious rule that
# leaves a game on a second shelf alone - so the removal half of the exclusions
# was permanently dead, while the card printed "Nothing already in the library
# matches". A feature that is a no-op reporting success is worse than one that
# is missing, which is the sentence at the top of this file.

@pytest_asyncio.fixture
async def feeding_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(Library.__table__.create)
        await conn.run_sync(LibraryGame.__table__.create)
        await conn.run_sync(LibraryFile.__table__.create)
        await conn.run_sync(LibraryMembership.__table__.create)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        session.add(Library(id=2, slug="games", name="Games", kind="custom",
                            storage_folder="CUSTOM"))
        session.add(Library(id=9, slug="ports", name="PC Ports", kind="custom_lib",
                            storage_folder="PC Ports", adds_to_default_library=True))
        session.add(Library(id=10, slug="kids", name="Kids", kind="custom_lib",
                            storage_folder="KIDS"))
        # Scanned by the feeding library: flag AND membership, both written by
        # the same scan.
        session.add(LibraryGame(id=1, title="Ported", slug="ported", source="custom",
                                is_active=True, in_default_library=True))
        session.add(LibraryFile(id=1, library_game_id=1, filename="t.exe",
                                file_path="games/PC Ports/mods/t.exe", source="custom"))
        session.add(LibraryMembership(library_game_id=1, library_id=9))
        # And the same game deliberately put on a third shelf as well.
        session.add(LibraryGame(id=2, title="Shared", slug="shared", source="custom",
                                is_active=True, in_default_library=True))
        session.add(LibraryFile(id=2, library_game_id=2, filename="s.exe",
                                file_path="games/PC Ports/mods/s.exe", source="custom"))
        session.add(LibraryMembership(library_game_id=2, library_id=9))
        session.add(LibraryMembership(library_game_id=2, library_id=10))
        await session.commit()
        yield session
    await engine.dispose()


@pytest.mark.asyncio
async def test_feeding_the_default_library_is_not_a_second_shelf(feeding_db):
    lib = await feeding_db.get(Library, 9)
    rows = await library_registry_handler.games_with_paths(lib, session=feeding_db)
    counts = {r["title"]: r["libraries"] for r in rows}
    assert counts["Ported"] == 1, (
        "gra widziana jako lezaca na dwoch polkach, wiec ostrozna regula nigdy "
        "jej nie obejmie i przycisk usuwania sie nie pojawi"
    )


@pytest.mark.asyncio
async def test_a_real_second_shelf_still_counts(feeding_db):
    """The caution this exists for is kept: a game somebody deliberately put in
    another library as well is still left alone."""
    lib = await feeding_db.get(Library, 9)
    rows = await library_registry_handler.games_with_paths(lib, session=feeding_db)
    counts = {r["title"]: r["libraries"] for r in rows}
    assert counts["Shared"] == 2


@pytest.mark.asyncio
async def test_the_builtin_library_still_counts_its_own_flag(feeding_db):
    """The Games library holds games BY the flag, so there it is the shelf
    rather than an echo of one."""
    lib = await feeding_db.get(Library, 2)
    rows = await library_registry_handler.games_with_paths(lib, session=feeding_db)
    counts = {r["title"]: r["libraries"] for r in rows}
    assert counts["Ported"] == 2, "polka wbudowana przestala liczyc sama siebie"
