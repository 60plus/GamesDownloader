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
import shutil
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from sqlalchemy import text

import socketio
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi_pagination import add_pagination
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from config import DEBUG, DEV_HOST, DEV_PORT, GD_VERSION, RESOURCES_PATH, SAVES_PATH
from handler.auth.middleware import AuthMiddleware
from middleware.ip_allowlist import IpAllowlistMiddleware
from middleware.etag import ETagMiddleware
from middleware.security_headers import SecurityHeadersMiddleware
from handler.auth.passwords import hash_password
from handler.database.session import async_engine, async_session_factory
from handler.socket_handler import sio
from models.base import Base
from models.user import Role, User
from plugins.manager import plugin_manager
from utils.http import close_client
from utils.save_paths import is_save_path, saves_root, saves_root_is_legacy, superseded_dir

logging.basicConfig(
    level=logging.DEBUG if DEBUG else logging.INFO,
    format="%(asctime)s %(levelname)-8s [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


async def _relocate_saves() -> None:
    """Move save files off the public resources mount and repoint their rows.

    Idempotent by construction: only rows still under the old root match, so a
    second boot finds nothing and does no work. A file that cannot be moved
    keeps its row pointing at the old path - a save that still loads from the
    wrong place beats a row pointing at nothing.
    """
    old_root = str(Path(RESOURCES_PATH) / "roms")
    new_root = saves_root()
    moved, failed = 0, 0
    async with async_engine.begin() as conn:
        for tbl, has_shot in (("rom_save_states", True), ("rom_saves", False)):
            try:
                cols = "id, file_path, file_name" + (", screenshot_path" if has_shot else "")
                rows = (await conn.execute(
                    text(f"SELECT {cols} FROM `{tbl}` WHERE file_path LIKE :p"),
                    {"p": old_root + "%"},
                )).all()
                for row in rows:
                    row_id, path, name = row[0], row[1], row[2]
                    shot_path = row[3] if has_shot else None
                    try:
                        # resources/roms/<slug>/<rom>/<kind>/<user> becomes
                        # saves/<slug>/<rom>/<kind>/<user>: same shape, new root.
                        new_dir = new_root / Path(path).relative_to(old_root)
                        new_dir.mkdir(parents=True, exist_ok=True)
                        upd = {"p": str(new_dir), "i": row_id}
                        src = Path(path) / name
                        if src.exists() and not (new_dir / name).exists():
                            shutil.move(str(src), str(new_dir / name))
                        sets = "file_path = :p"
                        if has_shot and shot_path:
                            s_src = Path(shot_path)
                            s_dst = new_dir / s_src.name
                            if s_src.exists() and not s_dst.exists():
                                shutil.move(str(s_src), str(s_dst))
                            sets += ", screenshot_path = :s"
                            upd["s"] = str(s_dst)
                        await conn.execute(
                            text(f"UPDATE `{tbl}` SET {sets} WHERE id = :i"), upd
                        )
                        moved += 1
                    except (OSError, ValueError) as exc:
                        failed += 1
                        logger.warning(
                            "Save relocation: leaving %s row %s at %s (%s)",
                            tbl, row_id, path, exc,
                        )
            except Exception as exc:
                logger.warning("Save relocation failed for %s: %s", tbl, exc)
    if moved or failed:
        logger.info(
            "Migration: relocated %d save(s) out of the public resources mount%s",
            moved, f", {failed} left in place" if failed else "",
        )


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
    import models.library                  # noqa: F401
    import models.collection               # noqa: F401

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
        ("download_stats", "duration_ms",       "BIGINT NULL"),
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
        ("roms",           "cover_url",         "VARCHAR(1024) NULL"),
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
        # 2FA / TOTP (RFC 6238)
        ("users",          "totp_secret",         "VARCHAR(64) NULL"),
        ("users",          "totp_enabled",        "TINYINT(1) NOT NULL DEFAULT 0"),
        ("users",          "totp_recovery_codes", "JSON NULL"),
        # Per-user opt-in for recently-added emails (default on).
        ("users",          "notify_recently_added", "TINYINT(1) NOT NULL DEFAULT 1"),
        # Library collections feature
        ("library_games",  "in_default_library",  "TINYINT(1) NOT NULL DEFAULT 1"),
        # Per-user library access control
        ("libraries",      "visibility",          "VARCHAR(16) NOT NULL DEFAULT 'public'"),
        # Collections live inside a container library (kind 'collections').
        ("collections",    "library_id",          "INT NULL"),
        # Collections: short description (list view) + HLTB playtime override.
        ("collections",    "description_short",   "TEXT NULL"),
        ("collections",    "hltb_main_s",         "INT NULL"),
        ("collections",    "hltb_complete_s",     "INT NULL"),
        # Collections: scraped/picked hero (backdrop) + logo (clearlogo).
        ("collections",    "hero_path",           "VARCHAR(512) NULL"),
        ("collections",    "logo_path",           "VARCHAR(512) NULL"),
        # Animated-cover flag (multi-frame webp/gif); NULL = not checked yet.
        ("library_games",  "cover_animated",      "TINYINT(1) NULL"),
        ("gog_games",      "cover_animated",      "TINYINT(1) NULL"),
        ("collections",    "cover_animated",      "TINYINT(1) NULL"),
        # Local trailer copy (downloaded via yt-dlp or uploaded in the editor).
        ("library_games",  "video_path",          "VARCHAR(512) NULL"),
        ("gog_games",      "video_path",          "VARCHAR(1024) NULL"),
        # Torrent downloads can target a custom library (folder + membership).
        ("torrent_downloads", "library",          "VARCHAR(128) NULL"),
        # Recently-added notification: one-shot guard (backfilled once below).
        ("library_games",  "announced_at",         "DATETIME NULL"),
        ("roms",           "announced_at",         "DATETIME NULL"),
        # Savestates live in numbered slots (1-9) and are replaced in place.
        # NULL marks legacy rows saved before slots existed.
        ("rom_save_states", "slot",                "INT NULL"),
        # Screenshot bytes count against the save quota like any other file.
        # Legacy rows read 0 until their slot is next written - undercounting a
        # thumbnail is not worth a disk walk at boot.
        ("rom_save_states", "screenshot_size_bytes", "BIGINT NOT NULL DEFAULT 0"),
        # Storefront libraries (GOG, and any catalogue of downloadable builds)
        # are grouped apart from real shelves in the navigation.
        ("libraries",      "is_store",              "TINYINT(1) NOT NULL DEFAULT 0"),
        # Whether a library feeds the default Games library. Existing user
        # libraries keep the old behaviour (they do not) until switched on.
        ("libraries",      "adds_to_default_library", "TINYINT(1) NOT NULL DEFAULT 0"),
        # Which plugin catalogue a store library lists, if any.
        ("libraries",      "catalog_id",            "VARCHAR(64) NULL"),
        # Which plugin owns a store, so it can be removed with the plugin without
        # a live instance. Backfilled onto pre-column stores by the reconcile.
        ("libraries",      "plugin_id",             "VARCHAR(64) NULL"),
        # Shown under the title. Tells two builds of the same game apart.
        ("library_games",  "subtitle",              "VARCHAR(255) NULL"),
        # Where a catalogue game came from, so a reinstall of the plugin re-links
        # its entry to this game instead of offering a second download.
        ("library_games",  "catalog_id",            "VARCHAR(64) NULL"),
        ("library_games",  "catalog_external_id",   "VARCHAR(255) NULL"),
        # What the catalogue last wrote, so a manual edit can be recognised and
        # left alone on the next sync.
        ("catalog_entries", "subtitle",             "VARCHAR(255) NULL"),
        ("catalog_entries", "catalog_title",        "VARCHAR(255) NULL"),
        # The metadata pass. NULL scraped_at means "not looked at yet", which is
        # what lets an interrupted run resume instead of restarting.
        ("catalog_entries", "meta_scraped_at",      "DATETIME NULL"),
        ("catalog_entries", "meta_search_term",     "VARCHAR(255) NULL"),
        ("catalog_entries", "meta_source",          "VARCHAR(32) NULL"),
        ("catalog_entries", "meta_matched_title",   "VARCHAR(255) NULL"),
        ("catalog_entries", "meta_confidence",      "VARCHAR(16) NULL"),
        # Local copy of the catalogue icon, served for the store view. A
        # catalogue entry is not a game (GOG model), so its artwork lives on the
        # entry rather than on a LibraryGame that exists only once downloaded.
        ("catalog_entries", "icon_path",            "VARCHAR(512) NULL"),
        # Scraped presentation held on the entry (the GogGame equivalent): the
        # store and the entry detail read these, and a download copies them onto
        # the new game. release_date is a plain string (a label, not a query).
        ("catalog_entries", "cover_path",           "VARCHAR(512) NULL"),
        ("catalog_entries", "background_path",       "VARCHAR(512) NULL"),
        ("catalog_entries", "logo_path",             "VARCHAR(512) NULL"),
        ("catalog_entries", "description",          "TEXT NULL"),
        ("catalog_entries", "developer",            "VARCHAR(255) NULL"),
        ("catalog_entries", "publisher",            "VARCHAR(255) NULL"),
        ("catalog_entries", "release_date",         "VARCHAR(32) NULL"),
        ("catalog_entries", "rating",               "FLOAT NULL"),
        ("catalog_entries", "genres",               "JSON NULL"),
        ("catalog_entries", "screenshots",          "JSON NULL"),
        ("catalog_entries", "meta_ratings",         "JSON NULL"),
        ("catalog_entries", "languages",            "JSON NULL"),
        ("catalog_entries", "requirements",         "JSON NULL"),
        ("catalog_entries", "hltb_main_s",          "INT NULL"),
        ("catalog_entries", "hltb_complete_s",      "INT NULL"),
        # Set by the packer, so "packaged" is a fact rather than a guess at the
        # file name. Rows that predate the column default to 0; there is no
        # backfill, so an archive uploaded earlier reads as a plain file until it
        # is repackaged.
        ("library_files",   "is_archive",           "TINYINT(1) NOT NULL DEFAULT 0"),
    ]
    _added_columns: set[tuple[str, str]] = set()
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
                    _added_columns.add((table, column))
            except Exception as exc:
                logger.warning("Migration check failed for %s.%s: %s", table, column, exc)

        # GOG was the only storefront before the flag existed, so it has to be
        # marked as one or it would vanish from the navigation on upgrade. Keyed
        # on the column having just been created, so it runs exactly once and an
        # admin who later unticks GOG is not overruled on the next boot.
        if ("libraries", "is_store") in _added_columns:
            try:
                await conn.execute(
                    text("UPDATE `libraries` SET `is_store` = 1 WHERE `kind` = 'gog'")
                )
                logger.info("Migration: marked GOG libraries as storefronts")
            except Exception as exc:
                logger.warning("Migration: GOG storefront backfill failed: %s", exc)

        # Stamp the catalogue origin onto games already downloaded from a
        # catalogue, read from the links that still exist - so a game downloaded
        # before this column can still be re-linked after its plugin is removed
        # and reinstalled. Keyed on the column being new, so it runs exactly once
        # and never before the entries it reads from are in place.
        if ("library_games", "catalog_external_id") in _added_columns:
            try:
                await conn.execute(text(
                    "UPDATE `library_games` lg "
                    "JOIN `catalog_entries` ce ON ce.library_game_id = lg.id "
                    "SET lg.catalog_id = ce.catalog_id, "
                    "    lg.catalog_external_id = ce.external_id "
                    "WHERE lg.catalog_external_id IS NULL"
                ))
                logger.info("Migration: stamped catalogue origin onto downloaded games")
            except Exception as exc:
                logger.warning("Migration: catalogue-origin backfill failed: %s", exc)

    # ── Relocate saves out of the public resources mount ──────────────────────
    # RESOURCES_PATH is served as static files with no authentication, and save
    # filenames are derived from the ROM and the slot - which made every user's
    # saves fetchable by anyone who could guess a name. Saves now live under
    # SAVES_PATH, reachable only through the authenticated routes. Move what is
    # already on disk and repoint the rows.
    #
    # Idempotent by construction: it only matches rows still under the old root,
    # so a second boot finds nothing and does no work. A file that cannot be
    # moved keeps its row pointing at the old path - a save that still loads
    # from the wrong place beats a row pointing at nothing.
    #
    # Skipped entirely when there is nowhere safe to move to: saves_root() falls
    # back to the legacy location when /data/saves has no volume, and moving
    # files into a directory that dies with the container would be far worse
    # than leaving them where they are. The static mount refuses to serve them
    # either way.
    if saves_root_is_legacy():
        logger.warning(
            "Skipping save relocation: no persistent volume for the new "
            "directory, so saves stay under %s (the resources mount refuses to "
            "serve them).", Path(RESOURCES_PATH) / "roms",
        )
    else:
        await _relocate_saves()

    # ── Battery-save dedupe (must precede the unique index below) ─────────────
    # A ROM has exactly one battery save per user - the .srm is the whole SRAM
    # chip, and the game's own in-game slots live inside that single blob. Two
    # things put extra rows in the table: the player's upload paths could race
    # (EJS_onSaveSave and the 60s auto-sync both inserting), and older builds
    # appended a row per distinct SRAM content, making the table a history.
    # The unique index below cannot be created while those rows exist.
    #
    # This DOES NOT delete anyone's files. That history is the only copy of a
    # playthrough somebody may still want; the superseded .srm files are parked
    # under SAVES_PATH/_superseded and only the rows go. Runs once, behind a
    # config flag, and GD_SKIP_SAVE_DEDUPE=1 stops it for an operator who wants
    # to look first.
    try:
        from handler.config.config_handler import config_handler as _cfg
        if os.environ.get("GD_SKIP_SAVE_DEDUPE", "").lower() in ("1", "true", "yes"):
            logger.warning(
                "GD_SKIP_SAVE_DEDUPE is set: leaving duplicate battery saves in "
                "place. The ux_save_user_rom index will not be created."
            )
        elif not await _cfg.get_bool("_battery_dedupe_done", default=False):
            async with async_engine.begin() as conn:
                # ROW_NUMBER names each superseded row exactly once. The old
                # self-join emitted a row per newer sibling, so 200 rows meant
                # 19,900 records and ~40k queries - and the count it logged was
                # the pair count, not the number of rows it actually removed.
                doomed = (await conn.execute(text(
                    "SELECT id, user_id, rom_id, file_path, file_name FROM ("
                    "  SELECT id, user_id, rom_id, file_path, file_name,"
                    "         ROW_NUMBER() OVER ("
                    "           PARTITION BY user_id, rom_id"
                    "           ORDER BY updated_at DESC, id DESC) AS rn"
                    "  FROM rom_saves"
                    ") t WHERE t.rn > 1"
                ))).all()
                if doomed:
                    # What the survivors still point at must stay where it is;
                    # rows that shared a filename share the file too.
                    kept = {
                        (r[0], r[1]) for r in (await conn.execute(text(
                            "SELECT file_path, file_name FROM ("
                            "  SELECT file_path, file_name,"
                            "         ROW_NUMBER() OVER ("
                            "           PARTITION BY user_id, rom_id"
                            "           ORDER BY updated_at DESC, id DESC) AS rn"
                            "  FROM rom_saves"
                            ") t WHERE t.rn = 1"
                        ))).all()
                    }
                    logger.info(
                        "Migration: %d superseded battery save row(s) to remove; "
                        "their files are being kept under %s",
                        len(doomed), superseded_dir(),
                    )
                    park = superseded_dir()
                    for _id, _uid, _rid, _path, _name in doomed:
                        logger.info(
                            "  battery row id=%s user=%s rom=%s file=%s",
                            _id, _uid, _rid, Path(_path) / _name,
                        )
                        if (_path, _name) in kept:
                            continue
                        try:
                            src = Path(_path) / _name
                            if src.exists():
                                park.mkdir(parents=True, exist_ok=True)
                                # The id keeps two same-named saves apart.
                                shutil.move(str(src), str(park / f"{_id} - {_name}"))
                        except OSError as exc:
                            logger.warning(
                                "Dedupe: could not park %s/%s (%s) - leaving it",
                                _path, _name, exc,
                            )
                    ids = ",".join(str(int(d[0])) for d in doomed)
                    await conn.execute(
                        text(f"DELETE FROM rom_saves WHERE id IN ({ids})")
                    )
                    logger.info(
                        "Migration: removed %d superseded battery save row(s); "
                        "files preserved in %s", len(doomed), park,
                    )
            await _cfg.set("_battery_dedupe_done", "true")
    except Exception as exc:
        logger.warning("Battery-save dedupe failed: %s", exc)

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
        # A slot holds exactly one savestate. MySQL allows repeated NULLs in a
        # unique index, so legacy slot-less rows survive this untouched.
        ("ux_state_user_rom_slot",   "rom_save_states",
         "CREATE UNIQUE INDEX ux_state_user_rom_slot ON rom_save_states (user_id, rom_id, slot)"),
        # One battery save per user+ROM, enforced by the DB so the player's two
        # concurrent upload paths cannot both insert. Deduped just above.
        ("ux_save_user_rom",         "rom_saves",
         "CREATE UNIQUE INDEX ux_save_user_rom ON rom_saves (user_id, rom_id)"),
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
                logger.info("Migration: renamed %d user role(s) viewer -> user", count)
        except Exception as exc:
            logger.warning("Role migration (viewer->user) failed: %s", exc)

    # ── Recently-added notification: one-time announced_at backfill ──────────
    # The announced_at columns are added by _COLUMN_MIGRATIONS above. Backfill
    # every existing row to NOW() ONCE so the pre-existing library never floods
    # the webhook; only rows created afterwards (announced_at NULL) are eligible
    # for the auto-announce. Guarded by a config flag rather than by column
    # existence, so a crash between the ALTER and the UPDATE cannot skip the
    # backfill permanently (which would make the whole legacy library announce).
    try:
        from handler.config.config_handler import config_handler as _cfg
        if not await _cfg.get_bool("_announced_at_backfilled", default=False):
            async with async_engine.begin() as conn:
                for _tbl in ("library_games", "roms"):
                    try:
                        await conn.execute(
                            text(f"UPDATE `{_tbl}` SET `announced_at` = NOW() WHERE `announced_at` IS NULL")
                        )
                    except Exception as exc:
                        logger.warning("announced_at backfill failed for %s: %s", _tbl, exc)
            await _cfg.set("_announced_at_backfilled", "true")
            logger.info("Migration: backfilled announced_at for existing rows")
    except Exception as exc:
        logger.warning("announced_at backfill guard failed: %s", exc)

    # ── NULL legacy remote request covers ─────────────────────────────────────
    # A request's cover_url used to be stored exactly as the scraper search
    # returned it and rendered straight into an <img>. A ScreenScraper URL
    # carries ssid/sspassword/devpassword in its query string, so every admin's
    # browser fetched it - password and all - from screenscraper.fr. New
    # requests download the art locally (download_request_cover); existing rows
    # drop the remote URL. Losing a thumbnail beats leaking the credential, and
    # a remote CDN cover was against the serve-media-locally rule regardless.
    async with async_engine.begin() as conn:
        try:
            count = (await conn.execute(text(
                "SELECT COUNT(*) FROM game_requests WHERE cover_url LIKE 'http%'"
            ))).scalar()
            if count:
                await conn.execute(text(
                    "UPDATE game_requests SET cover_url = NULL WHERE cover_url LIKE 'http%'"
                ))
                logger.info(
                    "Migration: nulled %d remote request cover(s) - serve-locally policy",
                    count,
                )
        except Exception as exc:
            logger.warning("Request cover migration failed: %s", exc)

    # ── SSRF hardening: NULL legacy http(s) avatar paths ──────────────────────
    # Older versions stored remote CDN URLs as avatar_path and the GET handler
    # issued a 302 redirect, which is an open-redirect / SSRF-adjacent surface.
    # Profile avatars are now upload-only (or copied locally from the GOG flow).
    async with async_engine.begin() as conn:
        try:
            result = await conn.execute(
                text("SELECT COUNT(*) FROM users WHERE avatar_path LIKE 'http%'")
            )
            count = result.scalar()
            if count:
                await conn.execute(
                    text("UPDATE users SET avatar_path = NULL WHERE avatar_path LIKE 'http%'")
                )
                logger.info("Migration: nulled %d remote avatar_path value(s) - upload-only policy", count)
        except Exception as exc:
            logger.warning("Avatar path migration failed: %s", exc)

    # ── Library kind rename: collection → custom_lib ──────────────────────────
    # User-created separate libraries were historically stored as kind
    # "collection". The word "collection(s)" now belongs to the distinct
    # Collections feature (game groupings), so user libraries become "custom_lib".
    async with async_engine.begin() as conn:
        try:
            result = await conn.execute(
                text("SELECT COUNT(*) FROM libraries WHERE kind = 'collection'")
            )
            count = result.scalar()
            if count:
                await conn.execute(
                    text("UPDATE libraries SET kind = 'custom_lib' WHERE kind = 'collection'")
                )
                logger.info("Migration: renamed %d library kind(s) collection -> custom_lib", count)
        except Exception as exc:
            logger.warning("Library kind migration (collection->custom_lib) failed: %s", exc)

    # ── Collection containers (kind 'collections') are user content ───────────
    # No permanent built-in: any legacy 'collections' library becomes a normal
    # deletable container, and any pre-existing collections are attached to it so
    # they are not orphaned by the new collections.library_id column.
    async with async_engine.begin() as conn:
        try:
            await conn.execute(
                text("UPDATE libraries SET is_builtin = 0 WHERE kind = 'collections' AND is_builtin = 1")
            )
            lib_id = (await conn.execute(
                text("SELECT id FROM libraries WHERE kind = 'collections' ORDER BY id LIMIT 1")
            )).scalar()
            if lib_id is not None:
                await conn.execute(
                    text("UPDATE collections SET library_id = :lid WHERE library_id IS NULL"),
                    {"lid": lib_id},
                )
        except Exception as exc:
            logger.warning("Collections container migration failed: %s", exc)

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
    # A KNOWN default/empty key lets anyone forge authentication tokens - refuse
    # to start ALWAYS, even under GD_DEBUG, because signing with a publicly-known
    # value is a full auth bypass regardless of environment.
    if AUTH_SECRET_KEY in _WEAK_KEYS:
        logger.critical(
            "FATAL: GD_AUTH_SECRET_KEY is a known default/empty value - anyone "
            "could forge authentication tokens. Set a strong random secret via "
            "the GD_AUTH_SECRET_KEY environment variable. Refusing to start."
        )
        raise SystemExit(1)
    # A short but non-default secret is weak yet not publicly forgeable: fatal in
    # production, a warning in debug (so local dev with a short random key runs).
    if len(AUTH_SECRET_KEY) < 32:
        if not DEBUG:
            logger.critical(
                "FATAL: GD_AUTH_SECRET_KEY is too short (min 32 chars). "
                "Refusing to start in production mode."
            )
            raise SystemExit(1)
        logger.warning(
            "⚠  GD_AUTH_SECRET_KEY is shorter than 32 chars. Set a strong random "
            "secret via the GD_AUTH_SECRET_KEY environment variable before production."
        )

    await _init_db()
    _init_rom_dirs()

    # Seed built-in library registry rows (idempotent)
    from handler.database.library_registry_handler import library_registry_handler
    await library_registry_handler.ensure_builtins()

    # Load plugins
    plugin_manager.discover_and_load()
    plugin_manager.hook.lifecycle_on_startup()

    # Remove storefronts whose catalogue plugin is gone (uninstalled while GD was
    # down, or before the per-uninstall cleanup existed). Keeps downloaded games.
    from handler.library.catalog_sync_handler import reconcile_catalog_stores
    try:
        await reconcile_catalog_stores()
    except Exception:
        logger.exception("Catalogue-store reconcile failed")

    # Pre-warm LaunchBox index in background (takes ~35s, avoids timeout on first search)
    from handler.metadata import launchbox_handler as _lb
    _lb_task = asyncio.create_task(_lb._ensure_index())

    def _lb_done(t: asyncio.Task) -> None:
        # Without this the only trace of a failed pre-warm is asyncio's own
        # "Task exception was never retrieved", which names neither LaunchBox
        # nor what it means for the app. Scraping still works from whatever
        # index is already on disk, so this is a warning, not an error.
        exc = t.exception() if not t.cancelled() else None
        if exc is not None:
            logger.warning(
                "LaunchBox index pre-warm failed (%s); scraping continues from "
                "the index already on disk, which will not refresh until this "
                "succeeds", exc,
            )
    _lb_task.add_done_callback(_lb_done)

    # One-shot: flag animated covers saved before the cover_animated column existed
    from utils.images import backfill_cover_animated as _cover_backfill
    asyncio.create_task(_cover_backfill())

    # ClamAV scheduled auto-update loop (sleeps 90 s before first check)
    from handler.clamav import clamav_handler as _clamav
    _clamav_task = asyncio.create_task(_clamav.auto_update_loop())

    # Security report scheduled loop (checks every hour)
    from handler.email.security_report import report_loop as _report_loop
    _report_task = asyncio.create_task(_report_loop())

    # Recently-added email newsletter loop (checks every few minutes for the slot)
    from handler.notifications.digest import digest_loop as _digest_loop
    _digest_task = asyncio.create_task(_digest_loop())

    # Torrent monitors
    from handler.torrent.seed_monitor import seed_monitor_loop, download_monitor_loop
    _seed_task     = asyncio.create_task(seed_monitor_loop())
    _dl_mon_task   = asyncio.create_task(download_monitor_loop())

    # Dashboard live-queue push (Socket.IO). No-op while no admin is watching.
    from handler.dashboard.queue_broadcaster import queue_broadcaster_loop
    _queue_task    = asyncio.create_task(queue_broadcaster_loop())

    # One-shot: re-align file availability and the GOG downloaded flag with what
    # is on disk, in case a crash landed between the files and the bookkeeping.
    from handler.library.reconcile import reconcile_loop as _reconcile_loop
    _reconcile_task = asyncio.create_task(_reconcile_loop())

    yield

    # Shutdown
    _clamav_task.cancel()
    _report_task.cancel()
    _digest_task.cancel()
    _seed_task.cancel()
    _dl_mon_task.cancel()
    _queue_task.cancel()
    _reconcile_task.cancel()
    plugin_manager.hook.lifecycle_on_shutdown()
    await close_client()
    logger.info("GamesDownloaderV3 shut down.")


app = FastAPI(
    title="GamesDownloader API",
    version=GD_VERSION,
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

# CORS - dynamic: reads allowed origins from config on every cross-origin
# preflight/request (requests without an Origin header skip the read).
# Changes via Settings -> Security take effect immediately (no restart needed).
class DynamicCORSMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        origin = request.headers.get("origin", "")

        # No Origin header -> not a cross-origin request. The logic below never
        # adds a CORS header without an origin, so skip the per-request config
        # read entirely for the common case (same-origin GET navigations and
        # non-browser API clients). Cross-origin requests still read fresh, so
        # Settings -> Security CORS changes keep taking effect immediately.
        if not origin:
            return await call_next(request)

        from handler.config.config_handler import config_handler as _cfg
        raw = (await _cfg.get("cors_origins")) or ""
        origins = [o.strip() for o in raw.split(",") if o.strip()] or (["*"] if DEBUG else [])

        # Handle CORS preflight
        if request.method == "OPTIONS":
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

# ETag - turns matching `If-None-Match` GETs into 304 Not Modified, so the
# blanket cache-control of `max-age=0, must-revalidate` does not waste
# bandwidth on unchanged list payloads. Wraps Auth so 401 responses skip it.
app.add_middleware(ETagMiddleware)

# ── Setup guard - redirect to setup when not yet configured ───────────────────


# Setup completes exactly once and never reverts. Once we have confirmed it from
# the DB, cache that positive result process-wide so the guard stops issuing a
# DB read on every request for the rest of the process lifetime. With a single
# uvicorn worker this cache is global and always correct; a transient DB error
# stays fail-open for that one request but is never cached.
_setup_guard_complete = False


class SetupGuardMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        path = request.url.path
        allowed_prefixes = ("/api/setup", "/api/health", "/api/auth/sso", "/assets", "/resources", "/_vite", "/favicon")
        if any(path.startswith(p) for p in allowed_prefixes) or path in ("/", "/setup"):
            return await call_next(request)
        global _setup_guard_complete
        if not _setup_guard_complete:
            from handler.config.config_handler import config_handler
            try:
                complete = await config_handler.is_setup_complete()
            except Exception:
                complete = True  # Don't block if DB not ready (do not cache a fail-open)
            else:
                if complete:
                    _setup_guard_complete = True
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
from endpoints.library.libraries_router import router as libraries_router
from endpoints.library.collections_router import router as collections_router
from endpoints.library.home_router import router as home_router

app.include_router(library_router, prefix="/api")
app.include_router(upload_router,  prefix="/api")
app.include_router(libraries_router)
app.include_router(collections_router)
app.include_router(home_router)

# ── Settings ──────────────────────────────────────────────────────────────────
from endpoints.settings.settings_router import settings_router
from endpoints.settings.clamav_router import clamav_router
from endpoints.settings.network_router import network_router
from endpoints.settings.sessions_router import router as sessions_router
from endpoints.settings.email_router import router as email_router
from endpoints.settings.download_tokens_router import router as download_tokens_router
from endpoints.settings.speed_limit_router import router as speed_limit_router
from endpoints.settings.download_limits_router import router as download_limits_router
from endpoints.settings.packaging_router import router as packaging_router
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
app.include_router(download_limits_router)
app.include_router(packaging_router)
app.include_router(security_report_router)
app.include_router(sso_settings_router)
app.include_router(plugins_router)
app.include_router(metadata_backup_router)
app.include_router(sso_router)
app.include_router(dl_router)
app.include_router(transmission_router)
app.include_router(torrent_router)

# ── Media proxy (scraper thumbnails, credential-free) ─────────────────────────
from endpoints.media_proxy_router import router as media_proxy_router  # noqa: E402

app.include_router(media_proxy_router)

# ── Game Requests ─────────────────────────────────────────────────────────────
from endpoints.requests.requests_router import requests_router

app.include_router(requests_router)

# ── ROM / Emulation ───────────────────────────────────────────────────────────
from endpoints.roms.roms_router import router as roms_router                         # noqa: E402
from endpoints.roms.savestate_router import router as savestate_router               # noqa: E402
from endpoints.roms.rom_sources_router import router as rom_sources_router           # noqa: E402
from endpoints.settings.roms_settings_router import router as roms_settings_router  # noqa: E402

app.include_router(roms_router)
app.include_router(savestate_router)
app.include_router(rom_sources_router)
app.include_router(roms_settings_router)

# ── Global search (Home navbar) ───────────────────────────────────────────────
from endpoints.search_router import router as search_router  # noqa: E402

app.include_router(search_router)

# ── Dashboard (role-aware admin/user overview; also exposed as __GD__.dashboard) ─
from endpoints.dashboard.dashboard_router import router as dashboard_router  # noqa: E402

app.include_router(dashboard_router)

# ── WebSocket / Socket.IO ─────────────────────────────────────────────────────
# socketio.ASGIApp wraps the FastAPI app so Socket.IO WS connections are handled
# before regular HTTP traffic is forwarded to FastAPI.
# NOTE: uvicorn/gunicorn must point to `main:app` - we rebind `app` below so
# that the exported symbol is the Socket.IO ASGI wrapper, not the bare FastAPI app.
socket_app = socketio.ASGIApp(sio, app)

# ── Health check ──────────────────────────────────────────────────────────────
@app.get("/api/health", tags=["system"])
async def health_check() -> dict:
    return {"status": "ok", "version": GD_VERSION}


# ── Static: serve /resources/ ─────────────────────────────────────────────────
# This mount has no authentication - it is the app's public media (covers, logos,
# screenshots). Save data must never be reachable through it. Saves normally live
# outside RESOURCES_PATH entirely, but an install whose compose has no volume for
# the new directory keeps them here, so the mount refuses their paths itself
# rather than trusting that they moved.
class _ResourcesStatic(StaticFiles):
    async def get_response(self, path: str, scope):
        if is_save_path(path):
            raise HTTPException(status_code=404, detail="Not found")
        response = await super().get_response(path, scope)
        # Public media (covers, logos, art). Let the browser reuse them within a
        # short window instead of firing a conditional GET per navigation; the
        # ETag / Last-Modified StaticFiles already sends still forces a
        # revalidation afterwards, and content-changing updates use ?v= cache
        # busters, so this bounded staleness is safe.
        response.headers.setdefault("Cache-Control", "public, max-age=600")
        return response


os.makedirs(RESOURCES_PATH, exist_ok=True)
app.mount("/resources", _ResourcesStatic(directory=RESOURCES_PATH), name="resources")

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
