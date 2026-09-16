"""An uploader's torrent had nowhere at all to appear.

MEASURED ON THE LIVE INSTALL, which is the only reason this was found. Over four
hours, `GET /api/torrents/downloads` was requested 147 times and every single
one came from the administrator's browser. gdtest, who queued the transfer,
asked `/api/torrents/enabled`, posted the magnet twice, and never once asked
what happened to it - because nothing in any skin ever asks on that account's
behalf.

The route was never the problem. It admits LIBRARY_UPLOAD and narrows the answer
to the caller's own rows, and its own comment says why: the account that was
refused for want of quota is the one that needs to read `error_msg`. The only
screen that calls it is Settings > Transmission, carrying `adminOnly: true`.

FLIPPING THAT FLAG WOULD BE THE WRONG FIX and was rejected for a reason: the
Transmission tab is an administrator's screen with five panels on it - session
limits, the daemon's whole torrent list, seeds, statistics - and the transfer
list is one of them. Opening all of that to reach one panel is how a role gate
turns into a hole.

The transfer tray is where the other four kinds of transfer already live: GOG
jobs, packaged files, URL uploads, ROM-source downloads and disc conversions.
Torrents were the only kind missing from it, and the tray was opened to
uploaders yesterday. So that is where this goes.

A NOTE ON WHAT THIS FILE CAN AND CANNOT DO. There is no JavaScript test runner
in this project, so these read the source as text. That catches only what was
thought of, which is exactly how the monitor came to crash every ten seconds
under eleven green tests. Each assertion below therefore anchors on an
INSTRUCTION - a call with its bracket, a registered event name - never on a word
that could turn up in a comment. What the tray does with what it receives is
still only proved by opening it.
"""

from __future__ import annotations

import io
import pathlib

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
FRONTEND = ROOT / "frontend" / "src"

#: Everything the monitor emits about a torrent. `refused` is new: it is what a
#: transfer turned away for want of quota now sends, and until this change
#: nothing anywhere listened to ANY of these four.
EVENTS = [
    "torrent:download_progress",
    "torrent:download_complete",
    "torrent:download_error",
    "torrent:download_refused",
]


def _read(path: pathlib.Path) -> str:
    if not path.is_file():
        pytest.skip("frontend tree not present")
    return io.open(path, encoding="utf-8").read()


# ── The socket store has to carry the events at all ──────────────────────────

@pytest.mark.parametrize("event", EVENTS)
def test_the_socket_store_listens_for_each_torrent_event(event):
    """The backend has emitted these for months into a room nobody joined."""
    body = _read(FRONTEND / "stores" / "socket.ts")
    assert f'socket.value.on("{event}"' in body, (
        f"nikt nie sluchna zdarzenia {event}, wiec serwer mowi w prozne"
    )


def test_the_store_hands_the_subscription_out():
    """A listener registered and never exported is a listener nothing can use."""
    body = _read(FRONTEND / "stores" / "socket.ts")
    at = body.rindex("return {")
    exported = body[at:body.index("}", at)]
    assert "onTorrent" in exported, (
        "subskrypcja torrentow nie jest zwracana ze sklepu gniazda"
    )


# ── The tray asks, listens, and lets go ──────────────────────────────────────

TRAY = FRONTEND / "components" / "gog" / "DownloadManager.vue"


def test_the_tray_asks_the_server_what_is_running():
    """The live events alone are not enough and that is the second half of the
    complaint: a torrent runs for hours, so a reload has to be able to find one
    that started before the page did. Every other section in this tray already
    rehydrates this way."""
    body = _read(TRAY)
    assert "client.get('/torrents/downloads')" in body or \
           'client.get("/torrents/downloads")' in body, (
        "tacka nie pyta serwera o trwajace torrenty, wiec po odswiezeniu strony "
        "transfer znika z ekranu, chociaz trwa"
    )
    # And it is CALLED. A fetcher that exists and is never reached is the same
    # empty screen with more code behind it, and asking only whether the string
    # appears in the file cannot tell the two apart.
    at = body.index("onMounted(")
    setup = body[at:body.index("})", at)]
    assert "fetchTorrentJobs()" in setup, (
        "pobranie listy torrentow istnieje, ale nikt go nie wola przy otwarciu "
        "tacki"
    )


def test_the_tray_subscribes_and_unsubscribes():
    body = _read(TRAY)

    at = body.index("onMounted(")
    setup = body[at:body.index("})", at)]
    assert "socketStore.onTorrent(handleTorrent)" in setup, (
        "tacka nie zapisuje sie na zdarzenia torrenta przy otwarciu"
    )

    at = body.index("onUnmounted(")
    teardown = body[at:body.index("})", at)]
    assert "unsubTorrent()" in teardown, (
        "subskrypcja zostaje po zamknieciu komponentu - to wyciek nasluchu przy "
        "kazdym przelaczeniu ekranu"
    )


def test_the_tray_counts_torrents_among_its_transfers():
    """The tray hides itself when it has nothing, and the badge says how many.
    A section left out of both is invisible even while it is drawing rows."""
    body = _read(TRAY)
    at = body.index('class="dm-header"')
    header = body[max(0, at - 400):at]
    assert "torrentList.length" in header, (
        "tacka nie liczy torrentow do swojej widocznosci, wiec konto z samym "
        "torrentem nadal nie widzi nic"
    )

    badge_at = body.index('class="dm-badge"')
    badge = body[badge_at:badge_at + 260]
    assert "torrentList.length" in badge, "licznik na tacce pomija torrenty"


def test_a_torrent_that_was_turned_away_says_so_on_the_tray():
    """`error_msg` is the whole reason the route was widened to the uploader.
    Carrying the row and dropping its reason would repeat the upload dialog that
    said "0 ROM(s) uploaded successfully" after refusing four files."""
    body = _read(TRAY)
    at = body.index("function handleTorrent")
    handler = body[at:body.index("\nfunction ", at + 10)]
    assert "error" in handler and "refused" in handler, (
        "tacka nie przenosi powodu odmowy, wiec konto widzi znikajacy transfer "
        "bez wyjasnienia"
    )


# ── What makes this one core change reach all three skins ────────────────────
#
# CHECKED BEFORE WRITING THE CODE, because the assumption went the other way
# twice in this release and cost a wasted fix each time. The refused-upload
# message was invisible to the owner because Vapor keeps its OWN copy of that
# dialog; the tray is the opposite case. Both themes render the core component:
#
#   VaporLayout.vue:155        <DownloadManager v-if="canSeeTransfers" />
#   NeonHorizonLayout.vue:150  <DownloadManager v-if="canSeeTransfers" />
#
# so torrents added to the core tray appear in all three skins with no theme
# change at all. That is a property worth holding onto: the day a theme forks
# this component, the fix stops travelling and nobody finds out for a release.
#
# Sibling checkouts, absent from the image and from CI, so these skip there and
# run here - the same reasoning as at the end of
# test_the_transfer_tray_shows_whose_transfer_it_is.py.

THEME_LAYOUTS = [
    ROOT.parent / "vapor_build" / "gd3-vapor" / "VaporLayout.vue",
    ROOT.parent / "nh_build" / "neon-horizon" / "NeonHorizonLayout.vue",
]


@pytest.mark.parametrize("path", THEME_LAYOUTS, ids=lambda p: p.name)
def test_each_theme_still_renders_the_core_tray_rather_than_a_copy(path):
    if not path.is_file():
        pytest.skip(f"{path.name} is a sibling checkout, absent here")
    body = io.open(path, encoding="utf-8").read()
    assert "<DownloadManager" in body, (
        f"{path.name} przestal renderowac tacke rdzenia - jesli ma teraz wlasna "
        "kopie, to torrenty trzeba dolozyc TAKZE tam, bo poprawka w rdzeniu "
        "przestala do niego docierac"
    )
    assert "canSeeTransfers" in body, (
        f"{path.name} znowu bramkuje tacke czyms innym niz uprawnienie"
    )
