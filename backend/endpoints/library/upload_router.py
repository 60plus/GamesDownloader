"""Library file upload endpoints - Admin/Uploader.

POST /library/games/{game_id}/upload
  - Accepts a single file (multipart/form-data)
  - os, file_type, language, version params
  - Saves to /data/games/CUSTOM/{slug}/{os}/
  - Creates LibraryFile record

POST /library/games/{game_id}/upload-url
  - Same destination and record, but the SERVER downloads the file from a
    direct http(s) link in the background; live progress goes out over
    socket.io: upload:url_progress / upload:url_complete / upload:url_error.
"""

from __future__ import annotations

import asyncio
import itertools
import logging
import os
import re
import time
import unicodedata
from pathlib import Path
from urllib.parse import unquote, urlparse

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel

from config import GAMES_PATH
from decorators.auth import protected_route
from handler.auth.scopes import Scope
from handler.database.library_handler import LibraryHandler
from models.library_file import LibraryFile

logger = logging.getLogger(__name__)

upload_router = APIRouter(prefix="/library", tags=["library"])
_lib = LibraryHandler()

_CHUNK_WRITE = 1024 * 256  # 256 KB write buffer


def _sanitize(title: str) -> str:
    t = unicodedata.normalize("NFKD", title)
    t = t.encode("ascii", errors="ignore").decode("ascii")
    t = re.sub(r'[<>:"/\\|?*]', "_", t)
    # Strip path traversal sequences
    t = re.sub(r'\.\.+', "_", t)
    return t.strip("./\\ ")


def _rel_from_abs(abs_path: str) -> str:
    from config import BASE_PATH
    return os.path.relpath(abs_path, BASE_PATH)


def _dest_dir_for(game_title: str, os_platform: str, file_type: str) -> Path:
    """Resolve (and create) the CUSTOM library folder for an upload."""
    folder_map = {
        "windows": "windows",
        "mac":     "mac",
        "linux":   "linux",
        "all":     ".",
    }
    sub = folder_map.get(os_platform, os_platform)
    if file_type in ("extra", "extras"):
        sub = "extra"
    elif file_type == "dlc":
        sub = "dlc"
    safe_title = _sanitize(game_title)
    if sub == ".":
        dest_dir = Path(GAMES_PATH) / "CUSTOM" / safe_title
    else:
        dest_dir = Path(GAMES_PATH) / "CUSTOM" / safe_title / sub
    dest_dir.mkdir(parents=True, exist_ok=True)
    return dest_dir


async def _max_upload_bytes() -> int:
    """Configurable upload size limit (default 50 GB)."""
    from handler.config.config_handler import config_handler as _cfg
    _raw_max = await _cfg.get("max_upload_bytes")
    try:
        return int(_raw_max) if _raw_max else 50 * 1024 ** 3
    except ValueError:
        return 50 * 1024 ** 3


class _VirusFound(Exception):
    def __init__(self, threat: str, action: str | None):
        super().__init__(f"virus detected: {threat}")
        self.threat = threat
        self.action = action


async def _finalize_upload(
    game_id: int,
    dest_path: Path,
    filename: str,
    size: int,
    os_platform: str,
    file_type: str,
    language: str | None,
    version: str | None,
    actor: str | None,
) -> dict:
    """Shared tail of every upload path: optional ClamAV check, duplicate
    guard and the LibraryFile record. Raises _VirusFound when ClamAV blocks
    the file (already quarantined/deleted by then).

    ClamAV is controlled by the `clamav_auto_scan_upload` admin setting (off
    by default). Only "FOUND" rejects the upload - scan errors fail open so a
    broken daemon does not block legitimate users."""
    try:
        from handler.clamav import clamav_handler as _clam
        if await _clam.is_upload_scanning_enabled():
            scan_res = await _clam.scan_file(str(dest_path))
            if scan_res.get("status") == "FOUND":
                threat = scan_res.get("threat") or "unknown"
                action_res = await _clam.quarantine_or_delete(
                    str(dest_path), threat, triggered_by=actor
                )
                logger.warning(
                    "ClamAV blocked upload '%s' (game=%d, threat=%s, action=%s)",
                    filename, game_id, threat, action_res.get("action"),
                )
                raise _VirusFound(threat, action_res.get("action"))
    except _VirusFound:
        raise
    except Exception:
        # Don't fail the upload because the scanner choked - log and continue.
        logger.exception("ClamAV scan check failed for %s; allowing upload", dest_path)

    rel = _rel_from_abs(str(dest_path))

    # Check for duplicate record
    existing_files = await _lib.get_files_for_game(game_id)
    if any(f.file_path == rel for f in existing_files):
        return {
            "ok": True,
            "file_path": rel,
            "size_bytes": size,
            "duplicate": True,
        }

    lib_file = LibraryFile(
        library_game_id=game_id,
        filename=filename,
        display_name=filename,
        file_type=file_type if file_type not in ("extras",) else "extra",
        os=os_platform,
        language=language,
        version=version,
        size_bytes=size,
        file_path=rel,
        source="custom",
        is_available=True,
    )
    created = await _lib.create_file(lib_file)
    logger.info("Uploaded '%s' (%d B) for game %d", filename, size, game_id)

    return {
        "ok":         True,
        "file_id":    created.id,
        "filename":   filename,
        "file_path":  rel,
        "size_bytes": size,
    }


@protected_route(upload_router.post, "/games/{game_id}/upload", scopes=[Scope.LIBRARY_UPLOAD])
async def upload_game_file(
    request: Request,
    game_id: int,
    file: UploadFile = File(...),
    os_platform: str  = Form("all",    alias="os"),
    file_type:   str  = Form("game"),
    language:    str  = Form(None),
    version:     str  = Form(None),
) -> dict:
    game = await _lib.get_by_id(game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    dest_dir = _dest_dir_for(game.title, os_platform, file_type)

    filename = Path(file.filename or "upload.bin").name
    # Reject filenames that contain traversal sequences after stripping the directory component
    if ".." in filename or filename.startswith(("/", "\\")):
        raise HTTPException(status_code=400, detail="Invalid filename")
    dest_path = dest_dir / filename

    max_bytes = await _max_upload_bytes()

    # Write file with size guard - abort and remove partial file if limit exceeded
    size = 0
    aborted = False
    try:
        with open(dest_path, "wb") as fh:
            while chunk := await file.read(_CHUNK_WRITE):
                fh.write(chunk)
                size += len(chunk)
                if size > max_bytes:
                    aborted = True
                    break
    finally:
        if aborted:
            dest_path.unlink(missing_ok=True)
            raise HTTPException(
                status_code=413,
                detail=f"File exceeds maximum allowed upload size "
                       f"({max_bytes // (1024 ** 3)} GB).",
            )

    actor = (request.state.user.username
             if getattr(request.state, "user", None) else None)
    try:
        return await _finalize_upload(
            game_id, dest_path, filename, size,
            os_platform, file_type, language, version, actor,
        )
    except _VirusFound as v:
        raise HTTPException(
            status_code=422,
            detail={
                "code":   "virus_detected",
                "threat": v.threat,
                "action": v.action,
            },
        )


# ── Upload from a direct URL (server-side background download) ───────────────

class UploadUrlBody(BaseModel):
    url: str
    os: str = "all"
    file_type: str = "game"
    language: str | None = None
    version: str | None = None


_url_job_seq = itertools.count(1)

_CD_FILENAME = re.compile(r'filename\*?=(?:UTF-8\'\')?["\']?([^"\';\r\n]+)', re.IGNORECASE)


def _safe_filename(raw: str, fallback: str = "download.bin") -> str:
    name = Path(unquote(raw or "")).name.strip()
    if not name or ".." in name or name.startswith(("/", "\\")):
        return fallback
    return re.sub(r'[<>:"/\\|?*]', "_", name)


async def _url_upload_job(
    job_id: int,
    game_id: int,
    url: str,
    dest_dir: Path,
    filename: str,
    os_platform: str,
    file_type: str,
    language: str | None,
    version: str | None,
    actor: str | None,
    max_bytes: int,
) -> None:
    from handler.socket_handler import sio
    import httpx

    dest_path = dest_dir / filename
    size = 0
    started = time.monotonic()
    last_emit = 0.0
    try:
        timeout = httpx.Timeout(30.0, read=300.0)
        async with httpx.AsyncClient(follow_redirects=True, timeout=timeout) as client:
            async with client.stream("GET", url) as resp:
                resp.raise_for_status()
                # Prefer the server-provided name (Content-Disposition).
                cd = resp.headers.get("content-disposition") or ""
                m = _CD_FILENAME.search(cd)
                if m:
                    better = _safe_filename(m.group(1), fallback=filename)
                    if better != filename:
                        filename = better
                        dest_path = dest_dir / filename
                total = int(resp.headers.get("content-length") or 0)
                if total and total > max_bytes:
                    raise ValueError(
                        f"File exceeds maximum allowed upload size "
                        f"({max_bytes // (1024 ** 3)} GB)."
                    )
                with open(dest_path, "wb") as fh:
                    async for chunk in resp.aiter_bytes(_CHUNK_WRITE):
                        fh.write(chunk)
                        size += len(chunk)
                        if size > max_bytes:
                            raise ValueError(
                                f"File exceeds maximum allowed upload size "
                                f"({max_bytes // (1024 ** 3)} GB)."
                            )
                        now = time.monotonic()
                        if now - last_emit >= 1.0:
                            last_emit = now
                            elapsed = max(now - started, 0.001)
                            await sio.emit("upload:url_progress", {
                                "id":       job_id,
                                "game_id":  game_id,
                                "filename": filename,
                                "percent":  round(size / total * 100, 1) if total else -1,
                                "received": size,
                                "total":    total,
                                "speed":    int(size / elapsed),
                            })

        result = await _finalize_upload(
            game_id, dest_path, filename, size,
            os_platform, file_type, language, version, actor,
        )
        await sio.emit("upload:url_complete", {"id": job_id, "game_id": game_id, **result})
        logger.info("URL upload #%d finished for game %d (%s, %d B)", job_id, game_id, filename, size)
    except _VirusFound as v:
        await sio.emit("upload:url_error", {
            "id": job_id, "game_id": game_id,
            "error": f"Blocked by antivirus ({v.threat}).",
        })
    except Exception as e:
        dest_path.unlink(missing_ok=True)
        logger.warning("URL upload #%d failed for game %d: %s", job_id, game_id, e)
        await sio.emit("upload:url_error", {
            "id": job_id, "game_id": game_id,
            "error": str(e)[:300] or "Download failed.",
        })


@protected_route(upload_router.post, "/games/{game_id}/upload-url", scopes=[Scope.LIBRARY_UPLOAD])
async def upload_game_file_from_url(request: Request, game_id: int, body: UploadUrlBody) -> dict:
    game = await _lib.get_by_id(game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    url = (body.url or "").strip()
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise HTTPException(status_code=400, detail="Only http(s) URLs are supported")

    filename = _safe_filename(parsed.path)
    dest_dir = _dest_dir_for(game.title, body.os, body.file_type)
    max_bytes = await _max_upload_bytes()
    actor = (request.state.user.username
             if getattr(request.state, "user", None) else None)

    job_id = next(_url_job_seq)
    asyncio.create_task(_url_upload_job(
        job_id, game_id, url, dest_dir, filename,
        body.os, body.file_type, body.language, body.version, actor, max_bytes,
    ))
    return {"id": job_id, "filename": filename}
