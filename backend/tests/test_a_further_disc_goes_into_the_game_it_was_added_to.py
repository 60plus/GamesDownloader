"""A file of the game added from a game's page lands in that game's folder.

"Add file" on a ROM offers "a further disc / game file" (the owner, 2026-09-18).
It goes through the platform upload, which already registers what it writes
and makes it the uploader's, with one more field, `into`: the ROM whose page it
was sent from. Without it the file is placed by its own name - a disc of a set
joins its set, anything else gets a folder named after itself - and a bonus
disc called something else would become a game of its own.

A loose game is given its folder first (game_folder.own_folder_held), and a
game on another platform is not a folder this upload may write into.
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import BackgroundTasks, HTTPException

from handler.auth.scopes import Scope

ME = 7
SCOPES = {Scope.LIBRARY_UPLOAD, Scope.ROMS_READ}


class _Upload:
    def __init__(self, filename: str, data: bytes = b"disc"):
        self.filename = filename
        self._data = data
        self._at = 0

    async def read(self, size: int) -> bytes:
        chunk = self._data[self._at:self._at + size]
        self._at += len(chunk)
        return chunk


@pytest.fixture
def route(tmp_path, monkeypatch):
    from endpoints.roms import roms_router as R
    from handler.clamav import clamav_handler as clam
    from handler.library import quota
    from handler.roms import game_folder
    from handler.roms import rom_source_handler as rsh

    folder = tmp_path / "psx" / "Final Fantasy IX"
    folder.mkdir(parents=True)
    state = SimpleNamespace(folder=folder, own=folder, registered=[],
                            target=SimpleNamespace(id=5, fs_path=str(folder),
                                                   platform=SimpleNamespace(fs_slug="psx")))

    async def roms_path():
        return str(tmp_path)

    async def ceiling(_user, _max):
        return 1 << 30

    async def unbounded(_user, **_k):
        return quota.Reservation(None, limit=0)

    async def nothing(*a, **k):
        return None

    async def clam_off():
        return False

    async def platform(_slug):
        return SimpleNamespace(id=1, slug="playstation", fs_slug="psx")

    async def nobody(_platform_id, _fs_name):
        return None

    async def zero():
        return 0

    async def with_platform(rom_id, **_k):
        return state.target if rom_id == 5 else None

    async def own(_rom_id, *, roms_base):
        return state.own

    def register(_tasks, _fs_slug, names, *_a, **k):
        state.registered.append((list(names), dict(k.get("written_to") or {})))
        release = k.get("release")
        if release:
            release()

    monkeypatch.setattr(R.rom_platform_handler, "get_by_slug", platform)
    monkeypatch.setattr(R.rom_handler, "any_row_named", nobody)
    monkeypatch.setattr(R.rom_handler, "max_rom_id", zero)
    monkeypatch.setattr(R.rom_handler, "get_with_platform", with_platform)
    monkeypatch.setattr(game_folder, "own_folder_held", own)
    monkeypatch.setattr(R, "_get_roms_path", roms_path)
    monkeypatch.setattr(R, "_schedule_registration", register)
    monkeypatch.setattr(quota, "ceiling_for", ceiling)
    monkeypatch.setattr(quota, "reservation_for", unbounded)
    monkeypatch.setattr(rsh, "scan_after_write", nothing)
    monkeypatch.setattr(clam, "is_upload_scanning_enabled", clam_off)
    state.R = R
    return state


def _request():
    return SimpleNamespace(state=SimpleNamespace(
        user=SimpleNamespace(id=ME, username="u"), scopes=set(SCOPES)))


async def _upload(route, name, *, into=5, slug="psx"):
    return await route.R.upload_roms(_request(), slug=slug, background_tasks=BackgroundTasks(),
                                     files=[_Upload(name)], into=into)


@pytest.mark.asyncio
async def test_a_file_of_another_name_joins_the_game_it_was_sent_from(route):
    await _upload(route, "FF9 Bonus Disc.chd")

    assert (route.folder / "FF9 Bonus Disc.chd").is_file()
    assert not (route.folder.parent / "FF9 Bonus Disc").exists(), "powstala osobna gra"
    [(names, written_to)] = route.registered
    assert names == ["FF9 Bonus Disc.chd"] and written_to == {"FF9 Bonus Disc.chd": str(route.folder)}


@pytest.mark.asyncio
async def test_without_into_it_is_placed_by_its_own_name_as_before(route):
    await _upload(route, "FF9 Bonus Disc.chd", into=None)

    assert (route.folder.parent / "FF9 Bonus Disc" / "FF9 Bonus Disc.chd").is_file()


@pytest.mark.asyncio
async def test_a_game_that_can_have_no_folder_of_its_own_takes_nothing(route):
    route.own = None
    out = await _upload(route, "FF9 Bonus Disc.chd")

    assert out["saved"] == [] and out["rejected"][0]["action"] == "no_folder_of_its_own"
    assert not list(route.folder.parent.rglob("FF9 Bonus Disc.chd"))


@pytest.mark.asyncio
async def test_a_game_on_another_platform_is_not_a_place_to_write(route):
    route.target.platform = SimpleNamespace(fs_slug="snes")
    with pytest.raises(HTTPException) as refused:
        await _upload(route, "FF9 Bonus Disc.chd")
    assert refused.value.status_code == 400


@pytest.mark.asyncio
async def test_a_game_that_is_not_there_is_a_404(route):
    with pytest.raises(HTTPException) as refused:
        await _upload(route, "FF9 Bonus Disc.chd", into=99)
    assert refused.value.status_code == 404
