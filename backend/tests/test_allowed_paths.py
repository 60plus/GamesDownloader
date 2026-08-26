"""Serving a file only from somewhere we meant to serve from.

The guard is old and its shape was right: resolve the path, refuse it unless it
sits under somewhere expected. What was wrong was the somewhere. Three routes
compared against the base directory alone, and the library does not have to
live there - the games, ROM and downloads directories are separate settings
that merely default to sitting under it.

So the interesting tests here are not the traversal ones. They are the two
supported layouts that the old guard answered 403 to, in a way that reads like
a permissions problem rather than a path one.
"""
from __future__ import annotations

import pytest

from utils import paths


def _point_at(monkeypatch, *, base, games=None, roms=None, downloads=None):
    monkeypatch.setattr(paths, "BASE_PATH", str(base))
    monkeypatch.setattr(paths, "GAMES_PATH", str(games or base))
    monkeypatch.setattr(paths, "ROMS_PATH", str(roms or base))
    monkeypatch.setattr(paths, "DOWNLOADS_PATH", str(downloads or base))


def test_an_ordinary_file_under_the_base_is_allowed(tmp_path, monkeypatch):
    base = tmp_path / "data"
    (base / "games").mkdir(parents=True)
    target = base / "games" / "game.zip"
    target.write_bytes(b"x")
    _point_at(monkeypatch, base=base)
    assert paths.is_within_allowed_roots(str(target))


def test_a_games_directory_symlinked_onto_another_disk(tmp_path, monkeypatch):
    """The failure this was written for.

    Resolving both sides moves the file outside the base, so the old guard
    refused every download on a perfectly ordinary layout: one big disk for the
    library, symlinked into place.
    """
    elsewhere = tmp_path / "disk2" / "games"
    elsewhere.mkdir(parents=True)
    target = elsewhere / "game.zip"
    target.write_bytes(b"x")

    base = tmp_path / "data"
    base.mkdir()
    try:
        (base / "games").symlink_to(elsewhere, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("this environment does not allow creating symlinks")

    _point_at(monkeypatch, base=base, games=base / "games")
    # Reached through the symlink, which is how the application builds the path.
    assert paths.is_within_allowed_roots(str(base / "games" / "game.zip"))


def test_a_games_directory_configured_somewhere_else_entirely(tmp_path, monkeypatch):
    """GD_GAMES_PATH is a setting, not a fixed corner of the base directory."""
    base = tmp_path / "data"
    base.mkdir()
    games = tmp_path / "mnt" / "big" / "games"
    games.mkdir(parents=True)
    target = games / "game.zip"
    target.write_bytes(b"x")

    _point_at(monkeypatch, base=base, games=games)
    assert paths.is_within_allowed_roots(str(target))


def test_something_outside_every_root_is_refused(tmp_path, monkeypatch):
    base = tmp_path / "data"
    base.mkdir()
    outsider = tmp_path / "etc" / "secret"
    outsider.mkdir(parents=True)
    (outsider / "passwd").write_bytes(b"x")

    _point_at(monkeypatch, base=base)
    assert not paths.is_within_allowed_roots(str(outsider / "passwd"))


def test_a_path_climbing_out_is_refused(tmp_path, monkeypatch):
    base = tmp_path / "data"
    base.mkdir()
    (tmp_path / "elsewhere").mkdir()
    _point_at(monkeypatch, base=base)
    assert not paths.is_within_allowed_roots(str(base / ".." / "elsewhere" / "x"))


def test_a_symlink_pointing_out_of_the_library_is_refused(tmp_path, monkeypatch):
    """The traversal the guard exists for, which resolving both sides catches.

    A file inside the library that is really a link to somewhere else is not
    inside the library, however contained its path looks.
    """
    base = tmp_path / "data"
    base.mkdir()
    secret = tmp_path / "etc" / "shadow"
    secret.parent.mkdir(parents=True)
    secret.write_bytes(b"x")
    try:
        (base / "escape.zip").symlink_to(secret)
    except (OSError, NotImplementedError):
        pytest.skip("this environment does not allow creating symlinks")

    _point_at(monkeypatch, base=base)
    assert not paths.is_within_allowed_roots(str(base / "escape.zip"))


def test_the_roots_are_deduplicated(tmp_path, monkeypatch):
    # By default every one of them sits under the base, and resolving them all
    # would otherwise list the same directory four times on every request.
    base = tmp_path / "data"
    base.mkdir()
    _point_at(monkeypatch, base=base)
    assert len(paths.allowed_roots()) == 1


def test_no_download_route_still_checks_only_the_base():
    """Three routes had their own copy of the old, narrower check."""
    import pathlib

    endpoints = pathlib.Path(__file__).resolve().parent.parent / "endpoints"
    offenders = []
    for path in endpoints.rglob("*.py"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "os.path.realpath(BASE_PATH)" in text:
            offenders.append(path.name)
    assert offenders == [], f"still comparing against the base alone: {offenders}"
