"""When a game's title changes, its folder follows.

The folder is named after the title, so a title that changes and a folder that
does not means the shelf reads one way and the disk another. The owner asked
for the files to move.

What moves is the whole game, never one file of it. A title split across four
discs is four files, plus the track files of any disc kept as a sheet, plus the
subchannel data a PAL disc needs to boot, plus the playlist the emulator
switches discs with - and every one of those is only found because it sits
beside the others. A move that took the discs and left the .sbi behind would
leave a game that starts and hangs on a black screen.

A game that already has a folder moves by renaming it, which is one operation
the filesystem either does or does not do: nothing can be left half moved, and
whatever else is in there - mods, extras, the discs a conversion put aside -
goes along because it is the game's. A game still lying flat on the shelf is
moved file by file into a new folder, because the shelf holds other people's
games too, and anything already moved goes back if one of them fails.

Two things stop a move. A folder of that name already belonging to another game
- the owner chose to keep the current name rather than invent "(2)" - and a
transfer in progress, which a .part file in the directory says plainly enough.
"""
from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from handler.database.rom_handler import rom_handler
from handler.roms.game_folder import follow_title, files_of_the_game
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


def _row(db, rom_id: int, directory, fs_name: str, name: str | None = None, **extra):
    stem, _, ext = fs_name.rpartition(".")
    db.add(Rom(id=rom_id, platform_id=1, name=name or stem, fs_name=fs_name,
               fs_name_no_ext=stem, fs_extension=ext, fs_path=str(directory),
               fs_size_bytes=4, **extra))


def _write(directory, *names):
    directory.mkdir(parents=True, exist_ok=True)
    for name in names:
        (directory / name).write_bytes(b"data")


def _playlist(directory, name: str, *discs: str):
    """A real playlist: it is recognised by what it names, not by its name."""
    directory.mkdir(parents=True, exist_ok=True)
    (directory / name).write_text("\n".join(discs) + "\n", encoding="utf-8")


async def _at(db, rom_id: int):
    return (await db.execute(select(Rom).where(Rom.id == rom_id))).scalars().first()


# ── Which files are this game's ─────────────────────────────────────────────


def test_the_discs_their_tracks_their_subchannel_and_the_playlist(tmp_path):
    _write(tmp_path,
           "Game (Disc 1).cue", "Game (Disc 1).bin", "Game (Disc 1).sbi",
           "Game (Disc 2).cue", "Game (Disc 2).bin",
           "Somebody Else.chd", "Somebody Else.sbi")
    _playlist(tmp_path, "Game.m3u", "Game (Disc 1).cue", "Game (Disc 2).cue")
    members = [type("R", (), {"fs_name": n})()
               for n in ("Game (Disc 1).cue", "Game (Disc 2).cue",
                         "Game (Disc 1).bin", "Game (Disc 2).bin")]

    found = {p.name for p in files_of_the_game(tmp_path, members)}

    assert "Game (Disc 1).sbi" in found, (
        "dane podkanalowe zostalyby - plyta PAL wstaje i wiesza sie na czarnym ekranie"
    )
    assert "Game.m3u" in found, "playlista zostalaby, a z nia przelaczanie plyt"
    assert "Somebody Else.chd" not in found and "Somebody Else.sbi" not in found, (
        "przeniesienie zabralo pliki innej gry"
    )


# ── A game that already has a folder ────────────────────────────────────────


@pytest.mark.asyncio
async def test_its_folder_is_renamed_with_everything_in_it(db, tmp_path):
    game = tmp_path / "psx" / "ff9-eu"
    _write(game, "ff9-eu-d1.chd")
    _write(game / "mods", "widescreen.zip")
    _row(db, 1, game, "ff9-eu-d1.chd", name="Final Fantasy 9")
    await db.commit()

    moved = await follow_title(1, roms_base=str(tmp_path), session=db)

    assert moved == str(tmp_path / "psx" / "Final Fantasy 9")
    assert (tmp_path / "psx" / "Final Fantasy 9" / "ff9-eu-d1.chd").is_file()
    assert (tmp_path / "psx" / "Final Fantasy 9" / "mods" / "widescreen.zip").is_file(), (
        "mody nie pojechaly z gra"
    )
    assert not game.exists()
    assert (await _at(db, 1)).fs_path == str(tmp_path / "psx" / "Final Fantasy 9")


@pytest.mark.asyncio
async def test_the_rom_keeps_its_id_so_the_saves_stay(db, tmp_path):
    game = tmp_path / "psx" / "old"
    _write(game, "rom.chd")
    _row(db, 42, game, "rom.chd", name="A Better Name")
    await db.commit()

    await follow_title(42, roms_base=str(tmp_path), session=db)

    assert (await _at(db, 42)) is not None


# ── A game still lying flat on the shelf ────────────────────────────────────


@pytest.mark.asyncio
async def test_a_flat_game_moves_into_a_folder_with_its_whole_set(db, tmp_path):
    shelf = tmp_path / "psx"
    _write(shelf,
           "FF9 (Disc 1).chd", "FF9 (Disc 2).chd", "FF9 (Disc 1).sbi", "Crash.chd")
    _playlist(shelf, "FF9.m3u", "FF9 (Disc 1).chd", "FF9 (Disc 2).chd")
    _row(db, 1, shelf, "FF9 (Disc 1).chd", name="Final Fantasy 9",
         disk_group="ff9", disk_number=1)
    _row(db, 2, shelf, "FF9 (Disc 2).chd", name="Final Fantasy 9",
         disk_group="ff9", disk_number=2, extra_disk=True)
    _row(db, 9, shelf, "Crash.chd", name="Crash Bandicoot")
    await db.commit()

    await follow_title(1, roms_base=str(tmp_path), session=db)

    folder = shelf / "Final Fantasy 9"
    assert {p.name for p in folder.iterdir()} == {
        "FF9 (Disc 1).chd", "FF9 (Disc 2).chd", "FF9 (Disc 1).sbi", "FF9.m3u"}
    assert (shelf / "Crash.chd").is_file(), "cudza gra ruszyla sie z polki"
    assert (await _at(db, 2)).fs_path == str(folder), (
        "druga plyta zostala na polce, wiec zestaw rozpadl sie na dwie gry"
    )


@pytest.mark.asyncio
async def test_a_flat_games_manual_follows_it_into_the_new_folder(db, tmp_path):
    """On a shared shelf the manual carries the game's name in the shared
    extras/. Moved into a folder of its own, it becomes that folder's plain
    Manual.pdf - or the row would point at a file left behind."""
    shelf = tmp_path / "psx"
    _write(shelf, "crash.chd")
    _write(shelf / "extras", "Crash Bandicoot - Manual.pdf")
    _row(db, 1, shelf, "crash.chd", name="Crash Bandicoot",
         manual_path="extras/Crash Bandicoot - Manual.pdf")
    await db.commit()

    await follow_title(1, roms_base=str(tmp_path), session=db)

    folder = shelf / "Crash Bandicoot"
    assert (folder / "extras" / "Manual.pdf").is_file(), "instrukcja zostala na polce"
    assert (await _at(db, 1)).manual_path == "extras/Manual.pdf"


@pytest.mark.asyncio
async def test_a_foldered_games_manual_simply_goes_with_the_folder(db, tmp_path):
    """Renaming the folder takes extras/ along, and the row keeps the path
    relative to the game, so nothing needs rewriting."""
    game = tmp_path / "psx" / "ff9-eu"
    _write(game, "ff9.chd")
    _write(game / "extras", "Manual.pdf")
    _row(db, 1, game, "ff9.chd", name="Final Fantasy 9", manual_path="extras/Manual.pdf")
    await db.commit()

    await follow_title(1, roms_base=str(tmp_path), session=db)

    assert (tmp_path / "psx" / "Final Fantasy 9" / "extras" / "Manual.pdf").is_file()
    assert (await _at(db, 1)).manual_path == "extras/Manual.pdf"


# ── roms/ is a shelf, not a game ────────────────────────────────────────────
#
# `{platform}/roms/` is the other shape a library has on disk, RomM's, and the
# scan reads it the way it reads the platform folder: a shelf shared by every
# game in it, with game folders one level down. It sits one level under the
# platform, which is exactly where a game's own folder sits - so a rule that
# asked only "is it one level down" renamed the whole of roms/, every other
# game inside, after the one game whose title changed.


@pytest.mark.asyncio
async def test_the_shared_roms_folder_is_never_renamed_after_one_game(db, tmp_path):
    shared = tmp_path / "psx" / "roms"
    _write(shared, "ff9-eu-d1.chd", "Crash.chd")
    _row(db, 1, shared, "ff9-eu-d1.chd", name="Final Fantasy 9")
    _row(db, 9, shared, "Crash.chd", name="Crash Bandicoot")
    await db.commit()

    moved = await follow_title(1, roms_base=str(tmp_path), session=db)

    assert (shared / "Crash.chd").is_file(), "cala polka roms/ przemianowana po jednej grze"
    assert moved == str(shared / "Final Fantasy 9")
    assert (shared / "Final Fantasy 9" / "ff9-eu-d1.chd").is_file()
    assert (await _at(db, 9)).fs_path == str(shared)


@pytest.mark.asyncio
async def test_a_game_folder_inside_roms_follows_its_title_there(db, tmp_path):
    game = tmp_path / "psx" / "roms" / "ff9-eu"
    _write(game, "ff9-eu-d1.chd")
    _row(db, 1, game, "ff9-eu-d1.chd", name="Final Fantasy 9")
    await db.commit()

    moved = await follow_title(1, roms_base=str(tmp_path), session=db)

    assert moved == str(tmp_path / "psx" / "roms" / "Final Fantasy 9"), (
        "gra z roms/ wyjechala poza swoj uklad albo nie ruszyla sie wcale"
    )
    assert (await _at(db, 1)).fs_path == moved


# ── When it must not move ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_a_name_another_game_already_uses_leaves_it_where_it_is(db, tmp_path):
    shelf = tmp_path / "psx"
    _write(shelf / "Final Fantasy 9", "somebody-elses.chd")
    game = shelf / "ff9-eu"
    _write(game, "ff9.chd")
    _row(db, 1, game, "ff9.chd", name="Final Fantasy 9")
    await db.commit()

    assert await follow_title(1, roms_base=str(tmp_path), session=db) is None
    assert (game / "ff9.chd").is_file()
    assert (await _at(db, 1)).fs_path == str(game)


@pytest.mark.asyncio
async def test_a_transfer_in_progress_is_left_alone(db, tmp_path):
    game = tmp_path / "psx" / "old"
    _write(game, "rom.chd", "another.chd.part")
    _row(db, 1, game, "rom.chd", name="New Name")
    await db.commit()

    assert await follow_title(1, roms_base=str(tmp_path), session=db) is None
    assert (game / "rom.chd").is_file()


@pytest.mark.asyncio
@pytest.mark.parametrize("inside", ["extras", "mods"])
async def test_a_file_being_added_beside_the_game_keeps_the_folder_in_place(db, tmp_path, inside):
    """"Add file" writes its .part into extras/ or mods/. Renamed under it, the
    upload failed with a 500 and left a full-size .part nobody would ever see
    (1.0.36 audit)."""
    game = tmp_path / "psx" / "old"
    _write(game, "rom.chd")
    _write(game / inside, "big.zip.part")
    _row(db, 1, game, "rom.chd", name="New Name")
    await db.commit()

    assert await follow_title(1, roms_base=str(tmp_path), session=db) is None
    assert (game / inside / "big.zip.part").is_file()


@pytest.mark.asyncio
async def test_a_conversion_in_progress_keeps_the_folder_in_place(db, tmp_path, monkeypatch):
    """A CHD conversion writes nothing into the folder until its last copy, so
    no .part says it is running - the job does. Moved under it, the discs after
    the first failed with the first already converted (1.0.36 audit)."""
    from handler.roms import chd_jobs

    game = tmp_path / "psx" / "old"
    _write(game, "rom.cue")
    _row(db, 1, game, "rom.cue", name="New Name")
    await db.commit()
    monkeypatch.setitem(chd_jobs._jobs, 991, chd_jobs._ChdJob(
        id=991, rom_id=1, title="x", total_discs=1, status="converting"))

    assert await follow_title(1, roms_base=str(tmp_path), session=db) is None
    assert (game / "rom.cue").is_file()

    chd_jobs._jobs[991].status = "completed"
    assert await follow_title(1, roms_base=str(tmp_path), session=db) is not None, (
        "skonczona konwersja nadal trzyma folder"
    )


# ── A folder other games live in too (1.0.36 audit) ─────────────────────────
#
# From 1.0.36 the scan reads one level below the platform, so a folder a library
# already had - snes/Hacks/, a Zelda/ holding three regions - holds several
# games. Renamed after the one whose title a scrape found, the others were left
# naming a folder that no longer existed, and a scrape of the whole platform
# does exactly that to every such folder at once.


@pytest.mark.asyncio
async def test_a_folder_other_games_live_in_is_not_renamed_after_one_of_them(db, tmp_path):
    hacks = tmp_path / "psx" / "Hacks"
    _write(hacks, "hack-a.chd", "hack-b.chd")
    _row(db, 1, hacks, "hack-a.chd", name="Super Hack")
    _row(db, 2, hacks, "hack-b.chd", name="Another Hack")
    await db.commit()

    assert await follow_title(1, roms_base=str(tmp_path), session=db) is None
    assert (hacks / "hack-a.chd").is_file() and (hacks / "hack-b.chd").is_file()
    assert (await _at(db, 2)).fs_path == str(hacks)


@pytest.mark.asyncio
async def test_a_game_gone_missing_from_the_folder_still_lives_there(db, tmp_path):
    """Its saves are on that row, waiting for the file to come back."""
    hacks = tmp_path / "psx" / "Hacks"
    _write(hacks, "hack-a.chd")
    _row(db, 1, hacks, "hack-a.chd", name="Super Hack")
    _row(db, 2, hacks, "hack-b.chd", name="Another Hack", missing_from_fs=True)
    await db.commit()

    assert await follow_title(1, roms_base=str(tmp_path), session=db) is None
    assert (hacks / "hack-a.chd").is_file()


# ── What else a loose game takes into its folder (1.0.36 audit) ─────────────


@pytest.mark.asyncio
async def test_a_loose_sheet_takes_the_tracks_it_names_that_never_became_rows(db, tmp_path):
    """.ogg, .wav and .raw are not ROM extensions, so the scan makes no row for
    a track kept in one - and a move by rows left it on the shelf, with a sheet
    in the new folder naming a file that is not beside it."""
    shelf = tmp_path / "psx"
    _write(shelf, "Sonic CD (Track 01).bin", "Sonic CD (Track 02).ogg", "Crash.chd")
    (shelf / "Sonic CD.cue").write_text(
        'FILE "Sonic CD (Track 01).bin" BINARY\n  TRACK 01 MODE1/2352\n'
        'FILE "Sonic CD (Track 02).ogg" OGG\n  TRACK 02 AUDIO\n', encoding="utf-8")
    _row(db, 1, shelf, "Sonic CD.cue", name="Sonic CD")
    _row(db, 2, shelf, "Sonic CD (Track 01).bin", track_of="Sonic CD.cue")
    _row(db, 9, shelf, "Crash.chd", name="Crash Bandicoot")
    await db.commit()

    assert await follow_title(1, roms_base=str(tmp_path), session=db) is not None

    folder = shelf / "Sonic CD"
    assert {p.name for p in folder.iterdir()} == {
        "Sonic CD.cue", "Sonic CD (Track 01).bin", "Sonic CD (Track 02).ogg"}, (
        "sciezka audio zostala na polce, gra nie wstanie"
    )
    assert (shelf / "Crash.chd").is_file()


@pytest.mark.asyncio
async def test_a_loose_games_patch_and_save_go_with_it(db, tmp_path):
    """A soft patch and a save beside the ROM under its name are how RetroArch
    and a handheld over SMB find them."""
    shelf = tmp_path / "psx"
    _write(shelf, "Zelda.chd", "Zelda.ips", "Zelda.srm", "Mario.chd", "Mario.srm")
    _row(db, 1, shelf, "Zelda.chd", name="The Legend of Zelda")
    _row(db, 9, shelf, "Mario.chd", name="Mario")
    await db.commit()

    await follow_title(1, roms_base=str(tmp_path), session=db)

    folder = shelf / "The Legend of Zelda"
    assert {p.name for p in folder.iterdir()} == {"Zelda.chd", "Zelda.ips", "Zelda.srm"}
    assert (shelf / "Mario.srm").is_file() and (shelf / "Mario.chd").is_file()


@pytest.mark.asyncio
async def test_a_name_two_games_share_keeps_its_companions_on_the_shelf(db, tmp_path):
    """Game.chd and Game.zip are two entries; whose Game.srm is, nobody can say."""
    shelf = tmp_path / "psx"
    _write(shelf, "Game.chd", "Game.zip", "Game.srm")
    _row(db, 1, shelf, "Game.chd", name="Game One")
    _row(db, 2, shelf, "Game.zip", name="Game Two")
    await db.commit()

    await follow_title(1, roms_base=str(tmp_path), session=db)

    assert (shelf / "Game One" / "Game.chd").is_file()
    assert (shelf / "Game.srm").is_file() and (shelf / "Game.zip").is_file()


@pytest.mark.asyncio
async def test_a_companion_another_sheet_names_stays_on_the_shelf(db, tmp_path):
    """Round 2 of the audit: a file under the game's name that another sheet
    names is that sheet's track, not this game's companion."""
    shelf = tmp_path / "psx"
    _write(shelf, "Rayman.chd", "Rayman.ogg")
    (shelf / "Other.cue").write_text('FILE "Rayman.ogg" WAVE\n  TRACK 01 AUDIO\n', encoding="utf-8")
    _row(db, 1, shelf, "Rayman.chd", name="Rayman")
    _row(db, 9, shelf, "Other.cue", name="Other")
    await db.commit()

    await follow_title(1, roms_base=str(tmp_path), session=db)

    assert (shelf / "Rayman" / "Rayman.chd").is_file()
    assert (shelf / "Rayman.ogg").is_file(), "sciezka innego arkusza pojechala z gra"


@pytest.mark.asyncio
async def test_a_rom_nobody_has_scanned_yet_is_not_a_companion(db, tmp_path):
    """Sonic.zip dropped over FTP beside Sonic.md is a game of its own the next
    scan will find, not something of Sonic.md's."""
    shelf = tmp_path / "psx"
    _write(shelf, "Sonic.chd", "Sonic.zip", "Sonic.srm")
    _row(db, 1, shelf, "Sonic.chd", name="Sonic the Hedgehog")
    await db.commit()

    await follow_title(1, roms_base=str(tmp_path), session=db)

    assert (shelf / "Sonic the Hedgehog" / "Sonic.srm").is_file()
    assert (shelf / "Sonic.zip").is_file(), "niezeskanowany ROM pojechal jako dodatek"


@pytest.mark.asyncio
async def test_the_game_that_stays_in_a_folder_is_a_game_and_present_if_it_can_be(db, tmp_path):
    """Round 2 of the audit: the lowest id in a folder is usually a track row,
    and added files handed to a track row are lost when that track goes (a CHD
    conversion takes track rows away) - with nothing to list or remove them by."""
    folder = tmp_path / "psx" / "Sonic CD"
    _row(db, 1, folder, "Sonic CD (USA) (Track 01).bin", track_of="Sonic CD (USA).cue")
    _row(db, 2, folder, "Sonic CD (Japan).cue", missing_from_fs=True)
    _row(db, 3, folder, "Sonic CD (USA).cue")
    _row(db, 9, folder, "Sonic CD (Europe).cue")
    await db.commit()

    assert await rom_handler.another_in_folder(str(folder), [9], session=db) == 3


@pytest.mark.asyncio
async def test_a_track_another_sheet_still_names_keeps_the_game_on_the_shelf(db, tmp_path):
    """Two regional sheets naming one data file: moving it with one of them
    leaves the other naming a file that is gone."""
    shelf = tmp_path / "psx"
    _write(shelf, "Game.bin")
    for region in ("USA", "Europe"):
        (shelf / f"Game ({region}).cue").write_text(
            'FILE "Game.bin" BINARY\n  TRACK 01 MODE2/2352\n', encoding="utf-8")
    _row(db, 1, shelf, "Game (USA).cue", name="Game")
    _row(db, 2, shelf, "Game (Europe).cue", name="Game EU")
    _row(db, 3, shelf, "Game.bin", track_of="Game (USA).cue")
    await db.commit()

    assert await follow_title(1, roms_base=str(tmp_path), session=db) is None
    assert (shelf / "Game.bin").is_file() and (shelf / "Game (USA).cue").is_file()


@pytest.mark.asyncio
async def test_a_title_that_names_the_same_folder_moves_nothing(db, tmp_path):
    game = tmp_path / "psx" / "Final Fantasy 9"
    _write(game, "ff9.chd")
    _row(db, 1, game, "ff9.chd", name="Final Fantasy 9")
    await db.commit()

    assert await follow_title(1, roms_base=str(tmp_path), session=db) is None
    assert (game / "ff9.chd").is_file()


# ── And somebody actually asks ──────────────────────────────────────────────


def _asks_after_a_title_change(path) -> bool:
    import io
    source = io.open(path, encoding="utf-8").read()
    at = source.index("update_metadata(rom_id, data)")
    return "follow_title(" in source[at:at + 600]


def test_the_editor_asks_the_folder_to_follow():
    """A rule nobody calls is a folder that keeps the old name for ever."""
    import pathlib
    router = (pathlib.Path(__file__).resolve().parent.parent
              / "endpoints" / "roms" / "roms_router.py")
    assert _asks_after_a_title_change(router), (
        "zmiana tytulu w edytorze nie rusza folderu"
    )


@pytest.mark.asyncio
async def test_saving_a_scrape_with_a_title_moves_the_folder(monkeypatch):
    from handler.metadata import rom_scrape_handler as h
    from handler.roms import game_folder

    saved, followed = [], []

    async def _update(rom_id, data):
        saved.append((rom_id, dict(data)))

    async def _follow(rom_id, **_k):
        followed.append(rom_id)

    monkeypatch.setattr(h.rom_handler, "update_metadata", _update)
    monkeypatch.setattr(game_folder, "follow_title", _follow)

    await h.save_scrape(7, {"name": "Final Fantasy IX", "summary": "x"})
    await h.save_scrape(8, {"summary": "no title in this one"})

    assert [r for r, _ in saved] == [7, 8]
    assert followed == [7], "folder nie poszedl za tytulem, albo ruszyl sie bez tytulu"


def test_every_road_a_scrape_comes_in_by_saves_through_one_place():
    """Found on 2026-09-18: the batch followed the title, and the Scrape button
    on one game and the scrape after a download wrote the row themselves - so
    the ordinary case, a downloaded `ff9-eu-d1.chd` scraped a moment later,
    left the folder named after the file. Every call that runs a scrape is
    followed by save_scrape, including any added later."""
    import pathlib
    import re
    backend = pathlib.Path(__file__).resolve().parent.parent
    offenders, found = [], 0
    for path in backend.rglob("*.py"):
        if "tests" in path.parts:
            continue
        source = path.read_text(encoding="utf-8")
        for m in re.finditer(r"await\s+(?:_scrape|scrape_rom)\(", source):
            found += 1
            if "save_scrape(" not in source[m.end():m.end() + 500]:
                offenders.append(f"{path.relative_to(backend)}:{source.count(chr(10), 0, m.start()) + 1}")
    assert found >= 3, "nie znalazlem drog, ktorymi przychodzi scrape - test szuka zle"
    assert not offenders, "scrape zapisany z pominieciem save_scrape: " + ", ".join(offenders)


def test_a_scrape_asks_too():
    """The ordinary way a title appears at all: a file downloaded as
    `ff9-eu-d1.chd` is scraped a moment later and turns out to be a game."""
    import pathlib
    scrape = (pathlib.Path(__file__).resolve().parent.parent
              / "handler" / "metadata" / "rom_scrape_handler.py")
    assert _asks_after_a_title_change(scrape), (
        "po scrapie folder zostaje nazwany jak plik, a nie jak gra"
    )


@pytest.mark.asyncio
async def test_a_rom_outside_the_library_is_never_touched(db, tmp_path):
    outside = tmp_path / "somewhere-else"
    _write(outside, "rom.chd")
    _row(db, 1, outside, "rom.chd", name="New Name")
    await db.commit()

    assert await follow_title(1, roms_base=str(tmp_path / "psx-library"), session=db) is None
    assert (outside / "rom.chd").is_file()
