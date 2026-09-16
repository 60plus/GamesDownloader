"""The ROM metadata editor: what the cover grid offers, and whose media fills the tabs.

Two things the owner asked for on 2026-09-16.

The cover grid. PPE.pl answers a search with a title and no picture, so every
PPE.pl result was an empty tile - "ppe dalej sie pojawia na liscie bez okladki".
Measured on the live server before deciding: picking the ScreenScraper result
for Crash Bandicoot 2 brought PPE.pl's 2145-character Polish description and its
screenshots, because `all-media` asks every plugin for the ROM's own name
whatever result was clicked. The PPE.pl tile added an empty box and nothing to
the edit, so a plugin result without a picture stays out of the grid. It is
still listed in the Description tab, and the grid still offers such results
when nothing else is left to pick - a game only a plugin knows has to stay
pickable.

The media of a pick. `selectResult` asked `all-media` and wrote whatever came
back, and any answer ended the spinner. A pick with ScreenScraper and the
plugins behind it takes several seconds (5 to 11 measured on five PlayStation
games), a SteamGridDB pick comes back almost at once, so the earlier pick's
media could land under the later one and the tabs showed a game that was no
longer selected. Only the latest pick may fill the tabs or end the spinner.

These read the component's source, as the other editor tests here do: the
frontend has no test runner of its own.
"""

from __future__ import annotations

import io
import pathlib
import re

import pytest

BACKEND = pathlib.Path(__file__).resolve().parent.parent
PANEL = BACKEND.parent / "frontend" / "src" / "views" / "emulation" / "EmulationRomMetadataPanel.vue"


def _source() -> str:
    if not PANEL.is_file():
        pytest.skip("frontend tree not present")
    return io.open(PANEL, encoding="utf-8").read()


def _computed(source: str, name: str) -> str:
    at = source.index(f"const {name} = computed(")
    return source[at:source.index("\n})", at)]


def _function(source: str, name: str) -> str:
    at = source.index(f"async function {name}(")
    return source[at:source.index("\n}\n", at)]


# ── the cover grid ───────────────────────────────────────────────────────────

def test_a_plugin_result_without_a_picture_stays_out_of_the_cover_grid():
    body = _computed(_source(), "coverResults")
    assert re.search(
        r"ssResults\.value\.filter\(\s*r\s*=>\s*r\.source\s*!==\s*'plugin'\s*\|\|\s*!!r\.cover_url\s*\)",
        body,
    ), "coverResults does not leave out a plugin result that has no picture"


def test_the_grid_still_offers_them_when_nothing_else_is_left_to_pick():
    """THE LEGAL CASE: a game only a plugin knows must stay pickable."""
    body = _computed(_source(), "coverResults")
    assert re.search(r"return\s+(\w+)\.length\s*\?\s*\1\s*:\s*ssResults\.value", body), (
        "with only picture-less plugin results the grid would be empty and nothing could be picked"
    )


@pytest.mark.parametrize("name", ["filteredResults", "searchFilters"])
def test_the_grid_and_its_chips_are_built_from_what_the_grid_offers(name):
    """A chip counting a tile the grid does not draw is a chip that leads nowhere."""
    body = _computed(_source(), name)
    assert "coverResults.value" in body, f"{name} is not built from coverResults"
    assert "ssResults.value" not in body, f"{name} still reads every result, pictures or not"


def test_the_cover_grid_draws_the_filtered_results():
    source = _source()
    grid = source[source.index('class="mep-covers-grid" style="position:relative"'):]
    assert 'v-for="result in filteredResults"' in grid[:400]


def test_the_description_tab_still_lists_every_result():
    """PPE.pl is picked for its text: its row stays where the text is."""
    source = _source()
    tab = source[source.index("DESCRIPTION TAB"):source.index("DETAILS TAB")]
    assert 'v-for="result in ssResults"' in tab, (
        "the Description tab no longer lists every result"
    )


# ── the media of a pick ──────────────────────────────────────────────────────

def _pick_guard(source: str) -> tuple[str, str, str]:
    body = _function(source, "selectResult")
    m = re.search(r"const (\w+) = \+\+(\w+)", body)
    assert m, "selectResult does not number its media request"
    return body, m.group(1), m.group(2)


def test_each_pick_numbers_its_media_request():
    source = _source()
    _, _, counter = _pick_guard(source)
    assert re.search(rf"^let {counter} = 0$", source, re.M), (
        f"the request counter {counter} is not a module-level counter starting at 0"
    )


def test_only_the_latest_pick_writes_the_media():
    source = _source()
    body, request, counter = _pick_guard(source)
    lines = [ln.strip() for ln in body.splitlines() if ln.strip()]
    writes = [i for i, ln in enumerate(lines) if ln.startswith("allMedia.value =")]
    assert len(writes) == 2, "expected the answer and the failure to be the two writes"
    for i in writes:
        assert lines[i - 1] == f"if ({request} !== {counter}) return", (
            f"`{lines[i]}` is not guarded by the latest-pick check (line before: {lines[i - 1]!r})"
        )


def test_only_the_latest_pick_ends_the_spinner():
    source = _source()
    body, request, counter = _pick_guard(source)
    ends = [ln.strip() for ln in body.splitlines() if "mediaLoading.value = false" in ln]
    assert ends == [f"if ({request} === {counter}) mediaLoading.value = false"], (
        f"the spinner is ended by an answer that may not be the latest: {ends}"
    )
