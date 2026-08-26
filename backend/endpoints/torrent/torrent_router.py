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
from utils.uploads import read_upload_capped
from handler.auth.scopes import Scope
from handler.config.config_handler import config_handler
from handler.torrent.transmission_handler import transmission_handler

logger = logging.getLogger(__name__)

torrent_router = APIRouter(prefix="/api/torrents", tags=["torrents"])

_TORRENT_DIR = "/data/downloads/torrents"
_MAX_TORRENT_BYTES = 10 * 1024 * 1024   # a .torrent is metadata, not the payload
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
        "library":         td.library,
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
    # Optional target library slug; NULL / "games" => built-in Games library.
    library: str | None = None


@protected_route(torrent_router.post, "/download/url", scopes=[Scope.LIBRARY_ADMIN])
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
        library=body.library,
    )
    return _fmt_download(td)


@protected_route(torrent_router.post, "/download/file", scopes=[Scope.LIBRARY_ADMIN])
async def add_torrent_file(
    request: Request,
    title:   str = Form(...),
    target_os: str = Form("windows"),
    library: str = Form(None),
    file:    UploadFile = File(...),
) -> dict:
    """Upload a .torrent file and add it to Transmission."""
    os.makedirs(_SEED_DIR, exist_ok=True)
    safe_name = Path(file.filename or "upload.torrent").name  # strip path traversal
    tmp_path = os.path.join(_SEED_DIR, f"upload_{safe_name}")
    content = await read_upload_capped(file, _MAX_TORRENT_BYTES, what="Torrent file")
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
        library=library,
    )
    return _fmt_download(td)


async def _create_torrent_download(request, title, os_name, download_dir, *, transmission_id, info_hash, library=None):
    from handler.database.session import async_session_factory
    from models.torrent_download import TorrentDownload
    username = request.state.user.username if request.state.user else "admin"
    target_lib = (library or "").strip() or None
    if target_lib == "games":
        target_lib = None  # built-in Games library is the default (CUSTOM)
    async with async_session_factory() as db:
        td = TorrentDownload(
            title=title,
            os=os_name,
            download_dir=download_dir,
            transmission_id=transmission_id,
            info_hash=info_hash,
            status="downloading",
            created_by=username,
            library=target_lib,
        )
        db.add(td)
        await db.commit()
        await db.refresh(td)
    return td


# ── Admin: list / manage downloads ───────────────────────────────────────────

@protected_route(torrent_router.get, "/downloads", scopes=[Scope.LIBRARY_ADMIN])
async def list_downloads(request: Request) -> list:
    from handler.database.session import async_session_factory
    from models.torrent_download import TorrentDownload
    from sqlalchemy import select
    async with async_session_factory() as db:
        rows = (await db.execute(
            select(TorrentDownload).order_by(TorrentDownload.id.desc())
        )).scalars().all()
    return [_fmt_download(r) for r in rows]


@protected_route(torrent_router.get, "/downloads/{dl_id}", scopes=[Scope.LIBRARY_ADMIN])
async def get_download(request: Request, dl_id: int) -> dict:
    from handler.database.session import async_session_factory
    from models.torrent_download import TorrentDownload
    async with async_session_factory() as db:
        td = await db.get(TorrentDownload, dl_id)
    if not td:
        raise HTTPException(404, "Download not found")
    return _fmt_download(td)


@protected_route(torrent_router.delete, "/downloads/{dl_id}", scopes=[Scope.LIBRARY_ADMIN])
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


# ── Controlling a download in flight ─────────────────────────────────────────
# Transmission has always been able to do these - the client wrapper had the
# calls - but nothing exposed them, so pausing a 60 GB torrent meant either
# cancelling it outright and starting again, or opening Transmission's own web
# interface on a port that is now deliberately shut.

async def _download_or_404(dl_id: int):
    from handler.database.session import async_session_factory
    from models.torrent_download import TorrentDownload
    async with async_session_factory() as db:
        td = await db.get(TorrentDownload, dl_id)
    if not td:
        raise HTTPException(404, "Download not found")
    if not td.transmission_id:
        raise HTTPException(409, "This download has not reached Transmission yet")
    return td


async def _set_download_status(dl_id: int, status: str) -> None:
    from handler.database.session import async_session_factory
    from models.torrent_download import TorrentDownload
    from sqlalchemy import update
    async with async_session_factory() as db:
        await db.execute(
            update(TorrentDownload).where(TorrentDownload.id == dl_id).values(status=status)
        )
        await db.commit()


@protected_route(torrent_router.post, "/downloads/{dl_id}/pause", scopes=[Scope.LIBRARY_ADMIN])
async def pause_download(request: Request, dl_id: int) -> dict:
    """Stop fetching. What has arrived stays on disk and resume carries on."""
    td = await _download_or_404(dl_id)
    ok = await transmission_handler.pause_torrent(td.transmission_id)
    if not ok:
        raise HTTPException(502, "Transmission refused to pause this torrent")
    await _set_download_status(dl_id, "paused")
    return {"ok": True, "status": "paused"}


@protected_route(torrent_router.post, "/downloads/{dl_id}/resume", scopes=[Scope.LIBRARY_ADMIN])
async def resume_download(request: Request, dl_id: int) -> dict:
    td = await _download_or_404(dl_id)
    ok = await transmission_handler.resume_torrent(td.transmission_id)
    if not ok:
        raise HTTPException(502, "Transmission refused to resume this torrent")
    await _set_download_status(dl_id, "downloading")
    return {"ok": True, "status": "downloading"}


@protected_route(torrent_router.post, "/downloads/{dl_id}/verify", scopes=[Scope.LIBRARY_ADMIN])
async def verify_download(request: Request, dl_id: int) -> dict:
    """Re-check what is on disk against the torrent, piece by piece.

    The answer to a transfer that stalled or came back looking wrong: it finds
    the bad pieces and fetches those again instead of the whole thing.
    Transmission stops the torrent while it reads, so a large one goes quiet
    for a while and then carries on.

    Only while the download is still in progress. Once it completes, its files
    are MOVED out of the download directory and into the library, so
    Transmission would find nothing there, decide every piece was missing, and
    start the entire torrent again. A finished game that will not install is a
    job for the library, not for this button.
    """
    td = await _download_or_404(dl_id)
    if td.status not in ("downloading", "paused"):
        raise HTTPException(
            409,
            "This download has already finished and its files have moved into "
            "the library, so there is nothing here left to check.",
        )
    ok = await transmission_handler.verify_torrent(td.transmission_id)
    if not ok:
        raise HTTPException(502, "Transmission refused to verify this torrent")
    return {"ok": True, "status": "verifying"}


class TorrentFilesBody(BaseModel):
    wanted:   list[int] = []
    unwanted: list[int] = []


@protected_route(torrent_router.get, "/downloads/{dl_id}/files", scopes=[Scope.LIBRARY_ADMIN])
async def list_download_files(request: Request, dl_id: int) -> list:
    """What is inside the torrent, and which parts are being fetched."""
    td = await _download_or_404(dl_id)
    return await transmission_handler.get_files(td.transmission_id)


@protected_route(torrent_router.put, "/downloads/{dl_id}/files", scopes=[Scope.LIBRARY_ADMIN])
async def choose_download_files(request: Request, dl_id: int, body: TorrentFilesBody) -> dict:
    """Pick which files to fetch from a torrent that holds more than one game.

    Deselecting everything is refused rather than obeyed: Transmission would
    accept it and sit at zero per cent for ever, which looks exactly like a
    torrent with no seeds.
    """
    td = await _download_or_404(dl_id)
    files = await transmission_handler.get_files(td.transmission_id)
    if not files:
        raise HTTPException(409, "Transmission does not know this torrent's contents yet")

    valid = {f["index"] for f in files}
    wanted   = [i for i in body.wanted if i in valid]
    unwanted = [i for i in body.unwanted if i in valid]
    if len(unwanted) >= len(valid) and not wanted:
        raise HTTPException(400, "At least one file has to be selected")

    ok = await transmission_handler.set_files_wanted(td.transmission_id, wanted, unwanted)
    if not ok:
        raise HTTPException(502, "Transmission refused the file selection")
    return {"ok": True, "files": await transmission_handler.get_files(td.transmission_id)}


# ── Everything the daemon holds ──────────────────────────────────────────────
# The two views above only know what this application put there. Transmission
# also holds the seeds, and anything added by hand before the control port was
# shut. Without this the daemon's own interface is still the only way to see it.

@protected_route(torrent_router.get, "/all", scopes=[Scope.LIBRARY_ADMIN])
async def list_all_torrents(request: Request) -> list:
    """Every torrent Transmission is holding, ours or not."""
    from handler.torrent.transmission_handler import STATUS
    torrents = await transmission_handler.get_all_torrents(label="")
    out = []
    for t in torrents:
        total = t.get("totalSize") or 0
        out.append({
            "id":          t.get("id"),
            "name":        t.get("name") or "",
            "status":      STATUS.get(t.get("status", 0), "unknown"),
            "percent":     round(float(t.get("percentDone") or 0) * 1000) / 10,
            "total_size":  total,
            "downloaded":  t.get("downloadedEver") or 0,
            "uploaded":    t.get("uploadedEver") or 0,
            "ratio":       round(float(t.get("uploadRatio") or 0), 2),
            "rate_down":   t.get("rateDownload") or 0,
            "rate_up":     t.get("rateUpload") or 0,
            "peers":       t.get("peersConnected") or 0,
            "peers_from":  t.get("peersSendingToUs") or 0,
            "peers_to":    t.get("peersGettingFromUs") or 0,
            "eta":         t.get("eta", -1),
            "queue":       t.get("queuePosition", 0),
            "stalled":     bool(t.get("isStalled")),
            "error":       t.get("errorString") or "",
            # Ours carry the application's label; anything else was added by
            # hand and is worth saying so, because removing it is not something
            # this application can undo.
            "ours":        bool(t.get("labels")),
            "added_at":    t.get("addedDate") or 0,
            "download_dir": t.get("downloadDir") or "",
        })
    out.sort(key=lambda r: (r["queue"], r["name"].lower()))
    return out


@protected_route(torrent_router.get, "/stats", scopes=[Scope.LIBRARY_ADMIN])
async def torrent_stats(request: Request) -> dict:
    """Session and lifetime totals, straight from the daemon."""
    raw = await transmission_handler.get_stats()
    if not raw:
        raise HTTPException(502, "Transmission did not answer")

    def _blok(d: dict) -> dict:
        return {
            "downloaded": d.get("downloadedBytes", 0),
            "uploaded":   d.get("uploadedBytes", 0),
            "files_added": d.get("filesAdded", 0),
            "seconds":    d.get("secondsActive", 0),
            "sessions":   d.get("sessionCount", 0),
        }

    return {
        "torrents":        raw.get("torrentCount", 0),
        "active":          raw.get("activeTorrentCount", 0),
        "paused":          raw.get("pausedTorrentCount", 0),
        "rate_down":       raw.get("downloadSpeed", 0),
        "rate_up":         raw.get("uploadSpeed", 0),
        "current":         _blok(raw.get("current-stats") or {}),
        "cumulative":      _blok(raw.get("cumulative-stats") or {}),
    }


class TorrentActionBody(BaseModel):
    # Per-torrent overrides, all optional. Transmission's own names and units.
    download_limit:    int | None = None      # KB/s, needs the flag below
    download_limited:  bool | None = None
    upload_limit:      int | None = None
    upload_limited:    bool | None = None
    seed_ratio_limit:  float | None = None
    seed_ratio_mode:   int | None = None      # 0 global, 1 own, 2 unlimited
    peer_limit:        int | None = None


@protected_route(torrent_router.post, "/all/{tid}/{action}", scopes=[Scope.LIBRARY_ADMIN])
async def act_on_torrent(request: Request, tid: int, action: str) -> dict:
    """pause | resume | verify | top | up | down | bottom

    By Transmission's own id rather than by a row of ours, because the point of
    this view is the torrents we have no row for.
    """
    if action in ("pause", "resume", "verify"):
        fn = {
            "pause":  transmission_handler.pause_torrent,
            "resume": transmission_handler.resume_torrent,
            "verify": transmission_handler.verify_torrent,
        }[action]
        if not await fn(tid):
            raise HTTPException(502, f"Transmission refused to {action} this torrent")
        return {"ok": True}

    if action in ("top", "up", "down", "bottom"):
        if not await transmission_handler.move_in_queue(tid, action):
            raise HTTPException(502, "Transmission refused to reorder this torrent")
        return {"ok": True}

    raise HTTPException(400, f"Unknown action: {action}")


@protected_route(torrent_router.put, "/all/{tid}/limits", scopes=[Scope.LIBRARY_ADMIN])
async def set_torrent_limits(request: Request, tid: int, body: TorrentActionBody) -> dict:
    """Caps for one torrent, overriding the session-wide ones."""
    mapa = {
        "download_limit":   "downloadLimit",
        "download_limited": "downloadLimited",
        "upload_limit":     "uploadLimit",
        "upload_limited":   "uploadLimited",
        "seed_ratio_limit": "seedRatioLimit",
        "seed_ratio_mode":  "seedRatioMode",
        "peer_limit":       "peer-limit",
    }
    values = {mapa[k]: v for k, v in body.model_dump().items() if v is not None}
    if not values:
        raise HTTPException(400, "Nothing to set")
    if not await transmission_handler.set_torrent_limits(tid, values):
        raise HTTPException(502, "Transmission refused those limits")
    return {"ok": True}


@protected_route(torrent_router.delete, "/all/{tid}", scopes=[Scope.LIBRARY_ADMIN])
async def remove_torrent(request: Request, tid: int, delete_data: bool = False) -> dict:
    """Drop a torrent from Transmission.

    `delete_data` also removes what it downloaded, which for a seed means the
    library file it was sharing. Off unless asked for, and the interface asks
    twice.
    """
    if not await transmission_handler.remove_torrent(tid, delete_data=delete_data):
        raise HTTPException(502, "Transmission refused to remove this torrent")
    return {"ok": True, "deleted_data": delete_data}


@protected_route(torrent_router.get, "/seeds", scopes=[Scope.LIBRARY_ADMIN])
async def list_seeds(request: Request) -> list:
    """What this server is sharing, with live figures from the daemon."""
    from handler.database.session import async_session_factory
    from models.library_torrent import LibraryTorrent
    from models.library_file import LibraryFile
    from sqlalchemy import select

    async with async_session_factory() as db:
        rows = (await db.execute(
            select(LibraryTorrent).order_by(LibraryTorrent.id.desc())
        )).scalars().all()
        nazwy: dict[int, str] = {}
        ids = [r.file_id for r in rows if r.file_id]
        if ids:
            for f in (await db.execute(
                select(LibraryFile).where(LibraryFile.id.in_(ids))
            )).scalars().all():
                nazwy[f.id] = f.display_name or f.filename

    live = {t.get("id"): t for t in await transmission_handler.get_all_torrents(label="")}
    out = []
    for r in rows:
        t = live.get(r.transmission_id) or {}
        out.append({
            "id":              r.id,
            "transmission_id": r.transmission_id,
            "filename":        nazwy.get(r.file_id, "") or (r.torrent_path or "").split("/")[-1],
            "status":          r.status,
            "file_size":       r.file_size or 0,
            "created_by":      r.created_by,
            "uploaded":        t.get("uploadedEver") or 0,
            "ratio":           round(float(t.get("uploadRatio") or 0), 2),
            "rate_up":         t.get("rateUpload") or 0,
            "peers_to":        t.get("peersGettingFromUs") or 0,
            # A row whose torrent is gone from the daemon can still say seeding.
            "live":            r.transmission_id in live,
        })
    return out


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
    import tempfile
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
        # Multiple files - stage with symlinks in a temp tree that MIRRORS the
        # on-disk layout, so the generated torrent preserves subdirectories
        # (e.g. gra/DATA/file03.bin) instead of flattening every file into one
        # folder. Using os.path.basename() used to drop the subdirectory and
        # collapse the whole game into a flat root.
        #
        # The staging root is named after the files' common ancestor directory
        # so the torrent's top-level folder matches the data on disk; that also
        # lets Transmission seed the existing files without re-hashing, because
        # it can find <seed_dir>/<root_name>/... exactly where the torrent says.
        common = os.path.commonpath(abs_paths)
        if not os.path.isdir(common):
            common = os.path.dirname(common)
        root_name = os.path.basename(common) or game_slug
        staging_parent = tempfile.mkdtemp(prefix="seed_", dir=_SEED_DIR)
        root_dir = os.path.join(staging_parent, root_name)
        os.makedirs(root_dir, exist_ok=True)
        try:
            for ap in abs_paths:
                rel = os.path.relpath(ap, common)
                link = os.path.join(root_dir, rel)
                if os.path.lexists(link):
                    continue  # identical path listed twice - skip duplicate
                os.makedirs(os.path.dirname(link), exist_ok=True)
                os.symlink(ap, link)
            try:
                torrent_path = await create_torrent(root_dir, _SEED_DIR)
            except RuntimeError as exc:
                logger.error("Torrent creation failed for game %d: %s", game_id, exc)
                raise HTTPException(500, f"Torrent creation failed: {exc}")
        finally:
            shutil.rmtree(staging_parent, ignore_errors=True)
        # Transmission must find <seed_dir>/<root_name>/... on disk to seed the
        # already-present data, so point it at the common ancestor's parent.
        seed_dir = os.path.dirname(common)

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
