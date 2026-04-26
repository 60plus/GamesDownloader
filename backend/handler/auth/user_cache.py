"""Redis-backed cache for the AuthMiddleware user lookup.

Every authenticated HTTP request used to issue a fresh
`SELECT * FROM users WHERE username = ?` query in the auth middleware.
That query was cheap individually but it ran on every HTTP request,
including 50+ resource fetches when a single library page rendered.
Multiplied across the WebSocket reconnect loop and the polling endpoints
it added measurable load on MariaDB and ~5 ms of latency to each call.

The cache stores a JSON snapshot of the User row in Redis under
`auth:user_by_username:<sha256(username)>` with a 60 s TTL.
Snapshots include only the fields that endpoints / decorators actually
read (id, role, enabled, permissions, hashed_password, totp flags, etc.).
The reconstructed `User` instance is *detached* from any SQLAlchemy
session - this is safe because UsersHandler.update() and .delete()
re-fetch by primary key inside their own session, so a stale `obj`
passed in as the first argument is harmless.

Invalidation is required whenever the row changes:

- `UsersHandler.update`  (role, email, enabled, permissions, password,
  TOTP, avatar_path, preferences ...)
- `UsersHandler.delete`
- the user-cache module exposes `invalidate_user_cache(...)` so any
  call site that bypasses UsersHandler can clear the cache directly.

Failures are non-fatal: if Redis is unreachable we fall back to a fresh
DB query, so the application keeps working without the speedup.
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime
from typing import Any

from models.user import Role, User

logger = logging.getLogger(__name__)

_CACHE_PREFIX = "auth:user_by_username:"
_CACHE_TTL    = 60   # seconds - short enough that role/disable changes apply quickly
                     # for the rare case where invalidation got lost (worker crash,
                     # Redis flush during a write).

_FIELDS = (
    "id", "username", "email", "hashed_password", "role", "enabled",
    "avatar_path", "permissions", "preferences",
    "totp_secret", "totp_enabled", "totp_recovery_codes",
    "created_at", "updated_at",
)


def _key(username: str) -> str:
    # Hash to keep the key opaque - usernames may contain characters that
    # complicate Redis key inspection or RESP framing.
    h = hashlib.sha256(username.encode("utf-8")).hexdigest()
    return f"{_CACHE_PREFIX}{h}"


async def _get_redis():
    """Reuse the brute_force singleton so we share the same connection pool."""
    from handler.auth.brute_force import _get_redis
    return _get_redis()


def _serialize(user: User) -> str:
    snap: dict[str, Any] = {}
    for f in _FIELDS:
        v = getattr(user, f, None)
        if isinstance(v, datetime):
            snap[f] = v.isoformat()
        elif isinstance(v, Role):
            snap[f] = v.value
        else:
            snap[f] = v
    return json.dumps(snap, default=str)


def _deserialize(blob: str) -> User | None:
    try:
        snap = json.loads(blob)
    except (TypeError, ValueError):
        return None

    # Use the regular constructor so SQLAlchemy's instrumentation initialises
    # `_sa_instance_state`. Bypassing __init__ via __new__ leaves the object
    # half-formed and any later attribute access (incl. Pydantic
    # `model_validate(user, from_attributes=True)`) raises AttributeError.
    user = User()
    for f in _FIELDS:
        if f not in snap:
            continue
        v = snap[f]
        if f in ("created_at", "updated_at") and isinstance(v, str):
            try:
                v = datetime.fromisoformat(v)
            except ValueError:
                v = None
        elif f == "role" and isinstance(v, str):
            try:
                v = Role(v)
            except ValueError:
                v = Role.USER
        setattr(user, f, v)
    return user


async def get_cached_user_by_username(username: str) -> User | None:
    """Return a detached User snapshot if cached, else None.

    Cache misses and Redis errors return None silently - the caller is
    expected to fall through to a real DB query.
    """
    if not username:
        return None
    try:
        r = await _get_redis()
        blob = await r.get(_key(username))
    except Exception:
        return None
    if not blob:
        return None
    return _deserialize(blob)


async def cache_user(user: User) -> None:
    """Store a snapshot of `user` so the next request hits Redis instead of MariaDB."""
    if user is None or not getattr(user, "username", None):
        return
    try:
        r = await _get_redis()
        await r.setex(_key(user.username), _CACHE_TTL, _serialize(user))
    except Exception:
        # Caching is best-effort - never bubble up.
        logger.debug("user_cache: failed to cache user %s", user.username, exc_info=True)


async def invalidate_user_cache(username: str | None = None) -> None:
    """Drop the cached snapshot so the next request re-reads from MariaDB.

    Call this whenever a user row changes (role, enabled, permissions,
    password, TOTP, etc.) so the change becomes visible without waiting
    for the TTL to elapse.
    """
    if not username:
        return
    try:
        r = await _get_redis()
        await r.delete(_key(username))
    except Exception:
        logger.debug("user_cache: failed to invalidate %s", username, exc_info=True)
