"""What one game's discs do must not reach the game in the folder beside it.

Three writes decide what a disc set is, and all three are issued across the
whole platform keyed on a bare file name:

  apply_disk_groups      UPDATE ... WHERE platform_id = ? AND fs_name = ?
  adopt_converted_file   DELETE ... WHERE platform_id = ? AND track_of = ?
  clear_container_hashes UPDATE ... WHERE platform_id = ? AND fs_name = ?

While every ROM of a platform sits in one directory that is exact, because one
directory cannot hold two files of a name. Per-game folders make `disc1.bin`
and `Disc 1.cue` the ordinary shape rather than a coincidence, and then each of
those three reaches into the folder next door: the grouping writes another
game's disc membership, the conversion DELETEs another game's track rows (and
their saves and play history cascade with them) while its files stay on the
disk with nothing pointing at them, and the hash clearing wipes digests off a
file nobody converted.

The tests use two folders under one platform, each holding a disc named the
same, and check that acting on one leaves the other exactly as it was.
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

HERE = "/roms/psx/Silent Hill"
NEXT_DOOR = "/roms/psx/Suikoden"


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


def _row(db, rom_id: int, directory: str, fs_name: str, **extra) -> None:
    stem, _, ext = fs_name.rpartition(".")
    db.add(Rom(
        id=rom_id, platform_id=1, name=stem,
        fs_name=fs_name, fs_name_no_ext=stem, fs_extension=ext,
        fs_path=directory, fs_size_bytes=1,
        **extra,
    ))


async def _two_games_one_disc_name(db) -> None:
    """Two games, each a sheet and its track, each in its own folder, and the
    files inside are named the same. This is what per-game folders look like."""
    _row(db, 1, HERE, "Disc 1.cue")
    _row(db, 2, HERE, "Disc 1.bin", track_of="Disc 1.cue")
    _row(db, 3, NEXT_DOOR, "Disc 1.cue")
    _row(db, 4, NEXT_DOOR, "Disc 1.bin", track_of="Disc 1.cue")
    await db.commit()


async def _get(db, rom_id: int) -> Rom | None:
    return (await db.execute(select(Rom).where(Rom.id == rom_id))).scalars().first()


@pytest.mark.asyncio
async def test_grouping_one_folder_leaves_the_other_ungrouped(db):
    await _two_games_one_disc_name(db)

    await rom_handler.apply_disk_groups(
        1, HERE, {"Disc 1.cue": ("Silent Hill", 1, False, None)}, session=db,
    )

    assert (await _get(db, 1)).disk_group == "Silent Hill"
    assert (await _get(db, 3)).disk_group is None, (
        "przypisanie plyt siegnelo do folderu obok"
    )


@pytest.mark.asyncio
async def test_grouping_clears_only_inside_the_folder_it_walked(db):
    """The other half of what this write is for: an entry with no set must have
    its fields cleared, and that clearing has the same reach."""
    await _two_games_one_disc_name(db)
    (await _get(db, 3)).disk_group = "Suikoden"
    (await _get(db, 3)).disk_number = 1
    await db.commit()

    await rom_handler.apply_disk_groups(
        1, HERE, {"Disc 1.cue": (None, None, False, None)}, session=db,
    )

    assert (await _get(db, 3)).disk_group == "Suikoden", (
        "czyszczenie przypisania zdjelo grupe gry z innego folderu"
    )


@pytest.mark.asyncio
async def test_a_conversion_takes_only_its_own_tracks(db):
    """Converting Silent Hill's sheet to a CHD ends its own track rows. The
    identically named track of the game next door is not part of that."""
    await _two_games_one_disc_name(db)

    await rom_handler.adopt_converted_file(1, "Disc 1.chd", 999, "abc", session=db)

    assert await _get(db, 2) is None, "wlasny slad plyty powinien zniknac"
    assert await _get(db, 4) is not None, (
        "konwersja skasowala sciezke plyty z folderu obok"
    )


async def _two_two_disc_games(db) -> None:
    """Two two-disc games, in their own folders, whose discs are named the same.
    The grouping key is worked out from the file names, so both sets carry it."""
    for rom_id, directory in ((1, HERE), (11, NEXT_DOOR)):
        for n in (1, 2):
            _row(db, rom_id + n, directory, f"Disc {n}.cue",
                 disk_group="Disc", disk_number=n, extra_disk=n != 1)
            _row(db, rom_id + n + 4, directory, f"Disc {n}.bin",
                 track_of=f"Disc {n}.cue", extra_disk=True)
    await db.commit()


@pytest.mark.asyncio
async def test_a_set_is_the_discs_in_one_folder(db):
    """Two discs and their two track files, not four discs and four tracks.
    Everything that acts on a ROM acts on this list: the download zips it, the
    delete removes it, the conversion reads a path off its first member."""
    await _two_two_disc_games(db)

    members = await rom_handler.disk_set(2, session=db)

    assert {r.fs_path for r in members} == {HERE}, (
        f"zestaw plyt siegnal do innego folderu: "
        f"{sorted((r.fs_path, r.fs_name) for r in members)}"
    )
    assert len(members) == 4


@pytest.mark.asyncio
async def test_a_track_belongs_to_the_sheet_beside_it(db):
    """Acting on a track means acting on its disc, and its disc is the one in
    its own folder. Resolved to the namesake next door, a download hands out
    another game's files and a delete removes them."""
    await _two_two_disc_games(db)

    members = await rom_handler.rom_with_tracks(16, session=db)

    assert {r.fs_path for r in members} == {NEXT_DOOR}, (
        "sciezka plyty rozwiazala sie na arkusz z innego folderu"
    )


@pytest.mark.asyncio
async def test_clearing_hashes_stops_at_the_file_it_was_asked_about(db):
    await _two_games_one_disc_name(db)
    for rom_id in (1, 3):
        row = await _get(db, rom_id)
        row.crc_hash, row.md5_hash, row.sha1_hash = "c", "m", "s"
    await db.commit()

    await rom_handler.clear_container_hashes(1, "Disc 1.cue", HERE, session=db)

    assert (await _get(db, 1)).crc_hash is None
    assert (await _get(db, 3)).crc_hash == "c", (
        "wyczyszczono sumy kontrolne pliku w innym folderze"
    )
