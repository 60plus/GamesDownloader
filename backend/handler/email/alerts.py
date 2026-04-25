"""Security email alert dispatcher.

Sends alerts to the admin on:
- login_fail - wrong password or unknown username (deduplicated per IP / 10 min)
- new_ip     - successful login from a previously unseen IP
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

_DEDUP_PREFIX = "alert_dedup:"
_DEDUP_TTL    = 600  # max 1 alert per (action, ip) per 10 minutes


async def _is_deduped(action: str, ip: str) -> bool:
    """Return True if an alert for this (action, ip) was already sent recently."""
    from config import REDIS_URL
    try:
        import redis.asyncio as aioredis
        async with aioredis.from_url(REDIS_URL, decode_responses=True) as r:
            key = f"{_DEDUP_PREFIX}{action}:{ip}"
            if await r.exists(key):
                return True
            await r.setex(key, _DEDUP_TTL, "1")
            return False
    except Exception:
        return False  # Redis down → send email anyway


async def maybe_alert(
    action:     str,
    username:   str | None,
    ip:         str | None,
    user_agent: str | None = None,
) -> None:
    """Conditionally send an email alert. All exceptions are swallowed."""
    try:
        await _dispatch(action, username, ip, user_agent)
    except Exception:
        logger.warning("Email alert dispatch failed", exc_info=True)


async def _dispatch(
    action:     str,
    username:   str | None,
    ip:         str | None,
    user_agent: str | None,
) -> None:
    from handler.config.config_handler import config_handler

    if not await config_handler.get_bool("smtp_enabled", default=False):
        return

    if action == "login_fail"  and not await config_handler.get_bool("alert_on_failed_login", default=True):
        return
    if action == "new_ip"      and not await config_handler.get_bool("alert_on_new_ip",       default=True):
        return
    if action == "new_user"    and not await config_handler.get_bool("alert_on_new_user",     default=True):
        return
    if action == "new_admin"   and not await config_handler.get_bool("alert_on_new_admin",    default=True):
        return
    if action == "brute_force" and not await config_handler.get_bool("alert_on_brute_force",  default=True):
        return

    # Deduplicate by (action, ip) to avoid spam during brute-force attacks
    if await _is_deduped(action, ip or "unknown"):
        return

    host      = await config_handler.get("smtp_host")         or ""
    port_str  = await config_handler.get("smtp_port")         or "587"
    user      = await config_handler.get("smtp_username")     or ""
    password  = await config_handler.get("smtp_password")     or ""
    from_addr = await config_handler.get("smtp_from_address") or ""
    to_addr   = await config_handler.get("alert_smtp_to")     or ""
    use_tls   = await config_handler.get_bool("smtp_use_tls", default=True)
    tls_mode  = "starttls" if use_tls else "none"

    if not host or not to_addr or not from_addr:
        logger.debug("Email alerts enabled but SMTP not fully configured - skipping")
        return

    try:
        port = int(port_str)
    except ValueError:
        port = 587

    subject, body = _build_email(action, username, ip, user_agent)

    from handler.email.smtp_sender import send_email
    await send_email(host, port, user, password, from_addr, to_addr, subject, body, tls_mode)
    logger.info("Security alert sent: action=%s user=%s ip=%s", action, username, ip)


def _build_email(
    action:     str,
    username:   str | None,
    ip:         str | None,
    user_agent: str | None,
) -> tuple[str, str]:
    now  = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    user = username or "unknown"
    addr = ip or "unknown"
    ua   = user_agent or "-"

    if action == "login_fail":
        subject = f"[GamesDownloader] Failed login attempt - {user} from {addr}"
        title   = "Failed Login Attempt"
        color   = "#ef4444"
        icon    = "&#9888;"  # ⚠
        desc    = f"A failed login attempt was recorded for user <strong>{user}</strong>."
        detail  = "This may indicate a wrong password or an attempt to access a non-existent account."
    elif action == "new_ip":
        subject = f"[GamesDownloader] New IP login - {user} from {addr}"
        title   = "Login from New IP Address"
        color   = "#f59e0b"
        icon    = "&#128276;"  # 🔔
        desc    = f"User <strong>{user}</strong> logged in from an IP address not seen before."
        detail  = "If this was expected, no action is needed. Otherwise, consider revoking this session in Settings &rarr; Users."
    elif action == "new_user":
        subject = f"[GamesDownloader] New user registered - {user}"
        title   = "New User Registration"
        color   = "#22c55e"
        icon    = "&#128100;"  # 👤
        desc    = f"A new user account was created: <strong>{user}</strong>."
        detail  = "If you did not expect this registration, review the new account in Settings &rarr; Users."
    elif action == "new_admin":
        subject = f"[GamesDownloader] Admin privileges granted - {user}"
        title   = "Admin Privileges Granted"
        color   = "#a78bfa"
        icon    = "&#9733;"  # ★
        desc    = f"User <strong>{user}</strong> was granted administrator privileges."
        detail  = "If this change was not authorised, revoke it immediately in Settings &rarr; Users."
    elif action == "brute_force":
        subject = f"[GamesDownloader] IP address banned - brute-force detected from {addr}"
        title   = "Brute-Force Attack Detected"
        color   = "#ef4444"
        icon    = "&#128683;"  # 🚫
        desc    = f"IP address <strong>{addr}</strong> has been temporarily banned after exceeding the failed login threshold."
        detail  = "No action is required - the IP is blocked automatically. Review the Audit Log for details."
    else:
        subject = f"[GamesDownloader] Security event: {action}"
        title   = f"Security Event: {action}"
        color   = "#6b7280"
        icon    = "&#8505;"  # ℹ
        desc    = "A security event was recorded."
        detail  = ""

    body = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>{title}</title></head>
<body style="margin:0;padding:0;background:#0f0f13;font-family:'Segoe UI',Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#0f0f13;padding:32px 16px;">
    <tr><td align="center">
      <table width="520" cellpadding="0" cellspacing="0"
        style="background:#1a1a24;border:1px solid #2a2a3a;border-radius:12px;overflow:hidden;max-width:520px;width:100%;">
        <tr>
          <td style="background:{color}1a;border-bottom:3px solid {color};padding:24px 28px;">
            <div style="font-size:24px;margin-bottom:6px;">{icon}</div>
            <div style="font-size:18px;font-weight:700;color:{color};">{title}</div>
            <div style="font-size:12px;color:#888;margin-top:4px;">GamesDownloader Security Alert</div>
          </td>
        </tr>
        <tr>
          <td style="padding:24px 28px;">
            <p style="font-size:14px;color:#c0c0d0;margin:0 0 12px 0;">{desc}</p>
            <p style="font-size:13px;color:#808090;margin:0 0 20px 0;">{detail}</p>
            <table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;border-radius:8px;overflow:hidden;">
              <tr>
                <td style="padding:8px 14px;background:#12121c;border:1px solid #2a2a3a;font-size:11px;font-weight:700;color:#555;text-transform:uppercase;letter-spacing:.5px;width:110px;">Time</td>
                <td style="padding:8px 14px;background:#12121c;border:1px solid #2a2a3a;border-left:none;font-size:13px;color:#c0c0d0;">{now}</td>
              </tr>
              <tr>
                <td style="padding:8px 14px;background:#0f0f18;border:1px solid #2a2a3a;border-top:none;font-size:11px;font-weight:700;color:#555;text-transform:uppercase;letter-spacing:.5px;">Username</td>
                <td style="padding:8px 14px;background:#0f0f18;border:1px solid #2a2a3a;border-top:none;border-left:none;font-size:13px;color:#c0c0d0;font-family:monospace;">{user}</td>
              </tr>
              <tr>
                <td style="padding:8px 14px;background:#12121c;border:1px solid #2a2a3a;border-top:none;font-size:11px;font-weight:700;color:#555;text-transform:uppercase;letter-spacing:.5px;">IP Address</td>
                <td style="padding:8px 14px;background:#12121c;border:1px solid #2a2a3a;border-top:none;border-left:none;font-size:13px;color:#c0c0d0;font-family:monospace;">{addr}</td>
              </tr>
              <tr>
                <td style="padding:8px 14px;background:#0f0f18;border:1px solid #2a2a3a;border-top:none;font-size:11px;font-weight:700;color:#555;text-transform:uppercase;letter-spacing:.5px;">Client</td>
                <td style="padding:8px 14px;background:#0f0f18;border:1px solid #2a2a3a;border-top:none;border-left:none;font-size:12px;color:#808090;">{ua}</td>
              </tr>
            </table>
          </td>
        </tr>
        <tr>
          <td style="padding:16px 28px;border-top:1px solid #2a2a3a;font-size:11px;color:#555;text-align:center;">
            Automated security notification &mdash; GamesDownloader
          </td>
        </tr>
      </table>
    </td></tr>
  </table>
</body>
</html>"""
    return subject, body
