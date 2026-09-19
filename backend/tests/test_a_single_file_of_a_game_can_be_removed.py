"""One file of a game can be removed on its own, by whoever may.

The owner (2026-09-18): a bin beside each file in a game's list, the way a
ROM's extras and mods get one. Until now a file went only with its whole game,
or all of an account's files at once ("Remove my files"), and the one route
that removed a single file was an administrator's that took the ROW and left
the bytes on the disk - counted against nobody, and back on the next scan.

Who may: an administrator, any file; an uploader, a file that counts against
their own account (`ownership.charged_to`) - the same sentence the quota sums
with and "Remove my files" removes by, so the bin, the bar and that button can
never disagree about what is "yours". A file somebody else added to your game
is theirs: the game's owner removes it with the game, not one at a time.

Always from the disk too, like "Remove my files".
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from handler.auth.scopes import Scope
from handler.library.ownership import can_remove_file

ADMIN = {Scope.LIBRARY_ADMIN, Scope.LIBRARY_UPLOAD, Scope.LIBRARY_READ}
UPLOADER = {Scope.LIBRARY_UPLOAD, Scope.LIBRARY_READ}
READER = {Scope.LIBRARY_READ}

ME, SOMEBODY = 7, 9


def _game(owner=SOMEBODY):
    return SimpleNamespace(id=1, published_by=owner)


def _file(owner=None, file_id=5):
    return SimpleNamespace(id=file_id, published_by=owner, file_path="games/CUSTOM/A/a.zip")


# ── The rule ─────────────────────────────────────────────────────────────────


def test_an_administrator_may_remove_any_file():
    assert can_remove_file(ADMIN, ME, _game(), _file(owner=SOMEBODY))


def test_an_uploader_may_remove_a_file_they_added_to_somebody_elses_game():
    assert can_remove_file(UPLOADER, ME, _game(owner=SOMEBODY), _file(owner=ME))


def test_an_uploader_may_not_remove_a_file_somebody_else_added():
    assert not can_remove_file(UPLOADER, ME, _game(owner=ME), _file(owner=SOMEBODY))


def test_an_unmarked_file_is_the_games_owners():
    """A file from before files carried an owner counts against the game's
    owner, so that owner may remove it and nobody else may."""
    assert can_remove_file(UPLOADER, ME, _game(owner=ME), _file(owner=None))
    assert not can_remove_file(UPLOADER, ME, _game(owner=SOMEBODY), _file(owner=None))


def test_nobody_owns_what_nobody_brought_in():
    """A scanned game with a scanned file names no account at all; reading two
    Nones as a match would hand it to the first uploader who looked."""
    assert not can_remove_file(UPLOADER, ME, _game(owner=None), _file(owner=None))
    assert not can_remove_file(UPLOADER, None, _game(owner=None), _file(owner=None))


def test_reading_is_not_enough():
    assert not can_remove_file(READER, ME, _game(owner=ME), _file(owner=ME))


# ── The route ────────────────────────────────────────────────────────────────


@pytest.fixture
def route(monkeypatch):
    from endpoints.library import library_router as R

    files = {5: _file(owner=ME, file_id=5), 6: _file(owner=SOMEBODY, file_id=6)}
    for f in files.values():
        f.library_game_id = 1
    state = SimpleNamespace(on_disk=[], rows=[], visible=True)

    async def get_file(file_id):
        return files.get(file_id)

    async def get_game(_game_id):
        return _game(owner=SOMEBODY)

    async def visible(_request, game):
        return game if state.visible else None

    async def delete_row(f):
        state.rows.append(f.id)

    def delete_disk(fs):
        state.on_disk.extend(f.id for f in fs)
        return len(fs)

    monkeypatch.setattr(R._lib, "get_file_by_id", get_file)
    monkeypatch.setattr(R._lib, "get_by_id", get_game)
    monkeypatch.setattr(R._lib, "delete_file", delete_row)
    monkeypatch.setattr(R, "_visible_or_none", visible)
    monkeypatch.setattr(R, "_delete_files_on_disk", delete_disk)
    return SimpleNamespace(R=R, state=state)


def _request(scopes, user_id=ME):
    return SimpleNamespace(state=SimpleNamespace(
        user=SimpleNamespace(id=user_id, username="u"), scopes=set(scopes)))


def _call(R, *args, **kwargs):
    return getattr(R.delete_library_file, "__wrapped__", R.delete_library_file)(*args, **kwargs)


@pytest.mark.asyncio
async def test_the_bin_takes_the_file_off_the_disk_and_the_row_with_it(route):
    out = await _call(route.R, _request(UPLOADER), file_id=5)

    assert out["ok"] and route.state.on_disk == [5] and route.state.rows == [5]


@pytest.mark.asyncio
async def test_an_uploader_is_refused_somebody_elses_file_and_nothing_is_touched(route):
    with pytest.raises(HTTPException) as refused:
        await _call(route.R, _request(UPLOADER), file_id=6)

    assert refused.value.status_code == 403
    assert route.state.on_disk == [] and route.state.rows == []


@pytest.mark.asyncio
async def test_a_file_of_a_game_you_cannot_see_is_not_there(route):
    route.state.visible = False
    with pytest.raises(HTTPException) as refused:
        await _call(route.R, _request(ADMIN), file_id=5)

    assert refused.value.status_code == 404 and route.state.on_disk == []


@pytest.mark.asyncio
async def test_an_unknown_file_is_a_404(route):
    with pytest.raises(HTTPException) as refused:
        await _call(route.R, _request(ADMIN), file_id=99)
    assert refused.value.status_code == 404


# ── What the page is told ────────────────────────────────────────────────────


def test_each_file_on_the_page_says_whether_its_bin_would_work():
    """Asked with the rule itself, per file, for the account looking."""
    from endpoints.library import library_router as R

    game = _game(owner=SOMEBODY)
    game.files = [_file(owner=ME, file_id=5), _file(owner=SOMEBODY, file_id=6)]
    listed = [{"id": 5}, {"id": 6}]

    R._mark_removable(_request(UPLOADER), game, listed)

    assert [f["can_delete"] for f in listed] == [True, False]


def test_the_game_page_marks_them():
    import pathlib

    source = (pathlib.Path(__file__).resolve().parent.parent / "endpoints" / "library"
              / "library_router.py").read_text(encoding="utf-8")
    page = source[source.index("async def get_library_game("):]
    page = page[:page.index("\n@")]
    assert "_mark_removable(" in page
