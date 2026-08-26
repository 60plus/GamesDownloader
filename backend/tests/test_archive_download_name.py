"""The name on a multi-file download, when the game is not called something Latin.

HTTP headers are latin-1. `_safe_download_name` keeps anything `str.isalnum()`
accepts, and that is true of every letter in every script, so a Japanese or
Cyrillic or Greek title came through it untouched and then went straight into
the header - where encoding it raised inside the server and the download
answered 500 instead of a file.

The helper that solves this was already in the tree, one import away, with its
own tests. It just was not being used here.
"""
from __future__ import annotations

import pytest

from endpoints.roms.roms_router import _safe_download_name
from utils.ranged_file import content_disposition


def _header_for(title: str) -> str:
    """What the archive route builds, by the same two calls it makes."""
    return content_disposition(_safe_download_name(title) + ".zip")


@pytest.mark.parametrize("title", [
    "ときめきメモリアル",          # Japanese
    "Тетрис",                      # Cyrillic
    "Ελληνικά",                    # Greek
    "Pokémon Édition Rouge",       # Latin with accents
    "海腹川背",
])
def test_a_title_outside_latin_1_does_not_take_the_download_down(title):
    header = _header_for(title)
    # The whole failure was here: this raised, inside the server, after the
    # response had been decided.
    header.encode("latin-1")


@pytest.mark.parametrize("title", ["ときめきメモリアル", "Тетрис"])
def test_and_the_real_name_still_travels(title):
    """Refusing to crash by throwing the name away would be its own bug: the
    file would arrive called "download.zip" and nothing would say which game."""
    from urllib.parse import quote

    header = _header_for(title)
    assert f"filename*=UTF-8''{quote(title, safe='')}" in header
    # With an ASCII fallback that is still a zip, for whatever cannot read that.
    assert 'filename="download.zip"' in header


def test_an_ordinary_title_is_unchanged():
    header = _header_for("Final Fantasy VII (Disc 1)")
    assert 'filename="Final Fantasy VII (Disc 1).zip"' in header
    header.encode("latin-1")


def test_a_title_of_nothing_usable_still_names_the_file():
    assert 'filename="disks.zip"' in _header_for("///")


def test_the_quote_that_would_end_the_header_early_is_gone():
    """A name carrying a double quote could otherwise close the filename and
    let whatever follows it read as another header parameter."""
    header = _header_for('Game" ; evil=1')
    ascii_part = header.split("filename*=")[0]
    assert ascii_part.count('"') == 2
