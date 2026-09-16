"""The last three defects the review found in the exclusion feature.

1. A game that also belongs to another library was deleted outright. The screen
   is per library and the sentence a pattern says is "this is not a game HERE";
   a game somebody deliberately put on a second shelf makes that sentence stop
   being obvious. Those are left alone and counted, which is the same caution
   the feature already applies when it refuses to cover a game with one file
   outside the excluded path.

2. The removal loop committed one row at a time with nothing catching a failure
   in the middle. Row three throwing meant rows one and two were already gone
   while the caller was told the whole thing failed - the worst possible answer,
   because the obvious response is to press the button again.

3. An excluded file still took part in deciding which files are one disc set.
   It has no row, so nothing was written for it, but it changed the grouping of
   the files around it: exclude `Game (Disc 2).chd` and `Game (Disc 1).chd` was
   still filed as disc one of a two-disc set, with the second disc nowhere.
"""
from __future__ import annotations

import io
import pathlib
import types

import pytest

BACKEND = pathlib.Path(__file__).resolve().parent.parent


def _source(rel: str) -> str:
    return io.open(BACKEND / rel, encoding="utf-8").read()


# ── 1. A game on a second shelf is left alone ────────────────────────────────


def test_a_game_that_is_also_somewhere_else_is_not_covered():
    from endpoints.library.libraries_router import _covered_here

    alone = {"id": 1, "title": "A", "paths": ["/x/mods/a.exe"], "libraries": 1}
    shared = {"id": 2, "title": "B", "paths": ["/x/mods/b.exe"], "libraries": 2}
    assert _covered_here(alone, ["mods/"], "/x")
    assert not _covered_here(shared, ["mods/"], "/x"), (
        "gra nalezaca tez do innej biblioteki zostalaby skasowana z wszystkich"
    )


def test_a_game_that_occupies_two_folders_is_not_covered_by_one_of_them():
    """The caution that was already there, kept. A title present in two places
    is one game, and covering half of it is not an answer."""
    from endpoints.library.libraries_router import _covered_here

    straddling = {"id": 3, "title": "C", "libraries": 1,
                  "paths": ["/x/mods/c.exe", "/x/elsewhere/c.dat"]}
    assert not _covered_here(straddling, ["mods/"], "/x")


def test_a_game_with_no_files_is_not_covered():
    """Nothing to say where it sits, so nothing to conclude."""
    from endpoints.library.libraries_router import _covered_here

    assert not _covered_here({"id": 4, "title": "D", "paths": [], "libraries": 1},
                             ["mods/"], "/x")


def test_how_many_libraries_hold_it_is_counted_not_guessed():
    source = _source("handler/database/library_registry_handler.py")
    assert '"libraries"' in source, (
        "games_with_paths nie mowi, ile bibliotek trzyma gre, wiec nie da sie "
        "odroznic gry z jednej polki od gry z dwoch"
    )


# ── 2. A removal that fails halfway says what it actually did ────────────────


@pytest.mark.parametrize("router,route", [
    ("endpoints/roms/roms_router.py", "apply_platform_exclusions"),
    ("endpoints/library/libraries_router.py", "apply_library_exclusions"),
])
def test_the_removal_loop_survives_one_row_failing(router, route):
    source = _source(router)
    start = source.index(f"async def {route}")
    body = source[start:source.index("\n@", start)]
    assert "try:" in body and "except Exception" in body, (
        "petla kasujaca nie lapie bledu na pojedynczym wierszu, wiec awaria "
        "w polowie zglasza calkowita porazke mimo czesciowego skasowania"
    )
    assert "failed" in body, "brak licznika wierszy, ktorych nie udalo sie usunac"


def test_a_failure_partway_reports_what_went_and_what_did_not(monkeypatch):
    import endpoints.roms.roms_router as rr
    from handler.auth.scopes import Scope

    platform = types.SimpleNamespace(id=7, scan_exclude="mods/")
    monkeypatch.setattr(rr.rom_platform_handler, "get_by_slug",
                        _fake_async(platform))

    async def _rows(_p, _pat):
        return [{"id": i, "fs_name": f"{i}", "name": f"{i}", "size_bytes": 1,
                 "path": f"/{i}"} for i in (1, 2, 3)]

    monkeypatch.setattr(rr, "_excluded_rows", _rows)

    async def _delete(rom_id, **k):
        if rom_id == 2:
            raise RuntimeError("dysk odmowil")
        return True

    monkeypatch.setattr(rr.rom_handler, "delete", _delete)

    got = _run(rr.apply_platform_exclusions(
        _FakeRequest({Scope.ROMS_WRITE}), "amiga",
        rr.ExclusionsApplyBody(ids=[1, 2, 3])))

    assert got["removed"] == 2, "udane usuniecia nie zostaly policzone"
    assert got["failed"] == [2], "wiersz, ktory padl, nie zostal zgloszony"


def test_the_rows_that_did_not_go_stay_on_screen():
    """The server says which ids it could not remove, and the panel used to
    throw that list away and clear the whole thing - so the amber "could not
    remove 2" printed directly above "nothing already in the library matches",
    with nothing left identifying the two entries that are still there and
    still match. The only way back to them was to press the button again, which
    the message gave no reason to do."""
    panel = BACKEND.parent / "frontend" / "src" / "views" / "settings" / "SettingsScanExclusions.vue"
    if not panel.exists():
        pytest.fail(f"brak {panel} - test nie ma czego sprawdzic")
    source = io.open(panel, encoding="utf-8").read()
    start = source.index("const { data } = await client.post(`${base(slug)}/apply`")
    body = source[start:source.index("} catch", start)]
    assert "card.found = []" not in body, (
        "panel czysci cala liste po czesciowej porazce, wiec komunikat i ekran "
        "mowia dwie rozne rzeczy"
    )
    assert "failed.includes" in body, (
        "wiersze, ktorych nie udalo sie usunac, nie zostaja na ekranie"
    )


# ── 3. An excluded file does not shape the disc sets around it ───────────────


def test_disc_grouping_is_told_which_files_were_excluded():
    source = _source("handler/filesystem/rom_scanner.py")
    # Anchored on the CALL, not on the first occurrence of the name - that one
    # is the def, four hundred lines earlier, and a window around it would be
    # reading the wrong code entirely.
    call = source.index("assignments.update(plan_disk_assignments(")
    window = source[call - 300:call]
    assert "excluded_files" in window, (
        "grupowanie plyt liczy sie po plikach wykluczonych, wiec wykluczenie "
        "jednej plyty zmienia zestaw pozostalych"
    )


def test_an_excluded_disc_does_not_leave_its_neighbour_in_a_set():
    """The behaviour, not the wiring: with disc two excluded, disc one is a
    plain game rather than half of a set whose other half does not exist."""
    from handler.filesystem.rom_scanner import plan_disk_assignments

    both = [pathlib.Path(f"/roms/psx/Game (Disc {n}).chd") for n in (1, 2)]
    assert any(group for group, _n, _e, _t in plan_disk_assignments(both).values())

    only_one = [both[0]]
    assert not any(group for group, _n, _e, _t in
                   plan_disk_assignments(only_one).values()), (
        "pojedyncza plyta nadal wyglada na komplet"
    )


# ── shared helpers ───────────────────────────────────────────────────────────

import asyncio as _asyncio


class _FakeRequest:
    def __init__(self, scopes):
        self.state = types.SimpleNamespace(user=object(), scopes=set(scopes))


def _run(coro):
    return _asyncio.new_event_loop().run_until_complete(coro)


def _fake_async(value):
    async def _f(*a, **k):
        return value
    return _f
