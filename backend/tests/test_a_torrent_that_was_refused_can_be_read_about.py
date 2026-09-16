"""Two rooms and two routes that were asked different questions.

THE SCAN ROOM. `scan_watcher_room` puts a socket in `scan:watchers` for
LIBRARY_UPLOAD or PLATFORMS_WRITE. `GET /roms/scan/status` asks for ROMS_READ,
and `protected_route` requires every scope it lists. Those are not the same
question, and the gap is reachable: `access_emulation: false` strips ROMS_READ
and PLATFORMS_READ while leaving the role and its upload permission alone. Such
an account is sent progress it cannot fetch - a bar drawn on screen that no
catch-up call will ever fill, and a refusal disappearing into a catch every ten
seconds. The comment above the room says the three answers have to agree; this
makes them.

THE TORRENT. Adding one needs LIBRARY_UPLOAD. Reading the list of downloads
needed LIBRARY_ADMIN, which an uploader does not have - so when a transfer was
refused for want of quota, the reason written into `error_msg` sat in a table
the account that started it could not read. The live event does not cover it
either: the views subscribe inside `submitTorrent()` and drop the subscription
with the component, so a reload - during a transfer that runs for hours, which
is the ordinary case - loses it.

So the list is declared against the permission that adds a torrent, and shows
that account its own transfers. An administrator still sees all of them.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from handler.auth.scopes import Scope

ME, SOMEBODY_ELSE = 7, 9


def _request(scopes, user_id=ME):
    return SimpleNamespace(state=SimpleNamespace(
        user=SimpleNamespace(id=user_id, username="u"), scopes=set(scopes)))


# ── Who may follow a scan ────────────────────────────────────────────────────

def test_an_account_that_cannot_read_roms_is_not_put_in_the_room():
    from handler.socket_handler import scan_watcher_room

    assert scan_watcher_room({Scope.LIBRARY_UPLOAD}) is None, (
        "konto bez ROMS_READ siedzi w pokoju postepu skanu, a trasa statusu "
        "odmawia mu - pasek, ktorego nie da sie napelnic"
    )
    assert scan_watcher_room({Scope.PLATFORMS_WRITE}) is None


def test_an_uploader_who_can_read_roms_still_follows_it():
    """The case the room exists for. Closing the gap by emptying the room would
    take the indicator away from everybody who should have it."""
    from handler.socket_handler import SCAN_WATCHER_ROOM, scan_watcher_room

    assert scan_watcher_room(
        {Scope.ROMS_READ, Scope.LIBRARY_UPLOAD}) == SCAN_WATCHER_ROOM
    assert scan_watcher_room(
        {Scope.ROMS_READ, Scope.PLATFORMS_WRITE}) == SCAN_WATCHER_ROOM


def test_reading_roms_alone_is_not_enough():
    """Everybody can read ROMs. The room is for accounts that put things in the
    library or run the scan, which is what makes it worth watching."""
    from handler.socket_handler import scan_watcher_room

    assert scan_watcher_room({Scope.ROMS_READ}) is None


def test_the_room_asks_for_everything_the_status_route_asks_for():
    """The pair. Whoever is sent the events has to be able to fetch the status,
    or the bar cannot be caught up after a dropped connection."""
    import inspect

    from endpoints.roms import roms_router
    from handler.socket_handler import scan_watcher_room

    source = inspect.getsource(roms_router)
    at = source.index('"/scan/status"')
    declared = source[source.rindex("scopes=[", 0, at + 200):]
    declared = declared[:declared.index("]")]
    for name in ("ROMS_READ",):
        assert name in declared, "test nie odtwarza deklaracji trasy statusu"
    assert scan_watcher_room({Scope.LIBRARY_UPLOAD}) is None, (
        "trasa statusu zada ROMS_READ, a pokoj o niego nie pyta"
    )


# ── Who may read about their own torrent ─────────────────────────────────────

class _Result:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)


class _Session:
    def __init__(self, rows):
        self.rows = rows
        self.seen = None

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def execute(self, stmt):
        self.seen = str(stmt)
        return _Result(self.rows)

    async def get(self, _model, dl_id):
        return next((r for r in self.rows if r.id == dl_id), None)


def _download(dl_id, owner):
    """The columns `_fmt_download` reads, and no invented ones.

    The first version of this fixture made up field names, so the route raised
    AttributeError and the tests failed for a reason that had nothing to do
    with permissions.
    """
    return SimpleNamespace(
        id=dl_id, created_by_id=owner, created_by=f"user{owner}",
        title=f"Game {dl_id}", os="windows", status="error",
        error_msg="This torrent is larger than what is left of this account's "
                  "upload quota.",
        percent_done=0.0, total_size=0, rate_download=0, eta=-1,
        game_id=None, library=None, created_at=None, completed_at=None,
    )


@pytest.fixture
def torrents(monkeypatch):
    import handler.database.session as session_mod
    from endpoints.torrent import torrent_router as R

    rows = [_download(1, ME), _download(2, SOMEBODY_ELSE)]
    session = _Session(rows)
    monkeypatch.setattr(session_mod, "async_session_factory", lambda: session)
    return R, session


@pytest.mark.asyncio
async def test_an_uploader_sees_the_transfer_they_started(torrents):
    R, _session = torrents

    listed = await R.list_downloads(_request({Scope.LIBRARY_UPLOAD}))

    assert [d["id"] for d in listed] == [1], (
        "konto, ktore zaczelo pobieranie, nie moze przeczytac, dlaczego zostalo "
        "odrzucone - powod siedzi w kolumnie widocznej tylko dla admina"
    )
    assert "quota" in listed[0]["error_msg"]


@pytest.mark.asyncio
async def test_an_uploader_does_not_see_somebody_elses(torrents):
    R, _session = torrents

    listed = await R.list_downloads(_request({Scope.LIBRARY_UPLOAD}))

    assert 2 not in [d["id"] for d in listed]


@pytest.mark.asyncio
async def test_an_administrator_still_sees_them_all(torrents):
    R, _session = torrents

    listed = await R.list_downloads(
        _request({Scope.LIBRARY_UPLOAD, Scope.LIBRARY_ADMIN}, user_id=1))

    assert sorted(d["id"] for d in listed) == [1, 2]


@pytest.mark.asyncio
async def test_one_transfer_is_readable_by_the_account_that_started_it(torrents):
    R, _session = torrents

    assert (await R.get_download(_request({Scope.LIBRARY_UPLOAD}), 1))["id"] == 1


@pytest.mark.asyncio
async def test_one_transfer_is_not_readable_by_anybody_else(torrents):
    from fastapi import HTTPException

    R, _session = torrents

    with pytest.raises(HTTPException) as refusal:
        await R.get_download(_request({Scope.LIBRARY_UPLOAD}), 2)
    assert refusal.value.status_code in (403, 404)
