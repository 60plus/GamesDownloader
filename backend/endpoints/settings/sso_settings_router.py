"""SSO / OAuth settings - admin configuration."""
from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

from decorators.auth import protected_route
from handler.auth.scopes import Scope
from handler.config.config_handler import config_handler

router = APIRouter(prefix="/api/settings/security/sso", tags=["sso-settings"])


class SsoConfig(BaseModel):
    login_mode: str = "alongside"   # "alongside" | "replace"

    # Generic OIDC
    oidc_enabled:        bool = False
    oidc_provider_name:  str  = ""
    oidc_discovery_url:  str  = ""
    oidc_client_id:      str  = ""
    oidc_client_secret:  str  = ""
    oidc_scopes:         str  = "openid email profile"

    # Google
    oauth_google_enabled:        bool = False
    oauth_google_client_id:      str  = ""
    oauth_google_client_secret:  str  = ""

    # GitHub
    oauth_github_enabled:        bool = False
    oauth_github_client_id:      str  = ""
    oauth_github_client_secret:  str  = ""

    # Microsoft
    oauth_microsoft_enabled:        bool = False
    oauth_microsoft_client_id:      str  = ""
    oauth_microsoft_client_secret:  str  = ""
    oauth_microsoft_tenant:         str  = "common"


@protected_route(router.get, "", scopes=[Scope.SETTINGS_READ])
async def get_sso_config(request: Request) -> SsoConfig:
    return SsoConfig(
        login_mode              = await config_handler.get("sso_login_mode")              or "alongside",
        oidc_enabled            = await config_handler.get_bool("oidc_enabled",            default=False),
        oidc_provider_name      = await config_handler.get("oidc_provider_name")           or "",
        oidc_discovery_url      = await config_handler.get("oidc_discovery_url")           or "",
        oidc_client_id          = await config_handler.get("oidc_client_id")               or "",
        oidc_client_secret      = await config_handler.get("oidc_client_secret")           or "",
        oidc_scopes             = await config_handler.get("oidc_scopes")                  or "openid email profile",
        oauth_google_enabled    = await config_handler.get_bool("oauth_google_enabled",    default=False),
        oauth_google_client_id  = await config_handler.get("oauth_google_client_id")       or "",
        oauth_google_client_secret  = await config_handler.get("oauth_google_client_secret") or "",
        oauth_github_enabled    = await config_handler.get_bool("oauth_github_enabled",    default=False),
        oauth_github_client_id  = await config_handler.get("oauth_github_client_id")       or "",
        oauth_github_client_secret  = await config_handler.get("oauth_github_client_secret") or "",
        oauth_microsoft_enabled = await config_handler.get_bool("oauth_microsoft_enabled", default=False),
        oauth_microsoft_client_id   = await config_handler.get("oauth_microsoft_client_id")   or "",
        oauth_microsoft_client_secret = await config_handler.get("oauth_microsoft_client_secret") or "",
        oauth_microsoft_tenant  = await config_handler.get("oauth_microsoft_tenant")       or "common",
    )


@protected_route(router.post, "", scopes=[Scope.SETTINGS_WRITE])
async def save_sso_config(request: Request, data: SsoConfig) -> dict:
    if data.login_mode not in ("alongside", "replace"):
        data.login_mode = "alongside"
    await config_handler.set_many({
        "sso_login_mode":             (data.login_mode,                              False),
        "oidc_enabled":               (str(data.oidc_enabled).lower(),               False),
        "oidc_provider_name":         (data.oidc_provider_name,                      False),
        "oidc_discovery_url":         (data.oidc_discovery_url,                      False),
        "oidc_client_id":             (data.oidc_client_id,                          False),
        "oidc_client_secret":         (data.oidc_client_secret,                      True),
        "oidc_scopes":                (data.oidc_scopes,                             False),
        "oauth_google_enabled":       (str(data.oauth_google_enabled).lower(),       False),
        "oauth_google_client_id":     (data.oauth_google_client_id,                  False),
        "oauth_google_client_secret": (data.oauth_google_client_secret,              True),
        "oauth_github_enabled":       (str(data.oauth_github_enabled).lower(),       False),
        "oauth_github_client_id":     (data.oauth_github_client_id,                  False),
        "oauth_github_client_secret": (data.oauth_github_client_secret,              True),
        "oauth_microsoft_enabled":    (str(data.oauth_microsoft_enabled).lower(),    False),
        "oauth_microsoft_client_id":  (data.oauth_microsoft_client_id,               False),
        "oauth_microsoft_client_secret": (data.oauth_microsoft_client_secret,        True),
        "oauth_microsoft_tenant":     (data.oauth_microsoft_tenant or "common",      False),
    })
    # Invalidate OIDC discovery cache
    from handler.auth.sso import _discovery_cache
    _discovery_cache.clear()
    return {"ok": True}
