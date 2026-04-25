"""Torrent endpoints.

Admin endpoints (Scope.LIBRARY_UPLOAD):
  POST /api/torrents/download        - add torrent to server (magnet/url/file)
  GET  /api/torrents/downloads       - list all admin download jobs
  GET  /api/torrents/downloads/{id}  - single download job
  DELETE /api/torrents/downloads/{id} - cancel + remove

User endpoints (authenticated):
  POST /api/torrents/seed/game/{game_id} - generate .torrent for ALL files in a game
  POST /api/torrents/seed/{file_id}      - generate .torrent for a single library file
  GET  /api/torrents/seed/{file_id}/status - check seed status

Shared:
  GET  /api/torrents/status          - Transmission availability
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
import re
import unicodedata

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from config import BASE_PATH
from decorators.auth import protected_route
from handler.auth.scopes import Scope
from handler.config.config_handler import config_handler
from handler.torrent.transmission_handler import transmission_handler

logger = logging.getLogger(__name__)

torrent_router = APIRouter(prefix="/api/torrents", tags=["torrents"])

_TORRENT_DIR = "/data/downloads/torrents"
_SEED_DIR    = "/data/config/torrents"     # generated .torrent files for seeding


# ── Helpers ───────────────────────────────────────────────────────────────────

def _slugify(title: str) -> str:
    t = unicodedata.normalize("NFKD", title).lower()
    t = t.encode("ascii", errors="ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-") or "game"


def _fmt_download(td) -> dict:
    return {
        "id":              td.id,
        "title":           td.title,
        "os":              td.os,
        "status":          td.status,
        "percent":         round(td.percent_done * 100, 1),
        "total_size":      td.total_size,
        "rate_download":   td.rate_download,
        "eta":             td.eta,
        "error_msg":       td.error_msg,
        "game_id":         td.game_id,
        "created_by":      td.created_by,
        "created_at":      td.created_at.isoformat() if td.created_at else None,
        "completed_at":    td.completed_at.isoformat() if td.completed_at else None,
    }


# ── Transmission status ───────────────────────────────────────────────────────

@protected_route(torrent_router.get, "/enabled", scopes=[Scope.LIBRARY_READ])
async def torrent_enabled(request: Request) -> dict:
    """Return whether Transmission is enabled in settings (config flag, not live check)."""
    import json as _json
    # Primary: dedicated bool key (set on every settings save)
    enabled = await config_handler.get_bool("transmission_enabled", default=False)
    if not enabled:
        # Fallback: read from full settings JSON (covers configs saved before the key existed)
        raw = await config_handler.get("transmission_settings")
        if raw:
            try:
                enabled = bool(_json.loads(raw).get("enabled", False))
            except Exception:
                pass
    return {"enabled": enabled}


@protected_route(torrent_router.get, "/status", scopes=[Scope.LIBRARY_READ])
async def torrent_status(request: Request) -> dict:
    available = await transmission_handler.is_available()
    stats     = await transmission_handler.get_stats() if available else None
    return {"available": available, "engine": "transmission", "stats": stats}


# ── Admin: add download to server ─────────────────────────────────────────────

class AddTorrentByUrl(BaseModel):
    url:   str
    title: str
    os:    str = "windows"


@protected_route(torrent_router.post, "/download/url", scopes=[Scope.LIBRARY_UPLOAD])
async def add_torrent_url(request: Request, body: AddTorrentByUrl) -> dict:
    """Add torrent by magnet link or .torrent URL."""
    slug = _slugify(body.title)
    download_dir = os.path.join(_TORRENT_DIR, slug)
    os.makedirs(download_dir, exist_ok=True)

    info = await transmission_handler.add_torrent_url(body.url, download_dir)
    if not info:
        raise HTTPException(502, "Transmission rejected the torrent")

    td = await _create_torrent_download(
        request, body.title, body.os, download_dir,
        transmission_id=info.get("id"),
        info_hash=info.get("hashString"),
    )
    return _fmt_download(td)


@protected_route(torrent_router.post, "/download/file", scopes=[Scope.LIBRARY_UPLOAD])
async def add_torrent_file(
    request: Request,
    title:   str = Form(...),
    target_os: str = Form("windows"),
    file:    UploadFile = File(...),
) -> dict:
    """Upload a .torrent file and add it to Transmission."""
    os.makedirs(_SEED_DIR, exist_ok=True)
    safe_name = Path(file.filename or "upload.torrent").name  # strip path traversal
    tmp_path = os.path.join(_SEED_DIR, f"upload_{safe_name}")
    content = await file.read()
    if len(content) > 10 * 1024 * 1024:  # 10 MB limit for .torrent files
        raise HTTPException(status_code=413, detail="Torrent file too large (max 10 MB)")
    with open(tmp_path, "wb") as f:
        f.write(content)

    slug = _slugify(title)
    download_dir = os.path.join(_TORRENT_DIR, slug)
    os.makedirs(download_dir, exist_ok=True)

    info = await transmission_handler.add_torrent_file(tmp_path, download_dir)
    try:
        os.remove(tmp_path)
    except OSError:
        pass
    if not info:
        raise HTTPException(502, "Transmission rejected the torrent")

    td = await _create_torrent_download(
        request, title, target_os, download_dir,
        transmission_id=info.get("id"),
        info_hash=info.get("hashString"),
    )
    return _fmt_download(td)


async def _create_torrent_download(request, title, os_name, download_dir, *, transmission_id, info_hash):
    from handler.database.session import async_session_factory
    from models.torrent_download import TorrentDownload
    username = request.state.user.username if request.state.user else "admin"
    async with async_session_factory() as db:
        td = TorrentDownload(
            title=title,
            os=os_name,
            download_dir=download_dir,
            transmission_id=transmission_id,
            info_hash=info_hash,
            status="downloading",
            created_by=username,
        )
        db.add(td)
        await db.commit()
        await db.refresh(td)
    return td


# ── Admin: list / manage downloads ───────────────────────────────────────────

@protected_route(torrent_router.get, "/downloads", scopes=[Scope.LIBRARY_UPLOAD])
async def list_downloads(request: Request) -> list:
    from handler.database.session import async_session_factory
    from models.torrent_download import TorrentDownload
    from sqlalchemy import select
    async with async_session_factory() as db:
        rows = (await db.execute(
            select(TorrentDownload).order_by(TorrentDownload.id.desc())
        )).scalars().all()
    return [_fmt_download(r) for r in rows]


@protected_route(torrent_router.get, "/downloads/{dl_id}", scopes=[Scope.LIBRARY_UPLOAD])
async def get_download(request: Request, dl_id: int) -> dict:
    from handler.database.session import async_session_factory
    from models.torrent_download import TorrentDownload
    async with async_session_factory() as db:
        td = await db.get(TorrentDownload, dl_id)
    if not td:
        raise HTTPException(404, "Download not found")
    return _fmt_download(td)


@protected_route(torrent_router.delete, "/downloads/{dl_id}", scopes=[Scope.LIBRARY_UPLOAD])
async def cancel_download(request: Request, dl_id: int) -> dict:
    from handler.database.session import async_session_factory
    from models.torrent_download import TorrentDownload
    from sqlalchemy import update
    async with async_session_factory() as db:
        td = await db.get(TorrentDownload, dl_id)
        if not td:
            raise HTTPException(404, "Download not found")
        if td.transmission_id:
            await transmission_handler.remove_torrent(td.transmission_id, delete_data=False)
        await db.execute(
            update(TorrentDownload).where(TorrentDownload.id == dl_id).values(status="removed")
        )
        await db.commit()
    return {"ok": True}


# ── User: generate seed .torrent for an entire game (all files) ───────────────

class SeedGameBody(BaseModel):
    file_ids: list[int] = []   # empty = all available files


@protected_route(torrent_router.post, "/seed/game/{game_id}", scopes=[Scope.LIBRARY_DOWNLOAD])
async def generate_game_torrent(request: Request, game_id: int, body: SeedGameBody):
    """Generate a single .torrent for selected files (or all if none specified).

    Files are staged in a temp directory so multi-directory selections work
    regardless of where each file lives on disk.
    """
    import shutil
    from handler.database.session import async_session_factory
    from handler.torrent.torrent_generator import create_torrent
    from models.library_file import LibraryFile
    from models.library_game import LibraryGame
    from sqlalchemy import select

    async with async_session_factory() as db:
        game = await db.get(LibraryGame, game_id)
        if not game:
            raise HTTPException(404, "Game not found")
        rows = (await db.execute(
            select(LibraryFile).where(
                LibraryFile.library_game_id == game_id,
                LibraryFile.is_available == True,  # noqa: E712
            )
        )).scalars().all()

    # Filter to requested selection (empty body = all)
    files = [f for f in rows if f.id in body.file_ids] if body.file_ids else list(rows)
    if not files:
        raise HTTPException(404, "No matching files for this game")

    abs_paths = [p for p in (os.path.join(BASE_PATH, f.file_path) for f in files) if os.path.exists(p)]
    if not abs_paths:
        raise HTTPException(404, "No files found on disk")

    game_slug = _slugify(game.title)
    os.makedirs(_SEED_DIR, exist_ok=True)

    if len(abs_paths) == 1:
        # Single file - no staging needed
        try:
            torrent_path = await create_torrent(abs_paths[0], _SEED_DIR)
        except RuntimeError as exc:
            logger.error("Torrent creation failed for game %d: %s", game_id, exc)
            raise HTTPException(500, f"Torrent creation failed: {exc}")
        seed_dir = os.path.dirname(abs_paths[0])
    else:
        # Multiple files - stage with symlinks so they share one directory.
        # The directory name becomes the root folder name inside the torrent.
        staging = os.path.join(_SEED_DIR, game_slug)
        os.makedirs(staging, exist_ok=True)
        try:
            seen: set[str] = set()
            for ap in abs_paths:
                name = os.path.basename(ap)
                # Avoid name collisions in staging dir
                if name in seen:
                    base, ext = os.path.splitext(name)
                    name = f"{base}_{len(seen)}{ext}"
                seen.add(name)
                os.symlink(ap, os.path.join(staging, name))
            try:
                torrent_path = await create_torrent(staging, _SEED_DIR)
            except RuntimeError as exc:
                logger.error("Torrent creation failed for game %d: %s", game_id, exc)
                raise HTTPException(500, f"Torrent creation failed: {exc}")
        finally:
            shutil.rmtree(staging, ignore_errors=True)
        seed_dir = os.path.commonpath(abs_paths)
        if not os.path.isdir(seed_dir):
            seed_dir = os.path.dirname(seed_dir)

    await transmission_handler.add_torrent_file(torrent_path, seed_dir)

    return FileResponse(
        torrent_path,
        media_type="application/x-bittorrent",
        filename=f"{game_slug}.torrent",
    )


# ── User: generate seed .torrent for a library file ──────────────────────────

@protected_route(torrent_router.post, "/seed/{file_id}", scopes=[Scope.LIBRARY_DOWNLOAD])
async def generate_seed_torrent(request: Request, file_id: int):
    """Generate (or return existing active) .torrent for a library file.

    Returns the .torrent file as a download.
    """
    from handler.database.session import async_session_factory
    from handler.torrent.torrent_generator import create_torrent
    from models.library_file import LibraryFile
    from models.library_game import LibraryGame
    from models.library_torrent import LibraryTorrent
    from sqlalchemy import select

    # Load file record + game title for a friendly download filename
    async with async_session_factory() as db:
        lf = await db.get(LibraryFile, file_id)
        if not lf or not lf.is_available:
            raise HTTPException(404, "File not found")

        game = await db.get(LibraryGame, lf.library_game_id)
        game_slug = _slugify(game.title) if game else f"game-{file_id}"

        # Check for existing active seed
        existing = (await db.execute(
            select(LibraryTorrent)
            .where(LibraryTorrent.file_id == file_id, LibraryTorrent.status == "seeding")
            .order_by(LibraryTorrent.id.desc())
        )).scalar_one_or_none()

        if existing and existing.torrent_path and os.path.exists(existing.torrent_path):
            return FileResponse(
                existing.torrent_path,
                media_type="application/x-bittorrent",
                filename=f"{game_slug}.torrent",
            )

    # Generate new .torrent
    abs_path = os.path.join(BASE_PATH, lf.file_path)
    if not os.path.exists(abs_path):
        raise HTTPException(404, "Physical file not found on disk")

    os.makedirs(_SEED_DIR, exist_ok=True)

    try:
        torrent_path = await create_torrent(abs_path, _SEED_DIR)
    except RuntimeError as exc:
        logger.error("Failed to create torrent for file %d: %s", file_id, exc)
        raise HTTPException(500, f"Torrent creation failed: {exc}")

    # Add to Transmission for seeding (file already downloaded, just seed)
    file_dir = os.path.dirname(abs_path)
    info = await transmission_handler.add_torrent_file(torrent_path, file_dir)

    tr_id     = info.get("id")   if info else None
    info_hash = info.get("hashString") if info else None
    file_size = lf.size_bytes or (os.path.getsize(abs_path) if os.path.exists(abs_path) else None)
    username  = request.state.user.username if request.state.user else "unknown"

    async with async_session_factory() as db:
        lt = LibraryTorrent(
            file_id=file_id,
            transmission_id=tr_id,
            info_hash=info_hash,
            torrent_path=torrent_path,
            status="seeding",
            file_size=file_size,
            created_by=username,
        )
        db.add(lt)
        await db.commit()

    return FileResponse(
        torrent_path,
        media_type="application/x-bittorrent",
        filename=f"{game_slug}.torrent",
    )


@protected_route(torrent_router.get, "/seed/{file_id}/status", scopes=[Scope.LIBRARY_DOWNLOAD])
async def seed_status(request: Request, file_id: int) -> dict:
    """Return current seed status for a file."""
    from handler.database.session import async_session_factory
    from models.library_torrent import LibraryTorrent
    from sqlalchemy import select

    async with async_session_factory() as db:
        lt = (await db.execute(
            select(LibraryTorrent)
            .where(LibraryTorrent.file_id == file_id)
            .order_by(LibraryTorrent.id.desc())
        )).scalar_one_or_none()

    if not lt:
        return {"status": "none"}

    result: dict = {
        "status":     lt.status,
        "created_at": lt.created_at.isoformat() if lt.created_at else None,
    }

    if lt.status == "seeding" and lt.transmission_id:
        info = await transmission_handler.get_torrent(lt.transmission_id)
        if info:
            result["uploaded"]    = info.get("uploadedEver", 0)
            result["file_size"]   = lt.file_size
            result["upload_ratio"] = round(
                info.get("uploadedEver", 0) / max(lt.file_size or 1, 1), 4
            )

    return result
