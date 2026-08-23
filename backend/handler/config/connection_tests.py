"""Shared "does this credential work" checks for Settings and for first-run setup.

Both places offer the same two buttons - test a scraper key, send a test email -
and both had their own copy of the code behind them. The copies drifted: the
setup one still pointed ScreenScraper at a different host and signed the request
with a placeholder developer account, and asked RetroAchievements for a top-ten
list without the username that API requires. Whichever screen a person happened
to use decided whether the answer was trustworthy, which is the opposite of what
a test button is for.

The routers keep their own request models and their own guards; only the work
lives here. Fields are read with `getattr` because the setup form is a narrower
version of the settings one and does not carry the developer-token overrides.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any

import httpx
from fastapi import HTTPException

logger = logging.getLogger(__name__)

# ScreenScraper reflects the request back inside some of its replies, password
# and all, so nothing from a response body reaches a log or a user without
# going through this first.
_POSWIADCZENIE = re.compile(
    r"(?i)\b((?:ss|dev)?pass(?:word)?|ssid|devid)\s*[=:]\s*[^&\s\"',}]+")


def _bez_poswiadczen(tekst: str) -> str:
    return _POSWIADCZENIE.sub(lambda m: f"{m.group(1)}=***", tekst)


TEST_EMAIL_HTML = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<style>
  body{margin:0;padding:0;background:#0d0d1a;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif}
  .wrap{max-width:520px;margin:0 auto;padding:40px 16px}
  .card{background:#1a1a2e;border:1px solid rgba(255,255,255,.1);border-radius:14px;overflow:hidden}
  .header{background:linear-gradient(135deg,#16213e 0%,#1a1040 100%);padding:32px 36px;text-align:center;border-bottom:1px solid rgba(167,139,250,.2)}
  .logo{font-size:22px;font-weight:800;color:#a78bfa;letter-spacing:-.5px}
  .logo-sub{font-size:10px;color:rgba(167,139,250,.5);text-transform:uppercase;letter-spacing:2px;margin-top:5px}
  .body{padding:32px 36px}
  .icon{width:56px;height:56px;border-radius:50%;background:rgba(34,197,94,.12);border:2px solid rgba(34,197,94,.3);margin:0 auto 20px;display:flex;align-items:center;justify-content:center;text-align:center;font-size:24px;line-height:56px}
  .title{font-size:20px;font-weight:700;color:#f1f1f1;margin:0 0 10px;text-align:center}
  .text{font-size:14px;color:#8888a8;line-height:1.7;margin:0 0 24px;text-align:center}
  .badge{display:block;width:fit-content;margin:0 auto;background:rgba(34,197,94,.12);border:1px solid rgba(34,197,94,.3);color:#86efac;padding:10px 24px;border-radius:24px;font-size:13px;font-weight:600}
  .footer{padding:16px 36px 24px;text-align:center;font-size:11px;color:rgba(255,255,255,.2)}
</style>
</head>
<body>
<div class="wrap">
  <div class="card">
    <div class="header">
      <div class="logo">GamesDownloader</div>
      <div class="logo-sub">Email Notification System</div>
    </div>
    <div class="body">
      <div class="icon">&#10003;</div>
      <div class="title">Test Email</div>
      <p class="text">
        Your GamesDownloader instance sent this test email successfully.<br>
        Email notifications are configured and working correctly.
      </p>
      <span class="badge">&#10003;&nbsp; Email sent successfully</span>
    </div>
    <div class="footer">GamesDownloader &mdash; Self-hosted game library</div>
  </div>
</div>
</body>
</html>
"""


async def run_scraper_test(req: Any) -> dict:
    """Check one scraper's credentials and say whether they work."""
    scraper = getattr(req, "scraper", "")
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            if scraper == "igdb":
                if not req.igdb_client_id or not req.igdb_client_secret:
                    raise HTTPException(status_code=400, detail="Client ID and Secret required")
                r = await c.post("https://id.twitch.tv/oauth2/token", params={
                    "client_id": req.igdb_client_id, "client_secret": req.igdb_client_secret,
                    "grant_type": "client_credentials",
                })
                if r.status_code != 200 or "access_token" not in r.json():
                    raise HTTPException(status_code=400, detail="Invalid IGDB credentials")

            elif scraper == "steamgriddb":
                if not req.steamgriddb_api_key:
                    raise HTTPException(status_code=400, detail="API key required")
                r = await c.get("https://www.steamgriddb.com/api/v2/grids/game/1",
                                headers={"Authorization": f"Bearer {req.steamgriddb_api_key}"})
                if r.status_code == 401:
                    raise HTTPException(status_code=400, detail="Invalid SteamGridDB API key")

            elif scraper == "rawg":
                if not req.rawg_api_key:
                    raise HTTPException(status_code=400, detail="API key required")
                r = await c.get("https://api.rawg.io/api/genres", params={"key": req.rawg_api_key})
                if r.status_code in (401, 403):
                    raise HTTPException(status_code=400, detail="Invalid RAWG API key")

            elif scraper == "screenscraper":
                if not req.screenscraper_username or not req.screenscraper_password:
                    raise HTTPException(status_code=400, detail="Username and password required")
                # devid/devpassword: user-configured → env var → built-in default
                from handler.metadata.screenscraper_handler import (
                    _SS_DEFAULT_DEVID, _SS_DEFAULT_DEVPW)
                devid = ((getattr(req, "screenscraper_devid", None) or "").strip()
                         or os.environ.get("SCREENSCRAPER_DEVID") or _SS_DEFAULT_DEVID)
                devpw = ((getattr(req, "screenscraper_devpassword", None) or "").strip()
                         or os.environ.get("SCREENSCRAPER_DEVPASSWORD") or _SS_DEFAULT_DEVPW)
                # ssuserInfos.php is the lightest credential-check endpoint
                r = await c.get("https://api.screenscraper.fr/api2/ssuserInfos.php", params={
                    "devid": devid, "devpassword": devpw,
                    "softname": "GamesDownloader", "output": "json",
                    "ssid": req.screenscraper_username, "sspassword": req.screenscraper_password,
                })
                logger.info("ScreenScraper credential check returned HTTP %d", r.status_code)
                if r.status_code == 403:
                    powod = _bez_poswiadczen(r.text.strip())[:200]
                    raise HTTPException(status_code=400,
                                        detail=f"ScreenScraper refused the credentials: {powod}")
                if r.status_code not in (200, 404):
                    raise HTTPException(
                        status_code=400,
                        detail=f"ScreenScraper returned HTTP {r.status_code}")

            elif scraper == "ra":
                # The API answers on `y` alone, but for somebody else's account -
                # so a wrong username would still look like a working key.
                if not req.ra_api_key or not getattr(req, "ra_api_username", None):
                    raise HTTPException(status_code=400,
                                        detail="RA Username and API Key are both required")
                r = await c.get("https://retroachievements.org/API/API_GetTopTenUsers.php",
                                params={"y": req.ra_api_key, "z": req.ra_api_username})
                if r.status_code == 401 or (r.status_code == 200 and r.json() is None):
                    raise HTTPException(status_code=400,
                                        detail="Invalid RetroAchievements credentials")

            else:
                raise HTTPException(status_code=400, detail=f"Unknown scraper: {scraper}")

        return {"ok": True}
    except HTTPException:
        raise
    except httpx.ConnectError as e:
        raise HTTPException(
            status_code=400,
            detail=("Network error: could not connect to the service. "
                    f"Check that the server has internet access. ({e})"))
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=400,
            detail="Connection timed out. The service may be unreachable from this server.")
    except Exception as e:
        raise HTTPException(status_code=400, detail=_bez_poswiadczen(str(e)))


async def run_smtp_test(req: Any) -> dict:
    """Send one test email with the settings as typed, without saving them."""
    try:
        from_addr = req.from_address or req.username or ""
        to_addr = req.test_to or req.from_address or req.username or ""
        msg = MIMEMultipart("alternative")
        msg["Subject"] = "GamesDownloader - Test Email"
        msg["From"] = from_addr
        msg["To"] = to_addr
        msg.attach(MIMEText(
            "GamesDownloader - Test Email\n\n"
            "Your GamesDownloader instance sent this test email successfully.\n"
            "Email notifications are configured and working correctly.",
            "plain",
        ))
        msg.attach(MIMEText(TEST_EMAIL_HTML, "html"))
        host = req.host or ""
        port = req.port
        use_tls = req.use_tls
        username = req.username
        password = req.password

        def _send_blocking() -> None:
            ctx = ssl.create_default_context() if use_tls else None
            with smtplib.SMTP(host, port, timeout=10) as server:
                if use_tls:
                    server.starttls(context=ctx)
                if username and password:
                    server.login(username, password)
                server.send_message(msg)

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, _send_blocking)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=400, detail=_bez_poswiadczen(str(e)))
