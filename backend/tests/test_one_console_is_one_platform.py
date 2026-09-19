"""One console is one platform, whatever it was called where it was sold.

The owner's question (2026-09-18): why are Mega Drive and Genesis two tiles when
it is one console? Folder names that meant exactly the same thing had been one
platform for a while - `snes`, `snesna` and `super-nintendo` all read "Super
Nintendo" - but a console sold under another name in another region was a
platform of its own: Mega Drive and Genesis, Famicom and NES, Super Famicom and
SNES. A source that files Mega Drive games under `megadrive` then put "Gods"
beside "The Lost Vikings", in a second tile, for the same machine.

ScreenScraper, the main scraper, keeps each of these as ONE system with one id,
and so does the library now (the owner's decision, all eleven groups). The
groups are written out rather than worked out from the ids, because a shared
ScreenScraper id is not proof of one console: every arcade board shares one, the
Amiga models share one, and 3DO and the Jaguar share one by mistake.
"""
from __future__ import annotations

import re

import pytest

from handler.metadata import rom_platform_map as m

GROUPS = {
    "nes": {"famicom"},
    "snes": {"snesna", "super-nintendo", "sfc"},
    "genesis": {"megadrive", "megadrivejp", "sega-genesis", "sega-mega-drive"},
    "segacd": {"megacd", "megacdjp"},
    "sega32x": {"sega32xjp", "sega32xna"},
    "saturn": {"saturnjp", "sega-saturn"},
    "mastersystem": {"mark3"},
    "pcengine": {"tg16"},
    "pcenginecd": {"tg-cd"},
    "neogeocd": {"neogeocdjp"},
    "gc": {"nintendo-gamecube"},
}


def _own_slug(fs_slug: str) -> str:
    """What a platform's URL slug was before any of this: its own name."""
    return re.sub(r"[^\w]+", "-", m.PLATFORM_MAP[fs_slug]["name"].lower()).strip("-")


@pytest.mark.parametrize("main, others", sorted(GROUPS.items()))
def test_every_name_of_a_console_is_its_one_platform(main, others):
    for other in others:
        assert m.canonical_fs_slug(other) == main, f"{other} nie trafia do {main}"
        assert m.slug_from_fs_slug(other) == m.slug_from_fs_slug(main), (
            f"{other} dostaje wlasny kafel obok {main}"
        )


@pytest.mark.parametrize("main", sorted(GROUPS))
def test_the_main_name_keeps_the_platform_it_had(main):
    """Every existing library has a row for these under this slug, with games
    on it. Changing it would orphan the lot."""
    assert m.canonical_fs_slug(main) == main
    assert m.slug_from_fs_slug(main) == _own_slug(main)


def test_no_other_platform_changes():
    grouped = set(GROUPS) | {n for names in GROUPS.values() for n in names}
    changed = [s for s in m.PLATFORM_MAP
               if s not in grouped and m.slug_from_fs_slug(s) != _own_slug(s)]
    assert not changed, f"scalenie dotknelo innych platform: {changed}"


@pytest.mark.parametrize("main, others", sorted(GROUPS.items()))
def test_a_group_is_one_system_to_screenscraper(main, others):
    """The rule the groups follow. Not the rule that makes them - see above."""
    assert {m.PLATFORM_MAP[s]["ss_id"] for s in {main} | others} == {m.PLATFORM_MAP[main]["ss_id"]}


def test_a_console_lists_every_folder_it_may_be_in():
    folders = m.platform_folders("genesis")
    assert folders[0] == "genesis"
    assert set(folders) == {"genesis"} | GROUPS["genesis"]
    assert m.platform_folders("megadrive") == folders
    assert m.platform_folders("n64")[0] == "n64"
    assert m.platform_folders("not-a-platform") == ("not-a-platform",)


def test_igdb_is_asked_about_every_platform_it_keeps_for_the_console():
    """IGDB keeps the Famicom and the Super Famicom apart from the NES and the
    SNES, so a Japan-only game is filed under the Japanese machine there."""
    assert m.igdb_platform_ids("nes") == (18, 99)
    assert m.igdb_platform_ids("famicom") == (18, 99)
    assert m.igdb_platform_ids("snes") == (19, 58)
    assert m.igdb_platform_ids("genesis") == (29,)
    assert m.igdb_platform_ids("not-a-platform") == ()


@pytest.mark.asyncio
async def test_a_folder_of_another_name_is_read_into_the_platform(tmp_path, monkeypatch):
    """`upsert` finds a row by folder name first, and creates one under the
    name it was given when there is none - so a library whose first Mega Drive
    game sat in `megadrive/` got a platform row called megadrive, and every
    rule that reads a platform's folder read the wrong one from then on."""
    import types

    from handler.filesystem import rom_scanner as scanner

    (tmp_path / "roms" / "megadrive").mkdir(parents=True)
    (tmp_path / "roms" / "megadrive" / "Gods (USA).zip").write_bytes(b"x")
    asked = []

    async def _nothing(*a, **k):
        return None

    async def _upsert(fs_slug, slug, name, **_k):
        asked.append((fs_slug, slug, name))
        return types.SimpleNamespace(id=1, slug=slug, fs_slug=fs_slug, scan_exclude=None)

    async def _stop(*a, **k):
        raise RuntimeError("dosc - platforma juz wybrana")

    async def _empty(*a, **k):
        return {}

    async def _none(*a, **k):
        return []

    monkeypatch.setattr(scanner.rom_platform_handler, "get_all_simple", _none)
    monkeypatch.setattr(scanner.rom_platform_handler, "rom_counts_by_fs_slug", _empty)
    monkeypatch.setattr(scanner.rom_platform_handler, "upsert", _upsert)
    monkeypatch.setattr(scanner.rom_handler, "present_ids", _none)
    monkeypatch.setattr(scanner.rom_handler, "mark_all_missing", _nothing)
    monkeypatch.setattr(scanner.rom_handler, "restore_present", _nothing)
    monkeypatch.setattr(scanner.rom_handler, "get_by_fs_name", _stop)
    monkeypatch.setattr(scanner.rom_handler, "rows_named_in", _none)

    with pytest.raises(RuntimeError):
        await scanner.scan_roms_path(str(tmp_path / "roms"))

    assert asked == [("genesis", m.slug_from_fs_slug("genesis"),
                      m.PLATFORM_MAP["genesis"]["name"])], (
        f"folder megadrive/ zalozyl wlasna platforme: {asked}"
    )


@pytest.mark.parametrize("ids, expected", [
    ((18, 99), " & platforms = (18,99)"),
    ((29,), " & platforms = (29)"),
    (29, " & platforms = (29)"),
    ((), ""),
    (None, ""),
])
def test_igdb_can_be_asked_about_several_platforms_at_once(ids, expected):
    from handler.metadata.igdb_rom_handler import _platform_filter

    assert _platform_filter(ids) == expected


def test_the_rom_scrape_and_the_editor_ask_igdb_about_the_whole_console():
    import pathlib

    backend = pathlib.Path(__file__).resolve().parent.parent
    for relative in ("handler/metadata/rom_scrape_handler.py", "endpoints/roms/roms_router.py"):
        source = (backend / relative).read_text(encoding="utf-8")
        assert "igdb_platform_ids(" in source, f"{relative} pyta IGDB tylko o jedna platforme"
        assert "get_igdb_id(" not in source.replace("_get_igdb_id(", "get_igdb_id("), (
            f"{relative} dalej pyta o jeden numer IGDB"
        )


def test_a_download_filed_under_another_name_goes_to_the_platforms_folder(monkeypatch):
    """A source files Mega Drive games under `megadrive`. The download goes
    where the platform keeps new files, one folder per console."""
    from handler.roms import rom_source_handler as rsh

    monkeypatch.setattr(rsh, "assert_fetch_allowed", lambda *a, **k: None)

    class _Source:
        def rom_source_resolve_download(self, entry_id):
            return {"url": "https://archive.example/Gods.zip", "filename": "Gods (USA).zip",
                    "fs_slug": "megadrive"}

    assert rsh._resolve_entry(_Source(), "e1")["fs_slug"] == "genesis"


@pytest.mark.asyncio
async def test_an_import_filed_under_another_name_goes_there_too(monkeypatch, tmp_path):
    from handler.roms import rom_source_handler as rsh

    async def _home(fs_slug, filename):
        return tmp_path / fs_slug / "x"

    async def _no_transfer(job):
        return None

    monkeypatch.setattr(rsh, "assert_fetch_allowed", lambda *a, **k: None)
    monkeypatch.setattr(rsh, "_home_for", _home)
    monkeypatch.setattr(rsh, "_rom_download_job", _no_transfer)
    rsh._dest_locks.clear()
    try:
        out = await rsh.import_rom("https://archive.example/Gods.zip", "megadrive", "Gods (USA).zip")
    finally:
        rsh._jobs.clear()
        rsh._dest_locks.clear()

    assert out["fs_slug"] == "genesis"


# ── A game lying in a folder of the console's other name ────────────────────
#
# New files go to the platform's own folder, and a library put together before
# keeps `megadrive/` beside `genesis/`. Everything that asks "is this one of
# the platform's shelves" has to count both, or a game in `megadrive/` never
# follows its title, its next disc lands in `genesis/` and splits the set, and
# a loose game's manual is named as if the game had a folder of its own.


def test_the_next_disc_joins_a_set_in_the_other_folder(tmp_path):
    from handler.roms.game_folder import choose_home

    other = tmp_path / "megadrive" / "Sonic CD"
    got = choose_home("Sonic CD (Disc 2).chd", [("Sonic CD (Disc 1).chd", str(other))],
                      tmp_path / "genesis")

    assert got == other, "druga plyta nie widzi pierwszej w folderze drugiej nazwy"


def test_a_loose_games_manual_there_is_named_after_the_game(tmp_path):
    from handler.metadata.manuals import manual_dest

    got = manual_dest(tmp_path / "megadrive", tmp_path / "genesis", "Gods", "Gods (USA).zip")

    assert got == tmp_path / "megadrive" / "extras" / "Gods - Manual.pdf", (
        "instrukcja luznej gry w megadrive/ nazwana jak w folderze gry - kazda luzna "
        "gra zajelaby ten sam plik"
    )


def test_an_upload_of_your_own_rom_there_is_written_where_it_is(tmp_path):
    from types import SimpleNamespace

    from endpoints.roms.roms_router import _upload_dest_dir

    def _at(folder):
        return SimpleNamespace(fs_name="Gods (USA).zip", fs_path=str(folder))

    base = str(tmp_path)
    assert _upload_dest_dir(base, "genesis", "Gods (USA).zip",
                            _at(tmp_path / "megadrive"), None) == tmp_path / "megadrive"
    assert _upload_dest_dir(base, "genesis", "Gods (USA).zip",
                            _at(tmp_path / "megadrive" / "Gods"), None) == (
        tmp_path / "megadrive" / "Gods")
    # And roms/ inside it keeps the rule roms/ always had.
    assert _upload_dest_dir(base, "genesis", "Gods (USA).zip",
                            _at(tmp_path / "megadrive" / "roms"), None) != (
        tmp_path / "megadrive" / "roms")


@pytest.mark.asyncio
async def test_a_game_there_follows_its_title_there(tmp_path):
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
    game = tmp_path / "megadrive" / "gods-usa"
    game.mkdir(parents=True)
    (game / "Gods (USA).zip").write_bytes(b"x")
    async with maker() as db:
        db.add(RomPlatform(id=1, fs_slug="genesis", slug=m.slug_from_fs_slug("genesis"),
                           name="Sega Genesis / Mega Drive"))
        db.add(Rom(id=1, platform_id=1, name="Gods", fs_name="Gods (USA).zip",
                   fs_name_no_ext="Gods (USA)", fs_extension="zip", fs_path=str(game),
                   fs_size_bytes=1))
        await db.commit()

        moved = await follow_title(1, roms_base=str(tmp_path), session=db)
        row = (await db.execute(select(Rom).where(Rom.id == 1))).scalars().first()
    await engine.dispose()

    assert moved == str(tmp_path / "megadrive" / "Gods"), (
        "gra w folderze drugiej nazwy konsoli nie idzie za tytulem"
    )
    assert row.fs_path == moved


def test_a_new_library_gets_one_folder_per_console():
    from handler.filesystem import rom_paths

    made = list(dict.fromkeys(m.canonical_fs_slug(s) for s in m.PLATFORM_MAP))
    assert "megadrive" not in made and "famicom" not in made and "sfc" not in made
    assert "genesis" in made and "nes" in made and "snes" in made
    source = rom_paths.__file__
    assert "canonical_fs_slug(" in open(source, encoding="utf-8").read(), (
        "tworzenie folderow nie pyta juz o glowna nazwe"
    )
