"""A bezel nobody has answered for yet is shown, not hidden.

The bezel is decorative art with a hole in the middle, scraped alongside the
cover, and whether to lay it over the picture is remembered per game under
gd3_bezel_<id>. Reading that answer with `=== '1'` gives false for a game that
has no answer yet, so a bezel that was scraped, stored and served stayed
invisible until somebody found the toggle and ticked it.

Modern was the surface that gave this away: its state starts as ref(true) and
the line above the read says "default on", while the read itself says
otherwise. Classic and Vapor were at least honest about it, saying "default
off" and meaning it.

Reading it as "not switched off" instead settles it the other way, which is
what the scraped artwork implies: the answer only exists once someone gives it,
and until then the art is shown.

Couch Mode is deliberately left alone. Its bezel is a global preference under a
key of its own, gd3_couch_bezel, with a visible on/off row in the menu, so its
default is a choice the user can already see and change.

Vapor carries its own copy of this page in its own repository and is out of
reach from here. It was changed the same way and checked in a browser.
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

# Every place that turns the stored answer back into a yes or a no.
READ = re.compile(r"localStorage\.getItem\(\s*bezelKey\([^)]*\)\s*\)\s*(===|!==)\s*'([01])'")


def _read(path: pathlib.Path) -> str:
    if not path.is_file():
        pytest.skip("drzewo frontendu nie jest obecne")
    return path.read_text(encoding="utf-8")


def _reads(source: str) -> list[str]:
    """Both the inline reads and the two step ones, which assign to a local
    first and compare on the next line."""
    out = [m.group(0) for m in READ.finditer(source)]
    for m in re.finditer(r"bSaved\s*(===|!==)\s*'([01])'", source):
        out.append(m.group(0))
    return out


@pytest.mark.parametrize("skin", sorted(SURFACES))
def test_the_stored_answer_is_read_somewhere(skin):
    """Guards the two tests below: a rename would otherwise make them pass by
    finding nothing to complain about."""
    assert _reads(_read(SURFACES[skin])), (
        f"{skin}: nie znalazlem odczytu zapamietanej ramki, test przestal cokolwiek pilnowac"
    )


@pytest.mark.parametrize("skin", sorted(SURFACES))
def test_a_game_never_answered_for_still_shows_its_bezel(skin):
    """`=== '1'` reads a missing answer as no. The scraped art is then served
    and never seen."""
    for read in _reads(_read(SURFACES[skin])):
        assert "!== '0'" in read, (
            f"{skin}: {read} chowa ramke gry, ktorej nikt jeszcze nie odpowiedzial"
        )


@pytest.mark.parametrize("skin", sorted(SURFACES))
def test_the_starting_state_agrees_with_the_stored_one(skin):
    """The ref is what the dialog shows before any game is loaded. Modern said
    true and read false, which is how the two drifted apart unnoticed."""
    source = _read(SURFACES[skin])
    assert re.search(r"bezelEnabled\s*=\s*ref\(true\)", source), (
        f"{skin}: stan poczatkowy ramki nie zgadza sie z domyslka odczytu"
    )
