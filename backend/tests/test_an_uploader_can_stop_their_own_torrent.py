"""The controls belonged to an administrator, the transfer to somebody else.

An uploader may queue a torrent - that is the whole point of the route being at
LIBRARY_UPLOAD - and from this release they can also see it, because it appears
in the transfer tray. Every button on it needed LIBRARY_ADMIN: pause, resume,
verify, cancel, and the file picker. So the account that started a sixty
gigabyte transfer could watch it and nothing else, and had to find an
administrator to stop one it had begun by mistake.

That was sharpest where the quota stops a transfer. A row stopped for want of
room can only be let go again by an administrator, so the person who could
actually fix it - by freeing space, or by having their games claimed - could not
then act on the result.

The ROM download routes next door settled this shape already: the scope says who
may reach the queue at all, and the handler asks who the job belongs to. Same
two questions here, in the same order, using the `_mine_only` rule this file
already had for the listing.

WIDENING A GATE IS THE DANGEROUS DIRECTION. The tests below spend most of their
length on what must STILL be refused: somebody else's transfer answers 404, the
same way the single-row read does, so the reply does not confirm that a transfer
with that number exists.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from handler.auth.scopes import Scope

ME, SOMEBODY_ELSE = 3, 1

#: What queueing a torrent needs, and therefore what controlling one needs.
UPLOADER = {Scope.LIBRARY_UPLOAD}
ADMIN = {Scope.LIBRARY_UPLOAD, Scope.LIBRARY_ADMIN}


def _request(scopes, user_id=ME):
    return SimpleNamespace(state=SimpleNamespace(
        user=SimpleNamespace(id=user_id, username="u"), scopes=set(scopes)))


@pytest.fixture
def rows(monkeypatch):
    from endpoints.torrent import torrent_router as R

    mine = SimpleNamespace(id=1, transmission_id=11, info_hash="a", total_size=10,
                           created_by_id=ME, status="downloading")
    theirs = SimpleNamespace(id=2, transmission_id=22, info_hash="b", total_size=10,
                             created_by_id=SOMEBODY_ELSE, status="downloading")
    table = {1: mine, 2: theirs}

    async def _row(dl_id):
        td = table.get(dl_id)
        if td is None:
            raise HTTPException(404, "Download not found")
        return td

    monkeypatch.setattr(R, "_download_or_404", _row)

    # Cancelling loads its own row, because it must also work on one that
    # never reached Transmission.
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

    # What reached the daemon, and under which name. A row that has a hash is
    # addressed by it: the number is renumbered by every daemon restart and
    # can belong to somebody else's torrent by then (audit finding #1).
    acted: list[tuple[str, object]] = []

    async def _pause(tid):
        acted.append(("pause", tid))
        return True

    async def _resume(tid):
        acted.append(("resume", tid))
        return True

    async def _verify(tid):
        acted.append(("verify", tid))
        return True

    async def _remove(tid, **_k):
        acted.append(("remove", tid))
        return True

    monkeypatch.setattr(R.transmission_handler, "pause_torrent", _pause)
    monkeypatch.setattr(R.transmission_handler, "resume_torrent", _resume)
    monkeypatch.setattr(R.transmission_handler, "verify_torrent", _verify)
    monkeypatch.setattr(R.transmission_handler, "remove_torrent", _remove)

    async def _status(*_a, **_k):
        return None

    monkeypatch.setattr(R, "_set_download_status", _status)

    # The limit is asked again on resume; it has its own file.
    from handler.torrent import seed_monitor as M

    async def _fits(_td, _size):
        return False

    monkeypatch.setattr(M, "_over_quota", _fits)

    # Nothing else holds these torrents here. The other case is
    # test_a_torrent_another_row_holds_is_left_to_it.py.
    async def _nobody_else(_td):
        return False

    monkeypatch.setattr(M, "held_by_another", _nobody_else)
    return SimpleNamespace(module=R, acted=acted)


@pytest.mark.asyncio
async def test_an_uploader_can_pause_their_own(rows):
    await rows.module.pause_download(_request(UPLOADER), 1)
    assert ("pause", "a") in rows.acted, (
        "konto, ktore zaczelo transfer, nadal nie moze go zatrzymac"
    )


@pytest.mark.asyncio
async def test_an_uploader_can_let_their_own_go_again(rows):
    await rows.module.resume_download(_request(UPLOADER), 1)
    assert ("resume", "a") in rows.acted


@pytest.mark.asyncio
async def test_an_uploader_can_cancel_their_own(rows):
    await rows.module.cancel_download(_request(UPLOADER), 1)
    assert ("remove", "a") in rows.acted


# ── What must still be refused ───────────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.parametrize("verb", ["pause_download", "resume_download",
                                  "verify_download", "cancel_download"])
async def test_an_uploader_cannot_touch_somebody_elses(rows, verb):
    with pytest.raises(HTTPException) as refusal:
        await getattr(rows.module, verb)(_request(UPLOADER), 2)

    assert refusal.value.status_code == 404, (
        "odmowa mowi 403, wiec potwierdza, ze transfer o tym numerze istnieje"
    )
    assert rows.acted == [], f"{verb} ruszyl cudzy transfer: {rows.acted}"


@pytest.mark.asyncio
async def test_an_account_without_the_upload_permission_gets_nowhere(rows):
    """The scope is still the first question. Only after it is answered does
    ownership come into it."""
    with pytest.raises(HTTPException) as refusal:
        await rows.module.pause_download(_request(set()), 1)
    assert refusal.value.status_code == 403


# ── And an administrator still sees to everything ────────────────────────────

@pytest.mark.asyncio
async def test_an_administrator_can_still_act_on_anybody(rows):
    """THE LEGAL CASE that the ownership check could break. An administrator is
    the one caller `_mine_only` answers None for, and they have to keep being
    able to clear up after other people."""
    await rows.module.pause_download(_request(ADMIN, user_id=SOMEBODY_ELSE), 1)
    assert ("pause", "a") in rows.acted
