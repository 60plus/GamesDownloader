"""The platform folders are made where the ROM library actually is.

They are how somebody knows where to put ROMs over FTP or a file share before
anything has been uploaded: one folder per platform, ready to fill. They were
made on every start in the default `/data/games/roms` whatever the library had
been moved to in Settings > ROMs. So a moved library had none, and the default
place kept a hundred empty folders nothing read. Saving a new path made nothing
at all until a restart, and then still in the wrong place.

THE OWNER DECIDED THIS (2026-09-17): made at start and again the moment a new
path is saved, in the library in use. A moved path that does not exist - a typo,
a disk that is not mounted into the container - is not created: folders made
there would live inside the container, invisible over FTP and gone when it is
recreated. The screen says so instead.
"""

from __future__ import annotations

import io
import json
import pathlib
import re
from types import SimpleNamespace

import pytest

BACKEND = pathlib.Path(__file__).resolve().parent.parent
FRONTEND = BACKEND.parent / "frontend"
SETTINGS_VUE = FRONTEND / "src" / "views" / "settings" / "SettingsRoms.vue"


# ── Making them ──────────────────────────────────────────────────────────────

def test_one_folder_per_platform_in_the_root_it_is_given(tmp_path):
    from handler.filesystem.rom_paths import make_platform_folders

    out = make_platform_folders(str(tmp_path), create_root=False)

    assert out["root_exists"] is True
    assert (tmp_path / "psx").is_dir() and (tmp_path / "snes").is_dir()
    assert not (tmp_path / "playstation").exists(), (
        "platforma z dwiema nazwami dostala drugi folder"
    )
    assert out["created"] == len([p for p in tmp_path.iterdir() if p.is_dir()])


def test_folders_already_there_are_left_as_they_are(tmp_path):
    from handler.filesystem.rom_paths import make_platform_folders

    (tmp_path / "psx").mkdir()
    (tmp_path / "psx" / "Game.cue").write_text("mine")
    first = make_platform_folders(str(tmp_path), create_root=False)
    again = make_platform_folders(str(tmp_path), create_root=False)

    assert (tmp_path / "psx" / "Game.cue").read_text() == "mine"
    assert first["created"] > 0 and again["created"] == 0


def test_a_library_that_is_not_there_is_not_made_up(tmp_path):
    from handler.filesystem.rom_paths import make_platform_folders

    missing = tmp_path / "not-mounted" / "roms"
    out = make_platform_folders(str(missing), create_root=False)

    assert out == {"root_exists": False, "created": 0}
    assert not missing.exists() and not (tmp_path / "not-mounted").exists(), (
        "foldery powstaly w sciezce, ktorej nie ma - w kontenerze znikna przy "
        "jego odtworzeniu i nie widac ich przez FTP"
    )


def test_the_default_library_is_still_made_on_a_fresh_install(tmp_path):
    from handler.filesystem.rom_paths import make_platform_folders

    fresh = tmp_path / "games" / "roms"
    out = make_platform_folders(str(fresh), create_root=True)

    assert out["root_exists"] is True and (fresh / "psx").is_dir()


# ── At start ─────────────────────────────────────────────────────────────────

@pytest.fixture
def moved(monkeypatch, tmp_path):
    """The library moved in Settings > ROMs to *tmp_path/moved*."""
    from config import config_manager

    root = tmp_path / "moved"
    monkeypatch.setattr(config_manager, "get_section",
                        lambda name: {"library_path": str(root)} if name == "roms" else {})
    return root


def test_start_makes_them_in_the_moved_library(moved):
    import main

    moved.mkdir()
    main._init_rom_dirs()

    assert (moved / "psx").is_dir(), "start zaklada foldery platform poza przeniesiona biblioteka"


def test_start_does_not_invent_a_moved_library_or_fall_back_to_the_old_place(moved, monkeypatch, tmp_path):
    import config
    import main
    from handler.filesystem import rom_paths

    # A default place of this test's own, so what another test made there
    # cannot pass for nothing having happened.
    default = tmp_path / "default" / "roms"
    monkeypatch.setattr(config, "ROMS_PATH", str(default))
    monkeypatch.setattr(rom_paths, "ROMS_PATH", str(default))

    main._init_rom_dirs()

    assert not moved.exists()
    assert not default.exists(), "przy braku przeniesionej biblioteki start zaklada foldery w starym miejscu"


# ── On save, and on the screen ───────────────────────────────────────────────

@pytest.fixture
def settings(monkeypatch):
    from endpoints.settings import roms_settings_router as r

    store: dict = {"roms": {}}
    monkeypatch.setattr(r.config_manager, "get_section", lambda name: dict(store.get(name) or {}))
    monkeypatch.setattr(r.config_manager, "save_section",
                        lambda name, data: store.__setitem__(name, dict(data)))
    return r, store


def _route(fn):
    return getattr(fn, "__wrapped__", fn)


@pytest.mark.asyncio
async def test_saving_a_new_path_makes_the_folders_right_away(settings, tmp_path):
    r, _store = settings
    root = tmp_path / "nas" / "roms"
    root.mkdir(parents=True)

    out = await _route(r.save_rom_settings)(SimpleNamespace(), r.RomSettingsBody(library_path=str(root)))

    assert (root / "psx").is_dir(), "po zapisie nowej sciezki folderow platform nie ma do restartu"
    assert out["library_path_missing"] is False


@pytest.mark.asyncio
async def test_saving_a_path_that_is_not_there_makes_nothing_and_says_so(settings, tmp_path):
    r, store = settings
    root = tmp_path / "typo" / "roms"

    out = await _route(r.save_rom_settings)(SimpleNamespace(), r.RomSettingsBody(library_path=str(root)))

    assert out["library_path_missing"] is True
    assert not root.exists() and not (tmp_path / "typo").exists()
    assert store["roms"]["library_path"] == str(root), "ustawienie ma sie zapisac mimo ostrzezenia"


@pytest.mark.asyncio
async def test_the_screen_is_told_when_the_library_is_missing(settings, tmp_path):
    r, store = settings
    store["roms"] = {"library_path": str(tmp_path / "gone")}

    shown = await _route(r.get_rom_settings)(SimpleNamespace())
    assert shown["library_path_missing"] is True

    (tmp_path / "gone").mkdir()
    shown = await _route(r.get_rom_settings)(SimpleNamespace())
    assert shown["library_path_missing"] is False


def _vue() -> str:
    return io.open(SETTINGS_VUE, encoding="utf-8").read()


def test_the_screen_shows_the_warning_after_loading_and_after_saving():
    source = _vue()
    load = source[source.index("async function load()"):]
    load = load[:load.index("\n}")]
    save = source[source.index("async function save()"):]
    save = save[:save.index("\n}")]

    assert re.search(r"libraryMissing\.value\s*=\s*!!data\.library_path_missing", load)
    assert re.search(r"libraryMissing\.value\s*=\s*!!data\??\.library_path_missing", save), (
        "ekran nie czyta odpowiedzi zapisu, wiec ostrzezenie pojawi sie dopiero po odswiezeniu"
    )
    assert re.search(r"v-if=\"libraryMissing\"[^>]*>\s*\{\{\s*t\('roms\.library_path_missing'\)", source)


def test_the_warning_is_written_in_every_language():
    key = "roms.library_path_missing"
    files = [FRONTEND / "src" / "i18n" / "en.json", *sorted((FRONTEND / "public" / "i18n").glob("*.json"))]
    assert len(files) == 8
    for path in files:
        text = json.loads(io.open(path, encoding="utf-8").read()).get(key, "")
        assert text.strip(), f"brak tlumaczenia {key} w {path.name}"
