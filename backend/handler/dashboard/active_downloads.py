"""In-memory registry of in-flight user file downloads (server -> user).

The file-streaming path registers a download when it starts, updates the bytes
sent as it streams, and drops it when the stream ends (its finally block). The
admin dashboard reads a snapshot to show who is downloading what right now - the
server's outbound/"upload" transfers, attributed to the requesting user.

Process-local and best-effort: the app runs a single uvicorn worker (Dockerfile
`--workers 1`), so one registry sees every stream. Every function swallows its
own errors so registry bookkeeping can never disturb a download.
"""
from __future__ import annotations

import itertools
import time

_seq = itertools.count(1)
_active: dict[int, dict] = {}
_MAX_AGE_S = 12 * 3600  # safety net: drop entries whose stream never unregistered


def register(
    username: str | None, filename: str | None, total: int | None,
    *, resumed_at: int = 0,
) -> int:
    """Start tracking a download. Returns an id for update()/unregister() (0 on
    failure - update/unregister treat an unknown id as a no-op).

    *resumed_at* is where in the file this request begins. Progress is reported
    against the whole file, so a resumed transfer picks the bar up where the
    last one left it - but speed is bytes over time, and the bytes have to be
    the ones this request moved. Counting from zero while the clock ran from
    this request's start put a download resumed at nine gigabytes on the
    dashboard at thirty gigabytes a second.
    """
    try:
        sid = next(_seq)
        start = max(0, int(resumed_at or 0))
        _active[sid] = {
            "username": username or "?", "filename": filename or "",
            "total": int(total or 0), "sent": start, "from": start,
            "started": time.monotonic(),
        }
        return sid
    except Exception:
        return 0


def update(sid: int, sent: int) -> None:
    e = _active.get(sid)
    if e is not None:
        e["sent"] = sent


def unregister(sid: int) -> None:
    _active.pop(sid, None)


def snapshot() -> list[dict]:
    """Current downloads with average speed + progress. Oldest first. Evicts
    stale leftovers defensively."""
    now = time.monotonic()
    out: list[dict] = []
    for sid, e in list(_active.items()):
        elapsed = now - e["started"]
        if elapsed > _MAX_AGE_S:
            _active.pop(sid, None)
            continue
        sent, total = e["sent"], e["total"]
        # Speed is what this request has moved; progress is how much of the file
        # the player now has. On a resume those are not the same number.
        moved = max(0, sent - e.get("from", 0))
        out.append({
            "username": e["username"], "filename": e["filename"],
            "sent": sent, "total": total,
            "speed_bps": int(moved / elapsed) if (moved and elapsed > 0.1) else 0,
            "progress": round(sent / total * 100, 1) if total else 0.0,
        })
    return out
