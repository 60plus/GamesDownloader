"""Authentication middleware - injects user and scopes into request.state.

Supports: Bearer JWT, Basic Auth, Session cookie.
Unauthenticated requests proceed with user=None (endpoints check via decorator).
"""

from __future__ import annotations

import base64
import logging

from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from handler.auth.passwords import verify_password
from handler.auth.scopes import apply_permission_overrides, scopes_for_role
from handler.auth.tokens import decode_token
from handler.database.session_handler import session_handler
from handler.database.users_handler import UsersHandler

logger = logging.getLogger(__name__)
_users_db = UsersHandler()
_REVOKED_PREFIX = "revoked_jti:"


async def _is_jti_revoked(jti: str) -> bool:
    """Check if a JTI has been revoked using the shared Redis singleton.

    Uses the same connection pool as brute_force to avoid creating a new
    Redis connection on every authenticated HTTP request.
    """
    try:
        from handler.auth.brute_force import _get_redis
        r = _get_redis()
        return await r.exists(f"{_REVOKED_PREFIX}{jti}") > 0
    except Exception:
        return False  # Redis down → fail open (don't block all users)


class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request.state.user      = None
        request.state.scopes    = set()
        request.state.token_jti = None

        auth_header = request.headers.get("Authorization", "")

        if auth_header.startswith("Bearer "):
            await self._handle_bearer(request, auth_header[7:])
        elif auth_header.startswith("Basic "):
            await self._handle_basic(request, auth_header[6:])

        return await call_next(request)

    async def _handle_bearer(self, request: Request, token: str) -> None:
        payload = decode_token(token)
        if not payload or payload.get("type") != "access":
            return

        username = payload.get("sub")
        if not username:
            return

        jti = payload.get("jti")
        if jti and await _is_jti_revoked(jti):
            return  # token revoked in Redis - treat as unauthenticated

        # Secondary check: DB session must be active (guards against Redis being cleared)
        if jti:
            sess = await session_handler.get_by_access_jti(jti)
            if sess is not None and not sess.is_active:
                return  # session revoked in DB - treat as unauthenticated

        user = await _users_db.get_by_username(username)
        if user and user.enabled:
            request.state.user      = user
            request.state.token_jti = jti
            base = scopes_for_role(user.role)
            request.state.scopes = apply_permission_overrides(user.permissions, base)

    async def _handle_basic(self, request: Request, encoded: str) -> None:
        try:
            decoded = base64.b64decode(encoded).decode("utf-8")
            username, password = decoded.split(":", 1)
        except Exception:
            return

        user = await _users_db.get_by_username(username)
        if user and user.enabled and verify_password(password, user.hashed_password):
            request.state.user = user
            base = scopes_for_role(user.role)
            request.state.scopes = apply_permission_overrides(user.permissions, base)
