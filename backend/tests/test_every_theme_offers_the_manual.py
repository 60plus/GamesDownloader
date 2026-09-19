"""The manual button lives in the core, so every theme has the same one.

The owner's call: at the core level, so all of them have it. One component
owns everything about it - when it shows, what it says in eight languages, how
it opens - and each game page places it:

  Modern         views/emulation/EmulationGameDetail.vue
  Neon Horizon   the same page: it opens a ROM through the core route and has
                 no ROM page of its own, so it gets the button with Modern
  Classic        layouts/ClassicGameDetail.vue, in its ROM branch
  Vapor          VaporRomDetail.vue, through the component core registers for
                 plugin themes, the way it already uses DownloadDialog

Couch mode is left for later, deliberately: a PDF viewer cannot be driven with
a gamepad.

The manual lives beside the game in its extras (the owner's decision), in the
ROM tree, which nothing serves by path. So the button carries no link at all:
it asks the server for a short-lived ticket and opens that, the way the ROM
download does, and the page is told only whether there is a manual - never
where it sits on the server's disk.
"""
from __future__ import annotations

import io
import pathlib

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent.parent
FRONTEND = REPO / "frontend" / "src"
COMPONENT = FRONTEND / "components" / "roms" / "RomManualButton.vue"
# Vapor is its own repository, checked out beside this one on a workstation and
# nowhere on the test server - so its assertion runs where it can and skips
# where it cannot, like the frontend checks do when the tree is absent.
VAPOR = REPO.parent / "vapor_build" / "gd3-vapor" / "VaporRomDetail.vue"


def _read(path: pathlib.Path) -> str:
    if not path.is_file():
        pytest.skip(f"{path.name} nie jest obecny w tym drzewie")
    return io.open(path, encoding="utf-8").read()


def test_there_is_one_manual_button():
    source = _read(COMPONENT)
    assert "detail.manual" in source and "detail.manual_hint" in source, (
        "przycisk nie idzie przez tlumaczenia"
    )


def test_it_opens_beside_the_app_and_cannot_reach_back():
    source = _read(COMPONENT)
    assert '"_blank"' in source
    assert "noopener" in source


def test_it_opens_through_a_ticket():
    """A navigation carries no Authorization header; the button asks for a
    ticket over the authenticated connection and opens that."""
    source = _read(COMPONENT)
    assert "/manual-ticket" in source, "przycisk nie prosi o bilet"
    assert "href" not in source, "przycisk niesie gotowy adres zamiast biletu"


def test_a_failure_is_said_out_loud():
    source = _read(COMPONENT)
    assert "detail.manual_failed" in source, "nieudane otwarcie konczy sie cisza"


def test_plugin_themes_can_use_it():
    main = _read(FRONTEND / "main.ts")
    assert 'app.component("RomManualButton"' in main, (
        "motywy-wtyczki nie dostana wspolnego przycisku"
    )


def test_modern_and_neon_horizon_show_it():
    page = _read(FRONTEND / "views" / "emulation" / "EmulationGameDetail.vue")
    assert "<RomManualButton" in page and "has_manual" in page


def test_classic_shows_it_for_a_rom():
    page = _read(FRONTEND / "layouts" / "ClassicGameDetail.vue")
    at = page.index("<RomManualButton")
    assert "roms" in page[at - 300:at + 200], (
        "Classic pokazuje instrukcje poza strona ROM-u"
    )


def test_vapor_shows_it():
    page = _read(VAPOR)
    assert "<RomManualButton" in page and "has_manual" in page
