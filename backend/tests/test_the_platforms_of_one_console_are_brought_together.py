"""The platforms a library already has for one console become one, on start.

A library that met Mega Drive games under `megadrive/` and Genesis games under
`genesis/` has two platform rows with games on each. The scan reads both
folders into one platform from now on (test_one_console_is_one_platform.py),
so the rows it made before have to be brought together first, or the scan
finds every game of the other row "new" in the first and the old entries go
missing - with their saves, play history, metadata and owner.

So each game is moved onto the console's platform row and keeps its id, which
everything hangs off. Its artwork is moved to the folder named after that row
and the paths the row keeps are rewritten to match; saves that an older install
keeps in a folder inside that one are left exactly where they are. A platform's
own settings come along when the console's row has none of its own.

THE ONE RULE THAT MATTERS MOST: a platform row takes its games with it when it
is deleted (ON DELETE CASCADE). So a row is removed only after its games are on
the other row, and that is counted, not assumed.
"""
from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy import event, func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from handler.metadata.rom_platform_map import slug_from_fs_slug
from handler.roms import platform_merge
from models.rom import Rom
from models.rom_platform import RomPlatform
from models.user import User

GENESIS = slug_from_fs_slug("genesis")      # "sega-genesis-mega-drive"
MEGADRIVE_OLD = "sega-mega-drive"           # what a megadrive row was called


@pytest_asyncio.fixture
async def db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)

    # SQLite ignores ON DELETE CASCADE unless told otherwise, and the cascade
    # is exactly what a wrong order here would set off on MariaDB.
    @event.listens_for(engine.sync_engine, "connect")
    def _foreign_keys(dbapi_connection, _record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as conn:
        # With foreign keys on, what a ROM row points at has to exist too.
        await conn.run_sync(User.__table__.create)
        await conn.run_sync(RomPlatform.__table__.create)
        await conn.run_sync(Rom.__table__.create)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as session:
        yield session
    await engine.dispose()


@pytest.fixture
def config(monkeypatch):
    sections: dict[str, dict] = {}
    monkeypatch.setattr(platform_merge.config_manager, "get_section",
                        lambda name: sections.get(name))
    monkeypatch.setattr(platform_merge.config_manager, "save_section",
                        lambda name, data: sections.__setitem__(name, data))
    return sections


def _platform(db, pid, fs_slug, slug, name, **extra):
    db.add(RomPlatform(id=pid, fs_slug=fs_slug, slug=slug, name=name, **extra))


def _rom(db, rid, pid, slug, **extra):
    base = f"/resources/roms/{slug}/{rid}/"
    fields = dict(cover_path=base + "cover.png", screenshots=[base + "screenshot_0.png"])
    fields.update(extra)
    db.add(Rom(id=rid, platform_id=pid, name=f"Game {rid}", fs_name=f"g{rid}.zip",
               fs_name_no_ext=f"g{rid}", fs_extension="zip", fs_path=f"/lib/x/{rid}",
               fs_size_bytes=1, **fields))


def _media(resources, slug, rid, *names):
    folder = resources / "roms" / slug / str(rid)
    folder.mkdir(parents=True, exist_ok=True)
    for name in names:
        (folder / name).write_bytes(name.encode())
    return folder


async def _row(db, model, key):
    return (await db.execute(select(model).where(model.id == key))).scalars().first()


@pytest.mark.asyncio
async def test_the_games_move_onto_the_console_and_keep_everything(db, config, tmp_path):
    resources = tmp_path / "resources"
    _platform(db, 36, "genesis", GENESIS, "Sega Genesis / Mega Drive")
    _platform(db, 43, "megadrive", MEGADRIVE_OLD, "Sega Mega Drive")
    _rom(db, 49, 36, GENESIS)
    _rom(db, 110, 43, MEGADRIVE_OLD, manual_path="extras/Manual.pdf")
    _rom(db, 111, 43, MEGADRIVE_OLD)
    await db.commit()
    _media(resources, MEGADRIVE_OLD, 110, "cover.png", "screenshot_0.png")

    await platform_merge.merge_console_platforms(session=db, resources_path=str(resources))

    total = (await db.execute(select(func.count(Rom.id)))).scalar()
    assert total == 3, "wiersze gier zginely przy scalaniu platform"
    gods = await _row(db, Rom, 110)
    assert gods.platform_id == 36 and gods.name == "Game 110"
    assert (await _row(db, Rom, 111)).platform_id == 36
    assert gods.cover_path == f"/resources/roms/{GENESIS}/110/cover.png"
    assert gods.screenshots == [f"/resources/roms/{GENESIS}/110/screenshot_0.png"]
    assert gods.manual_path == "extras/Manual.pdf", "sciezka wzgledna do folderu gry ruszona"
    assert (resources / "roms" / GENESIS / "110" / "cover.png").read_bytes() == b"cover.png"
    assert await _row(db, RomPlatform, 43) is None, "wiersz drugiej nazwy konsoli zostal"


@pytest.mark.asyncio
async def test_a_picture_that_could_not_be_moved_keeps_its_old_address(db, config, tmp_path):
    """The old address still serves the file, so it is kept rather than
    pointed at a place the file never reached."""
    resources = tmp_path / "resources"
    _platform(db, 36, "genesis", GENESIS, "Sega Genesis / Mega Drive")
    _platform(db, 43, "megadrive", MEGADRIVE_OLD, "Sega Mega Drive")
    _rom(db, 110, 43, MEGADRIVE_OLD)
    await db.commit()
    _media(resources, MEGADRIVE_OLD, 110, "cover.png", "screenshot_0.png")
    _media(resources, GENESIS, 110, "cover.png")     # already taken over there

    await platform_merge.merge_console_platforms(session=db, resources_path=str(resources))

    gods = await _row(db, Rom, 110)
    assert gods.cover_path == f"/resources/roms/{MEGADRIVE_OLD}/110/cover.png"
    assert gods.screenshots == [f"/resources/roms/{GENESIS}/110/screenshot_0.png"]


@pytest.mark.asyncio
async def test_saves_kept_inside_the_artwork_folder_are_not_touched(db, config, tmp_path):
    """An install without a volume for saves keeps them in the artwork folder,
    under states/ and saves/, and the save rows point at those paths."""
    resources = tmp_path / "resources"
    _platform(db, 36, "genesis", GENESIS, "Sega Genesis / Mega Drive")
    _platform(db, 43, "megadrive", MEGADRIVE_OLD, "Sega Mega Drive")
    _rom(db, 110, 43, MEGADRIVE_OLD)
    await db.commit()
    old = _media(resources, MEGADRIVE_OLD, 110, "cover.png")
    (old / "states" / "7").mkdir(parents=True)
    (old / "states" / "7" / "Gods [slot 1].state").write_bytes(b"save")

    await platform_merge.merge_console_platforms(session=db, resources_path=str(resources))

    assert (old / "states" / "7" / "Gods [slot 1].state").read_bytes() == b"save"


@pytest.mark.asyncio
async def test_a_console_with_no_main_row_gets_one(db, config, tmp_path):
    _platform(db, 43, "megadrive", MEGADRIVE_OLD, "Sega Mega Drive")
    _rom(db, 110, 43, MEGADRIVE_OLD)
    await db.commit()
    _media(tmp_path / "resources", MEGADRIVE_OLD, 110, "cover.png", "screenshot_0.png")

    await platform_merge.merge_console_platforms(session=db,
                                                 resources_path=str(tmp_path / "resources"))

    row = await _row(db, RomPlatform, 43)
    assert (row.fs_slug, row.slug, row.name) == ("genesis", GENESIS, "Sega Genesis / Mega Drive")
    assert (await _row(db, Rom, 110)).cover_path == f"/resources/roms/{GENESIS}/110/cover.png"


@pytest.mark.asyncio
async def test_a_platforms_settings_come_along(db, config, tmp_path):
    _platform(db, 36, "genesis", GENESIS, "Sega Genesis / Mega Drive", scan_exclude="Thumbs.db")
    _platform(db, 43, "megadrive", MEGADRIVE_OLD, "Sega Mega Drive",
              scan_exclude="*.txt\nThumbs.db", custom_name="My Mega Drive",
              cover_path="/resources/platforms/md.png")
    _platform(db, 27, "famicom", "famicom", "Famicom", scan_exclude="*.nfo")
    _platform(db, 54, "nes", slug_from_fs_slug("nes"), "Nintendo Entertainment System")
    await db.commit()
    config["rom_scrape_presets"] = {
        "megadrive": {"cover_type": "box-3D", "extras": ["manuel"]},
        "famicom": {"cover_type": "box-2D", "extras": ["ss"]},
        "nes": {"cover_type": "box-3D", "extras": ["ss", "video"]},
    }
    config["platform_info"] = {"megadrive": {"description": "Sega's 16-bit console"}}

    await platform_merge.merge_console_platforms(session=db, resources_path=str(tmp_path))

    genesis = await _row(db, RomPlatform, 36)
    assert set(genesis.scan_exclude.splitlines()) == {"Thumbs.db", "*.txt"}
    assert genesis.custom_name == "My Mega Drive"
    assert genesis.cover_path == "/resources/platforms/md.png"
    presets = config["rom_scrape_presets"]
    assert presets["genesis"] == {"cover_type": "box-3D", "extras": ["manuel"]}
    assert presets["nes"] == {"cover_type": "box-3D", "extras": ["ss", "video"]}, (
        "preset glownej platformy nadpisany presetem drugiej nazwy"
    )
    assert "megadrive" not in presets and "famicom" not in presets
    assert config["platform_info"] == {"genesis": {"description": "Sega's 16-bit console"}}


@pytest.mark.asyncio
async def test_running_it_again_changes_nothing(db, config, tmp_path):
    _platform(db, 36, "genesis", GENESIS, "Sega Genesis / Mega Drive")
    _platform(db, 43, "megadrive", MEGADRIVE_OLD, "Sega Mega Drive")
    _rom(db, 110, 43, MEGADRIVE_OLD)
    await db.commit()

    first = await platform_merge.merge_console_platforms(session=db, resources_path=str(tmp_path))
    second = await platform_merge.merge_console_platforms(session=db, resources_path=str(tmp_path))

    assert first["merged"] == 1
    assert second == {"merged": 0, "renamed": 0, "roms_moved": 0}


@pytest.mark.asyncio
async def test_platforms_of_other_consoles_are_left_alone(db, config, tmp_path):
    _platform(db, 85, "snes", slug_from_fs_slug("snes"), "Super Nintendo")
    _platform(db, 2, "amiga", "amiga", "Amiga")
    _platform(db, 3, "amiga1200", "amiga-1200", "Amiga 1200")
    await db.commit()

    out = await platform_merge.merge_console_platforms(session=db, resources_path=str(tmp_path))

    assert out == {"merged": 0, "renamed": 0, "roms_moved": 0}
    assert await _row(db, RomPlatform, 3) is not None


def test_it_runs_on_start_before_anything_can_scan():
    """After the database is ready and before the folders are made or any scan
    can run: a scan that came first would find every game of the other row new
    in the console's platform."""
    import pathlib

    main = (pathlib.Path(__file__).resolve().parent.parent / "main.py").read_text(encoding="utf-8")
    body = main[main.index("async def lifespan("):]
    ready = body.index("await _init_db()")
    merge = body.index("await _merge_console_platforms()")
    folders = body.index("_init_rom_dirs()")
    assert ready < merge < folders


def test_empty_folders_of_the_other_names_are_tidied_away(tmp_path):
    """Folders the application made for every name, before one console was one
    platform. Only empty ones: a folder with anything in it is somebody's."""
    for name in ("genesis", "megadrive", "famicom", "sfc", "n64"):
        (tmp_path / name).mkdir()
    (tmp_path / "famicom" / "Mario.nes").write_bytes(b"x")

    removed = platform_merge.tidy_console_folders(str(tmp_path))

    assert sorted(removed) == ["megadrive", "sfc"]
    assert (tmp_path / "famicom" / "Mario.nes").is_file()
    assert (tmp_path / "genesis").is_dir() and (tmp_path / "n64").is_dir()
