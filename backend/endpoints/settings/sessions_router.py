"""Sessions management - list and revoke active JWT sessions."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from decorators.auth import protected_route
from handler.auth.scopes import Scope
from handler.database.session_handler import session_handler
from handler.config.config_handler import config_handler
from config import REFRESH_TOKEN_EXPIRE_DAYS
from models.user import Role

router = APIRouter(prefix="/api/settings/security/sessions", tags=["sessions"])


class SessionOut(BaseModel):
    id:         int
    username:   str
    ip_address: str | None
    user_agent: str | None
    last_used:  datetime | None
    created_at: datetime | None
    is_current: bool

    model_config = {"from_attributes": True}


def _parse_browser(ua: str | None) -> str:
    """Return a short human-readable browser/client label from User-Agent."""
    if not ua:
        return "Unknown client"
    ua_lower = ua.lower()
    if "curl" in ua_lower:
        return "curl"
    if "python" in ua_lower:
        return "Python script"
    if "insomnia" in ua_lower or "postman" in ua_lower:
        return "API client"
    browsers = [
        ("edg/",    "Edge"),
        ("opr/",    "Opera"),
        ("chrome/", "Chrome"),
        ("firefox/","Firefox"),
        ("safari/", "Safari"),
        ("msie",    "IE"),
    ]
    for token, name in browsers:
        if token in ua_lower:
            # Try to get OS
            if "windows" in ua_lower:
                return f"{name} / Windows"
            if "android" in ua_lower:
                return f"{name} / Android"
            if "iphone" in ua_lower or "ipad" in ua_lower:
                return f"{name} / iOS"
            if "mac" in ua_lower:
                return f"{name} / macOS"
            if "linux" in ua_lower:
                return f"{name} / Linux"
            return name
    return ua[:60]


def _to_out(sess, current_jti: str | None) -> dict:
    return {
        "id":         sess.id,
        "username":   sess.username,
        "ip_address": sess.ip_address,
        "user_agent": _parse_browser(sess.user_agent),
        "last_used":  sess.last_used,
        "created_at": sess.created_at,
        "is_current": bool(current_jti and sess.access_jti == current_jti),
    }


class SessionLifetimeBody(BaseModel):
    session_lifetime_days: int


@protected_route(router.get, "/config")
async def get_session_config(request: Request) -> dict:
    """Return session lifetime setting (admin only)."""
    if request.state.user.role != Role.ADMIN:
        raise HTTPException(status_code=403, detail="Admin only")
    raw = await config_handler.get("session_lifetime_days")
    try:
        days = int(raw) if raw else REFRESH_TOKEN_EXPIRE_DAYS
    except ValueError:
        days = REFRESH_TOKEN_EXPIRE_DAYS
    return {"session_lifetime_days": days}


@protected_route(router.post, "/config")
async def set_session_config(request: Request, body: SessionLifetimeBody) -> dict:
    """Update session lifetime setting (admin only)."""
    if request.state.user.role != Role.ADMIN:
        raise HTTPException(status_code=403, detail="Admin only")
    days = max(1, min(body.session_lifetime_days, 3650))
    await config_handler.set("session_lifetime_days", str(days))
    return {"session_lifetime_days": days}


@protected_route(router.get, "", response_model=list[SessionOut])
async def list_sessions(request: Request) -> list[dict]:
    """List active sessions. Admins see all users, others see only own."""
    current_jti = getattr(request.state, "token_jti", None)
    user = request.state.user

    if user.role == Role.ADMIN:
        sessions = await session_handler.get_all_active()
    else:
        sessions = await session_handler.get_active_for_user(user.username)

    return [_to_out(s, current_jti) for s in sessions]


@protected_route(router.delete, "/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_session(request: Request, session_id: int) -> None:
    """Revoke a specific session. Users can only revoke their own."""
    user = request.state.user
    sess = await session_handler.get_by_id(session_id)
    if not sess or not sess.is_active:
        raise HTTPException(status_code=404, detail="Session not found")
    if user.role != Role.ADMIN and sess.username != user.username:
        raise HTTPException(status_code=403, detail="Cannot revoke another user's session")
    await session_handler.revoke(session_id)


@protected_route(router.delete, "", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_all_my_sessions(request: Request) -> None:
    """Revoke all sessions for the current user (logout everywhere)."""
    user = request.state.user
    await session_handler.revoke_all_for_user(user.username)
