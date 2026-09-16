"""Telling a scanner never to look at something.

There was no way to say "never scan this path", so a stray file - a mod folder
kept beside the ROMs, a manual, an editor's own working copy - was picked up and
reported as a game every single scan, forever. Deleting it from the library did
nothing: the next scan found the file again and put it straight back.

Patterns live per library and per platform rather than in one global list. Both
are the same thing from the scanner's point of view - a folder that gets walked -
and the case that motivated it is local: a modding folder that belongs beside the
Amiga ROMs and nowhere else.

WHAT A PATTERN MUST NOT DO IS HIDE A GAME BEHIND SOMEBODY'S BACK. A scanner skips
what it is told to skip, and a file that is skipped looks exactly like a file that
was deleted - so the obvious implementation marks half a library missing the
moment somebody saves a slightly wrong pattern. That is why the rows that already
exist are left completely alone, and why applying a pattern to them is a separate,
deliberate act with the list shown first.
"""
from __future__ import annotations

import pytest

from handler.filesystem.exclusions import is_excluded, parse_patterns


# ── Reading what somebody typed ──────────────────────────────────────────────

def test_one_pattern_per_line():
    assert parse_patterns("*.txt\n_originals/") == ["*.txt", "_originals/"]


def test_blank_lines_and_spacing_are_forgiven():
    assert parse_patterns("  *.txt  \n\n\n  _originals/\n") == ["*.txt", "_originals/"]


def test_a_comment_is_not_a_pattern():
    """People annotate these lists, and a line beginning with # matching a file
    literally called "#something" is not what anybody meant."""
    assert parse_patterns("# smieci z windowsa\nThumbs.db") == ["Thumbs.db"]


@pytest.mark.parametrize("raw", [None, "", "   ", "\n\n"])
def test_nothing_configured_is_an_empty_list_not_a_match_everything(raw):
    """The failure that would empty a library on the first save."""
    assert parse_patterns(raw) == []


# ── Matching ─────────────────────────────────────────────────────────────────

def test_a_plain_name_matches_that_file_anywhere_underneath():
    assert is_excluded("roms/amiga/Thumbs.db", ["Thumbs.db"])
    assert is_excluded("roms/amiga/sub/Thumbs.db", ["Thumbs.db"])


def test_a_glob_matches_by_extension():
    assert is_excluded("roms/amiga/readme.txt", ["*.txt"])
    assert not is_excluded("roms/amiga/game.lha", ["*.txt"])


def test_a_folder_pattern_excludes_everything_inside_it():
    """The case this exists for: a directory kept beside the ROMs that is not
    ROMs. Naming it should not require naming every file in it."""
    assert is_excluded("roms/amiga/_originals/game.lha", ["_originals/"])
    assert is_excluded("roms/amiga/mods/deep/thing.lha", ["mods/"])


def test_a_folder_pattern_does_not_match_a_file_of_that_name():
    assert not is_excluded("roms/amiga/mods", ["mods/"])


def test_matching_ignores_case():
    """Names arrive from whatever wrote them, and half the strays in a real
    library came off a Windows machine."""
    assert is_excluded("roms/amiga/THUMBS.DB", ["thumbs.db"])


def test_a_pattern_matches_a_whole_path_when_it_looks_like_one():
    assert is_excluded("roms/amiga/extra/manual.pdf", ["amiga/extra/*"])
    assert not is_excluded("roms/snes/extra/manual.pdf", ["amiga/extra/*"])


def test_an_empty_pattern_list_excludes_nothing():
    assert not is_excluded("roms/amiga/anything.lha", [])


def test_a_pattern_that_is_only_a_slash_is_ignored():
    """It would otherwise read as "every folder", which is the whole library."""
    assert not is_excluded("roms/amiga/game.lha", ["/"])


@pytest.mark.parametrize("pattern", ["*", "**", "*/*"])
def test_a_pattern_that_would_swallow_everything_is_refused(pattern):
    """Saving one of these is never what somebody meant, and the cost of being
    wrong is the whole library going quiet. They are dropped when read rather
    than obeyed."""
    assert parse_patterns(pattern) == []


# ── What the scanners are allowed to do with a match ─────────────────────────
#
# The matching above is the easy half. This is the half that can empty a
# library: a skipped file looks exactly like a deleted one, so a scanner that
# simply stops seeing a path marks that part of the library missing the moment
# somebody saves a slightly wrong pattern.

import io as _io
import pathlib as _pathlib

_BACKEND = _pathlib.Path(__file__).resolve().parent.parent
_SCANNER = _BACKEND / "handler" / "filesystem" / "rom_scanner.py"


def _scanner_source() -> str:
    return _io.open(_SCANNER, encoding="utf-8").read()


def test_the_rom_scanner_asks_about_exclusions():
    source = _scanner_source()
    assert "is_excluded" in source, "skaner ROM-ow nie pyta o wykluczenia"
    assert "scan_exclude" in source, "skaner nie czyta wzorcow platformy"


def test_a_match_only_stops_something_being_added():
    """The decision has to sit AFTER the row lookup, not before it. Filtering
    the directory listing instead would mean an excluded file that already has
    a row is never seen by the scan, so the row is left marked missing - which
    is the library quietly losing games, the exact thing the owner said must not
    happen without being asked.
    """
    source = _scanner_source()
    lookup = source.index("existing = await rom_handler.get_by_fs_name")
    decision = source.index("is_excluded(", lookup - 4000)
    assert decision > lookup, (
        "wykluczenie sprawdzane przed wyszukaniem wiersza, wiec istniejaca gra "
        "zostanie oznaczona jako zaginiona"
    )


def test_an_excluded_file_that_already_has_a_row_is_left_completely_alone():
    """Not skipped either: skipping is what marks it missing. It goes through
    the normal path, exactly as before the feature existed."""
    source = _scanner_source()
    at = source.index("is_excluded(", source.index("existing = await rom_handler.get_by_fs_name"))
    # Both directions: the guard sits on the same condition as the call, and on
    # its left. A window looking only forwards misses it entirely, which is how
    # the first version of this test failed against correct code.
    window = source[at - 200:at + 200]
    assert "existing is None" in window, (
        "wykluczenie dziala tez na wiersze, ktore juz istnieja"
    )


_LIBRARY = _BACKEND / "endpoints" / "library" / "library_router.py"


def test_the_games_scanner_asks_too():
    """The plan said both scanners consult these, and it is the same rule: a
    stray folder sitting beside the games is reported forever otherwise."""
    source = _io.open(_LIBRARY, encoding="utf-8").read()
    assert "is_excluded" in source, "skaner gier nie pyta o wykluczenia"
    assert "scan_exclude" in source, "skaner gier nie czyta wzorcow biblioteki"


def test_the_games_scanner_also_only_declines_new_ones():
    source = _io.open(_LIBRARY, encoding="utf-8").read()
    lookup = source.index("existing = await _lib.get_by_slug(slug)")
    # `is_excluded_dir` since the scan started asking about the game's folder as
    # a folder; the rule being pinned here is unchanged and is about WHERE the
    # decision sits, not what it is called.
    decision = source.index("is_excluded_dir(", lookup)
    assert "not existing" in source[lookup:decision], (
        "wykluczenie w skanerze gier dziala tez na gry, ktore juz sa"
    )


# ── Saving them, and applying them to what is already here ───────────────────

_ROMS = _BACKEND / "endpoints" / "roms" / "roms_router.py"


def _route_scopes(source: str, verb: str, path: str) -> set[str]:
    import re as _re
    m = _re.search(
        r'@protected_route\(router\.' + verb + r',\s*"' + _re.escape(path)
        + r'",\s*scopes=\[([^\]]*)\]', source)
    assert m, f"nie znalazlem trasy {verb.upper()} {path}"
    return {x.strip().split(".")[-1] for x in m.group(1).split(",") if x.strip()}


def test_patterns_are_saved_through_a_route_that_does_only_that():
    """Rather than a field on the general platform PATCH, which also writes the
    display name: a request carrying one would silently clear the other."""
    source = _io.open(_ROMS, encoding="utf-8").read()
    assert _route_scopes(source, "put", "/platforms/{slug}/exclusions") == {"PLATFORMS_WRITE"}


def test_there_is_a_preview_before_anything_is_removed():
    """The owner's condition: nothing already in the library changes until it is
    asked for, and the list is shown first."""
    source = _io.open(_ROMS, encoding="utf-8").read()
    assert _route_scopes(source, "get", "/platforms/{slug}/exclusions/preview") == {"PLATFORMS_WRITE"}


def test_applying_is_a_separate_act_from_saving():
    source = _io.open(_ROMS, encoding="utf-8").read()
    assert _route_scopes(source, "post", "/platforms/{slug}/exclusions/apply") == {"ROMS_WRITE"}


def test_applying_is_admin_only_even_though_saving_is_not():
    """Saving a pattern changes what a future scan adds and is reversible by
    deleting the line. Applying one deletes rows, with the saves and play
    history that hang off them, so it asks for the permission every other
    destructive ROM route asks for."""
    source = _io.open(_ROMS, encoding="utf-8").read()
    assert "ROMS_WRITE" in _route_scopes(source, "post", "/platforms/{slug}/exclusions/apply")


def test_the_preview_and_the_apply_agree_on_what_matches():
    """Two lists built by two rules is how somebody ends up confirming one thing
    and losing another."""
    source = _io.open(_ROMS, encoding="utf-8").read()
    start = source.index('"/platforms/{slug}/exclusions/preview"')
    end = source.index("\n@protected_route", source.index('"/platforms/{slug}/exclusions/apply"'))
    block = source[start:end]
    assert block.count("_excluded_rows(") >= 2, (
        "podglad i zastosowanie licza dopasowania osobno"
    )


# -- Reading back what is saved, cheaply -------------------------------------
#
# The screen has to show what is already saved before somebody edits it, and the
# only route that returned the patterns was the preview - which reads every row
# of the platform to work out what they match. Opening a settings screen must
# not walk a twenty thousand ROM table, so reading the patterns is its own
# route, and it is asked for the same permission as writing them.
#
# It also keeps the preview honest. The preview reports what the SAVED patterns
# cover, so the screen can only offer it once what is typed matches what is
# saved - and it can only know that if it can read what is saved.

import asyncio as _asyncio
import types as _types


class _FakeRequest:
    """Enough of a request for a route to run: who is asking, and with what."""

    def __init__(self, scopes):
        self.state = _types.SimpleNamespace(user=object(), scopes=set(scopes))


def _run(coro):
    return _asyncio.new_event_loop().run_until_complete(coro)


def test_reading_the_patterns_back_does_not_touch_the_rom_table(monkeypatch):
    """Cheap enough to run when a settings screen opens."""
    import endpoints.roms.roms_router as rr
    from handler.auth.scopes import Scope

    platform = _types.SimpleNamespace(id=7, scan_exclude="mods/\n*.txt")
    monkeypatch.setattr(rr.rom_platform_handler, "get_by_slug",
                        _fake_async(platform))

    def _explode(*a, **k):
        raise AssertionError("czytanie wzorcow siegnelo po wiersze ROM-ow")

    monkeypatch.setattr(rr.rom_handler, "all_for_platform", _explode)

    got = _run(rr.get_platform_exclusions(
        _FakeRequest({Scope.PLATFORMS_WRITE}), "amiga"))
    assert got["patterns"] == ["mods/", "*.txt"]


def test_a_platform_with_nothing_saved_reads_as_an_empty_list():
    """Not None, and not a one-line list holding an empty string: the screen
    puts this straight into a textarea."""
    import endpoints.roms.roms_router as rr
    from handler.auth.scopes import Scope

    import pytest as _pytest

    for raw in (None, "", "\n\n"):
        platform = _types.SimpleNamespace(id=7, scan_exclude=raw)
        with _pytest.MonkeyPatch.context() as mp:
            mp.setattr(rr.rom_platform_handler, "get_by_slug", _fake_async(platform))
            got = _run(rr.get_platform_exclusions(
                _FakeRequest({Scope.PLATFORMS_WRITE}), "amiga"))
        assert got["patterns"] == []


def test_whoever_may_write_the_patterns_may_read_them():
    """Recorded on the route by the decorator, so this is the rule the server
    enforces rather than the text of a source file."""
    import endpoints.roms.roms_router as rr
    from handler.auth.scopes import Scope

    assert rr.get_platform_exclusions.required_scopes == (Scope.PLATFORMS_WRITE,)


def test_a_library_reads_its_patterns_back_the_same_way(monkeypatch):
    import endpoints.library.libraries_router as lr
    from handler.auth.scopes import Scope

    library = _types.SimpleNamespace(id=3, scan_exclude="_originals/")
    monkeypatch.setattr(lr.library_registry_handler, "get_by_slug",
                        _fake_async(library))
    got = _run(lr.get_library_exclusions(
        _FakeRequest({Scope.SETTINGS_WRITE}), "pc"))
    assert got["patterns"] == ["_originals/"]
    assert lr.get_library_exclusions.required_scopes == (Scope.SETTINGS_WRITE,)


def _fake_async(value):
    async def _f(*a, **k):
        return value
    return _f


def test_asking_about_a_platform_that_is_not_there_is_a_404(monkeypatch):
    """The same answer the write route gives, rather than an empty list, which
    would read as "this platform has no patterns"."""
    import endpoints.roms.roms_router as rr
    from fastapi import HTTPException
    from handler.auth.scopes import Scope

    import pytest as _pytest

    monkeypatch.setattr(rr.rom_platform_handler, "get_by_slug", _fake_async(None))
    with _pytest.raises(HTTPException) as err:
        _run(rr.get_platform_exclusions(_FakeRequest({Scope.PLATFORMS_WRITE}), "zx"))
    assert err.value.status_code == 404


# -- Only where a scanner actually walks -------------------------------------
#
# Not every library is a folder somebody scans. GOG has its own sync pipeline,
# Emulation derives its games from the ROM table, and a collections container
# holds groupings rather than files - none of them ever read these patterns.
#
# Offering the field on one of those would be a setting that saves cleanly and
# then does nothing, which is worse than not offering it: the person who typed
# the pattern goes away believing the stray folder is handled.
#
# The rule lives in ONE place. The scan and the route asking each other the same
# question two ways is how one of them ends up out of date.


def test_the_rule_for_what_gets_scanned_is_written_once():
    from handler.database.library_registry_handler import is_folder_scanned

    scanned = _types.SimpleNamespace(kind="custom_lib", storage_folder="KIDS")
    builtin = _types.SimpleNamespace(kind="custom", storage_folder="CUSTOM")
    assert is_folder_scanned(scanned)
    assert is_folder_scanned(builtin)


@pytest.mark.parametrize("kind", ["gog", "emulation", "couch", "collections"])
def test_a_library_nobody_walks_is_not_folder_scanned(kind):
    from handler.database.library_registry_handler import is_folder_scanned

    assert not is_folder_scanned(
        _types.SimpleNamespace(kind=kind, storage_folder="SOMETHING"))


def test_a_folder_library_without_a_folder_is_not_scanned_either():
    """`custom_lib` is created before its folder is chosen, and the scan skips
    one with no storage_folder. The field has to skip it for the same reason."""
    from handler.database.library_registry_handler import is_folder_scanned

    assert not is_folder_scanned(
        _types.SimpleNamespace(kind="custom_lib", storage_folder=None))


def test_the_games_scan_asks_that_one_question_rather_than_its_own():
    source = _io.open(_LIBRARY, encoding="utf-8").read()
    assert "is_folder_scanned" in source, (
        "skan gier ma wlasna kopie reguly, wiec obie moga sie rozjechac"
    )


def test_patterns_cannot_be_saved_where_nothing_would_read_them(monkeypatch):
    import endpoints.library.libraries_router as lr
    from fastapi import HTTPException
    from handler.auth.scopes import Scope

    gog = _types.SimpleNamespace(id=1, kind="gog", storage_folder=None,
                                 scan_exclude=None)
    monkeypatch.setattr(lr.library_registry_handler, "get_by_slug", _fake_async(gog))

    def _explode(*a, **k):
        raise AssertionError("zapisano wzorzec do biblioteki, ktorej nikt nie skanuje")

    monkeypatch.setattr(lr.library_registry_handler, "set_scan_exclude", _explode)

    with pytest.raises(HTTPException) as err:
        _run(lr.set_library_exclusions(
            _FakeRequest({Scope.SETTINGS_WRITE}), "gog",
            lr.LibraryExclusionsBody(patterns="mods/")))
    assert err.value.status_code == 400


def test_clearing_patterns_is_allowed_even_where_saving_them_is_not(monkeypatch):
    """A library can STOP being scanned - its folder is taken away, or its kind
    changes - with patterns already saved on it. A guard that refuses every
    write would leave those saved and unreachable, which is a worse trap than
    the one it prevents. Refusing to add a pattern nobody would read does not
    mean refusing to take one away.
    """
    import endpoints.library.libraries_router as lr
    from handler.auth.scopes import Scope

    stranded = _types.SimpleNamespace(id=4, kind="custom_lib", storage_folder=None,
                                      scan_exclude="mods/")
    wrote = []
    monkeypatch.setattr(lr.library_registry_handler, "get_by_slug", _fake_async(stranded))

    async def _record(slug, patterns, **k):
        wrote.append((slug, patterns))

    monkeypatch.setattr(lr.library_registry_handler, "set_scan_exclude", _record)

    got = _run(lr.set_library_exclusions(
        _FakeRequest({Scope.SETTINGS_WRITE}), "kids",
        lr.LibraryExclusionsBody(patterns="")))
    assert got["patterns"] == []
    assert wrote == [("kids", None)], "wyczyszczenie wzorcow nie doszlo do bazy"


# ── Nothing is removed that was not on the list ──────────────────────────────
#
# The owner's rule was "show the list first, then remove it". The route was
# built to recompute the match set when the button is pressed, which is not the
# same thing: between the list being drawn and the button being pressed, the
# saved patterns can change - another tab, another administrator, a second
# window on a phone - and the set recomputed at that moment can be LARGER than
# the one that was confirmed.
#
# Concretely: `mods/` matches three rows, the screen says "Remove these entries
# (3)", somebody else saves `*.lha`, and the button now deletes every Amiga ROM
# there is, with the saves and play history hanging off each one.
#
# The rule that fixes it is one sentence: THE LIST SHOWN IS AN UPPER BOUND. The
# request carries the ids that were on screen, the server still recomputes what
# the patterns cover, and it deletes the INTERSECTION. Anything that stopped
# matching is skipped and reported. Anything that started matching was never
# confirmed by anybody and is not touched.


def test_the_apply_route_is_told_which_rows_were_shown():
    """A request that names nothing cannot be checked against anything."""
    import endpoints.roms.roms_router as rr
    import inspect

    params = inspect.signature(rr.apply_platform_exclusions).parameters
    assert "body" in params, (
        "trasa zastosowania nie przyjmuje listy pokazanych wierszy, wiec nie ma "
        "czego porownac z tym, co skasuje"
    )


def test_a_row_that_was_not_shown_is_never_removed(monkeypatch):
    """The failure this exists for: the patterns widened between the list and
    the button, and the button deleted rows nobody confirmed."""
    import endpoints.roms.roms_router as rr
    from handler.auth.scopes import Scope

    platform = _types.SimpleNamespace(id=7, scan_exclude="*.lha")
    monkeypatch.setattr(rr.rom_platform_handler, "get_by_slug", _fake_async(platform))

    # What the patterns cover NOW - wider than what the screen showed.
    async def _wide(_platform, _patterns):
        return [{"id": 1, "fs_name": "a.lha", "name": "A", "size_bytes": 1, "path": "/a.lha"},
                {"id": 2, "fs_name": "b.lha", "name": "B", "size_bytes": 1, "path": "/b.lha"},
                {"id": 3, "fs_name": "c.lha", "name": "C", "size_bytes": 1, "path": "/c.lha"}]

    monkeypatch.setattr(rr, "_excluded_rows", _wide)

    deleted = []

    async def _delete(rom_id, **k):
        deleted.append(rom_id)
        return True

    monkeypatch.setattr(rr.rom_handler, "delete", _delete)

    # The screen only ever showed row 1.
    got = _run(rr.apply_platform_exclusions(
        _FakeRequest({Scope.ROMS_WRITE}), "amiga",
        rr.ExclusionsApplyBody(ids=[1])))

    assert deleted == [1], f"skasowano wiersze, ktorych nikt nie widzial: {deleted}"
    assert got["removed"] == 1


def test_a_row_that_stopped_matching_is_skipped_and_said_so(monkeypatch):
    """The other direction is safe but must not be silent: the person is looking
    at a list of three and gets two."""
    import endpoints.roms.roms_router as rr
    from handler.auth.scopes import Scope

    platform = _types.SimpleNamespace(id=7, scan_exclude="mods/")
    monkeypatch.setattr(rr.rom_platform_handler, "get_by_slug", _fake_async(platform))

    async def _narrow(_platform, _patterns):
        return [{"id": 1, "fs_name": "a", "name": "A", "size_bytes": 1, "path": "/a"}]

    monkeypatch.setattr(rr, "_excluded_rows", _narrow)

    deleted = []

    async def _delete(rom_id, **k):
        deleted.append(rom_id)
        return True

    monkeypatch.setattr(rr.rom_handler, "delete", _delete)

    got = _run(rr.apply_platform_exclusions(
        _FakeRequest({Scope.ROMS_WRITE}), "amiga",
        rr.ExclusionsApplyBody(ids=[1, 2, 3])))

    assert deleted == [1]
    assert got["removed"] == 1
    assert sorted(got.get("skipped") or []) == [2, 3], (
        "pominiete wiersze nie zostaly zgloszone, wiec ekran sklamie o wyniku"
    )


def test_the_same_rule_guards_the_library_side(monkeypatch):
    import endpoints.library.libraries_router as lr
    from handler.auth.scopes import Scope
    import inspect

    assert "body" in inspect.signature(lr.apply_library_exclusions).parameters


# ── A pattern that would swallow the tree, written with a backslash ──────────


@pytest.mark.parametrize("raw", ["*\\*", "**\\*", "*\\**"])
def test_the_swallow_guard_sees_windows_slashes_too(raw):
    r"""The guard compared the raw line against a list of forward-slash shapes,
    and matching normalises backslashes afterwards. So `*\*` was saved happily
    and then covered the entire library, which is the exact outcome the guard
    exists to prevent. Measured on the running server before this was written.
    """
    kept = parse_patterns(raw)
    assert not any(is_excluded("/data/games/roms/amiga/Any Game.lha", [p])
                   for p in kept), (
        f"wzorzec {raw!r} przeszedl przez zapore i obejmuje cala biblioteke"
    )


# ── Asking about a directory ─────────────────────────────────────────────────
#
# `is_excluded` deliberately refuses to match a folder pattern against a path
# whose last segment IS the folder, so that a FILE called `mods` is not caught
# by `mods/`. Correct for a file, wrong for a directory, and the games scan asks
# about directories - so it gets its own entry point, and a trailing slash means
# "this is a directory" here exactly as it always has in a pattern.
#
# Whether the scan and the settings screen agree about a whole GAME is a
# different question, and a bigger one: it is answered end to end in
# test_the_scan_and_the_preview_agree_about_a_game.py, over a real tree, for
# every pattern shape and both folder layouts.


def test_a_folder_pattern_covers_the_directory_it_names():
    from handler.filesystem.exclusions import is_excluded_dir

    assert is_excluded_dir("/data/games/CUSTOM/mods", ["mods/"])
    assert is_excluded_dir("/data/games/CUSTOM/mods/", ["mods/"])


def test_a_folder_pattern_reaches_everything_underneath():
    """Naming a folder is not naming only the folder."""
    from handler.filesystem.exclusions import is_excluded_dir

    for pattern in ("mods/", "_originals/", "extras/"):
        d = "/data/games/CUSTOM/" + pattern.rstrip("/")
        assert is_excluded_dir(d, [pattern]), f"katalog nieobjety wzorcem {pattern!r}"
        assert is_excluded(d + "/anything.exe", [pattern])
        assert is_excluded(d + "/deeper/still.exe", [pattern])


def test_a_bare_name_does_not_catch_a_whole_folder():
    """`mods` names a file, and a folder called `mods` is not one. This is the
    difference the trailing slash carries, and it is why the help text says a
    bare name covers no game on the library side."""
    from handler.filesystem.exclusions import is_excluded_dir

    d = "/data/games/CUSTOM/mods"
    assert not is_excluded_dir(d, ["mods"])
    assert not is_excluded(d + "/anything.exe", ["mods"])


def test_a_file_named_like_a_folder_is_still_left_alone():
    """The original rule, unchanged: a ROM file called `mods` is not what
    `mods/` was written for."""
    assert not is_excluded("roms/amiga/mods", ["mods/"])


def test_the_games_scan_asks_about_a_directory_as_a_directory():
    source = _io.open(_LIBRARY, encoding="utf-8").read()
    assert "is_excluded_dir" in source, (
        "skan gier pyta o katalog tak, jakby byl plikiem, wiec wzorzec "
        "folderowy nigdy tam nie zadziala"
    )


# ── An absolute path, typed from the screen next to the box ──────────────────
#
# The preview lists full absolute paths, so an absolute pattern is the obvious
# thing to type rather than an odd one. Matching is relative to what is being
# scanned, so one used to be accepted and then match nothing at all, for ever,
# with the card reporting it as a saved pattern.
#
# It is read as what it plainly means now. The dangerous half of this - an
# absolute pattern covering the WHOLE library because matching ran against
# absolute paths and the guard probes relative ones - went when patterns became
# relative to the thing being scanned; measured before this was written, `/*`
# covered every ROM without a root and nothing with one.

_PLATFORM = "/APPS/GamesDownloader/library/roms/nes"


def test_an_absolute_path_inside_the_library_means_what_it_says():
    """Cut down when it is SAVED, not when it is matched. Doing it at match
    time put the swallow guard and the matcher on opposite sides of the same
    rewrite - see test_the_swallow_guard_sees_what_matching_sees.py."""
    folder = parse_patterns(_PLATFORM + "/mods/", root=_PLATFORM)
    named = parse_patterns(_PLATFORM + "/Thumbs.db", root=_PLATFORM)
    assert folder == ["mods/"] and named == ["Thumbs.db"]
    assert is_excluded(_PLATFORM + "/mods/patch.ips", folder, root=_PLATFORM)
    assert is_excluded(_PLATFORM + "/Thumbs.db", named, root=_PLATFORM)


def test_the_relative_spelling_still_works(): 
    """The form the help text describes has not changed."""
    assert is_excluded(_PLATFORM + "/mods/patch.ips", ["mods/"], root=_PLATFORM)


def test_an_absolute_path_outside_the_library_covers_nothing():
    """It names something else. Silently widening it to a suffix match is how a
    pattern comes to cover a folder somebody never mentioned."""
    assert not is_excluded(_PLATFORM + "/Super Mario.nes", ["/etc/*"], root=_PLATFORM)
    assert not is_excluded(_PLATFORM + "/Super Mario.nes", ["/*"], root=_PLATFORM)


def test_naming_the_library_itself_covers_nothing():
    """Not a pattern, it is everything - and the whole point of the guard above
    is that everything is never what somebody meant."""
    for spelling in (_PLATFORM, _PLATFORM + "/"):
        assert not is_excluded(_PLATFORM + "/Super Mario.nes", [spelling],
                               root=_PLATFORM)


def test_a_folder_named_absolutely_is_still_a_folder():
    """The trailing slash keeps its meaning after the root is taken off, so the
    scan and the preview go on agreeing about it."""
    from handler.filesystem.exclusions import is_excluded_dir

    kept = parse_patterns(_PLATFORM + "/mods/", root=_PLATFORM)
    assert is_excluded_dir(_PLATFORM + "/mods", kept, root=_PLATFORM)
    assert not is_excluded(_PLATFORM + "/mods", kept, root=_PLATFORM)
