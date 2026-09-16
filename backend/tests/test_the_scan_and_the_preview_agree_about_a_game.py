"""One question about a game, asked by both halves of the exclusions.

The scan decides whether to ADD a game; the settings screen previews which
games already here a pattern covers, and removes the ones confirmed. They have
to answer the same, or the feature does the opposite of what it says: a game
the preview removes and the scan does not exclude comes straight back on the
next scan, blank, with its metadata gone.

The two ask about different things - the scan holds a game's DIRECTORY, the
preview holds the file paths stored in the database - so agreement is a
property to be tested rather than something the shapes give for free. The
previous round tested it with folder patterns only, and every other shape a
person can type diverged:

    *.zip        every file matched, so the preview offered to delete the game;
                 the directory matched nothing, so the scan added it straight
                 back. Nearly every custom game is a zip.
    Thumbs.db    the same shape, the other way round.
    Junk         the same.

and on a real install the preview was worse than divergent, it was dead: the
paths in the database are relative to BASE_PATH (`games/CUSTOM/Title/x.zip`,
measured on the running server) while the root handed to the matcher was
absolute, so nothing was ever inside anything and every pattern covered nothing.

These tests build a real directory tree, ask the real scan rule about it, and
ask the real preview rule about the paths that scan would have stored.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from endpoints.library.libraries_router import _covered_here
from endpoints.library.library_router import _pending_game_dirs
from handler.filesystem.exclusions import is_excluded_dir

# Every shape the help text offers, in both layouts. A pattern only has to give
# the SAME answer on both sides here; which answer is the useful one is asked
# separately further down.
PATTERNS = [
    ["mods/"],
    ["_originals/"],
    ["Junk/"],
    ["*.zip"],
    ["Thumbs.db"],
    ["Junk"],
    ["windows/"],
    ["Shooter"],
    ["Junk/*"],
    ["*.zip", "mods/"],
]


def _write(games, rel):
    p = games / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b"x")


@pytest.fixture
def library(tmp_path, monkeypatch):
    """A library folder holding both layouts, and BASE_PATH pointed at it.

    The paths the preview reads are stored relative to BASE_PATH, so a test
    that does not move BASE_PATH is not testing what the server does.
    """
    games = tmp_path / "games" / "CUSTOM"
    _write(games, "Junk/game.zip")                 # title-first, one file
    _write(games, "Cool Game/windows/setup.exe")   # title-first with an os subfolder
    _write(games, "Cool Game/extras/manual.pdf")   # ...and a second container
    _write(games, "windows/Shooter/shooter.exe")   # os-first: windows/ is a container
    _write(games, "mods/thing.exe")                # a folder people exclude by name
    _write(games, "Real/real.exe")                 # a game that KEEPS a mods folder
    _write(games, "Real/mods/patch.exe")

    monkeypatch.setattr("config.BASE_PATH", str(tmp_path))

    cases = []
    for _slug, info in sorted(_pending_game_dirs(games).items()):
        dirs = [d[0] for d in info["dirs"]]
        files = sorted(
            f for d in dirs for f in Path(d).rglob("*") if f.is_file()
        )
        cases.append((
            info["title"], dirs,
            [os.path.relpath(str(f), str(tmp_path)) for f in files],
        ))
    return str(games), cases


def _covered(library, title, patterns, libraries=1):
    root, cases = library
    paths = next(c[2] for c in cases if c[0] == title)
    return _covered_here({"paths": paths, "libraries": libraries}, patterns, root)


@pytest.mark.parametrize("patterns", PATTERNS, ids=lambda p: ",".join(p))
def test_the_scan_and_the_preview_answer_the_same(library, patterns):
    root, cases = library
    for title, dirs, paths in cases:
        scan_skips = any(is_excluded_dir(d, patterns, root=root) for d in dirs)
        preview_covers = _covered_here({"paths": paths, "libraries": 1}, patterns, root)
        assert scan_skips == preview_covers, (
            f"{patterns} - skan mowi {scan_skips}, podglad mowi {preview_covers} "
            f"o grze {title!r}"
        )


def test_the_scan_finds_the_games_this_test_thinks_it_does(library):
    """A parity test over an empty list passes for the wrong reason."""
    _root, cases = library
    assert sorted(c[0] for c in cases) == [
        "Cool Game", "Junk", "Real", "Shooter", "mods",
    ]


def test_the_preview_reads_the_paths_the_database_actually_holds(library):
    """The regression that made this feature a no-op on the owner's server. The
    paths are relative to BASE_PATH and the root is absolute; a preview that
    cannot bridge that finds nothing, for every pattern, forever."""
    _root, cases = library
    stored = next(c[2] for c in cases if c[0] == "Junk")
    assert stored and not os.path.isabs(stored[0]), "test nie odtwarza ksztaltu z bazy"
    assert _covered(library, "Junk", ["Junk/"]), "podglad nie widzi gry, ktora skan by pominal"


def test_a_folder_pattern_covers_the_game_folder_it_names(library):
    """Not just agreement - the answer has to be the useful one."""
    _root, cases = library
    covered = [t for t, _d, _p in cases if _covered(library, t, ["mods/"])]
    assert covered == ["mods"], "wzorzec `mods/` ma zakrywac folder mods, i nic wiecej"


def test_a_game_that_keeps_a_mods_folder_is_left_alone(library):
    """`Real` has its own mods/ subfolder. Under the file-by-file rule a game
    whose every file happened to live in one was removed and re-added blank."""
    assert not _covered(library, "Real", ["mods/"])


def test_a_mask_does_not_quietly_empty_the_library(library):
    """`*.zip` is an ordinary thing to type - it is the example on the ROM side -
    and nearly every custom game is a zip. Under the file-by-file rule it
    covered them all, and the removal button offered to delete the library."""
    _root, cases = library
    covered = [t for t, _d, _p in cases if _covered(library, t, ["*.zip"])]
    assert covered == [], "maska plikowa zakryla cala gre"


def test_the_os_first_layout_is_covered_by_its_own_title(library):
    """`windows/Shooter` is one game, not a game called windows. Excluding it
    has to be possible by naming the title."""
    assert _covered(library, "Shooter", ["Shooter/"])
    assert not _covered(library, "Cool Game", ["Shooter/"])


def test_a_game_on_a_second_shelf_is_still_left_alone(library):
    """The caution that was already there, kept."""
    assert not _covered(library, "Junk", ["Junk/"], libraries=2)


def test_a_game_with_no_files_is_still_left_alone(library):
    root, _cases = library
    assert not _covered_here({"paths": [], "libraries": 1}, ["Junk/"], root)


def test_a_game_outside_this_library_is_left_alone(library):
    """A GOG game carried into the default library by its flag lives under
    games/GOG. A pattern saved on the Games library says nothing about it, and
    every game on the owner's server looks like this."""
    root, _cases = library
    assert not _covered_here(
        {"paths": ["games/GOG/Some Game/windows/some.zip"], "libraries": 1},
        ["Some Game/"], root,
    )


# ── The library does not have to live under BASE_PATH ────────────────────────
#
# `GD_GAMES_PATH` and `GD_BASE_PATH` are separate settings - utils/paths.py says
# so and test_allowed_paths pins it - so a library on another volume is a
# supported install, not an exotic one. The paths in the database are relative
# to BASE_PATH, and joining them onto it without normalising leaves
# `/data/../mnt/sda1/games/...`, which never starts with the library root. Every
# game then answered "outside this library" and the whole preview went quiet,
# while the scan - which asks about a path off the disk - excluded correctly.

def test_a_library_on_another_volume_is_still_read(tmp_path, monkeypatch):
    from endpoints.library.libraries_router import _game_folders

    base = tmp_path / "data"
    volume = tmp_path / "mnt" / "sda1" / "games"
    (volume / "CUSTOM" / "Junk").mkdir(parents=True)
    monkeypatch.setattr("config.BASE_PATH", str(base))

    stored = os.path.relpath(str(volume / "CUSTOM" / "Junk" / "game.zip"), str(base))
    assert stored.startswith(".."), "test nie odtwarza ukladu z osobnym wolumenem"

    folders = _game_folders([stored.replace("\\", "/")], str(volume / "CUSTOM"))
    assert folders == [str(volume / "CUSTOM" / "Junk").replace("\\", "/")], (
        "podglad nie widzi gry, bo sciezka nie zostala znormalizowana"
    )


def test_a_game_on_another_volume_but_outside_the_library_is_still_left_alone(
        tmp_path, monkeypatch):
    """The caution that made this worth doing carefully: normalising must not
    turn "somewhere else" into "inside"."""
    from endpoints.library.libraries_router import _game_folders

    base = tmp_path / "data"
    volume = tmp_path / "mnt" / "sda1" / "games"
    (volume / "OTHER" / "Thing").mkdir(parents=True)
    monkeypatch.setattr("config.BASE_PATH", str(base))

    stored = os.path.relpath(str(volume / "OTHER" / "Thing" / "x.zip"), str(base))
    assert _game_folders([stored.replace("\\", "/")], str(volume / "CUSTOM")) == []


# ── What the screen shows has to be something you can paste back ─────────────
#
# The list under the exclusions box exists so somebody can see what a pattern
# covers, and the obvious next move is to copy a line from it into the box. On
# the ROM side that works: `Rom.fs_path` is a full directory path, so the line
# is absolute and `_made_relative` trims it on save.
#
# On the library side it did not. `LibraryFile.file_path` is stored relative to
# BASE_PATH, so the screen showed `games/CUSTOM/Doom/doom.zip` - which is
# neither absolute (nothing trims it) nor relative to the LIBRARY (which is
# what the matcher compares against). Pasting it saved silently and covered
# nothing, for ever, with no warning anywhere.

def test_the_preview_shows_a_path_that_can_be_pasted_back(tmp_path, monkeypatch):
    from endpoints.library.libraries_router import _shown_path
    from handler.filesystem.exclusions import is_excluded, parse_patterns

    base = tmp_path / "data"
    root = base / "games" / "CUSTOM"
    monkeypatch.setattr("config.BASE_PATH", str(base))

    stored = "games/CUSTOM/Doom/doom.zip"
    shown = _shown_path(stored)
    assert os.path.isabs(shown), "ekran nadal pokazuje sciezke wzgledna"

    # And the round trip: what the screen shows, typed back into the box, has to
    # cover the file it was shown for.
    kept = parse_patterns(shown, root=str(root))
    assert kept, "wklejona linia zostala odrzucona"
    assert is_excluded(str(root / "Doom" / "doom.zip"), kept, root=str(root)), (
        "wzorzec wklejony z ekranu nie obejmuje pliku, dla ktorego byl pokazany"
    )


def test_a_path_that_is_already_absolute_is_left_alone(tmp_path, monkeypatch):
    """Belt and braces: a row that somehow holds a full path must not be
    joined onto BASE_PATH a second time."""
    from endpoints.library.libraries_router import _shown_path

    monkeypatch.setattr("config.BASE_PATH", str(tmp_path / "data"))
    absolute = str(tmp_path / "mnt" / "sda1" / "games" / "x.zip")
    assert _shown_path(absolute) == absolute


def test_an_empty_path_stays_empty(tmp_path, monkeypatch):
    from endpoints.library.libraries_router import _shown_path

    monkeypatch.setattr("config.BASE_PATH", str(tmp_path))
    assert _shown_path("") == ""
