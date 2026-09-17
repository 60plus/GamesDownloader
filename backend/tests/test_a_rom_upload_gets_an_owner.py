"""A ROM put here through the upload form belongs to whoever put it here.

This release charges ROMs against an uploader's quota and lets that uploader
remove their own, and both of those read `published_by`. A downloaded ROM gets
it stamped (rom_source_handler._register_and_scrape). An uploaded one never did:
the route wrote the file, kicked off a scan and returned, and the scan is
owner-blind on purpose, because it re-walks the whole tree and stamping there
would hand one account every ROM on the disk.

So the headline feature of the release did not work on the path a person is
most likely to use. The upload counted against nobody's quota, and the account
that made it could not delete it, because the rule reads an owner and there was
none.

Two things are checked here. That the stamp happens, and that it happens even
when a scan is already running - the route used to skip its own scan in that
case on the assumption that the one in flight would pick the file up, which is
true of the row and was never true of the owner.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import BackgroundTasks

from handler.auth.scopes import Scope

UPLOADER_ID = 7
SCOPES = {Scope.LIBRARY_UPLOAD, Scope.ROMS_READ}


class _Upload:
    """Enough of UploadFile for the route: a name and a stream."""

    def __init__(self, filename: str, data: bytes):
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
    from handler.library import quota
    from handler.roms import rom_source_handler as rsh

    state = SimpleNamespace(scanned=0, stamped=[], rows={})

    async def roms_path():
        return str(tmp_path)

    async def ceiling(_user, _max):
        # Room to spare. Never zero: ceiling_for returns the install-wide
        # ceiling when no account limit applies and raises when there is none
        # left, so zero would mean "no room" and refuse the upload.
        return 1024 ** 3

    async def scan_after_write():
        # What a scan does, as far as this route is concerned: rows appear.
        state.scanned += 1
        for name in state.pending:
            # setdefault, not assignment: a file that already has a row keeps
            # it, which is what a re-upload over an existing ROM looks like.
            # With the file name and folder a real row carries: the stamp only
            # lands on a row holding exactly the uploaded name, in the shelf.
            state.rows.setdefault(
                name, SimpleNamespace(id=100 + len(state.rows), fs_name=name,
                                      fs_path=str(tmp_path / "psx"), published_by=None))

    async def get_by_fs_name(_platform_id, name):
        return state.rows.get(name)

    async def set_owner(rom_id, user_id):
        state.stamped.append((rom_id, user_id))

    async def get_by_slug(_slug):
        return SimpleNamespace(id=1, slug="psx")

    async def clam_off():
        return False

    state.pending = []
    monkeypatch.setattr(R, "_get_roms_path", roms_path)
    monkeypatch.setattr(quota, "ceiling_for", ceiling)

    async def no_live_limit(_user, **_k):
        # The budget here is the ceiling above. Uploads running side by side
        # are checked live as well, and that has its own tests
        # (test_uploads_running_side_by_side_see_each_other).
        return quota.Reservation(None, limit=0)

    monkeypatch.setattr(quota, "reservation_for", no_live_limit)
    monkeypatch.setattr(rsh, "scan_after_write", scan_after_write)
    monkeypatch.setattr(R.rom_handler, "get_by_fs_name", get_by_fs_name)
    monkeypatch.setattr(R.rom_handler, "set_owner", set_owner)
    monkeypatch.setattr(R.rom_platform_handler, "get_by_slug", get_by_slug)
    from handler.clamav import clamav_handler as clam
    monkeypatch.setattr(clam, "is_upload_scanning_enabled", clam_off)

    async def newest_rom_id():
        # An empty library before the upload: every row the scan makes here is
        # newer. Rows the scanner carries over are
        # test_a_rom_already_on_the_shelf_is_not_the_uploaders_to_take.py.
        return 0

    monkeypatch.setattr(R.rom_handler, "max_rom_id", newest_rom_id)
    return R, state, tmp_path


def _request(user_id=UPLOADER_ID):
    return SimpleNamespace(state=SimpleNamespace(
        user=SimpleNamespace(id=user_id, username="u"), scopes=set(SCOPES),
    ))


async def _upload(R, state, names, *, user_id=UPLOADER_ID):
    state.pending = list(names)
    tasks = BackgroundTasks()
    out = await R.upload_roms(
        _request(user_id), slug="psx", background_tasks=tasks,
        files=[_Upload(n, b"rom bytes") for n in names],
    )
    await tasks()          # the route defers the scan; run it as the server would
    return out


@pytest.mark.asyncio
async def test_an_uploaded_rom_records_who_uploaded_it(route):
    R, state, tmp_path = route
    out = await _upload(R, state, ["Sonic.bin"])

    assert out["saved"] == ["Sonic.bin"]
    assert (tmp_path / "psx" / "Sonic.bin").is_file()
    assert state.stamped == [(100, UPLOADER_ID)], (
        "wgrany ROM nie ma wlasciciela, wiec nie liczy sie do limitu i "
        "wgrywajacy go nie skasuje"
    )


@pytest.mark.asyncio
async def test_every_file_in_the_request_is_stamped(route):
    R, state, _tmp = route
    await _upload(R, state, ["A.bin", "B.bin"])
    assert sorted(state.stamped) == [(100, UPLOADER_ID), (101, UPLOADER_ID)]


@pytest.mark.asyncio
async def test_the_stamp_happens_even_while_another_scan_is_running(route):
    """The route used to schedule nothing at all when the scan lock was held,
    on the grounds that the scan in flight would pick the files up. It picks up
    the rows; it cannot pick up an owner nobody recorded."""
    R, state, _tmp = route
    from handler.filesystem import rom_scanner as scanner

    async with scanner._scan_lock:
        await _upload(R, state, ["Held.bin"])

    assert state.stamped == [(100, UPLOADER_ID)]


@pytest.mark.asyncio
async def test_a_rom_that_already_has_an_owner_is_left_alone(route):
    """Uploading over an existing file must not move it from one account to
    another, and must not undo an admin's claim. Same rule as set_owner's."""
    R, state, _tmp = route
    state.pending = ["Taken.bin"]
    tasks = BackgroundTasks()
    await R.upload_roms(_request(), slug="psx", background_tasks=tasks,
                        files=[_Upload("Taken.bin", b"x")])
    state.rows["Taken.bin"] = SimpleNamespace(id=55, published_by=3)
    await tasks()
    assert state.stamped == [], "wgranie przeniosloby ROM na inne konto"


# ── A stopped scan must not cost the upload its owner ────────────────────────
#
# The scan that registers an uploaded file can be stopped by an administrator
# halfway, and a stopped scan takes back the rows it created. The stamp then
# found nothing and gave up - and because the scan is owner-blind by design, no
# later scan ever repairs it: the ROM is owned by nobody for ever, counts
# against no quota, and the account that uploaded it cannot delete it.

@pytest.mark.asyncio
async def test_the_stamp_asks_for_another_scan_when_the_row_is_missing(route):
    R, state, _tmp = route
    from handler.roms import rom_source_handler as rsh

    scans = {"n": 0}

    async def _flaky_scan():
        # The first scan is stopped before it reaches this platform: no row.
        scans["n"] += 1
        if scans["n"] >= 2:
            for name in state.pending:
                state.rows.setdefault(
                    name, SimpleNamespace(id=100 + len(state.rows), fs_name=name,
                                          fs_path=str(_tmp / "psx"), published_by=None))

    import pytest as _pytest
    monkeypatch = _pytest.MonkeyPatch()
    monkeypatch.setattr(rsh, "scan_after_write", _flaky_scan)
    try:
        await _upload(R, state, ["Late.bin"])
    finally:
        monkeypatch.undo()

    assert scans["n"] >= 2, "stempel odpuscil po pierwszym skanie"
    assert state.stamped == [(100, UPLOADER_ID)], (
        "ROM wgrany podczas zatrzymanego skanu zostal bez wlasciciela na stale"
    )


@pytest.mark.asyncio
async def test_it_gives_up_rather_than_scanning_for_ever(route):
    """An administrator who keeps pressing Stop must not have us starting scans
    without end."""
    R, state, _tmp = route
    from handler.roms import rom_source_handler as rsh

    scans = {"n": 0}

    async def _never_registers():
        scans["n"] += 1

    import pytest as _pytest
    monkeypatch = _pytest.MonkeyPatch()
    monkeypatch.setattr(rsh, "scan_after_write", _never_registers)
    try:
        await _upload(R, state, ["Ghost.bin"])
    finally:
        monkeypatch.undo()

    assert scans["n"] == 3
    assert state.stamped == []


# ── The download path needs the same persistence ─────────────────────────────

def test_the_download_path_also_scans_more_than_once():
    """`_register_and_scrape` is the download side of everything above: it too
    runs a scan and then stamps the row that scan made. It tried once.

    A stopped scan takes back the rows it created, so one attempt found nothing
    and gave up - and no later scan repairs it, because the scan is owner-blind
    by design. The ROM is then nobody's for ever: uncounted, and not removable
    by the account that fetched it.
    """
    import io as _io
    import pathlib

    backend = pathlib.Path(__file__).resolve().parent.parent
    source = _io.open(backend / "handler" / "roms" / "rom_source_handler.py",
                      encoding="utf-8").read()
    at = source.index("async def _register_and_scrape(")
    # It is the last function in the file, so there is no next `async def` to
    # slice on - looking for one raised instead of asserting.
    nxt = source.find("\nasync def ", at + 10)
    body = source[at:nxt if nxt != -1 else len(source)]

    assert "range(3)" in body, (
        "droga pobierania probuje raz - zatrzymany skan zostawia ROM bez "
        "wlasciciela na stale"
    )
    # The lookup INSIDE the loop, the one a repeated scan can change. The function
    # also asks, once and before any scan, whether the name had a row already -
    # a different question, and the reason this anchors on the assignment.
    assert body.index("range(3)") < body.index("rom = await rom_handler.get_by_fs_name"), (
        "petla nie obejmuje wyszukania wiersza, wiec powtorka niczego nie zmienia"
    )
