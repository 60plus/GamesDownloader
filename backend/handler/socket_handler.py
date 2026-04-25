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
from typing import Any

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


def _role_room(role: str) -> str:
    return f"role:{role}"


async def emit_event(
    event: str,
    data: dict[str, Any],
    *,
    to_user: int | str | None = None,
    to_role: str | None = None,
    room: str | None = None,
) -> None:
    """Emit an event to a specific room or broadcast to all clients.

    Targeting precedence: explicit `room` > `to_user` > `to_role` > broadcast.
    Broadcasts (all params None) reach every authenticated client.
    """
    try:
        target_room: str | None
        if room:
            target_room = room
        elif to_user is not None:
            target_room = _user_room(to_user)
        elif to_role:
            target_room = _role_room(to_role)
        else:
            target_room = None
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
    logger.debug("WebSocket connected: sid=%s user=%s role=%s", sid, user.username, role_val)


@sio.event
async def disconnect(sid: str) -> None:
    logger.debug("WebSocket disconnected: %s", sid)
