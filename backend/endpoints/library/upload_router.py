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
import hashlib
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

# The only os values that become a directory. LibraryFile.os documents the same
# four; keeping the map closed is what stops a caller-supplied value from being
# used as a path segment.
_OS_FOLDERS = {"windows": "windows", "mac": "mac", "linux": "linux", "all": "."}


def _sanitize(title: str) -> str:
    t = unicodedata.normalize("NFKD", title)
    t = t.encode("ascii", errors="ignore").decode("ascii")
    t = re.sub(r'[<>:"/\\|?*]', "_", t)
    # Strip path traversal sequences
    t = re.sub(r'\.\.+', "_", t)
    cleaned = t.strip("./\\ ")
    if cleaned:
        return cleaned
    # A title with no ASCII in it at all - a Japanese or Cyrillic name - used to
    # come back empty, and an empty path segment silently disappears: every such
    # game shared one directory and their files overwrote each other. The hash
    # keeps them apart and keeps the same title on the same folder across runs.
    return "game-" + hashlib.sha1(title.encode("utf-8")).hexdigest()[:10]


def _rel_from_abs(abs_path: str) -> str:
    from config import BASE_PATH
    return os.path.relpath(abs_path, BASE_PATH)


def _dest_dir_for(
    game_title: str, os_platform: str, file_type: str, storage_folder: str = "CUSTOM",
) -> Path:
    """Resolve (and create) the on-disk folder for an upload.

    `storage_folder` is the library's folder under GAMES_PATH: "CUSTOM" for the
    built-in Games library, or a custom library's own folder (e.g. "kids-games").
    Files land in <storage_folder>/<title>/<os>/.
    """
    # An unrecognised os used to be dropped into the path verbatim, and pathlib
    # does not normalise a segment: "../../../plugins" walks out of GAMES_PATH,
    # and an absolute segment replaces the whole prefix outright. Since the
    # caller-supplied os reaches here from a request body, a form field and a
    # catalogue entry, that was an arbitrary file write. Only the four known
    # values are folders now; anything else is refused.
    sub = _OS_FOLDERS.get(os_platform)
    if sub is None:
        raise ValueError(
            f"Unknown os {os_platform!r} - expected one of "
            + ", ".join(sorted(_OS_FOLDERS))
        )
    if file_type in ("extra", "extras"):
        sub = "extra"
    elif file_type == "dlc":
        sub = "dlc"
    safe_title = _sanitize(game_title)
    if sub == ".":
        dest_dir = Path(GAMES_PATH) / storage_folder / safe_title
    else:
        dest_dir = Path(GAMES_PATH) / storage_folder / safe_title / sub
    dest_dir.mkdir(parents=True, exist_ok=True)
    return dest_dir


async def _resolve_storage_folder(game_id: int) -> str:
    """Pick the on-disk folder for a game's uploads: if the game belongs to a
    folder-backed custom library, use that library's folder; otherwise "CUSTOM"
    (the built-in Games library)."""
    from handler.database.library_registry_handler import library_registry_handler
    member_ids = set(await library_registry_handler.get_member_library_ids(game_id))
    if member_ids:
        for lib in await library_registry_handler.get_all():
            if lib.id in member_ids and lib.kind == "custom_lib" and lib.storage_folder:
                return lib.storage_folder
    return "CUSTOM"


async def _max_upload_bytes(user=None) -> int:
    """Effective upload size limit: a per-user override (User.permissions
    ["max_upload_bytes"], set in Settings > Users) wins; otherwise the global
    default from Settings > Downloads (config "max_upload_bytes"); otherwise 50 GB."""
    perm = (getattr(user, "permissions", None) or {}).get("max_upload_bytes")
    try:
        if perm and int(perm) > 0:
            return int(perm)
    except (ValueError, TypeError):
        pass
    from handler.config.config_handler import config_handler as _cfg
    _raw_max = await _cfg.get("max_upload_bytes")
    try:
        v = int(_raw_max) if _raw_max else 0
        return v if v > 0 else 50 * 1024 ** 3
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

    try:
        dest_dir = _dest_dir_for(
            game.title, os_platform, file_type, await _resolve_storage_folder(game_id),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    filename = Path(file.filename or "upload.bin").name
    # Reject filenames that contain traversal sequences after stripping the directory component
    if ".." in filename or filename.startswith(("/", "\\")):
        raise HTTPException(status_code=400, detail="Invalid filename")
    dest_path = dest_dir / filename

    max_bytes = await _max_upload_bytes(getattr(request.state, "user", None))

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
    game_title: str = "",
    tray: bool = False,
) -> None:
    from handler.socket_handler import sio
    import httpx
    from utils.net_guard import make_request_guard

    dest_path = dest_dir / filename
    size = 0
    started = time.monotonic()
    last_emit = 0.0
    try:
        timeout = httpx.Timeout(30.0, read=300.0)
        # SSRF guard: block localhost / cloud-metadata / link-local on every hop
        # (initial + redirects), but allow RFC-1918 LAN so a self-hoster can pull
        # a file from a NAS on their own network.
        async with httpx.AsyncClient(
            follow_redirects=True, timeout=timeout,
            event_hooks={"request": [make_request_guard(allow_private_lan=True)]},
        ) as client:
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
                                "game_title": game_title,
                                "tray":     tray,
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
        await sio.emit("upload:url_complete", {"id": job_id, "game_id": game_id, "game_title": game_title, "tray": tray, **result})
        logger.info("URL upload #%d finished for game %d (%s, %d B)", job_id, game_id, filename, size)
    except _VirusFound as v:
        await sio.emit("upload:url_error", {
            "id": job_id, "game_id": game_id,
            "game_title": game_title, "tray": tray,
            "error": f"Blocked by antivirus ({v.threat}).",
        })
    except Exception as e:
        dest_path.unlink(missing_ok=True)
        logger.warning("URL upload #%d failed for game %d: %s", job_id, game_id, e)
        await sio.emit("upload:url_error", {
            "id": job_id, "game_id": game_id,
            "game_title": game_title, "tray": tray,
            "error": str(e)[:300] or "Download failed.",
        })


async def queue_url_download(
    game, url: str, *, os_platform: str, file_type: str,
    language: str | None = None, version: str | None = None,
    actor: str | None = None, max_bytes: int, storage_folder: str | None = None,
    storage_title: str | None = None, tray: bool = False,
) -> dict:
    """Validate a URL and start a background download into a game's folder.

    Shared so that anything pulling a build onto the server - the admin pasting
    a link, a catalogue offering one - goes through the same checks. A second
    copy of this would be a second place to forget the SSRF guard.

    ``storage_folder`` overrides the on-disk folder. A catalogue download shows
    its game in the Games library but keeps its files under the store's own
    folder (the way GOG puts installers under /GOG), so the folder cannot be
    read back from library membership and is passed in.

    ``storage_title`` overrides the per-game folder name. Two catalogue entries
    can share a title, and their builds must not share a folder - one would
    overwrite the other and deleting one would strand the other's files - so the
    caller passes a disambiguated name. Defaults to the game's title.

    Raises ValueError on a URL that must not be fetched; callers turn that into
    whatever their transport calls a bad request.
    """
    url = (url or "").strip()
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("Only http(s) URLs are supported")

    # Fail fast on an obviously-internal target (localhost / cloud metadata /
    # link-local). LAN is allowed here (self-hosters pull from their own NAS);
    # the download job re-checks every redirect hop with the same policy.
    from utils.net_guard import assert_fetch_allowed
    assert_fetch_allowed(url, allow_private_lan=True)

    folder = storage_folder if storage_folder is not None else await _resolve_storage_folder(game.id)
    filename = _safe_filename(parsed.path)
    dest_dir = _dest_dir_for(storage_title or game.title, os_platform, file_type, folder)
    job_id = next(_url_job_seq)
    asyncio.create_task(_url_upload_job(
        job_id, game.id, url, dest_dir, filename,
        os_platform, file_type, language, version, actor, max_bytes,
        game_title=game.title, tray=tray,
    ))
    return {"id": job_id, "filename": filename}


@protected_route(upload_router.post, "/games/{game_id}/upload-url", scopes=[Scope.LIBRARY_UPLOAD])
async def upload_game_file_from_url(request: Request, game_id: int, body: UploadUrlBody) -> dict:
    game = await _lib.get_by_id(game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    try:
        return await queue_url_download(
            game, body.url,
            os_platform=body.os, file_type=body.file_type,
            language=body.language, version=body.version,
            actor=(request.state.user.username
                   if getattr(request.state, "user", None) else None),
            max_bytes=await _max_upload_bytes(getattr(request.state, "user", None)),
        )
    # UnsafeURLError is a ValueError, so the blocked-URL case lands here too.
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
