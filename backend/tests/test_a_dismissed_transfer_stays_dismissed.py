"""Transfers dismissed from the list came back on every reload.

Reported by the owner from the tray, with a screenshot: three finished transfers
sitting there marked Cancelled, and no way to be rid of them. "nie da sie
usuniac tych przerwanych ... one tam ciagle sa nawet po refresh strony".

THE ROUTE ALREADY SAYS WHAT SHOULD HAPPEN, in its own first line:

    \"\"\"Stop and delete a running one, or drop a finished one from the list.\"\"\"

It writes `status = "removed"` and does not delete the row, which is right - the
game the transfer became is still in the library and the row is what connects
the two. What never happened is the second half of that sentence. The listing
returned every row it had, so a transfer somebody had explicitly dropped came
back at the next fetch, for ever.

That was invisible while the only screen showing this list was the
administrator's Transmission tab, where a long history reads as a log. In a tray
meant to show what is happening now, it is three dead rows and a badge counting
them.

"removed" is the one status that means a person has said they are done with it.
Nothing else is hidden: complete, error and paused all stay, because they are
things that happened rather than things somebody dismissed - and the reason a
transfer was refused lives on one of them.

WHY THIS RUNS AGAINST A REAL DATABASE. The first version of this file used a
fake session whose `execute` handed back whatever rows it had been given,
ignoring the query. That fake cannot tell a filtered SELECT from an unfiltered
one, so every assertion here would have passed against the unfixed route and
gone on passing if the WHERE clause were deleted. sqlite runs the statement.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from handler.auth.scopes import Scope
from models.library_file import LibraryFile
from models.library_game import LibraryGame
from models.torrent_download import TorrentDownload
from models.user import User

ME = 3
ALL_STATES = ["downloading", "paused", "complete", "error", "removed"]


@pytest_asyncio.fixture
async def db(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    async with engine.begin() as conn:
        for table in (User, LibraryGame, LibraryFile, TorrentDownload):
            await conn.run_sync(table.__table__.create)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async with maker() as session:
        for i, state in enumerate(ALL_STATES, start=1):
            session.add(TorrentDownload(
                id=i, title=f"gra {i}", os="windows", download_dir=f"/d/{i}",
                status=state, percent_done=1.0, total_size=10, transmission_id=i,
                created_by="gdtest", created_by_id=ME, uploaded_by_id=ME))
        await session.commit()

    from handler.database import session as S
    monkeypatch.setattr(S, "async_session_factory", maker)
    yield maker
    await engine.dispose()


def _request(scopes, user_id=ME, name="gdtest"):
    return SimpleNamespace(state=SimpleNamespace(
        user=SimpleNamespace(id=user_id, username=name), scopes=set(scopes)))


@pytest.mark.asyncio
async def test_a_transfer_somebody_dismissed_does_not_come_back(db):
    from endpoints.torrent import torrent_router as R

    out = await R.list_downloads(_request({Scope.LIBRARY_UPLOAD}))

    states = {row["status"] for row in out}
    assert "removed" not in states, (
        "transfer zdjety z listy wraca przy nastepnym pobraniu, wiec po "
        f"odswiezeniu strony jest z powrotem: {states}"
    )


@pytest.mark.asyncio
async def test_everything_that_merely_happened_is_still_there(db):
    """THE LEGAL CASE, and the one a careless filter would take with it. Only
    "removed" means somebody said they were done. Finished, failed and paused
    are things that happened, and hiding those would hide the answer - including
    the message saying why a transfer was refused."""
    from endpoints.torrent import torrent_router as R

    out = await R.list_downloads(_request({Scope.LIBRARY_UPLOAD}))

    assert {row["status"] for row in out} == {
        "downloading", "paused", "complete", "error"}


@pytest.mark.asyncio
async def test_an_administrator_sees_the_same_rule(db):
    """The administrator's Transmission tab reads the same route. A dismissed
    transfer is dismissed for everybody; the row stays in the database, which is
    what keeps a finished game connected to the download it came from."""
    from endpoints.torrent import torrent_router as R

    out = await R.list_downloads(
        _request({Scope.LIBRARY_UPLOAD, Scope.LIBRARY_ADMIN}, user_id=1,
                 name="60plus"))

    assert "removed" not in {row["status"] for row in out}
    assert len(out) == 4, "admin przestal widziec cudze transfery"


@pytest.mark.asyncio
async def test_dismissing_one_takes_it_off_the_list_for_good(db, monkeypatch):
    """The whole journey, end to end: a finished transfer is listed, somebody
    dismisses it, and it is gone from the next fetch. This is the sentence the
    route has always promised."""
    from endpoints.torrent import torrent_router as R

    async def _remove(_tid, **_k):
        return True

    monkeypatch.setattr(R.transmission_handler, "remove_torrent", _remove)

    caller = _request({Scope.LIBRARY_UPLOAD})
    before = {row["id"] for row in await R.list_downloads(caller)}
    assert 3 in before, "zakonczony transfer nie byl w ogole na liscie"

    await R.cancel_download(caller, 3)

    after = {row["id"] for row in await R.list_downloads(caller)}
    assert 3 not in after, (
        "transfer zdjety przyciskiem nadal jest na liscie - dokladnie to widzial "
        "wlasciciel po odswiezeniu strony"
    )
    assert after == before - {3}, "zniknelo cos jeszcze poza zdjetym transferem"


@pytest.mark.asyncio
async def test_the_row_is_kept_rather_than_deleted(db):
    """Marked, not deleted. The game a finished torrent became is in the
    library, and this row is what ties them together - the backfill in main.py
    reads exactly that link."""
    from sqlalchemy import select

    from endpoints.torrent import torrent_router as R

    async def _remove(_tid, **_k):
        return True

    R.transmission_handler.remove_torrent = _remove
    await R.cancel_download(_request({Scope.LIBRARY_UPLOAD}), 3)

    async with db() as session:
        row = (await session.execute(
            select(TorrentDownload).where(TorrentDownload.id == 3)
        )).scalar_one_or_none()

    assert row is not None, "wiersz zostal skasowany, a mial tylko zniknac z listy"
    assert row.status == "removed"


# ── The one thing "removed" must NOT swallow ─────────────────────────────────

@pytest.mark.asyncio
async def test_a_transfer_refused_for_quota_is_still_shown_with_its_reason(db):
    """Two changes made hours apart, each right on its own, wrong together.

    The quota refusal takes the transfer off the daemon and writes the row
    `status="removed"` with the reason in `error_msg`. The filter above then
    hides everything marked "removed". So the one row whose whole purpose is to
    explain itself became the one row nobody could see - and the account was
    back to watching a transfer vanish with no word, which is exactly what the
    visibility work existed to end.

    The two meanings had been sharing a word. A person pressing the cross means
    "I am done with this, take it away". The monitor means "this was turned
    away, here is why". Only the first is a dismissal.
    """
    from sqlalchemy import update

    from endpoints.torrent import torrent_router as R
    from handler.torrent import seed_monitor as M

    async with db() as session:
        await session.execute(
            update(TorrentDownload).where(TorrentDownload.id == 1).values(
                status=M.REFUSED_STATUS,
                error_msg="Refused: this torrent is 21.34 GB and only 3.34 GB is left "
                          "of this account's upload quota."))
        await session.commit()

    out = await R.list_downloads(_request({Scope.LIBRARY_UPLOAD}))

    odmowiony = [row for row in out if row["id"] == 1]
    assert odmowiony, (
        "transfer odrzucony za limit zniknal z listy razem z powodem - konto "
        "widzi, jak pobieranie znika bez slowa"
    )
    assert "GB" in (odmowiony[0]["error_msg"] or ""), (
        f"wiersz jest, ale powodu nie niesie: {odmowiony[0]}"
    )


def test_the_two_meanings_do_not_share_a_word():
    """Structural, and the point is that they can never be merged back by
    somebody tidying up: the status a refusal writes has to differ from the one
    the listing hides."""
    from endpoints.torrent import torrent_router as R
    from handler.torrent import seed_monitor as M

    assert M.REFUSED_STATUS != R.DISMISSED_STATUS, (
        "odmowa i zdjecie z listy zapisuja ten sam stan, wiec odmowa znowu "
        "zniknie razem z wyjasnieniem"
    )


# ── And the tray needs the button that does it ───────────────────────────────

def test_the_tray_offers_a_way_to_dismiss_one():
    """Filtering is half the answer. Without a button the only place to dismiss
    a transfer is the administrator's settings screen, which is where this
    started."""
    import io
    import pathlib

    tray = (pathlib.Path(__file__).resolve().parent.parent.parent
            / "frontend" / "src" / "components" / "gog" / "DownloadManager.vue")
    if not tray.is_file():
        pytest.skip("frontend tree not present")
    body = io.open(tray, encoding="utf-8").read()

    at = body.index('v-for="tr in torrentList"')
    row = body[at:body.index('<div v-for="job in jobs"', at)]
    assert "torrentDismiss(tr)" in row, (
        "wiersz torrenta nie ma czym sie zamknac, wiec zostaje w tacce na stale"
    )
    assert "client.delete(`/torrents/downloads/" in body, (
        "tacka nie wola trasy, ktora zdejmuje transfer z listy"
    )
