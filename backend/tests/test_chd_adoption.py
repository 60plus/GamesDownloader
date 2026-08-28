"""What happens to the library row when a disc becomes a CHD.

The file changes and the game does not. Saves, savestates and play history all
key on the row's id, so the row has to survive the conversion: a new row with
the new filename would look identical on the shelf and would have lost every
hour anybody put into the game.

The other half is the disc that was there before. Deleting it is the person's
choice, made before the conversion starts, and when they say no it cannot
simply stay where it is: the row now names the .chd, so the next scan would
find an unclaimed .zip beside it and file it as a second copy of the same
game. It goes into a folder the scan does not descend into instead.
"""
from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from handler.database.rom_handler import rom_handler
from models.rom import Rom
from models.rom_platform import RomPlatform


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


def _rom(**over):
    base = dict(
        platform_id=1,
        fs_name="Game (Disc 1).cue",
        fs_name_no_ext="Game (Disc 1)",
        fs_extension="cue",
        fs_path="/data/games/roms/psx",
        fs_size_bytes=100,
    )
    base.update(over)
    return Rom(**base)


@pytest.mark.asyncio
async def test_the_row_survives_the_conversion_with_everything_that_matters(db):
    """Its id above all: a savestate belongs to a row, not to a filename."""
    db.add(_rom(
        id=65, name="Final Fantasy IX", slug="final-fantasy-ix",
        disk_group="Final Fantasy IX", disk_number=1,
        crc_hash="deadbeef", md5_hash="0" * 32, sha1_hash="1" * 40,
    ))
    await db.commit()

    await rom_handler.adopt_converted_file(
        65, "Game (Disc 1).chd", 431976198, "12b44045ba9b51ddda320c465056dfb77d43ef3b",
        session=db,
    )

    row = (await db.execute(select(Rom).where(Rom.id == 65))).scalar_one()
    assert row.id == 65, "wiersz musi zostac ten sam"
    assert row.fs_name == "Game (Disc 1).chd"
    assert row.fs_name_no_ext == "Game (Disc 1)"
    assert row.fs_extension == "chd"
    assert row.fs_size_bytes == 431976198
    assert row.name == "Final Fantasy IX", "metadane zostaja"
    assert row.disk_group == "Final Fantasy IX" and row.disk_number == 1, \
        "przynaleznosc do kompletu zostaje, inaczej gra sie rozpada na cztery"


@pytest.mark.asyncio
async def test_the_hash_becomes_the_one_the_header_carries(db):
    """A CHD is identified by the SHA-1 in its header and by nothing else. The
    old digests described a file that no longer exists, and leaving them there
    would have the scan believe this row was already hashed correctly."""
    db.add(_rom(id=7, crc_hash="deadbeef", md5_hash="0" * 32, sha1_hash="1" * 40))
    await db.commit()

    await rom_handler.adopt_converted_file(
        7, "Game.chd", 10, "12b44045ba9b51ddda320c465056dfb77d43ef3b", session=db)

    row = (await db.execute(select(Rom).where(Rom.id == 7))).scalar_one()
    assert row.sha1_hash == "12b44045ba9b51ddda320c465056dfb77d43ef3b"
    assert not row.crc_hash, "stary CRC opisywal inny plik"
    assert not row.md5_hash, "stary MD5 opisywal inny plik"


@pytest.mark.asyncio
async def test_the_tracks_of_the_old_sheet_stop_being_rows(db):
    """A .cue keeps its .bin as a row of its own, marked as a track. After the
    conversion there is no sheet and no track, only one file, and a row
    pointing at a .bin that is about to go is a row pointing at nothing."""
    db.add(_rom(id=7, fs_name="Game (Disc 1).cue"))
    db.add(_rom(
        id=8, fs_name="Game (Disc 1).bin", fs_name_no_ext="Game (Disc 1)",
        fs_extension="bin", track_of="Game (Disc 1).cue",
    ))
    await db.commit()

    await rom_handler.adopt_converted_file(7, "Game (Disc 1).chd", 10, "a" * 40,
                                           session=db)

    left = (await db.execute(select(Rom).where(Rom.platform_id == 1))).scalars().all()
    assert [r.id for r in left] == [7], "sciezka .bin powinna zniknac z biblioteki"


@pytest.mark.asyncio
async def test_a_track_of_a_different_sheet_is_left_alone(db):
    """Two games in one folder is the normal case, and one of them is being
    converted. Taking the neighbour's track with it would be the third time
    this project deleted somebody's data by being too broad."""
    db.add(_rom(id=7, fs_name="Game (Disc 1).cue"))
    db.add(_rom(id=8, fs_name="Game (Disc 1).bin", track_of="Game (Disc 1).cue"))
    db.add(_rom(id=9, fs_name="Other (Disc 1).bin", track_of="Other (Disc 1).cue"))
    await db.commit()

    await rom_handler.adopt_converted_file(7, "Game (Disc 1).chd", 10, "a" * 40,
                                           session=db)

    left = {r.id for r in (await db.execute(select(Rom))).scalars().all()}
    assert left == {7, 9}, "cudzy sciezka nie ma prawa zniknac"


@pytest.mark.asyncio
async def test_converting_a_disc_that_is_not_there_changes_nothing(db):
    from fastapi import HTTPException

    with pytest.raises(HTTPException):
        await rom_handler.adopt_converted_file(999, "x.chd", 1, "a" * 40, session=db)


# ── The disc that was there before ────────────────────────────────────────────

def test_a_kept_original_leaves_the_part_of_the_shelf_the_scan_reads(tmp_path):
    """The row names the .chd now, so a .zip left beside it is unclaimed and
    the next scan would file it as a second copy of the same game. The scan
    reads files in the platform directory and does not descend, so one level
    down is out of its sight and still in the person's."""
    from handler.roms.chd_convert import retire_sources

    psx = tmp_path / "psx"
    psx.mkdir()
    source = psx / "Game (Disc 1).zip"
    source.write_bytes(b"disc")
    keep = psx / "Game (Disc 1).sbi"
    keep.write_bytes(b"\0" * 452)

    moved = retire_sources([source], psx)

    assert not source.exists(), "oryginal zostal tam, gdzie skan go widzi"
    assert moved and moved[0].is_file()
    assert moved[0].parent.name == "_originals"
    assert moved[0].read_bytes() == b"disc", "plik ma byc przeniesiony, nie podmieniony"
    assert keep.is_file(), "plik podkanalu zostaje przy plycie, rdzen go potrzebuje"


def test_the_scan_does_not_look_inside_the_folder_the_originals_go_to(tmp_path):
    """The whole plan rests on this, so it is asked of the scanner itself
    rather than assumed from reading it."""
    from handler.filesystem.rom_scanner import scan_candidates

    psx = tmp_path / "psx"
    (psx / "_originals").mkdir(parents=True)
    (psx / "Game (Disc 1).chd").write_bytes(b"MComprHD")
    (psx / "_originals" / "Game (Disc 1).zip").write_bytes(b"disc")

    found = {p.name for p in scan_candidates(psx)}
    assert found == {"Game (Disc 1).chd"}, f"skan zajrzal gdzie nie trzeba: {found}"


def test_retiring_never_reaches_outside_the_directory_it_was_given(tmp_path):
    """fs_path is a stored string and this moves files. A row pointing
    somewhere else, through a symlink or after the library path moved under
    it, must not turn a conversion into arbitrary file movement."""
    from handler.roms.chd_convert import retire_sources

    psx = tmp_path / "psx"
    psx.mkdir()
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    stranger = outside / "not ours.zip"
    stranger.write_bytes(b"someone else's file")

    moved = retire_sources([stranger], psx)

    assert moved == [], "nic spoza katalogu nie powinno byc ruszone"
    assert stranger.is_file(), "cudzy plik zostal ruszony"
