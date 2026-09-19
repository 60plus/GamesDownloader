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
from handler.library import quota
from decorators.auth import protected_route
from handler.auth.scopes import Scope
from handler.database.library_handler import LibraryHandler
from handler.library.ownership import assert_can_upload_into
from models.library_file import FILE_TYPES, LibraryFile, file_type_of
from utils.async_utils import fire_task, note_unscanned
from utils.errors import safe_note, safe_note_ref

logger = logging.getLogger(__name__)

upload_router = APIRouter(prefix="/library", tags=["library"])
_lib = LibraryHandler()

_CHUNK_WRITE = 1024 * 256  # 256 KB write buffer

# The only os values that become a directory. LibraryFile.os documents the same
# four; keeping the map closed is what stops a caller-supplied value from being
# used as a path segment.
_OS_FOLDERS = {"windows": "windows", "mac": "mac", "linux": "linux", "all": "."}

# What is not the game has a folder of its own in the game's, whatever its os.
# `mods`, plural, the way a ROM's mods/ folder is named (the owner, 2026-09-18);
# extra/ and dlc/ keep the names they have always had on disk.
_TYPE_FOLDERS = {"extra": "extra", "dlc": "dlc", "mod": "mods"}


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
    # The kind is closed the same way, and for the same reason it is asked
    # first: it picks the folder, and it arrives from the same untrusted places.
    kind = file_type_of(file_type)
    if kind is None:
        raise ValueError(
            f"Unknown file_type {file_type!r} - expected one of " + ", ".join(FILE_TYPES)
        )
    if kind in _TYPE_FOLDERS:
        sub = _TYPE_FOLDERS[kind]
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


async def _folder_title_for(game) -> str:
    """The name of this game's folder: its title, unless an older game on the
    same shelf has the same one.

    Two games may share a title - Doom from 1993 and Doom from 2016 - and the
    upload dialog offers a separate entry for exactly that. The folder is named
    from the title, so both entries used to write into one folder: a file of one
    could be refused as already there, or replaced by the other's.

    The OLDER entry keeps the plain name, so a game that has files already keeps
    writing where they are. A newer one gets its slug beside the title, which is
    unique and stays the same on every upload.
    """
    from sqlalchemy import func, select

    from handler.database.session import async_session_factory
    from models.library_game import LibraryGame

    title = (game.title or "").strip()
    async with async_session_factory() as db:
        older = (await db.execute(
            select(LibraryGame.id, LibraryGame.title)
            .where(func.lower(LibraryGame.title) == title.lower(),
                   LibraryGame.id < game.id)
        )).all()
    if not older:
        return title
    mine = await _resolve_storage_folder(game.id)
    for other_id, other_title in older:
        if (_sanitize(other_title or "") == _sanitize(title)
                and await _resolve_storage_folder(other_id) == mine):
            return f"{title} [{game.slug}]"
    return title


async def _game_open_to_upload(request: Request, game_id: int):
    """The game this caller may add a file to, or the refusal.

    404 for a game they cannot see, the same answer as for one that does not
    exist. This used to go straight to "may you add to it", and the 403 that
    answered for somebody else's game in a restricted library said the id was
    real (1.0.34 audit, #7). Anybody who may upload may add to any game they can
    see - see `ownership.can_upload_into_game`.
    """
    from handler.library.visibility import visible_game_or_none

    game = await _lib.get_by_id(game_id)
    if not game or await visible_game_or_none(getattr(request.state, "user", None), game) is None:
        raise HTTPException(status_code=404, detail="Game not found")
    assert_can_upload_into(request, game)
    return game


async def _refuse_replacing_another_accounts_file(
    game, dest_path: Path, *, scopes, user_id: int | None,
) -> None:
    """Refuse to overwrite a file somebody else is charged for.

    Adding to another account's game is allowed; writing over what that account
    put there is not. Only when the file is really there: a new name replaces
    nothing.
    """
    from handler.library.ownership import can_replace_file

    if not dest_path.exists():
        return
    rel = _rel_from_abs(str(dest_path))
    row = next((f for f in await _lib.get_files_for_game(game.id) if f.file_path == rel), None)
    if not can_replace_file(scopes, user_id, game, row):
        raise HTTPException(
            status_code=403,
            detail=(f"'{dest_path.name}' was added by another account, so only an "
                    "administrator or that account may replace it."),
        )


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


def _part_path(dest_path: Path) -> Path:
    """Where the bytes land while they are still arriving.

    Nothing writes straight to its final name any more. Both upload paths used
    to open the destination directly, so an upload of a name that already
    existed truncated a finished game file the moment the first byte arrived,
    and the blanket error handler then deleted what was left. Failures that had
    written nothing at all reached that delete too - a 404 on a pasted link, a
    file bigger than the limit, a blocked redirect - so pasting a dead URL
    removed a healthy install whose only crime was sharing a filename.
    """
    return dest_path.with_name(dest_path.name + ".part")


def _refuse_existing(dest_path: Path, overwrite: bool) -> None:
    """Do not replace a file that is already there unless asked to.

    The duplicate guard further down only looks at the database, and only after
    the bytes are on disk. This looks at the disk, first. Same rule the ROM
    downloader applies for the same reason: a stale listing or a double click
    should not be able to write over something already downloaded.
    """
    if overwrite or not dest_path.exists():
        return
    raise ValueError(
        f"'{dest_path.name}' is already in this game's folder. "
        f"Remove it first, or send overwrite=true to replace it."
    )


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
    staged: Path | None = None,
    owner_id: int | None = None,
) -> dict:
    """Shared tail of every upload path: optional ClamAV check, duplicate
    guard and the LibraryFile record. Raises _VirusFound when ClamAV blocks
    the file (already quarantined/deleted by then).

    `staged` is where the bytes actually are: the scan runs against that, and
    only a file that survives it is moved onto `dest_path`. Scanning after the
    move would mean an infected upload had already replaced a good file by the
    time anything objected, and ClamAV's own quarantine step would then carry
    off the wrong one.

    ClamAV is controlled by the `clamav_auto_scan_upload` admin setting (off
    by default). Only "FOUND" rejects the upload - scan errors fail open so a
    broken daemon does not block legitimate users."""
    scan_target = staged or dest_path
    try:
        from handler.clamav import clamav_handler as _clam
        if await _clam.is_upload_scanning_enabled():
            scan_res = await _clam.scan_file(str(scan_target))
            note_unscanned(scan_res, "upload", filename)
            if scan_res.get("status") == "FOUND":
                threat = scan_res.get("threat") or "unknown"
                action_res = await _clam.quarantine_or_delete(
                    str(scan_target), threat, triggered_by=actor
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
        logger.exception("ClamAV scan check failed for %s; allowing upload", scan_target)

    # Clean, so it can take its real name. os.replace is atomic within a
    # filesystem: either the old file is there or the new one is, never a
    # half-written thing wearing the name of something that worked.
    if staged is not None:
        os.replace(str(staged), str(dest_path))

    rel = _rel_from_abs(str(dest_path))

    # The path already has a row, so the bytes on disk just changed under it.
    #
    # This used to return here without a single write, and the quota is a SUM of
    # `LibraryFile.size_bytes` in SQL - never a counter, never measured from the
    # disk - so the row was the only thing saying how big the file is, and it
    # went on saying the old number. Write one byte under a name, replace it
    # with the real file, and the disk grows while `used_bytes` does not.
    #
    # And the OWNER goes with them.
    #
    # This used to leave `published_by` alone, reasoning that a catalogue entry
    # fetched a second time reuses the first account's game on purpose. That is
    # true of the GAME and not of the file: on a file row this column means "who
    # brought these bytes in", and after a replacement that is whoever just
    # replaced them.
    #
    # Leaving it made one account's allowance move by another account's action.
    # The store route hardcodes `overwrite=True` and asks only for an upload
    # permission and store access, so a second person fetching the same entry
    # rewrote the size on the first person's row: their bar jumped, they could be
    # pushed over the limit and refused their next upload for something they did
    # not do, and the account that actually put the bytes on the disk was charged
    # nothing and could repeat it.
    #
    # NOT closed with a refusal. Two accounts fetching the same catalogue entry
    # is what that route is for.
    existing_files = await _lib.get_files_for_game(game_id)
    prior = next((f for f in existing_files if f.file_path == rel), None)
    if prior is not None:
        changes: dict = {"size_bytes": size, "is_available": True}
        # Only when there is somebody to charge. Some ways in carry no account -
        # a server-side fetch, a job with no caller - and writing None over a
        # real owner would take the bytes off every total and leave the sum
        # smaller than the disk.
        if owner_id:
            changes["published_by"] = owner_id
        await _lib.update_file(prior, changes)
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
        # One of the four, whatever the form called it ("extras", "mods"):
        # _dest_dir_for has refused anything else before the bytes were taken.
        file_type=file_type_of(file_type) or "game",
        os=os_platform,
        language=language,
        version=version,
        size_bytes=size,
        file_path=rel,
        source="custom",
        is_available=True,
        # Charged to whoever brought this file in, rather than worked out later
        # from the game it hangs off. A game can hold files from two accounts -
        # a catalogue entry downloaded a second time reuses the first account's
        # game on purpose - and asking only the game billed the second person's
        # bytes to the first.
        published_by=owner_id,
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
    # Replacing a file that is already in the folder has to be asked for. It
    # used to happen by itself, at the first byte, before anything had checked
    # the replacement was even downloadable.
    overwrite:   bool = Form(False),
) -> dict:
    # A game this caller can see, whoever added it. The bytes are charged to
    # the caller below, not to the game's owner.
    game = await _game_open_to_upload(request, game_id)

    try:
        dest_dir = _dest_dir_for(
            await _folder_title_for(game), os_platform, file_type,
            await _resolve_storage_folder(game_id),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    filename = Path(file.filename or "upload.bin").name
    # Reject filenames that contain traversal sequences after stripping the directory component
    if ".." in filename or filename.startswith(("/", "\\")):
        raise HTTPException(status_code=400, detail="Invalid filename")
    dest_path = dest_dir / filename
    try:
        _refuse_existing(dest_path, overwrite)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    if overwrite:
        await _refuse_replacing_another_accounts_file(
            game, dest_path, scopes=getattr(request.state, "scopes", set()),
            user_id=getattr(getattr(request.state, "user", None), "id", None))

    max_bytes = await _max_upload_bytes(getattr(request.state, "user", None))
    # Two different limits, and both have to hold: max_bytes is the ceiling on
    # this one file, room_left is what the account has spare across everything
    # it owns. Asked before a byte is written, so a hopeless upload is refused
    # at once rather than after the whole file has crossed the wire.
    _uploader = getattr(request.state, "user", None)
    # What this upload is about to give back. What has landed already counts
    # the file being replaced, so charging the replacement on top of it would
    # refuse an account whose allowance is filled by the very file it is
    # swapping - which is the ordinary reason to send the same path twice. Only
    # the caller's own bytes come back: a file somebody else is charged for
    # stays on their total until the row is rewritten.
    replacing = 0
    if overwrite:
        for f in await _lib.get_files_for_game(game_id):
            if f.file_path == _rel_from_abs(str(dest_path)) and (
                    f.published_by or None) == getattr(_uploader, "id", None):
                replacing = int(f.size_bytes or 0)
                break
    # The bytes this upload writes, counted against what has landed, what this
    # account's torrents are still bringing and every other stream it has
    # running - at the start and at every chunk. Held until the file row counts
    # them, so they are never counted nowhere.
    reservation = await quota.reservation_for(_uploader, credit=replacing)
    if reservation.bounded and await reservation.room() == 0:
        raise HTTPException(
            status_code=413,
            detail=f"Upload quota reached: none of this account's {reservation.limit} bytes is free.",
        )
    reservation.open()

    try:
        # Into a .part, never straight onto the destination. Writing to the
        # final name truncated whatever was already there before a single byte
        # of the replacement had been checked, and a browser that went away
        # mid-upload left the wreckage wearing the name of something that used
        # to work.
        part_path = _part_path(dest_path)
        size = 0
        aborted = False
        over_quota = False
        try:
            with open(part_path, "wb") as fh:
                while chunk := await file.read(_CHUNK_WRITE):
                    fh.write(chunk)
                    size += len(chunk)
                    if size > max_bytes:
                        aborted = True
                        break
                    # The quota is checked here as well as before the write.
                    # The size is not known in advance for a streamed body, and
                    # the account's other uploads grow while this one runs.
                    if not await reservation.take(len(chunk)):
                        aborted = True
                        over_quota = True
                        break
        except Exception:
            part_path.unlink(missing_ok=True)
            raise
        finally:
            if aborted:
                part_path.unlink(missing_ok=True)
                raise HTTPException(
                    status_code=413,
                    detail=(
                        f"Upload quota reached: this upload and the rest of this "
                        f"account's do not fit in its {reservation.limit} bytes."
                        if over_quota else
                        f"File exceeds maximum allowed upload size "
                        f"({max_bytes // (1024 ** 3)} GB)."
                    ),
                )

        actor = (request.state.user.username
                 if getattr(request.state, "user", None) else None)
        try:
            return await _finalize_upload(
                game_id, dest_path, filename, size,
                os_platform, file_type, language, version, actor,
                staged=part_path,
                owner_id=getattr(getattr(request.state, "user", None), "id", None),
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
    finally:
        # Only now: the file row counts these bytes, or they are gone.
        reservation.close()


# ── Upload from a direct URL (server-side background download) ───────────────

class UploadUrlBody(BaseModel):
    url: str
    os: str = "all"
    file_type: str = "game"
    language: str | None = None
    version: str | None = None
    overwrite: bool = False


_url_job_seq = itertools.count(1)

_CD_FILENAME = re.compile(r'filename\*?=(?:UTF-8\'\')?["\']?([^"\';\r\n]+)', re.IGNORECASE)


def _safe_filename(raw: str, fallback: str = "download.bin") -> str:
    name = Path(unquote(raw or "")).name.strip()
    if not name or ".." in name or name.startswith(("/", "\\")):
        return fallback
    return re.sub(r'[<>:"/\\|?*]', "_", name)


async def _emit_url_job(actor_id: int | None, event: str, payload: dict) -> None:
    """Send one URL-upload event to the account that started it, and to admins.

    These four events used to go out with no room at all, which socket.io reads
    as everybody: the game's title, the file name and the job id to every
    logged-in account on the server. The ROM download path had the same hole and
    was given `_download_audience`; this one lives in another file and was
    missed. Same rule, asked from there so the two cannot drift.
    """
    from handler.roms.rom_source_handler import _download_audience
    from handler.socket_handler import sio
    from types import SimpleNamespace

    for room in _download_audience(SimpleNamespace(actor_id=actor_id))["rooms"]:
        try:
            await sio.emit(event, payload, room=room)
        except Exception:   # noqa: BLE001 - a progress line, never the transfer
            logger.debug("Could not emit %s", event, exc_info=True)


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
    overwrite: bool = False,
    actor_id: int | None = None,
    replace_guard: tuple | None = None,
) -> None:
    from handler.socket_handler import sio
    import httpx
    from utils.net_guard import make_request_guard

    dest_path = dest_dir / filename
    part_path = _part_path(dest_path)
    size = 0
    started = time.monotonic()
    last_emit = 0.0
    # The bytes this job writes, counted with the account's other streams at
    # every chunk; `max_bytes` was the room when the job was queued, and the
    # account's other uploads grow while this one runs. Held until the file
    # row counts them.
    reservation = await quota.reservation_for_account(actor_id)
    reservation.open()
    try:
        _refuse_existing(dest_path, overwrite)
        if overwrite and replace_guard is not None:
            game, scopes, user_id = replace_guard
            await _refuse_replacing_another_accounts_file(
                game, dest_path, scopes=scopes, user_id=user_id)
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
                        part_path = _part_path(dest_path)
                        # The server named it, so the collision check has to run
                        # again against the name that will actually be used.
                        _refuse_existing(dest_path, overwrite)
                        if overwrite and replace_guard is not None:
                            game, scopes, user_id = replace_guard
                            await _refuse_replacing_another_accounts_file(
                                game, dest_path, scopes=scopes, user_id=user_id)
                total = int(resp.headers.get("content-length") or 0)
                if total and total > max_bytes:
                    raise ValueError(
                        f"File exceeds maximum allowed upload size "
                        f"({max_bytes // (1024 ** 3)} GB)."
                    )
                with open(part_path, "wb") as fh:
                    async for chunk in resp.aiter_bytes(_CHUNK_WRITE):
                        fh.write(chunk)
                        size += len(chunk)
                        if size > max_bytes:
                            raise ValueError(
                                f"File exceeds maximum allowed upload size "
                                f"({max_bytes // (1024 ** 3)} GB)."
                            )
                        if not await reservation.take(len(chunk)):
                            raise ValueError(
                                "Upload quota reached: this download and the rest of "
                                "this account's do not fit."
                            )
                        now = time.monotonic()
                        if now - last_emit >= 1.0:
                            last_emit = now
                            elapsed = max(now - started, 0.001)
                            await _emit_url_job(actor_id, "upload:url_progress", {
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
            staged=part_path, owner_id=actor_id,
        )
        await _emit_url_job(actor_id, "upload:url_complete", {"id": job_id, "game_id": game_id, "game_title": game_title, "tray": tray, **result})
        logger.info("URL upload #%d finished for game %d (%s, %d B)", job_id, game_id, filename, size)
    except _VirusFound as v:
        part_path.unlink(missing_ok=True)
        await _emit_url_job(actor_id, "upload:url_error", {
            "id": job_id, "game_id": game_id,
            "game_title": game_title, "tray": tray,
            # The sentence stays as the fallback; the name is what the tray
            # translates. The signature is not ours to translate - it is a name,
            # and rewriting it would make it unsearchable.
            "error": f"Blocked by antivirus ({v.threat}).",
            "error_code": "url_virus",
            "error_detail": v.threat,
        })
    except Exception as e:
        # Only ever the .part. This line used to name the destination, and
        # every failure reached it - including the ones that had not written a
        # byte, like a 404, a file over the size limit, or a redirect the SSRF
        # guard turned down. A dead link deleted a finished game.
        part_path.unlink(missing_ok=True)
        logger.warning("URL upload #%d failed for game %d: %s", job_id, game_id, e)
        said, ref = safe_note_ref(e, what="Download failed")
        await _emit_url_job(actor_id, "upload:url_error", {
            "id": job_id, "game_id": game_id,
            "game_title": game_title, "tray": tray,
            # Nothing here can be classified - it is whatever went wrong - so
            # the reason travels as "we do not know" plus the reference that
            # ties this row to the traceback in the log. Without the reference
            # on its own, the tray could only repeat the English sentence.
            "error": said,
            "error_code": "url_failed",
            "error_detail": ref,
        })
    finally:
        # Only now: the file row counts these bytes, or they are gone.
        reservation.close()


async def queue_url_download(
    game, url: str, *, os_platform: str, file_type: str,
    language: str | None = None, version: str | None = None,
    actor: str | None = None, actor_id: int | None = None,
    max_bytes: int, storage_folder: str | None = None,
    storage_title: str | None = None, tray: bool = False,
    overwrite: bool = False, replace_guard: tuple | None = None,
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
    caller passes a disambiguated name. Defaults to the game's own folder name,
    which is its title unless an older game on the shelf has the same one.

    ``replace_guard`` is ``(game, scopes, user_id)`` for a caller who may add to
    a game but not write over another account's file in it: the manual upload.
    A catalogue download leaves it out on purpose - two accounts fetching the
    same entry replace the same build, and that is what the route is for.

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
    dest_dir = _dest_dir_for(storage_title or await _folder_title_for(game),
                             os_platform, file_type, folder)
    if overwrite and replace_guard is not None:
        # Asked here as well as in the job, so a refusal reaches the dialog that
        # is still open rather than the tray a moment later. The job asks again
        # for a name the server hands out in its answer.
        _game, scopes, user_id = replace_guard
        await _refuse_replacing_another_accounts_file(
            _game, dest_dir / filename, scopes=scopes, user_id=user_id)
    job_id = next(_url_job_seq)
    fire_task(_url_upload_job(
        job_id, game.id, url, dest_dir, filename,
        os_platform, file_type, language, version, actor, max_bytes,
        game_title=game.title, tray=tray, overwrite=overwrite,
        actor_id=actor_id, replace_guard=replace_guard,
    ))
    return {"id": job_id, "filename": filename}


@protected_route(upload_router.post, "/games/{game_id}/upload-url", scopes=[Scope.LIBRARY_UPLOAD])
async def upload_game_file_from_url(request: Request, game_id: int, body: UploadUrlBody) -> dict:
    # A game this caller can see, whoever added it; see the file route above.
    game = await _game_open_to_upload(request, game_id)

    try:
        return await queue_url_download(
            game, body.url,
            os_platform=body.os, file_type=body.file_type,
            language=body.language, version=body.version,
            actor=(request.state.user.username
                   if getattr(request.state, "user", None) else None),
            actor_id=getattr(getattr(request.state, "user", None), "id", None),
            max_bytes=await quota.ceiling_for(
                getattr(request.state, "user", None),
                await _max_upload_bytes(getattr(request.state, "user", None)),
            ),
            overwrite=body.overwrite,
            replace_guard=(game, getattr(request.state, "scopes", set()),
                           getattr(getattr(request.state, "user", None), "id", None)),
        )
    # UnsafeURLError is a ValueError, so the blocked-URL case lands here too.
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
