"""What the dashboard says a download is doing right now.

Two numbers come out of one registry and they are measured from different
places, which is easy to miss and was missed. Progress is against the whole
file, so a resumed transfer picks the bar up where the last one left it rather
than starting over. Speed is bytes over time, and the time is this request's -
so the bytes have to be this request's too.

Counting the whole file against one request's clock put a download resumed at
nine gigabytes on the dashboard at thirty gigabytes a second, on a machine
whose network card tops out at one gigabit.
"""
from __future__ import annotations

import time

from handler.dashboard import active_downloads


def _fresh():
    active_downloads._active.clear()


def _age(sid: int, seconds: float) -> None:
    """Pretend the transfer started that long ago."""
    active_downloads._active[sid]["started"] = time.monotonic() - seconds


def test_a_plain_download_reports_the_speed_it_is_actually_moving_at():
    _fresh()
    sid = active_downloads.register("ada", "game.iso", 100_000_000)
    _age(sid, 10)
    active_downloads.update(sid, 50_000_000)

    row = active_downloads.snapshot()[0]
    # Loose by a hair: the clock moves between setting the start and reading it.
    assert 4_950_000 <= row["speed_bps"] <= 5_000_000
    assert row["progress"] == 50.0


def test_a_resumed_download_is_not_credited_with_what_it_did_not_send():
    """The whole defect, in the shape it appeared in.

    A ten gigabyte file resumed at nine gigabytes, one second in, having moved
    ten megabytes. Progress is right at ninety percent; the speed is ten
    megabytes a second, not nine gigabytes.
    """
    _fresh()
    nine_gb = 9 * 1024 ** 3
    sid = active_downloads.register("ada", "big.iso", 10 * 1024 ** 3, resumed_at=nine_gb)
    _age(sid, 1)
    active_downloads.update(sid, nine_gb + 10 * 1024 ** 2)

    row = active_downloads.snapshot()[0]
    ten_mb = 10 * 1024 ** 2
    assert ten_mb * 0.99 <= row["speed_bps"] <= ten_mb
    assert row["progress"] == 90.1        # nine gigabytes of ten, plus the ten megabytes
    # And nowhere near the number this used to print, which was the file size
    # over one request's clock.
    assert row["speed_bps"] < nine_gb


def test_a_resume_shows_the_bar_where_it_left_off_before_any_bytes_move():
    """Registering is the first thing that happens; the panel polls every one
    and a half seconds and would otherwise catch the bar at zero."""
    _fresh()
    sid = active_downloads.register("ada", "big.iso", 1000, resumed_at=900)
    row = active_downloads.snapshot()[0]
    assert row["progress"] == 90.0
    assert row["speed_bps"] == 0, "nothing has moved yet"
    assert sid


def test_a_nonsense_offset_cannot_make_the_speed_negative():
    _fresh()
    sid = active_downloads.register("ada", "game.iso", 1000, resumed_at=-5)
    _age(sid, 1)
    active_downloads.update(sid, 100)
    assert 95 <= active_downloads.snapshot()[0]["speed_bps"] <= 100


def test_an_entry_whose_stream_never_ended_is_dropped_eventually():
    """Unchanged behaviour, asserted because the entry now carries one more
    field and a stale row is the one nobody is watching."""
    _fresh()
    sid = active_downloads.register("ada", "game.iso", 1000)
    _age(sid, 13 * 3600)
    assert active_downloads.snapshot() == []
    assert sid not in active_downloads._active
