"""WebSocket event emitter - broadcasts real-time events to connected clients.

Events: sync_progress, scrape_progress, download_progress, scan_progress, etc.
"""

from __future__ import annotations

import logging
from typing import Any

import socketio

logger = logging.getLogger(__name__)

def _get_cors_origins() -> list[str] | str:
    """Read CORS origins from env or default to permissive for local dev."""
    import os
    raw = os.environ.get("GD_CORS_ORIGINS", "")
    if not raw or raw.strip() == "*":
        return "*"
    return [o.strip() for o in raw.split(",") if o.strip()]

sio = socketio.AsyncServer(
    async_mode="asgi",
    cors_allowed_origins=_get_cors_origins(),
    logger=False,
    engineio_logger=False,
)


async def emit_event(event: str, data: dict[str, Any]) -> None:
    """Broadcast an event to all connected WebSocket clients."""
    try:
        await sio.emit(event, data)
    except Exception:
        logger.exception("Failed to emit event '%s'", event)


async def emit_progress(
    event: str,
    current: int,
    total: int,
    message: str = "",
    extra: dict[str, Any] | None = None,
) -> None:
    """Emit a progress event with standardised payload."""
    data = {
        "current": current,
        "total": total,
        "progress": round(current / total * 100, 1) if total > 0 else 0,
        "message": message,
    }
    if extra:
        data.update(extra)
    await emit_event(event, data)


@sio.event
async def connect(sid: str, environ: dict) -> None:
    logger.debug("WebSocket client connected: %s", sid)


@sio.event
async def disconnect(sid: str) -> None:
    logger.debug("WebSocket client disconnected: %s", sid)
