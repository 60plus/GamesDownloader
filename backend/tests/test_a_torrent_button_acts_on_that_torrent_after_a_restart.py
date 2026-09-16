"""A button on a transfer acts on that transfer, even after the daemon restarted.

Finding #1 of the 1.0.34 pre-release audit, confirmed in part by a skeptic.

`transmission_id` is handed out by the daemon and starts again from 1 whenever it
restarts - every deploy and every upgrade. Nothing rewrites it on the row. Pause,
resume, verify, cancel and the file picker all passed that stored number straight
to the daemon, so after a restart a row's number could name somebody else's
torrent. The reachable case the skeptic found is an everyday one: uploader A
dismisses an old refused row with the cross, its stale number now belongs to
uploader B's running download, and B's transfer is taken off the daemon.

In 1.0.33 only an administrator could press these, and they can reach everything
anyway. 1.0.34 gave the buttons to uploaders and put the cross on every row of the
tray, which turned a stale number into one account acting on another's transfer.

`info_hash` is the torrent's own name and does not move. Transmission accepts it
wherever it accepts an id - measured on the test server on 2026-09-13: a torrent
added paused, then read, stopped and removed by its hash alone, each call landing
on that torrent, and an unknown hash answering with nothing. So every control now
reaches the daemon by the hash when the row has one, and a stale number cannot
reach anybody.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from handler.auth.scopes import Scope

ME = 3
UPLOADER = {Scope.LIBRARY_UPLOAD}
HASH = "0123456789abcdef0123456789abcdef01234567"


def _request():
    return SimpleNamespace(state=SimpleNamespace(
        user=SimpleNamespace(id=ME, username="u"), scopes=set(UPLOADER)))


@pytest.fixture
def daemon(monkeypatch):
    from endpoints.torrent import torrent_router as R

    # Written before a restart: the daemon has since handed number 11 to a
    # torrent that is not this one. The hash still names this one.
    renumbered = SimpleNamespace(id=1, transmission_id=11, info_hash=HASH, total_size=10,
                                 created_by_id=ME, status="downloading")
    # Written before hashes were recorded at all. Its number is all it has.
    legacy = SimpleNamespace(id=2, transmission_id=22, info_hash=None, total_size=10,
                             created_by_id=ME, status="downloading")
    table = {1: renumbered, 2: legacy}

    async def _row(dl_id):
        td = table.get(dl_id)
        if td is None:
            raise HTTPException(404, "Download not found")
        return td

    monkeypatch.setattr(R, "_download_or_404", _row)

    class _Db:
        async def get(self, _model, key):
            return table.get(key)

        async def execute(self, *_a, **_k):
            return None

        async def commit(self):
            return None

    class _Factory:
        def __call__(self):
            return self

        async def __aenter__(self):
            return _Db()

        async def __aexit__(self, *_a):
            return False

    from handler.database import session as S
    monkeypatch.setattr(S, "async_session_factory", _Factory())

    acted: list[tuple[str, object]] = []

    def _recording(name, answer=True):
        async def _call(ref, *_a, **_k):
            acted.append((name, ref))
            return answer
        return _call

    for name in ("pause_torrent", "resume_torrent", "verify_torrent", "remove_torrent",
                 "set_files_wanted"):
        monkeypatch.setattr(R.transmission_handler, name, _recording(name))
    monkeypatch.setattr(R.transmission_handler, "get_files",
                        _recording("get_files", answer=[{"index": 0}]))

    async def _status(*_a, **_k):
        return None

    monkeypatch.setattr(R, "_set_download_status", _status)

    from handler.torrent import seed_monitor as M

    async def _fits(_td, _size):
        return False

    monkeypatch.setattr(M, "_over_quota", _fits)

    # Nothing else holds these torrents here. The other case is
    # test_a_torrent_another_row_holds_is_left_to_it.py.
    async def _nobody_else(_td):
        return False

    monkeypatch.setattr(M, "held_by_another", _nobody_else)
    return SimpleNamespace(R=R, acted=acted)


def _refs(acted, name):
    return [ref for n, ref in acted if n == name]


@pytest.mark.asyncio
@pytest.mark.parametrize("control, daemon_call", [
    ("pause_download", "pause_torrent"),
    ("resume_download", "resume_torrent"),
    ("verify_download", "verify_torrent"),
    ("cancel_download", "remove_torrent"),
    ("list_download_files", "get_files"),
])
async def test_a_control_reaches_the_daemon_by_the_torrents_own_hash(daemon, control, daemon_call):
    await getattr(daemon.R, control)(_request(), 1)

    refs = _refs(daemon.acted, daemon_call)
    assert refs, f"{control} w ogole nie zapytal demona"
    assert refs == [HASH], (
        f"{control} poslal demonowi {refs!r} - numer sprzed restartu, ktory "
        "moze juz nalezec do cudzego transferu"
    )


@pytest.mark.asyncio
async def test_choosing_files_reads_and_sets_by_the_hash(daemon):
    await daemon.R.choose_download_files(
        _request(), 1, daemon.R.TorrentFilesBody(wanted=[0]))

    assert {ref for _n, ref in daemon.acted} == {HASH}, (
        "wybor plikow dotknal torrentu po numerze: %r" % (daemon.acted,)
    )


@pytest.mark.asyncio
async def test_a_row_from_before_hashes_were_recorded_still_works_by_its_number(daemon):
    """THE LEGAL CASE. Rows that never had a hash have nothing else to go by."""
    await daemon.R.pause_download(_request(), 2)

    assert _refs(daemon.acted, "pause_torrent") == [22]
