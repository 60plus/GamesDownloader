"""A disc kept as a sheet weighs what its tracks weigh.

A .cue is a few kilobytes of text naming the .bin files that are the disc, and
the game's page put the sheet's own size on it: "Show details" listed a
PlayStation disc at 1 KB, and a game on one disc said the same under its
buttons. The download has always been the sheet and its tracks together
(rom_with_tracks), so the size is counted from the same rows - what the page
says is what arrives.

Real files, the scan's own plan written into a real database, the way
test_disc_membership.py goes about it.
"""
from __future__ import annotations

from functools import partial
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from handler.database.rom_handler import rom_handler
from handler.filesystem.rom_scanner import plan_disk_assignments, scan_candidates
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


async def _import(session, directory):
    files = scan_candidates(directory)
    for path in files:
        session.add(Rom(platform_id=1, fs_name=path.name, fs_name_no_ext=path.stem,
                        fs_extension=path.suffix.lstrip("."), fs_path=str(directory),
                        fs_size_bytes=path.stat().st_size))
    await session.commit()
    await rom_handler.apply_disk_groups(1, str(directory), plan_disk_assignments(files),
                                        session=session)
    await session.commit()


async def _row(session, directory, fs_name) -> Rom:
    found = await session.execute(
        select(Rom).where(Rom.fs_name == fs_name, Rom.fs_path == str(directory)))
    return found.scalars().one()


def _disc(directory, stem, tracks):
    """A sheet naming one .bin per entry of *tracks*, each that many bytes."""
    directory.mkdir(parents=True, exist_ok=True)
    names = [f"{stem} (Track {i}).bin" for i in range(1, len(tracks) + 1)]
    (directory / f"{stem}.cue").write_text(
        "".join(f'FILE "{n}" BINARY\n' for n in names))
    for name, size in zip(names, tracks):
        (directory / name).write_bytes(b"x" * size)


@pytest.mark.asyncio
async def test_the_tracks_of_each_sheet_are_added_up(db, tmp_path):
    _disc(tmp_path, "Game (Disc 1)", [1000, 500])
    _disc(tmp_path, "Game (Disc 2)", [700])
    await _import(db, tmp_path)

    got = await rom_handler.track_bytes(
        1, str(tmp_path), ["Game (Disc 1).cue", "Game (Disc 2).cue"], session=db)

    assert got == {"Game (Disc 1).cue": 1500, "Game (Disc 2).cue": 700}


@pytest.mark.asyncio
async def test_a_track_that_is_gone_weighs_nothing(db, tmp_path):
    """The download leaves out a file that is not there, so the size does too."""
    _disc(tmp_path, "Game", [1000, 500])
    await _import(db, tmp_path)
    await db.execute(update(Rom).where(Rom.fs_name == "Game (Track 2).bin")
                     .values(missing_from_fs=True))
    await db.commit()

    got = await rom_handler.track_bytes(1, str(tmp_path), ["Game.cue"], session=db)

    assert got == {"Game.cue": 1000}


@pytest.mark.asyncio
async def test_a_namesake_in_another_folder_is_not_counted(db, tmp_path):
    """A sheet names the files beside it, and nothing further away."""
    _disc(tmp_path / "EU", "Game", [1000])
    _disc(tmp_path / "US", "Game", [9999])
    await _import(db, tmp_path / "EU")
    await _import(db, tmp_path / "US")

    got = await rom_handler.track_bytes(1, str(tmp_path / "EU"), ["Game.cue"], session=db)

    assert got == {"Game.cue": 1000}


@pytest.fixture
def weights(db, monkeypatch):
    from endpoints.roms import roms_router as R

    monkeypatch.setattr(R.rom_handler, "track_bytes",
                        partial(rom_handler.track_bytes, session=db))
    return R._track_weights


@pytest.mark.asyncio
async def test_the_page_weighs_each_disc_with_its_tracks(db, tmp_path, weights):
    _disc(tmp_path, "Game (Disc 1)", [1000, 500])
    _disc(tmp_path, "Game (Disc 2)", [700])
    await _import(db, tmp_path)
    discs = [await _row(db, tmp_path, "Game (Disc 1).cue"),
             await _row(db, tmp_path, "Game (Disc 2).cue")]

    got = await weights(1, discs)

    assert got == {(str(tmp_path), "Game (Disc 1).cue"): 1500,
                   (str(tmp_path), "Game (Disc 2).cue"): 700}


@pytest.mark.asyncio
async def test_a_game_that_is_one_file_costs_no_query(weights, monkeypatch):
    """Most games are one file, and the page is opened far more often than a
    disc is ripped: nothing but a sheet has tracks to ask about."""
    from endpoints.roms import roms_router as R

    async def refuse(*_a, **_k):
        raise AssertionError("zapytanie o sciezki dla gry bez arkusza")

    monkeypatch.setattr(R.rom_handler, "track_bytes", refuse)
    chd = SimpleNamespace(fs_path="/l/psx/FF9", fs_name="FF9 (Disc 1).chd")

    assert await weights(1, [chd]) == {}


def test_the_page_puts_the_tracks_on_the_discs_and_the_game():
    """The themes add tracks_bytes to a game on one disc
    (test_every_theme_offers_the_extras.py)."""
    import pathlib

    source = (pathlib.Path(__file__).resolve().parent.parent / "endpoints" / "roms"
              / "roms_router.py").read_text(encoding="utf-8")
    page = source[source.index("async def get_rom("):]
    page = page[:page.index("\n@")]
    assert "_track_weights(" in page, "strona gry nie liczy sciezek plyty"
    assert '"tracks_bytes"' in page, "gra z jednej plyty nie dostaje wagi sciezek"
