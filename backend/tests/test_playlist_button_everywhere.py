"""The playlist button has to exist on every ROM page this repository owns.

This project's recurring failure is not a broken feature, it is a feature that
only exists in one skin. RomDownloader's source screen was the last one: fixed
in the core, invisible to anyone using a theme, and nobody found out until a
user asked why their setting did nothing.

There are three ROM detail surfaces. Two of them are here:

  * Modern - and NEON HORIZON through it, because NH has no detail page of its
    own and renders the core's (NeonHorizonLayout.vue: "All other pages
    (detail, profile, settings) use standard router-view").
  * Classic.

The third, Vapor, intercepts the route with its own component and lives in a
separate repository, so this test cannot reach it and deliberately does not
pretend to. A test that skips forever looks like coverage and is worse than
none. Vapor is covered by its own release check.

There is no runner for .vue files, so this reads them. That is worth doing for
a guarantee whose failure mode is silence rather than an error.
"""
from __future__ import annotations

import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
SURFACES = {
    "Modern (and NEON HORIZON through it)":
        ROOT / "frontend" / "src" / "views" / "emulation" / "EmulationGameDetail.vue",
    "Classic":
        ROOT / "frontend" / "src" / "layouts" / "ClassicGameDetail.vue",
}


def _read(path: pathlib.Path) -> str:
    if not path.is_file():
        pytest.skip("drzewo frontendu nie jest obecne")
    return path.read_text(encoding="utf-8")


@pytest.mark.parametrize("skin", sorted(SURFACES))
def test_every_rom_page_offers_to_write_the_playlist(skin):
    source = _read(SURFACES[skin])
    assert "writePlaylist" in source, f"{skin}: brak obslugi przycisku"
    assert "/playlist" in source, f"{skin}: nie wola trasy zapisujacej playliste"


@pytest.mark.parametrize("skin", sorted(SURFACES))
def test_the_offer_is_only_made_when_there_is_no_playlist_yet(skin):
    """Otherwise the button invites you to overwrite a playlist that may have
    come down with the discs, or been written by hand on a handheld. The server
    reports one in `playlist`, so the button has to consult it."""
    source = _read(SURFACES[skin])
    # `playlist` is the field the ROM payload carries for exactly this. A page
    # that offers the button unconditionally has no reason to mention it, so
    # its absence is the tell.
    assert ".playlist" in source, (
        f"{skin}: przycisk nie sprawdza, czy playlista juz istnieje"
    )


@pytest.mark.parametrize("skin", sorted(SURFACES))
def test_play_loads_the_whole_title_when_it_is_split_across_discs(skin):
    """Play means the game, not the disc the library row happens to name.

    This was a second button for a while, sitting beside Play with the size on
    it. Nobody wants disc one of four on its own, so the second button was the
    one anybody would press, and the page had grown a control for every way of
    starting the same game. The per-disc buttons stay, because starting from a
    later disc is a real thing to want on the sets that put a level editor or
    a second scenario there.
    """
    source = _read(SURFACES[skin])
    assert "set_loads_whole" in source, f"{skin}: Graj nie sprawdza, czy komplet wejdzie"
    assert "'discs', 'all'" in source or '"discs", "all"' in source, (
        f"{skin}: Graj nie prosi playera o caly komplet"
    )


@pytest.mark.parametrize("skin", sorted(SURFACES))
def test_a_split_title_is_weighed_whole(skin):
    """The row names disc one, so printing its size answered a question nobody
    asked: a four disc PlayStation set read as 480 MB when it is nearer 1.5 GB.
    Reported by the user."""
    source = _read(SURFACES[skin])
    assert "titleBytes" in source, f"{skin}: rozmiar nie sumuje plyt"
    assert "diskSetBytes" in source, f"{skin}: brak sumy wagi kompletu"
