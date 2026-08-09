"""Filenames for picked ROM media (endpoints.roms.roms_router).

This is the function behind the v1.0.25 regression: a picked background saved
under an extension taken from a whole proxy URL, whose slashes then became
directories, after which every later metadata save on that ROM failed. The
invariant that matters is the one asserted first: whatever the URL, the result
must be usable as a bare file extension.
"""
from __future__ import annotations

import pytest

from endpoints.roms.roms_router import _clear_media, _media_ext

URLS = [
    "/api/media/proxy/gdmp1|abcdefghijklmnop",          # opaque, carries no dot
    "https://cdn.example.com/art/cover.png",
    "https://cdn.example.com/art/cover.png?width=600",
    "https://cdn.example.com/art/cover.PNG#frag",
    "https://www.screenscraper.fr/image.php?gameid=1&media=box-2D",
    "https://cdn.example.com/no-extension-at-all",
    "https://cdn.example.com/dotted.name/art",          # dot in a directory only
    "",
]


@pytest.mark.parametrize("url", URLS)
def test_result_is_always_a_bare_extension(url):
    """No separator may survive, or the save path grows directories."""
    ext = _media_ext(url)
    assert ext, "an empty extension would leave the file without a suffix"
    assert ext.isalnum(), f"{ext!r} is not usable as a file extension"
    assert len(ext) <= 5


def test_proxy_url_falls_back_rather_than_swallowing_the_url():
    # The exact shape that produced a "background./api/media/proxy/" tree.
    assert _media_ext("/api/media/proxy/gdmp1|abcdefghijklmnop") == "jpg"


def test_real_extension_is_kept_and_lowercased():
    assert _media_ext("https://cdn.example.com/art/cover.PNG") == "png"


def test_query_string_is_not_part_of_the_extension():
    assert _media_ext("https://cdn.example.com/art/cover.png?width=600") == "png"


def test_dot_in_a_directory_does_not_count():
    """Only the last path segment may supply the extension."""
    assert _media_ext("https://cdn.example.com/dotted.name/art") == "jpg"


def test_clear_media_removes_only_files_of_that_slot(tmp_path):
    (tmp_path / "background.png").write_bytes(b"x")
    (tmp_path / "background.webp").write_bytes(b"x")
    (tmp_path / "cover.png").write_bytes(b"x")

    _clear_media(tmp_path, "background")

    assert not (tmp_path / "background.png").exists()
    assert not (tmp_path / "background.webp").exists()
    assert (tmp_path / "cover.png").exists(), "another slot must be left alone"


def test_clear_media_steps_over_a_directory(tmp_path):
    """The wedge that made the regression permanent.

    A directory left by the bug used to be handed to unlink(), which raised
    IsADirectoryError and failed the whole save. Clearing must survive it.
    """
    (tmp_path / "background.leftover").mkdir()
    (tmp_path / "background.png").write_bytes(b"x")

    _clear_media(tmp_path, "background")

    assert not (tmp_path / "background.png").exists()
    assert (tmp_path / "background.leftover").is_dir()
