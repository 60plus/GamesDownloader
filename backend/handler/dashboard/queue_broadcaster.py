"""Socket.IO push for the admin dashboard's live feed (transfer queue + health).

Instead of every open admin dashboard polling the API on a timer, one server-side
loop pushes updates over Socket.IO to all subscribed admins. The design is
deliberately economical:

  * The loop does NO work while nobody is watching. An admin dashboard emits
    "dashboard:subscribe" on mount (joining the `dashboard:live` room) and
    "dashboard:unsubscribe" on unmount. Only while that room has members does the
    loop compute + emit. One subscription feeds both the queue and health.
  * Queue: while transfers are live it pushes every ACTIVE_INTERVAL so the bars
    move. When watched-but-idle it re-checks internally on the IDLE_INTERVAL (a
    few async DB reads, plus a Transmission RPC when seeding) but emits the queue
    only when the snapshot signature changes - no queue traffic flows at rest.
  * Health: server vitals (CPU/RAM/uptime/load) drift constantly, so a small
    heartbeat is pushed EVERY tick while watched - cheap (just /proc reads, no
    DB) and the reason an admin sees health update live without a page reload.
  * A brand-new subscriber gets an immediate queue + health snapshot.
  * Subscribers are periodically re-checked against their current DB role; a
    demoted admin is dropped from the room so the sensitive feed (who is
    downloading what) tracks role changes, not just the connect-time snapshot.

Clients keep a polling fallback (dashboardActions.queue) for when the socket is
down, so this is a pure enhancement - never a single point of failure.

Only admins may subscribe; the subscribe handler checks the socket session role.
Events out (to room): "dashboard:queue" -> {downloads, uploads, seeding, active};
"dashboard:health" -> {cpu_percent, load1, mem_used, mem_total, uptime_seconds, cores}.
"""
from __future__ import annotations

import asyncio
import json
import logging

from handler.socket_handler import emit_event, sio

logger = logging.getLogger(__name__)

_ROOM = "dashboard:live"

# sids of admins currently watching the dashboard live feed. The loop is a no-op
# while this is empty, so an unwatched server does no work at all.
_subscribers: set[str] = set()

_NO_WATCHER_SLEEP = 2.0   # nobody watching: just wait cheaply for a subscriber
_ACTIVE_INTERVAL = 1.5    # a download/upload is live: push often so progress animates
_IDLE_INTERVAL = 3.0      # watched but idle (or only seeding): re-check, emit only on change
_REVALIDATE_EVERY = 6     # re-check subscriber roles every N iterations (~9-18 s)


def _signature(snap: dict) -> str:
    """Cheap change-detector. During a transfer the speeds/bytes shift every tick
    so this differs each time (we push); when idle it is stable (we stay silent)."""
    return json.dumps(snap, sort_keys=True, default=str)


async def _snapshot() -> dict:
    from handler.dashboard.dashboard_handler import dashboard_handler
    return await dashboard_handler.get_download_queue()


async def _health() -> dict:
    # /proc reads only (no DB); the 0.12 s CPU sample runs off the event loop.
    from handler.dashboard.dashboard_handler import _server_health
    return await asyncio.get_running_loop().run_in_executor(None, _server_health)


async def _on_subscribe(sid: str, *_args) -> None:
    """Admin dashboard mounted its queue panel. Join the room and send an
    immediate snapshot so it renders without waiting for the next loop tick."""
    try:
        session = await sio.get_session(sid)
    except Exception:
        session = None
    if not session or session.get("role") != "admin":
        return  # non-admins (or unknown sockets) are silently ignored
    # The socket session froze this role at connect time and nothing refreshes
    # it, so a demoted admin's open socket still says "admin". The periodic
    # revalidation only walks CURRENT subscribers, which an unsubscribe/subscribe
    # pair skips entirely - so re-resolve the role from the DB before letting
    # anyone back in, and refuse on doubt (the eviction path may fail open, but
    # admitting a new subscriber must not).
    if not await _still_admin(sid, default=False):
        return
    _subscribers.add(sid)
    await sio.enter_room(sid, _ROOM)
    # Immediate first paint for the new watcher: current queue + health.
    try:
        await sio.emit("dashboard:queue", await _snapshot(), room=sid)
        await sio.emit("dashboard:health", await _health(), room=sid)
    except Exception:
        logger.exception("dashboard live: initial snapshot failed")


async def _on_unsubscribe(sid: str, *_args) -> None:
    _subscribers.discard(sid)
    try:
        await sio.leave_room(sid, _ROOM)
    except Exception:
        pass


def handle_disconnect(sid: str) -> None:
    """Called from socket_handler.disconnect so a closed tab stops the loop."""
    _subscribers.discard(sid)


async def _still_admin(sid: str, *, default: bool = True) -> bool:
    """Re-resolve a subscriber's CURRENT role from the DB (cached).

    `default` is the answer to a transient error. Eviction passes True so a DB
    hiccup never kicks a legitimate admin off a live panel; admission passes
    False, because failing open there would hand the feed to whoever asked while
    the lookup happened to be broken.
    """
    try:
        session = await sio.get_session(sid)
        username = session.get("username") if session else None
        if not username:
            return False
        from handler.database.users_handler import UsersHandler
        user = await UsersHandler().get_by_username(username)
        if not user or not user.enabled:
            return False
        role = user.role.value if hasattr(user.role, "value") else str(user.role)
        return role == "admin"
    except Exception:
        return default


async def _revalidate_subscribers() -> None:
    """Drop any subscriber who is no longer an enabled admin (e.g. demoted), so
    the live transfer feed stops for them without waiting for a reconnect."""
    for sid in list(_subscribers):
        if not await _still_admin(sid):
            _subscribers.discard(sid)
            try:
                await sio.leave_room(sid, _ROOM)
            except Exception:
                pass


# Register the client->server events at import time (before any client connects,
# since this module is imported during app startup). One subscription feeds both
# the queue and the health heartbeat.
sio.on("dashboard:subscribe", _on_subscribe)
sio.on("dashboard:unsubscribe", _on_unsubscribe)


async def queue_broadcaster_loop() -> None:
    """Push the live feed (queue + health heartbeat) to subscribed admins; idle
    when unwatched."""
    await asyncio.sleep(8)  # let the app and Transmission settle on startup
    last_sig: str | None = None
    ticks = 0
    while True:
        try:
            if not _subscribers:
                last_sig = None  # forget, so the next watched push always fires
                await asyncio.sleep(_NO_WATCHER_SLEEP)
                continue
            ticks += 1
            if ticks % _REVALIDATE_EVERY == 0:
                await _revalidate_subscribers()
                if not _subscribers:
                    continue
            snap = await _snapshot()
            # A pure-seeding server ticks on the gentler idle cadence; only an
            # in-flight download/upload warrants the fast progress-animation rate.
            active = bool(snap.get("downloads") or snap.get("uploads"))
            sig = _signature(snap)
            if sig != last_sig:
                await emit_event("dashboard:queue", snap, room=_ROOM)
                last_sig = sig
            # Server-health heartbeat: CPU/RAM always drift, so this is the tick
            # that keeps the health widget live. Isolated so a /proc hiccup does
            # not stall the queue side.
            try:
                await emit_event("dashboard:health", await _health(), room=_ROOM)
            except Exception:
                logger.exception("dashboard health emit failed")
            await asyncio.sleep(_ACTIVE_INTERVAL if active else _IDLE_INTERVAL)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("queue_broadcaster loop error")
            await asyncio.sleep(5.0)
