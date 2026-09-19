"""The game page's media row moves one whole picture per click, as Classic's does.

Reported by the owner on Final Fantasy VI (2026-09-18), in Modern and in Neon
Horizon, which opens a ROM through the same page: pressing the arrow moved the
row a sliver, the first picture cut off on the left and a strip of the next one
showing on the right. Measured on the page: 42 pixels.

Two faults, both in `slideTo`:

  Where a picture starts was read from `offsetLeft`, which counts from the
  nearest positioned ancestor - the row's wrapper, which also holds the left
  arrow and the gap after it. Every stop was off by that much.

  How far the row may go was counted in screenshots, and the row holds the
  trailer's picture as well. With a trailer and three screenshots the arrow was
  lit and the stop it asked for was clamped back to the first, so all a click
  did was the 42 pixels.
"""
from __future__ import annotations

import io
import pathlib
import re

PAGE = (pathlib.Path(__file__).resolve().parent.parent.parent
        / "frontend" / "src" / "views" / "emulation" / "EmulationGameDetail.vue")


def _slide_to() -> str:
    source = io.open(PAGE, encoding="utf-8").read()
    at = source.index("function slideTo(")
    return source[at:source.index("\n}\n", at)]


def test_the_last_stop_counts_every_picture_in_the_row():
    body = _slide_to()
    assert "carouselSlides.value.length" in body, (
        "koniec karuzeli liczony bez kafelka wideo"
    )
    assert "screenshots" not in body


def test_a_stop_is_measured_from_the_first_picture_not_the_arrow():
    body = _slide_to()
    assert re.search(r"offsetLeft\s*-\s*first\.offsetLeft", body), (
        "przesuniecie liczone od krawedzi paska ze strzalka, nie od pierwszego obrazka"
    )
    assert "offsetLeft - 2" not in body
