"""
Settings endpoints - read/write app config after setup is complete.
Requires SETTINGS_READ (GET) or SETTINGS_WRITE (POST/PUT) scope.
"""
from __future__ import annotations


from handler.config.connection_tests import run_scraper_test, run_smtp_test
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
    metadata_parallel_media: bool | None = None


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
    notify_to: str | None = None
    email_notify_download: bool = True
    email_notify_sync: bool = True
    email_notify_request: bool = True
    # Recently-added email delivery: off | immediate | daily | weekly. This mode
    # is the whole of the "recently added" email switch - there is deliberately
    # no subject/body pair beside it, because that mail is a rendered card
    # (cover, stars, genre, link) built in handler.notifications.digest, not a
    # template. A pair used to sit here, and in the settings screen, and was
    # read by nothing at all.
    recently_added_mode: str = "off"
    recently_added_time: str = "09:00"     # HH:MM, server local time (daily/weekly)
    recently_added_weekday: int = 0        # 0=Mon .. 6=Sun (weekly)
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
    notify_added: bool = True
    include_cover: bool = True
    avatar_url: str | None = None
    server_name: str | None = None
    tpl_added_title: str | None = None
    tpl_added_body: str | None = None
    tpl_added_content: str | None = None
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
    # A behaviour toggle rather than a credential: whether scraped screenshots
    # are fetched in parallel (bounded) or strictly one at a time.
    result["metadata_parallel_media"] = await config_handler.get_bool("metadata_parallel_media", default=True)
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
    if req.metadata_parallel_media is not None:  data["metadata_parallel_media"]   = ("true" if req.metadata_parallel_media else "false", False)
    if data:
        await config_handler.set_many(data)
    # A Twitch token is cached for its full hour, so a corrected IGDB key would
    # otherwise sit unused until the old one expired.
    if req.igdb_client_id is not None or req.igdb_client_secret is not None:
        from handler.metadata.igdb_auth import forget_token
        forget_token()
    return {"ok": True}


@protected_route(settings_router.post, "/scrapers/test", scopes=[Scope.SETTINGS_WRITE])
async def test_scraper(request: Request, req: ScraperTestRequest) -> dict:
    return await run_scraper_test(req)


# ── SMTP ───────────────────────────────────────────────────────────────────────



def _valid_ra_mode(mode: str | None) -> str:
    m = (mode or "off").strip().lower()
    return m if m in ("off", "immediate", "daily", "weekly") else "off"


def _valid_hhmm(s: str | None) -> str:
    try:
        hh, mm = (s or "09:00").split(":", 1)
        return f"{max(0, min(23, int(hh))):02d}:{max(0, min(59, int(mm))):02d}"
    except (ValueError, AttributeError):
        return "09:00"


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
        "notify_to":    await config_handler.get("smtp_notify_to") or "",
        "email_notify_download": await config_handler.get_bool("email_notify_download", default=True),
        "email_notify_sync":     await config_handler.get_bool("email_notify_sync", default=True),
        "email_notify_request":  await config_handler.get_bool("email_notify_request", default=True),
        "recently_added_mode":    await config_handler.get("smtp_recently_added_mode") or "off",
        "recently_added_time":    await config_handler.get("smtp_recently_added_time") or "09:00",
        "recently_added_weekday": int(await config_handler.get("smtp_recently_added_weekday") or "0"),
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
        "smtp_notify_to":    (req.notify_to or "", False),
        "email_notify_download": (str(req.email_notify_download).lower(), False),
        "email_notify_sync":     (str(req.email_notify_sync).lower(), False),
        "email_notify_request":  (str(req.email_notify_request).lower(), False),
        "smtp_recently_added_mode":    (_valid_ra_mode(req.recently_added_mode), False),
        "smtp_recently_added_time":    (_valid_hhmm(req.recently_added_time), False),
        "smtp_recently_added_weekday": (str(max(0, min(6, req.recently_added_weekday))), False),
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
    # Switching to a digest mode: seed the cursor to "now" so the first
    # newsletter only contains items added AFTER enabling it, never the whole
    # back-catalogue. Only when no cursor exists yet.
    if _valid_ra_mode(req.recently_added_mode) in ("daily", "weekly"):
        if not (await config_handler.get("smtp_recently_added_last_sent") or "").strip():
            from datetime import datetime, timezone
            await config_handler.set("smtp_recently_added_last_sent",
                                     datetime.now(timezone.utc).isoformat())
    return {"ok": True}


@protected_route(settings_router.get, "/notifications/added-enabled", scopes=None)
async def added_notifications_enabled(request: Request) -> dict:
    """Whether a 'recently added' notification can be delivered on any channel
    (Discord/webhook or email). The metadata editor hides its 'Send
    notification' button when both are off. Auth-only: returns just a bool."""
    from handler.notifications.recently_added import _delivery_configured
    return {"enabled": await _delivery_configured()}


@protected_route(settings_router.post, "/smtp/recently-added-digest/test", scopes=[Scope.SETTINGS_WRITE])
async def send_recently_added_digest_now(request: Request) -> dict:
    """Send a recently-added newsletter right now for the last 7 days, ignoring
    the schedule. For previewing the digest without waiting for the slot."""
    from handler.notifications.digest import send_now
    try:
        sent = await send_now(days=7)
        return {"ok": True, "emails_sent": sent}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "error": str(e)}


@protected_route(settings_router.post, "/smtp/test", scopes=[Scope.SETTINGS_WRITE])
async def test_smtp(request: Request, req: SmtpRequest) -> dict:
    return await run_smtp_test(req)


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
        "notify_added":    await config_handler.get_bool("webhook_notify_added", default=True),
        "include_cover":   await config_handler.get_bool("webhook_include_cover", default=True),
        "avatar_url":      await config_handler.get("webhook_avatar_url") or "",
        "server_name":     await config_handler.get("server_name") or "",
        "tpl_added_title":          await config_handler.get("webhook_tpl_added_title") or "",
        "tpl_added_body":           await config_handler.get("webhook_tpl_added_body") or "",
        "tpl_added_content":        await config_handler.get("webhook_tpl_added_content") or "",
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
        "webhook_notify_added":    (str(req.notify_added).lower(), False),
        "webhook_include_cover":   (str(req.include_cover).lower(), False),
        "webhook_avatar_url":      (req.avatar_url or "", False),
        "server_name":             (req.server_name or "", False),
        "webhook_tpl_added_title":          (req.tpl_added_title or "", False),
        "webhook_tpl_added_body":           (req.tpl_added_body or "", False),
        "webhook_tpl_added_content":        (req.tpl_added_content or "", False),
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
