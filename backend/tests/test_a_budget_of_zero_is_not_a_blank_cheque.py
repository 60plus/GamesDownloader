"""Spending the last byte of an allowance is not the same as having no allowance.

The ROM upload loop spends one budget across the whole request, which is right:
ten files of a gigabyte are a ten gigabyte upload. It kept that budget in a
single variable that doubled as the amount left AND as the flag saying a limit
applies - `if remaining and written > remaining`. A file that consumed the
budget exactly is allowed, because the refusal is "greater than", and it leaves
`remaining` at zero, which is falsy. Every later file in the same request was
then written with no check at all.

It is not a corner case to reach. `GET /library/my-uploads` hands an account its
own `used_bytes` and `limit_bytes`, so the size that lands on zero exactly is a
subtraction anybody can do, and the route is deliberately exempt from the
request-size middleware on the grounds that it polices itself.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import BackgroundTasks, HTTPException

from handler.auth.scopes import Scope

UPLOADER_ID = 7
SCOPES = {Scope.LIBRARY_UPLOAD, Scope.ROMS_READ}
BUDGET = 1024


class _Upload:
    def __init__(self, filename: str, size: int):
        self.filename = filename
        self._data = b"x" * size
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
    from handler.roms import rom_source_handler as rsh

    async def roms_path():
        return str(tmp_path)

    async def ceiling(_user, _max):
        return BUDGET

    async def nothing(*a, **k):
        return None

    async def clam_off():
        return False

    async def platform(_slug):
        # The route now resolves the shelf before it writes anything, so that a
        # slug reaching out of the ROM tree - or naming a platform nobody has -
        # is refused before `mkdir` makes the folder. Without this the fixture
        # goes looking for a real database.
        return SimpleNamespace(id=1, slug="psx", fs_slug="psx")

    monkeypatch.setattr(R.rom_platform_handler, "get_by_slug", platform)

    async def no_row(_platform_id, _name):
        # Every name in these tests is new to the shelf. The route asks this
        # before writing any file, not only when one is already there.
        return None

    monkeypatch.setattr(R.rom_handler, "get_by_fs_name", no_row)

    async def newest_rom_id():
        return 0

    monkeypatch.setattr(R.rom_handler, "max_rom_id", newest_rom_id)
    monkeypatch.setattr(R, "_get_roms_path", roms_path)
    monkeypatch.setattr(quota, "ceiling_for", ceiling)
    monkeypatch.setattr(rsh, "scan_after_write", nothing)
    monkeypatch.setattr(R, "_stamp_uploaded", nothing)
    monkeypatch.setattr(clam, "is_upload_scanning_enabled", clam_off)
    return R, tmp_path


def _request():
    return SimpleNamespace(state=SimpleNamespace(
        user=SimpleNamespace(id=UPLOADER_ID, username="u"), scopes=set(SCOPES),
    ))


async def _upload(R, files):
    tasks = BackgroundTasks()
    return await R.upload_roms(_request(), slug="psx", background_tasks=tasks, files=files)


@pytest.mark.asyncio
async def test_the_file_after_one_that_used_the_budget_exactly_is_refused(route):
    R, tmp_path = route

    out = await _upload(R, [_Upload("exact.bin", BUDGET), _Upload("free.bin", BUDGET * 4)])

    assert out.status_code == 413
    assert not (tmp_path / "psx" / "free.bin").exists(), (
        "plik po tym, ktory wyczerpal pule co do bajta, poszedl na dysk bez "
        "zadnej kontroli"
    )


@pytest.mark.asyncio
async def test_a_file_that_fits_exactly_is_still_allowed(route):
    """The other half. Refusing at the boundary would make the last byte of an
    allowance unusable."""
    R, tmp_path = route
    out = await _upload(R, [_Upload("exact.bin", BUDGET)])

    assert out["saved"] == ["exact.bin"]
    assert (tmp_path / "psx" / "exact.bin").stat().st_size == BUDGET


@pytest.mark.asyncio
async def test_the_budget_is_spent_across_the_whole_request(route):
    """Two halves of the allowance are one allowance, not two."""
    R, tmp_path = route

    out = await _upload(R, [_Upload("a.bin", BUDGET // 2 + 1),
                            _Upload("b.bin", BUDGET // 2 + 1)])

    assert out.status_code == 413
    assert (tmp_path / "psx" / "a.bin").exists()
    assert not (tmp_path / "psx" / "b.bin").exists()


@pytest.mark.asyncio
async def test_the_part_that_did_not_fit_leaves_nothing_behind(route):
    """A refusal that left the partial file would cost the disk exactly what the
    refusal was meant to save."""
    R, tmp_path = route

    assert (await _upload(R, [_Upload("toobig.bin", BUDGET * 3)])).status_code == 413

    assert not (tmp_path / "psx" / "toobig.bin").exists()


# ── The refusal is RETURNED, not raised ──────────────────────────────────────
#
# Every assertion above used to be `pytest.raises(HTTPException)`. The route now
# builds the same 413 and returns it, because FastAPI attaches background tasks
# only to a response the endpoint RETURNS - and the registration of whatever
# already reached the disk is scheduled in that very branch. Raising threw the
# task away, which made the fix below a no-op on the only path it was for.
#
# The framework behaviour that forces this is measured, not assumed, in
# test_a_refusal_still_runs_its_background_work.py.


# ── Bytes that land are counted, or the limit is a suggestion ────────────────

@pytest.mark.asyncio
async def test_a_file_the_library_will_never_register_is_refused(route):
    """The scan only ever makes a row for an extension it knows. A file with no
    row has no owner, counts against nobody, and can be repeated for ever - the
    volume fills while My uploads reads zero."""
    R, tmp_path = route
    out = await _upload(R, [_Upload("blob.dat", 10)])

    assert out["saved"] == []
    assert out["rejected"] and out["rejected"][0]["filename"] == "blob.dat"
    assert not (tmp_path / "psx" / "blob.dat").exists(), (
        "plik, ktorego biblioteka nigdy nie zarejestruje, zostal na dysku"
    )


@pytest.mark.asyncio
async def test_a_recognised_extension_is_still_accepted(route):
    R, tmp_path = route
    out = await _upload(R, [_Upload("game.iso", 10)])
    assert out["saved"] == ["game.iso"]
    assert (tmp_path / "psx" / "game.iso").is_file()


@pytest.mark.asyncio
async def test_what_landed_before_a_refusal_is_still_registered(route, monkeypatch):
    """Ten files and a refusal on the ninth used to leave eight on the disk with
    no scan behind them: no rows, so no owner, so nothing counted against the
    quota that had just refused them."""
    R, tmp_path = route
    scheduled: list = []
    monkeypatch.setattr(R, "_schedule_registration",
                        lambda tasks, slug, names, owner, **_k: scheduled.append(list(names)))

    out = await _upload(R, [_Upload("a.iso", BUDGET), _Upload("b.iso", BUDGET * 4)])
    assert out.status_code == 413

    assert scheduled and scheduled[-1] == ["a.iso"], (
        "to, co zdazylo wyladowac, nie zostanie zarejestrowane ani policzone"
    )


class _BrokenUpload(_Upload):
    """A file whose stream gives out partway. A full volume, a name the
    filesystem will not take, a browser that stops sending."""

    async def read(self, size: int) -> bytes:
        if self._at:
            raise OSError("no space left on device")
        return await super().read(size)


@pytest.mark.asyncio
async def test_what_landed_before_a_crash_is_still_registered(route, monkeypatch):
    """The same care, on the branch that catches everything else.

    The refusal branch beside it was taught both halves of this - register what
    landed, and RETURN so the framework keeps the background task - and this one
    was left raising with no registration at all. The files before the failure
    are in exactly the state that branch exists to prevent: on the disk, with no
    row, so owned by nobody and counting against no quota.
    """
    R, tmp_path = route
    scheduled: list = []
    monkeypatch.setattr(R, "_schedule_registration",
                        lambda tasks, slug, names, owner, **_k: scheduled.append(list(names)))

    out = await _upload(R, [_Upload("a.iso", 64), _BrokenUpload("b.iso", 64)])

    assert getattr(out, "status_code", None) == 500, (
        "awaria zapisu nadal leci wyjatkiem, wiec FastAPI buduje wlasna "
        "odpowiedz i wyrzuca zaplanowane zadanie w tle"
    )
    assert scheduled and scheduled[-1] == ["a.iso"], (
        "plik, ktory zdazyl wyladowac przed awaria, nie zostanie zarejestrowany "
        "ani policzony - zostaje na dysku jako niczyj"
    )
