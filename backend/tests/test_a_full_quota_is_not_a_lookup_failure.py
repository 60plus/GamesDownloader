"""Running out of quota is an answer, not an error.

`quota.ceiling_for` reports a full account by RAISING a 413. The ROM download
wrapped it in `except Exception: return max_rom_bytes()`, and an HTTPException
is an Exception - so the single case the quota exists to stop was caught,
written to the log as "could not read the upload quota", and answered with the
whole install-wide per-file ceiling.

The effect is not one download slipping through. From the moment an account
first goes over, every download it starts is handed the full allowance, so the
quota stops binding at exactly the point it starts mattering. And the operator
who goes looking at disk growth is pointed at the database by a log line about a
lookup that never failed.
"""

from __future__ import annotations

import types

import pytest
from fastapi import HTTPException, status


@pytest.fixture
def ceiling(monkeypatch):
    from handler.database import users_handler as uh
    from handler.library import quota
    from handler.roms import rom_source_handler as rsh

    class _Users:
        async def get_by_id(self, _uid):
            return types.SimpleNamespace(id=7, username="u")

    monkeypatch.setattr(uh, "UsersHandler", _Users)
    monkeypatch.setattr(rsh, "max_rom_bytes", lambda: 64 * 1024 ** 3)
    return rsh, quota


def _job(actor_id=7):
    return types.SimpleNamespace(id=1, actor_id=actor_id)


@pytest.mark.asyncio
async def test_a_full_account_gets_no_room(ceiling, monkeypatch):
    rsh, quota = ceiling

    async def _full(_user, _max):
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                            detail="Upload quota reached: 10 of 10 bytes already used.")

    monkeypatch.setattr(quota, "ceiling_for", _full)

    assert await rsh._ceiling_for_job(_job()) == 0, (
        "pelny limit czytany jako awaria odczytu, wiec konto dostaje cala pule"
    )


@pytest.mark.asyncio
async def test_room_that_is_left_is_still_handed_over(ceiling, monkeypatch):
    """The other half. Zero for everything would refuse every download."""
    rsh, quota = ceiling

    async def _room(_user, _max):
        return 5 * 1024 ** 3

    monkeypatch.setattr(quota, "ceiling_for", _room)
    assert await rsh._ceiling_for_job(_job()) == 5 * 1024 ** 3


@pytest.mark.asyncio
async def test_a_real_lookup_failure_still_falls_back(ceiling, monkeypatch):
    """The behaviour the fallback was written for is kept: refusing a download
    because the database hiccuped would be worse than the limit not binding for
    one transfer."""
    rsh, quota = ceiling

    async def _broken(_user, _max):
        raise RuntimeError("baza padla")

    monkeypatch.setattr(quota, "ceiling_for", _broken)
    assert await rsh._ceiling_for_job(_job()) == 64 * 1024 ** 3


@pytest.mark.asyncio
async def test_a_job_with_nobody_behind_it_is_unchanged(ceiling):
    """An internal fetch has no account and no quota to weigh it against."""
    rsh, _quota = ceiling
    assert await rsh._ceiling_for_job(_job(actor_id=None)) == 64 * 1024 ** 3


@pytest.mark.asyncio
async def test_the_download_refuses_instead_of_starting_with_no_room(monkeypatch, tmp_path):
    """A ceiling of zero has to stop the transfer. Read as "no limit" by the
    loop, it would be the same hole one layer down."""
    from handler.roms import rom_source_handler as rsh

    async def _no_room(_job):
        return 0

    monkeypatch.setattr(rsh, "_ceiling_for_job", _no_room)
    monkeypatch.setattr(rsh, "_roms_base", lambda: str(tmp_path))

    emitted: list = []

    class _Sio:
        async def emit(self, name, payload=None):
            emitted.append((name, payload))

    monkeypatch.setattr("handler.socket_handler.sio", _Sio())

    job = rsh._RomJob(
        id=1, source_id="s", entry_id="e", url="http://x/y", filename="g.zip",
        fs_slug="psx", headers=None, cookies=None, actor="u", entry_key=None,
        dest_key=("psx", "g.zip"), actor_id=7,
    )
    landed = await rsh._run_rom_download(job)

    # Falsy, which is what the caller reads. Every failure path here returns
    # None rather than False; the point is that nothing is registered.
    assert not landed
    assert job.status == "failed"
    # The reason, not merely a failure: without this the test passes on the
    # transfer falling over for any other reason, which is how it passed
    # against the unfixed code.
    assert "quota" in (job.error or "").lower(), (
        f"zadanie odrzucone, ale nie z powodu limitu: {job.error!r}"
    )
    assert not (tmp_path / "psx" / "g.zip").exists()
