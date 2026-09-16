"""A ROM download is somebody's, and only they and an administrator may touch it.

This release opened the ROM Downloader from admin-only to any account holding
the store permission, so an uploader can fetch their own ROMs. The job routes
came with it and were never given an owner to ask about: pause, resume, retry
and cancel take a job id and nothing else, and cancelling deletes the partial
file. One uploader could stop and destroy another's download by guessing a small
number, and the job list handed them every job on the server to guess from.

The job already knows whose it is - `actor_id` was added when the quota learned
to charge downloads to an account - so this is a question nobody was asking
rather than a fact nobody had.

The same routes are also missing the emulation permission. Fetching a ROM onto
the server is an emulation act, and an account with emulation revoked was still
allowed it, which the ROM upload route beside them declares against explicitly.
"""

from __future__ import annotations

import io
import pathlib
import re
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from handler.auth.scopes import Scope

MINE = 7
THEIRS = 9

UPLOADER_SCOPES = {Scope.LIBRARY_UPLOAD, Scope.STORE_ACCESS, Scope.ROMS_READ}
ADMIN_SCOPES = UPLOADER_SCOPES | {Scope.ROMS_WRITE}

_BACKEND = pathlib.Path(__file__).resolve().parent.parent


def _request(scopes, user_id):
    return SimpleNamespace(state=SimpleNamespace(
        user=SimpleNamespace(id=user_id, username="u"), scopes=set(scopes),
    ))


@pytest.fixture
def jobs(monkeypatch):
    """Two real job objects in the real registry, one per account."""
    from handler.roms import rom_source_handler as rsh

    def job(job_id, actor_id, status="downloading"):
        return rsh._RomJob(
            id=job_id, source_id="s", entry_id="e", url="http://x/y",
            filename=f"{job_id}.zip", fs_slug="psx", headers=None, cookies=None,
            actor="u", entry_key=None, dest_key=("psx", f"{job_id}.zip"),
            actor_id=actor_id, status=status,
        )

    registry = {1: job(1, MINE), 2: job(2, THEIRS), 3: job(3, None)}
    monkeypatch.setattr(rsh, "_jobs", registry)
    return rsh, registry


@pytest.fixture
def routes(monkeypatch, jobs):
    """The routes, with the acting half stubbed so a refusal is visible.

    Anything recorded here happened AFTER the ownership question, so a test that
    sees nothing recorded has proved the question was asked.
    """
    from endpoints.roms import rom_sources_router as R

    acted: list = []

    async def stop(job_id):
        acted.append(job_id)
        return True

    for name in ("pause_job", "resume_job", "retry_job", "cancel_or_forget_job"):
        monkeypatch.setattr(R.rsh, name, stop)
    return R, acted


@pytest.mark.parametrize("route", ["pause_download", "resume_download",
                                   "retry_download", "cancel_download"])
@pytest.mark.asyncio
async def test_somebody_elses_download_is_refused(routes, route):
    R, acted = routes
    with pytest.raises(HTTPException) as raised:
        await getattr(R, route)(_request(UPLOADER_SCOPES, MINE), job_id=2)
    assert raised.value.status_code == 403
    assert acted == [], "odmowa, a zadanie i tak ruszylo"


@pytest.mark.parametrize("route", ["pause_download", "resume_download",
                                   "retry_download", "cancel_download"])
@pytest.mark.asyncio
async def test_their_own_download_still_works(routes, route):
    """The other half. A guard that refused everything would pass the test above
    and take the feature with it."""
    R, acted = routes
    out = await getattr(R, route)(_request(UPLOADER_SCOPES, MINE), job_id=1)
    assert out["ok"] is True
    assert acted == [1]


@pytest.mark.asyncio
async def test_an_administrator_may_touch_any_of_them(routes):
    R, acted = routes
    await R.cancel_download(_request(ADMIN_SCOPES, 1), job_id=2)
    await R.cancel_download(_request(ADMIN_SCOPES, 1), job_id=3)
    assert acted == [2, 3]


@pytest.mark.asyncio
async def test_a_job_with_nobody_behind_it_is_not_up_for_grabs(routes):
    """An internal fetch has no account. Reading that as a match rather than as
    "not mine" is the mistake the delete rule already documents."""
    R, acted = routes
    with pytest.raises(HTTPException) as raised:
        await R.cancel_download(_request(UPLOADER_SCOPES, MINE), job_id=3)
    assert raised.value.status_code == 403
    assert acted == []


@pytest.mark.asyncio
async def test_a_missing_job_is_still_a_404(routes):
    R, _acted = routes
    with pytest.raises(HTTPException) as raised:
        await R.cancel_download(_request(ADMIN_SCOPES, 1), job_id=99)
    assert raised.value.status_code == 404


@pytest.mark.asyncio
async def test_the_list_shows_an_uploader_only_their_own(jobs):
    from endpoints.roms import rom_sources_router as R

    out = await R.list_downloads(_request(UPLOADER_SCOPES, MINE))
    assert [j["id"] for j in out["jobs"]] == [1], (
        "lista pokazuje cudze pobierania, wiec jest spisem numerow do zgadniecia"
    )


@pytest.mark.asyncio
async def test_the_list_shows_an_administrator_everything(jobs):
    from endpoints.roms import rom_sources_router as R

    out = await R.list_downloads(_request(ADMIN_SCOPES, 1))
    assert sorted(j["id"] for j in out["jobs"]) == [1, 2, 3]


# ── the emulation permission ──────────────────────────────────────────────────

def test_every_rom_downloader_route_names_the_emulation_permission():
    """Fetching a ROM onto the server is an emulation act. The ROM upload route
    says so in as many words; these did not, so an account with emulation
    revoked could still pull ROMs down."""
    source = io.open(_BACKEND / "endpoints" / "roms" / "rom_sources_router.py",
                     encoding="utf-8").read()
    declarations = re.findall(r"@protected_route\([^)]*\)", source, re.S)
    assert len(declarations) >= 12, "test nie widzi tras, ktore mial sprawdzic"
    missing = [d for d in declarations if "ROMS_READ" not in d]
    assert not missing, "trasy bez uprawnienia emulacji: " + "; ".join(missing)


# ── And the events go to the same people as the listing ──────────────────────
#
# `GET /downloads` shows an uploader their own jobs and an administrator
# everything. The socket events carry the same thing - filenames, platforms, job
# numbers, progress - and were broadcast to every authenticated client, so a
# plain account holding none of the three permissions the route requires was
# handed the lot anyway.

@pytest.mark.asyncio
async def test_a_download_event_reaches_the_owner_and_administrators(monkeypatch):
    from handler.roms import rom_source_handler as rsh
    import handler.socket_handler as sh

    rooms: list = []

    class _Sio:
        async def emit(self, _event, _payload, room=None):
            rooms.append(room)

    monkeypatch.setattr(sh, "sio", _Sio())
    job = SimpleNamespace(id=1, actor_id=MINE)
    await rsh._emit_download(job, "romsource:download_state", {"id": 1})

    assert rooms == ["role:admin", f"user:{MINE}"], (
        f"zdarzenie poszlo do {rooms} zamiast do wlasciciela i adminow"
    )


@pytest.mark.asyncio
async def test_a_job_with_nobody_behind_it_goes_to_administrators_only(monkeypatch):
    from handler.roms import rom_source_handler as rsh
    import handler.socket_handler as sh

    rooms: list = []

    class _Sio:
        async def emit(self, _event, _payload, room=None):
            rooms.append(room)

    monkeypatch.setattr(sh, "sio", _Sio())
    await rsh._emit_download(SimpleNamespace(id=2, actor_id=None),
                             "romsource:download_state", {"id": 2})
    assert rooms == ["role:admin"]


def test_nothing_broadcasts_a_download_event_any_more():
    """A single `sio.emit` without a room reaches every logged-in client."""
    import io
    import pathlib

    source = io.open(pathlib.Path(__file__).resolve().parent.parent
                     / "handler" / "roms" / "rom_source_handler.py",
                     encoding="utf-8").read()
    assert 'sio.emit("romsource:' not in source, (
        "zostalo rozgloszenie zdarzenia pobierania do wszystkich"
    )
