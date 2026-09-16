"""Two ways the exclusions screen described something other than what it did.

ONE. The save reports which typed lines it threw away, and it worked that out by
comparing the text typed with the text stored. That was sound until the same
release taught `parse_patterns` to cut an absolute path down to a relative one
at save time: the two strings stopped being equal for every pattern it rewrote,
so a pattern that was stored AND WORKING came back on the "not saved" list,
under a message that says it would have covered the whole library.

The screen then drops those lines out of the box, which leaves the card looking
edited, which enables Save and disables the preview. A second Save sends the
shorter text and the pattern really is gone - deleted by a message that said it
had never been stored.

Asked of the parser per line instead: a line is ignored exactly when nothing is
left of it.

TWO. The scan skips a game when ANY of its directories is covered; the preview
called it covered only when ALL of them were. A game in the container layout has
two - `<root>/Quake` and `<root>/windows/Quake` - so excluding `windows/` stopped
the whole game being added, while the screen said the pattern covered nothing.
"""

from __future__ import annotations

import io
import pathlib

BACKEND = pathlib.Path(__file__).resolve().parent.parent


def _fn(path: str, name: str) -> str:
    source = io.open(BACKEND / path, encoding="utf-8").read()
    at = source.index(name)
    return source[at:source.index("\n@", at)]


# ── One: what "ignored" means ────────────────────────────────────────────────

def test_a_rewritten_pattern_is_not_reported_as_thrown_away():
    """Measured on the real parser: the stored text differs from the typed text
    by design, so equality is the wrong question."""
    from handler.filesystem.exclusions import parse_patterns

    root = "/data/games/CUSTOM"
    typed = "/data/games/CUSTOM/mods/"

    kept = parse_patterns(typed, root=root)
    assert kept == ["mods/"], "test nie odtwarza przycinania sciezki bezwzglednej"
    assert typed not in kept, "obie strony sa rowne - nie ma czego testowac"

    # The rule the routes must use: ask the parser about the line itself.
    assert parse_patterns(typed, root=root), (
        "linia zostala zapisana, wiec nie moze byc meldowana jako odrzucona"
    )


def test_a_pattern_that_really_is_refused_still_reports_as_refused():
    """The other half. A line that swallows the tree has to keep saying so, or
    the fix trades one lie for the opposite one."""
    from handler.filesystem.exclusions import parse_patterns

    root = "/data/games/CUSTOM"
    for swallows in ("*", "**", "/", "/data/games/CUSTOM", "/data/games/CUSTOM/*"):
        assert not parse_patterns(swallows, root=root), swallows


def test_both_routes_ask_the_parser_per_line():
    for path, name in (
        ("endpoints/library/libraries_router.py", "async def set_library_exclusions("),
        ("endpoints/roms/roms_router.py", "async def set_platform_exclusions("),
    ):
        body = _fn(path, name)
        assert "p not in kept" not in body and "ln not in kept" not in body, (
            f"{name} porownuje tekst wpisany z zapisanym, wiec wzorzec, ktory "
            "zostal przyciety i DZIALA, melduje sie jako odrzucony"
        )
        assert "parse_patterns(ln" in body, (
            f"{name} nie pyta parsera o pojedyncza linie"
        )


# ── Two: the scan and the preview count directories the same way ─────────────

def test_the_scan_and_the_preview_use_the_same_quantifier():
    # `_scan_one_folder`, which is where the call actually is. The first version
    # of this test read `scan_custom_library` - a function that mentions
    # `is_excluded_dir` without being the one that decides - and so passed over
    # the defect twice: once by looking in the wrong body, once by searching the
    # whole of it for a word instead of reading the call.
    scan = _fn("endpoints/library/library_router.py", "async def _scan_one_folder(")
    preview = _fn("endpoints/library/libraries_router.py", "def _covered_here(")

    assert "all(" in preview, "podglad przestal pytac o wszystkie katalogi gry"
    # The quantifier standing in front of THIS call, not anywhere in the route.
    # The first version of this assertion searched the whole body for "any(" and
    # passed over the very `any(` it was written to catch - the route has other
    # ones. Read the word immediately before the call instead.
    at = scan.index("is_excluded_dir(")
    guard = scan[:at].rsplit("excludes and ", 1)[-1]
    assert "all(" in guard and "any(" not in guard, (
        f"warunek przed wywolaniem brzmi `{guard.strip()[:60]}` - skan pomija "
        "cala gre, gdy JEDEN jej katalog jest objety, a podglad mowi, ze "
        "wzorzec nie obejmuje nic; wykluczenie `windows/` wywala wtedy kazda "
        "gre majaca podfolder windows"
    )


def test_a_container_folder_pattern_does_not_swallow_the_whole_game(tmp_path,
                                                                    monkeypatch):
    """The case that makes this concrete, measured on the real matcher."""
    from endpoints.library.libraries_router import _covered_here
    from handler.filesystem.exclusions import is_excluded_dir

    root = tmp_path / "games" / "CUSTOM"
    (root / "Quake").mkdir(parents=True)
    (root / "windows" / "Quake").mkdir(parents=True)
    monkeypatch.setattr("config.BASE_PATH", str(tmp_path))

    dirs = [str(root / "Quake"), str(root / "windows" / "Quake")]
    patterns = ["windows/"]

    covered_each = [is_excluded_dir(d, patterns, root=str(root)) for d in dirs]
    assert covered_each == [False, True], "test nie odtwarza ukladu kontenerowego"

    # The preview's answer, which is the one both sides now have to give.
    import os
    paths = [os.path.relpath(str(root / "windows" / "Quake" / "q.exe"), str(tmp_path)),
             os.path.relpath(str(root / "Quake" / "q.exe"), str(tmp_path))]
    assert not _covered_here({"paths": paths, "libraries": 1}, patterns, str(root)), (
        "podglad uznaje gre za objeta, choc jeden z jej katalogow nie jest"
    )
