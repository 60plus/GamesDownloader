"""A torrent that another row still holds is left to that row.

Found by the adversarial round on the 1.0.34 fixes, and half of it was made by
the fix for finding #1. A hash names the CONTENT, not the row, and two rows can
carry the same one:

  * a refused magnet stays on the list with its reason, and the same magnet
    added again after freeing space gets a new row with the same hash;
  * an old finished or failed row sits beside a new transfer of the same game;
  * a library file being seeded is the same torrent as a download of it.

Reaching the daemon by the stored number, a stale row named nothing - the number
had been retired with its torrent. Reaching it by the hash, the cross on the old
red row took the NEW transfer off the daemon, and its row was lost for good; the
same from another account's old row. And a quota refusal on a row that shared a
torrent removed it with its data.

So nothing is done to a torrent in the daemon from a row while another live
transfer, or a seed, holds the same hash. Dismissing the row still works; the
torrent stays with whoever is using it.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from handler.auth.scopes import Scope

ME = 3
HASH = "0123456789abcdef0123456789abcdef01234567"


def _request():
    return SimpleNamespace(state=SimpleNamespace(
        user=SimpleNamespace(id=ME, username="u"), scopes={Scope.LIBRARY_UPLOAD}))


@pytest.fixture
def tray(monkeypatch):
    from endpoints.torrent import torrent_router as R
    from handler.database import session as S
    from handler.torrent import seed_monitor as M

    # The refused row, still on the list with its reason, and whatever else may
    # hold the same torrent is decided per test through `state.shared`.
    old = SimpleNamespace(id=1, transmission_id=11, info_hash=HASH, total_size=10,
                          created_by_id=ME, status="error")
    table = {1: old}
    state = SimpleNamespace(shared=True, acted=[], asked_about=[])

    async def _row(dl_id):
        td = table.get(dl_id)
        if td is None:
            raise HTTPException(404, "Download not found")
        return td

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

    monkeypatch.setattr(R, "_download_or_404", _row)
    monkeypatch.setattr(S, "async_session_factory", _Factory())

    def _recording(name, answer=True):
        async def _call(ref, *_a, **_k):
            state.acted.append((name, ref))
            return answer
        return _call

    for name in ("pause_torrent", "resume_torrent", "verify_torrent", "remove_torrent",
                 "set_files_wanted"):
        monkeypatch.setattr(R.transmission_handler, name, _recording(name))
    monkeypatch.setattr(R.transmission_handler, "get_files",
                        _recording("get_files", answer=[{"index": 0}]))

    async def _held(td):
        state.asked_about.append(td.id)
        return state.shared

    monkeypatch.setattr(M, "held_by_another", _held, raising=False)

    async def _status(*_a, **_k):
        return None

    async def _fits(_td, _size):
        return False

    monkeypatch.setattr(R, "_set_download_status", _status)
    monkeypatch.setattr(M, "_over_quota", _fits)
    return SimpleNamespace(R=R, M=M, state=state, old=old)


# ── The cross ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_dismissing_a_row_leaves_a_torrent_another_row_is_using(tray):
    out = await tray.R.cancel_download(_request(), 1)

    assert out == {"ok": True}, "wiersza nie da sie zdjac z listy"
    assert tray.state.acted == [], (
        "krzyzyk na starym wierszu zdjal z demona torrent, ktory trzyma inny "
        f"transfer: {tray.state.acted}"
    )


@pytest.mark.asyncio
async def test_dismissing_the_only_row_still_takes_its_torrent_off_the_daemon(tray):
    """THE LEGAL CASE: the cross is also how a finished or failed transfer is
    cleaned out of Transmission."""
    tray.state.shared = False

    await tray.R.cancel_download(_request(), 1)

    assert tray.state.acted == [("remove_torrent", HASH)]


# ── The other buttons ────────────────────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.parametrize("control", ["pause_download", "resume_download", "verify_download"])
async def test_a_control_does_not_reach_a_torrent_another_row_is_using(tray, control):
    # A live row, so the verify button's own "already finished" refusal cannot be
    # what answers here: two live rows on one torrent, written before duplicates
    # were refused, are exactly where this still matters.
    tray.old.status = "paused"

    with pytest.raises(HTTPException) as refusal:
        await getattr(tray.R, control)(_request(), 1)

    assert refusal.value.status_code == 409
    assert tray.state.acted == [], (
        f"{control} dotknal torrentu, ktory trzyma inny transfer: {tray.state.acted}"
    )


@pytest.mark.asyncio
async def test_choosing_files_does_not_reach_a_torrent_another_row_is_using(tray):
    with pytest.raises(HTTPException) as refusal:
        await tray.R.choose_download_files(
            _request(), 1, tray.R.TorrentFilesBody(wanted=[0]))

    assert refusal.value.status_code == 409
    assert not [a for a in tray.state.acted if a[0] == "set_files_wanted"]


@pytest.mark.asyncio
async def test_a_control_on_a_torrent_nobody_else_holds_still_works(tray):
    """THE LEGAL CASE for the buttons."""
    tray.state.shared = False
    tray.old.status = "downloading"

    await tray.R.pause_download(_request(), 1)

    assert tray.state.acted == [("pause_torrent", HASH)]


# ── The quota refusal ────────────────────────────────────────────────────────

@pytest.fixture
def refusal(monkeypatch):
    from handler.torrent import seed_monitor as M
    from handler.torrent import transmission_handler as TH

    td = SimpleNamespace(id=4, transmission_id=2, info_hash=HASH, total_size=0,
                         created_by_id=ME, status="downloading")
    state = SimpleNamespace(shared=True, acted=[], written=[])

    async def _remove(ref, *, delete_data=False):
        state.acted.append(("remove", ref, delete_data))
        return True

    async def _pause(ref):
        state.acted.append(("pause", ref))
        return True

    async def _held(_td):
        return state.shared

    async def _room(_td):
        return 0

    async def _update(_id, values):
        state.written.append(dict(values))

    async def _emit(*_a, **_k):
        return None

    monkeypatch.setattr(TH.transmission_handler, "remove_torrent", _remove)
    monkeypatch.setattr(TH.transmission_handler, "pause_torrent", _pause)
    monkeypatch.setattr(M, "held_by_another", _held, raising=False)
    monkeypatch.setattr(M, "_room_left", _room)
    monkeypatch.setattr(M, "_update_download", _update)
    monkeypatch.setattr(M, "_emit_to_owner", _emit)
    return SimpleNamespace(M=M, td=td, state=state, info={"hashString": HASH})


@pytest.mark.asyncio
async def test_a_refusal_does_not_delete_a_torrent_another_row_is_using(refusal):
    """Its data is the other account's partial download, or the library folder a
    seed is sharing."""
    await refusal.M._refuse_over_quota(refusal.td, refusal.info, 56_373_525_225)

    assert refusal.state.acted == [], (
        "odmowa za limit usunela z danymi torrent, ktory trzyma inny transfer: "
        f"{refusal.state.acted}"
    )
    stany = [w.get("status") for w in refusal.state.written if "status" in w]
    assert stany == [refusal.M.REFUSED_STATUS], (
        f"wiersz nie zostal zapisany jako odrzucony: {refusal.state.written}"
    )


@pytest.mark.asyncio
async def test_a_refusal_of_a_torrent_nobody_else_holds_still_removes_it(refusal):
    """THE LEGAL CASE: the refusal the owner asked for."""
    refusal.state.shared = False

    await refusal.M._refuse_over_quota(refusal.td, refusal.info, 56_373_525_225)

    assert refusal.state.acted == [("remove", HASH, True)]


# ── The question itself ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_row_without_a_hash_is_not_looked_up_at_all(monkeypatch):
    """Nothing to compare, so nothing to ask - and no session opened for it."""
    from handler.database import session as S
    from handler.torrent import seed_monitor as M

    class _Boom:
        def __call__(self):
            raise AssertionError("sesja otwarta dla wiersza bez hasha")

    monkeypatch.setattr(S, "async_session_factory", _Boom())

    assert await M.held_by_another(SimpleNamespace(id=1, info_hash=None)) is False


@pytest.mark.asyncio
@pytest.mark.parametrize("transfers, seeds, expected", [
    ([], [], False),
    ([(9,)], [], True),
    ([], [(5,)], True),
])
async def test_another_live_transfer_or_a_seed_counts_as_holding_it(monkeypatch, transfers, seeds, expected):
    from handler.database import session as S
    from handler.torrent import seed_monitor as M

    asked: list[str] = []

    class _Result:
        def __init__(self, rows):
            self._rows = rows

        def first(self):
            return self._rows[0] if self._rows else None

    class _Db:
        async def execute(self, stmt, *_a, **_k):
            # With the values written in, so the test reads WHICH statuses and
            # which hash are asked about, not only that the words appear.
            sql = str(stmt.compile(compile_kwargs={"literal_binds": True}))
            asked.append(sql)
            return _Result(seeds if "library_torrents" in sql else transfers)

    class _Factory:
        def __call__(self):
            return self

        async def __aenter__(self):
            return _Db()

        async def __aexit__(self, *_a):
            return False

    monkeypatch.setattr(S, "async_session_factory", _Factory())

    held = await M.held_by_another(SimpleNamespace(id=1, info_hash=HASH))

    assert held is expected
    transfer_query = next(q for q in asked if "torrent_downloads" in q)
    assert f"info_hash = '{HASH}'" in transfer_query, (
        "zapytanie o inne transfery nie pyta o ten hash"
    )
    assert "'downloading'" in transfer_query and "'paused'" in transfer_query, (
        "zapytanie nie liczy pobierajacych albo wstrzymanych transferow"
    )
    assert "'error'" not in transfer_query and "'complete'" not in transfer_query, (
        "martwe wiersze licza sie jak zywe, wiec stary wiersz blokuje nowy"
    )
    assert "id != 1" in transfer_query, "wiersz liczy sam siebie jako kogos innego"
    if not transfers:
        seed_query = next(q for q in asked if "library_torrents" in q)
        assert f"info_hash = '{HASH}'" in seed_query and "status = 'seeding'" in seed_query, (
            "zapytanie o seedy nie pyta o ten hash albo o seedowanie"
        )


@pytest.mark.asyncio
async def test_reading_the_file_list_stays_open_on_a_torrent_another_row_holds(tray):
    """Reading changes nothing, and this row's owner added this very content."""
    await tray.R.list_download_files(_request(), 1)

    assert tray.state.acted == [("get_files", HASH)], (
        "lista plikow zablokowana, choc tylko czyta"
    )
