"""Three ways the scan indicator said something that was not so.

1. IT SHOWED ITSELF TO PEOPLE WHO GET NO EVENTS. Progress and completion go to
   named rooms, and the status call that seeds the indicator was open to every
   account - so a player who loaded a page during a scan got a progress line
   frozen on whatever platform it first saw, for the rest of the session, and a
   Stop button that answered "Missing scopes". Who those rooms are is settled in
   test_the_scan_is_watched_by_who_can_add_things.py.

2. ONE DROPPED COMPLETION WEDGED IT FOREVER. The completion event was the only
   way out of the running phases, and it is genuinely droppable: any 401 makes
   the client tear the socket down and build a new one, and whatever is emitted
   in that gap is gone. The line then never cleared, the caller's reload never
   ran, and the Classic sidebar's sync spinner turned until somebody reloaded
   the page - which also meant no further ROM scan could be started at all.

3. A SCAN THAT COULD NOT START SAID NOTHING. An unmounted drive or a typo in the
   ROM path made the walk return in silence: 200 from the request, no completion
   event ever, and the indicator on "Starting the scan..." for good. The only
   sign was a line in the server log.
"""

from __future__ import annotations

import io
import pathlib
import re
import pytest

_BACKEND = pathlib.Path(__file__).resolve().parent.parent
_FRONTEND = _BACKEND.parent / "frontend" / "src"
_COMPOSABLE = _FRONTEND / "composables" / "useRomScan.ts"


def _read(path: pathlib.Path) -> str:
    if not path.exists():
        pytest.fail(f"brak {path} - test nie ma czego sprawdzic")
    return io.open(path, encoding="utf-8").read()


# ── 3. A scan that could not start ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_missing_rom_folder_still_announces_the_end(tmp_path, monkeypatch):
    from handler.filesystem import rom_scanner as scanner

    announced: list = []

    async def _announce(stats):
        announced.append(dict(stats))

    monkeypatch.setattr(scanner, "_announce_scan_finished", _announce)

    stats = await scanner.scan_roms_path(str(tmp_path / "nie ma takiego katalogu"))

    assert announced, (
        "skan po nieistniejacej sciezce konczy sie w ciszy, wiec wskaznik "
        "zostaje na 'Rozpoczynanie skanowania' do konca zycia strony"
    )
    assert stats["error"] == "path_missing"
    assert announced[0]["error"] == "path_missing", "koniec ogloszony bez powodu"


@pytest.mark.asyncio
async def test_an_ordinary_scan_says_nothing_about_an_error(tmp_path, monkeypatch):
    """The other half: `error` present on every scan would make the indicator
    report a broken path every time one finished."""
    from handler.filesystem import rom_scanner as scanner

    (tmp_path / "roms").mkdir()
    announced: list = []

    async def _announce(stats):
        announced.append(dict(stats))

    async def _nothing(*a, **k):
        return None

    async def _fake(value):
        async def _f(*a, **k):
            return value
        return _f

    monkeypatch.setattr(scanner, "_announce_scan_finished", _announce)
    monkeypatch.setattr(scanner.rom_platform_handler, "get_all_simple", await _fake([]))
    monkeypatch.setattr(scanner.rom_platform_handler, "rom_counts_by_fs_slug", await _fake({}))
    monkeypatch.setattr(scanner.rom_handler, "present_ids", await _fake([]))
    monkeypatch.setattr(scanner.rom_handler, "mark_all_missing", _nothing)
    monkeypatch.setattr(scanner.rom_handler, "restore_present", _nothing)

    stats = await scanner.scan_roms_path(str(tmp_path / "roms"))

    assert "error" not in stats
    assert announced and "error" not in announced[0]


# ── 1. Who the indicator is for ──────────────────────────────────────────────

# Who may watch, who may stop, and who the events are sent to are three answers
# that have to agree, and they are asserted together in
# test_the_scan_is_watched_by_who_can_add_things.py. They used to be asserted
# here as "administrators only", which was one role too few: an uploader cannot
# start a scan, but an upload starts one by itself and watching it is how they
# know their file arrived.


def test_the_indicator_does_not_draw_itself_for_other_accounts():
    source = _read(_COMPOSABLE)
    assert "useAuthStore" in source and "canWatchScan" in source, (
        "wskaznik nie pyta, kto patrzy, wiec zamarza kazdemu innemu"
    )
    # Asked once in the composable rather than in each of the three views that
    # draw it - that is the point of it living here.
    for view in ("layouts/ClassicLayout.vue", "views/emulation/EmulationHome.vue",
                 "views/emulation/EmulationLibrary.vue"):
        text = _read(_FRONTEND / view)
        assert "visible.value" in text, f"{view} nie rysuje wskaznika wcale?"


# ── 2. A dropped completion ──────────────────────────────────────────────────

def test_something_other_than_the_event_can_end_the_scan_on_screen():
    source = _read(_COMPOSABLE)
    assert "WATCHDOG_MS" in source, (
        "jedynym wyjsciem z fazy 'skanowanie' jest zdarzenie, ktore da sie "
        "zgubic przy odnowieniu gniazda - wtedy pasek zostaje na zawsze"
    )
    # The recovery has to go through the same ending as the event, or the
    # caller's reload and the sidebar's spinner are released on one path only.
    assert re.search(r"function finish\(", source), "brak wspolnego zakonczenia"
    assert source.count("finish(") >= 3, (
        "zakonczenie nie jest uzywane i przez zdarzenie, i przez dozor"
    )


def test_the_watchdog_stops_when_there_is_nothing_to_watch():
    """A timer left running is a request every ten seconds for the life of the
    session, on every page that draws this."""
    source = _read(_COMPOSABLE)
    assert "stopWatchdog" in source
    # The CALL, not the import line above it, which is what this caught first.
    at = source.index("onUnmounted(()")
    assert "stopWatchdog()" in source[at:at + 200], "dozor przezywa odmontowanie widoku"


# ── The watchdog has to be armed, not merely written ─────────────────────────
#
# Everything above asks whether the watchdog EXISTS. It can exist, be correct,
# and never run: it was started by `start()` and by the first progress event,
# and the case it was written for - a page whose socket is being rebuilt after a
# token refresh - produces neither. The catch-up call is the only thing that
# runs in that case, so it has to arm the timer as well.

def test_the_catch_up_call_arms_the_watchdog():
    source = _read(_COMPOSABLE)
    at = source.index("async function refresh(")
    body = source[at:source.index("function finish(", at)]
    assert "startWatchdog()" in body, (
        "dozor uzbraja tylko start skanu i pierwsze zdarzenie - a strona "
        "otwarta w trakcie skanu, ktorej gniazdo sie odbudowuje, nie dostaje "
        "ani jednego z nich"
    )


def test_the_watchdog_does_not_invent_a_result():
    """`/roms/scan/status` answers where a scan IS, not what it did. It carries
    no counts, so the watchdog's ending cannot report any - it used to send
    zeros, and the indicator then said "Scan finished. ROMs found: 0" after a
    scan that had added hundreds."""
    source = _read(_COMPOSABLE)
    at = source.index("async function refresh(")
    body = source[at:source.index("function finish(", at)]
    call = re.search(r"finish\(\{[^}]*\}\)", body, re.S)
    assert call, "dozor nie konczy skanu wcale?"
    assert "unknown: true" in call.group(0), (
        "dozor oglasza wynik, ktorego nie zna - zera z /scan/status czytaja sie "
        "jako 'znaleziono 0 ROM-ow'"
    )
    assert "unknown?: boolean" in source, "podsumowanie nie ma jak powiedziec 'nie wiem'"


def test_the_views_do_not_report_a_count_the_watchdog_never_had():
    """The other half of it. A flag nobody reads changes nothing on screen."""
    for view in ("layouts/ClassicLayout.vue", "views/emulation/EmulationHome.vue",
                 "views/emulation/EmulationLibrary.vue"):
        text = _read(_FRONTEND / view)
        assert "summary" not in text or "unknown" in text, (
            f"{view} pokazuje liczby z podsumowania, ktore ich nie zna"
        )


def test_the_indicator_subscribes_once_the_account_is_known():
    """`allowed` reads the account, and the account arrives from /users/me a
    round trip after mount. Subscribing only at mount therefore did nothing at
    all after an ordinary page refresh: no progress events for the whole scan,
    so the bar sat on "Starting" and the Stop button never appeared."""
    source = _read(_COMPOSABLE)
    at = source.index("onMounted(()")
    body = source[at:source.index("onUnmounted(()", at)]
    assert "watch(allowed" in body, (
        "subskrypcja zdarzen zalezy od tego, czy konto zdazylo dojsc przed "
        "zamontowaniem widoku - po odswiezeniu strony przewaznie nie zdazy"
    )
    assert "stopWatching" in source[source.index("onUnmounted(()"):], (
        "obserwator konta przezywa odmontowanie widoku"
    )
