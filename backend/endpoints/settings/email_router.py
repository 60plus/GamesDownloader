"""Security alert configuration - uses shared Notifications SMTP settings."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from decorators.auth import protected_route
from handler.config.config_handler import config_handler

router = APIRouter(prefix="/api/settings/security/email", tags=["email"])


class AlertConfig(BaseModel):
    smtp_to:                str  = ""
    alert_on_failed_login:  bool = True
    alert_on_new_ip:        bool = True
    alert_on_new_user:      bool = True
    alert_on_new_admin:     bool = True
    alert_on_brute_force:   bool = True


@protected_route(router.get, "", response_model=AlertConfig)
async def get_alert_config(request: Request) -> AlertConfig:
    return AlertConfig(
        smtp_to               = await config_handler.get("alert_smtp_to")                    or "",
        alert_on_failed_login = await config_handler.get_bool("alert_on_failed_login",  default=True),
        alert_on_new_ip       = await config_handler.get_bool("alert_on_new_ip",        default=True),
        alert_on_new_user     = await config_handler.get_bool("alert_on_new_user",      default=True),
        alert_on_new_admin    = await config_handler.get_bool("alert_on_new_admin",     default=True),
        alert_on_brute_force  = await config_handler.get_bool("alert_on_brute_force",   default=True),
    )


@protected_route(router.post, "")
async def save_alert_config(request: Request, data: AlertConfig) -> dict:
    await config_handler.set_many({
        "alert_smtp_to":          (data.smtp_to,                             False),
        "alert_on_failed_login":  (str(data.alert_on_failed_login).lower(),  False),
        "alert_on_new_ip":        (str(data.alert_on_new_ip).lower(),        False),
        "alert_on_new_user":      (str(data.alert_on_new_user).lower(),      False),
        "alert_on_new_admin":     (str(data.alert_on_new_admin).lower(),     False),
        "alert_on_brute_force":   (str(data.alert_on_brute_force).lower(),   False),
    })
    return {"ok": True}


@protected_route(router.post, "/test")
async def test_alert_email(request: Request) -> dict:
    """Send a test alert email using the shared Notifications SMTP config."""
    host      = await config_handler.get("smtp_host")         or ""
    port_str  = await config_handler.get("smtp_port")         or "587"
    user      = await config_handler.get("smtp_username")     or ""
    password  = await config_handler.get("smtp_password")     or ""
    from_addr = await config_handler.get("smtp_from_address") or ""
    to_addr   = await config_handler.get("alert_smtp_to")     or ""
    use_tls   = await config_handler.get_bool("smtp_use_tls", default=True)
    tls_mode  = "starttls" if use_tls else "none"

    if not host:
        raise HTTPException(status_code=400, detail="SMTP not configured. Go to Settings → Notifications to set up SMTP first.")
    if not to_addr:
        raise HTTPException(status_code=400, detail="Alert recipient address (smtp_to) is not configured.")

    try:
        port = int(port_str)
    except ValueError:
        port = 587

    from handler.email.smtp_sender import send_email
    try:
        await send_email(
            host      = host,
            port      = port,
            user      = user,
            password  = password,
            from_addr = from_addr,
            to_addr   = to_addr,
            subject   = "[GamesDownloader] Test alert email",
            body_html = """<!DOCTYPE html><html><body
                style="font-family:'Segoe UI',Arial,sans-serif;background:#0f0f13;color:#c0c0d0;padding:32px;margin:0;">
                <div style="max-width:480px;margin:0 auto;background:#1a1a24;border:1px solid #2a2a3a;
                    border-radius:12px;padding:28px;">
                  <div style="font-size:22px;margin-bottom:10px;">&#10003;</div>
                  <h2 style="color:#a78bfa;margin:0 0 12px 0;">Security alerts are working</h2>
                  <p style="color:#808090;font-size:13px;margin:0;">
                    If you received this message, GamesDownloader security email alerts are correctly configured.
                  </p>
                </div>
              </body></html>""",
            tls_mode  = tls_mode,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to send: {exc}")
    return {"ok": True}
