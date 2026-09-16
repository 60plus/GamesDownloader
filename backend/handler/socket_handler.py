"""WebSocket event emitter - broadcasts real-time events to authenticated clients.

Authentication
--------------
Clients MUST present a Bearer JWT in the Socket.IO `auth` handshake payload:

    io({ auth: { token: "<jwt>" } })

The handler decodes the token, verifies the user, then joins the socket to:
  - room "user:<id>"   - per-user targeted events (downloads, save-states)
  - room "role:<role>" - role-scoped broadcasts (e.g. admin notifications)

`emit_event()` accepts an optional `to_user` / `to_role` / `room` parameter to
scope the emit. When all are None the emit is broadcast to ALL authenticated
clients (used for global progress like ClamAV definition update).

Events: sync_progress, scrape_progress, download:progress, scan_progress, etc.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Iterable

import socketio

from handler.auth.tokens import decode_token

logger = logging.getLogger(__name__)


def _get_cors_origins() -> list[str] | str:
    """Read CORS origins from env or default to permissive for local dev."""
    raw = os.environ.get("GD_CORS_ORIGINS", "")
    if not raw or raw.strip() == "*":
        return "*"
    return [o.strip() for o in raw.split(",") if o.strip()]


sio = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins=_get_cors_origins(),
    logger=False,
    engineio_logger=False,
)


def _user_room(user_id: int | str) -> str:
    return f"user:{user_id}"


#: The one room for "may follow a ROM scan".
#:
#: Named after what an account may DO rather than after the role it had when the
#: socket connected. A role room is blind to `_PERM_REVOKE`: an uploader whose
#: upload chip is switched off keeps the role and loses the scope, so it stayed
#: in `role:uploader` and went on being sent progress that the status route -
#: which asks about scopes - refuses it. The bar was drawn and could never be
#: filled, and the refusal disappeared into an empty catch every ten seconds.
SCAN_WATCHER_ROOM = "scan:watchers"


def scan_watcher_room(scopes) -> str | None:
    """The scan room this set of scopes belongs in, or None.

    The same sentence as the one guarding `GET /roms/scan/status`: an account
    that adds things to the library, or one that can run a scan. Written once
    and asked from both places, because three answers have to agree - who the
    events are sent to, who the status call admits, and who the screen draws for
    - and the last time they disagreed the bar froze for the life of the page.
    """
    from handler.auth.scopes import Scope

    held = set(scopes or ())
    # ROMS_READ as well, because `protected_route` requires EVERY scope it
    # lists and the status route lists that one. Without it the two answers
    # differed in a way somebody can actually reach: turning off the emulation
    # permission strips ROMS_READ and PLATFORMS_READ and leaves the role and its
    # upload permission where they were, so the account stayed in this room and
    # was sent progress that the catch-up call refuses. A bar on screen that
    # nothing can fill, and the refusal disappearing into a catch every ten
    # seconds.
    if Scope.ROMS_READ not in held:
        return None
    if held & {Scope.LIBRARY_UPLOAD, Scope.PLATFORMS_WRITE}:
        return SCAN_WATCHER_ROOM
    return None


async def drop_sockets_for_user(user_id: int) -> int:
    """Disconnect this account's sockets so the next handshake recomputes them.

    Room membership is worked out once, at connect. That is the right place -
    `connect` reads the account from the database every time - but it means an
    administrator unticking a chip changes nothing for a socket that is already
    open: it keeps the rooms it joined for up to the life of the access token,
    an hour by default, and goes on being sent what it may no longer fetch.

    Dropping the socket is the whole fix, because the client reconnects on its
    own and the handshake asks again. Nothing is lost by it: the events are
    progress lines, and every view catches up with a status call on mount.
    """
    dropped = 0
    try:
        room = _user_room(user_id)
        for sid, _ns in list(sio.manager.get_participants("/", room)):
            try:
                await sio.disconnect(sid)
                dropped += 1
            except Exception:  # noqa: BLE001 - one socket must not stop the rest
                logger.debug("Could not drop socket %s", sid, exc_info=True)
    except Exception:  # noqa: BLE001 - never break the write that asked for this
        logger.debug("Could not drop sockets for user %s", user_id, exc_info=True)
    return dropped


def _role_room(role: str) -> str:
    return f"role:{role}"


async def emit_event(
    event: str,
    data: dict[str, Any],
    *,
    to_user: int | str | None = None,
    to_role: str | None = None,
    to_roles: Iterable[str] | None = None,
    room: str | None = None,
) -> None:
    """Emit an event to a specific room or broadcast to all clients.

    Targeting precedence: explicit `room` > `to_user` > `to_roles` > `to_role` >
    broadcast. Broadcasts (all params None) reach every authenticated client.

    `to_roles` is two or more of them, sent one room at a time because a client
    joins exactly one role room. It exists because "who has a reason to see
    this" is not always one role: an administrator and an uploader are both
    accounts that put things in the library, so both have a reason to watch a
    scan register what they added.
    """
    try:
        rooms: list[str | None]
        if room:
            rooms = [room]
        elif to_user is not None:
            rooms = [_user_room(to_user)]
        elif to_roles:
            rooms = [_role_room(r) for r in to_roles]
        elif to_role:
            rooms = [_role_room(to_role)]
        else:
            rooms = [None]
        for target_room in rooms:
            if target_room:
                await sio.emit(event, data, room=target_room)
            else:
                await sio.emit(event, data)
    except Exception:
        logger.exception("Failed to emit event '%s'", event)


async def emit_progress(
    event: str,
    current: int,
    total: int,
    message: str = "",
    extra: dict[str, Any] | None = None,
    *,
    to_user: int | str | None = None,
    to_role: str | None = None,
) -> None:
    """Emit a progress event with a standardised payload."""
    data = {
        "current": current,
        "total": total,
        "progress": round(current / total * 100, 1) if total > 0 else 0,
        "message": message,
    }
    if extra:
        data.update(extra)
    await emit_event(event, data, to_user=to_user, to_role=to_role)


# ── Connection lifecycle ─────────────────────────────────────────────────────

@sio.event
async def connect(sid: str, environ: dict, auth: dict | None = None) -> None:
    """Reject connections without a valid Bearer JWT.

    Joins the socket to per-user and per-role rooms so emits can be scoped.
    """
    token = (auth or {}).get("token") if isinstance(auth, dict) else None
    if not token and isinstance(auth, str):
        token = auth
    if not token:
        # Fallback: allow query-string ?token=... for clients that can't set auth
        qs = environ.get("QUERY_STRING", "") or ""
        for pair in qs.split("&"):
            if pair.startswith("token="):
                token = pair[6:]
                break

    if not token:
        logger.info("WebSocket rejected (no token): %s", sid)
        raise socketio.exceptions.ConnectionRefusedError("Authentication required")

    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        logger.info("WebSocket rejected (invalid token): %s", sid)
        raise socketio.exceptions.ConnectionRefusedError("Invalid token")

    username = payload.get("sub")
    if not username:
        raise socketio.exceptions.ConnectionRefusedError("Invalid token subject")

    # Resolve user from DB - rejects disabled or revoked accounts
    try:
        from handler.database.users_handler import UsersHandler
        user = await UsersHandler().get_by_username(username)
    except Exception:
        user = None

    if not user or not user.enabled:
        logger.info("WebSocket rejected (user disabled/missing): %s", sid)
        raise socketio.exceptions.ConnectionRefusedError("User not found or disabled")

    # Optional: check JTI revocation list (Redis). Fail-open if Redis is down.
    jti = payload.get("jti")
    if jti:
        try:
            from handler.auth.brute_force import _get_redis
            r = _get_redis()
            if await r.exists(f"revoked_jti:{jti}") > 0:
                raise socketio.exceptions.ConnectionRefusedError("Token revoked")
        except socketio.exceptions.ConnectionRefusedError:
            raise
        except Exception:
            pass

    role_val = user.role.value if hasattr(user.role, "value") else str(user.role)
    await sio.save_session(sid, {
        "user_id":  user.id,
        "username": user.username,
        "role":     role_val,
    })
    await sio.enter_room(sid, _user_room(user.id))
    await sio.enter_room(sid, _role_room(role_val))
    # And the room for what this account may actually do, worked out the same
    # way the HTTP middleware works it out. The role rooms stay for everything
    # that really is about a role; this one is about a permission, and the two
    # part company the moment an administrator unticks a chip.
    try:
        from handler.auth.scopes import apply_permission_overrides, scopes_for_role

        effective = apply_permission_overrides(
            getattr(user, "permissions", None) or {}, scopes_for_role(user.role))
        watcher = scan_watcher_room(effective)
        if watcher:
            await sio.enter_room(sid, watcher)
    except Exception:  # noqa: BLE001 - a room, never the connection
        logger.debug("Could not work out the scan room for %s", user.id, exc_info=True)
    logger.debug("WebSocket connected: sid=%s user=%s role=%s", sid, user.username, role_val)


@sio.event
async def disconnect(sid: str) -> None:
    # Drop the socket from any live-queue subscription so the broadcaster loop
    # goes idle once the last watcher's tab closes. Lazy import avoids a cycle.
    try:
        from handler.dashboard.queue_broadcaster import handle_disconnect
        handle_disconnect(sid)
    except Exception:
        pass
    logger.debug("WebSocket disconnected: %s", sid)
