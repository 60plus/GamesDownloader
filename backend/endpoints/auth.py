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
from schemas.user import (
    Disable2FARequest,
    Enable2FAStartResponse,
    Enable2FAVerifyRequest,
    Enable2FAVerifyResponse,
    LoginResponse,
    LoginTotpRequest,
    TokenResponse,
    TotpStatusResponse,
    UserCreate,
    UserResponse,
)
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


_TOTP_CHALLENGE_EXPIRE_MINUTES = 5


def _create_totp_challenge_token(user_id: int) -> str:
    """Issue a 5-min JWT that proves the user passed the password step.

    Carries `type: "totp_challenge"` so a confused-deputy attacker cannot pass
    it as an access token. The jti is one-shot via the existing Redis blacklist.
    """
    expire = datetime.now(timezone.utc) + timedelta(minutes=_TOTP_CHALLENGE_EXPIRE_MINUTES)
    payload = {
        "sub":  str(user_id),
        "exp":  expire,
        "type": "totp_challenge",
        "jti":  secrets.token_hex(16),
    }
    return jwt.encode(payload, AUTH_SECRET_KEY, algorithm=AUTH_ALGORITHM)


def _decode_totp_challenge_token(token: str) -> dict | None:
    try:
        payload = jwt.decode(token, AUTH_SECRET_KEY, algorithms=[AUTH_ALGORITHM])
        if payload.get("type") != "totp_challenge":
            return None
        int(payload["sub"])
        return payload
    except (JWTError, KeyError, ValueError):
        return None


async def _issue_session_tokens(user: User, request: Request) -> TokenResponse:
    """Create access + refresh tokens, persist the session, fire alerts.

    Used by both the standard login path and the post-TOTP completion path so
    the two stay in lockstep.
    """
    ip = brute_force._client_ip(request)
    ua = _user_agent(request)

    known_ips = await audit_handler.get_known_ips(user.username)
    is_new_ip = bool(known_ips) and ip not in known_ips

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


@router.post("/login", response_model=LoginResponse)
async def login(req: LoginRequest, request: Request) -> LoginResponse:
    """Authenticate a user. Returns access+refresh, or a TOTP challenge.

    When the user has 2FA enabled, the response carries `requires_totp: True`
    and a short-lived `challenge_token` instead of access/refresh tokens. The
    client then submits the 6-digit code (or a recovery code) to
    /auth/login-totp to complete the session.
    """
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

    # Password OK. If 2FA is enrolled, gate the session behind a TOTP challenge.
    if user.totp_enabled and user.totp_secret:
        challenge = _create_totp_challenge_token(user.id)
        await log_event(request, "login_totp_required", username=user.username)
        return LoginResponse(requires_totp=True, challenge_token=challenge)

    # No 2FA: complete login immediately.
    await brute_force.record_success(request)
    await log_event(request, "login_ok", username=user.username)
    tokens = await _issue_session_tokens(user, request)
    return LoginResponse(
        requires_totp=False,
        access_token=tokens.access_token,
        refresh_token=tokens.refresh_token,
    )


@router.post("/login-totp", response_model=TokenResponse)
async def login_totp(req: LoginTotpRequest, request: Request) -> TokenResponse:
    """Complete a TOTP-gated login.

    Accepts the challenge token issued by /auth/login plus either a 6-digit
    code from the user's authenticator OR a single-use recovery code. Recovery
    codes are bcrypt-hashed at rest and consumed on use. The challenge token's
    jti is added to the Redis blacklist on success so it cannot be replayed.
    """
    blocked, remaining = await brute_force.check_ip(request)
    if blocked:
        raise HTTPException(status_code=429, detail=f"Too many failed attempts. Try again in {remaining}s.")

    payload = _decode_totp_challenge_token(req.challenge_token)
    if payload is None:
        await brute_force.record_failure(request)
        raise HTTPException(status_code=400, detail="Invalid or expired challenge")

    jti = payload.get("jti")
    if jti and await _is_reset_jti_revoked(jti):
        # Re-using the revoked_jti namespace - same TTL contract, smaller code.
        raise HTTPException(status_code=400, detail="Challenge already used")

    try:
        user_id = int(payload["sub"])
    except (KeyError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid challenge")

    user = await _users_db.get_by_id(user_id)
    if not user or not user.enabled or not user.totp_enabled or not user.totp_secret:
        raise HTTPException(status_code=400, detail="Invalid challenge")

    from handler.auth.totp import verify_code, consume_recovery_code

    # First try the live TOTP, fall back to recovery codes for the lockout case.
    code_ok = verify_code(user.totp_secret, req.code)
    used_recovery = False
    new_recovery: list[str] | None = None
    if not code_ok:
        consumed, remaining_codes = consume_recovery_code(user.totp_recovery_codes, req.code)
        if consumed:
            code_ok = True
            used_recovery = True
            new_recovery = remaining_codes

    if not code_ok:
        await brute_force.record_failure(request)
        await log_event(request, "login_totp_fail", username=user.username, status="fail")
        raise HTTPException(status_code=401, detail="Invalid 2FA code")

    if used_recovery and new_recovery is not None:
        await _users_db.update(user, {"totp_recovery_codes": new_recovery})
        await log_event(request, "totp_recovery_used", username=user.username,
                        details=f"{len(new_recovery)} codes left", status="warn")

    # Burn the challenge so it cannot be replayed within its 5-minute lifetime.
    if jti:
        try:
            await _revoke_reset_jti(jti, int(payload.get("exp", 0)))
        except Exception:
            pass

    await brute_force.record_success(request)
    await log_event(request, "login_ok", username=user.username,
                    details="totp" if not used_recovery else "totp_recovery")
    return await _issue_session_tokens(user, request)


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


def _decode_reset_token(token: str) -> dict | None:
    """Decode a password-reset JWT. Returns the full payload or None on failure.

    Caller is responsible for additionally checking the jti against the Redis
    blacklist so a successfully used token cannot be replayed within its 1h TTL.
    """
    try:
        payload = jwt.decode(token, AUTH_SECRET_KEY, algorithms=[AUTH_ALGORITHM])
        if payload.get("type") != "password_reset":
            return None
        # Sanity-check required claims
        int(payload["sub"])
        return payload
    except (JWTError, KeyError, ValueError):
        return None


async def _is_reset_jti_revoked(jti: str) -> bool:
    """Return True when the reset token's jti is on the Redis blacklist."""
    try:
        from handler.auth.brute_force import _get_redis
        r = _get_redis()
        return await r.exists(f"revoked_jti:{jti}") > 0
    except Exception:
        # Fail open on Redis outage - reset still gated by token validity
        return False


async def _revoke_reset_jti(jti: str, exp_unix: int) -> None:
    """Add a reset token's jti to the Redis blacklist until it would expire."""
    try:
        from handler.auth.brute_force import _get_redis
        r = _get_redis()
        ttl = max(60, int(exp_unix - datetime.now(timezone.utc).timestamp()))
        await r.set(f"revoked_jti:{jti}", "1", ex=ttl)
    except Exception:
        logger.warning("Could not blacklist reset jti (Redis unavailable)")


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

    payload = _decode_reset_token(req.token)
    if payload is None:
        raise HTTPException(status_code=400, detail="Invalid or expired reset link")

    jti = payload.get("jti")
    if jti and await _is_reset_jti_revoked(jti):
        # Token was already used to reset this account; do not allow replay.
        raise HTTPException(status_code=400, detail="Invalid or expired reset link")

    try:
        user_id = int(payload["sub"])
    except (KeyError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid or expired reset link")

    user = await _users_db.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=400, detail="Invalid or expired reset link")

    if len(req.password) < 8 or not any(c.isalpha() for c in req.password) or not any(c.isdigit() for c in req.password):
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters with at least one letter and one digit")

    await _users_db.update(user, {"hashed_password": hash_password(req.password)})
    await session_handler.revoke_all_for_user(user.username)

    # Burn the reset jti so the same link cannot be used twice. TTL matches the
    # token's remaining validity so Redis cleans up automatically.
    if jti:
        try:
            await _revoke_reset_jti(jti, int(payload.get("exp", 0)))
        except Exception:
            logger.warning("Reset jti blacklist write failed (non-fatal)")

    await log_event(request, "password_reset", username=user.username)
    logger.info("Password reset completed for user %s", user.username)

    return {"ok": True}


# ── Two-factor authentication (TOTP) ─────────────────────────────────────────
# Enrollment is a two-step ritual:
#   1. POST /auth/2fa/setup  - generates a candidate secret, stashes it in
#      Redis under auth:totp_pending:<user_id>, returns the otpauth:// URI for
#      the QR code and the base32 secret for manual entry.
#   2. POST /auth/2fa/verify - the user submits a 6-digit code from their
#      authenticator. On match the secret is moved from Redis to the users
#      table, totp_enabled flips true, and a one-shot recovery list is shown.
#
# Disabling requires both the password (defence against a temporarily borrowed
# session) and a valid current code (proof the user still has the device).

from decorators.auth import protected_route
from handler.auth.scopes import Scope


def _user_or_401(request: Request) -> User:
    user = getattr(request.state, "user", None)
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user


@protected_route(router.post, "/2fa/setup", response_model=Enable2FAStartResponse, scopes=[Scope.LIBRARY_READ])
async def setup_2fa(request: Request) -> Enable2FAStartResponse:
    """Stage a fresh TOTP secret and return the provisioning URI.

    Calling this while 2FA is already enabled rotates the staged secret without
    breaking the live one - actual rotation happens only after /verify succeeds.
    """
    from handler.auth.totp import generate_secret, provisioning_uri, render_qr_svg, stash_pending_secret

    user = _user_or_401(request)
    secret = generate_secret()
    await stash_pending_secret(user.id, secret)
    uri = provisioning_uri(secret, user.username)
    qr  = render_qr_svg(uri)
    return Enable2FAStartResponse(secret=secret, provisioning_uri=uri, qr_svg=qr)


@protected_route(router.post, "/2fa/verify", response_model=Enable2FAVerifyResponse, scopes=[Scope.LIBRARY_READ])
async def verify_2fa(request: Request, req: Enable2FAVerifyRequest) -> Enable2FAVerifyResponse:
    """Activate 2FA after the user proves they configured the authenticator."""
    from handler.auth.totp import (
        pop_pending_secret,
        verify_code,
        generate_recovery_codes,
        hash_recovery_codes,
    )

    user = _user_or_401(request)
    secret = await pop_pending_secret(user.id)
    if not secret:
        raise HTTPException(status_code=400, detail="No pending 2FA setup. Start over from Settings.")

    if not verify_code(secret, req.code):
        # Re-stash the secret so the user does not have to scan a fresh QR after
        # one mistyped code.
        from handler.auth.totp import stash_pending_secret
        await stash_pending_secret(user.id, secret)
        raise HTTPException(status_code=400, detail="Invalid code. Try again.")

    plain_codes = generate_recovery_codes(10)
    hashed = hash_recovery_codes(plain_codes)

    await _users_db.update(user, {
        "totp_secret":         secret,
        "totp_enabled":        True,
        "totp_recovery_codes": hashed,
    })
    await log_event(request, "totp_enabled", username=user.username)
    logger.info("2FA enabled for user %s", user.username)

    return Enable2FAVerifyResponse(enabled=True, recovery_codes=plain_codes)


@protected_route(router.post, "/2fa/disable", scopes=[Scope.LIBRARY_READ])
async def disable_2fa(request: Request, req: Disable2FARequest) -> dict:
    """Turn 2FA off. Requires password AND a valid current TOTP / recovery code."""
    from handler.auth.totp import verify_code, consume_recovery_code

    user = _user_or_401(request)
    if not user.totp_enabled or not user.totp_secret:
        raise HTTPException(status_code=400, detail="2FA is not enabled")

    if not verify_password(req.password, user.hashed_password):
        await log_event(request, "totp_disable_fail", username=user.username, status="fail")
        raise HTTPException(status_code=401, detail="Incorrect password")

    code_ok = verify_code(user.totp_secret, req.code)
    if not code_ok:
        consumed, _remaining = consume_recovery_code(user.totp_recovery_codes, req.code)
        if not consumed:
            await log_event(request, "totp_disable_fail", username=user.username, status="fail")
            raise HTTPException(status_code=401, detail="Invalid 2FA code")

    await _users_db.update(user, {
        "totp_secret":         None,
        "totp_enabled":        False,
        "totp_recovery_codes": None,
    })
    await log_event(request, "totp_disabled", username=user.username, status="warn")
    logger.info("2FA disabled for user %s", user.username)
    return {"ok": True}


@protected_route(router.post, "/2fa/recovery-regenerate", response_model=Enable2FAVerifyResponse, scopes=[Scope.LIBRARY_READ])
async def regenerate_recovery_codes(request: Request, req: Disable2FARequest) -> Enable2FAVerifyResponse:
    """Mint a fresh recovery list. Old codes stop working immediately."""
    from handler.auth.totp import (
        verify_code,
        consume_recovery_code,
        generate_recovery_codes,
        hash_recovery_codes,
    )

    user = _user_or_401(request)
    if not user.totp_enabled or not user.totp_secret:
        raise HTTPException(status_code=400, detail="2FA is not enabled")

    if not verify_password(req.password, user.hashed_password):
        raise HTTPException(status_code=401, detail="Incorrect password")

    code_ok = verify_code(user.totp_secret, req.code)
    if not code_ok:
        consumed, _remaining = consume_recovery_code(user.totp_recovery_codes, req.code)
        if not consumed:
            raise HTTPException(status_code=401, detail="Invalid 2FA code")

    plain = generate_recovery_codes(10)
    hashed = hash_recovery_codes(plain)
    await _users_db.update(user, {"totp_recovery_codes": hashed})
    await log_event(request, "totp_recovery_regenerated", username=user.username)
    return Enable2FAVerifyResponse(enabled=True, recovery_codes=plain)


@protected_route(router.get, "/2fa/status", response_model=TotpStatusResponse, scopes=[Scope.LIBRARY_READ])
async def status_2fa(request: Request) -> TotpStatusResponse:
    user = _user_or_401(request)
    return TotpStatusResponse(
        enabled=bool(user.totp_enabled),
        recovery_codes_left=len(user.totp_recovery_codes or []),
    )


@protected_route(router.post, "/2fa/admin-disable/{user_id}", scopes=[Scope.USERS_WRITE])
async def admin_disable_2fa(request: Request, user_id: int) -> dict:
    """Admin recovery: clear another user's 2FA when they have lost their device.

    This is the break-glass path for the lockout case where the user has neither
    their authenticator nor any recovery codes. It bypasses the password+code
    proof required by /2fa/disable. To keep the admin pool honest:

    - it is restricted to USERS_WRITE (admin role)
    - the action is recorded in the audit log with `actor_username` and target
    - both the target user (if they have an email on file) and the admin alert
      pool receive an email notification when SMTP is configured
    """
    admin = _user_or_401(request)
    target = await _users_db.get_by_id(user_id)
    if not target:
        from exceptions.common import NotFoundException
        raise NotFoundException("User", user_id)
    if not target.totp_enabled and not target.totp_secret and not target.totp_recovery_codes:
        # Idempotent no-op: 2FA was already off. Still log it for audit clarity.
        await log_event(
            request, "totp_admin_disable_noop", username=target.username,
            details=f"by={admin.username}", status="info",
        )
        return {"ok": True, "already_disabled": True}

    target_email = target.email
    target_username = target.username

    await _users_db.update(target, {
        "totp_secret":         None,
        "totp_enabled":        False,
        "totp_recovery_codes": None,
    })
    await log_event(
        request, "totp_admin_disabled", username=target_username,
        details=f"by={admin.username}", status="warn",
    )
    logger.info("Admin %s reset 2FA for user %s", admin.username, target_username)

    # Email both parties. Best-effort, never blocks the response.
    from handler.email.alerts import notify_2fa_admin_reset
    client_ip = request.client.host if request.client else None
    fire_task(notify_2fa_admin_reset(target_username, target_email, admin.username, client_ip))

    return {"ok": True, "already_disabled": False}
