"""A library can be re-scanned on a timer, and it is off until somebody says so.

Today the only scans are the ones something asks for: a press of Scan, a finished
upload, a finished ROM download. A library that grows from outside the app - a
share somebody drops files into, a sync job, another machine - is invisible until
a person happens to press the button. That is item three.

Off by default, and that is the design rather than caution. A scan walks every
platform directory and hashes what it has not seen; on a large library over a
slow mount that is not something to start happening to people who never asked
for it. Somebody who wants it turns it on and picks the interval.

The part that actually matters here is that there is ONE lock. A timed scan that
could run beside a manual one would have two passes marking rows missing and
clearing them in each other's shadow, which is the same class of bug the comment
above mark_all_missing records: a second pass re-marking what the first had just
found. The lock already existed, in the router, and a handler was reaching across
into it to borrow it. It moves to the scanner, where the thing it guards lives,
and everyone shares the one.
"""
from __future__ import annotations

import io
import pathlib

import pytest

BACKEND = pathlib.Path(__file__).resolve().parent.parent
SCANNER = BACKEND / "handler" / "filesystem" / "rom_scanner.py"
ROUTER = BACKEND / "endpoints" / "roms" / "roms_router.py"
SOURCES = BACKEND / "handler" / "roms" / "rom_source_handler.py"


def _source(path: pathlib.Path) -> str:
    return io.open(path, encoding="utf-8").read()


# ── Off unless asked for ─────────────────────────────────────────────────────

def test_it_is_off_when_nothing_is_configured():
    from handler.filesystem.rom_scanner import resolve_scan_interval_hours

    assert resolve_scan_interval_hours(None) == 0


@pytest.mark.parametrize("raw", ["", "later", "-2", "2.5"])
def test_anything_that_is_not_a_whole_number_of_hours_leaves_it_off(raw):
    """Off is the safe reading of a value nobody can act on. A scan started by
    a typo is a scan nobody asked for."""
    from handler.filesystem.rom_scanner import resolve_scan_interval_hours

    assert resolve_scan_interval_hours(raw) == 0


def test_a_setting_turns_it_on():
    from handler.filesystem.rom_scanner import resolve_scan_interval_hours

    assert resolve_scan_interval_hours("12") == 12


# ── One lock, shared by everybody ────────────────────────────────────────────

def test_the_lock_lives_with_the_thing_it_guards():
    """It was in the router, and a handler was reaching across to borrow it."""
    assert "_scan_lock = asyncio.Lock()" in _source(SCANNER)


def test_nobody_keeps_a_second_lock():
    """Two locks is no lock. A timed scan running beside a manual one gives two
    passes marking rows missing in each other's shadow."""
    assert "asyncio.Lock()" not in _source(ROUTER), "router nadal ma wlasny zamek"


def test_the_router_and_the_source_handler_use_the_shared_one():
    for path in (ROUTER, SOURCES):
        source = _source(path)
        assert "rom_scanner" in source and "_scan_lock" in source, (
            f"{path.name} nie uzywa wspolnego zamka"
        )


def test_a_scan_already_running_is_not_queued_behind():
    """Waiting would mean a timer that fell behind spent the night running the
    scans it had missed, one after another. Skipping is the honest answer: the
    next tick is soon enough."""
    source = _source(SCANNER)
    start = source.index("async def periodic_scan_loop")
    body = source[start:]
    assert "locked()" in body, "petla czeka na zamek zamiast pominac obrot"


# ── The loop ─────────────────────────────────────────────────────────────────

def test_the_interval_is_read_on_every_turn():
    source = _source(SCANNER)
    start = source.index("async def periodic_scan_loop")
    loop_at = source.index("while True", start)
    assert "resolve_scan_interval_hours" in source[loop_at:], (
        "odstep czytany raz, wiec wlaczenie wymagaloby restartu"
    )


def test_being_off_does_not_end_the_task():
    """Off has to stay switchable. If the loop returned when it found zero,
    turning it on later would do nothing until a restart - and the setting would
    look broken rather than delayed."""
    source = _source(SCANNER)
    start = source.index("async def periodic_scan_loop")
    body = source[start:source.index("\nasync def ", start + 10) if "\nasync def " in source[start:] else len(source)]
    assert "return" not in body.split("while True")[1][:600], (
        "petla konczy sie, gdy skan jest wylaczony, wiec wlaczenie nie zadziala"
    )


def test_one_bad_scan_does_not_end_the_loop():
    source = _source(SCANNER)
    start = source.index("async def periodic_scan_loop")
    body = source[start:]
    assert "except Exception" in body
    assert body.index("except asyncio.CancelledError") < body.index("except Exception"), (
        "ogolny wyjatek lapie anulowanie, wiec zamkniecie sie zawiesi"
    )
