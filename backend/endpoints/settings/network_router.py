"""Network & access security settings.

Covers:
  - Trusted proxy IPs (used by brute-force & allowlist for real-IP extraction)
  - IP allowlist (global block of unlisted IPs)
  - CORS allowed origins
  - Registration mode (open / disabled / invite_only)
  - Invite code management
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, field_validator

from decorators.auth import protected_route
from handler.auth.scopes import Scope
from handler.config.config_handler import config_handler
from handler.database.invite_handler import invite_handler

logger = logging.getLogger(__name__)

network_router = APIRouter(
    prefix="/api/settings/security/network", tags=["network-security"]
)


# ── Pydantic models ─────────────────────────────────────────────────────────────

class NetworkConfig(BaseModel):
    """Trusted proxies, IP allowlist, CORS origins."""
    trusted_proxies:      str  = ""     # comma-separated IPs / CIDRs
    ip_allowlist_enabled: bool = False
    ip_allowlist:         str  = ""     # comma-separated IPs / CIDRs
    cors_origins:         str  = ""     # comma-separated origins (* = wildcard)


class RegistrationConfig(BaseModel):
    mode: str = "open"   # "open" | "disabled" | "invite_only"

    @field_validator("mode")
    @classmethod
    def _validate_mode(cls, v: str) -> str:
        if v not in ("open", "disabled", "invite_only"):
            raise ValueError("mode must be 'open', 'disabled', or 'invite_only'")
        return v


class InviteCreateRequest(BaseModel):
    max_uses:   int           = 1
    expires_in_hours: int | None = None   # None = never expires
    note:       str | None    = None


# ── Network config ──────────────────────────────────────────────────────────────

@protected_route(network_router.get, "/config", scopes=[Scope.SETTINGS_READ])
async def get_network_config(request: Request):
    return {
        "trusted_proxies":      (await config_handler.get("trusted_proxies"))      or "",
        "ip_allowlist_enabled": await config_handler.get_bool("ip_allowlist_enabled", default=False),
        "ip_allowlist":         (await config_handler.get("ip_allowlist"))          or "",
        "cors_origins":         (await config_handler.get("cors_origins"))          or "",
    }


@protected_route(network_router.post, "/config", scopes=[Scope.SETTINGS_WRITE])
async def save_network_config(request: Request, body: NetworkConfig):
    await config_handler.set("trusted_proxies",      body.trusted_proxies)
    await config_handler.set("ip_allowlist_enabled", str(body.ip_allowlist_enabled).lower())
    await config_handler.set("ip_allowlist",         body.ip_allowlist)
    await config_handler.set("cors_origins",         body.cors_origins)
    logger.info("Network security config updated by %s", getattr(request.state, "user", "?"))
    return {"ok": True, "note": "CORS changes take effect after container restart."}


# ── Registration ────────────────────────────────────────────────────────────────

@protected_route(network_router.get, "/registration", scopes=[Scope.SETTINGS_READ])
async def get_registration(request: Request):
    # Legacy: enable_registrations (bool) → maps to open/disabled
    mode = await config_handler.get("registration_mode")
    if not mode:
        legacy = await config_handler.get_bool("enable_registrations", default=True)
        mode = "open" if legacy else "disabled"
    return {"mode": mode}


@protected_route(network_router.post, "/registration", scopes=[Scope.SETTINGS_WRITE])
async def save_registration(request: Request, body: RegistrationConfig):
    await config_handler.set("registration_mode", body.mode)
    # Keep legacy key in sync for backwards compat
    await config_handler.set("enable_registrations", str(body.mode == "open").lower())
    return {"ok": True}


# ── Invite codes ────────────────────────────────────────────────────────────────

def _fmt_invite(inv) -> dict:
    return {
        "id":         inv.id,
        "code":       inv.code,
        "created_by": inv.created_by,
        "note":       inv.note,
        "max_uses":   inv.max_uses,
        "use_count":  inv.use_count,
        "expires_at": inv.expires_at.isoformat() if inv.expires_at else None,
        "is_active":  inv.is_active,
        "created_at": inv.created_at.isoformat() if inv.created_at else None,
    }


@protected_route(network_router.get, "/invites", scopes=[Scope.SETTINGS_READ])
async def list_invites(request: Request):
    return [_fmt_invite(i) for i in await invite_handler.get_all()]


@protected_route(network_router.post, "/invites", scopes=[Scope.SETTINGS_WRITE])
async def create_invite(request: Request, body: InviteCreateRequest):
    user = getattr(request.state, "user", "admin")
    expires_at = None
    if body.expires_in_hours:
        from datetime import timedelta
        expires_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=body.expires_in_hours)
    inv = await invite_handler.create(
        created_by=user,
        max_uses=max(1, body.max_uses),
        expires_at=expires_at,
        note=body.note,
    )
    return _fmt_invite(inv)


@protected_route(network_router.delete, "/invites/{invite_id}", scopes=[Scope.SETTINGS_WRITE])
async def delete_invite(request: Request, invite_id: int):
    inv = await invite_handler.get_all()
    if not any(i.id == invite_id for i in inv):
        raise HTTPException(404, "Invite code not found")
    await invite_handler.delete(invite_id)
    return {"ok": True}
