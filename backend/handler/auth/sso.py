"""SSO / OAuth2 / OIDC helpers.

Supported providers
-------------------
  oidc     - generic OpenID Connect (Keycloak, Authentik, …)
  google   - Google OAuth2 (OIDC-compatible)
  github   - GitHub OAuth2  (no OIDC, custom user-info endpoint)
  microsoft- Microsoft / Azure AD (OIDC-compatible)

Flow
----
1. initiate_flow()  - build authorization URL, persist state in Redis (10 min)
2. handle_callback() - verify state, exchange code for tokens, fetch user-info
3. find_user()       - match DB user by email → username
"""
from __future__ import annotations

import logging
import secrets
from datetime import datetime, timezone
from typing import Any

import redis.asyncio as aioredis

from config import REDIS_URL

logger = logging.getLogger(__name__)

_STATE_PREFIX = "sso_state:"
_STATE_TTL    = 600   # 10 minutes
_SID_PREFIX   = "sso_sid:"
_SID_TTL      = 60    # 1 minute - frontend must collect JWT quickly

# ── Redis helpers ─────────────────────────────────────────────────────────────

def _redis():
    return aioredis.from_url(REDIS_URL, decode_responses=True)


# ── OIDC discovery cache (in-process, refreshed after 1 h) ───────────────────

_discovery_cache: dict[str, tuple[dict, datetime]] = {}


async def _discover(url: str) -> dict:
    """Fetch and cache the OpenID Connect discovery document."""
    import httpx
    cached = _discovery_cache.get(url)
    if cached:
        doc, ts = cached
        if (datetime.now(timezone.utc) - ts).total_seconds() < 3600:
            return doc
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.get(url)
        r.raise_for_status()
        doc = r.json()
    _discovery_cache[url] = (doc, datetime.now(timezone.utc))
    return doc


# ── Provider config ───────────────────────────────────────────────────────────

_GOOGLE_DISCOVERY    = "https://accounts.google.com/.well-known/openid-configuration"
_MICROSOFT_DISCOVERY = "https://login.microsoftonline.com/{tenant}/v2.0/.well-known/openid-configuration"

# GitHub doesn't support OIDC - fixed endpoints
_GITHUB_AUTH_URL     = "https://github.com/login/oauth/authorize"
_GITHUB_TOKEN_URL    = "https://github.com/login/oauth/access_token"
_GITHUB_USER_URL     = "https://api.github.com/user"
_GITHUB_EMAILS_URL   = "https://api.github.com/user/emails"


async def _provider_endpoints(provider: str) -> dict[str, str]:
    """Return {auth_url, token_url, userinfo_url} for the given provider."""
    from handler.config.config_handler import config_handler

    if provider == "github":
        return {
            "auth_url":     _GITHUB_AUTH_URL,
            "token_url":    _GITHUB_TOKEN_URL,
            "userinfo_url": _GITHUB_USER_URL,
        }

    if provider == "google":
        doc = await _discover(_GOOGLE_DISCOVERY)
    elif provider == "microsoft":
        tenant = await config_handler.get("oauth_microsoft_tenant") or "common"
        doc = await _discover(_MICROSOFT_DISCOVERY.format(tenant=tenant))
    elif provider == "oidc":
        discovery_url = await config_handler.get("oidc_discovery_url") or ""
        if not discovery_url:
            raise ValueError("OIDC discovery URL is not configured")
        doc = await _discover(discovery_url)
    else:
        raise ValueError(f"Unknown SSO provider: {provider}")

    return {
        "auth_url":     doc["authorization_endpoint"],
        "token_url":    doc["token_endpoint"],
        "userinfo_url": doc.get("userinfo_endpoint", ""),
    }


async def _provider_credentials(provider: str) -> tuple[str, str]:
    """Return (client_id, client_secret) for the given provider."""
    from handler.config.config_handler import config_handler
    if provider == "oidc":
        cid = await config_handler.get("oidc_client_id")     or ""
        sec = await config_handler.get("oidc_client_secret") or ""
    elif provider == "google":
        cid = await config_handler.get("oauth_google_client_id")     or ""
        sec = await config_handler.get("oauth_google_client_secret") or ""
    elif provider == "github":
        cid = await config_handler.get("oauth_github_client_id")     or ""
        sec = await config_handler.get("oauth_github_client_secret") or ""
    elif provider == "microsoft":
        cid = await config_handler.get("oauth_microsoft_client_id")     or ""
        sec = await config_handler.get("oauth_microsoft_client_secret") or ""
    else:
        raise ValueError(f"Unknown SSO provider: {provider}")
    return cid, sec


def _provider_scopes(provider: str) -> str:
    if provider == "github":
        return "read:user user:email"
    if provider == "microsoft":
        return "openid email profile"
    return "openid email profile"


# ── Initiate flow ─────────────────────────────────────────────────────────────

async def initiate_flow(provider: str, redirect_uri: str) -> str:
    """Store state in Redis and return the provider's authorization URL."""
    import urllib.parse

    endpoints  = await _provider_endpoints(provider)
    client_id, _ = await _provider_credentials(provider)
    if not client_id:
        raise ValueError(f"SSO provider '{provider}' client_id is not configured")

    state = secrets.token_urlsafe(32)
    async with _redis() as r:
        await r.setex(f"{_STATE_PREFIX}{state}", _STATE_TTL, provider)

    params: dict[str, str] = {
        "response_type": "code",
        "client_id":     client_id,
        "redirect_uri":  redirect_uri,
        "scope":         _provider_scopes(provider),
        "state":         state,
    }

    # OIDC providers may want additional scopes from config
    if provider == "oidc":
        from handler.config.config_handler import config_handler
        extra = await config_handler.get("oidc_scopes") or ""
        if extra:
            params["scope"] = extra

    return endpoints["auth_url"] + "?" + urllib.parse.urlencode(params)


# ── Handle callback ───────────────────────────────────────────────────────────

async def handle_callback(
    provider: str,
    code: str,
    state: str,
    redirect_uri: str,
) -> dict[str, Any]:
    """
    Verify state, exchange code for tokens, fetch user-info.
    Returns a dict with at least: email, username, name, raw.
    Raises ValueError on any failure.
    """
    import httpx

    # Verify state
    async with _redis() as r:
        stored_provider = await r.get(f"{_STATE_PREFIX}{state}")
        if stored_provider:
            await r.delete(f"{_STATE_PREFIX}{state}")

    if not stored_provider or stored_provider != provider:
        raise ValueError("Invalid or expired OAuth state - possible CSRF attempt")

    endpoints    = await _provider_endpoints(provider)
    client_id, client_secret = await _provider_credentials(provider)

    async with httpx.AsyncClient(timeout=15) as client:
        # Exchange code for access token
        if provider == "github":
            token_resp = await client.post(
                endpoints["token_url"],
                data={
                    "client_id":     client_id,
                    "client_secret": client_secret,
                    "code":          code,
                    "redirect_uri":  redirect_uri,
                },
                headers={"Accept": "application/json"},
            )
        else:
            token_resp = await client.post(
                endpoints["token_url"],
                data={
                    "grant_type":    "authorization_code",
                    "code":          code,
                    "redirect_uri":  redirect_uri,
                    "client_id":     client_id,
                    "client_secret": client_secret,
                },
                headers={"Accept": "application/json"},
            )

        if token_resp.status_code >= 400:
            raise ValueError(f"Token exchange failed: {token_resp.text}")
        token_data = token_resp.json()
        if "error" in token_data:
            raise ValueError(f"Token error: {token_data.get('error_description', token_data['error'])}")

        access_token = token_data.get("access_token", "")

        # Fetch user info
        if provider == "github":
            user_resp = await client.get(
                endpoints["userinfo_url"],
                headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
            )
            user_resp.raise_for_status()
            raw = user_resp.json()

            # GitHub may not expose email in /user - fetch separately
            email = raw.get("email") or ""
            if not email:
                emails_resp = await client.get(
                    _GITHUB_EMAILS_URL,
                    headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
                )
                if emails_resp.status_code == 200:
                    for entry in emails_resp.json():
                        if entry.get("primary") and entry.get("verified"):
                            email = entry.get("email", "")
                            break

            return {
                "email":    email,
                "username": raw.get("login", ""),
                "name":     raw.get("name") or raw.get("login", ""),
                "raw":      raw,
            }
        else:
            # OIDC - use id_token claims or userinfo endpoint
            userinfo_url = endpoints.get("userinfo_url", "")
            if userinfo_url:
                ui_resp = await client.get(
                    userinfo_url,
                    headers={"Authorization": f"Bearer {access_token}"},
                )
                ui_resp.raise_for_status()
                raw = ui_resp.json()
            else:
                # Fall back to id_token claims
                import base64, json as _json
                id_token = token_data.get("id_token", "")
                payload  = id_token.split(".")[1] if id_token else ""
                padding  = "=" * (4 - len(payload) % 4)
                raw = _json.loads(base64.urlsafe_b64decode(payload + padding))

            return {
                "email":    raw.get("email", ""),
                "username": raw.get("preferred_username") or raw.get("login") or raw.get("sub", ""),
                "name":     raw.get("name") or raw.get("given_name", ""),
                "raw":      raw,
            }


# ── Find DB user ──────────────────────────────────────────────────────────────

async def find_user(user_info: dict[str, Any]):
    """
    Match a DB user by email (case-insensitive) then by username.
    Returns the User ORM object or None.
    """
    from handler.database.users_handler import UsersHandler
    _users = UsersHandler()

    email    = (user_info.get("email") or "").strip().lower()
    username = (user_info.get("username") or "").strip()

    # Try email first
    if email:
        user = await _users.get_by_email(email)
        if user:
            return user

    # Fall back to username match
    if username:
        user = await _users.get_by_username(username)
        if user:
            return user

    return None


# ── Session store (one-time JWT pickup) ──────────────────────────────────────

async def store_session(access_token: str, refresh_token: str) -> str:
    """Store tokens in Redis, return sid for frontend to collect."""
    import json
    sid = secrets.token_urlsafe(32)
    async with _redis() as r:
        await r.setex(
            f"{_SID_PREFIX}{sid}",
            _SID_TTL,
            json.dumps({"access_token": access_token, "refresh_token": refresh_token}),
        )
    return sid


async def pop_session(sid: str) -> dict | None:
    """Retrieve and delete a one-time SSO session. Returns None if expired."""
    import json
    async with _redis() as r:
        raw = await r.get(f"{_SID_PREFIX}{sid}")
        if raw:
            await r.delete(f"{_SID_PREFIX}{sid}")
    return json.loads(raw) if raw else None
