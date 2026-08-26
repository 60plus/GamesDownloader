"""A disc that is more than one file, from the directory through to the download.

A PlayStation rip is a .cue naming a .bin, and a Dreamcast rip is a .gdi naming
several tracks. The library shows one game, which is right, and until now that
was the end of it: nothing recorded which data files the sheet stood for. So
downloading the game handed over two kilobytes of text naming files that were
not in the download, and deleting it removed the sheet and left the data on
disk with no entry left to reach it by.

These tests go the whole way on purpose - real files in a real directory, the
plan the scan makes of them, that plan written into a real database, and the
membership questions the download and delete routes ask of it. The previous
round of tests for this code built the middle of that chain by hand and missed
every defect in it.
"""
from __future__ import annotations

import io
import zipfile
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from endpoints.roms.roms_router import _member_files, _zip_chunks
from handler.database.rom_handler import rom_handler
from handler.filesystem.rom_scanner import plan_disk_assignments, scan_candidates
from handler.roms import rom_removal
from models.rom import Rom
from models.rom_platform import RomPlatform


@pytest_asyncio.fixture
async def db():
    """A real database, small enough to build per test.

    StaticPool because an in-memory sqlite lives inside one connection: without
    it the table would be created on a connection the queries never see again.
    """
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
    """What the scan does, minus the hashing: collect, decide, write."""
    files = scan_candidates(directory)
    for path in files:
        session.add(Rom(
            platform_id=1,
            fs_name=path.name,
            fs_name_no_ext=path.stem,
            fs_extension=path.suffix.lstrip("."),
            fs_path=str(directory),
            fs_size_bytes=path.stat().st_size,
        ))
    await session.commit()
    await rom_handler.apply_disk_groups(
        1, plan_disk_assignments(files), session=session
    )
    await session.commit()
    return {r.fs_name: r for r in (await session.execute(Rom.__table__.select())).all()}


async def _row(session, fs_name) -> Rom:
    from sqlalchemy import select
    found = await session.execute(select(Rom).where(Rom.fs_name == fs_name))
    return found.scalars().one()


def _write(directory, name, body=b"data"):
    path = directory / name
    path.write_text(body) if isinstance(body, str) else path.write_bytes(body)
    return path


def _single_disc(directory):
    _write(directory, "Game.cue", 'FILE "Game.bin" BINARY\n')
    _write(directory, "Game.bin", b"disc data" * 1000)


def _two_discs(directory):
    for disc in (1, 2):
        _write(directory, f"Game (Disc {disc}).cue",
               f'FILE "Game (Disc {disc}).bin" BINARY\n')
        _write(directory, f"Game (Disc {disc}).bin", f"data {disc}".encode())


# ── Which rows travel together ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_cue_and_its_bin_are_one_thing(db, tmp_path):
    _single_disc(tmp_path)
    await _import(db, tmp_path)
    cue = await _row(db, "Game.cue")

    names = [r.fs_name for r in await rom_handler.disk_set(cue.id, session=db)]
    assert names == ["Game.cue", "Game.bin"], "deleting the sheet must take the data"

    names = [r.fs_name for r in await rom_handler.rom_with_tracks(cue.id, session=db)]
    assert names == ["Game.cue", "Game.bin"], "downloading the disc must include the data"


@pytest.mark.asyncio
async def test_the_bin_is_hidden_but_knows_what_it_belongs_to(db, tmp_path):
    _single_disc(tmp_path)
    await _import(db, tmp_path)
    binary = await _row(db, "Game.bin")

    assert binary.extra_disk is True, "it must not show up as a second game"
    assert binary.track_of == "Game.cue"
    # Not a disk: nothing should ever offer it as something to boot.
    assert binary.disk_group is None and binary.disk_number is None


@pytest.mark.asyncio
async def test_a_track_id_answers_for_its_disc(db, tmp_path):
    """Nothing in the interface offers a track, but an id is an id, and a route
    reached with one should not delete half a disc."""
    _single_disc(tmp_path)
    await _import(db, tmp_path)
    binary = await _row(db, "Game.bin")

    names = [r.fs_name for r in await rom_handler.disk_set(binary.id, session=db)]
    assert names == ["Game.cue", "Game.bin"]


@pytest.mark.asyncio
async def test_asking_for_one_disc_does_not_hand_over_the_box(db, tmp_path):
    _two_discs(tmp_path)
    await _import(db, tmp_path)
    second = await _row(db, "Game (Disc 2).cue")

    one = [r.fs_name for r in await rom_handler.rom_with_tracks(second.id, session=db)]
    assert one == ["Game (Disc 2).cue", "Game (Disc 2).bin"]

    whole = [r.fs_name for r in await rom_handler.disk_set(second.id, session=db)]
    assert set(whole) == {
        "Game (Disc 1).cue", "Game (Disc 1).bin",
        "Game (Disc 2).cue", "Game (Disc 2).bin",
    }
    # Disks first and in order, so a caller listing them does not have to sort.
    assert whole[:2] == ["Game (Disc 1).cue", "Game (Disc 2).cue"]


@pytest.mark.asyncio
async def test_a_two_disc_game_offers_exactly_two_disks(db, tmp_path):
    """The disk selector reads this, and it used to be handed four entries with
    two of them numbered the same."""
    _two_discs(tmp_path)
    await _import(db, tmp_path)
    first = await _row(db, "Game (Disc 1).cue")

    disks = await rom_handler.get_disk_set(1, first.disk_group, session=db)
    assert [(d.fs_name, d.disk_number) for d in disks] == [
        ("Game (Disc 1).cue", 1), ("Game (Disc 2).cue", 2),
    ]


@pytest.mark.asyncio
async def test_a_cartridge_is_still_just_itself(db, tmp_path):
    _write(tmp_path, "Sonic.bin", b"mega drive")
    await _import(db, tmp_path)
    rom = await _row(db, "Sonic.bin")

    assert [r.fs_name for r in await rom_handler.disk_set(rom.id, session=db)] == ["Sonic.bin"]
    assert rom.extra_disk is False and rom.track_of is None


@pytest.mark.asyncio
async def test_a_rescan_lets_a_disc_stop_being_one(db, tmp_path):
    """The fields are rewritten every scan, which is what lets a title stop
    being a set when the rest of it is deleted."""
    _single_disc(tmp_path)
    await _import(db, tmp_path)
    assert (await _row(db, "Game.bin")).track_of == "Game.cue"

    (tmp_path / "Game.cue").unlink()
    await rom_handler.apply_disk_groups(
        1, plan_disk_assignments(scan_candidates(tmp_path)), session=db
    )
    await db.commit()
    binary = await _row(db, "Game.bin")
    assert binary.track_of is None and binary.extra_disk is False


# ── Which link the interface is handed ────────────────────────────────────────


def _ticket_request():
    from handler.auth.scopes import Scope

    return SimpleNamespace(state=SimpleNamespace(
        user=SimpleNamespace(id=7), scopes={Scope.ROMS_READ},
    ))


@pytest_asyncio.fixture
def routed(db, monkeypatch):
    """The ticket route talking to this test's database.

    Only the session plumbing is stood in for; the membership questions the
    route asks are answered by the real queries, tested above.
    """
    for name in ("disk_set", "rom_with_tracks", "get_by_id"):
        original = getattr(rom_handler, name)
        monkeypatch.setattr(
            rom_handler, name,
            (lambda fn: lambda rom_id: fn(rom_id, session=db))(original),
        )


@pytest.mark.asyncio
async def test_the_link_for_a_disc_asks_for_the_whole_disc(db, tmp_path, routed):
    """Nothing in the interface knows a .cue needs its .bin, and it should not
    have to: asking for one disc means asking for the disc."""
    from endpoints.roms.roms_router import issue_download_ticket

    _single_disc(tmp_path)
    await _import(db, tmp_path)
    cue = await _row(db, "Game.cue")

    ticket = await issue_download_ticket(request=_ticket_request(), rom_id=cue.id)
    assert f"/api/roms/{cue.id}/download-files/" in ticket["url"]


@pytest.mark.asyncio
async def test_the_link_for_a_cartridge_is_still_the_plain_file(db, tmp_path, routed):
    """One file is one file. Wrapping it in a zip would be a worse download."""
    from endpoints.roms.roms_router import issue_download_ticket

    _write(tmp_path, "Sonic.bin", b"mega drive")
    await _import(db, tmp_path)
    rom = await _row(db, "Sonic.bin")

    ticket = await issue_download_ticket(request=_ticket_request(), rom_id=rom.id)
    assert f"/api/roms/{rom.id}/download/" in ticket["url"]


@pytest.mark.asyncio
async def test_the_whole_set_link_is_a_different_ticket_from_one_disc(db, tmp_path, routed):
    """They pack different things, so a ticket for one must not be presentable
    for the other."""
    from endpoints.roms.roms_router import issue_download_ticket

    _two_discs(tmp_path)
    await _import(db, tmp_path)
    first = await _row(db, "Game (Disc 1).cue")

    one = await issue_download_ticket(request=_ticket_request(), rom_id=first.id)
    whole = await issue_download_ticket(
        request=_ticket_request(), rom_id=first.id, whole_set=True
    )
    assert "/download-files/" in one["url"] and "/download-set/" in whole["url"]
    assert one["url"].rsplit("/", 1)[-1] != whole["url"].rsplit("/", 1)[-1]


# ── What the download actually contains ───────────────────────────────────────


def _rows(directory, *names):
    return [SimpleNamespace(fs_path=str(directory), fs_name=n) for n in names]


def test_a_download_of_a_disc_carries_the_data_the_sheet_names(tmp_path):
    _single_disc(tmp_path)
    files = _member_files(_rows(tmp_path, "Game.cue", "Game.bin"), str(tmp_path))
    assert [name for _p, name in files] == ["Game.cue", "Game.bin"]


def test_a_track_with_no_library_row_of_its_own_is_still_included(tmp_path):
    """The .raw of a Dreamcast rip. It is deliberately not an extension the
    scanner claims, so it has no row - and a disc missing it will not boot."""
    _write(tmp_path, "Game.gdi",
           "2\n1 0 4 2352 track01.bin 0\n2 756 0 2352 track02.raw 0\n")
    _write(tmp_path, "track01.bin")
    _write(tmp_path, "track02.raw", b"red book audio")

    files = _member_files(_rows(tmp_path, "Game.gdi", "track01.bin"), str(tmp_path))
    assert sorted(name for _p, name in files) == ["Game.gdi", "track01.bin", "track02.raw"]


def test_nothing_outside_the_rom_directory_is_ever_packed(tmp_path):
    """A stored path is data, and data that decides what gets read is not
    trusted just because it came out of our own database."""
    outside = tmp_path / "outside"
    outside.mkdir()
    _write(outside, "secret.bin", b"not yours")
    inside = tmp_path / "roms"
    inside.mkdir()
    _write(inside, "Game.bin")

    files = _member_files(
        _rows(inside, "Game.bin") + _rows(outside, "secret.bin"), str(inside)
    )
    assert [name for _p, name in files] == ["Game.bin"]


def test_the_archive_is_a_real_zip_that_unpacks_to_the_original_files(tmp_path):
    """Streamed rather than built in memory, so the size is not known when the
    headers go out. That means data descriptors, which is exactly the part
    worth checking against a reader rather than assuming."""
    _write(tmp_path, "Game.cue", 'FILE "Game.bin" BINARY\n')
    _write(tmp_path, "Game.bin", b"\x00\xff" * 100_000)

    files = _member_files(_rows(tmp_path, "Game.cue", "Game.bin"), str(tmp_path))
    packed = b"".join(_zip_chunks(files))

    with zipfile.ZipFile(io.BytesIO(packed)) as archive:
        assert archive.testzip() is None
        assert archive.namelist() == ["Game.cue", "Game.bin"]
        assert archive.read("Game.bin") == b"\x00\xff" * 100_000
        assert archive.read("Game.cue") == b'FILE "Game.bin" BINARY\n'
        # Stored, not deflated: a disc image does not compress and waiting for
        # it to try only delays the download.
        assert all(i.compress_type == zipfile.ZIP_STORED for i in archive.infolist())


def test_the_archive_is_produced_in_pieces_rather_than_all_at_once(tmp_path):
    """The point of the rewrite. A floppy set was a few megabytes; a disc is
    most of a gigabyte, and holding it in memory to hand it over is not on."""
    _write(tmp_path, "Game.bin", b"x" * (5 * 1024 * 1024))
    chunks = list(_zip_chunks(_member_files(_rows(tmp_path, "Game.bin"), str(tmp_path))))
    assert len(chunks) > 1, "one chunk means the whole file was buffered"
    assert max(len(c) for c in chunks) < 2 * 1024 * 1024


# ── The playlist that makes a multi-disc download switchable ──────────────────


def _members(*specs):
    """Rows as the membership queries return them: (fs_name, track_of)."""
    return [SimpleNamespace(fs_name=n, track_of=t) for n, t in specs]


def test_a_two_disc_title_gets_a_playlist_naming_both():
    """Without one the player reaches the end of disc one and has to go and
    find disc two by hand; with one the emulator offers the swap itself."""
    from endpoints.roms.roms_router import _playlist_for

    text = _playlist_for(_members(
        ("Game (Disc 1).cue", None), ("Game (Disc 2).cue", None),
    ))
    assert text == "Game (Disc 1).cue\nGame (Disc 2).cue\n"


def test_the_playlist_never_names_a_raw_track():
    """The one way to produce a playlist that looks right and is useless: a
    line pointing at a .bin hands the emulator a data file, not a game."""
    from endpoints.roms.roms_router import _playlist_for

    text = _playlist_for(_members(
        ("Game (Disc 1).cue", None), ("Game (Disc 1).bin", "Game (Disc 1).cue"),
        ("Game (Disc 2).cue", None), ("Game (Disc 2).bin", "Game (Disc 2).cue"),
    ))
    assert text == "Game (Disc 1).cue\nGame (Disc 2).cue\n"
    assert ".bin" not in text


def test_one_disc_gets_no_playlist_however_many_files_it_takes():
    """Nothing to switch between. A .m3u with a single line is clutter that
    some cores will happily boot instead of the disc."""
    from endpoints.roms.roms_router import _playlist_for

    assert _playlist_for(_members(("Game.cue", None), ("Game.bin", "Game.cue"))) == ""
    assert _playlist_for(_members(("Sonic.bin", None))) == ""
    assert _playlist_for([]) == ""


def test_floppies_get_one_too():
    """Not only discs: an Amiga title on several floppies swaps the same way."""
    from endpoints.roms.roms_router import _playlist_for

    text = _playlist_for(_members(
        ("Legion (Disk 1 of 2).adf", None), ("Legion (Disk 2 of 2).adf", None),
    ))
    assert text.splitlines() == ["Legion (Disk 1 of 2).adf", "Legion (Disk 2 of 2).adf"]


def test_the_archive_carries_the_playlist_beside_the_discs(tmp_path):
    """End to end through the real zip writer, because the playlist is written
    from memory rather than read off the disk and takes a different path."""
    from endpoints.roms.roms_router import _playlist_for, _zip_chunks

    for disc in (1, 2):
        _write(tmp_path, f"Game (Disc {disc}).cue", f'FILE "Game (Disc {disc}).bin" BINARY\n')
        _write(tmp_path, f"Game (Disc {disc}).bin", f"data {disc}".encode())

    rows = _members(
        ("Game (Disc 1).cue", None), ("Game (Disc 1).bin", "Game (Disc 1).cue"),
        ("Game (Disc 2).cue", None), ("Game (Disc 2).bin", "Game (Disc 2).cue"),
    )
    files = _member_files(_rows(tmp_path, *[r.fs_name for r in rows]), str(tmp_path))
    extra = [("Game.m3u", _playlist_for(rows).encode("utf-8"))]
    packed = b"".join(_zip_chunks(files, extra))

    with zipfile.ZipFile(io.BytesIO(packed)) as archive:
        assert archive.testzip() is None
        assert "Game.m3u" in archive.namelist()
        assert archive.read("Game.m3u").decode() == "Game (Disc 1).cue\nGame (Disc 2).cue\n"
        # And the discs themselves are all still in there.
        assert archive.read("Game (Disc 2).bin") == b"data 2"


# ── What deleting takes with it ───────────────────────────────────────────────


def test_deleting_a_disc_takes_the_files_that_have_no_row(tmp_path, monkeypatch):
    monkeypatch.setattr(rom_removal, "ROMS_PATH", str(tmp_path))
    _write(tmp_path, "Game.gdi",
           "2\n1 0 4 2352 track01.bin 0\n2 756 0 2352 track02.raw 0\n")
    _write(tmp_path, "track01.bin")
    _write(tmp_path, "track02.raw", b"red book audio")

    orphans = rom_removal.unrowed_tracks(_rows(tmp_path, "Game.gdi", "track01.bin"))
    assert [p.name for p in orphans] == ["track02.raw"]

    assert rom_removal.delete_paths(orphans) == 1
    assert not (tmp_path / "track02.raw").exists()
    # The rows' own files are left to the ordinary path, not deleted twice.
    assert (tmp_path / "track01.bin").exists()


def test_a_file_outside_the_rom_directory_is_not_unlinked(tmp_path, monkeypatch):
    roms = tmp_path / "roms"
    roms.mkdir()
    monkeypatch.setattr(rom_removal, "ROMS_PATH", str(roms))
    elsewhere = _write(tmp_path, "important.bin", b"keep me")

    assert rom_removal.delete_paths([elsewhere]) == 0
    assert elsewhere.exists()


# ── Two sheets, one data file ─────────────────────────────────────────────────
#
# Two rips of a game can sit in one directory naming the same data file: two
# regional versions of a .cue, or a .gdi kept beside a .cue. The scan hands the
# file to whichever sheet sorts first, which is a fine way to decide what the
# library shows and a ruinous way to decide what a delete may take. Whichever of
# the two was deleted, the file went - by different routes - and the survivor was
# left naming bytes that are not there.


def _shared_bin(directory):
    """A.cue and B.cue, both naming data.bin, and the file itself."""
    _write(directory, "A.cue", 'FILE "data.bin" BINARY\n')
    _write(directory, "B.cue", 'FILE "data.bin" BINARY\n')
    _write(directory, "data.bin", b"the only copy")


def test_the_scan_still_gives_the_file_to_one_sheet(tmp_path):
    """Not the thing being fixed, and worth pinning: the library shows one
    entry for the data file, and which sheet it hangs off is arbitrary. What
    changes is that deletion no longer takes that arbitrary answer as licence."""
    _shared_bin(tmp_path)
    plan = plan_disk_assignments(scan_candidates(tmp_path))
    assert plan["data.bin"][3] in ("A.cue", "B.cue")


def test_deleting_the_sheet_that_won_the_file_leaves_it_for_the_other(tmp_path, monkeypatch):
    """Route one: the file became a row of A's set, so the ordinary member loop
    deleted it along with A."""
    monkeypatch.setattr(rom_removal, "ROMS_PATH", str(tmp_path))
    _shared_bin(tmp_path)
    members = _rows(tmp_path, "A.cue", "data.bin")

    spoken_for = rom_removal.spoken_for_elsewhere(members)
    assert "data.bin" in spoken_for, "B.cue still names it"

    for member in members:
        rom_removal.delete_rom_file(member, spoken_for=spoken_for)

    assert not (tmp_path / "A.cue").exists()
    assert (tmp_path / "data.bin").exists(), "B.cue was left naming a file that is gone"


def test_deleting_the_sheet_that_lost_the_file_leaves_it_too(tmp_path, monkeypatch):
    """Route two, and the one that reads as harmless: B has no row for the file,
    so it looked like an orphan nothing would miss."""
    monkeypatch.setattr(rom_removal, "ROMS_PATH", str(tmp_path))
    _shared_bin(tmp_path)

    orphans = rom_removal.unrowed_tracks(_rows(tmp_path, "B.cue"))

    assert [p.name for p in orphans] == []
    assert rom_removal.delete_paths(orphans) == 0
    assert (tmp_path / "data.bin").exists()


def test_a_lone_sheet_still_takes_its_data_with_it(tmp_path, monkeypatch):
    """The guard must not turn the ordinary case into a leak: with nobody else
    naming the file, it is an orphan the moment the sheet goes."""
    monkeypatch.setattr(rom_removal, "ROMS_PATH", str(tmp_path))
    _write(tmp_path, "Only.cue", 'FILE "only.bin" BINARY\n')
    _write(tmp_path, "only.bin", b"nothing else points here")

    orphans = rom_removal.unrowed_tracks(_rows(tmp_path, "Only.cue"))

    assert [p.name for p in orphans] == ["only.bin"]
    assert rom_removal.delete_paths(orphans) == 1


def test_the_sheets_of_one_multi_disc_set_do_not_shield_each_other(tmp_path, monkeypatch):
    """Both sheets are going, so neither is "somebody else" - otherwise a
    two-disc game would leave all of its data behind."""
    monkeypatch.setattr(rom_removal, "ROMS_PATH", str(tmp_path))
    _two_discs(tmp_path)
    members = _rows(tmp_path, "Game (Disc 1).cue", "Game (Disc 1).bin",
                    "Game (Disc 2).cue", "Game (Disc 2).bin")

    assert rom_removal.spoken_for_elsewhere(members) == set()

    for member in members:
        rom_removal.delete_rom_file(member, spoken_for=set())
    assert list(tmp_path.iterdir()) == []
