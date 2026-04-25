"""Authentication endpoints - login, register, refresh, logout, password reset."""

from __future__ import annotations

import asyncio
import logging
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel

from config import AUTH_ALGORITHM, AUTH_SECRET_KEY
from exceptions.auth import InvalidCredentialsException, UserDisabledException
from handler.auth.passwords import hash_password, verify_password
from handler.auth.scopes import scopes_for_role
from handler.auth.tokens import create_access_token, create_refresh_token, decode_token
from handler.auth import brute_force
from handler.auth.audit import log_event
from handler.database.users_handler import UsersHandler
from handler.database.session_handler import session_handler
from handler.database.audit_handler import audit_handler
from models.user import Role, User
from schemas.user import TokenResponse, UserCreate, UserResponse
from utils.async_utils import fire_task

from jose import jwt, JWTError

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])
_users_db = UsersHandler()


def _user_agent(request: Request) -> str:
    return request.headers.get("User-Agent", "")[:512]


class LoginRequest(BaseModel):
    username: str
    password: str


@router.post("/login", response_model=TokenResponse)
async def login(req: LoginRequest, request: Request) -> TokenResponse:
    """Authenticate a user. Credentials are sent as a JSON body (never in the URL)."""
    blocked, remaining = await brute_force.check_ip(request)
    if blocked:
        await log_event(request, "login_blocked", username=req.username, details=f"Blocked, {remaining}s remaining", status="warn")
        raise HTTPException(status_code=429, detail=f"Too many failed attempts. Try again in {remaining}s.")

    ip = brute_force._client_ip(request)
    ua = _user_agent(request)

    user = await _users_db.get_by_username(req.username)
    if not user or not verify_password(req.password, user.hashed_password):
        await brute_force.record_failure(request)
        await log_event(request, "login_fail", username=req.username, status="fail")
        from handler.email.alerts import maybe_alert
        fire_task(maybe_alert("login_fail", req.username, ip, ua))
        raise InvalidCredentialsException()
    if not user.enabled:
        raise UserDisabledException()

    # Detect new IP before logging login_ok (so current IP is not yet in the set)
    known_ips = await audit_handler.get_known_ips(user.username)
    is_new_ip = bool(known_ips) and ip not in known_ips

    await brute_force.record_success(request)
    await log_event(request, "login_ok", username=user.username)
    scopes = scopes_for_role(user.role)

    access_jti  = secrets.token_hex(16)
    refresh_jti = secrets.token_hex(16)

    from handler.config.config_handler import config_handler
    from config import REFRESH_TOKEN_EXPIRE_DAYS
    _raw = await config_handler.get("session_lifetime_days")
    try:
        lifetime_days = int(_raw) if _raw else REFRESH_TOKEN_EXPIRE_DAYS
    except ValueError:
        lifetime_days = REFRESH_TOKEN_EXPIRE_DAYS

    access_token  = create_access_token(user.username, list(scopes), role=user.role, jti=access_jti)
    refresh_token = create_refresh_token(user.username, jti=refresh_jti, expires_days=lifetime_days)

    await session_handler.create(
        username=user.username,
        access_jti=access_jti,
        refresh_jti=refresh_jti,
        ip_address=ip,
        user_agent=ua,
    )

    if is_new_ip:
        from handler.email.alerts import maybe_alert
        fire_task(maybe_alert("new_ip", user.username, ip, ua))

    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(req: UserCreate, request: Request) -> UserResponse:
    # Rate limit: max 5 registrations per IP per 5 minutes
    await brute_force.rate_limit(request, limit=5, window=300, key_prefix="register")
    count = await _users_db.count()
    if count > 0:
        from handler.config.config_handler import config_handler
        mode = await config_handler.get("registration_mode") or (
            "open" if await config_handler.get_bool("enable_registrations", default=True) else "disabled"
        )
        if mode == "disabled":
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Registrations are disabled")
        if mode == "invite_only":
            invite_code = getattr(req, "invite_code", None)
            if not invite_code:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="An invite code is required to register")
            from handler.database.invite_handler import invite_handler
            if not await invite_handler.validate_and_use(invite_code):
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid, expired, or exhausted invite code")

    role = Role.ADMIN if count == 0 else Role.USER
    existing = await _users_db.get_by_username(req.username)
    if existing:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Username '{req.username}' already taken")

    user = User(
        username=req.username,
        email=req.email,
        hashed_password=hash_password(req.password),
        role=role,
        enabled=True,
    )
    user = await _users_db.create(user)

    # Alert admin about new registration (skip for the very first admin account)
    if role != Role.ADMIN:
        from handler.email.alerts import maybe_alert
        fire_task(maybe_alert("new_user", user.username, None))

    return UserResponse.model_validate(user)


class RefreshRequest(BaseModel):
    refresh_token: str


@router.post("/refresh", response_model=TokenResponse)
async def refresh(req: RefreshRequest, request: Request) -> TokenResponse:
    # Rate limit: max 60 refresh calls per IP per 5 minutes
    await brute_force.rate_limit(request, limit=60, window=300, key_prefix="refresh")
    payload = decode_token(req.refresh_token)
    if not payload or payload.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    username = payload.get("sub")
    user = await _users_db.get_by_username(username)
    if not user or not user.enabled:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or disabled")

    refresh_jti = payload.get("jti")
    if refresh_jti and await session_handler.is_revoked(refresh_jti):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session has been revoked")

    scopes = scopes_for_role(user.role)
    new_access_jti = secrets.token_hex(16)
    access_token   = create_access_token(user.username, list(scopes), role=user.role, jti=new_access_jti)
    # Keep the same refresh JTI so the session row stays linked
    new_refresh    = create_refresh_token(user.username, jti=refresh_jti)

    if refresh_jti:
        await session_handler.update_access_jti(refresh_jti, new_access_jti)

    return TokenResponse(access_token=access_token, refresh_token=new_refresh)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request) -> None:
    """Revoke the current session."""
    access_jti = getattr(request.state, "token_jti", None)
    if access_jti:
        sess = await session_handler.get_by_access_jti(access_jti)
        if sess:
            await session_handler.revoke(sess.id)


# ── Password reset ───────────────────────────────────────────────────────────

_RESET_TOKEN_EXPIRE_HOURS = 1


def _base_url(request: Request) -> str:
    """Return scheme://host -- works behind reverse proxies."""
    fwd_proto = request.headers.get("X-Forwarded-Proto", "")
    scheme = fwd_proto or request.url.scheme
    host = request.headers.get("X-Forwarded-Host", "") or request.headers.get("Host", "") or request.url.netloc
    return f"{scheme}://{host}"


def _create_reset_token(user_id: int) -> str:
    """Create a short-lived JWT for password reset (no DB storage needed)."""
    expire = datetime.now(timezone.utc) + timedelta(hours=_RESET_TOKEN_EXPIRE_HOURS)
    payload = {
        "sub": str(user_id),
        "exp": expire,
        "type": "password_reset",
        "jti": secrets.token_hex(16),
    }
    return jwt.encode(payload, AUTH_SECRET_KEY, algorithm=AUTH_ALGORITHM)


def _decode_reset_token(token: str) -> int | None:
    """Decode a password-reset JWT. Returns user ID or None on failure."""
    try:
        payload = jwt.decode(token, AUTH_SECRET_KEY, algorithms=[AUTH_ALGORITHM])
        if payload.get("type") != "password_reset":
            return None
        return int(payload["sub"])
    except (JWTError, KeyError, ValueError):
        return None


async def _send_reset_email(to_addr: str, reset_url: str) -> None:
    """Send the password-reset email using configured SMTP settings."""
    from handler.config.config_handler import config_handler

    if not await config_handler.get_bool("smtp_enabled", default=False):
        logger.warning("Password reset requested but SMTP is not enabled")
        return

    host = await config_handler.get("smtp_host") or ""
    port_str = await config_handler.get("smtp_port") or "587"
    user = await config_handler.get("smtp_username") or ""
    password = await config_handler.get("smtp_password") or ""
    from_addr = await config_handler.get("smtp_from_address") or ""
    use_tls = await config_handler.get_bool("smtp_use_tls", default=True)
    tls_mode = "starttls" if use_tls else "none"

    if not host or not from_addr:
        logger.warning("Password reset: SMTP not fully configured")
        return

    try:
        port = int(port_str)
    except ValueError:
        port = 587

    subject = "Password Reset Request"
    body = f"""\
<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;background:#0d0d1a;color:#e0e0e0;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#0d0d1a;padding:40px 20px;">
    <tr><td align="center">
      <table width="480" cellpadding="0" cellspacing="0" style="background:#1a1a2e;border-radius:12px;border:1px solid rgba(255,255,255,0.08);padding:40px;">
        <tr><td align="center" style="padding-bottom:24px;">
          <span style="font-size:22px;font-weight:700;color:#c4b5fd;">GamesDownloader</span>
        </td></tr>
        <tr><td style="padding-bottom:16px;font-size:15px;line-height:1.6;color:#d0d0d0;">
          You requested a password reset for your account. Click the button below to choose a new password.
        </td></tr>
        <tr><td align="center" style="padding:20px 0;">
          <a href="{reset_url}" style="display:inline-block;padding:14px 36px;background:#7c3aed;color:#ffffff;text-decoration:none;border-radius:8px;font-weight:700;font-size:15px;">
            Reset Password
          </a>
        </td></tr>
        <tr><td style="padding-top:8px;font-size:13px;color:#888;">
          This link will expire in 1 hour. If the button does not work, copy and paste this URL into your browser:
        </td></tr>
        <tr><td style="padding-top:8px;word-break:break-all;">
          <a href="{reset_url}" style="color:#a78bfa;font-size:13px;">{reset_url}</a>
        </td></tr>
        <tr><td style="padding-top:24px;font-size:12px;color:#666;border-top:1px solid rgba(255,255,255,0.06);margin-top:24px;padding-top:16px;">
          If you did not request a password reset, you can safely ignore this email. Your password will remain unchanged.
        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""

    from handler.email.smtp_sender import send_email
    await send_email(host, port, user, password, from_addr, to_addr, subject, body, tls_mode)
    logger.info("Password reset email sent to %s", to_addr)


class ForgotPasswordRequest(BaseModel):
    email: str


@router.post("/forgot-password")
async def forgot_password(req: ForgotPasswordRequest, request: Request) -> dict:
    """Send a password-reset link. Always returns ok to prevent email enumeration."""
    await brute_force.rate_limit(request, limit=5, window=300, key_prefix="forgot_pw")

    user = await _users_db.get_by_email(req.email)
    if user and user.enabled:
        token = _create_reset_token(user.id)
        reset_url = f"{_base_url(request)}/reset-password?token={token}"
        fire_task(_send_reset_email(user.email, reset_url))

    return {"ok": True}


class ResetPasswordRequest(BaseModel):
    token: str
    password: str


@router.post("/reset-password")
async def reset_password(req: ResetPasswordRequest, request: Request) -> dict:
    """Reset the user's password using a valid reset token."""
    await brute_force.rate_limit(request, limit=10, window=300, key_prefix="reset_pw")

    user_id = _decode_reset_token(req.token)
    if user_id is None:
        raise HTTPException(status_code=400, detail="Invalid or expired reset link")

    user = await _users_db.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired reset link")

    if len(req.password) < 8 or not any(c.isalpha() for c in req.password) or not any(c.isdigit() for c in req.password):
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters with at least one letter and one digit")

    await _users_db.update(user, {"hashed_password": hash_password(req.password)})
    await session_handler.revoke_all_for_user(user.username)

    await log_event(request, "password_reset", username=user.username)
    logger.info("Password reset completed for user %s", user.username)

    return {"ok": True}
