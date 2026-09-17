"""Uploads running side by side count each other against the quota.

The owner said "teraz" (2026-09-17) to the last part of the 1.0.34 audit's #2.
Torrents on their way were counted in 1.0.35 already
(test_a_transfer_still_on_its_way_counts_against_the_quota). The rest of the
gap was every transfer written as a stream - a file upload, a download from an
address, a catalogue download, a ROM upload, a ROM download: each asked how
much room there was ONCE, at its start, and counted only its own bytes after
that. Two 9 GB uploads started together onto a 10 GB allowance each saw 10 GB
free and both finished.

So a stream holds a reservation for the bytes it has written:

  - every other transfer of the same account sees them, both at its start
    (`committed_bytes` includes them) and while it runs (`take` asks again at
    every chunk);
  - it holds them until they are counted somewhere else - the file row a game
    upload writes, or the ROM row a scan makes - and only then lets go, so there
    is never a moment when the bytes count nowhere;
  - when one lets go, the others read what has landed again, because the bytes
    moved from "being written" to "landed" and a figure read at the start would
    no longer be true.

One process holds all of this (uvicorn runs one worker, see the Dockerfile), so
memory is the right place: nothing here outlives the transfers it describes.
"""

from __future__ import annotations

import io
import pathlib
import re
from types import SimpleNamespace

import pytest

BACKEND = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture
def ledger(monkeypatch):
    """What has landed, per account, as the database would answer it."""
    from handler.library import quota

    landed: dict[int, int] = {}

    # Below `committed_bytes`, so the real one adds the streams being written.
    async def _landed(user_id):
        return landed.get(user_id, 0)

    async def _no_torrents(user_id, *, except_torrent_id=None):
        return 0

    monkeypatch.setattr(quota, "used_bytes", _landed)
    monkeypatch.setattr(quota, "in_flight_bytes", _no_torrents)
    monkeypatch.setattr(quota, "_writing", {})
    monkeypatch.setattr(quota, "_settled", {})
    return SimpleNamespace(quota=quota, landed=landed)


def _res(q, uid=3, limit=10, credit=0):
    return q.Reservation(uid, limit=limit, credit=credit)


@pytest.mark.asyncio
async def test_two_uploads_of_one_account_see_each_other(ledger):
    q = ledger.quota
    async with _res(q) as a, _res(q) as b:
        assert await a.take(6) is True
        assert await b.take(5) is False, (
            "dwa rownolegle wgrania jednego konta nie widza sie nawzajem - razem 11 z 10"
        )


@pytest.mark.asyncio
async def test_what_still_fits_beside_the_other_goes_through(ledger):
    q = ledger.quota
    async with _res(q) as a, _res(q) as b:
        await a.take(6)
        assert await b.take(4) is True


@pytest.mark.asyncio
async def test_another_account_is_not_in_the_way(ledger):
    q = ledger.quota
    async with _res(q, uid=3) as a, _res(q, uid=7) as b:
        await a.take(9)
        assert await b.take(9) is True


@pytest.mark.asyncio
async def test_a_transfer_that_let_go_without_landing_gives_its_room_back(ledger):
    q = ledger.quota
    async with _res(q) as b:
        async with _res(q) as a:
            await a.take(6)
        assert await b.take(9) is True


@pytest.mark.asyncio
async def test_a_transfer_that_landed_is_counted_where_it_landed(ledger):
    """The bytes move from "being written" to "landed". Holding on to the figure
    read at the start would see neither."""
    q = ledger.quota
    async with _res(q) as b:
        await b.take(1)
        async with _res(q) as a:
            await a.take(6)
            ledger.landed[3] = 6          # its file row is written...
        # ...and then it lets go.
        assert await b.take(4) is False, (
            "po zakonczeniu innego wgrania ten czyta limit sprzed jego wyladowania"
        )


@pytest.mark.asyncio
async def test_a_new_transfer_starts_by_seeing_the_ones_already_running(ledger):
    q = ledger.quota
    user = SimpleNamespace(id=3)

    async def _limit(_user):
        return 10

    import handler.library.quota as Q
    Q_limit = Q.limit_for
    Q.limit_for = _limit
    try:
        async with _res(q) as a:
            await a.take(6)
            assert q.writing_bytes(3) == 6
            assert await q.ceiling_for(user, 100) == 4, (
                "nowy transfer dostaje pulap, ktory nie liczy trwajacych wgran"
            )
    finally:
        Q.limit_for = Q_limit


@pytest.mark.asyncio
async def test_replacing_a_file_gives_its_bytes_back(ledger):
    q = ledger.quota
    ledger.landed[3] = 8
    async with _res(q, credit=5) as a:
        assert await a.take(7) is True       # 8 - 5 + 7 = 10
        assert await a.take(1) is False


@pytest.mark.asyncio
@pytest.mark.parametrize("uid,limit", [(None, 10), (3, 0)])
async def test_no_account_or_no_limit_is_never_refused(ledger, uid, limit):
    q = ledger.quota
    async with _res(q, uid=uid, limit=limit) as a:
        assert await a.take(10 ** 12) is True


@pytest.mark.asyncio
async def test_letting_go_twice_is_harmless(ledger):
    q = ledger.quota
    a = _res(q)
    a.open()
    await a.take(3)
    a.close()
    a.close()
    assert q.writing_bytes(3) == 0 and q._settled.get(3) == 1


# ── Every stream holds one, until its bytes are counted elsewhere ────────────

def _fn(path, head):
    source = io.open(BACKEND / path, encoding="utf-8").read()
    at = source.index(head)
    nxt = re.search(r"\n(?=[@A-Za-z_#])", source[at + len(head):])
    return source[at:at + len(head) + nxt.start()] if nxt else source[at:]


def test_a_game_file_upload_holds_it_until_its_row_is_written():
    fn = _fn("endpoints/library/upload_router.py", "async def upload_game_file(")
    assert "reservation.take(len(chunk))" in fn
    assert fn.index("reservation.open()") < fn.index("open(part_path")
    at_finalize = fn.index("await _finalize_upload(")
    assert "reservation.close()" in fn[at_finalize:], (
        "rezerwacja zwolniona przed zapisaniem wiersza pliku - bajty przez chwile nie licza sie nigdzie"
    )


def test_a_download_from_an_address_holds_it_until_its_row_is_written():
    """The pasted address and every catalogue build go through this one job, and
    each carries the account it charges as `actor_id`."""
    fn = _fn("endpoints/library/upload_router.py", "async def _url_upload_job(")
    assert "reservation = await quota.reservation_for_account(actor_id)" in fn
    assert "await reservation.take(len(chunk))" in fn
    assert fn.index("reservation.open()") < fn.index("open(part_path")
    assert fn.index("await _finalize_upload(") < fn.rindex("reservation.close()")
    assert "finally:" in fn[fn.index("await _finalize_upload("):]


def test_a_game_file_upload_asks_with_its_account():
    fn = _fn("endpoints/library/upload_router.py", "async def upload_game_file(")
    assert "reservation = await quota.reservation_for(_uploader, credit=replacing)" in fn


def test_a_rom_upload_holds_it_until_the_scan_has_registered_the_files():
    fn = _fn("endpoints/roms/roms_router.py", "async def upload_roms(")
    assert "await reservation.take(len(chunk))" in fn
    assert fn.count("release=reservation.close") == 3, (
        "nie kazda droga wyjscia z wgrania ROM-ow oddaje rezerwacje po rejestracji"
    )
    assert re.search(
        r'remaining \+= int\(getattr\(existing, "fs_size_bytes", 0\) or 0\)\s*'
        r'reservation\.give_back\(int\(getattr\(existing, "fs_size_bytes", 0\) or 0\)\)', fn), (
        "podmiana ROM-u nie oddaje bajtow starego pliku"
    )


class _Tasks:
    def __init__(self):
        self.tasks = []

    def add_task(self, fn):
        self.tasks.append(fn)


@pytest.mark.asyncio
@pytest.mark.parametrize("stamp_fails", [False, True])
async def test_the_registration_lets_go_after_it_has_run_whatever_happens(monkeypatch, stamp_fails):
    from endpoints.roms import roms_router as R
    from handler.roms import rom_source_handler as rsh

    order = []

    async def _scan():
        order.append("scan")

    async def _stamp(*_a, **_k):
        order.append("stamp")
        if stamp_fails:
            raise RuntimeError("baza nie odpowiada")
        return []

    monkeypatch.setattr(rsh, "scan_after_write", _scan)
    monkeypatch.setattr(R, "_stamp_uploaded", _stamp)
    tasks = _Tasks()
    R._schedule_registration(tasks, "psx", ["Game.chd"], 3, release=lambda: order.append("release"))
    assert order == [], "rezerwacja oddana, zanim cokolwiek zarejestrowano"
    try:
        await tasks.tasks[0]()
    except RuntimeError:
        pass
    assert order == ["scan", "stamp", "release"], (
        f"rezerwacja wgrania ROM-ow nie zostaje oddana po rejestracji: {order}"
    )


def test_nothing_to_register_lets_go_at_once():
    from endpoints.roms import roms_router as R

    released = []
    tasks = _Tasks()
    R._schedule_registration(tasks, "psx", [], 3, release=lambda: released.append(1))
    assert released == [1] and tasks.tasks == []


def test_a_rom_download_holds_it_until_the_row_is_stamped():
    run = _fn("handler/roms/rom_source_handler.py", "async def _run_rom_download(")
    assert "await job.reservation.take(len(chunk))" in run
    job = _fn("handler/roms/rom_source_handler.py", "async def _rom_download_job(")
    at = job.index("_register_after_download(job)")
    assert "_let_go_of_reservation(job)" in job[at:], (
        "pobrany ROM oddaje rezerwacje przed rejestracja"
    )
