"""Changing disc from the in-game menu, not only from the mouse.

Loading a multi-disc title puts every disc in the emulator at once, and
EmulatorJS shows a disc list of its own in the control bar. That list is a
mouse target: it sits in a toolbar under the canvas, and a player on a sofa
with a gamepad cannot reach it. The in-game menu, which is what Start+Select
opens, had a Disks page for Amiga floppies and nothing at all for a
PlayStation game on four discs, so the one platform where disc swapping is
routine was the one platform that could not do it without a mouse.

Reported by the user while looking at the release notes for the feature.

The switch itself goes through EmulatorJS's own `menuOptionChanged('disk', n)`
rather than straight to `gameManager.setCurrentDisk(n)`. Both change the disc,
but only the first also records it in `allSettings`, which is what the
emulator's own disc list reads back: calling the low level one leaves the two
menus disagreeing about which disc is in the machine.
"""
from __future__ import annotations

import pathlib

import pytest

PLAYER = (pathlib.Path(__file__).resolve().parent.parent.parent
          / "frontend" / "public" / "player.html")


@pytest.fixture(scope="module")
def player() -> str:
    if not PLAYER.is_file():
        pytest.skip("player.html nie jest kopiowany do obrazu")
    return PLAYER.read_text(encoding="utf-8")


def test_the_menu_offers_discs_and_not_only_amiga_floppies(player):
    """The Disks page existed, but every path into it asked the Amiga disk set
    whether there was anything to show, and for a PlayStation title that set is
    empty."""
    assert "_gdDiscSet" in player, "brak listy plyt dla menu w grze"


@pytest.mark.parametrize("where", ["_refreshItems", "_ensureDiskCategory"])
def test_every_path_into_the_page_asks_about_discs_too(player, where):
    """Two separate decisions, and missing either leaves the page unreachable
    in a way that looks like a design choice: one shows the entry in the pause
    menu, the other gives the sub-page a heading to exist under."""
    at = player.index("function " + where)
    body = player[at:at + 900]
    assert "_ejsDiscCount" in body, f"{where}: pyta wylacznie o dyskietki Amigi"


def test_switching_goes_through_the_emulators_own_setting(player):
    """setCurrentDisk alone changes the disc and leaves EmulatorJS's own list
    still pointing at the previous one."""
    assert "menuOptionChanged('disk'" in player, (
        "zmiana plyty omija ustawienie, ktore czyta wlasne menu emulatora"
    )


def test_the_count_the_emulator_reports_wins_over_our_labels(player):
    """Labels come from the library and the index from the playlist the
    emulator was handed. They are built from the same ordered query, so they
    agree, but a menu that puts in the wrong disc is worse than one with plain
    labels, so a disagreement falls back to counting."""
    assert "getDiskCount" in player, (
        "nic nie sprawdza, ile plyt emulator naprawde widzi"
    )
