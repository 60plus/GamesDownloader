"""Deciding whether a file we are about to serve is one we are allowed to serve.

The check itself is old and correct in shape: resolve the path, and refuse it
unless it sits under somewhere we expect. What was wrong was the somewhere.

Three routes compared against `BASE_PATH` alone, and the library does not have
to live there. `GD_GAMES_PATH`, `GD_ROMS_PATH` and `GD_DOWNLOADS_PATH` are
separate settings that merely default to sitting under it, and the same thing
happens without touching any of them if `/data/games` is a symlink onto another
disk: resolving both sides then lands the file outside `BASE_PATH` and every
download answers 403. A guard that refuses a supported configuration outright
is not being strict, it is broken, and it fails in a way that looks like a
permissions problem rather than a path one.

The ROM routes already did this properly, checking against the ROM directory
rather than the base. This is that idea, in one place, for everybody.
"""

from __future__ import annotations

import os

from config import BASE_PATH, DOWNLOADS_PATH, GAMES_PATH, ROMS_PATH


def allowed_roots() -> tuple[str, ...]:
    """Every directory a served file may legitimately sit under, resolved.

    Resolved on each call rather than at import: a root may be a symlink, and
    a deployment that repoints one should not need a restart to be believed.
    """
    seen: list[str] = []
    for root in (BASE_PATH, GAMES_PATH, ROMS_PATH, DOWNLOADS_PATH):
        if not root:
            continue
        real = os.path.realpath(root)
        if real not in seen:
            seen.append(real)
    return tuple(seen)


def is_within_allowed_roots(candidate: str, roots: tuple[str, ...] | None = None) -> bool:
    """Whether `candidate` resolves to somewhere we are willing to serve from.

    Both sides are resolved, which is the point: a path that only looks
    contained because of a symlink is not contained, and that is the traversal
    this refuses.
    """
    resolved = os.path.realpath(candidate)
    for root in (roots if roots is not None else allowed_roots()):
        if resolved == root or resolved.startswith(root + os.sep):
            return True
    return False
