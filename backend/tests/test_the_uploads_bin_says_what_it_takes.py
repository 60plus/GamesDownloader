"""The bin on "My uploads" has to be able to say what it is about to take.

Deleting a ROM there sends delete_files=true, and for a disc title that reaches
every disc of the set, the track files behind each, the .m3u playlist, the .sbi
subchannel data, the media directory and every account's savestates and memory
cards. The panel asked one sentence - "Delete {name} and its files from disk?" -
and could not have said more, because the route that works all of that out was
declared administrator-only and an uploader is not one.

The ROM detail page has always asked the other way, fetching the preview and
naming the disc count and the save count. The two screens do the same thing to
the same rows, so they ask the same question now, and the preview is declared
exactly like the deletion it describes: you may see what would go precisely
when you could make it go.
"""

from __future__ import annotations

import io
import pathlib
import re
from dataclasses import dataclass
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from handler.auth.scopes import Scope

_FRONTEND = pathlib.Path(__file__).resolve().parent.parent.parent / "frontend" / "src"
_PANEL = _FRONTEND / "components" / "MyUploadsPanel.vue"

UPLOADER_ID = 7
SOMEBODY_ELSE = 9
UPLOADER_SCOPES = {Scope.LIBRARY_UPLOAD, Scope.ROMS_READ}


@dataclass
class _Rom:
    id: int = 1
    fs_name: str = "Game (Disc 1).cue"
    fs_path: str = "/nowhere"
    published_by: int | None = UPLOADER_ID
    platform_id: int = 1
    track_of: str | None = None
    disk_group: str | None = "game"
    disk_number: int | None = 1


def _request(scopes, user_id):
    return SimpleNamespace(state=SimpleNamespace(
        user=SimpleNamespace(id=user_id, username="u"), scopes=set(scopes),
    ))


@pytest.fixture
def preview(monkeypatch):
    """The real handler, with the database and the disk stubbed out."""
    from endpoints.roms import roms_router as R

    rows: list = []

    async def get_by_id(rom_id):
        return next((r for r in rows if r.id == rom_id), None)

    async def disk_set(_rom_id):
        return list(rows)

    async def states(_rom_id):
        return ["one"]

    async def saves(_rom_id):
        return []

    async def tracks(_members):
        return []

    monkeypatch.setattr(R.rom_handler, "get_by_id", get_by_id)
    monkeypatch.setattr(R.rom_handler, "disk_set", disk_set)
    monkeypatch.setattr(R.save_state_handler, "list_states_for_rom", states)
    monkeypatch.setattr(R.save_state_handler, "list_saves_for_rom", saves)
    monkeypatch.setattr(R, "removable_tracks", tracks)
    monkeypatch.setattr(R.rom_removal, "spoken_for_elsewhere", lambda *a, **k: set())
    monkeypatch.setattr(R, "_playlists_naming", lambda *a, **k: [])
    monkeypatch.setattr(R, "subchannel_files_for", lambda *a, **k: [])
    # Nothing beside these games in extras/ or mods/
    # (test_a_games_extras_and_mods_are_offered.py).
    monkeypatch.setattr(R, "_extras_going_with", tracks)
    return R, rows


@pytest.mark.asyncio
async def test_an_uploader_can_see_what_removing_their_own_rom_would_take(preview):
    R, rows = preview
    rows.extend([
        _Rom(id=1, published_by=UPLOADER_ID),
        _Rom(id=2, fs_name="Game (Disc 2).cue", disk_number=2, published_by=UPLOADER_ID),
    ])

    out = await R.rom_removal_preview(_request(UPLOADER_SCOPES, UPLOADER_ID), rom_id=1)

    assert len(out["disks"]) == 2, "podglad nie mowi, ze to komplet dwoch plyt"
    assert out["saves"] == 2, "podglad nie liczy zapisow, ktore znikna"


@pytest.mark.asyncio
async def test_an_uploader_cannot_read_a_set_they_could_not_delete(preview):
    """It reports file names. Opening that to every uploader for every id would
    be a listing of the library from an account that may not have one."""
    R, rows = preview
    rows.extend([
        _Rom(id=1, published_by=SOMEBODY_ELSE),
        _Rom(id=2, fs_name="Game (Disc 2).cue", disk_number=2, published_by=SOMEBODY_ELSE),
    ])

    with pytest.raises(HTTPException) as raised:
        await R.rom_removal_preview(_request(UPLOADER_SCOPES, UPLOADER_ID), rom_id=1)
    assert raised.value.status_code == 403


@pytest.mark.asyncio
async def test_a_missing_rom_is_still_a_404(preview):
    R, _rows = preview
    with pytest.raises(HTTPException) as raised:
        await R.rom_removal_preview(_request(UPLOADER_SCOPES, UPLOADER_ID), rom_id=99)
    assert raised.value.status_code == 404


def test_the_preview_is_declared_like_the_deletion_it_describes():
    """The pair only holds while both are declared the same way. Written down
    here because the next person to widen one will not think to widen both.

    The two lines against EACH OTHER, rather than against a permission spelled
    out here. This test used to name the pair, and when the declaration moved -
    it asked for a Games permission to reach an emulation route, so an
    administrator with the Games chip off was drawn a delete button that could
    only answer 403 - the widening was done to both and this still failed,
    pointing at neither. Which permission it is belongs in the file that decides
    it; what belongs here is that they are the same.
    """
    backend = pathlib.Path(__file__).resolve().parent.parent
    source = io.open(backend / "endpoints" / "roms" / "roms_router.py",
                     encoding="utf-8").read()

    def scopes_of(marker: str) -> set[str]:
        line = source[source.index(marker):]
        return set(re.findall(r"Scopes\.(\w+)", line[:line.index("\n")]))

    preview = scopes_of('@protected_route(router.get, "/{rom_id}/removal"')
    delete = scopes_of('@protected_route(router.delete, "/{rom_id}"')
    assert preview and preview == delete, (
        f"podglad wpuszcza {preview}, a kasowanie {delete} - jedno z nich "
        "odmawia komus, komu drugie pozwala"
    )


# ── the screen ────────────────────────────────────────────────────────────────

def _panel() -> str:
    if not _PANEL.exists():
        pytest.fail(f"brak {_PANEL} - test nie ma czego sprawdzic")
    return io.open(_PANEL, encoding="utf-8").read()


def test_the_panel_asks_the_server_before_it_asks_the_person():
    source = _panel()
    assert "/roms/${g.id}/removal" in source, (
        "kosz nadal pyta jednym zdaniem, nie wiedzac, co zabierze"
    )


def test_what_the_server_said_reaches_the_question():
    """Fetching it and not using it would be the same one sentence."""
    source = _panel()
    start = source.index("async function remove(")
    body = source[start:source.index("\n}", start)]
    assert "removalDetail(g)" in body, "podglad pobrany, ale pytanie go nie uzywa"
    assert "gdConfirm" in body


def test_the_question_names_the_discs_the_files_and_the_saves():
    source = _panel()
    for key in ("uploads.delete_discs", "uploads.delete_extra_files", "uploads.delete_saves"):
        assert key in source, f"pytanie nie mowi o {key}"
