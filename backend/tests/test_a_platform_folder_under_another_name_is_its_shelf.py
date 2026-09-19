"""A platform folder under a name the scan knows is one of the platform's shelves.

The scan reads every directory under the ROM root and files it under the
platform its name stands for: `PlayStation/` is read as `psx`, `Super Nintendo/`
as `snes`, because those names are what a folder made by another program is
called. The rules that decide where a game's files go knew only the folder
names written in the platform map, so a game in `PlayStation/` was on the psx
platform to the scan and nowhere to them: its next disc went to `psx/` and split
the set, a download fetched it a second time, a loose game there took the whole
shelf for its own folder and offered every other game's extras as its own, and
a restart left its unfinished transfers on the disk (the owner's decision,
2026-09-19: the folders keep their names, the rules learn what the scan knows).
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from handler.metadata import rom_platform_map as m
from utils.game_folders import platform_dirs, shelves_of


@pytest.fixture
def library(tmp_path):
    for name in ("psx", "PlayStation", "PlayStation 2", "Sony PlayStation"):
        (tmp_path / name).mkdir()
    return tmp_path


def test_the_scan_reads_these_names_into_the_platform():
    """What the rest of this file rests on, asked of the scan's own rule."""
    assert m.canonical_fs_slug("PlayStation") == "psx"
    assert m.canonical_fs_slug("Super Nintendo") == "snes"
    assert m.canonical_fs_slug("PlayStation 2") != "psx"
    assert m.canonical_fs_slug("Sony PlayStation") != "psx"


def test_a_folder_the_scan_reads_into_the_platform_is_one_of_its_folders(library):
    dirs = platform_dirs(library / "psx")

    assert dirs[0] == library / "psx", "nowe pliki ida do wlasnego folderu platformy"
    assert library / "PlayStation" in dirs
    assert library / "PlayStation" / "roms" in shelves_of(library / "psx")


@pytest.mark.parametrize("platform, folder", [
    ("snes", "Super Nintendo"),
    ("n64", "Nintendo 64"),
])
def test_a_name_that_differs_by_more_than_letter_case_counts_too(tmp_path, platform, folder):
    """`PlayStation` and the map's `playstation` differ only in letter case,
    and a path compared without regard to case would pass without the rule."""
    (tmp_path / platform).mkdir()
    (tmp_path / folder).mkdir()

    assert tmp_path / folder in platform_dirs(tmp_path / platform)


def test_a_platform_of_its_own_counts_its_other_spelling(tmp_path):
    """The scan finds a platform by its folder's name first and by its URL slug
    next, so `my-hacks/` beside `My Hacks/` is read into the platform the first
    one made, although neither name is in the map."""
    for name in ("My Hacks", "my-hacks", "My Hacks 2"):
        (tmp_path / name).mkdir()

    dirs = platform_dirs(tmp_path / "My Hacks")

    assert dirs[0] == tmp_path / "My Hacks"
    assert tmp_path / "my-hacks" in dirs
    assert tmp_path / "My Hacks 2" not in dirs


def test_another_platforms_folder_is_not(library):
    dirs = platform_dirs(library / "psx")

    assert library / "PlayStation 2" not in dirs
    assert library / "Sony PlayStation" not in dirs


def test_a_file_of_that_name_is_not_a_folder(tmp_path):
    (tmp_path / "psx").mkdir()
    (tmp_path / "PlayStation").write_bytes(b"not a folder")

    assert tmp_path / "PlayStation" not in platform_dirs(tmp_path / "psx")


def test_a_folder_is_named_once(tmp_path):
    for name in ("genesis", "megadrive"):
        (tmp_path / name).mkdir()

    dirs = platform_dirs(tmp_path / "genesis")

    assert len(dirs) == len(set(dirs))


def test_a_library_without_such_a_folder_keeps_the_folders_it_had(tmp_path):
    (tmp_path / "psx").mkdir()
    (tmp_path / "n64").mkdir()

    assert platform_dirs(tmp_path / "psx") == tuple(
        tmp_path / name for name in m.platform_folders("psx"))


def test_a_root_that_cannot_be_read_keeps_the_folders_of_the_map(tmp_path):
    missing = tmp_path / "not-mounted" / "psx"

    assert platform_dirs(missing) == tuple(
        missing.parent / name for name in m.platform_folders("psx"))


# ── What the rules do with it ───────────────────────────────────────────────


def test_the_next_disc_joins_a_set_there(library):
    from handler.roms.game_folder import choose_home

    there = library / "PlayStation" / "Final Fantasy IX"
    got = choose_home("Final Fantasy IX (Disc 2).chd",
                      [("Final Fantasy IX (Disc 1).chd", str(there))], library / "psx")

    assert got == there, "druga plyta idzie do psx/ i dzieli zestaw na dwie gry"


def test_the_next_disc_joins_a_loose_set_there(library):
    from handler.roms.game_folder import choose_home

    got = choose_home("Final Fantasy IX (Disc 2).chd",
                      [("Final Fantasy IX (Disc 1).chd", str(library / "PlayStation"))],
                      library / "psx")

    assert got == library / "PlayStation"


@pytest.mark.asyncio
@pytest.mark.parametrize("where", ["", "roms"])
async def test_a_file_there_is_not_fetched_again(library, monkeypatch, where):
    from handler.roms import rom_source_handler as rsh

    async def nowhere_known(fs_slug, filename):
        return library / fs_slug / "Crash Bandicoot"

    monkeypatch.setattr(rsh, "_roms_base", lambda: str(library))
    monkeypatch.setattr(rsh, "_home_for", nowhere_known)
    folder = library / "PlayStation" / where
    folder.mkdir(exist_ok=True)
    (folder / "Crash Bandicoot.chd").write_bytes(b"disc")

    assert await rsh._already_here("psx", "Crash Bandicoot.chd") is True


@pytest.mark.asyncio
async def test_a_game_the_library_has_in_its_folder_there_is_not_fetched_again(library, monkeypatch):
    """Asked of the library: its row names the game's folder in PlayStation/."""
    from handler.roms import game_folder
    from handler.roms import rom_source_handler as rsh

    folder = library / "PlayStation" / "Crash Bandicoot"
    folder.mkdir()
    (folder / "Crash Bandicoot.chd").write_bytes(b"disc")

    async def rows(fs_slug, prefix, **_k):
        return [("Crash Bandicoot.chd", str(folder))]

    monkeypatch.setattr(rsh, "_roms_base", lambda: str(library))
    monkeypatch.setattr(game_folder.rom_handler, "files_starting_with", rows)

    assert await rsh._already_here("psx", "Crash Bandicoot.chd") is True


def test_the_download_queue_lists_the_root_off_the_event_loop():
    """Finding the shelves now reads the ROM root, which on a sleeping NAS
    takes as long as the disk needs to wake. The download queue asks it for
    every entry, so it asks from a worker thread, as it already did for the
    files themselves."""
    import inspect

    from handler.roms import game_folder
    from handler.roms import rom_source_handler as rsh

    here = inspect.getsource(rsh._already_here)
    assert "shelves_of(" in here[here.index("to_thread("):], (
        "polki liczone w petli zdarzen, nie w watku"
    )
    home = inspect.getsource(game_folder.existing_home)
    assert "to_thread(choose_home" in home, "choose_home listuje korzen w petli zdarzen"


def test_a_loose_game_there_has_no_folder_of_its_own(library):
    from handler.roms import game_extras

    shelf = library / "PlayStation"
    (shelf / "extras").mkdir()
    (shelf / "extras" / "Somebody Else - Manual.pdf").write_bytes(b"%PDF")
    rom = SimpleNamespace(id=1, fs_path=str(shelf), fs_name="crash.chd", manual_path=None,
                          name="Crash")

    assert game_extras._own_folder(rom, str(library), "psx") is None
    assert game_extras.extras_of(rom, library_root=str(library), fs_slug="psx") == [], (
        "luzna gra w PlayStation/ pokazuje extras wszystkich gier z polki jako swoje"
    )


def test_a_game_in_its_folder_there_keeps_it(library):
    from handler.roms import game_extras

    folder = library / "PlayStation" / "Crash Bandicoot"
    folder.mkdir()
    rom = SimpleNamespace(id=1, fs_path=str(folder), fs_name="crash.chd", manual_path=None,
                          name="Crash")

    assert game_extras._own_folder(rom, str(library), "psx") == folder


def test_a_loose_games_manual_there_is_named_after_the_game(library):
    from handler.metadata.manuals import manual_dest

    got = manual_dest(library / "PlayStation", library / "psx", "Crash Bandicoot", "crash.chd")

    assert got == library / "PlayStation" / "extras" / "Crash Bandicoot - Manual.pdf", (
        "kazda luzna gra w PlayStation/ zajelaby ten sam Manual.pdf"
    )


def test_an_upload_of_your_own_rom_there_is_written_where_it_is(library):
    from endpoints.roms.roms_router import _upload_dest_dir

    def _at(folder):
        return SimpleNamespace(fs_name="crash.chd", fs_path=str(folder))

    base = str(library)
    loose = library / "PlayStation"
    own = library / "PlayStation" / "Crash Bandicoot"
    assert _upload_dest_dir(base, "psx", "crash.chd", _at(loose), None) == loose
    assert _upload_dest_dir(base, "psx", "crash.chd", _at(own), None) == own


@pytest.mark.parametrize("folder", ["PlayStation", "playstation"])
def test_an_upload_of_a_file_lying_there_unscanned_is_written_over_it(tmp_path, folder):
    """The rule the platform's own folder has always had: a file on the disk
    with no row yet is still somebody's, and writing beside it leaves two
    copies where the next scan makes two games. `playstation/` is the map's
    own other name, `PlayStation/` a name only the scan knows."""
    from endpoints.roms.roms_router import _upload_dest_dir

    (tmp_path / "psx").mkdir()
    (tmp_path / folder).mkdir()
    (tmp_path / folder / "crash.chd").write_bytes(b"disc")

    assert _upload_dest_dir(str(tmp_path), "psx", "crash.chd", None, None) == tmp_path / folder


@pytest.mark.asyncio
async def test_a_game_there_follows_its_title_there(library):
    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import StaticPool

    from handler.roms.game_folder import follow_title
    from models.rom import Rom
    from models.rom_platform import RomPlatform

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(RomPlatform.__table__.create)
        await conn.run_sync(Rom.__table__.create)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    game = library / "PlayStation" / "crash-eu"
    game.mkdir()
    (game / "crash-eu.chd").write_bytes(b"x")
    async with maker() as db:
        db.add(RomPlatform(id=1, fs_slug="psx", slug=m.slug_from_fs_slug("psx"),
                           name="PlayStation"))
        db.add(Rom(id=1, platform_id=1, name="Crash Bandicoot", fs_name="crash-eu.chd",
                   fs_name_no_ext="crash-eu", fs_extension="chd", fs_path=str(game),
                   fs_size_bytes=1))
        await db.commit()

        moved = await follow_title(1, roms_base=str(library), session=db)
        row = (await db.execute(select(Rom).where(Rom.id == 1))).scalars().first()
    await engine.dispose()

    assert moved == str(library / "PlayStation" / "Crash Bandicoot"), (
        "gra w PlayStation/ nie idzie za tytulem"
    )
    assert row.fs_path == moved
    assert (library / "PlayStation" / "Crash Bandicoot" / "crash-eu.chd").is_file()


def test_a_restart_clears_unfinished_transfers_there(library, monkeypatch):
    import main
    from handler.roms import rom_source_handler

    monkeypatch.setattr(rom_source_handler, "_roms_base", lambda: str(library))
    left = [library / "PlayStation" / "Crash Bandicoot" / "crash.chd.part",
            library / "PlayStation" / "Crash Bandicoot" / "extras" / "map.png.part"]
    for path in left:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"half")

    main._sweep_rom_parts()

    assert not any(p.exists() for p in left), "polowki w PlayStation/ zostaly po restarcie"


def test_a_folder_of_no_platform_is_still_not_walked_deep(library, monkeypatch):
    """The round-2 rule stays: below the first level, only a platform's folders."""
    import main
    from handler.roms import rom_source_handler

    monkeypatch.setattr(rom_source_handler, "_roms_base", lambda: str(library))
    live = library / "downloads" / "torrents" / "Game" / "live.part"
    live.parent.mkdir(parents=True)
    live.write_bytes(b"half")

    main._sweep_rom_parts()

    assert live.is_file()
