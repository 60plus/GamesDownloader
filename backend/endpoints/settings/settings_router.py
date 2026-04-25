"""
Settings endpoints - read/write app config after setup is complete.
Requires SETTINGS_READ (GET) or SETTINGS_WRITE (POST/PUT) scope.
"""
from __future__ import annotations

import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from decorators.auth import protected_route
from handler.auth.scopes import Scope
from handler.config.config_handler import config_handler

settings_router = APIRouter(prefix="/api/settings", tags=["settings"])


# ── Pydantic models ────────────────────────────────────────────────────────────

class ScraperKeysRequest(BaseModel):
    igdb_client_id: str | None = None
    igdb_client_secret: str | None = None
    steamgriddb_api_key: str | None = None
    rawg_api_key: str | None = None
    screenscraper_username: str | None = None
    screenscraper_password: str | None = None
    screenscraper_devid: str | None = None
    screenscraper_devpassword: str | None = None
    ra_api_username: str | None = None
    ra_api_key: str | None = None


class ScraperTestRequest(BaseModel):
    scraper: str
    igdb_client_id: str | None = None
    igdb_client_secret: str | None = None
    steamgriddb_api_key: str | None = None
    rawg_api_key: str | None = None
    screenscraper_username: str | None = None
    screenscraper_password: str | None = None
    screenscraper_devid: str | None = None
    screenscraper_devpassword: str | None = None
    ra_api_username: str | None = None
    ra_api_key: str | None = None


class SmtpRequest(BaseModel):
    enabled: bool = False
    host: str | None = None
    port: int = 587
    username: str | None = None
    password: str | None = None
    from_address: str | None = None
    use_tls: bool = True
    test_to: str | None = None
    email_notify_download: bool = True
    email_notify_sync: bool = True
    email_notify_request: bool = True
    email_tpl_download_subject: str | None = None
    email_tpl_download_body: str | None = None
    email_tpl_sync_subject: str | None = None
    email_tpl_sync_body: str | None = None
    email_tpl_request_new_subject: str | None = None
    email_tpl_request_new_body: str | None = None
    email_tpl_request_pending_subject: str | None = None
    email_tpl_request_pending_body: str | None = None
    email_tpl_request_approved_subject: str | None = None
    email_tpl_request_approved_body: str | None = None
    email_tpl_request_rejected_subject: str | None = None
    email_tpl_request_rejected_body: str | None = None
    email_tpl_request_done_subject: str | None = None
    email_tpl_request_done_body: str | None = None


class WebhookRequest(BaseModel):
    enabled: bool = False
    url: str | None = None
    type: str = "generic"          # "generic" | "discord"
    notify_download: bool = True
    notify_sync: bool = True
    notify_request: bool = True
    include_cover: bool = True
    avatar_url: str | None = None
    tpl_download_title: str | None = None
    tpl_download_body: str | None = None
    tpl_sync_title: str | None = None
    tpl_sync_body: str | None = None
    tpl_request_new_title: str | None = None
    tpl_request_new_body: str | None = None
    tpl_request_pending_title: str | None = None
    tpl_request_pending_body: str | None = None
    tpl_request_approved_title: str | None = None
    tpl_request_approved_body: str | None = None
    tpl_request_rejected_title: str | None = None
    tpl_request_rejected_body: str | None = None
    tpl_request_done_title: str | None = None
    tpl_request_done_body: str | None = None


# ── Scrapers ───────────────────────────────────────────────────────────────────

@protected_route(settings_router.get, "/scrapers", scopes=[Scope.SETTINGS_READ])
async def get_scraper_keys(request: Request) -> dict:
    keys = [
        "igdb_client_id", "igdb_client_secret", "steamgriddb_api_key",
        "rawg_api_key", "screenscraper_username", "screenscraper_password",
        "screenscraper_devid", "screenscraper_devpassword",
        "ra_api_username", "ra_api_key",
    ]
    result = {}
    for k in keys:
        val = await config_handler.get(k)
        result[k] = val or ""
    return result


@protected_route(settings_router.post, "/scrapers", scopes=[Scope.SETTINGS_WRITE])
async def save_scraper_keys(request: Request, req: ScraperKeysRequest) -> dict:
    data: dict[str, tuple[str, bool]] = {}
    if req.igdb_client_id is not None:           data["igdb_client_id"]            = (req.igdb_client_id, True)
    if req.igdb_client_secret is not None:       data["igdb_client_secret"]        = (req.igdb_client_secret, True)
    if req.steamgriddb_api_key is not None:      data["steamgriddb_api_key"]       = (req.steamgriddb_api_key, True)
    if req.rawg_api_key is not None:             data["rawg_api_key"]              = (req.rawg_api_key, True)
    if req.screenscraper_username is not None:   data["screenscraper_username"]    = (req.screenscraper_username, False)
    if req.screenscraper_password is not None:   data["screenscraper_password"]    = (req.screenscraper_password, True)
    if req.screenscraper_devid is not None:      data["screenscraper_devid"]       = (req.screenscraper_devid, False)
    if req.screenscraper_devpassword is not None: data["screenscraper_devpassword"] = (req.screenscraper_devpassword, True)
    if req.ra_api_username is not None:          data["ra_api_username"]           = (req.ra_api_username, False)
    if req.ra_api_key is not None:               data["ra_api_key"]                = (req.ra_api_key, True)
    if data:
        await config_handler.set_many(data)
    return {"ok": True}


@protected_route(settings_router.post, "/scrapers/test", scopes=[Scope.SETTINGS_WRITE])
async def test_scraper(request: Request, req: ScraperTestRequest) -> dict:
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            if req.scraper == "igdb":
                if not req.igdb_client_id or not req.igdb_client_secret:
                    raise HTTPException(status_code=400, detail="Client ID and Secret required")
                r = await c.post("https://id.twitch.tv/oauth2/token", params={
                    "client_id": req.igdb_client_id, "client_secret": req.igdb_client_secret,
                    "grant_type": "client_credentials",
                })
                if r.status_code != 200 or "access_token" not in r.json():
                    raise HTTPException(status_code=400, detail="Invalid IGDB credentials")

            elif req.scraper == "steamgriddb":
                if not req.steamgriddb_api_key:
                    raise HTTPException(status_code=400, detail="API key required")
                r = await c.get("https://www.steamgriddb.com/api/v2/grids/game/1",
                                headers={"Authorization": f"Bearer {req.steamgriddb_api_key}"})
                if r.status_code == 401:
                    raise HTTPException(status_code=400, detail="Invalid SteamGridDB API key")

            elif req.scraper == "rawg":
                if not req.rawg_api_key:
                    raise HTTPException(status_code=400, detail="API key required")
                r = await c.get("https://api.rawg.io/api/genres", params={"key": req.rawg_api_key})
                if r.status_code in (401, 403):
                    raise HTTPException(status_code=400, detail="Invalid RAWG API key")

            elif req.scraper == "screenscraper":
                if not req.screenscraper_username or not req.screenscraper_password:
                    raise HTTPException(status_code=400, detail="Username and password required")
                # devid/devpassword: user-configured → env var → built-in default
                import os as _os
                from handler.metadata.screenscraper_handler import _SS_DEFAULT_DEVID, _SS_DEFAULT_DEVPW
                devid = (req.screenscraper_devid or "").strip() or _os.environ.get("SCREENSCRAPER_DEVID") or _SS_DEFAULT_DEVID
                devpw = (req.screenscraper_devpassword or "").strip() or _os.environ.get("SCREENSCRAPER_DEVPASSWORD") or _SS_DEFAULT_DEVPW
                import logging as _log
                _log.getLogger("settings.scraper_test").info(
                    "SS test: devid=%s ssid=%s", devid, req.screenscraper_username
                )
                # ssuserInfos.php is the lightest credential-check endpoint
                r = await c.get("https://api.screenscraper.fr/api2/ssuserInfos.php", params={
                    "devid": devid, "devpassword": devpw,
                    "softname": "GamesDownloader", "output": "json",
                    "ssid": req.screenscraper_username, "sspassword": req.screenscraper_password,
                })
                _log.getLogger("settings.scraper_test").info(
                    "SS test response: status=%d body=%s", r.status_code, r.text[:400]
                )
                if r.status_code == 403:
                    body = r.text[:400]
                    raise HTTPException(status_code=400, detail=f"ScreenScraper 403: {body}")
                elif r.status_code not in (200, 404):
                    raise HTTPException(status_code=400, detail=f"ScreenScraper returned HTTP {r.status_code}: {r.text[:200]}")

            elif req.scraper == "ra":
                if not req.ra_api_key or not req.ra_api_username:
                    raise HTTPException(status_code=400, detail="RA Username and API Key are both required")
                params: dict = {"y": req.ra_api_key, "z": req.ra_api_username}
                r = await c.get("https://retroachievements.org/API/API_GetTopTenUsers.php", params=params)
                if r.status_code == 401 or (r.status_code == 200 and r.json() is None):
                    raise HTTPException(status_code=400, detail="Invalid RetroAchievements credentials")

            else:
                raise HTTPException(status_code=400, detail=f"Unknown scraper: {req.scraper}")

        return {"ok": True}
    except HTTPException:
        raise
    except httpx.ConnectError as e:
        raise HTTPException(status_code=400, detail=f"Network error: could not connect to the service. Check that the server has internet access. ({e})")
    except httpx.TimeoutException:
        raise HTTPException(status_code=400, detail="Connection timed out. The service may be unreachable from this server.")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── SMTP ───────────────────────────────────────────────────────────────────────

_TEST_EMAIL_HTML = """\
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


@protected_route(settings_router.get, "/smtp", scopes=[Scope.SETTINGS_READ])
async def get_smtp(request: Request) -> dict:
    return {
        "enabled":      await config_handler.get_bool("smtp_enabled"),
        "host":         await config_handler.get("smtp_host") or "",
        "port":         int(await config_handler.get("smtp_port") or "587"),
        "username":     await config_handler.get("smtp_username") or "",
        "password":     await config_handler.get("smtp_password") or "",
        "from_address": await config_handler.get("smtp_from_address") or "",
        "use_tls":      await config_handler.get_bool("smtp_use_tls", default=True),
        "email_notify_download": await config_handler.get_bool("email_notify_download", default=True),
        "email_notify_sync":     await config_handler.get_bool("email_notify_sync", default=True),
        "email_notify_request":  await config_handler.get_bool("email_notify_request", default=True),
        "email_tpl_download_subject":       await config_handler.get("email_tpl_download_subject") or "",
        "email_tpl_download_body":          await config_handler.get("email_tpl_download_body") or "",
        "email_tpl_sync_subject":           await config_handler.get("email_tpl_sync_subject") or "",
        "email_tpl_sync_body":              await config_handler.get("email_tpl_sync_body") or "",
        "email_tpl_request_new_subject":    await config_handler.get("email_tpl_request_new_subject") or "",
        "email_tpl_request_new_body":       await config_handler.get("email_tpl_request_new_body") or "",
        "email_tpl_request_pending_subject":  await config_handler.get("email_tpl_request_pending_subject") or "",
        "email_tpl_request_pending_body":     await config_handler.get("email_tpl_request_pending_body") or "",
        "email_tpl_request_approved_subject": await config_handler.get("email_tpl_request_approved_subject") or "",
        "email_tpl_request_approved_body":    await config_handler.get("email_tpl_request_approved_body") or "",
        "email_tpl_request_rejected_subject": await config_handler.get("email_tpl_request_rejected_subject") or "",
        "email_tpl_request_rejected_body":    await config_handler.get("email_tpl_request_rejected_body") or "",
        "email_tpl_request_done_subject":     await config_handler.get("email_tpl_request_done_subject") or "",
        "email_tpl_request_done_body":        await config_handler.get("email_tpl_request_done_body") or "",
    }


@protected_route(settings_router.post, "/smtp", scopes=[Scope.SETTINGS_WRITE])
async def save_smtp(request: Request, req: SmtpRequest) -> dict:
    await config_handler.set_many({
        "smtp_enabled":      (str(req.enabled).lower(), False),
        "smtp_host":         (req.host or "", False),
        "smtp_port":         (str(req.port), False),
        "smtp_username":     (req.username or "", False),
        "smtp_password":     (req.password or "", True),
        "smtp_from_address": (req.from_address or "", False),
        "smtp_use_tls":      (str(req.use_tls).lower(), False),
        "email_notify_download": (str(req.email_notify_download).lower(), False),
        "email_notify_sync":     (str(req.email_notify_sync).lower(), False),
        "email_notify_request":  (str(req.email_notify_request).lower(), False),
        "email_tpl_download_subject":       (req.email_tpl_download_subject or "", False),
        "email_tpl_download_body":          (req.email_tpl_download_body or "", False),
        "email_tpl_sync_subject":           (req.email_tpl_sync_subject or "", False),
        "email_tpl_sync_body":              (req.email_tpl_sync_body or "", False),
        "email_tpl_request_new_subject":    (req.email_tpl_request_new_subject or "", False),
        "email_tpl_request_new_body":       (req.email_tpl_request_new_body or "", False),
        "email_tpl_request_pending_subject":  (req.email_tpl_request_pending_subject or "", False),
        "email_tpl_request_pending_body":     (req.email_tpl_request_pending_body or "", False),
        "email_tpl_request_approved_subject": (req.email_tpl_request_approved_subject or "", False),
        "email_tpl_request_approved_body":    (req.email_tpl_request_approved_body or "", False),
        "email_tpl_request_rejected_subject": (req.email_tpl_request_rejected_subject or "", False),
        "email_tpl_request_rejected_body":    (req.email_tpl_request_rejected_body or "", False),
        "email_tpl_request_done_subject":     (req.email_tpl_request_done_subject or "", False),
        "email_tpl_request_done_body":        (req.email_tpl_request_done_body or "", False),
    })
    return {"ok": True}


@protected_route(settings_router.post, "/smtp/test", scopes=[Scope.SETTINGS_WRITE])
async def test_smtp(request: Request, req: SmtpRequest) -> dict:
    try:
        from_addr = req.from_address or req.username or ""
        to_addr   = req.test_to or req.from_address or req.username or ""
        msg = MIMEMultipart("alternative")
        msg["Subject"] = "GamesDownloader - Test Email"
        msg["From"]    = from_addr
        msg["To"]      = to_addr
        msg.attach(MIMEText(
            "GamesDownloader - Test Email\n\n"
            "Your GamesDownloader instance sent this test email successfully.\n"
            "Email notifications are configured and working correctly.",
            "plain",
        ))
        msg.attach(MIMEText(_TEST_EMAIL_HTML, "html"))
        host = req.host or ''
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

        import asyncio
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, _send_blocking)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ── Webhooks ───────────────────────────────────────────────────────────────────

@protected_route(settings_router.get, "/webhooks", scopes=[Scope.SETTINGS_READ])
async def get_webhooks(request: Request) -> dict:
    return {
        "enabled":         await config_handler.get_bool("webhook_enabled"),
        "url":             await config_handler.get("webhook_url") or "",
        "type":            await config_handler.get("webhook_type") or "generic",
        "notify_download": await config_handler.get_bool("webhook_notify_download", default=True),
        "notify_sync":     await config_handler.get_bool("webhook_notify_sync", default=True),
        "notify_request":  await config_handler.get_bool("webhook_notify_request", default=True),
        "include_cover":   await config_handler.get_bool("webhook_include_cover", default=True),
        "avatar_url":      await config_handler.get("webhook_avatar_url") or "",
        "tpl_download_title":       await config_handler.get("webhook_tpl_download_title") or "",
        "tpl_download_body":        await config_handler.get("webhook_tpl_download_body") or "",
        "tpl_sync_title":           await config_handler.get("webhook_tpl_sync_title") or "",
        "tpl_sync_body":            await config_handler.get("webhook_tpl_sync_body") or "",
        "tpl_request_new_title":    await config_handler.get("webhook_tpl_request_new_title") or "",
        "tpl_request_new_body":     await config_handler.get("webhook_tpl_request_new_body") or "",
        "tpl_request_pending_title":  await config_handler.get("webhook_tpl_request_pending_title") or "",
        "tpl_request_pending_body":   await config_handler.get("webhook_tpl_request_pending_body") or "",
        "tpl_request_approved_title": await config_handler.get("webhook_tpl_request_approved_title") or "",
        "tpl_request_approved_body":  await config_handler.get("webhook_tpl_request_approved_body") or "",
        "tpl_request_rejected_title": await config_handler.get("webhook_tpl_request_rejected_title") or "",
        "tpl_request_rejected_body":  await config_handler.get("webhook_tpl_request_rejected_body") or "",
        "tpl_request_done_title":     await config_handler.get("webhook_tpl_request_done_title") or "",
        "tpl_request_done_body":      await config_handler.get("webhook_tpl_request_done_body") or "",
    }


@protected_route(settings_router.post, "/webhooks", scopes=[Scope.SETTINGS_WRITE])
async def save_webhooks(request: Request, req: WebhookRequest) -> dict:
    await config_handler.set_many({
        "webhook_enabled":         (str(req.enabled).lower(), False),
        "webhook_url":             (req.url or "", False),
        "webhook_type":            (req.type, False),
        "webhook_notify_download": (str(req.notify_download).lower(), False),
        "webhook_notify_sync":     (str(req.notify_sync).lower(), False),
        "webhook_notify_request":  (str(req.notify_request).lower(), False),
        "webhook_include_cover":   (str(req.include_cover).lower(), False),
        "webhook_avatar_url":      (req.avatar_url or "", False),
        "webhook_tpl_download_title":       (req.tpl_download_title or "", False),
        "webhook_tpl_download_body":        (req.tpl_download_body or "", False),
        "webhook_tpl_sync_title":           (req.tpl_sync_title or "", False),
        "webhook_tpl_sync_body":            (req.tpl_sync_body or "", False),
        "webhook_tpl_request_new_title":    (req.tpl_request_new_title or "", False),
        "webhook_tpl_request_new_body":     (req.tpl_request_new_body or "", False),
        "webhook_tpl_request_pending_title":  (req.tpl_request_pending_title or "", False),
        "webhook_tpl_request_pending_body":   (req.tpl_request_pending_body or "", False),
        "webhook_tpl_request_approved_title": (req.tpl_request_approved_title or "", False),
        "webhook_tpl_request_approved_body":  (req.tpl_request_approved_body or "", False),
        "webhook_tpl_request_rejected_title": (req.tpl_request_rejected_title or "", False),
        "webhook_tpl_request_rejected_body":  (req.tpl_request_rejected_body or "", False),
        "webhook_tpl_request_done_title":     (req.tpl_request_done_title or "", False),
        "webhook_tpl_request_done_body":      (req.tpl_request_done_body or "", False),
    })
    return {"ok": True}


@protected_route(settings_router.post, "/webhooks/test", scopes=[Scope.SETTINGS_WRITE])
async def test_webhook(request: Request, req: WebhookRequest) -> dict:
    if not req.url:
        raise HTTPException(status_code=400, detail="Webhook URL is required")
    try:
        from handler.notifications.webhook_handler import send_discord, send_generic
        if req.type == "discord":
            await send_discord(
                req.url,
                title="GamesDownloader - Test Webhook",
                description="Your webhook is configured and working correctly.",
                fields=[{"name": "Status", "value": "✅ Connected", "inline": True}],
            )
        else:
            await send_generic(
                req.url,
                "Test Webhook",
                "GamesDownloader webhook is working correctly.",
            )
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ─── Security - Brute-force config ────────────────────────────────────────────

class BruteForceConfig(BaseModel):
    enabled:        bool = True
    max_attempts:   int  = 5
    window_seconds: int  = 300
    ban_seconds:    int  = 900
    whitelist:      str  = ""   # comma-separated IPs


@protected_route(settings_router.get, "/security/brute-force", scopes=[Scope.SETTINGS_READ])
async def get_brute_force_config(request: Request) -> BruteForceConfig:
    return BruteForceConfig(
        enabled        = await config_handler.get_bool("bf_enabled", default=True),
        max_attempts   = int(await config_handler.get("bf_max_attempts")   or 5),
        window_seconds = int(await config_handler.get("bf_window_seconds") or 300),
        ban_seconds    = int(await config_handler.get("bf_ban_seconds")    or 900),
        whitelist      = await config_handler.get("bf_whitelist") or "",
    )


@protected_route(settings_router.post, "/security/brute-force", scopes=[Scope.SETTINGS_WRITE])
async def save_brute_force_config(request: Request, cfg: BruteForceConfig) -> dict:
    await config_handler.set("bf_enabled",        str(cfg.enabled).lower())
    await config_handler.set("bf_max_attempts",   str(cfg.max_attempts))
    await config_handler.set("bf_window_seconds", str(cfg.window_seconds))
    await config_handler.set("bf_ban_seconds",    str(cfg.ban_seconds))
    await config_handler.set("bf_whitelist",      cfg.whitelist or "")
    return {"ok": True}


@protected_route(settings_router.get, "/security/banned-ips", scopes=[Scope.SETTINGS_READ])
async def get_banned_ips(request: Request) -> list:
    from handler.auth.brute_force import get_banned_ips as _get
    return await _get()


@protected_route(settings_router.delete, "/security/banned-ips/{ip}", scopes=[Scope.SETTINGS_WRITE])
async def unban_ip(request: Request, ip: str) -> dict:
    from handler.auth import brute_force
    from handler.auth.audit import log_event
    ok = await brute_force.unban_ip(ip)
    if ok:
        await log_event(request, "unban_ip", details={"ip": ip})
    return {"ok": ok}


# ─── Security - Audit Log ─────────────────────────────────────────────────────

@protected_route(settings_router.get, "/security/audit-log", scopes=[Scope.SETTINGS_READ])
async def get_audit_log(
    request: Request,
    limit: int = 100,
    offset: int = 0,
    filter: str = "",
) -> dict:
    from handler.database.audit_handler import audit_handler
    items, total = await audit_handler.get_recent(
        limit=limit, offset=offset,
        action_filter=filter or None,
    )
    return {
        "items": [
            {
                "id":         i.id,
                "action":     i.action,
                "username":   i.username,
                "ip_address": i.ip_address,
                "details":    i.details,
                "status":     i.status,
                "created_at": i.created_at.isoformat() if i.created_at else None,
            }
            for i in items
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@protected_route(settings_router.delete, "/security/audit-log", scopes=[Scope.SETTINGS_WRITE])
async def clear_audit_log(request: Request) -> dict:
    from handler.database.audit_handler import audit_handler
    from handler.auth.audit import log_event
    await log_event(request, "audit_log_cleared", username=getattr(request.state, "user", None) and getattr(request.state.user, "username", None))
    await audit_handler.clear_all()
    return {"ok": True}
