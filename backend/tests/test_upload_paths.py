"""Where an upload is allowed to land on disk.

The os value reaching _dest_dir_for arrives from a request body, a multipart
form field and a catalogue entry - none of them trustworthy. It used to be
dropped into the path verbatim when it was not one of the four known values,
and pathlib does not normalise a path segment: ".." walks up, and an absolute
segment discards everything before it. That was an arbitrary file write, so
these tests pin the shape of the fix rather than any particular message.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from endpoints.library.upload_router import _OS_FOLDERS, _dest_dir_for, _sanitize

ESCAPES = [
    "../../../plugins/pwn",
    "..",
    "../",
    "/etc/cron.d",
    "/data/plugins/evil",
    "windows/../../..",
    "..\\..\\windows",
    "",
    ".",
]


@pytest.mark.parametrize("os_value", ESCAPES)
def test_an_unknown_os_is_refused(os_value):
    """Refused, not sanitised. Only four values name a folder."""
    with pytest.raises(ValueError):
        _dest_dir_for("Some Game", os_value, "game")


@pytest.mark.parametrize("os_value", sorted(_OS_FOLDERS))
def test_the_known_os_values_stay_inside_games_path(tmp_path, monkeypatch, os_value):
    # _dest_dir_for creates the folder as a side effect, so point GAMES_PATH at a
    # writable temp dir - the real /data does not exist on a CI runner.
    import endpoints.library.upload_router as ur
    monkeypatch.setattr(ur, "GAMES_PATH", str(tmp_path))
    dest = _dest_dir_for("Some Game", os_value, "game")
    root = Path(tmp_path).resolve()
    assert root in dest.resolve().parents or dest.resolve() == root


def test_extra_and_dlc_do_not_reopen_the_hole():
    """file_type overrides the folder, but the os is still validated first."""
    with pytest.raises(ValueError):
        _dest_dir_for("Some Game", "../../../plugins", "extra")
    with pytest.raises(ValueError):
        _dest_dir_for("Some Game", "/etc", "dlc")


def test_a_title_always_yields_a_directory_name():
    """An empty component silently vanishes from a path, so every game would
    share one folder and their files would overwrite each other."""
    for title in ("東方Project", "Дюна", "...", "///", "   ", "..."):
        assert _sanitize(title), f"{title!r} produced no directory name"


def test_the_same_title_always_gives_the_same_directory():
    assert _sanitize("東方Project") == _sanitize("東方Project")


def test_different_non_ascii_titles_do_not_collide():
    assert _sanitize("東方Project") != _sanitize("Дюна")


def test_traversal_in_a_title_is_still_neutralised():
    out = _sanitize("../../etc/passwd")
    assert ".." not in out
    assert not out.startswith(("/", "\\"))
