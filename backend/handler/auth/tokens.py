"""JWT token creation and validation."""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from jose import JWTError, jwt

from config import (
    ACCESS_TOKEN_EXPIRE_MINUTES,
    AUTH_ALGORITHM,
    AUTH_SECRET_KEY,
    REFRESH_TOKEN_EXPIRE_DAYS,
)
from handler.auth.scopes import Scope


def _jti() -> str:
    """Generate a unique JWT ID (128-bit random hex)."""
    return secrets.token_hex(16)


def create_access_token(
    subject: str,
    scopes: list[Scope] | None = None,
    expires_delta: timedelta | None = None,
    role: Any = None,
    jti: str | None = None,
) -> str:
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    payload: dict[str, Any] = {
        "sub":    subject,
        "exp":    expire,
        "type":   "access",
        "scopes": [s.value for s in (scopes or [])],
        "jti":    jti or _jti(),
    }
    if role is not None:
        payload["role"] = role.value if hasattr(role, "value") else str(role)
    return jwt.encode(payload, AUTH_SECRET_KEY, algorithm=AUTH_ALGORITHM)


def create_refresh_token(subject: str, jti: str | None = None, expires_days: int | None = None) -> str:
    days = expires_days if expires_days is not None else REFRESH_TOKEN_EXPIRE_DAYS
    expire = datetime.now(timezone.utc) + timedelta(days=days)
    payload = {
        "sub":  subject,
        "exp":  expire,
        "type": "refresh",
        "jti":  jti or _jti(),
    }
    return jwt.encode(payload, AUTH_SECRET_KEY, algorithm=AUTH_ALGORITHM)


def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, AUTH_SECRET_KEY, algorithms=[AUTH_ALGORITHM])
    except JWTError:
        return None
