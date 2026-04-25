"""SSO / OAuth2 public endpoints.

GET  /api/auth/sso/providers             - list enabled providers (for Login page)
GET  /api/auth/sso/{provider}            - initiate flow (redirect to provider)
GET  /api/auth/sso/{provider}/callback   - handle OAuth callback
GET  /api/auth/sso/session/{sid}         - one-time JWT pickup (60 s TTL)
"""
from __future__ import annotations

import logging
import secrets

import redis.asyncio as aioredis
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import RedirectResponse

from config import REDIS_URL

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/auth/sso", tags=["sso"])

_SSO_RATE_PREFIX = "gd:sso:rate:"
_SSO_RATE_LIMIT  = 10   # max initiations per window
_SSO_RATE_WINDOW = 60   # seconds

# Reuse the same atomic Lua pattern as brute_force.py
_LUA_INCR_EXPIRE = """
local count = redis.call('incr', KEYS[1])
if count == 1 then
  redis.call('expire', KEYS[1], tonumber(ARGV[1]))
end
return count
"""

_redis: aioredis.Redis | None = None

def _get_redis() -> aioredis.Redis:
    global _redis
    if _redis is None:
        _redis = aioredis.from_url(REDIS_URL, decode_responses=True)
    return _redis


async def _check_sso_rate(ip: str) -> bool:
    """Return True if request is allowed, False if rate-limited."""
    try:
        r = _get_redis()
        count = await r.eval(_LUA_INCR_EXPIRE, 1, f"{_SSO_RATE_PREFIX}{ip}", _SSO_RATE_WINDOW)
        return count <= _SSO_RATE_LIMIT
    except Exception:
        return True  # Redis down - allow through


# ── Helpers ───────────────────────────────────────────────────────────────────

def _base_url(request: Request) -> str:
    """Return scheme://host - works behind reverse proxies."""
    fwd_proto = request.headers.get("X-Forwarded-Proto", "")
    scheme    = fwd_proto or request.url.scheme
    host      = request.headers.get("X-Forwarded-Host", "") or request.headers.get("Host", "") or request.url.netloc
    return f"{scheme}://{host}"


def _callback_uri(request: Request, provider: str) -> str:
    return f"{_base_url(request)}/api/auth/sso/{provider}/callback"


def _frontend_error(request: Request, code: str) -> RedirectResponse:
    return RedirectResponse(f"{_base_url(request)}/login?sso_error={code}", status_code=302)


# ── Providers list (used by Login page) ───────────────────────────────────────

@router.get("/providers")
async def list_providers() -> dict:
    """Return enabled SSO providers and the login mode."""
    from handler.config.config_handler import config_handler

    login_mode = await config_handler.get("sso_login_mode") or "alongside"
    providers  = []

    if await config_handler.get_bool("oidc_enabled", default=False):
        name = await config_handler.get("oidc_provider_name") or "SSO"
        providers.append({"id": "oidc", "name": name, "icon": "oidc"})

    if await config_handler.get_bool("oauth_google_enabled", default=False):
        providers.append({"id": "google", "name": "Google", "icon": "google"})

    if await config_handler.get_bool("oauth_github_enabled", default=False):
        providers.append({"id": "github", "name": "GitHub", "icon": "github"})

    if await config_handler.get_bool("oauth_microsoft_enabled", default=False):
        providers.append({"id": "microsoft", "name": "Microsoft", "icon": "microsoft"})

    return {"providers": providers, "login_mode": login_mode}


# ── Initiate ──────────────────────────────────────────────────────────────────

@router.get("/{provider}", response_class=RedirectResponse)
async def sso_initiate(request: Request, provider: str):
    if provider not in ("oidc", "google", "github", "microsoft"):
        raise HTTPException(status_code=404, detail="Unknown provider")

    ip = (request.headers.get("CF-Connecting-IP")
          or request.headers.get("X-Real-IP")
          or (request.client.host if request.client else "unknown"))
    if not await _check_sso_rate(ip):
        logger.warning("SSO rate limit exceeded for IP %s", ip)
        return _frontend_error(request, "provider_error")

    from handler.auth.sso import initiate_flow
    try:
        auth_url = await initiate_flow(provider, _callback_uri(request, provider))
    except ValueError as exc:
        logger.warning("SSO initiate failed (%s): %s", provider, exc)
        return _frontend_error(request, "not_configured")
    except Exception as exc:
        logger.error("SSO initiate error (%s): %s", provider, exc)
        return _frontend_error(request, "provider_error")

    return RedirectResponse(auth_url, status_code=302)


# ── Callback ──────────────────────────────────────────────────────────────────

@router.get("/{provider}/callback")
async def sso_callback(
    request: Request,
    provider: str,
    code:  str | None = Query(default=None),
    state: str | None = Query(default=None),
    error: str | None = Query(default=None),
):
    if error:
        logger.info("SSO callback: provider returned error=%s", error)
        return _frontend_error(request, "provider_denied")

    if not code or not state:
        return _frontend_error(request, "missing_params")

    if provider not in ("oidc", "google", "github", "microsoft"):
        return _frontend_error(request, "unknown_provider")

    from handler.auth.sso import handle_callback, find_user, store_session
    from handler.auth.tokens import create_access_token, create_refresh_token
    from handler.auth.scopes import scopes_for_role, apply_permission_overrides
    from handler.database.session_handler import session_handler
    from handler.database.audit_handler import audit_handler

    ip = request.headers.get("CF-Connecting-IP") or request.headers.get("X-Real-IP") or (request.client.host if request.client else "unknown")
    ua = request.headers.get("User-Agent", "")

    # Exchange code for user info
    try:
        user_info = await handle_callback(provider, code, state, _callback_uri(request, provider))
    except ValueError as exc:
        logger.warning("SSO callback failed (%s): %s", provider, exc)
        return _frontend_error(request, "state_invalid" if "state" in str(exc).lower() else "token_error")
    except Exception as exc:
        logger.error("SSO callback error (%s): %s", provider, exc)
        return _frontend_error(request, "provider_error")

    # Find user in DB
    user = await find_user(user_info)
    if not user:
        logger.info("SSO login: no matching user for email=%s username=%s",
                    user_info.get("email"), user_info.get("username"))
        await audit_handler.log("sso_no_user", ip_address=ip,
                                details={"provider": provider, "email": user_info.get("email")},
                                status="fail")
        return _frontend_error(request, "user_not_found")

    if not user.enabled:
        await audit_handler.log("sso_disabled", username=user.username, ip_address=ip, status="fail")
        return _frontend_error(request, "account_disabled")

    # Issue tokens
    scopes      = scopes_for_role(user.role)
    scopes      = apply_permission_overrides(user.permissions, scopes)
    access_jti  = secrets.token_hex(16)
    refresh_jti = secrets.token_hex(16)

    access_token  = create_access_token(user.username, list(scopes), role=user.role, jti=access_jti)
    refresh_token = create_refresh_token(user.username, jti=refresh_jti)

    await session_handler.create(
        username=user.username, access_jti=access_jti, refresh_jti=refresh_jti,
        ip_address=ip, user_agent=ua,
    )
    await audit_handler.log("login_ok", username=user.username, ip_address=ip,
                            details={"via": f"sso:{provider}"})

    sid = await store_session(access_token, refresh_token)
    return RedirectResponse(f"{_base_url(request)}/sso-callback?sid={sid}", status_code=302)


# ── One-time session pickup ───────────────────────────────────────────────────

@router.get("/session/{sid}")
async def sso_session(sid: str) -> dict:
    """Frontend calls this once to retrieve the JWT. Token deleted after retrieval."""
    from handler.auth.sso import pop_session
    data = await pop_session(sid)
    if not data:
        raise HTTPException(status_code=404, detail="SSO session expired or already used")
    return data
