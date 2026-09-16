"""Ticking "remember my choice" was a one way trip.

The dialog behind Play asks three things at once: fullscreen or window or new
tab, whether to lay the bezel over the picture, and whether to remember the
answer. Remembering it is what made the other two unreachable. Modern and Vapor
skip the dialog entirely once a mode is saved, so from then on there is no way
to change the mode back and, worse, no way to reach the bezel toggle at all:
for a game never launched before, the bezel reads as off and nothing can turn
it on.

Classic had the mirror image of the problem. It shows the dialog on every
launch, deliberately, with a comment saying that is how the bezel toggle stays
visible. The cost is that "remember my choice" is a promise it never keeps.

So the same dialog is now reached two ways in every skin. Play honours what was
remembered and starts the game, and a control of its own reopens the dialog.
Modern and Vapor put a caret beside Play; Classic puts a button in the row over
the cover, which is where that skin keeps its actions.

The reopening control cannot simply raise the dialog. Play does two things
first that the dialog then depends on: it records which disc was asked for, and
it reads this game's bezel preference. A control that skipped both would offer
the previous game's disc and a stale bezel, so it has to do that work too.

Vapor carries its own copy of this page in its own repository and is out of
reach from here, as it is for the two tests either side of this one. It was
checked in a browser instead. A test that skips forever looks like coverage and
is worse than none.
"""
from __future__ import annotations

import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent

SURFACES = {
    "Modern (and NEON HORIZON through it)":
        ROOT / "frontend" / "src" / "views" / "emulation" / "EmulationGameDetail.vue",
    "Classic":
        ROOT / "frontend" / "src" / "layouts" / "ClassicGameDetail.vue",
}

# The one control that reopens the dialog, named the same in both skins so a
# reader who finds it in one knows what to grep for in the other.
HANDLER = "openDisplayOptions"


def _read(path: pathlib.Path) -> str:
    if not path.is_file():
        pytest.skip("drzewo frontendu nie jest obecne")
    return path.read_text(encoding="utf-8")


def _function(source: str, name: str) -> str:
    """The body of one top level function, brace matched.

    Counting braces rather than reading to the next blank line, because these
    functions contain both.
    """
    at = source.index(f"function {name}(")
    start = source.index("{", at)
    depth, i = 0, start
    while i < len(source):
        if source[i] == "{":
            depth += 1
        elif source[i] == "}":
            depth -= 1
            if depth == 0:
                return source[start:i + 1]
        i += 1
    raise AssertionError(f"nie znalazlem konca funkcji {name}")


@pytest.mark.parametrize("skin", sorted(SURFACES))
def test_the_dialog_can_be_reopened_after_the_choice_was_remembered(skin):
    """Without this there is no way back: no mode change and no bezel."""
    source = _read(SURFACES[skin])
    assert f"function {HANDLER}(" in source, (
        f"{skin}: brak sposobu na ponowne otwarcie okna wyboru trybu"
    )


@pytest.mark.parametrize("skin", sorted(SURFACES))
def test_the_control_is_wired_to_something_the_user_can_click(skin):
    """A handler nothing calls is the same as no handler."""
    source = _read(SURFACES[skin])
    template = source[:source.index("<script")]
    assert f"{HANDLER}(" in template, (
        f"{skin}: {HANDLER} istnieje, ale nic w szablonie go nie wola"
    )


@pytest.mark.parametrize("skin", sorted(SURFACES))
def test_the_control_says_what_it_does(skin):
    """Icon only buttons need a title, and the string for this one already
    exists in all eight languages, so no new key had to be invented."""
    source = _read(SURFACES[skin])
    template = source[:source.index("<script")]
    at = template.index(HANDLER + "(")
    around = template[max(0, at - 400):at + 200]
    assert "detail.choose_display" in around, (
        f"{skin}: przycisk otwierajacy okno nie ma etykiety detail.choose_display"
    )


@pytest.mark.parametrize("skin", sorted(SURFACES))
def test_play_honours_what_was_remembered(skin):
    """Classic asked every time, which made the checkbox a promise it never
    kept, and made the new control pointless: it would open what Play already
    opened."""
    source = _read(SURFACES[skin])
    body = _function(source, "requestPlay")
    assert "launchPlayer()" in body, (
        f"{skin}: requestPlay nigdy nie startuje gry wprost, wiec zapamietany "
        "tryb nic nie daje"
    )


@pytest.mark.parametrize("skin", sorted(SURFACES))
def test_reopening_forgets_which_disc_the_last_launch_asked_for(skin):
    """The per disc buttons route through the same dialog, so a control that
    only raised it would offer whatever disc was picked last time."""
    source = _read(SURFACES[skin])
    body = _function(source, HANDLER)
    assert "pendingDisk" in body, (
        f"{skin}: {HANDLER} nie zeruje wybranej plyty, wiec okno pokaze stara"
    )
    assert "pendingWholeSet" in body, (
        f"{skin}: {HANDLER} nie zeruje trybu calego kompletu"
    )


@pytest.mark.parametrize("skin", sorted(SURFACES))
def test_reopening_reads_this_games_bezel_setting(skin):
    """The bezel is stored per game. Raising the dialog without reading it
    shows the previous game's answer, and saving from there would overwrite
    this game's with it."""
    source = _read(SURFACES[skin])
    body = _function(source, HANDLER)
    assert "bezelKey" in body or "bezelEnabled" in body, (
        f"{skin}: {HANDLER} nie wczytuje ustawienia bezela dla tej gry"
    )


@pytest.mark.parametrize("skin", sorted(SURFACES))
def test_the_remembered_mode_is_still_shown_as_selected(skin):
    """Reopening to a default rather than to the current answer reads as the
    setting having been lost."""
    source = _read(SURFACES[skin])
    body = _function(source, HANDLER)
    assert re.search(r"pendingMode\.value\s*=", body), (
        f"{skin}: {HANDLER} nie ustawia zaznaczonego trybu w oknie"
    )
