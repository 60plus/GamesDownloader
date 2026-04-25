"""Convenience wrappers for audit logging from request context."""
from __future__ import annotations

from handler.database.audit_handler import audit_handler
from handler.auth.brute_force import _client_ip


async def log_event(
    request,
    action: str,
    username: str | None = None,
    details: dict | str | None = None,
    status: str = "ok",
) -> None:
    ip = _client_ip(request) if request else None
    await audit_handler.log(
        action=action,
        username=username,
        ip_address=ip,
        details=details,
        status=status,
    )
