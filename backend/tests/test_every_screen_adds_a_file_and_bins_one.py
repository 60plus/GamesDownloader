"""Every screen can add a file to a ROM game and put a bin beside one file.

The owner (2026-09-18): "Add file" on a ROM, the way games have it, and a bin
beside each file - in ROMs and in games, and in Modern, Neon Horizon and
Classic the games get the "Show details" list Vapor has, for the bin to stand
in. The server's side is tested beside the routes; this is the screens':

  * the requests live in the core (API-first): the ROM dialog is the core's,
    opened through __GD__.ui.openRomAddFileDialog, and the bins call
    __GD__.roms.removeExtra and __GD__.library.removeFile - the last one only
    reaches a theme if it is in the hand-written list at the end of
    libraryActions.ts (the trap that broke Vapor's upload on 2026-09-10);
  * a bin is drawn only where the server says it works (can_delete);
  * My uploads offers "Remove my files" on a ROM the account only added to.
"""
from __future__ import annotations

import pathlib

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent.parent
FRONTEND = REPO / "frontend" / "src"
VAPOR = REPO.parent / "vapor_build" / "gd3-vapor"


def _read(path: pathlib.Path) -> str:
    if not path.is_file():
        pytest.skip(f"{path.name} nie jest obecny w tym drzewie")
    return path.read_text(encoding="utf-8")


def test_the_core_carries_every_request():
    roms = _read(FRONTEND / "lib" / "romSourceActions.ts")
    at = roms.index("export const romActions")
    ns = roms[at:roms.index("};", at)]
    for name in ("addFile: addRomFile", "removeExtra: removeRomExtra", "removeMyFiles: removeMyRomFiles"):
        assert name in ns, f"__GD__.roms nie ma {name}"

    library = _read(FRONTEND / "lib" / "libraryActions.ts")
    at = library.index("const libraryActions = {")
    assert "removeFile," in library[at:library.index("};", at)], (
        "removeFile nie trafil do recznej listy __GD__.library - Vapor go nie zobaczy")

    main = _read(FRONTEND / "main.ts")
    assert "openRomAddFileDialog," in main, "__GD__.ui nie otwiera okna dodawania pliku do ROM-u"


def test_the_rom_dialog_asks_before_replacing_and_names_each_refusal():
    form = _read(FRONTEND / "components" / "roms" / "RomAddFileForm.vue")
    assert "x-gd-reason" in form and "'already_here'" in form
    assert "upload.replace_confirm" in form
    for kind in ('value="extra"', 'value="mod"', 'value="manual"', 'value="game"'):
        assert kind in form
    # Every reason the route can send has its words (1.0.36 audit: not_a_file
    # came through as the server's English sentence).
    import re
    router = _read(pathlib.Path(__file__).resolve().parent.parent
                   / "endpoints" / "roms" / "roms_router.py")
    block = router[router.index("async def add_rom_file("):router.index("async def remove_rom_extra(")]
    sent = set(re.findall(r'_refused\(\d+, "(\w+)"', block)) - {"already_here", "bad_kind"}
    reasons = form[form.index("const REASONS"):]
    reasons = reasons[:reasons.index("}")]
    missing = {r for r in sent if f"{r}:" not in reasons}
    assert not missing, f"powod bez zdania na ekranie: {sorted(missing)}"


def test_a_further_disc_shows_up_once_its_scan_has_run():
    """It is registered by a scan after the upload answers, so the page is
    asked again while that runs - by the host, which stays mounted when the
    dialog is closed after "done" (1.0.36 audit, round 2: timers in the form
    went with it)."""
    form = _read(FRONTEND / "components" / "roms" / "RomAddFileForm.vue")
    fn = form[form.index("async function submit("):]
    fn = fn[:fn.index("\n}\n")]
    assert "emit('added', sent === 'game')" in fn
    assert "setTimeout" not in form, "ponowienia w formularzu gina razem z oknem"
    host = _read(FRONTEND / "components" / "common" / "PluginUiHost.vue")
    added = host[host.index("function onRomFileAdded("):]
    added = added[:added.index("\n}\n")]
    assert "if (scanning)" in added and "setTimeout(tell" in added


def test_classic_keeps_a_late_quiet_answer_off_another_game():
    page = _read(FRONTEND / "layouts" / "ClassicGameDetail.vue")
    fn = page[page.index("async function loadGame("):]
    fn = fn[:fn.index("\n}\n")]
    got = fn.index("await client.get(endpoint)")
    guard = fn.index("if (quiet && String(id) !== String(props.gameId)) return")
    assert got < guard < fn.index("game.value = {")


@pytest.mark.parametrize("page", [
    FRONTEND / "views" / "emulation" / "EmulationGameDetail.vue",
    FRONTEND / "layouts" / "ClassicGameDetail.vue",
    VAPOR / "VaporRomDetail.vue",
])
def test_every_rom_page_opens_the_core_dialog(page):
    assert "openRomAddFileDialog" in _read(page)


@pytest.mark.parametrize("page", [
    FRONTEND / "views" / "emulation" / "EmulationGameDetail.vue",
    FRONTEND / "layouts" / "ClassicGameDetail.vue",
])
def test_the_rom_list_is_given_its_rom_so_it_can_bin(page):
    source = _read(page)
    at = source.index("<RomFilesList")
    tag = source[at:source.index("/>", at)]
    assert ":rom-id=" in tag and "@changed=" in tag


@pytest.mark.parametrize("page", [
    FRONTEND / "views" / "emulation" / "EmulationGameDetail.vue",
    FRONTEND / "layouts" / "ClassicGameDetail.vue",
])
def test_show_details_stays_once_the_last_extra_is_binned(page):
    """The owner, 2026-09-19: in Classic, binning a game's only extra took the
    Show details button away with it - the list was drawn only while there was
    something beside the game. It stays, as in Modern and Neon Horizon."""
    import re

    source = _read(page)
    at = source.index("<RomFilesList")
    tag = source[at:source.index("/>", at)]
    assert re.search(r"\salways[\s/>]", tag), "Show details znika razem z ostatnim dodatkiem"


def test_the_rom_list_bins_only_what_it_may():
    files = _read(FRONTEND / "components" / "roms" / "RomFilesList.vue")
    assert "f.can_delete" in files and "removeRomExtra(" in files


@pytest.mark.parametrize("page", [
    FRONTEND / "views" / "games" / "GamesGameDetail.vue",
    FRONTEND / "layouts" / "ClassicGameDetail.vue",
])
def test_modern_neon_horizon_and_classic_games_show_details_with_a_bin(page):
    assert "<GameFilesList" in _read(page)


def test_the_game_list_bins_only_what_it_may():
    files = _read(FRONTEND / "components" / "games" / "GameFilesList.vue")
    assert "f.can_delete" in files and "removeFile(" in files


def test_vapor_bins_through_the_core_and_asks_first():
    rom = _read(VAPOR / "VaporRomDetail.vue")
    game = _read(VAPOR / "VaporGameDetail.vue")
    assert "_gd.roms.removeExtra(" in rom and "f.can_delete" in rom
    assert "_gd.library.removeFile(" in game and "f.can_delete" in game
    for source in (rom, game):
        for fn in ("async function removeExtra(", "async function removeGameFile("):
            if fn in source:
                body = source[source.index(fn):]
                body = body[:body.index("\n}\n")]
                assert "window.confirm" not in body, "natywne okno w motywie"


def test_my_uploads_takes_back_the_files_added_to_somebody_elses_rom():
    panel = _read(FRONTEND / "components" / "MyUploadsPanel.vue")
    assert "files_only" in panel and "/roms/${g.id}/my-files" in panel
