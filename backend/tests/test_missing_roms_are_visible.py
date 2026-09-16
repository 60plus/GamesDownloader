"""Rows that point at nothing have to be findable, and removable on purpose.

Every listing, count and search filters on `~Rom.missing_from_fs`, so a row whose
file has gone is not merely unimportant, it is invisible. Nothing anywhere shows
it. An administrator has no way to learn that forty rows point into empty space,
and the saves and play history hanging off them are equally out of sight.

This is the other half of the rename fix. That one stopped MAKING invisible
rows; this one lets somebody clear up the ones that are already there.

The removal follows the same rule as the exclusions, and for the same reason: the
request names the rows that were on screen, and the server removes only those.
The set of missing rows changes on its own - a scan runs, a drive comes back -
so recomputing it at the moment of the click would remove rows nobody was shown.
"""
from __future__ import annotations

import asyncio
import types

import pytest


class _FakeRequest:
    def __init__(self, scopes):
        self.state = types.SimpleNamespace(user=object(), scopes=set(scopes))


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


def _fake_async(value):
    async def _f(*a, **k):
        return value
    return _f


# ── Seeing them ──────────────────────────────────────────────────────────────


def test_listing_missing_roms_is_administrator_only():
    """It reports filesystem paths and it is the door to a bulk delete."""
    import endpoints.roms.roms_router as rr
    from handler.auth.scopes import Scope

    assert rr.list_missing_roms.required_scopes == (Scope.ROMS_WRITE,)
    assert rr.remove_missing_roms.required_scopes == (Scope.ROMS_WRITE,)


def test_the_list_says_which_platform_each_row_belongs_to(monkeypatch):
    """Grouped by platform on the screen, so the platform has to come back with
    the row rather than being looked up one at a time."""
    import endpoints.roms.roms_router as rr
    from handler.auth.scopes import Scope

    rows = [
        {"id": 7, "name": "Tetris", "fs_name": "tetris.gb", "fs_path": "/roms/gb",
         "size_bytes": 512, "platform_slug": "game-boy", "platform_name": "Game Boy"},
    ]
    monkeypatch.setattr(rr.rom_handler, "all_missing", _fake_async(rows))

    got = _run(rr.list_missing_roms(_FakeRequest({Scope.ROMS_WRITE})))
    assert got["count"] == 1
    entry = got["roms"][0]
    assert entry["platform_name"] == "Game Boy"
    assert entry["path"].replace("\\", "/") == "/roms/gb/tetris.gb"


def test_an_empty_library_reports_zero_rather_than_failing(monkeypatch):
    import endpoints.roms.roms_router as rr
    from handler.auth.scopes import Scope

    monkeypatch.setattr(rr.rom_handler, "all_missing", _fake_async([]))
    got = _run(rr.list_missing_roms(_FakeRequest({Scope.ROMS_WRITE})))
    assert got == {"count": 0, "roms": []}


# ── Removing them ────────────────────────────────────────────────────────────


def test_only_the_rows_that_were_shown_are_removed(monkeypatch):
    """A drive that came back between the list and the click makes a row stop
    being missing. Removing it then would delete a game that is present."""
    import endpoints.roms.roms_router as rr
    from handler.auth.scopes import Scope

    monkeypatch.setattr(rr.rom_handler, "all_missing", _fake_async([
        {"id": 1, "name": "A", "fs_name": "a", "fs_path": "/r", "size_bytes": 1,
         "platform_slug": "psx", "platform_name": "PlayStation"},
        {"id": 2, "name": "B", "fs_name": "b", "fs_path": "/r", "size_bytes": 1,
         "platform_slug": "psx", "platform_name": "PlayStation"},
    ]))

    deleted = []

    async def _delete(rom_id, **k):
        deleted.append(rom_id)
        return True

    monkeypatch.setattr(rr.rom_handler, "delete", _delete)

    got = _run(rr.remove_missing_roms(
        _FakeRequest({Scope.ROMS_WRITE}), rr.MissingRemoveBody(ids=[1])))
    assert deleted == [1]
    assert got["removed"] == 1


def test_a_row_that_stopped_being_missing_is_skipped_and_reported(monkeypatch):
    import endpoints.roms.roms_router as rr
    from handler.auth.scopes import Scope

    monkeypatch.setattr(rr.rom_handler, "all_missing", _fake_async([
        {"id": 1, "name": "A", "fs_name": "a", "fs_path": "/r", "size_bytes": 1,
         "platform_slug": "psx", "platform_name": "PlayStation"},
    ]))

    deleted = []

    async def _delete(rom_id, **k):
        deleted.append(rom_id)
        return True

    monkeypatch.setattr(rr.rom_handler, "delete", _delete)

    got = _run(rr.remove_missing_roms(
        _FakeRequest({Scope.ROMS_WRITE}), rr.MissingRemoveBody(ids=[1, 2, 3])))
    assert deleted == [1]
    assert sorted(got["skipped"]) == [2, 3]


def test_one_row_failing_does_not_hide_the_ones_that_went(monkeypatch):
    import endpoints.roms.roms_router as rr
    from handler.auth.scopes import Scope

    monkeypatch.setattr(rr.rom_handler, "all_missing", _fake_async([
        {"id": i, "name": str(i), "fs_name": str(i), "fs_path": "/r",
         "size_bytes": 1, "platform_slug": "psx", "platform_name": "PlayStation"}
        for i in (1, 2, 3)
    ]))

    async def _delete(rom_id, **k):
        if rom_id == 2:
            raise RuntimeError("baza odmowila")
        return True

    monkeypatch.setattr(rr.rom_handler, "delete", _delete)

    got = _run(rr.remove_missing_roms(
        _FakeRequest({Scope.ROMS_WRITE}), rr.MissingRemoveBody(ids=[1, 2, 3])))
    assert got["removed"] == 2
    assert got["failed"] == [2]


def test_removing_nothing_is_allowed_and_does_nothing(monkeypatch):
    """An empty list is the screen saying "none of them", not a malformed
    request."""
    import endpoints.roms.roms_router as rr
    from handler.auth.scopes import Scope

    monkeypatch.setattr(rr.rom_handler, "all_missing", _fake_async([]))

    async def _explode(*a, **k):
        raise AssertionError("skasowano cos przy pustej liscie")

    monkeypatch.setattr(rr.rom_handler, "delete", _explode)
    got = _run(rr.remove_missing_roms(
        _FakeRequest({Scope.ROMS_WRITE}), rr.MissingRemoveBody(ids=[])))
    assert got["removed"] == 0


def test_missing_is_matched_before_the_catch_all_rom_id():
    """`/roms/{rom_id}` would swallow `/roms/missing` and answer 422 for a rom
    called "missing". FastAPI matches in registration order, so the order in the
    file is the behaviour, and nothing else in it says so."""
    import io
    import pathlib

    source = io.open(
        pathlib.Path(__file__).resolve().parent.parent
        / "endpoints" / "roms" / "roms_router.py",
        encoding="utf-8").read()
    assert (source.index('router.get, "/missing"')
            < source.index('router.get, "/{rom_id}"')), (
        "trasa /missing rejestruje sie po /{rom_id}, wiec nigdy nie zostanie trafiona"
    )


def test_the_request_must_name_its_rows():
    """No body means no list, and a bulk delete with no list is exactly what
    this route exists not to be."""
    import endpoints.roms.roms_router as rr
    import inspect

    params = inspect.signature(rr.remove_missing_roms).parameters
    assert "body" in params
    assert params["body"].default is inspect.Parameter.empty
