"""Library file upload endpoint - multipart upload for Admin/Uploader.

POST /library/games/{game_id}/upload
  - Accepts a single file (multipart/form-data)
  - os, file_type, language, version params
  - Saves to /data/games/CUSTOM/{slug}/{os}/
  - Creates LibraryFile record
"""

from __future__ import annotations

import logging
import os
import re
import unicodedata
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

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

    # Determine save directory
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

    safe_title = _sanitize(game.title)
    if sub == ".":
        dest_dir = Path(GAMES_PATH) / "CUSTOM" / safe_title
    else:
        dest_dir = Path(GAMES_PATH) / "CUSTOM" / safe_title / sub
    dest_dir.mkdir(parents=True, exist_ok=True)

    filename = Path(file.filename or "upload.bin").name
    # Reject filenames that contain traversal sequences after stripping the directory component
    if ".." in filename or filename.startswith(("/", "\\")):
        raise HTTPException(status_code=400, detail="Invalid filename")
    dest_path = dest_dir / filename

    # Configurable upload size limit (default 50 GB)
    from handler.config.config_handler import config_handler as _cfg
    _raw_max = await _cfg.get("max_upload_bytes")
    try:
        max_bytes = int(_raw_max) if _raw_max else 50 * 1024 ** 3
    except ValueError:
        max_bytes = 50 * 1024 ** 3

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

    # ── Optional ClamAV scan on upload ────────────────────────────────────────
    # Controlled by the `clamav_auto_scan_upload` admin setting (off by default).
    # Only "FOUND" rejects the upload - scan errors fail open so a broken
    # daemon does not block legitimate users.
    try:
        from handler.clamav import clamav_handler as _clam
        if await _clam.is_upload_scanning_enabled():
            scan_res = await _clam.scan_file(str(dest_path))
            if scan_res.get("status") == "FOUND":
                threat = scan_res.get("threat") or "unknown"
                actor = (request.state.user.username
                         if getattr(request.state, "user", None) else None)
                action_res = await _clam.quarantine_or_delete(
                    str(dest_path), threat, triggered_by=actor
                )
                logger.warning(
                    "ClamAV blocked upload '%s' (game=%d, threat=%s, action=%s)",
                    filename, game_id, threat, action_res.get("action"),
                )
                raise HTTPException(
                    status_code=422,
                    detail={
                        "code":   "virus_detected",
                        "threat": threat,
                        "action": action_res.get("action"),
                    },
                )
    except HTTPException:
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
