"""A ROM is the file at a place, not a name on a platform.

Every lookup in the library asks `WHERE platform_id = ? AND fs_name = ?` and
takes the first row back. That held while the library was flat, because one
directory cannot hold two files of one name. It stops holding the moment a
platform has more than one directory, and a platform already can: the scan
reads `{platform}/` and `{platform}/roms/` as a union. Put `Game.chd` in both
and the second file finds the first file's row, overwrites its path, its size
and its hashes, and reports itself present. One of the two games is then gone
from the library while its file sits on the disk, and the row that remains
points somewhere its owner never put it.

Nothing raises. The scan counts two files found and leaves one row.

This is also the wall in front of per-game folders, where two games holding a
`disc1.bin` is not an edge case but the ordinary shape, and where the damage
is worse than a lost row: deletes and CHD conversions issue their DELETE and
UPDATE across the whole platform keyed on that same bare name, so they reach
into the folder next door and unlink files that belong to another game.

So identity gains the directory. `fs_path` holds the parent directory of the
file, which makes (platform_id, fs_path, fs_name) the triple that is actually
unique on disk, and a lookup has to say which directory it means.
"""
from __future__ import annotations

import io
import pathlib

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from handler.database.rom_handler import rom_handler
from models.rom import Rom
from models.rom_platform import RomPlatform

SCANNER = (pathlib.Path(__file__).resolve().parent.parent
           / "handler" / "filesystem" / "rom_scanner.py")


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(RomPlatform.__table__.create)
        await conn.run_sync(Rom.__table__.create)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        session.add(RomPlatform(id=1, fs_slug="psx", slug="playstation", name="PlayStation"))
        await session.commit()
        yield session
    await engine.dispose()


async def _scan_found(db, directory: str, fs_name: str = "Game.chd", size: int = 10):
    """One file, upserted the way the walk upserts what it just listed."""
    stem, _, ext = fs_name.rpartition(".")
    return await rom_handler.upsert(
        1, fs_name, stem, ext, directory, size, session=db,
    )


async def _count(db) -> int:
    return (await db.execute(select(func.count(Rom.id)))).scalar_one()


@pytest.mark.asyncio
async def test_two_files_of_one_name_keep_two_rows(db):
    """The failure this file exists for, at the size the scan meets it."""
    await _scan_found(db, "/roms/psx", size=111)
    await _scan_found(db, "/roms/psx/roms", size=222)

    assert await _count(db) == 2, (
        "drugi plik o tej samej nazwie wszedl na wiersz pierwszego"
    )


@pytest.mark.asyncio
async def test_neither_row_is_moved_to_the_other_directory(db):
    """Counting rows is not enough: the row that loses this race keeps its id
    and its saves, and points at a file that is not its own."""
    await _scan_found(db, "/roms/psx", size=111)
    await _scan_found(db, "/roms/psx/roms", size=222)

    rows = (await db.execute(select(Rom).order_by(Rom.fs_path))).scalars().all()
    assert [(r.fs_path, r.fs_size_bytes) for r in rows] == [
        ("/roms/psx", 111), ("/roms/psx/roms", 222),
    ]


@pytest.mark.asyncio
async def test_the_same_file_seen_twice_is_still_one_row(db):
    """The other half, and the reason this cannot be fixed by always inserting:
    a second scan of an unchanged library must not double the library."""
    first = await _scan_found(db, "/roms/psx", size=111)
    again = await _scan_found(db, "/roms/psx", size=111)

    assert first.id == again.id
    assert await _count(db) == 1


@pytest.mark.asyncio
async def test_a_lookup_says_which_directory_it_means(db):
    """Without the directory the answer is whichever row the database hands
    back first, which is not a choice anybody made."""
    await _scan_found(db, "/roms/psx", size=111)
    await _scan_found(db, "/roms/psx/roms", size=222)

    here = await rom_handler.get_by_fs_name(1, "Game.chd", "/roms/psx", session=db)
    there = await rom_handler.get_by_fs_name(1, "Game.chd", "/roms/psx/roms", session=db)

    assert here.fs_size_bytes == 111
    assert there.fs_size_bytes == 222
    assert here.id != there.id


@pytest.mark.asyncio
async def test_a_directory_with_no_such_file_answers_nothing(db):
    """A lookup that misses must miss, not fall back to a namesake elsewhere."""
    await _scan_found(db, "/roms/psx", size=111)

    assert await rom_handler.get_by_fs_name(
        1, "Game.chd", "/roms/psx/roms", session=db) is None


@pytest.mark.asyncio
async def test_a_restored_save_is_not_guessed_onto_one_of_two_namesakes(db):
    """Importing a save from another install matches by hash, then by file
    name, then by title. The archive carries no folder, so the file name step
    has to answer for two games at once - and attaching somebody's hours to
    the wrong game is worse than saying the save could not be placed."""
    await _scan_found(db, "/roms/psx", size=111)
    await _scan_found(db, "/roms/psx/roms", size=222)

    found = await rom_handler.find_for_import(
        fs_name="Game.chd", platform_id=1, session=db)

    assert found is None, (
        "zapis przypiety do losowej z dwoch gier o tej samej nazwie pliku"
    )


@pytest.mark.asyncio
async def test_a_restored_save_still_finds_the_one_rom_of_that_name(db):
    """The ordinary case, which must keep working: one candidate, matched."""
    await _scan_found(db, "/roms/psx", size=111)

    found = await rom_handler.find_for_import(
        fs_name="Game.chd", platform_id=1, session=db)

    assert found is not None and found.fs_size_bytes == 111


def test_the_scan_asks_for_the_row_in_the_directory_it_walked():
    """A handler that can tell two directories apart, called from a walk that
    does not pass one, is the same bug with better test coverage."""
    source = io.open(SCANNER, encoding="utf-8").read()
    walk = source.index("async def scan_roms_path")
    body = source[walk:]
    at = body.index("rom_handler.get_by_fs_name(")
    call = body[at:at + 160]
    assert "fs_path" in call, (
        f"skan pyta o wiersz po samej nazwie: {call.splitlines()[0]}"
    )
