"""Every theme shows a ROM's extras and mods, and downloads them one way.

The owner's decision (2026-09-19): the files beside a game are offered the way
a GOG or custom game offers its own - listed behind "Show details" with what
each is and its size, and the Download button opening a picker with the game
ticked when there is anything to pick from. The model is Vapor's.

  Modern         views/emulation/EmulationGameDetail.vue
  Neon Horizon   the same page, through the core route
  Classic        layouts/ClassicGameDetail.vue, in its ROM info card
  Vapor          VaporRomDetail.vue, its own picker in its own look

The downloading is the core's alone (__GD__.roms.downloadFiles): which ticket,
the whole-set archive, one file after another. A theme that built the routes
itself would be one more place to change when they move.
"""
from __future__ import annotations

import io
import pathlib

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent.parent
FRONTEND = REPO / "frontend" / "src"
VAPOR = REPO.parent / "vapor_build" / "gd3-vapor"


def _read(path: pathlib.Path) -> str:
    if not path.is_file():
        pytest.skip(f"{path.name} nie jest obecny w tym drzewie")
    return io.open(path, encoding="utf-8").read()


def test_the_core_downloads_a_rom_and_its_files_in_one_place():
    actions = _read(FRONTEND / "lib" / "romSourceActions.ts")
    assert "/extra-ticket" in actions and "downloadFiles: downloadRomFiles" in actions


def test_the_picker_ticks_the_game_and_offers_the_rest():
    dialog = _read(FRONTEND / "components" / "roms" / "RomDownloadDialog.vue")
    assert "romActions.downloadFiles(" in dialog
    assert "detail.type_mods" in dialog and "detail.type_extras" in dialog
    assert "new Set<string>([GAME])" in dialog, "gra nie jest zaznaczona z gory"


@pytest.mark.parametrize("page", [
    FRONTEND / "views" / "emulation" / "EmulationGameDetail.vue",
    FRONTEND / "layouts" / "ClassicGameDetail.vue",
])
def test_modern_neon_horizon_and_classic_show_them(page):
    source = _read(page)
    assert "<RomFilesList" in source and "<RomDownloadDialog" in source
    assert "extras?.length" in source, "Download nie otwiera wyboru, gdy sa dodatki"


def test_the_list_names_every_disc_of_the_game():
    """The owner (2026-09-18): Show details lists every disc, the way a GOG
    game lists each of its files, rather than one "All 2 discs" line."""
    files = _read(FRONTEND / "components" / "roms" / "RomFilesList.vue")
    assert 'v-for="d in discs"' in files, "lista nie pokazuje plyt osobno"
    assert "always ||" in files, "lista znika w grze bez dodatkow"


def test_modern_and_neon_horizon_show_the_files_only_in_the_list():
    """The row that named the first disc alone is gone: the list says it all,
    and on those two it is always there to open."""
    page = _read(FRONTEND / "views" / "emulation" / "EmulationGameDetail.vue")
    assert "gd-file-info-row" not in page, "wiersz z pierwszym plikiem nadal jest"
    at = page.index("<RomFilesList")
    tag = page[at:page.index("/>", at)]
    assert ':discs="diskSet"' in tag and "always" in tag


def test_classic_lists_every_disc_too():
    page = _read(FRONTEND / "layouts" / "ClassicGameDetail.vue")
    at = page.index("<RomFilesList")
    assert ':discs="diskSet"' in page[at:page.index("/>", at)]


@pytest.mark.parametrize("page", [
    FRONTEND / "views" / "emulation" / "EmulationGameDetail.vue",
    FRONTEND / "layouts" / "ClassicGameDetail.vue",
    VAPOR / "VaporRomDetail.vue",
])
def test_every_theme_weighs_a_game_on_one_disc_with_its_tracks(page):
    """A .cue alone is a few kilobytes; the server says what its tracks add
    (test_a_disc_weighs_what_its_download_holds.py)."""
    source = _read(page)
    at = source.index("const titleBytes")
    assert "tracks_bytes" in source[at:at + 220], "rozmiar gry z jednej plyty to sam arkusz"


def test_vapor_lists_each_disc_with_its_size():
    """The owner (2026-09-18): Vapor's list gave "Disc 1" where the other
    themes give the size."""
    source = _read(VAPOR / "VaporRomDetail.vue")
    at = source.index('v-for="d in diskSet" :key="d.id" class="vp-dlfile"')
    row = source[at:source.index("</div>", at)]
    assert "gb(d.size" in row and "disk_n" not in row


@pytest.mark.parametrize("page, key", [
    (FRONTEND / "views" / "emulation" / "EmulationGameDetail.vue", "detail.delete_rom_extras"),
    (FRONTEND / "layouts" / "ClassicGameDetail.vue", "detail.delete_rom_extras"),
    (FRONTEND / "components" / "MyUploadsPanel.vue", "uploads.delete_extras"),
    (VAPOR / "VaporRomDetail.vue", "detail.delete_rom_extras"),
])
def test_the_delete_warning_says_the_extras_and_mods_go(page, key):
    """Decision D: they go with the files, after a warning that names them -
    not counted among the data files the disc sheets name."""
    source = _read(page)
    assert key in source and ".extras" in source, "ostrzezenie nie mowi, ze dodatki i mody znikna"


def test_vapor_shows_them_and_leaves_the_downloading_to_the_core():
    page = _read(VAPOR / "VaporRomDetail.vue")
    dialog = _read(VAPOR / "VaporRomDownloadDialog.vue")
    assert "<VaporRomDownloadDialog" in page and "romExtras" in page
    assert "_gd.roms.downloadFiles(" in dialog
    assert "/extra-ticket" not in dialog + page, "Vapor sam sklada trase dodatkow"
