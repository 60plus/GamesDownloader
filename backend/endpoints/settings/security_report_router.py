"""Security report settings - schedule and send periodic summary emails."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from decorators.auth import protected_route
from handler.auth.scopes import Scope
from handler.config.config_handler import config_handler

router = APIRouter(prefix="/api/settings/security/report", tags=["security-report"])


class ReportConfig(BaseModel):
    enabled:   bool = False
    frequency: str  = "weekly"   # "weekly" | "monthly"


@protected_route(router.get, "/config", scopes=[Scope.SETTINGS_READ])
async def get_report_config(request: Request) -> dict:
    last_sent = await config_handler.get("report_last_sent") or ""
    return {
        "enabled":    await config_handler.get_bool("report_enabled",  default=False),
        "frequency":  await config_handler.get("report_frequency")     or "weekly",
        "last_sent":  last_sent,
        "recipient":  await config_handler.get("alert_smtp_to")        or "",
    }


@protected_route(router.post, "/config", scopes=[Scope.SETTINGS_WRITE])
async def save_report_config(request: Request, data: ReportConfig) -> dict:
    if data.frequency not in ("weekly", "monthly"):
        raise HTTPException(status_code=400, detail="frequency must be 'weekly' or 'monthly'")
    await config_handler.set_many({
        "report_enabled":   (str(data.enabled).lower(),  False),
        "report_frequency": (data.frequency,              False),
    })
    return {"ok": True}


@protected_route(router.post, "/send-now", scopes=[Scope.SETTINGS_WRITE])
async def send_report_now(request: Request) -> dict:
    """Manually trigger report send using current frequency setting."""
    host    = await config_handler.get("smtp_host")         or ""
    to_addr = await config_handler.get("alert_smtp_to")     or ""
    if not host:
        raise HTTPException(status_code=400, detail="SMTP not configured. Go to Settings → Notifications first.")
    if not to_addr:
        raise HTTPException(status_code=400, detail="Alert recipient not configured in Email Alerts settings.")

    frequency = await config_handler.get("report_frequency") or "weekly"
    from handler.email.security_report import send_now
    try:
        await send_now(frequency)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to send report: {exc}")
    return {"ok": True}


@protected_route(router.get, "/preview", scopes=[Scope.SETTINGS_READ])
async def preview_report(request: Request) -> dict:
    """Return current-period stats without sending an email."""
    from datetime import datetime, timedelta, timezone
    frequency = await config_handler.get("report_frequency") or "weekly"
    since = datetime.now(timezone.utc) - timedelta(days=7 if frequency == "weekly" else 30)
    from handler.email.security_report import gather_report_data
    return await gather_report_data(since)
