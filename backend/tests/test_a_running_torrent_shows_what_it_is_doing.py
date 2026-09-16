"""A transfer in flight, with something to read while it runs.

Reported by the owner after the three acceptance tests passed: "malo info jest w
tray/tacce i w zakladce settings/Transmision. nie widac ilosci peer/seed itd
podczas pobierania torrent." A torrent differs from every other transfer in this
application in one way that matters to whoever is watching it: it can sit at the
same percentage for an hour and be perfectly healthy, or be dead, and the only
thing that tells those apart is how many peers it has found. A percentage and a
speed cannot answer it.

>>> NOTHING NEW IS ASKED OF THE DAEMON. `_TORRENT_FIELDS` already requests
peersConnected, peersSendingToUs, peersGettingFromUs, rateUpload, uploadedEver,
downloadedEver, uploadRatio, isStalled and queuePosition on every call, and the
"All torrents" tab two functions away already renders all of it - which is the
proof the path works. `_fmt_download`, which feeds BOTH screens the owner named,
keeps two of those figures and drops the rest on the floor.

>>> MATCH BY HASH, NEVER BY THE DAEMON'S ID. `transmission_id` is handed out per
daemon session and reused after a restart, so the number on a months-old row can
belong to a completely different torrent today. `info_hash` is the identity that
does not move. Matching on the id would print a stranger's peers and speed
against this account's transfer, and it would look entirely plausible.

>>> AND THE PERCENTAGE IN THAT TAB HAS ALWAYS BEEN ZERO. Found while measuring
what the screen reads rather than what it draws: the route sends `percent`
(already multiplied out), the tab reads `d.percent_done`, which no reply has
ever contained. `Math.round((undefined || 0) * 1000) / 10` is 0, so the bar sits
empty and the label says 0% for the whole transfer. It is in the screen the
owner is complaining about, it is the first thing anybody looks at, and no test
covered it.
"""

from __future__ import annotations

import io
import pathlib
from types import SimpleNamespace

import pytest

from handler.auth.scopes import Scope

BACKEND = pathlib.Path(__file__).resolve().parent.parent
#: Beside the backend, in the repo AND in the test container. Computed a level
#: higher once and seven checks SKIPPED instead of running, which says nothing
#: at all - unlike a red one.
FRONTEND = BACKEND.parent / "frontend"

ME = 3
UPLOADER = {Scope.LIBRARY_UPLOAD}


def _request(scopes=UPLOADER, user_id=ME):
    return SimpleNamespace(state=SimpleNamespace(
        user=SimpleNamespace(id=user_id, username="u"), scopes=set(scopes)))


def _row(**kw):
    base = dict(
        id=1, title="Some Game", os="windows", status="downloading",
        percent_done=0.42, total_size=1000, rate_download=500, eta=120,
        error_msg=None, error_code=None, error_detail=None,
        game_id=None, library=None, created_by="gdtest", created_by_id=ME,
        created_at=None, completed_at=None,
        transmission_id=11, info_hash="AAAA",
    )
    base.update(kw)
    return SimpleNamespace(**base)


@pytest.fixture
def listing(monkeypatch):
    """The route with a stand-in database and a stand-in daemon.

    The fake session answers with fixed rows and ignores the query, which is
    fine HERE and would not be elsewhere: what is under test is the merging of
    live figures onto rows, not which rows the query selects. The tests that ask
    what the WHERE clause does run on sqlite, in the file beside this one.
    """
    from endpoints.torrent import torrent_router as R

    state: dict = {"rows": [_row()], "live": [], "boom": False}

    class _Db:
        async def execute(self, *_a, **_k):
            rows = state["rows"]
            return SimpleNamespace(scalars=lambda: SimpleNamespace(all=lambda: rows))

    class _Factory:
        def __call__(self):
            return self

        async def __aenter__(self):
            return _Db()

        async def __aexit__(self, *_a):
            return False

    from handler.database import session as S
    monkeypatch.setattr(S, "async_session_factory", _Factory())

    async def _all(*_a, **_k):
        if state["boom"]:
            raise RuntimeError("daemon went away mid-listing")
        return state["live"]

    monkeypatch.setattr(R.transmission_handler, "get_all_torrents", _all)
    return R, state


LIVE = {
    "id": 11,
    "hashString": "aaaa",
    "peersConnected": 14,
    "peersSendingToUs": 6,
    "peersGettingFromUs": 3,
    "rateUpload": 4096,
    "uploadedEver": 900,
    "downloadedEver": 4200,
    "uploadRatio": 0.2143,
    "isStalled": False,
    "queuePosition": 2,
}


# ── The figures reach the screens ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_the_listing_carries_what_the_daemon_knows(listing):
    """Asked per FIGURE, with the value the daemon gave, so a field that is
    present but wired to the wrong key fails here rather than showing a
    confident zero on screen."""
    R, state = listing
    state["live"] = [LIVE]

    out = (await R.list_downloads(_request()))[0]

    for key, expected in (
        ("peers",       14),    # everybody we are connected to
        ("peers_from",  6),     # the ones actually feeding us: the seeds
        ("peers_to",    3),
        ("rate_upload", 4096),
        ("uploaded",    900),
        ("downloaded",  4200),
        ("ratio",       0.21),
        ("stalled",     False),
        ("queue",       2),
        # Whether the daemon knows this row at all. Without it a finished
        # transfer is indistinguishable from a running one that has found
        # nobody: both answer zero to every question above. `list_seeds` next
        # door carries the same flag for the same reason.
        ("live",        True),
    ):
        assert key in out, f"lista nie podaje `{key}`, wiec ekran nie ma czego pokazac"
        assert out[key] == expected, (
            f"`{key}` = {out[key]!r}, a demon podal {expected!r} - pole jest "
            "podpiete pod zly klucz i pokaze pewna siebie zerowke"
        )


@pytest.mark.asyncio
async def test_the_figures_are_matched_by_hash_not_by_the_daemons_number(listing):
    """The trap this whole release has been walking around.

    `transmission_id` is handed out per daemon session and reused after a
    restart. Here the daemon holds a stranger under the very number this row
    remembers, and our torrent under a different one. Matching on the number
    prints the stranger's peers and speed against this account's transfer, and
    nothing about the screen would look wrong.
    """
    R, state = listing
    stranger = dict(LIVE, id=11, hashString="ffff", peersConnected=99,
                    peersSendingToUs=99, rateUpload=999999)
    ours = dict(LIVE, id=77, hashString="aaaa")
    state["live"] = [stranger, ours]

    out = (await R.list_downloads(_request()))[0]

    assert out["peers"] == 14 and out["rate_upload"] == 4096, (
        "wiersz dostal liczby CUDZEGO torrenta, bo dopasowanie idzie po numerze "
        "sesji demona zamiast po info_hash"
    )


@pytest.mark.asyncio
async def test_a_transfer_the_daemon_has_never_heard_of_still_lists(listing):
    """Every finished, refused and paused-into-oblivion row is in this state,
    and they are the rows carrying the reason a transfer stopped."""
    R, state = listing
    state["live"] = []

    out = (await R.list_downloads(_request()))[0]

    assert out["id"] == 1
    assert out["peers"] == 0 and out["ratio"] == 0
    assert out["live"] is False, (
        "wiersz twierdzi, ze demon go zna, wiec ekran pokaze zera jako pomiar"
    )
    assert out["error_msg"] is None


@pytest.mark.asyncio
async def test_a_daemon_that_falls_over_does_not_empty_the_tray(listing):
    """The tray is the only place an uploader sees their own transfers at all.
    Losing the peer counts because the daemon blinked is a nuisance; losing the
    list, and with it the reason a transfer was refused, is the complaint this
    release started from."""
    R, state = listing
    state["boom"] = True

    out = await R.list_downloads(_request())

    assert len(out) == 1, (
        "awaria demona zabiera cala liste transferow, a nie same liczby"
    )
    assert out[0]["peers"] == 0


@pytest.mark.asyncio
async def test_the_daemon_is_asked_once_for_the_whole_list(listing):
    """A round trip per row turns a page of ten transfers into ten RPC calls
    against a daemon in this same container. `list_seeds` two functions away
    already does it the right way and is where this was copied from."""
    R, state = listing
    state["rows"] = [_row(id=i, info_hash=f"{i:04x}") for i in range(1, 8)]
    state["live"] = [LIVE]

    calls = {"n": 0}
    orig = R.transmission_handler.get_all_torrents

    async def _counted(*a, **k):
        calls["n"] += 1
        return await orig(*a, **k)

    R.transmission_handler.get_all_torrents = _counted
    try:
        out = await R.list_downloads(_request())
    finally:
        R.transmission_handler.get_all_torrents = orig

    assert len(out) == 7
    assert calls["n"] == 1, f"{calls['n']} zapytan do demona na jedna liste"


@pytest.mark.asyncio
async def test_an_empty_list_does_not_wake_the_daemon(listing):
    """Measured on the live install while checking this work: the tray polls
    this route every thirty seconds from every open page, and on that server
    every row is finished - so the answer is the empty list and there is nothing
    to merge figures onto. Asking the daemon anyway is a round trip per browser
    tab per half minute, bought for nothing.

    Counted rather than made to explode: `_live_by_hash` swallows a failing
    daemon on purpose, so a call that raises would prove nothing here.
    """
    R, state = listing
    state["rows"] = []

    calls = {"n": 0}
    orig = R.transmission_handler.get_all_torrents

    async def _counted(*a, **k):
        calls["n"] += 1
        return await orig(*a, **k)

    R.transmission_handler.get_all_torrents = _counted
    try:
        assert await R.list_downloads(_request()) == []
    finally:
        R.transmission_handler.get_all_torrents = orig

    assert calls["n"] == 0, "pusta lista i tak budzi demona"


@pytest.mark.asyncio
async def test_one_row_read_on_its_own_has_the_same_shape(listing, monkeypatch):
    """`GET /downloads/{id}` returns "the same thing" as the listing, and no
    screen in this repo calls it - it is there for plugins and for anybody with
    curl. A shape that quietly loses nine fields depending on which route
    produced it is how a reader ends up printing "0 peers" against a healthy
    transfer."""
    R, state = listing
    state["live"] = [LIVE]

    class _Db:
        async def get(self, _model, _key):
            return state["rows"][0]

    class _Factory:
        def __call__(self):
            return self

        async def __aenter__(self):
            return _Db()

        async def __aexit__(self, *_a):
            return False

    from handler.database import session as S
    monkeypatch.setattr(S, "async_session_factory", _Factory())

    out = await R.get_download(_request(), 1)
    assert out["peers"] == 14 and out["peers_from"] == 6, (
        "pojedynczy wiersz oddaje inny ksztalt niz lista"
    )


# ── And they stay live between fetches ───────────────────────────────────────

def test_the_progress_event_carries_them_too():
    """The tray refetches every thirty seconds and the monitor ticks every ten,
    so between fetches the tray is driven by this event alone. An event carrying
    only percent and speed leaves the peer count frozen beside numbers that are
    moving, which reads as a broken screen rather than a stale one."""
    body = io.open(BACKEND / "handler" / "torrent" / "seed_monitor.py",
                   encoding="utf-8").read()
    at = body.index('"torrent:download_progress"')
    payload = body[at:body.index("})", at)]
    for field in ("peers", "peers_from"):
        assert f'"{field}"' in payload, (
            f"zdarzenie o postepie nie niesie `{field}`, wiec liczba peerow "
            "zamarza na pol minuty miedzy odswiezeniami"
        )


# ── The screens ──────────────────────────────────────────────────────────────

def _read(path: pathlib.Path) -> str:
    if not path.is_file():
        pytest.skip("frontend tree not present")
    return io.open(path, encoding="utf-8").read()


TRAY = FRONTEND / "src" / "components" / "gog" / "DownloadManager.vue"
TAB = FRONTEND / "src" / "views" / "settings" / "SettingsTransmission.vue"


def test_the_tray_shows_the_peers_and_the_time_left():
    """The tray row is narrow, so it gets the three that answer "is this
    moving": the seeds feeding us, everybody connected, and the time left."""
    body = _read(TRAY)
    at = body.index('v-for="tr in torrentList"')
    row = body[at:body.index("\n        </div>\n\n        <div v-for=\"job", at)]
    for expr in ("tr.peers_from", "tr.peers", "tr.eta"):
        assert expr in row, f"wiersz torrenta w tacce nie pokazuje `{expr}`"


def test_the_live_event_does_not_wipe_the_figures_it_just_drew():
    """The exact trap `created_by` fell into in this same function: the progress
    branch REBUILDS the row from the payload, so any field the event does not
    carry is erased a second after the fetch put it there. Asserted per
    assignment, because that bug was three branches out of four forgetting a
    field the fourth one set."""
    body = _read(TRAY)
    at = body.index("function handleTorrent")
    handler = body[at:body.index("\nfunction ", at + 10)]
    for field in ("peers", "peers_from", "eta"):
        assert f"{field}:" in handler, (
            f"galaz postepu przebudowuje wiersz bez `{field}`, wiec pierwszy takt "
            "kasuje to, co dopiero co pobrano"
        )


def test_the_settings_tab_shows_the_whole_set():
    """This one has room for the full picture: both directions, both peer
    counts, what has been sent and received, the ratio and the queue."""
    body = _read(TAB)
    at = body.index("v-for=\"d in downloads\"")
    row = body[at:body.index("sd-dl-actions", at)]
    for expr in ("d.rate_upload", "d.peers_from", "d.peers", "d.ratio",
                 "d.uploaded", "d.downloaded", "d.stalled"):
        assert expr in row, f"zakladka Downloads nie pokazuje `{expr}`"
    assert "d.live" in row, (
        "zakladka pokazuje liczby demona takze dla wierszy, o ktorych demon nic "
        "nie wie - a tam kazde zero jest brakiem odpowiedzi, nie pomiarem"
    )


def test_the_settings_tab_reads_the_percentage_the_route_actually_sends():
    """Always zero, for as long as this tab has existed.

    The route sends `percent`, already multiplied out and rounded. The tab
    declares and reads `percent_done`, which no reply has ever contained, so the
    bar sits empty and the label reads 0% for the whole transfer. Nothing
    crashes, nothing is logged, and it is the first thing anybody looks at.
    """
    route = io.open(BACKEND / "endpoints" / "torrent" / "torrent_router.py",
                    encoding="utf-8").read()
    at = route.index("def _fmt_download(")
    sent = route[at:route.index("\n\n", at)]
    assert '"percent_done"' not in sent, (
        "trasa zaczela oddawac percent_done - ten test bada juz co innego"
    )

    body = _read(TAB)
    at = body.index("function dlPercent")
    rule = body[at:body.index("\n}", at)]
    assert "percent_done" not in rule, (
        "zakladka liczy postep z pola, ktorego trasa nie przysyla, wiec pasek "
        "stoi pusty i etykieta pokazuje 0% przez cale pobieranie"
    )
    assert "d.percent" in rule


# ── In every language ────────────────────────────────────────────────────────

NEW_KEYS = ["transmission.col_seeds", "transmission.tstalled"]


@pytest.mark.parametrize("key", NEW_KEYS)
def test_every_language_has_a_word_for_it(key):
    import json

    en = FRONTEND / "src" / "i18n" / "en.json"
    if not en.is_file():
        pytest.skip("frontend tree not present")
    langs = sorted((FRONTEND / "public" / "i18n").glob("*.json"))
    assert len(langs) == 7, f"{len(langs)} plikow jezykowych zamiast siedmiu"
    for path in [en, *langs]:
        d = json.load(io.open(path, encoding="utf-8"))
        assert key in d, f"{path.name}: brak {key}"
