"""
Setup endpoints - only accessible when setup is not yet complete.
Secured by SetupGuardMiddleware (enforced in main.py).
"""

from __future__ import annotations

import re
import smtplib
import ssl
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator

from handler.auth.passwords import hash_password
from handler.config.config_handler import config_handler
from handler.database.users_handler import UsersHandler
from handler.gog.gog_auth_handler import gog_auth_handler
from models.user import Role, User

setup_router = APIRouter(prefix="/api/setup", tags=["setup"])

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
users_handler = UsersHandler()


class AdminCreateRequest(BaseModel):
    username: str
    password: str
    email: str

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        if not re.search(r"[A-Za-z]", v):
            raise ValueError("Password must contain at least one letter")
        if not re.search(r"\d", v):
            raise ValueError("Password must contain at least one digit")
        return v


class GogCodeRequest(BaseModel):
    code: str


class ApiKeysRequest(BaseModel):
    igdb_client_id: str | None = None
    igdb_client_secret: str | None = None
    steamgriddb_api_key: str | None = None
    rawg_api_key: str | None = None
    screenscraper_username: str | None = None
    screenscraper_password: str | None = None
    ra_api_key: str | None = None


class ScraperTestRequest(BaseModel):
    scraper: str   # igdb | steamgriddb | rawg | screenscraper | ra
    igdb_client_id: str | None = None
    igdb_client_secret: str | None = None
    steamgriddb_api_key: str | None = None
    rawg_api_key: str | None = None
    screenscraper_username: str | None = None
    screenscraper_password: str | None = None
    ra_api_key: str | None = None


class SmtpRequest(BaseModel):
    enabled: bool = False
    host: str | None = None
    port: int = 587
    username: str | None = None
    password: str | None = None
    from_address: str | None = None
    use_tls: bool = True
    test_to: str | None = None   # recipient for test email


class AppSettingsRequest(BaseModel):
    enable_registrations: bool = False


class GogAvatarRequest(BaseModel):
    avatar_url: str


@setup_router.get("/status")
async def get_setup_status() -> dict:
    is_complete = await config_handler.is_setup_complete()
    user_count  = await users_handler.count()
    return {
        "is_setup_complete": is_complete,
        "has_admin":         user_count > 0,
    }


@setup_router.post("/admin")
async def create_admin(req: AdminCreateRequest) -> dict:
    if await config_handler.is_setup_complete():
        raise HTTPException(status_code=404, detail="Not found")
    count = await users_handler.count()
    if count > 0:
        raise HTTPException(status_code=400, detail="Admin account already exists")
    existing = await users_handler.get_by_username(req.username)
    if existing:
        raise HTTPException(status_code=400, detail="Username already taken")
    user = User(
        username=req.username,
        hashed_password=hash_password(req.password),
        email=req.email,
        role=Role.ADMIN,
        enabled=True,
    )
    await users_handler.create(user)
    return {"ok": True, "username": req.username}


@setup_router.get("/gog/url")
async def get_gog_url() -> dict:
    return {"url": gog_auth_handler.get_auth_url()}


@setup_router.post("/gog")
async def setup_gog(req: GogCodeRequest) -> dict:
    if await config_handler.is_setup_complete():
        raise HTTPException(status_code=404, detail="Not found")
    try:
        result = await gog_auth_handler.exchange_code(req.code)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"GOG authentication failed: {str(e)}")


@setup_router.post("/gog/avatar")
async def set_gog_avatar(req: GogAvatarRequest) -> dict:
    """During setup: copy the locally-downloaded GOG avatar to the admin user's profile.

    SECURITY: Only accepts server-controlled paths under /resources/avatars/.
    External http(s) URLs are rejected to prevent SSRF and open-redirect via
    the /users/me/avatar handler. The GOG flow downloads avatars locally first
    via handler.gog.media_handler.download_avatar; only that local path is
    accepted here.
    """
    if await config_handler.is_setup_complete():
        raise HTTPException(status_code=404, detail="Not found")
    from pathlib import Path as _Path

    from config import GD_BASE_PATH, RESOURCES_PATH

    raw = (req.avatar_url or "").strip()
    # Reject any external URL or non-resource path - upload-only policy
    if not raw.startswith("/resources/avatars/"):
        raise HTTPException(status_code=400, detail="Invalid avatar path - must be a server-downloaded resource")

    avatars_dir = _Path(RESOURCES_PATH) / "avatars"
    candidate = (_Path(GD_BASE_PATH) / raw.lstrip("/")).resolve()
    try:
        # Path traversal guard: candidate MUST live under avatars_dir
        candidate.relative_to(avatars_dir.resolve())
    except (ValueError, RuntimeError):
        raise HTTPException(status_code=400, detail="Invalid avatar path")
    if not candidate.is_file():
        raise HTTPException(status_code=400, detail="Avatar file not found")

    # NOTE: uses a single DB session internally to avoid SQLAlchemy detached-instance bug
    ok = await users_handler.update_first_user_avatar(str(candidate))
    if not ok:
        raise HTTPException(status_code=400, detail="No user found")
    return {"ok": True}


@setup_router.post("/api-keys")
async def save_api_keys(req: ApiKeysRequest) -> dict:
    if await config_handler.is_setup_complete():
        raise HTTPException(status_code=404, detail="Not found")
    data: dict[str, tuple[str, bool]] = {}
    if req.igdb_client_id:         data["igdb_client_id"]         = (req.igdb_client_id, True)
    if req.igdb_client_secret:     data["igdb_client_secret"]     = (req.igdb_client_secret, True)
    if req.steamgriddb_api_key:    data["steamgriddb_api_key"]    = (req.steamgriddb_api_key, True)
    if req.rawg_api_key:           data["rawg_api_key"]            = (req.rawg_api_key, True)
    if req.screenscraper_username: data["screenscraper_username"]  = (req.screenscraper_username, False)
    if req.screenscraper_password: data["screenscraper_password"]  = (req.screenscraper_password, True)
    if req.ra_api_key:             data["ra_api_key"]              = (req.ra_api_key, True)
    if data:
        await config_handler.set_many(data)
    return {"ok": True}


@setup_router.post("/scrapers/test")
async def test_scraper(req: ScraperTestRequest) -> dict:
    if await config_handler.is_setup_complete():
        raise HTTPException(status_code=404, detail="Not found")
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
                if r.status_code == 401 or r.status_code == 403:
                    raise HTTPException(status_code=400, detail="Invalid RAWG API key")

            elif req.scraper == "screenscraper":
                if not req.screenscraper_username or not req.screenscraper_password:
                    raise HTTPException(status_code=400, detail="Username and password required")
                r = await c.get("https://www.screenscraper.fr/api2/ssuserInfos.php", params={
                    "devid": "GamesDownloader", "devpassword": "dev", "softname": "GamesDownloader",
                    "output": "json", "ssid": req.screenscraper_username,
                    "sspassword": req.screenscraper_password,
                })
                if r.status_code == 401 or "wrongpass" in r.text.lower():
                    raise HTTPException(status_code=400, detail="Invalid ScreenScraper credentials")

            elif req.scraper == "ra":
                if not req.ra_api_key:
                    raise HTTPException(status_code=400, detail="API key required")
                r = await c.get("https://retroachievements.org/API/API_GetTopTenUsers.php",
                                params={"y": req.ra_api_key})
                if r.status_code == 401 or (r.status_code == 200 and r.json() is None):
                    raise HTTPException(status_code=400, detail="Invalid RetroAchievements API key")
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


@setup_router.post("/smtp")
async def save_smtp(req: SmtpRequest) -> dict:
    if await config_handler.is_setup_complete():
        raise HTTPException(status_code=404, detail="Not found")
    await config_handler.set_many({
        "smtp_enabled":      (str(req.enabled).lower(), False),
        "smtp_host":         (req.host or "", False),
        "smtp_port":         (str(req.port), False),
        "smtp_username":     (req.username or "", False),
        "smtp_password":     (req.password or "", True),
        "smtp_from_address": (req.from_address or "", False),
        "smtp_use_tls":      (str(req.use_tls).lower(), False),
    })
    return {"ok": True}


@setup_router.post("/smtp/test")
async def test_smtp(req: SmtpRequest) -> dict:
    if await config_handler.is_setup_complete():
        raise HTTPException(status_code=404, detail="Not found")
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

        import asyncio
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, _send_blocking)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@setup_router.post("/app-settings")
async def save_app_settings(req: AppSettingsRequest) -> dict:
    if await config_handler.is_setup_complete():
        raise HTTPException(status_code=404, detail="Not found")
    await config_handler.set_many({
        "enable_registrations": (str(req.enable_registrations).lower(), False),
    })
    return {"ok": True}


@setup_router.post("/complete")
async def complete_setup() -> dict:
    if await config_handler.is_setup_complete():
        raise HTTPException(status_code=404, detail="Not found")
    await config_handler.mark_setup_complete()
    return {"ok": True}
