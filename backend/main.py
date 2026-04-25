"""GamesDownloader - FastAPI application entry point.

Architecture:
  - Core:        Auth, users, setup wizard, plugin system
  - GOG module:  GOG manifest sync, metadata scraping, direct download
  - ROM module:  ROM library, platforms, EmulatorJS  (future)
  - Torrent:     qBittorrent / Transmission integration  (future)
  - Shared:      WebSockets, task queue (Redis), notifications
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy import text

import socketio
import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi_pagination import add_pagination
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from config import DEBUG, DEV_HOST, DEV_PORT, RESOURCES_PATH
from handler.auth.middleware import AuthMiddleware
from middleware.ip_allowlist import IpAllowlistMiddleware
from middleware.security_headers import SecurityHeadersMiddleware
from handler.auth.passwords import hash_password
from handler.database.session import async_engine, async_session_factory
from handler.socket_handler import sio
from models.base import Base
from models.user import Role, User
from plugins.manager import plugin_manager
from utils.http import close_client

logging.basicConfig(
    level=logging.DEBUG if DEBUG else logging.INFO,
    format="%(asctime)s %(levelname)-8s [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


async def _init_db() -> None:
    """Create all tables and run incremental column migrations."""
    # Import all models so Base knows about them
    import models.gog_game       # noqa: F401
    import models.game_request   # noqa: F401
    import models.app_config     # noqa: F401
    import models.gog_account    # noqa: F401
    import models.download_job   # noqa: F401
    import models.library_game   # noqa: F401
    import models.library_file   # noqa: F401
    import models.download_stat  # noqa: F401
    import models.user_game_access  # noqa: F401
    import models.audit_log         # noqa: F401
    import models.scan_result       # noqa: F401
    import models.quarantine_entry  # noqa: F401
    import models.invite_code       # noqa: F401
    import models.user_session      # noqa: F401
    import models.download_token    # noqa: F401
    import models.library_torrent   # noqa: F401
    import models.torrent_download  # noqa: F401
    import models.rom_platform             # noqa: F401
    import models.rom                      # noqa: F401
    import models.rom_save_state           # noqa: F401
    import models.plugin_config            # noqa: F401

    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # ── Incremental migrations (ALTER TABLE for new columns) ──────────────────
    # create_all() only creates missing tables; it never alters existing ones.
    # Each entry: (table, column, DDL type).  Safe to re-run - checks first.
    _COLUMN_MIGRATIONS = [
        ("gog_games",      "requirements",      "JSON NULL"),
        ("gog_games",      "icon_path",         "VARCHAR(1024) NULL"),
        ("library_games",  "icon_path",         "VARCHAR(512) NULL"),
        ("gog_games",      "logo_url",          "VARCHAR(512) NULL"),
        ("gog_games",      "logo_path",         "VARCHAR(1024) NULL"),
        ("download_jobs",  "verify_checksum",   "TINYINT(1) NOT NULL DEFAULT 0"),
        ("download_jobs",  "checksum",          "VARCHAR(64) NULL"),
        ("download_jobs",  "checksum_status",   "VARCHAR(16) NULL"),
        ("users",          "permissions",       "JSON NULL"),
        ("users",          "preferences",       "JSON NULL"),
        # ROM extra media columns (added in migration 002)
        ("roms",           "support_path",      "VARCHAR(512) NULL"),
        ("roms",           "wheel_path",        "VARCHAR(512) NULL"),
        ("roms",           "bezel_path",        "VARCHAR(512) NULL"),
        ("roms",           "steamgrid_path",    "VARCHAR(512) NULL"),
        ("roms",           "video_path",        "VARCHAR(512) NULL"),
        ("roms",           "picto_path",        "VARCHAR(512) NULL"),
        ("roms",           "sha1_hash",         "VARCHAR(40) NULL"),
        ("roms",           "cover_type",        "VARCHAR(32) NULL"),
        ("roms",           "cover_aspect",      "VARCHAR(10) NULL"),
        ("roms",           "developer_ss_id",   "INT NULL"),
        ("roms",           "publisher_ss_id",   "INT NULL"),
        ("roms",           "ss_score",          "FLOAT NULL"),
        ("roms",           "igdb_rating",       "FLOAT NULL"),
        ("roms",           "lb_rating",         "FLOAT NULL"),
        ("roms",           "plugin_ratings",    "JSON NULL"),
        ("roms",           "alternative_names", "JSON NULL"),
        ("roms",           "franchises",        "JSON NULL"),
        ("roms",           "hltb_id",           "INT NULL"),
        ("roms",           "hltb_main_s",        "INT NULL"),
        ("roms",           "hltb_extra_s",       "INT NULL"),
        ("roms",           "hltb_complete_s",    "INT NULL"),

        ("library_games",  "hltb_main_s",        "INT NULL"),
        ("library_games",  "hltb_complete_s",    "INT NULL"),
        ("gog_games",      "hltb_main_s",        "INT NULL"),
        ("gog_games",      "hltb_complete_s",    "INT NULL"),
        # game_requests: new columns added when feature was built out
        ("game_requests",  "link",               "VARCHAR(512) NULL"),
        ("game_requests",  "platform",           "VARCHAR(16) NOT NULL DEFAULT 'games'"),
        ("game_requests",  "admin_note",         "TEXT NULL"),
        ("game_requests",  "username",           "VARCHAR(128) NULL"),
        ("game_requests",  "platform_slug",      "VARCHAR(64) NULL"),
        ("game_requests",  "cover_url",          "VARCHAR(512) NULL"),
    ]
    async with async_engine.begin() as conn:
        for table, column, col_ddl in _COLUMN_MIGRATIONS:
            try:
                # Check whether the column already exists
                exists = await conn.execute(
                    text(
                        "SELECT COUNT(*) FROM information_schema.columns "
                        "WHERE table_schema = DATABASE() "
                        f"AND table_name = '{table}' AND column_name = '{column}'"
                    )
                )
                if exists.scalar() == 0:
                    await conn.execute(
                        text(f"ALTER TABLE `{table}` ADD COLUMN `{column}` {col_ddl}")
                    )
                    logger.info("Migration: added column %s.%s", table, column)
            except Exception as exc:
                logger.warning("Migration check failed for %s.%s: %s", table, column, exc)

    # ── Index migrations ─────────────────────────────────────────────────────
    # Composite and single-column indexes that speed up common queries.
    # Safe to re-run - each checks information_schema.statistics first.
    _INDEX_MIGRATIONS = [
        # roms: most list queries filter by platform AND exclude missing files
        ("ix_roms_platform_missing", "roms",       "CREATE INDEX ix_roms_platform_missing ON roms (platform_id, missing_from_fs)"),
        # gog_games: title search used by GOG scraper and library search
        ("ix_gog_games_title",       "gog_games",  "CREATE INDEX ix_gog_games_title ON gog_games (title(255))"),
        # audit_logs: logs are queried/trimmed by creation date
        ("ix_audit_logs_created_at", "audit_logs", "CREATE INDEX ix_audit_logs_created_at ON audit_logs (created_at)"),
        # download_tokens: token lookup on every public download
        ("ix_dl_tokens_token",       "download_tokens", "CREATE INDEX ix_dl_tokens_token ON download_tokens (token(64))"),
        # users: username lookup on every login
        ("ix_users_username",        "users",           "CREATE UNIQUE INDEX ix_users_username ON users (username)"),
        # user_sessions: JTI lookup on every authenticated request
        ("ix_sessions_access_jti",   "user_sessions",   "CREATE INDEX ix_sessions_access_jti ON user_sessions (access_jti(64))"),
        ("ix_sessions_refresh_jti",  "user_sessions",   "CREATE INDEX ix_sessions_refresh_jti ON user_sessions (refresh_jti(64))"),
    ]
    async with async_engine.begin() as conn:
        for index_name, table, ddl in _INDEX_MIGRATIONS:
            try:
                exists = await conn.execute(
                    text(
                        "SELECT COUNT(*) FROM information_schema.statistics "
                        "WHERE table_schema = DATABASE() "
                        f"AND table_name = '{table}' AND index_name = '{index_name}'"
                    )
                )
                if exists.scalar() == 0:
                    await conn.execute(text(ddl))
                    logger.info("Migration: created index %s on %s", index_name, table)
            except Exception as exc:
                logger.warning("Migration check failed for index %s: %s", index_name, exc)

    logger.info("Database tables ready.")

    # ── Role value migration: viewer → user ───────────────────────────────────
    async with async_engine.begin() as conn:
        try:
            result = await conn.execute(
                text("SELECT COUNT(*) FROM users WHERE role = 'viewer'")
            )
            count = result.scalar()
            if count:
                await conn.execute(
                    text("UPDATE users SET role = 'user' WHERE role = 'viewer'")
                )
                logger.info("Migration: renamed %d user role(s) viewer → user", count)
        except Exception as exc:
            logger.warning("Role migration (viewer→user) failed: %s", exc)

    # No default admin seeding - admin is created through the setup wizard


def _init_rom_dirs() -> None:
    """Create ROM library subdirectory for every known platform on startup.

    De-duplicates by canonical slug so alias fs_slugs (e.g. `atari-2600`,
    `super-nintendo`) don't create a second folder next to the primary
    one (`atari2600`, `snes`) - users saw confusing duplicate tiles and
    the scanner choked on the shared unique-slug index.  First declaration
    in PLATFORM_MAP wins as the canonical fs_slug.
    """
    import pathlib
    from config import ROMS_PATH
    from handler.metadata.rom_platform_map import PLATFORM_MAP, slug_from_fs_slug

    base = pathlib.Path(ROMS_PATH)
    base.mkdir(parents=True, exist_ok=True)

    seen_slugs: set[str] = set()
    canonical_fs_slugs: list[str] = []
    for fs_slug in PLATFORM_MAP:
        slug = slug_from_fs_slug(fs_slug)
        if slug in seen_slugs:
            continue
        seen_slugs.add(slug)
        canonical_fs_slugs.append(fs_slug)

    created = 0
    for fs_slug in canonical_fs_slugs:
        d = base / fs_slug
        if not d.exists():
            d.mkdir(exist_ok=True)
            created += 1
    logger.info(
        "ROM dirs ready - %d canonical platforms (%d aliases skipped), %d new folder(s) created",
        len(canonical_fs_slugs), len(PLATFORM_MAP) - len(canonical_fs_slugs), created,
    )


_WEAK_KEYS = {"change-me-in-production", "secret", "changeme", "insecure", ""}


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    logger.info("GamesDownloaderV3 starting up…")

    from config import AUTH_SECRET_KEY
    if AUTH_SECRET_KEY in _WEAK_KEYS or len(AUTH_SECRET_KEY) < 32:
        if not DEBUG:
            logger.critical(
                "FATAL: GD_AUTH_SECRET_KEY is weak or default. "
                "Set a strong random secret (min 32 chars) via the GD_AUTH_SECRET_KEY "
                "environment variable. Refusing to start in production mode."
            )
            raise SystemExit(1)
        logger.warning(
            "⚠  GD_AUTH_SECRET_KEY is weak or default! Set a strong random secret "
            "via the GD_AUTH_SECRET_KEY environment variable before going to production."
        )

    await _init_db()
    _init_rom_dirs()

    # Load plugins
    plugin_manager.discover_and_load()
    plugin_manager.hook.lifecycle_on_startup()

    # Pre-warm LaunchBox index in background (takes ~35s, avoids timeout on first search)
    from handler.metadata import launchbox_handler as _lb
    asyncio.create_task(_lb._ensure_index())

    # ClamAV scheduled auto-update loop (sleeps 90 s before first check)
    from handler.clamav import clamav_handler as _clamav
    _clamav_task = asyncio.create_task(_clamav.auto_update_loop())

    # Security report scheduled loop (checks every hour)
    from handler.email.security_report import report_loop as _report_loop
    _report_task = asyncio.create_task(_report_loop())

    # Torrent monitors
    from handler.torrent.seed_monitor import seed_monitor_loop, download_monitor_loop
    _seed_task     = asyncio.create_task(seed_monitor_loop())
    _dl_mon_task   = asyncio.create_task(download_monitor_loop())

    yield

    # Shutdown
    _clamav_task.cancel()
    _report_task.cancel()
    _seed_task.cancel()
    _dl_mon_task.cancel()
    plugin_manager.hook.lifecycle_on_shutdown()
    await close_client()
    logger.info("GamesDownloaderV3 shut down.")


app = FastAPI(
    title="GamesDownloader API",
    version="3.0.0",
    description="Self-hosted game library - GOG + ROMs + Emulation + Plugins",
    lifespan=lifespan,
    docs_url="/api/docs" if DEBUG else None,
    redoc_url="/api/redoc" if DEBUG else None,
)

# ── Middleware (order matters: outermost = last added runs first) ─────────────

# Security headers - added to every response
app.add_middleware(SecurityHeadersMiddleware)

# IP allowlist - blocks unlisted IPs before anything else runs
app.add_middleware(IpAllowlistMiddleware)

# CORS - dynamic: reads allowed origins from config on every preflight/request.
# Changes via Settings → Security take effect immediately (no restart needed).
class DynamicCORSMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        from handler.config.config_handler import config_handler as _cfg
        raw = (await _cfg.get("cors_origins")) or ""
        origins = [o.strip() for o in raw.split(",") if o.strip()] or (["*"] if DEBUG else [])

        origin = request.headers.get("origin", "")

        # Handle CORS preflight
        if request.method == "OPTIONS" and origin:
            allowed = "*" in origins or origin in origins
            if allowed:
                headers = {
                    "Access-Control-Allow-Origin":      origin if "*" not in origins else "*",
                    "Access-Control-Allow-Credentials": "true",
                    "Access-Control-Allow-Methods":     "GET, POST, PUT, PATCH, DELETE, OPTIONS",
                    "Access-Control-Allow-Headers":     "*",
                    "Access-Control-Max-Age":           "86400",
                }
                return JSONResponse(None, status_code=204, headers=headers)

        response = await call_next(request)

        if origin and ("*" in origins or origin in origins):
            response.headers["Access-Control-Allow-Origin"]      = origin if "*" not in origins else "*"
            response.headers["Access-Control-Allow-Credentials"] = "true"

        return response

app.add_middleware(DynamicCORSMiddleware)
app.add_middleware(AuthMiddleware)

# ── Setup guard - redirect to setup when not yet configured ───────────────────


class SetupGuardMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        path = request.url.path
        allowed_prefixes = ("/api/setup", "/api/health", "/api/auth/sso", "/assets", "/resources", "/_vite", "/favicon")
        if any(path.startswith(p) for p in allowed_prefixes) or path in ("/", "/setup"):
            return await call_next(request)
        from handler.config.config_handler import config_handler
        try:
            complete = await config_handler.is_setup_complete()
        except Exception:
            complete = True  # Don't block if DB not ready
        if not complete and path.startswith("/api"):
            return JSONResponse({"detail": "Setup not complete"}, status_code=503)
        return await call_next(request)


app.add_middleware(SetupGuardMiddleware)

# ── Auth + Users ──────────────────────────────────────────────────────────────
from endpoints.auth import router as auth_router
from endpoints.users import router as users_router

app.include_router(auth_router, prefix="/api")
app.include_router(users_router, prefix="/api")

# ── Setup wizard ──────────────────────────────────────────────────────────────
from endpoints.setup.setup_router import setup_router

app.include_router(setup_router)

# ── GOG ───────────────────────────────────────────────────────────────────────
from endpoints.gog.gog_router import gog_router
from endpoints.gog.download_router import download_router

app.include_router(gog_router)
app.include_router(download_router)

# ── Library (GamesDownloader) ─────────────────────────────────────────────────
from endpoints.library.library_router import library_router
from endpoints.library.upload_router import upload_router

app.include_router(library_router, prefix="/api")
app.include_router(upload_router,  prefix="/api")

# ── Settings ──────────────────────────────────────────────────────────────────
from endpoints.settings.settings_router import settings_router
from endpoints.settings.clamav_router import clamav_router
from endpoints.settings.network_router import network_router
from endpoints.settings.sessions_router import router as sessions_router
from endpoints.settings.email_router import router as email_router
from endpoints.settings.download_tokens_router import router as download_tokens_router
from endpoints.settings.speed_limit_router import router as speed_limit_router
from endpoints.settings.security_report_router import router as security_report_router
from endpoints.settings.sso_settings_router import router as sso_settings_router
from endpoints.settings.plugins_router import plugins_router
from endpoints.settings.metadata_backup_router import router as metadata_backup_router
from endpoints.sso_router import router as sso_router
from endpoints.dl_router import router as dl_router
from endpoints.settings.transmission_router import transmission_router
from endpoints.torrent.torrent_router import torrent_router

app.include_router(settings_router)
app.include_router(clamav_router)
app.include_router(network_router)
app.include_router(sessions_router)
app.include_router(email_router)
app.include_router(download_tokens_router)
app.include_router(speed_limit_router)
app.include_router(security_report_router)
app.include_router(sso_settings_router)
app.include_router(plugins_router)
app.include_router(metadata_backup_router)
app.include_router(sso_router)
app.include_router(dl_router)
app.include_router(transmission_router)
app.include_router(torrent_router)

# ── Game Requests ─────────────────────────────────────────────────────────────
from endpoints.requests.requests_router import requests_router

app.include_router(requests_router)

# ── ROM / Emulation ───────────────────────────────────────────────────────────
from endpoints.roms.roms_router import router as roms_router                         # noqa: E402
from endpoints.roms.savestate_router import router as savestate_router               # noqa: E402
from endpoints.settings.roms_settings_router import router as roms_settings_router  # noqa: E402

app.include_router(roms_router)
app.include_router(savestate_router)
app.include_router(roms_settings_router)

# ── WebSocket / Socket.IO ─────────────────────────────────────────────────────
# socketio.ASGIApp wraps the FastAPI app so Socket.IO WS connections are handled
# before regular HTTP traffic is forwarded to FastAPI.
# NOTE: uvicorn/gunicorn must point to `main:app` - we rebind `app` below so
# that the exported symbol is the Socket.IO ASGI wrapper, not the bare FastAPI app.
socket_app = socketio.ASGIApp(sio, app)

# ── Health check ──────────────────────────────────────────────────────────────
@app.get("/api/health", tags=["system"])
async def health_check() -> dict:
    return {"status": "ok", "version": "3.0.0"}


# ── Static: serve /resources/ ─────────────────────────────────────────────────
os.makedirs(RESOURCES_PATH, exist_ok=True)
app.mount("/resources", StaticFiles(directory=RESOURCES_PATH), name="resources")

# ── Serve Vue SPA ─────────────────────────────────────────────────────────────
STATIC_PATH = os.path.join(os.path.dirname(__file__), "static")
if os.path.isdir(STATIC_PATH):
    from fastapi.responses import FileResponse

    app.mount("/", StaticFiles(directory=STATIC_PATH, html=True), name="spa")

    @app.exception_handler(404)
    async def spa_fallback(request, exc):
        index = os.path.join(STATIC_PATH, "index.html")
        if os.path.exists(index):
            return FileResponse(
                index,
                headers={"Cache-Control": "no-cache, no-store, must-revalidate"},
            )
        return exc

add_pagination(app)

# Rebind `app` to the Socket.IO ASGI wrapper so that `uvicorn main:app`
# (and the Docker CMD) automatically includes WebSocket/Socket.IO support.
# All FastAPI routes and middleware have already been registered on the
# original FastAPI instance at this point; socket_app just wraps it.
app = socket_app  # type: ignore[assignment]

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host=DEV_HOST,
        port=DEV_PORT,
        reload=True,
        access_log=False,
    )
