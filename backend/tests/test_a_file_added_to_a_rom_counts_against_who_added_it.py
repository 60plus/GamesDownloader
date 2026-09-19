"""A file added beside a ROM game counts against the account that added it.

"Add file" on a ROM is open to uploaders (the owner, 2026-09-18), and every
door bytes come in through is counted (test_everything_brought_in_is_counted).
The files beside a game have no rows of their own, so each one added through
the page gets one (models/rom_added_file.py), and the quota sums them.

The bar and the list under it have to agree ("three routes hand the figure and
the list out together and promise in writing that they agree", quota.py), so
what the bar charges for appears on the list:

  * added to a ROM the account owns - on that ROM's row, which grows;
  * added to somebody else's ROM - a row of its own, that the account cannot
    delete (the game is not theirs) but can take its files back from
    ("Remove my files", /roms/{id}/my-files), the way a DLC added to somebody
    else's game is listed.
"""
from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

ME, SOMEBODY = 7, 9


@pytest_asyncio.fixture
async def db(monkeypatch):
    from models.library import Library, LibraryMembership
    from models.library_file import LibraryFile
    from models.library_game import LibraryGame
    from models.rom import Rom
    from models.rom_added_file import RomAddedFile
    from models.rom_platform import RomPlatform

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    async with engine.begin() as conn:
        for model in (LibraryGame, LibraryFile, RomPlatform, Rom, RomAddedFile,
                      Library, LibraryMembership):
            await conn.run_sync(model.__table__.create)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    import handler.database.session as session_mod
    monkeypatch.setattr(session_mod, "async_session_factory", maker)

    def rom(rid, name, owner, size, missing=False):
        return Rom(id=rid, platform_id=1, name=name, fs_name=f"{name}.chd", fs_name_no_ext=name,
                   fs_extension="chd", fs_path=f"/l/psx/{name}", fs_size_bytes=size,
                   published_by=owner, missing_from_fs=missing)

    async with maker() as s:
        s.add(RomPlatform(id=1, fs_slug="psx", slug="playstation", name="PlayStation"))
        s.add(rom(1, "Theirs", SOMEBODY, 1000))
        s.add(rom(2, "Mine", ME, 2000))
        s.add(rom(3, "Gone", ME, 4000, missing=True))
        s.add(RomAddedFile(rom_id=1, rel_path="mods/a.zip", size_bytes=100, published_by=ME))
        s.add(RomAddedFile(rom_id=1, rel_path="extras/b.txt", size_bytes=200, published_by=ME))
        s.add(RomAddedFile(rom_id=1, rel_path="extras/c.txt", size_bytes=999, published_by=SOMEBODY))
        s.add(RomAddedFile(rom_id=2, rel_path="extras/Manual.pdf", size_bytes=50, published_by=ME))
        s.add(RomAddedFile(rom_id=3, rel_path="mods/d.zip", size_bytes=5, published_by=ME))
        await s.commit()
    yield maker
    await engine.dispose()


@pytest.mark.asyncio
async def test_the_bar_counts_what_the_account_added(db):
    from handler.library import quota

    # Its own ROM (2000), not the missing one, and every file it added: 355.
    assert await quota.used_bytes(ME) == 2000 + 100 + 200 + 50 + 5


@pytest.mark.asyncio
async def test_a_file_added_to_somebody_elses_rom_is_theirs_to_take_back(db):
    from handler.library import quota

    rows = {g["id"]: g for g in await quota.owned_games(ME) if g["kind"] == "rom"}
    theirs = rows[1]
    assert (theirs["size_bytes"], theirs["file_count"]) == (300, 2)
    assert theirs["can_delete"] is False and theirs["files_only"] is True


@pytest.mark.asyncio
async def test_a_file_added_to_its_own_rom_grows_that_row(db):
    from handler.library import quota

    rows = {g["id"]: g for g in await quota.owned_games(ME) if g["kind"] == "rom"}
    mine = rows[2]
    assert (mine["size_bytes"], mine["file_count"]) == (2050, 2)
    assert mine["files_only"] is False


@pytest.mark.asyncio
async def test_the_list_adds_up_to_the_bar(db):
    from handler.library import quota

    listed = sum(g["size_bytes"] for g in await quota.owned_games(ME))
    assert listed == await quota.used_bytes(ME), "pasek i lista sie rozjechaly"


@pytest.mark.asyncio
async def test_somebody_elses_files_are_not_on_my_list(db):
    from handler.library import quota

    assert all(g["size_bytes"] != 999 for g in await quota.owned_games(ME))
    assert await quota.used_bytes(SOMEBODY) == 1000 + 999


# ── A claim takes them over like the game's own files ────────────────────────


@pytest.mark.asyncio
async def test_handing_over_moves_only_that_accounts_files_of_that_rom(db):
    from handler.database.rom_added_file_handler import rom_added_file_handler
    from handler.library import quota

    async with db() as s, s.begin():
        moved = await rom_added_file_handler.hand_over(1, ME, 1, session=s)

    assert moved == 2
    assert await quota.used_bytes(ME) == 2000 + 50 + 5
    assert await quota.used_bytes(SOMEBODY) == 1000 + 999
