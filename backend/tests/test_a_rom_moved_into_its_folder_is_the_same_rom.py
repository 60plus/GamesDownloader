"""Moving a ROM into its own folder must not turn it into a different game.

Until now a ROM was found by name alone, so moving `Game.chd` from
`{platform}/` into `{platform}/Game/` was free: the scan found the row by its
name and wrote the new folder onto it. Saves, play history, collections and
the owner all hang off that row's id and never noticed.

Identity has the directory in it now, which is what stops two games sharing a
file name from merging - and it means that move is no longer free. Left alone,
the scan sees a file it has no row for, makes a new one, and leaves the old row
marked missing: the game appears twice, and the copy people have hours in is
the one that reads as gone.

Renaming is already handled: a vanished row and an arrival are merged when
their digest and size agree. That does not cover this, because a digest is
nullable and unhashed is routine for anything over the hashing ceiling - which
is most of a CHD library, and exactly the files worth moving.

So a move is recognised as a move: same file name, one level up or one level
down, and the file is gone from where the row says it is. Anything less certain
is left as two rows, which is a mess a person can fix, rather than one row
carrying somebody else's saves.
"""
from __future__ import annotations

import io
import pathlib

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from handler.database.rom_handler import rom_handler
from handler.filesystem.rom_scanner import moved_row
from models.rom import Rom
from models.rom_platform import RomPlatform

SCANNER = (pathlib.Path(__file__).resolve().parent.parent
           / "handler" / "filesystem" / "rom_scanner.py")

PLATFORM = "/roms/psx"
GAME = "/roms/psx/Silent Hill"


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


def _row(db, rom_id: int, directory: str, fs_name: str = "Game.chd") -> None:
    stem, _, ext = fs_name.rpartition(".")
    db.add(Rom(id=rom_id, platform_id=1, name=stem, fs_name=fs_name,
               fs_name_no_ext=stem, fs_extension=ext, fs_path=directory,
               fs_size_bytes=10))


# ── Which rows are even worth asking about ──────────────────────────────────


@pytest.mark.asyncio
async def test_only_the_directories_asked_about_are_searched(db):
    _row(db, 1, PLATFORM)
    _row(db, 2, "/roms/psx/Suikoden")
    _row(db, 3, "/roms/snes")
    await db.commit()

    found = await rom_handler.rows_named_in(1, "Game.chd", [PLATFORM], session=db)

    assert [r.id for r in found] == [1]


@pytest.mark.asyncio
async def test_nothing_asked_is_nothing_searched(db):
    _row(db, 1, PLATFORM)
    await db.commit()

    assert await rom_handler.rows_named_in(1, "Game.chd", [], session=db) == []


# ── Whether an arrival is a move, decided without touching the database ─────


def _gone(_directory: str, _fs_name: str) -> bool:
    return False


def _still_there(_directory: str, _fs_name: str) -> bool:
    return True


def test_one_candidate_whose_file_is_gone_is_the_move():
    assert moved_row([{"id": 7, "fs_path": PLATFORM}], "Game.chd", _gone) == 7


def test_a_candidate_whose_file_is_still_there_is_a_different_copy():
    """Two files of one name, one in the platform folder and one in a game
    folder, is the shape this whole change exists to keep apart. Claiming the
    row would put the older file's saves on the newer file."""
    assert moved_row([{"id": 7, "fs_path": PLATFORM}], "Game.chd", _still_there) is None


def test_two_candidates_are_left_alone():
    """Timid on purpose, like the rename rule beside it: two rows is a mess a
    person can fix, one row carrying the wrong game's hours is not."""
    candidates = [{"id": 7, "fs_path": PLATFORM}, {"id": 8, "fs_path": GAME}]
    assert moved_row(candidates, "Game.chd", _gone) is None


def test_no_candidates_is_simply_a_new_game():
    assert moved_row([], "Game.chd", _gone) is None


# ── The row really moves ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_moving_a_row_keeps_its_id_and_changes_its_folder(db):
    _row(db, 42, PLATFORM)
    await db.commit()

    await rom_handler.move_row_to(42, GAME, session=db)

    row = await rom_handler.get_by_fs_name(1, "Game.chd", GAME, session=db)
    assert row is not None and row.id == 42, (
        "przeniesiony ROM dostal nowy wiersz zamiast zachowac swoj"
    )
    assert await rom_handler.get_by_fs_name(1, "Game.chd", PLATFORM, session=db) is None


# ── And the walk actually asks ──────────────────────────────────────────────


def test_the_scan_asks_whether_an_unknown_file_is_a_move():
    """A rule that is correct and never called is the same lost save with
    better test coverage."""
    source = io.open(SCANNER, encoding="utf-8").read()
    walk = source.index("async def scan_roms_path")
    body = source[walk:]
    at = body.index("rom_handler.get_by_fs_name(")
    window = body[at:at + 1200]
    assert "moved_row(" in window, "spacer nie pyta, czy plik sie przeniosl"
    assert "move_row_to(" in window, "spacer nie przenosi wiersza, ktory rozpoznal"
