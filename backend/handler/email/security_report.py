"""Security report - gather stats and send a periodic summary email."""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)


# ── Data gathering ────────────────────────────────────────────────────────────

async def gather_report_data(since: datetime) -> dict:
    """Collect security and activity stats since `since` (UTC)."""
    from sqlalchemy import select, func
    from handler.database.session import async_session_factory
    from models.audit_log import AuditLog
    from models.download_stat import DownloadStat
    from models.scan_result import ScanResult
    from models.user import User

    now = datetime.now(timezone.utc)

    async with async_session_factory() as session:

        # ── Audit log stats ───────────────────────────────────────────────────
        def _audit_count(action: str):
            return (
                select(func.count())
                .select_from(AuditLog)
                .where(AuditLog.action == action, AuditLog.created_at >= since)
            )

        logins_ok      = (await session.execute(_audit_count("login_ok"))).scalar_one()
        logins_failed  = (await session.execute(_audit_count("login_fail"))).scalar_one()
        logins_blocked = (await session.execute(_audit_count("login_blocked"))).scalar_one()

        # Unique users who logged in successfully
        unique_users_r = await session.execute(
            select(func.count(func.distinct(AuditLog.username)))
            .select_from(AuditLog)
            .where(AuditLog.action == "login_ok", AuditLog.created_at >= since)
        )
        unique_users = unique_users_r.scalar_one()

        # Top 5 active users by successful logins
        top_users_r = await session.execute(
            select(AuditLog.username, func.count().label("cnt"))
            .where(AuditLog.action == "login_ok", AuditLog.created_at >= since,
                   AuditLog.username.isnot(None))
            .group_by(AuditLog.username)
            .order_by(func.count().desc())
            .limit(5)
        )
        top_users = [{"username": r.username, "count": r.cnt} for r in top_users_r]

        # ── New user registrations ────────────────────────────────────────────
        new_users_r = await session.execute(
            select(func.count()).select_from(User).where(User.created_at >= since)
        )
        new_users = new_users_r.scalar_one()

        # ── Download stats ────────────────────────────────────────────────────
        dl_count_r = await session.execute(
            select(func.count()).select_from(DownloadStat).where(DownloadStat.created_at >= since)
        )
        dl_count = dl_count_r.scalar_one()

        dl_bytes_r = await session.execute(
            select(func.coalesce(func.sum(DownloadStat.bytes_transferred), 0))
            .select_from(DownloadStat)
            .where(DownloadStat.created_at >= since)
        )
        dl_bytes = dl_bytes_r.scalar_one() or 0

        # ── ClamAV scans ──────────────────────────────────────────────────────
        scans_r = await session.execute(
            select(
                func.count().label("total"),
                func.coalesce(func.sum(ScanResult.infected_count), 0).label("threats"),
            )
            .select_from(ScanResult)
            .where(ScanResult.created_at >= since, ScanResult.status == "complete")
        )
        scan_row  = scans_r.one()
        scans_total  = scan_row.total
        threats_found = int(scan_row.threats)

    return {
        "period_start":    since.strftime("%Y-%m-%d %H:%M UTC"),
        "period_end":      now.strftime("%Y-%m-%d %H:%M UTC"),
        "logins_ok":       logins_ok,
        "logins_failed":   logins_failed,
        "logins_blocked":  logins_blocked,
        "unique_users":    unique_users,
        "new_users":       new_users,
        "downloads_count": dl_count,
        "downloads_bytes": dl_bytes,
        "scans_total":     scans_total,
        "threats_found":   threats_found,
        "top_users":       top_users,
    }


def _fmt_bytes(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


# ── Email builder ─────────────────────────────────────────────────────────────

def build_report_email(data: dict, frequency: str) -> tuple[str, str]:
    label    = "Weekly" if frequency == "weekly" else "Monthly"
    period   = f"{data['period_start']} - {data['period_end']}"
    subject  = f"[GamesDownloader] {label} Security Report"

    threat_color = "#ef4444" if data["threats_found"] > 0 else "#22c55e"
    threat_label = str(data["threats_found"]) if data["threats_found"] > 0 else "None ✓"

    def stat_row(label: str, value: str, highlight: str = "#c0c0d0") -> str:
        return f"""
        <tr>
          <td style="padding:9px 16px;border:1px solid #2a2a3a;font-size:12px;font-weight:700;
                     color:#555;text-transform:uppercase;letter-spacing:.4px;width:180px;
                     background:#12121c;">{label}</td>
          <td style="padding:9px 16px;border:1px solid #2a2a3a;border-left:none;font-size:14px;
                     color:{highlight};font-family:monospace;background:#0f0f18;">{value}</td>
        </tr>"""

    top_rows = "".join(
        f'<tr><td style="padding:6px 12px;font-size:13px;color:#c0c0d0;'
        f'border:1px solid #2a2a3a;background:#12121c;">{u["username"]}</td>'
        f'<td style="padding:6px 12px;font-size:13px;color:#a78bfa;font-family:monospace;'
        f'border:1px solid #2a2a3a;border-left:none;background:#0f0f18;">{u["count"]}</td></tr>'
        for u in data["top_users"]
    ) if data["top_users"] else (
        '<tr><td colspan="2" style="padding:8px 12px;font-size:12px;color:#555;'
        'border:1px solid #2a2a3a;background:#12121c;">No logins in this period</td></tr>'
    )

    body = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>{label} Security Report</title></head>
<body style="margin:0;padding:0;background:#0f0f13;font-family:'Segoe UI',Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#0f0f13;padding:32px 16px;">
    <tr><td align="center">
      <table width="580" cellpadding="0" cellspacing="0"
        style="background:#1a1a24;border:1px solid #2a2a3a;border-radius:12px;
               overflow:hidden;max-width:580px;width:100%;">

        <!-- Header -->
        <tr>
          <td style="background:#a78bfa1a;border-bottom:3px solid #a78bfa;padding:24px 28px;">
            <div style="font-size:24px;margin-bottom:6px;">&#128203;</div>
            <div style="font-size:18px;font-weight:700;color:#a78bfa;">{label} Security Report</div>
            <div style="font-size:12px;color:#666;margin-top:4px;">{period}</div>
          </td>
        </tr>

        <!-- Login stats -->
        <tr><td style="padding:24px 28px 0;">
          <div style="font-size:11px;font-weight:700;color:#555;text-transform:uppercase;
                      letter-spacing:.5px;margin-bottom:10px;">Login Activity</div>
          <table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;border-radius:8px;overflow:hidden;">
            {stat_row("Successful logins",  str(data['logins_ok']),      "#22c55e")}
            {stat_row("Failed logins",       str(data['logins_failed']),  "#f59e0b" if data['logins_failed'] > 0 else "#c0c0d0")}
            {stat_row("Blocked attempts",    str(data['logins_blocked']), "#ef4444" if data['logins_blocked'] > 0 else "#c0c0d0")}
            {stat_row("Unique active users", str(data['unique_users']))}
            {stat_row("New registrations",   str(data['new_users']),      "#22c55e" if data['new_users'] > 0 else "#c0c0d0")}
          </table>
        </td></tr>

        <!-- Downloads -->
        <tr><td style="padding:20px 28px 0;">
          <div style="font-size:11px;font-weight:700;color:#555;text-transform:uppercase;
                      letter-spacing:.5px;margin-bottom:10px;">Downloads</div>
          <table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;border-radius:8px;overflow:hidden;">
            {stat_row("Files downloaded", str(data['downloads_count']))}
            {stat_row("Data transferred", _fmt_bytes(data['downloads_bytes']))}
          </table>
        </td></tr>

        <!-- Security scans -->
        <tr><td style="padding:20px 28px 0;">
          <div style="font-size:11px;font-weight:700;color:#555;text-transform:uppercase;
                      letter-spacing:.5px;margin-bottom:10px;">Security Scans</div>
          <table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;border-radius:8px;overflow:hidden;">
            {stat_row("Scans completed", str(data['scans_total']))}
            {stat_row("Threats detected", threat_label, threat_color)}
          </table>
        </td></tr>

        <!-- Top users -->
        <tr><td style="padding:20px 28px 0;">
          <div style="font-size:11px;font-weight:700;color:#555;text-transform:uppercase;
                      letter-spacing:.5px;margin-bottom:10px;">Most Active Users</div>
          <table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;border-radius:8px;overflow:hidden;">
            <tr>
              <th style="padding:6px 12px;font-size:11px;font-weight:700;color:#777;text-align:left;
                         background:#1a1a30;border:1px solid #2a2a3a;">Username</th>
              <th style="padding:6px 12px;font-size:11px;font-weight:700;color:#777;text-align:left;
                         background:#1a1a30;border:1px solid #2a2a3a;border-left:none;">Logins</th>
            </tr>
            {top_rows}
          </table>
        </td></tr>

        <!-- Footer -->
        <tr>
          <td style="padding:20px 28px;border-top:1px solid #2a2a3a;margin-top:24px;
                     font-size:11px;color:#444;text-align:center;">
            Automated {label.lower()} report &mdash; GamesDownloader
          </td>
        </tr>

      </table>
    </td></tr>
  </table>
</body>
</html>"""
    return subject, body


# ── Scheduled send ────────────────────────────────────────────────────────────

async def check_and_send() -> bool:
    """Send report if enabled and due. Returns True if sent."""
    from handler.config.config_handler import config_handler

    if not await config_handler.get_bool("report_enabled", default=False):
        return False

    frequency   = await config_handler.get("report_frequency") or "weekly"
    last_sent_s = await config_handler.get("report_last_sent") or ""

    interval = timedelta(days=7 if frequency == "weekly" else 30)
    now      = datetime.now(timezone.utc)

    if last_sent_s:
        try:
            last_sent = datetime.fromisoformat(last_sent_s.replace("Z", "+00:00"))
            if last_sent.tzinfo is None:
                last_sent = last_sent.replace(tzinfo=timezone.utc)
            if now - last_sent < interval:
                return False
        except Exception:
            pass

    since = now - interval
    try:
        data = await gather_report_data(since)
        await _send(data, frequency)
        await config_handler.set("report_last_sent", now.isoformat())
        logger.info("Security report sent (%s)", frequency)
        return True
    except Exception as exc:
        logger.warning("Security report send failed: %s", exc)
        return False


async def send_now(frequency: str = "weekly") -> None:
    """Send immediately regardless of schedule."""
    from handler.config.config_handler import config_handler
    from datetime import timezone

    interval = timedelta(days=7 if frequency == "weekly" else 30)
    since    = datetime.now(timezone.utc) - interval
    data     = await gather_report_data(since)
    await _send(data, frequency)
    await config_handler.set("report_last_sent", datetime.now(timezone.utc).isoformat())


async def _send(data: dict, frequency: str) -> None:
    from handler.config.config_handler import config_handler
    from handler.email.smtp_sender import send_email

    host      = await config_handler.get("smtp_host")         or ""
    port_str  = await config_handler.get("smtp_port")         or "587"
    user      = await config_handler.get("smtp_username")     or ""
    password  = await config_handler.get("smtp_password")     or ""
    from_addr = await config_handler.get("smtp_from_address") or ""
    to_addr   = await config_handler.get("alert_smtp_to")     or ""
    use_tls   = await config_handler.get_bool("smtp_use_tls", default=True)

    if not host or not to_addr or not from_addr:
        raise RuntimeError("SMTP not fully configured")

    try:
        port = int(port_str)
    except ValueError:
        port = 587

    subject, body = build_report_email(data, frequency)
    tls_mode = "starttls" if use_tls else "none"
    await send_email(host, port, user, password, from_addr, to_addr, subject, body, tls_mode)


# ── Background loop ───────────────────────────────────────────────────────────

async def report_loop() -> None:
    """Background task - checks every hour whether a report is due."""
    import asyncio
    await asyncio.sleep(3600)
    while True:
        try:
            await check_and_send()
        except Exception as exc:
            logger.warning("Security report loop error: %s", exc)
        await asyncio.sleep(3600)
