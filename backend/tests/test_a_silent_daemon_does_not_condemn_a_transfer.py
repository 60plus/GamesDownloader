"""Two different things arrived at the monitor looking identical.

`get_torrent` answers None when the daemon says it is not holding that torrent,
and ALSO when the daemon did not answer at all - a timeout, a refused
connection, an HTTP error, a second 409 after the one session renewal it
attempts. The monitor read both as "gone" and wrote the row to `status="error"`,
from which nothing brings it back: the loop only ever selects "downloading", and
no route moves a row out of "error". A ten second network hiccup permanently
killed a running transfer's bookkeeping, while Transmission carried on
downloading it into a folder nobody would ever file.

Asking whether the daemon is there is the difference, and it costs one call on
the failure path only.

THE OTHER HALF OF THE SAME PROBLEM. `transmission_id` is handed out by the
daemon and starts again from 1 on restart, so after one the row's number can
point at a DIFFERENT torrent - two rows on the live install already share id 1.
Following it would mean reporting somebody else's progress as this transfer's,
and then registering their files as this account's game. `info_hash` is the
content's own name, both queue routes write it, and until this release nothing
ever read it.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

OURS = "aaaa1111"
THEIRS = "bbbb2222"


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _Db:
    def __init__(self, rows):
        self._rows = rows

    async def execute(self, *_a, **_k):
        return _Result(self._rows)

    async def commit(self):
        return None


class _Factory:
    def __init__(self, rows):
        self._rows = rows

    def __call__(self):
        return self

    async def __aenter__(self):
        return _Db(self._rows)

    async def __aexit__(self, *_a):
        return False


@pytest.fixture
def world(monkeypatch):
    from handler.database import session as S
    from handler.socket_handler import sio
    from handler.torrent import seed_monitor as M
    from handler.torrent import transmission_handler as TH

    row = SimpleNamespace(id=4, transmission_id=2, info_hash=OURS,
                          total_size=1000, created_by_id=3, status="downloading")
    monkeypatch.setattr(S, "async_session_factory", _Factory([row]))

    daemon = SimpleNamespace(answer=None, alive=True)

    async def _get_torrent(_tid):
        return daemon.answer

    async def _is_available():
        return daemon.alive

    monkeypatch.setattr(TH.transmission_handler, "get_torrent", _get_torrent)
    monkeypatch.setattr(TH.transmission_handler, "is_available", _is_available)

    written: list[dict] = []

    async def _update(_id, values):
        written.append(dict(values))

    monkeypatch.setattr(M, "_update_download", _update)

    said: list[tuple] = []

    async def _emit(event, payload=None, **_k):
        said.append((event, payload))

    monkeypatch.setattr(sio, "emit", _emit)

    return SimpleNamespace(module=M, row=row, daemon=daemon,
                           written=written, said=said)


def _running(hash_string=OURS):
    return {"hashString": hash_string, "status": 4, "percentDone": 0.4,
            "totalSize": 1000, "downloadedEver": 400, "rateDownload": 500,
            "eta": 60, "error": 0}


@pytest.mark.asyncio
async def test_a_daemon_that_did_not_answer_does_not_kill_the_transfer(world):
    world.daemon.answer = None      # the RPC failed
    world.daemon.alive = False      # ...because the daemon is not there

    await world.module._check_downloads()

    assert not any(w.get("status") == "error" for w in world.written), (
        "chwilowa cisza demona zabija zdrowy transfer, i to na stale - z 'error' "
        f"nic go nie przywraca: {world.written}"
    )


@pytest.mark.asyncio
async def test_a_torrent_really_gone_is_still_reported(world):
    """THE LEGAL CASE for that guard. A live daemon that does not know this
    torrent means it really has gone, and the row has to say so - otherwise a
    transfer somebody removed by hand is polled for ever."""
    world.daemon.answer = None
    world.daemon.alive = True

    await world.module._check_downloads()

    assert any(w.get("status") == "error" for w in world.written), (
        "torrent naprawde usuniety z demona nie zostaje odnotowany, wiec wiersz "
        "bedzie odpytywany bez konca"
    )


@pytest.mark.asyncio
async def test_a_reused_number_is_not_followed(world):
    """After a restart the id can belong to somebody else's torrent. Reporting
    its progress here would end with its files registered as this account's
    game."""
    world.daemon.answer = _running(THEIRS)

    await world.module._check_downloads()

    progress = [p for e, p in world.said if e == "torrent:download_progress"]
    assert not progress, (
        "wiersz sledzi CUDZY torrent, bo numer sesyjny demona zostal przydzielony "
        "ponownie po restarcie"
    )


@pytest.mark.asyncio
async def test_a_row_from_before_the_hash_still_follows_its_number(world):
    """THE LEGAL CASE. Rows queued before the hash was recorded have nothing to
    compare, and refusing to follow them would freeze every transfer that
    predates the column."""
    world.row.info_hash = None
    world.daemon.answer = _running(THEIRS)

    await world.module._check_downloads()

    progress = [p for e, p in world.said if e == "torrent:download_progress"]
    assert progress, "transfer bez zapisanego hasha przestal byc sledzony"


@pytest.mark.asyncio
async def test_the_ordinary_case_is_untouched(world):
    """And the one that happens every ten seconds on a healthy install."""
    world.daemon.answer = _running()

    await world.module._check_downloads()

    progress = [p for e, p in world.said if e == "torrent:download_progress"]
    assert progress and progress[0]["percent"] == 40.0
    assert not any(w.get("status") == "error" for w in world.written)
