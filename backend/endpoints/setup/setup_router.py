"""
Setup endpoints - only accessible when setup is not yet complete.
Secured by SetupGuardMiddleware (enforced in main.py).
"""

from __future__ import annotations


from handler.config.connection_tests import run_scraper_test, run_smtp_test
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator

from handler.auth.passwords import hash_password, password_problem
from handler.config.config_handler import config_handler
from handler.database.users_handler import UsersHandler
from handler.gog.gog_auth_handler import gog_auth_handler
from models.user import Role, User

setup_router = APIRouter(prefix="/api/setup", tags=["setup"])

users_handler = UsersHandler()


class AdminCreateRequest(BaseModel):
    username: str
    password: str
    email: str

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        # Same rule as every other route, stated in handler.auth.passwords.
        # Kept as a validator rather than a handler call because this wizard
        # runs before there is anyone to show a 400 to, and its own form
        # already blocks a weak password client-side.
        problem = password_problem(v)
        if problem:
            raise ValueError(problem)
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

    from config import BASE_PATH, RESOURCES_PATH

    raw = (req.avatar_url or "").strip()
    # Reject any external URL or non-resource path - upload-only policy
    if not raw.startswith("/resources/avatars/"):
        raise HTTPException(status_code=400, detail="Invalid avatar path - must be a server-downloaded resource")

    avatars_dir = _Path(RESOURCES_PATH) / "avatars"
    candidate = (_Path(BASE_PATH) / raw.lstrip("/")).resolve()
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
    return await run_scraper_test(req)


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
    return await run_smtp_test(req)


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
