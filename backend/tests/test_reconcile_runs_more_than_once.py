"""The pass that makes the database agree with the disk runs again.

It ran exactly once, forty-five seconds after boot, and then the process sat
there for weeks. Everything it corrects can happen at any moment - a crash
mid-write, a detached hook that never landed, a file removed from outside the
app - so a server that is never restarted is a server where the correction never
happens. That is the whole of item two.

Turning a one-shot into a loop is easy to get subtly wrong in three ways, and
each has a test here. The interval has to be read on every turn, or changing it
in settings does nothing until a restart, which is the thing being fixed.
A failure has to be survivable, or one bad pass silently ends the loop and the
symptom is identical to never having built it. And zero has to keep meaning
something deliberate rather than becoming a busy loop.

The pass itself is untouched, including its refusal to run when the games root
is absent and its holding back of storage areas that look unmounted. A missing
mount looks exactly like somebody deleting their library, and running this more
often multiplies whatever that judgement gets wrong.
"""
from __future__ import annotations

import io
import pathlib

import pytest

BACKEND = pathlib.Path(__file__).resolve().parent.parent
RECONCILE = BACKEND / "handler" / "library" / "reconcile.py"


def _source() -> str:
    return io.open(RECONCILE, encoding="utf-8").read()


# ── The interval ─────────────────────────────────────────────────────────────

def test_a_sensible_setting_is_used():
    from handler.library.reconcile import resolve_interval_hours

    assert resolve_interval_hours("6", default=12) == 6


@pytest.mark.parametrize("raw", [None, "", "soon", "-3", "3.5"])
def test_anything_that_is_not_a_whole_number_of_hours_falls_back(raw):
    """A negative interval is not an instruction, it is a typo. Falling back
    beats both crashing and treating it as zero."""
    from handler.library.reconcile import resolve_interval_hours

    assert resolve_interval_hours(raw, default=12) == 12


def test_zero_means_once_at_startup_and_no_more():
    """Which is exactly today's behaviour, kept reachable on purpose: somebody
    who wants the old shape should not have to disable a feature to get it."""
    from handler.library.reconcile import resolve_interval_hours

    assert resolve_interval_hours("0", default=12) == 0


def test_zero_can_never_become_a_busy_loop():
    """The one failure mode that would take the server down rather than leave a
    stale row. Nothing may sleep for zero seconds and go round again."""
    source = _source()
    start = source.index("async def reconcile_loop")
    body = source[start:]
    assert "if not interval" in body or "interval <= 0" in body or "interval == 0" in body, (
        "zero nie ma osobnej galezi, wiec petla moze sie zapetlic bez przerwy"
    )


# ── The loop ─────────────────────────────────────────────────────────────────

def test_the_pass_is_repeated():
    source = _source()
    start = source.index("async def reconcile_loop")
    assert "while True" in source[start:], "przebieg nadal wykonuje sie raz"


def test_the_interval_is_read_on_every_turn():
    """Read once before the loop and a change in settings would do nothing until
    the next restart, which is the thing being fixed."""
    source = _source()
    start = source.index("async def reconcile_loop")
    loop_at = source.index("while True", start)
    assert "resolve_interval_hours" in source[loop_at:], (
        "odstep czytany raz przed petla, wiec zmiana ustawienia nic nie da"
    )


def test_one_bad_pass_does_not_end_the_loop():
    """A failure used to be the end of the task. Ending quietly and never
    running again is indistinguishable from the bug this replaces."""
    source = _source()
    start = source.index("while True", source.index("async def reconcile_loop"))
    body = source[start:]
    assert body.count("except Exception") >= 1, "wyjatek nadal konczy petle"
    assert "CancelledError" in body, "petla nie da sie zatrzymac przy zamykaniu"


def test_shutdown_still_stops_it():
    """asyncio cancels these tasks on shutdown, and a bare except would swallow
    that and hang the process."""
    source = _source()
    start = source.index("async def reconcile_loop")
    body = source[start:]
    assert body.index("except asyncio.CancelledError") < body.index("except Exception"), (
        "ogolny wyjatek lapie anulowanie, wiec zamkniecie sie zawiesi"
    )


# ── What must not change ─────────────────────────────────────────────────────

def test_the_unmounted_guard_is_still_there():
    """Running this more often multiplies whatever that judgement gets wrong: a
    missing mount looks exactly like somebody having deleted their library."""
    source = _source()
    assert "_group_looks_unmounted" in source
