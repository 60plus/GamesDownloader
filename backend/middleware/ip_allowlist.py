"""IP allowlist middleware - blocks requests from unlisted IPs when enabled.

Supports individual IPs and CIDR subnets (e.g. 192.168.1.0/24).
Loopback (127.0.0.1 / ::1) is always allowed.
Health-check, assets and setup paths bypass the check so the app
stays manageable even if the allowlist is misconfigured.
"""
from __future__ import annotations

import ipaddress
import logging

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

_BYPASS_PREFIXES = (
    "/api/health", "/api/setup", "/assets", "/resources",
    "/_vite", "/favicon", "/",
)


def _parse_networks(raw: str) -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
    nets: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
    for token in raw.split(","):
        token = token.strip()
        if not token:
            continue
        try:
            nets.append(ipaddress.ip_network(token, strict=False))
        except ValueError:
            logger.warning("IP allowlist: invalid entry %r - skipped", token)
    return nets


def _ip_allowed(ip_str: str, networks: list) -> bool:
    try:
        addr = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    if addr.is_loopback:
        return True
    return any(addr in net for net in networks)


class IpAllowlistMiddleware(BaseHTTPMiddleware):
    """Block all incoming requests whose source IP is not in the configured allowlist."""

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Static bypasses - never block these
        if any(path.startswith(p) for p in _BYPASS_PREFIXES):
            return await call_next(request)

        from handler.config.config_handler import config_handler
        enabled = await config_handler.get_bool("ip_allowlist_enabled", default=False)
        if not enabled:
            return await call_next(request)

        raw = (await config_handler.get("ip_allowlist")) or ""
        networks = _parse_networks(raw)
        if not networks:
            # Allowlist enabled but empty → allow all (misconfiguration safety net)
            return await call_next(request)

        # Use the same safe IP extraction logic as brute_force (only honours
        # CF-Connecting-IP / X-Real-IP / X-Forwarded-For when the direct TCP
        # peer is a trusted/private address, preventing header spoofing).
        from handler.auth.brute_force import _client_ip as _safe_client_ip
        candidate_ip = _safe_client_ip(request)

        if _ip_allowed(candidate_ip, networks):
            return await call_next(request)

        logger.warning(
            "IP allowlist: blocked %s → %s",
            candidate_ip, path,
        )
        return JSONResponse(
            {"detail": "Your IP address is not permitted to access this server."},
            status_code=403,
        )
