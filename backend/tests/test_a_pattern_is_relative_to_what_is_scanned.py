"""A pattern describes the library, not the road to it.

Matching ran against the absolute path, so every directory above the library was
a segment a pattern could name. On a default install the road is
`/data/games/roms/{platform}/...`, which means `roms/`, `games/` and `data/` each
covered the entire library - and the guard against patterns that swallow
everything could not see it, because it probes with relative paths where those
words do not appear.

`roms/` is not a far-fetched thing to type. GD documents a `{platform}/roms/`
subfolder, so somebody excluding it writes exactly that, and gets a preview
offering to delete every ROM they own.

Patterns are therefore matched against the path RELATIVE to the thing being
scanned: the platform folder for a ROM platform, the library folder for a games
library. Which is what a person means when they type a pattern into a box that
belongs to one platform.
"""
from __future__ import annotations

import pytest

from handler.filesystem.exclusions import is_excluded, is_excluded_dir, parse_patterns

ROM = "/data/games/roms/amiga"
LIB = "/data/games/CUSTOM"


@pytest.mark.parametrize("pattern", ["roms/", "games/", "data/", "amiga/"])
def test_a_directory_on_the_road_to_the_library_covers_nothing(pattern):
    """Every one of these swallowed the whole library."""
    assert not is_excluded(f"{ROM}/Gra.lha", parse_patterns(pattern), root=ROM), (
        f"wzorzec {pattern!r} obejmuje cala biblioteke, bo nazywa katalog "
        f"lezacy NAD nia"
    )


def test_a_folder_inside_the_platform_still_works():
    """The thing patterns are for."""
    assert is_excluded(f"{ROM}/mods/pack.zip", ["mods/"], root=ROM)
    assert is_excluded_dir(f"{LIB}/mods", ["mods/"], root=LIB)


def test_the_structure_b_subfolder_can_be_named_deliberately():
    """`{platform}/roms/` is a documented layout, so somebody may genuinely want
    to exclude it - and now that is what typing `roms/` does, rather than
    covering the entire tree."""
    assert is_excluded(f"{ROM}/roms/Gra.lha", ["roms/"], root=ROM)
    assert not is_excluded(f"{ROM}/Gra.lha", ["roms/"], root=ROM)


def test_names_and_masks_are_unaffected():
    """They only ever looked at the last segment, so they were never wrong."""
    assert is_excluded(f"{ROM}/Thumbs.db", ["Thumbs.db"], root=ROM)
    assert is_excluded(f"{ROM}/notes.txt", ["*.txt"], root=ROM)
    assert not is_excluded(f"{ROM}/Gra.lha", ["*.txt"], root=ROM)


def test_a_path_outside_the_root_is_not_silently_matched():
    """If the two ever disagree about where the root is, the safe answer is to
    leave the file alone rather than to fall back to matching the whole
    absolute path - which is the behaviour this replaces."""
    assert not is_excluded("/somewhere/else/roms/Gra.lha", ["roms/"], root=ROM)


def test_without_a_root_nothing_changes_for_a_bare_name():
    """Callers that have no root - and the tests that predate this - keep the
    old behaviour for the shapes where it was never wrong."""
    assert is_excluded("roms/amiga/Thumbs.db", ["Thumbs.db"])
    assert is_excluded("roms/amiga/mods/x.lha", ["mods/"])


def test_both_scanners_pass_the_root():
    """A relative rule with an absolute path handed to it is the old bug with
    extra steps."""
    import io
    import pathlib

    backend = pathlib.Path(__file__).resolve().parent.parent
    for rel, call in (
        ("handler/filesystem/rom_scanner.py", "is_excluded("),
        ("endpoints/library/library_router.py", "is_excluded_dir("),
    ):
        source = io.open(backend / rel, encoding="utf-8").read()
        at = source.index(call, source.index("excludes"))
        window = source[at:at + 200]
        assert "root=" in window, f"{rel}: dopasowanie bez korzenia"
