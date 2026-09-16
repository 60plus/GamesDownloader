"""The guard and the matcher have to be asked the same question.

`parse_patterns` refuses a pattern that would cover the whole tree, and it does
that by asking the real matcher rather than comparing against a list of shapes -
the file's own header records why: a list of shapes is a list somebody can step
around, and `*\\*` did exactly that.

Then absolute patterns were made to work. The screen beside the box lists full
absolute paths, so typing one is the obvious thing to do, and `is_excluded`
learned to strip the root off a pattern that names something inside what is
being scanned. That rewrite happens WITH a root. The guard asks WITHOUT one.

Two different questions, and the gap between them is the whole library:

    <root>/*   guard sees "/APPS/.../roms/nes/*", which matches neither probe,
               so it is saved. Matching sees it with the root stripped - a bare
               `*` - which matches every file and every directory.

Measured on the shipped code before this was written: saved, then `plik=True`
and `katalog=True` for every row on the platform. The preview then offers the
entire platform for removal and the apply route deletes each row, and deleting
a ROM row takes its savestates and play history by cascade - every account's.
That is the class of defect the owner has lost save games to three times.

The rewrite moved to where the root is actually known: saving. A pattern is
stored in the form it will be matched in, so the guard sees what the matcher
will see, and `<root>/*` is refused like the bare `*` it is.
"""

from __future__ import annotations

import pytest

from handler.filesystem.exclusions import is_excluded, is_excluded_dir, parse_patterns

ROOT = "/APPS/GamesDownloader/library/roms/nes"
ROM = ROOT + "/Super Mario.nes"
SUBDIR = ROOT + "/mods"


# ── What must never be saved ─────────────────────────────────────────────────

@pytest.mark.parametrize("raw", [
    ROOT + "/*",
    ROOT + "/**",
    ROOT + "/",
    ROOT,
    ROOT + "/*/*",
])
def test_a_pattern_that_becomes_everything_is_refused(raw):
    """Each of these reduces to "the whole library" once the root comes off."""
    assert parse_patterns(raw, root=ROOT) == [], (
        f"{raw!r} zapisany, a po przycieciu obejmuje cala platforme"
    )


@pytest.mark.parametrize("raw", [ROOT + "/*", ROOT + "/**", ROOT + "/"])
def test_and_so_covers_nothing(raw):
    """Belt and braces: even if one were saved, it must not sweep the tree."""
    kept = parse_patterns(raw, root=ROOT)
    assert not is_excluded(ROM, kept, root=ROOT)
    assert not is_excluded_dir(SUBDIR, kept, root=ROOT)


# ── What must still be saved, and still work ─────────────────────────────────

def test_an_absolute_path_inside_the_library_still_means_what_it_says():
    """The reason the rewrite exists. The screen lists absolute paths."""
    kept = parse_patterns(ROOT + "/mods/", root=ROOT)
    assert kept == ["mods/"], f"zapisano {kept}, a mialo zostac przyciete"
    assert is_excluded_dir(SUBDIR, kept, root=ROOT)
    assert is_excluded(SUBDIR + "/patch.ips", kept, root=ROOT)


def test_an_absolute_file_name_works_too():
    kept = parse_patterns(ROOT + "/Thumbs.db", root=ROOT)
    assert kept == ["Thumbs.db"]
    assert is_excluded(ROOT + "/Thumbs.db", kept, root=ROOT)


def test_the_relative_spelling_is_untouched():
    assert parse_patterns("mods/\n*.txt", root=ROOT) == ["mods/", "*.txt"]


def test_an_absolute_path_somewhere_else_is_left_alone():
    """It names something outside this library. Kept as typed, matches nothing
    here - which is honest, and is what it did before absolute paths were
    handled at all."""
    kept = parse_patterns("/etc/*", root=ROOT)
    assert kept == ["/etc/*"]
    assert not is_excluded(ROM, kept, root=ROOT)


def test_the_old_shapes_are_still_refused():
    """The guard's original job, unchanged."""
    for raw in ("*", "**", "*/*", "*\\*", "/"):
        assert parse_patterns(raw, root=ROOT) == [], raw
        assert parse_patterns(raw) == [], raw


def test_parsing_without_a_root_still_works():
    """Reading stored patterns back does not need one - they are stored in the
    form they are matched in."""
    assert parse_patterns("mods/\n# nota\n*.txt") == ["mods/", "*.txt"]


# ── And matching no longer rewrites, so a stored pattern cannot become `*` ────

def test_matching_does_not_rewrite_absolute_patterns_any_more():
    """The hole itself. A pattern stored before this release could be absolute;
    it matched nothing then and must match nothing now, rather than quietly
    becoming a bare `*` at match time."""
    stored = [ROOT + "/*"]          # as an older install could have saved it
    assert not is_excluded(ROM, stored, root=ROOT), (
        "przechowany wzorzec bezwzgledny nadal zwija sie do `*` przy dopasowaniu"
    )
    assert not is_excluded_dir(SUBDIR, stored, root=ROOT)


# ── Both save routes hand it the root ────────────────────────────────────────

@pytest.mark.parametrize("path,route", [
    ("endpoints/library/libraries_router.py", "set_library_exclusions"),
    ("endpoints/roms/roms_router.py", "set_platform_exclusions"),
])
def test_the_save_routes_pass_the_root(path, route):
    """Without it the guard is back to judging one thing and the matcher
    another."""
    import io
    import pathlib

    backend = pathlib.Path(__file__).resolve().parent.parent
    source = io.open(backend / path, encoding="utf-8").read()
    at = source.index(f"async def {route}(")
    body = source[at:source.index("\n@", at)]
    assert "parse_patterns(" in body
    assert "root=" in body, f"{route} nie podaje korzenia, wiec zapora nie widzi tego, co dopasowanie"
