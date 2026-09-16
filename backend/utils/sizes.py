"""Sizes written the way a person reads them.

Refusals composed on the server quoted raw integers:

    This torrent is 22914307626 bytes and only 0 are left of this account's
    upload quota.

The point of that sentence is to let somebody judge how much room they need to
free, and twenty-two billion is not a number anybody converts in their head.

The interface has done this properly all along, in `formatBytes`
(frontend/src/utils/format.ts). The units and the rounding here match it on
purpose: a refusal saying 21.3 GB beside a tray saying 21.34 GB for the same
file reads as two different numbers.
"""

from __future__ import annotations

_UNITS = ("B", "KB", "MB", "GB", "TB", "PB")


def human_bytes(size) -> str:
    """`size` in bytes as text, 1024-based. Anything unreadable comes back as
    "0 B" rather than raising - these end up inside refusals, and a message that
    fails on its own wording turns a clear no into a 500."""
    try:
        value = float(size)
    except (TypeError, ValueError):
        return "0 B"
    if value <= 0 or value != value or value in (float("inf"), float("-inf")):
        return "0 B"

    unit = 0
    while value >= 1024 and unit < len(_UNITS) - 1:
        value /= 1024
        unit += 1
    # No decimals for bytes, one up to gigabytes, two from there: the same three
    # rules the interface applies.
    decimals = 0 if unit == 0 else (2 if unit >= 3 else 1)
    return f"{value:.{decimals}f} {_UNITS[unit]}"
