"""A scan you can watch, and stop without losing half the library.

The whole status of a running scan was one boolean, polled every two seconds by
three different views. No counter, no filename, and no way to stop it. On a
library of discs that is a progress bar that says "yes" for two hours.

THE DANGEROUS HALF IS STOPPING IT. A scan opens by marking every ROM missing and
relies on the walk to un-mark what it finds, so a scan abandoned halfway leaves
everything it had not reached yet marked missing - the library goes half empty,
and nothing says why. Cancellation is therefore not "stop the loop": a cancelled
scan does not get to claim anything is missing at all, and puts back exactly the
snapshot it took before it started. The next complete scan is what decides.
"""
from __future__ import annotations

import pytest

from handler.filesystem import rom_scanner


@pytest.fixture(autouse=True)
def _clean():
    rom_scanner.reset_scan_progress()
    yield
    rom_scanner.reset_scan_progress()


# ── What a watcher can see ───────────────────────────────────────────────────


def test_an_idle_scanner_says_so():
    snap = rom_scanner.scan_progress()
    assert snap["running"] is False
    assert snap["files_done"] == 0


def test_progress_reports_where_it_is():
    rom_scanner.begin_scan_progress(platform_total=3)
    rom_scanner.note_scan_platform("Amiga", index=1, files_total=9)
    rom_scanner.note_scan_file("Gra.lha", done=4)

    snap = rom_scanner.scan_progress()
    assert snap["running"] is True
    assert snap["platform"] == "Amiga"
    assert (snap["platform_index"], snap["platform_total"]) == (1, 3)
    assert (snap["files_done"], snap["files_total"]) == (4, 9)
    assert snap["current"] == "Gra.lha"


def test_the_snapshot_is_a_copy():
    """A watcher holding the dict must not be able to change the scanner's
    state, and must not see it mutate under them mid-render."""
    rom_scanner.begin_scan_progress(platform_total=1)
    snap = rom_scanner.scan_progress()
    snap["files_done"] = 999
    assert rom_scanner.scan_progress()["files_done"] == 0


def test_finishing_puts_it_back_to_idle():
    rom_scanner.begin_scan_progress(platform_total=1)
    rom_scanner.note_scan_file("a", done=1)
    rom_scanner.reset_scan_progress()
    assert rom_scanner.scan_progress()["running"] is False


# ── Asking it to stop ────────────────────────────────────────────────────────


def test_a_scan_that_was_not_asked_to_stop_carries_on():
    rom_scanner.begin_scan_progress(platform_total=1)
    assert rom_scanner.scan_cancelled() is False


def test_asking_it_to_stop_is_visible_to_the_walk_and_to_watchers():
    rom_scanner.begin_scan_progress(platform_total=1)
    assert rom_scanner.request_scan_stop() is True
    assert rom_scanner.scan_cancelled() is True
    assert rom_scanner.scan_progress()["cancelling"] is True


def test_asking_an_idle_scanner_to_stop_does_nothing():
    """Not an error, and not a flag left lying around for the next scan to trip
    over the moment it starts."""
    assert rom_scanner.request_scan_stop() is False
    rom_scanner.begin_scan_progress(platform_total=1)
    assert rom_scanner.scan_cancelled() is False


def test_starting_a_scan_clears_a_stop_from_the_last_one():
    rom_scanner.begin_scan_progress(platform_total=1)
    rom_scanner.request_scan_stop()
    rom_scanner.reset_scan_progress()
    rom_scanner.begin_scan_progress(platform_total=1)
    assert rom_scanner.scan_cancelled() is False, (
        "nowy skan startuje z prosba o zatrzymanie po poprzednim"
    )


# ── The half that can empty a library ────────────────────────────────────────


def test_a_cancelled_scan_restores_what_it_marked_missing():
    """The rule: a scan that did not finish makes no claim about what is
    missing. Everything it marked missing on the way in goes back exactly as it
    was, and the next complete scan decides."""
    import io
    import pathlib

    source = io.open(
        pathlib.Path(__file__).resolve().parent.parent
        / "handler" / "filesystem" / "rom_scanner.py",
        encoding="utf-8").read()
    walk = source.index("async def scan_roms_path")
    body = source[walk:]
    assert "restore_present" in body, (
        "przerwany skan nie przywraca stanu sprzed siebie, wiec zostawia "
        "polowe biblioteki oznaczona jako zaginiona"
    )
    # And it restores the snapshot it actually took, not some other set.
    at = body.index("restore_present")
    assert "present_before" in body[at - 200:at + 200]


def test_the_restore_is_one_statement_not_one_per_row():
    """A library that has just been marked missing is every row there is, and
    putting them back one at a time is the same mistake the pre-pass made."""
    import inspect

    from handler.database.rom_handler import rom_handler

    src = inspect.getsource(rom_handler.restore_present.__wrapped__)
    assert "in_(" in src, "przywracanie idzie wiersz po wierszu"


def test_a_stopped_scan_still_announces_that_it_ended():
    """Both exits have to tell the watchers, or the ones who stopped it wait
    for ever.

    The views hang their "and now reload the list" on the completion event, and
    the Classic sidebar clears its spinner there. A stop that returned without
    announcing anything left that spinner turning until the page was reloaded,
    and the list showing what it had before the scan.
    """
    import io
    import pathlib

    source = io.open(
        pathlib.Path(__file__).resolve().parent.parent
        / "handler" / "filesystem" / "rom_scanner.py",
        encoding="utf-8").read()
    walk = source.index("async def scan_roms_path")
    body = source[walk:]

    # EVERY exit announces, and by the same call - asserting on the event name
    # would only pin whichever exit happened to inline it, which is how the
    # first version of this test failed against a correct refactor. Counted
    # against the exits rather than pinned to a number, because a new way out
    # of this function is exactly the thing that should be caught here: the
    # third one, the ROM folder not being there, was added later and returned
    # in silence for a release.
    # Counting `return stats` misses the exit that LEAVES BY RAISING, and that
    # is the exit which announced nothing for a release: the bar went on turning
    # until the client watchdog filled it in as an ordinary finish. So the exits
    # are the returns plus the failure, and shutting down is deliberately not one
    # of them - the socket is going away with the process.
    returns = body.count("return stats")
    assert returns >= 3, "test nie widzi juz wszystkich wyjsc z funkcji"
    assert body.count("_announce_scan_finished(") == returns + 1, (
        "jakies wyjscie ze skanu nie oglasza konca, wiec wskaznik na nim zawisa"
    )

    failed_at = body.index("except BaseException:")
    failed = body[failed_at:body.index("\n        raise", failed_at)]
    assert "_announce_scan_finished(" in failed, (
        "skan przerwany bledem nic nie oglasza"
    )
    assert 'stats["error"]' in failed, (
        "zdarzenie nie mowi, ze to byla awaria, wiec ekran narysuje zwykle "
        "zakonczenie"
    )
    cancelled_at = body.index("except asyncio.CancelledError:")
    cancelled = body[cancelled_at:body.index("\n        raise", cancelled_at)]
    assert "_announce_scan_finished(" not in cancelled, (
        "zamykanie serwera probuje jeszcze cos wyslac po gniezdzie, ktore znika"
    )

    cancel_at = body.index('stats["cancelled"] = True')
    branch_end = body.index("return stats", cancel_at)
    assert "_announce_scan_finished(" in body[cancel_at:branch_end], (
        "zatrzymany skan nie oglasza, ze sie skonczyl, wiec widoki czekaja w "
        "nieskonczonosc"
    )


def test_the_announcement_says_which_of_the_two_it_was():
    """A screen that says "found 0 ROMs" after a stop is lying about a scan that
    never looked, so the flag has to be on the payload BEFORE it is sent."""
    import io
    import pathlib

    source = io.open(
        pathlib.Path(__file__).resolve().parent.parent
        / "handler" / "filesystem" / "rom_scanner.py",
        encoding="utf-8").read()
    flag_at = source.index('stats["cancelled"] = True')
    announce_at = source.index("_announce_scan_finished(stats)", flag_at)
    assert flag_at < announce_at, (
        "flaga o przerwaniu ustawiana po ogloszeniu, wiec nie trafi do odbiorcy"
    )


# ── The routes ───────────────────────────────────────────────────────────────


def test_stopping_a_scan_needs_the_same_permission_as_starting_one():
    import endpoints.roms.roms_router as rr
    from handler.auth.scopes import Scope

    assert rr.stop_scan.required_scopes == (Scope.PLATFORMS_WRITE,)


def test_the_status_route_answers_with_the_whole_snapshot():
    """A client that joined mid-scan has missed every event so far, and this one
    call is how it catches up."""
    import inspect

    import endpoints.roms.roms_router as rr

    src = inspect.getsource(rr.scan_status.__wrapped__)
    assert "scan_progress()" in src, (
        "status skanu nadal zwraca sam boolean, wiec klient ktory dolaczyl w "
        "trakcie nie ma jak sie dowiedziec, gdzie skan jest"
    )
