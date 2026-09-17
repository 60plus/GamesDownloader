"""Three prices a .sbi upload charged that nobody chose to pay.

Subchannel files are the odd ones out on this route. They are not ROM
extensions and never will be, so no scan gives one a row - which is the whole
reason the upload gate needed an exception for them at all, and the reason
three separate things went wrong once it had one.

THE SCANS. Every name that lands goes to `_schedule_registration`, which loops
until each one has a row, up to three times, running a full walk of the ROM tree
each time. A .sbi can never satisfy that loop, so one 452 byte file bought three
complete scans - each holding the scanner lock, each starting with
`mark_all_missing()`, each driving the progress bar through the whole library -
and then logged a warning saying the file "is owned by nobody and counts against
no quota", which for a .sbi is the intended state and not a fault.

THE ORDER. The gate admits a subchannel file only beside the disc it names, and
it looks for that disc on the DISK. Files in one request are written one at a
time, so dropping `Game.sbi` and `Game.cue` together worked or did not depending
on which the browser listed first. The rejection is silent: `rejected` comes back
in the JSON and no screen in this project renders it.

THE BYTES. Within one request a subchannel file is charged like anything else.
It never reaches `used_bytes`, though, because that sum reads rows - so the next
request starts with the allowance full again, and nothing bounded the SIZE of a
file claiming to be subchannel data. A real .sbi is 452 bytes and a full .sub is
about 35 MB; anything beyond that is not subchannel data, whatever it is called.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import BackgroundTasks

from handler.auth.scopes import Scope

ME = 7
UPLOADER = {Scope.LIBRARY_UPLOAD, Scope.ROMS_READ}
BUDGET = 512 * 1024 * 1024


class _Upload:
    def __init__(self, filename: str, size: int = 16):
        self.filename = filename
        self._size = size
        self._at = 0

    async def read(self, size: int) -> bytes:
        take = min(size, self._size - self._at)
        self._at += take
        return b"n" * take


@pytest.fixture
def route(tmp_path, monkeypatch):
    from endpoints.roms import roms_router as R
    from handler.clamav import clamav_handler as clam
    from handler.library import quota
    from handler.roms import rom_source_handler as rsh

    shelf = tmp_path / "psx"
    shelf.mkdir(parents=True)
    registered: list[list[str]] = []

    async def roms_path():
        return str(tmp_path)

    async def ceiling(_user, _max):
        return BUDGET

    async def nothing(*a, **k):
        return None

    async def clam_off():
        return False

    async def platform(_slug):
        return SimpleNamespace(id=1, slug="playstation", fs_slug="psx")

    async def my_disc(_platform_id, fs_name):
        # Every disc on this shelf is mine, so ownership never gets in the way
        # of what these tests are about.
        # In the shelf's own folder: the file a replacement would replace.
        return SimpleNamespace(id=1, fs_name=fs_name, published_by=ME, fs_path=str(shelf))

    monkeypatch.setattr(R.rom_platform_handler, "get_by_slug", platform)
    monkeypatch.setattr(R.rom_handler, "get_by_fs_name", my_disc)
    monkeypatch.setattr(R.rom_handler, "max_rom_id", nothing)
    monkeypatch.setattr(R, "_get_roms_path", roms_path)
    monkeypatch.setattr(quota, "ceiling_for", ceiling)

    async def no_live_limit(_user, **_k):
        # The budget here is the ceiling above. Uploads running side by side
        # are checked live as well, and that has its own tests
        # (test_uploads_running_side_by_side_see_each_other).
        return quota.Reservation(None, limit=0)

    monkeypatch.setattr(quota, "reservation_for", no_live_limit)
    monkeypatch.setattr(rsh, "scan_after_write", nothing)
    monkeypatch.setattr(R, "_stamp_uploaded", nothing)
    monkeypatch.setattr(clam, "is_upload_scanning_enabled", clam_off)
    monkeypatch.setattr(
        R, "_schedule_registration",
        lambda tasks, fs_slug, names, owner, **_k: registered.append(list(names)))
    return R, shelf, registered


async def _upload(R, files):
    return await R.upload_roms(
        SimpleNamespace(state=SimpleNamespace(
            user=SimpleNamespace(id=ME, username="u"), scopes=set(UPLOADER))),
        slug="psx", background_tasks=BackgroundTasks(), files=files)


# ── The scans ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_subchannel_file_is_not_queued_for_registration(route):
    """It cannot be registered - that is what makes it a subchannel file - so
    asking three times only costs three walks of the library."""
    R, shelf, registered = route
    (shelf / "Game (Disc 1).cue").write_bytes(b"disc")

    out = await _upload(R, [_Upload("Game (Disc 1).sbi", 452)])

    assert out["saved"] == ["Game (Disc 1).sbi"], "plik nie wyladowal"
    assert registered[-1] == [], (
        "plik podkanalu trafia do petli rejestracji, ktora nigdy nie moze go "
        "znalezc - trzy pelne skany biblioteki i falszywe ostrzezenie w logu"
    )


@pytest.mark.asyncio
async def test_a_real_rom_is_still_queued_for_registration(route):
    """The other half. Skipping registration for everything would leave every
    upload owned by nobody, which is the fault this loop exists to prevent."""
    R, shelf, registered = route

    await _upload(R, [_Upload("Game (Disc 1).cue", 40)])

    assert registered[-1] == ["Game (Disc 1).cue"]


@pytest.mark.asyncio
async def test_a_mixed_request_registers_only_the_discs(route):
    R, shelf, registered = route

    out = await _upload(R, [_Upload("Game (Disc 1).cue", 40),
                            _Upload("Game (Disc 1).sbi", 452)])

    assert sorted(out["saved"]) == ["Game (Disc 1).cue", "Game (Disc 1).sbi"]
    assert registered[-1] == ["Game (Disc 1).cue"]


# ── The order ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_subchannel_file_sent_before_its_disc_still_lands(route):
    """Whether a drop of two files works must not depend on which one the
    browser happened to list first, least of all when the refusal is silent."""
    R, shelf, _registered = route

    out = await _upload(R, [_Upload("Game (Disc 1).sbi", 452),
                            _Upload("Game (Disc 1).cue", 40)])

    assert out["rejected"] == [], (
        "plik podkanalu wyslany PRZED swoja plyta w tym samym zadaniu jest "
        "odrzucany, i to po cichu - zaden ekran nie pokazuje `rejected`"
    )
    assert (shelf / "Game (Disc 1).sbi").is_file()


@pytest.mark.asyncio
async def test_a_subchannel_file_with_no_disc_anywhere_is_still_refused(route):
    """Reordering must not turn into admitting them unconditionally: a file with
    no row, no owner and no quota, uploadable under any name, is the hole the
    gate exists to close."""
    R, shelf, _registered = route

    out = await _upload(R, [_Upload("Orphan.sbi", 452)])

    assert out["saved"] == []
    assert [r["action"] for r in out["rejected"]] == ["extension_not_recognised"]


# ── The bytes ────────────────────────────────────────────────────────────────

def test_the_cap_still_fits_a_whole_disc_of_subchannel_data():
    """The arithmetic, so the limit is a measurement and not a round number
    somebody liked. 96 bytes of subchannel data per sector, and an 80 minute
    disc holds 360,000 sectors."""
    from endpoints.roms import roms_router as R

    full_sub = 96 * 360_000
    assert R._MAX_SUBCHANNEL_BYTES > full_sub, (
        "limit odcina pelny plik .sub prawdziwej plyty"
    )
    assert R._MAX_SUBCHANNEL_BYTES < 20 * full_sub, (
        "limit jest tak luzny, ze nie jest limitem"
    )


@pytest.mark.asyncio
async def test_a_real_subchannel_file_still_fits(route):
    R, shelf, _registered = route
    (shelf / "Game (Disc 1).cue").write_bytes(b"disc")

    out = await _upload(R, [_Upload("Game (Disc 1).sbi", 452)])

    assert out["saved"] == ["Game (Disc 1).sbi"]


@pytest.mark.asyncio
async def test_something_far_too_big_to_be_subchannel_data_is_refused(route):
    """These files never get a row, so they never reach `used_bytes` and the
    next request finds the allowance full again. Nothing bounded the size, so
    the exception was free storage of any size, beside any file with a ROM
    extension - and that neighbour may be zero bytes long."""
    R, shelf, _registered = route
    (shelf / "Game (Disc 1).cue").write_bytes(b"disc")

    out = await _upload(R, [_Upload("Game (Disc 1).sbi",
                                    R_max() + 1)])

    assert out["saved"] == []
    assert [r["action"] for r in out["rejected"]] == ["subchannel_too_large"]
    assert not (shelf / "Game (Disc 1).sbi").exists()
    assert sorted(p.name for p in shelf.iterdir()) == ["Game (Disc 1).cue"], (
        "po odmowie zostal plik roboczy"
    )


def R_max() -> int:
    from endpoints.roms import roms_router as R
    return R._MAX_SUBCHANNEL_BYTES
