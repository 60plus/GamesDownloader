"""Converting a disc to CHD may give up only the files that are really its own.

A conversion replaces a sheet and every file the sheet names with one .chd,
and then deletes those files or moves them into `_originals/`. It collected
them by reading the sheet and nothing else. A sheet naming a file is not the
same as the file being that sheet's:

  * two regional sheets side by side can name one data file. Converting the
    European one took the track from under the French one - deleted with
    "remove the originals", moved out of the folder without it. Either way the
    other game stopped starting, and in the first case its only copy was gone.
  * a sheet can name a file that is somebody else's entry in the library.

Deleting a ROM already asks both questions (`spoken_for_elsewhere` for the other
sheets, the database for the other entries). Conversion now asks the same ones,
so the two ways a disc's files leave the folder cannot disagree about whose
they are.

Real discs, real chdman, a real database, as in test_chd_set_conversion.
"""
from __future__ import annotations

import shutil

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from models.rom import Rom
from models.rom_platform import RomPlatform

needs_chdman = pytest.mark.skipif(
    not shutil.which("chdman"), reason="chdman nie jest w tym obrazie")


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


def _data(path, sectors=512):
    path.write_bytes(bytes(range(256)) * 8 * sectors)


def _sheet(path, track):
    path.write_text(
        f'FILE "{track}" BINARY\n  TRACK 01 MODE1/2048\n    INDEX 01 00:00:00\n',
        encoding="utf-8",
    )


def _row(db, rom_id, directory, fs_name, **extra):
    stem, _, ext = fs_name.rpartition(".")
    db.add(Rom(
        id=rom_id, platform_id=1, name=stem,
        fs_name=fs_name, fs_name_no_ext=stem, fs_extension=ext,
        fs_path=str(directory), fs_size_bytes=(directory / fs_name).stat().st_size,
        **extra,
    ))


async def _two_regions_one_track(db, tmp_path):
    """Europe and France, one data file between them, as the scanner stores it:
    the track goes to the sheet that sorts first."""
    psx = tmp_path / "psx"
    psx.mkdir()
    _data(psx / "Game (Track 1).bin")
    _sheet(psx / "Game (Europe).cue", "Game (Track 1).bin")
    _sheet(psx / "Game (France).cue", "Game (Track 1).bin")
    _row(db, 1, psx, "Game (Europe).cue")
    _row(db, 2, psx, "Game (France).cue")
    _row(db, 11, psx, "Game (Track 1).bin", track_of="Game (Europe).cue")
    await db.commit()
    return psx


def test_both_sheets_really_name_the_one_file(tmp_path):
    """Without this the assertions below could pass because the sheet reader
    never found the track at all."""
    from handler.filesystem.rom_scanner import tracks_referenced_by

    _sheet(tmp_path / "Game (Europe).cue", "Game (Track 1).bin")
    _sheet(tmp_path / "Game (France).cue", "Game (Track 1).bin")
    for region in ("Europe", "France"):
        assert "game (track 1).bin" in tracks_referenced_by(tmp_path / f"Game ({region}).cue")


@needs_chdman
@pytest.mark.asyncio
async def test_removing_the_originals_leaves_a_track_another_sheet_still_names(db, tmp_path):
    from handler.roms.chd_jobs import convert_set

    psx = await _two_regions_one_track(db, tmp_path)

    result = await convert_set(1, delete_source=True, session=db)

    assert (psx / "Game (Europe).chd").is_file()
    assert not (psx / "Game (Europe).cue").exists(), "arkusz konwertowanej plyty ma odejsc"
    assert (psx / "Game (Track 1).bin").is_file(), (
        "konwersja wersji europejskiej skasowala sciezke, z ktorej gra francuska wersja"
    )
    assert (psx / "Game (France).cue").is_file()
    assert result["kept"] == ["Game (Track 1).bin"], "tray ma wiedziec, co zostalo i dlaczego"
    assert result["saved_bytes"] == 0, (
        "zostawiony plik nie zwolnil miejsca, a byl liczony jako zaoszczedzony"
    )


@needs_chdman
@pytest.mark.asyncio
async def test_keeping_the_originals_does_not_move_a_shared_track_out_of_the_folder(db, tmp_path):
    from handler.roms.chd_jobs import convert_set

    psx = await _two_regions_one_track(db, tmp_path)

    await convert_set(1, delete_source=False, session=db)

    assert (psx / "Game (Track 1).bin").is_file(), (
        "sciezka wyniesiona do _originals/ - francuska wersja przestaje startowac"
    )
    assert {p.name for p in (psx / "_originals").iterdir()} == {"Game (Europe).cue"}


@needs_chdman
@pytest.mark.asyncio
async def test_a_sheet_does_not_take_a_file_that_is_another_entry(db, tmp_path):
    """A file with a row of its own is somebody's game, whatever a sheet beside
    it says. Uploading a .cue that names it is all it took."""
    from handler.roms.chd_jobs import convert_set

    psx = tmp_path / "psx"
    psx.mkdir()
    _data(psx / "Victim.bin")
    _sheet(psx / "evil.cue", "Victim.bin")
    _row(db, 5, psx, "Victim.bin")
    _row(db, 9, psx, "evil.cue")
    await db.commit()

    result = await convert_set(9, delete_source=True, session=db)

    assert (psx / "Victim.bin").is_file(), "konwersja cudzego arkusza skasowala czyjs wpis"
    assert result["kept"] == ["Victim.bin"]


@needs_chdman
@pytest.mark.asyncio
async def test_a_track_nothing_else_needs_still_goes_with_the_conversion(db, tmp_path):
    """The legal case. A track with no row and no other sheet naming it is this
    disc's alone, and leaving it would strand it beside the .chd."""
    from handler.roms.chd_jobs import convert_set

    psx = tmp_path / "psx"
    psx.mkdir()
    _data(psx / "Solo.bin")
    _sheet(psx / "Solo.cue", "Solo.bin")
    _row(db, 3, psx, "Solo.cue")
    await db.commit()

    result = await convert_set(3, delete_source=True, session=db)

    assert (psx / "Solo.chd").is_file()
    assert not (psx / "Solo.bin").exists(), "sciezka, ktorej nikt nie potrzebuje, zostala"
    assert not (psx / "Solo.cue").exists()
    assert result["kept"] == []
    assert result["saved_bytes"] > 0
