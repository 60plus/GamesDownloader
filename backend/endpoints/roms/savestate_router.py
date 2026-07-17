"""Savestate and battery-save endpoints for the in-browser ROM emulator.

Prefix: /api/savestates

Savestates live in numbered slots (1-9) like a console memory card: saving to a
slot replaces whatever was in it. Battery saves (.srm) are the cartridge SRAM -
one per ROM+core, overwritten in place, since the single blob already holds all
of the game's own in-game slots.

Routes:
  POST   /{rom_id}/states            upload savestate (into `slot`, replacing it)
  GET    /{rom_id}/states            list user's savestates for a ROM
  GET    /states/{id}/content        download .state file
  DELETE /states/{id}                delete savestate

  POST   /{rom_id}/saves             upload battery save (.srm)
  GET    /{rom_id}/saves             list user's battery saves for a ROM
  GET    /saves/{id}/content         download .srm file
  DELETE /saves/{id}                 delete battery save

  GET    /quota                      user's storage usage vs quota
  GET    /my                         all user's saves+states (for profile page)
"""

from __future__ import annotations

import hashlib
import io
import logging
import os
import zipfile
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.exc import IntegrityError
from starlette.background import BackgroundTask
from starlette.concurrency import run_in_threadpool

from decorators.auth import protected_route
from handler.auth.scopes import Scope as Scopes
from handler.config.config_handler import config_handler
from handler.database.rom_handler import rom_handler, rom_platform_handler
from handler.database.save_state_handler import save_state_handler
from handler.metadata.rom_platform_map import rom_cover_aspect as _rom_cover_aspect
from models.rom_save_state import RomSave, RomSaveState
from utils.save_archive import build_archive, member_bytes, read_manifest
from utils.save_paths import (
    saves_dir as _saves_dir,
    screenshot_sig_valid,
    screenshot_url as _screenshot_url,
    states_dir as _states_dir,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/savestates", tags=["savestates"])

_DEFAULT_QUOTA = 100 * 1024 * 1024   # 100 MB
_MAX_FILE_SIZE  = 64 * 1024 * 1024   # 64 MB per file
# A savestate thumbnail is a screen grab, not a payload. Capping it separately
# from the state itself stops a 64 MB "screenshot" from riding in on the state
# limit - the bytes land on disk either way.
_MAX_SHOT_SIZE  = 4 * 1024 * 1024    # 4 MB per screenshot
_MAX_SLOT       = 9                  # EmulatorJS offers slots 1-9


# ── Helpers ───────────────────────────────────────────────────────────────────

def _safe_stem(name: str) -> str:
    """A ROM name is scanned off disk, so it can carry separators ("Sonic 1/2")
    that would scatter save files into subdirectories. Keep it to one segment."""
    cleaned = "".join("_" if c in '/\\:*?"<>|' else c for c in name).strip(" .")
    return (cleaned or "rom")[:80]

async def _scan_or_reject(file_path: Path, *, username: str | None) -> None:
    """Run ClamAV on `file_path` if upload scanning is enabled.

    Raises HTTPException(422) when the file is infected. Scanner errors
    fail open so a broken daemon does not block legitimate users.
    """
    try:
        from handler.clamav import clamav_handler as _clam
        if not await _clam.is_upload_scanning_enabled():
            return
        res = await _clam.scan_file(str(file_path))
        if res.get("status") == "FOUND":
            threat = res.get("threat") or "unknown"
            action = await _clam.quarantine_or_delete(
                str(file_path), threat, triggered_by=username
            )
            logger.warning(
                "ClamAV blocked savestate upload '%s' (threat=%s, action=%s)",
                file_path.name, threat, action.get("action"),
            )
            raise HTTPException(
                status_code=422,
                detail={
                    "code":   "virus_detected",
                    "threat": threat,
                    "action": action.get("action"),
                },
            )
    except HTTPException:
        raise
    except Exception:
        logger.exception("ClamAV scan failed for %s; allowing upload", file_path)


async def _quota_limit(user=None) -> int:
    """Effective save quota: a per-user override (User.permissions
    ["saves_quota_bytes"], set in Settings > Users) wins; otherwise the global
    default from Settings > Downloads (config "saves_quota_bytes"); otherwise 100 MB."""
    perm = (getattr(user, "permissions", None) or {}).get("saves_quota_bytes")
    try:
        if perm and int(perm) > 0:
            return int(perm)
    except (ValueError, TypeError):
        pass
    raw = await config_handler.get("saves_quota_bytes")
    try:
        v = int(raw) if raw else 0
        return v if v > 0 else _DEFAULT_QUOTA
    except ValueError:
        return _DEFAULT_QUOTA


async def _check_quota(user, extra: int) -> None:
    limit = await _quota_limit(user)
    used = await save_state_handler.get_user_total_size(user.id)
    if used + extra > limit:
        raise HTTPException(
            status_code=413,
            detail=(
                f"Save quota exceeded. Used {used // (1024 * 1024)} MB "
                f"of {limit // (1024 * 1024)} MB."
            ),
        )


def _rom_info(rom) -> dict:
    """The bits the saves UI needs to draw a game header: name, cover, platform.
    `platform_slug` is the routable slug, so a tile can link to the ROM.
    `rom_cover_aspect` ships too - SNES boxes are 4/3 and a fixed portrait frame
    would crop them, same trap the dashboard strips hit.

    `rom_support` is the cartridge/disc art. A battery save IS the cartridge's
    SRAM, so the tile shows the cartridge it came out of; it is scraped art, so
    it may be absent and the UI falls back to an icon.
    """
    if rom is None:
        return {"rom_name": None, "rom_cover": None, "rom_cover_aspect": None,
                "rom_support": None, "platform_name": None, "platform_slug": None}
    plat = getattr(rom, "platform", None)
    return {
        "rom_name":         rom.name or rom.fs_name_no_ext,
        "rom_cover":        rom.cover_path,
        "rom_cover_aspect": _rom_cover_aspect(
            rom.cover_type, rom.cover_aspect, plat.fs_slug if plat else None
        ),
        "rom_support":      rom.support_path,
        "platform_name":    (plat.custom_name or plat.name) if plat else None,
        "platform_slug":    plat.slug if plat else None,
    }


def _state_dict(s: RomSaveState, rom=None) -> dict:
    return {
        "id":             s.id,
        "rom_id":         s.rom_id,
        "slot":           s.slot,          # None on legacy rows saved before slots
        "file_name":      s.file_name,
        "file_size_bytes": s.file_size_bytes,
        "emulator_core":  s.emulator_core,
        "screenshot_url": _screenshot_url(s.id, s.screenshot_path),
        "created_at":     s.created_at.isoformat() if s.created_at else None,
        "updated_at":     s.updated_at.isoformat() if s.updated_at else None,
        # download_url is the RAW state - the player fetches it to resume, so it
        # must stay raw bytes. export_url is the archive a human downloads.
        "download_url":   f"/api/savestates/states/{s.id}/content",
        "export_url":     f"/api/savestates/states/{s.id}/export",
        **_rom_info(rom),
    }


def _save_dict(s: RomSave, rom=None) -> dict:
    return {
        "id":             s.id,
        "rom_id":         s.rom_id,
        "file_name":      s.file_name,
        "file_size_bytes": s.file_size_bytes,
        "emulator_core":  s.emulator_core,
        "slot":           s.slot,
        "created_at":     s.created_at.isoformat() if s.created_at else None,
        "updated_at":     s.updated_at.isoformat() if s.updated_at else None,
        # See _state_dict: download_url stays raw for the player, export_url is
        # the archive.
        "download_url":   f"/api/savestates/saves/{s.id}/content",
        "export_url":     f"/api/savestates/saves/{s.id}/export",
        **_rom_info(rom),
    }


def _drop_stale_files(row, keep: set[str | None]) -> None:
    """Delete the files a replaced row pointed at, unless the new save just
    rewrote that same path. Without this, renaming a legacy timestamped save to
    its slot name would strand the old file on disk, uncounted and undeletable."""
    old = [str(Path(row.file_path) / row.file_name), getattr(row, "screenshot_path", None)]
    for p in old:
        if not p or p in keep:
            continue
        try:
            fp = Path(p)
            if fp.exists():
                fp.unlink()
        except OSError:
            logger.warning("Could not remove replaced save file %s", p)


async def _get_rom_or_404(rom_id: int):
    rom = await rom_handler.get_with_platform(rom_id)
    if not rom:
        raise HTTPException(status_code=404, detail="ROM not found")
    return rom


# ── Quota + My (must be before /{rom_id} pattern) ────────────────────────────

@protected_route(router.get, "/quota", scopes=[Scopes.LIBRARY_READ])
async def get_quota(request: Request) -> dict:
    user_id = request.state.user.id
    used  = await save_state_handler.get_user_total_size(user_id)
    limit = await _quota_limit(request.state.user)
    return {"used_bytes": used, "limit_bytes": limit}


@protected_route(router.get, "/my", scopes=[Scopes.LIBRARY_READ])
async def my_data(request: Request) -> dict:
    """All saves and states for the current user, each carrying its ROM's name,
    cover and platform so the saves UI can group them by game without N calls."""
    user_id = request.state.user.id
    states = await save_state_handler.list_all_states_for_user(user_id)
    saves  = await save_state_handler.list_all_saves_for_user(user_id)
    used   = await save_state_handler.get_user_total_size(user_id)
    limit  = await _quota_limit(request.state.user)
    roms   = await rom_handler.get_by_ids(
        [s.rom_id for s in states] + [s.rom_id for s in saves]
    )
    return {
        "states":      [_state_dict(s, roms.get(s.rom_id)) for s in states],
        "saves":       [_save_dict(s,  roms.get(s.rom_id)) for s in saves],
        "max_slot":    _MAX_SLOT,
        "used_bytes":  used,
        "limit_bytes": limit,
    }


# ── States ────────────────────────────────────────────────────────────────────

@protected_route(router.get, "/states/{state_id}/content", scopes=[Scopes.LIBRARY_READ])
async def download_state(request: Request, state_id: int):
    """Download the raw .state file."""
    user_id = request.state.user.id
    state = await save_state_handler.get_state(state_id, user_id)
    if not state:
        raise HTTPException(status_code=404, detail="State not found")
    fp = Path(state.file_path) / state.file_name
    if not fp.exists():
        raise HTTPException(status_code=404, detail="State file missing on disk")
    return FileResponse(str(fp), filename=state.file_name, media_type="application/octet-stream")


@router.get("/states/{state_id}/screenshot/{sig}.png")
async def state_screenshot(state_id: int, sig: str):
    """A savestate's thumbnail, addressed by an unguessable signed URL.

    Deliberately NOT @protected_route. Thumbnails render in plain <img> tags -
    in the saves panel, the home rails, the player's load menu and both theme
    plugins - and an <img> sends no Authorization header, which is the only
    thing AuthMiddleware reads. Every one of them would 401. The signature over
    the server secret takes the place of the session: nobody can enumerate these,
    and holding one URL grants one thumbnail.
    """
    if not screenshot_sig_valid(state_id, sig):
        raise HTTPException(status_code=404, detail="Not found")
    row = await save_state_handler.get_state_any(state_id)
    if not row or not row.screenshot_path:
        raise HTTPException(status_code=404, detail="Not found")
    fp = Path(row.screenshot_path)
    if not fp.exists():
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(str(fp), media_type="image/png")


@protected_route(router.delete, "/states/{state_id}", scopes=[Scopes.LIBRARY_READ])
async def delete_state(request: Request, state_id: int) -> dict:
    user_id = request.state.user.id
    state = await save_state_handler.get_state(state_id, user_id)
    if not state:
        raise HTTPException(status_code=404, detail="State not found")
    fp = Path(state.file_path) / state.file_name
    if fp.exists():
        fp.unlink()
    if state.screenshot_path:
        ss = Path(state.screenshot_path)
        if ss.exists():
            ss.unlink()
    await save_state_handler.delete_state(state_id, user_id)
    return {"ok": True}


@protected_route(router.post, "/{rom_id}/states", scopes=[Scopes.LIBRARY_READ])
async def upload_state(
    request: Request,
    rom_id: int,
    emulator_core: str | None = Form(None),
    slot: int | None = Form(None),
    stateFile: UploadFile = File(...),
    screenshotFile: UploadFile | None = File(None),
) -> dict:
    """Save into `slot` (1-9), replacing whatever occupied it - a slot holds one
    savestate, like a console memory card. Without a slot the save lands in
    slot 1, so a client that never learned about slots cannot pile up rows."""
    user_id = request.state.user.id
    rom = await _get_rom_or_404(rom_id)

    slot = 1 if slot is None else slot
    if not 1 <= slot <= _MAX_SLOT:
        raise HTTPException(status_code=400, detail=f"Slot must be 1-{_MAX_SLOT}")

    data = await stateFile.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty state file")
    if len(data) > _MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="State file too large (max 64 MB)")

    ss_data = await screenshotFile.read() if screenshotFile else b""
    if len(ss_data) > _MAX_SHOT_SIZE:
        raise HTTPException(status_code=413, detail="Screenshot too large (max 4 MB)")

    existing = await save_state_handler.get_state_by_slot(user_id, rom_id, slot)
    # Replacing a slot frees the old bytes, so only the growth counts against
    # quota - and both halves are weighed, before anything reaches the disk. A
    # kept thumbnail keeps its bytes, so it nets out to zero.
    old_bytes = 0
    if existing:
        old_bytes = existing.file_size_bytes or 0
        if ss_data:
            old_bytes += existing.screenshot_size_bytes or 0
    await _check_quota(request.state.user, len(data) + len(ss_data) - old_bytes)

    platform_slug = rom.platform.fs_slug if rom.platform else "unknown"
    save_dir = _states_dir(platform_slug, rom_id, user_id)
    save_dir.mkdir(parents=True, exist_ok=True)

    # Slot-stable names: re-saving a slot overwrites its file instead of leaving
    # an orphan behind (legacy rows keep their old timestamped names).
    stem     = _safe_stem(rom.name or rom.fs_name_no_ext or f"rom_{rom_id}")
    filename = f"{stem} [slot {slot}].state"
    state_fp = save_dir / filename
    state_fp.write_bytes(data)

    actor = request.state.user.username if getattr(request.state, "user", None) else None
    await _scan_or_reject(state_fp, username=actor)

    screenshot_path = None
    if ss_data:
        ss_fp = save_dir / f"{stem} [slot {slot}].png"
        ss_fp.write_bytes(ss_data)
        await _scan_or_reject(ss_fp, username=actor)
        screenshot_path = str(ss_fp)

    if existing:
        # A save without a fresh shot keeps the slot's previous thumbnail rather
        # than blanking the tile - so work out what the row will actually hold
        # BEFORE deciding what to delete. Handing _drop_stale_files the incoming
        # (None) shot had it unlink the very file the next line wrote back.
        retained_shot = screenshot_path or existing.screenshot_path
        retained_size = len(ss_data) if ss_data else (existing.screenshot_size_bytes or 0)
        _drop_stale_files(existing, keep={str(state_fp), retained_shot})
        state = await save_state_handler.update_state(existing.id, {
            "file_name":       filename,
            "file_path":       str(save_dir),
            "file_size_bytes": len(data),
            "emulator_core":   emulator_core,
            "screenshot_path": retained_shot,
            "screenshot_size_bytes": retained_size,
            "updated_at":      datetime.utcnow(),
        })
    else:
        try:
            state = await save_state_handler.create_state(RomSaveState(
                rom_id=rom_id,
                user_id=user_id,
                slot=slot,
                file_name=filename,
                file_path=str(save_dir),
                file_size_bytes=len(data),
                emulator_core=emulator_core,
                screenshot_path=screenshot_path,
                screenshot_size_bytes=len(ss_data),
            ))
        except IntegrityError:
            # Two saves into the same slot raced; the unique index kept the data
            # honest, so fold this one into the row the winner just created
            # rather than failing the user's save.
            state = await save_state_handler.get_state_by_slot(user_id, rom_id, slot)
            if state is None:
                raise
            state = await save_state_handler.update_state(state.id, {
                "file_name":       filename,
                "file_path":       str(save_dir),
                "file_size_bytes": len(data),
                "emulator_core":   emulator_core,
                "screenshot_path": screenshot_path or state.screenshot_path,
                "screenshot_size_bytes": (
                    len(ss_data) if ss_data else (state.screenshot_size_bytes or 0)
                ),
                "updated_at":      datetime.utcnow(),
            })
    return _state_dict(state, rom)


@protected_route(router.get, "/{rom_id}/states", scopes=[Scopes.LIBRARY_READ])
async def list_states(request: Request, rom_id: int) -> list[dict]:
    user_id = request.state.user.id
    await _get_rom_or_404(rom_id)
    states = await save_state_handler.list_states(user_id, rom_id)
    return [_state_dict(s) for s in states]


# ── Battery Saves ─────────────────────────────────────────────────────────────

@protected_route(router.get, "/saves/{save_id}/content", scopes=[Scopes.LIBRARY_READ])
async def download_save(request: Request, save_id: int):
    """Download the raw .srm file."""
    user_id = request.state.user.id
    save = await save_state_handler.get_save(save_id, user_id)
    if not save:
        raise HTTPException(status_code=404, detail="Save not found")
    fp = Path(save.file_path) / save.file_name
    if not fp.exists():
        raise HTTPException(status_code=404, detail="Save file missing on disk")
    return FileResponse(str(fp), filename=save.file_name, media_type="application/octet-stream")


@protected_route(router.delete, "/saves/{save_id}", scopes=[Scopes.LIBRARY_READ])
async def delete_save(request: Request, save_id: int) -> dict:
    user_id = request.state.user.id
    save = await save_state_handler.get_save(save_id, user_id)
    if not save:
        raise HTTPException(status_code=404, detail="Save not found")
    fp = Path(save.file_path) / save.file_name
    if fp.exists():
        fp.unlink()
    await save_state_handler.delete_save(save_id, user_id)
    return {"ok": True}


@protected_route(router.post, "/{rom_id}/saves", scopes=[Scopes.LIBRARY_READ])
async def upload_save(
    request: Request,
    rom_id: int,
    emulator_core: str | None = Form(None),
    slot: str | None = Form(None),
    saveFile: UploadFile = File(...),
) -> dict:
    """Store the cartridge SRAM. One row per ROM+core, overwritten in place: the
    .srm is the whole chip, so the game's own save slots already live inside it -
    keeping a row per change would only hoard copies of the same file (the
    in-player auto-sync uploads on every SRAM change)."""
    user_id = request.state.user.id
    rom = await _get_rom_or_404(rom_id)

    data = await saveFile.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty save file")
    if len(data) > _MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="Save file too large (max 64 MB)")

    content_hash  = hashlib.md5(data).hexdigest()
    platform_slug = rom.platform.fs_slug if rom.platform else "unknown"

    existing = await save_state_handler.get_save_for_rom(user_id, rom_id)

    # Unchanged SRAM → nothing to rewrite, just record that it is still current.
    if existing and existing.content_hash == content_hash:
        existing = await save_state_handler.update_save(
            existing.id, {"updated_at": datetime.utcnow()}
        )
        return _save_dict(existing, rom)

    # Overwriting frees the old bytes, so only the growth counts against quota.
    await _check_quota(
        request.state.user, len(data) - (existing.file_size_bytes if existing else 0)
    )

    save_dir = _saves_dir(platform_slug, rom_id, user_id)
    save_dir.mkdir(parents=True, exist_ok=True)

    stem     = _safe_stem(rom.name or rom.fs_name_no_ext or f"rom_{rom_id}")
    filename = f"{stem}.srm"
    srm_fp = save_dir / filename
    srm_fp.write_bytes(data)

    actor = request.state.user.username if getattr(request.state, "user", None) else None
    await _scan_or_reject(srm_fp, username=actor)

    if existing:
        _drop_stale_files(existing, keep={str(srm_fp)})

    # Upsert rather than read-then-insert: the player's two upload paths
    # (EJS_onSaveSave and the 60s auto-sync) can fire together, and both racers
    # would otherwise miss `existing` and insert their own row.
    save = await save_state_handler.upsert_save(user_id, rom_id, {
        "file_name":       filename,
        "file_path":       str(save_dir),
        "file_size_bytes": len(data),
        "emulator_core":   emulator_core,
        "slot":            slot or (existing.slot if existing else None),
        "content_hash":    content_hash,
        "updated_at":      datetime.utcnow(),
    })
    return _save_dict(save, rom)


@protected_route(router.get, "/{rom_id}/saves", scopes=[Scopes.LIBRARY_READ])
async def list_saves(request: Request, rom_id: int) -> list[dict]:
    user_id = request.state.user.id
    await _get_rom_or_404(rom_id)
    saves = await save_state_handler.list_saves(user_id, rom_id)
    return [_save_dict(s) for s in saves]


# ── Export / import ───────────────────────────────────────────────────────────
# A raw .state carries nothing but bytes: its screenshot stays here and nothing
# says which game or slot it was, so a reinstall cannot put it back. The archive
# fixes that; see utils/save_archive.py for the format.

def _archive_items(rows: list, roms: dict, kind: str) -> list[dict]:
    return [{
        "rom":  roms.get(r.rom_id),
        "row":  r,
        "kind": kind,
        "file_path": str(Path(r.file_path) / r.file_name),
        "screenshot_path": getattr(r, "screenshot_path", None),
    } for r in rows]


def _zip_response(path: Path, filename: str) -> FileResponse:
    return FileResponse(
        str(path),
        media_type="application/zip",
        filename=filename,
        # The archive is a temp file; drop it once it has been sent.
        background=BackgroundTask(lambda: path.unlink(missing_ok=True)),
    )


@protected_route(router.get, "/states/{state_id}/export", scopes=[Scopes.LIBRARY_READ])
async def export_state(request: Request, state_id: int):
    """One savestate, its screenshot and where it belongs, as a zip."""
    user_id = request.state.user.id
    state = await save_state_handler.get_state(state_id, user_id)
    if not state:
        raise HTTPException(status_code=404, detail="State not found")
    roms = await rom_handler.get_by_ids([state.rom_id])
    rom = roms.get(state.rom_id)
    path = await run_in_threadpool(build_archive, _archive_items([state], roms, "state"))
    stem = _safe_stem((rom.name if rom else None) or f"rom {state.rom_id}")
    slot = f" slot {state.slot}" if state.slot else ""
    return _zip_response(path, f"{stem}{slot}.zip")


@protected_route(router.get, "/saves/{save_id}/export", scopes=[Scopes.LIBRARY_READ])
async def export_save(request: Request, save_id: int):
    """One battery save and where it belongs, as a zip."""
    user_id = request.state.user.id
    save = await save_state_handler.get_save(save_id, user_id)
    if not save:
        raise HTTPException(status_code=404, detail="Save not found")
    roms = await rom_handler.get_by_ids([save.rom_id])
    rom = roms.get(save.rom_id)
    path = await run_in_threadpool(build_archive, _archive_items([save], roms, "battery"))
    stem = _safe_stem((rom.name if rom else None) or f"rom {save.rom_id}")
    return _zip_response(path, f"{stem} battery.zip")


@protected_route(router.get, "/export", scopes=[Scopes.LIBRARY_READ])
async def export_saves(request: Request, rom_id: int | None = None):
    """Every save this user holds, or just one game's (?rom_id=). The backup."""
    user_id = request.state.user.id
    states = await save_state_handler.list_all_states_for_user(user_id)
    saves  = await save_state_handler.list_all_saves_for_user(user_id)
    if rom_id is not None:
        states = [s for s in states if s.rom_id == rom_id]
        saves  = [s for s in saves  if s.rom_id == rom_id]
    if not states and not saves:
        raise HTTPException(status_code=404, detail="Nothing to export")

    roms = await rom_handler.get_by_ids([s.rom_id for s in states] + [s.rom_id for s in saves])
    items = _archive_items(states, roms, "state") + _archive_items(saves, roms, "battery")
    path = await run_in_threadpool(build_archive, items)

    if rom_id is not None:
        rom = roms.get(rom_id)
        name = f"{_safe_stem((rom.name if rom else None) or f'rom {rom_id}')} saves.zip"
    else:
        name = f"gd-saves-{datetime.utcnow().strftime('%Y-%m-%d')}.zip"
    return _zip_response(path, name)


def _mstr(value, limit: int) -> str | None:
    """One string field off an attacker-supplied manifest.

    Anything that is not a string is dropped rather than handed to the query or
    the column: a dict here reached SQLAlchemy as a comparison value, and an
    over-long emulator_core hit a String(50) and raised a DataError - neither is
    an HTTPException, so both escaped the per-entry catch as a 500 that stranded
    the restore halfway, with the earlier entries already committed.
    """
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value[:limit] or None


async def _match_rom(entry_rom: dict):
    """The ROM a restored entry belongs to on THIS install (ids do not travel)."""
    if not isinstance(entry_rom, dict):
        return None
    plat_slug = _mstr(entry_rom.get("platform_slug"), 128)
    plat = await rom_platform_handler.get_by_slug(plat_slug) if plat_slug else None
    return await rom_handler.find_for_import(
        sha1=_mstr(entry_rom.get("sha1"), 64),
        fs_name=_mstr(entry_rom.get("fs_name"), 512),
        name=_mstr(entry_rom.get("name"), 512),
        platform_id=plat.id if plat else None,
    )


async def _store_state(request: Request, rom, data: bytes, shot: bytes | None,
                       slot: int, core: str | None) -> str:
    """Write a savestate into `slot`, replacing whatever is there - the same rule
    the in-game save follows."""
    user_id = request.state.user.id
    if shot and len(shot) > _MAX_SHOT_SIZE:
        raise HTTPException(status_code=413, detail="Screenshot too large (max 4 MB)")
    existing = await save_state_handler.get_state_by_slot(user_id, rom.id, slot)
    # Both halves counted, before either touches the disk. Billing only the
    # state let an archive smuggle unlimited image bytes past the quota.
    old_bytes = 0
    if existing:
        old_bytes = existing.file_size_bytes or 0
        if shot:
            old_bytes += existing.screenshot_size_bytes or 0
    await _check_quota(request.state.user, len(data) + len(shot or b"") - old_bytes)

    platform_slug = rom.platform.fs_slug if rom.platform else "unknown"
    save_dir = _states_dir(platform_slug, rom.id, user_id)
    save_dir.mkdir(parents=True, exist_ok=True)
    stem = _safe_stem(rom.name or rom.fs_name_no_ext or f"rom_{rom.id}")
    filename = f"{stem} [slot {slot}].state"
    fp = save_dir / filename
    fp.write_bytes(data)

    actor = request.state.user.username
    await _scan_or_reject(fp, username=actor)

    shot_path = None
    if shot:
        ss_fp = save_dir / f"{stem} [slot {slot}].png"
        ss_fp.write_bytes(shot)
        await _scan_or_reject(ss_fp, username=actor)
        shot_path = str(ss_fp)

    if existing:
        # See upload_state: settle what the row keeps before deleting anything.
        retained_shot = shot_path or existing.screenshot_path
        retained_size = len(shot) if shot else (existing.screenshot_size_bytes or 0)
        _drop_stale_files(existing, keep={str(fp), retained_shot})
        await save_state_handler.update_state(existing.id, {
            "file_name": filename, "file_path": str(save_dir),
            "file_size_bytes": len(data), "emulator_core": core,
            "screenshot_path": retained_shot,
            "screenshot_size_bytes": retained_size,
            "updated_at": datetime.utcnow(),
        })
        return "replaced"
    try:
        await save_state_handler.create_state(RomSaveState(
            rom_id=rom.id, user_id=user_id, slot=slot, file_name=filename,
            file_path=str(save_dir), file_size_bytes=len(data),
            emulator_core=core, screenshot_path=shot_path,
            screenshot_size_bytes=len(shot or b""),
        ))
    except IntegrityError:
        # Raced with a concurrent write to the same slot; fold into the winner.
        row = await save_state_handler.get_state_by_slot(user_id, rom.id, slot)
        if row is None:
            raise
        await save_state_handler.update_state(row.id, {
            "file_name": filename, "file_path": str(save_dir),
            "file_size_bytes": len(data), "emulator_core": core,
            "screenshot_path": shot_path or row.screenshot_path,
            "screenshot_size_bytes": (
                len(shot) if shot else (row.screenshot_size_bytes or 0)
            ),
            "updated_at": datetime.utcnow(),
        })
        return "replaced"
    return "imported"


async def _store_battery(request: Request, rom, data: bytes, core: str | None) -> str:
    """Write the battery save - one per game, replaced in place."""
    user_id = request.state.user.id
    existing = await save_state_handler.get_save_for_rom(user_id, rom.id)
    await _check_quota(request.state.user,
                       len(data) - (existing.file_size_bytes if existing else 0))

    platform_slug = rom.platform.fs_slug if rom.platform else "unknown"
    save_dir = _saves_dir(platform_slug, rom.id, user_id)
    save_dir.mkdir(parents=True, exist_ok=True)
    stem = _safe_stem(rom.name or rom.fs_name_no_ext or f"rom_{rom.id}")
    filename = f"{stem}.srm"
    fp = save_dir / filename
    fp.write_bytes(data)
    await _scan_or_reject(fp, username=request.state.user.username)

    if existing:
        _drop_stale_files(existing, keep={str(fp)})
    await save_state_handler.upsert_save(user_id, rom.id, {
        "file_name": filename, "file_path": str(save_dir),
        "file_size_bytes": len(data), "emulator_core": core,
        "slot": existing.slot if existing else None,
        "content_hash": hashlib.md5(data).hexdigest(),
        "updated_at": datetime.utcnow(),
    })
    return "replaced" if existing else "imported"


async def _import_archive(request: Request, raw: bytes) -> list[dict]:
    """Restore every entry an archive carries, routing each by its manifest."""
    out: list[dict] = []
    with zipfile.ZipFile(io.BytesIO(raw)) as zf:
        manifest = read_manifest(zf)
        if manifest is None:
            raise HTTPException(
                status_code=400,
                detail="This zip is not a GamesDownloader save archive.",
            )
        entries = manifest.get("entries")
        if not isinstance(entries, list):
            raise HTTPException(status_code=400, detail="Malformed archive manifest.")
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            label = _mstr((entry.get("rom") or {}).get("name")
                          if isinstance(entry.get("rom"), dict) else None, 200) \
                or _mstr(entry.get("file"), 200) or "?"
            try:
                rom = await _match_rom(entry.get("rom") or {})
                if rom is None:
                    out.append({"name": label, "status": "no_rom"})
                    continue
                data = member_bytes(zf, _mstr(entry.get("file"), 512), _MAX_FILE_SIZE)
                shot = None
                if entry.get("screenshot"):
                    try:
                        shot = member_bytes(
                            zf, _mstr(entry.get("screenshot"), 512), _MAX_SHOT_SIZE
                        )
                    except (KeyError, ValueError):
                        shot = None   # a missing thumbnail must not lose the save
                # emulator_core lands in a String(50).
                core = _mstr(entry.get("emulator_core"), 50)
                if entry.get("kind") == "battery":
                    status = await _store_battery(request, rom, data, core)
                else:
                    try:
                        slot = int(entry.get("slot") or 1)
                    except (TypeError, ValueError):
                        slot = 1
                    if not 1 <= slot <= _MAX_SLOT:
                        slot = 1
                    status = await _store_state(request, rom, data, shot, slot, core)
                out.append({"name": rom.name or label, "slot": entry.get("slot"),
                            "kind": entry.get("kind"), "status": status})
            except HTTPException as exc:
                # Quota and virus rejections are per-entry; the rest still import.
                out.append({"name": label, "status": "error",
                            "detail": str(exc.detail)})
            except Exception as exc:
                # One bad entry must not strand a restore halfway through - the
                # entries before it are already committed and the user has no way
                # to tell how far it got.
                logger.exception("Import: entry %s failed", label)
                out.append({"name": label, "status": "error", "detail": str(exc)})
    return out


@protected_route(router.post, "/import", scopes=[Scopes.LIBRARY_READ])
async def import_saves(
    request: Request,
    files: list[UploadFile] = File(...),
    rom_id: int | None = Form(None),
    slot: int | None = Form(None),
) -> dict:
    """Restore saves.

    A GamesDownloader archive routes itself - the manifest names each entry's
    game and slot. A bare .state/.srm carries none of that, so the caller has to
    say which ROM (and, for a savestate, which slot) it belongs to.
    """
    results: list[dict] = []
    for f in files:
        raw = await f.read()
        name = (f.filename or "").lower()
        if not raw:
            results.append({"name": f.filename or "?", "status": "error",
                            "detail": "empty file"})
            continue
        if len(raw) > _MAX_FILE_SIZE:
            results.append({"name": f.filename or "?", "status": "error",
                            "detail": "file too large (max 64 MB)"})
            continue

        if name.endswith(".zip") or raw[:2] == b"PK":
            try:
                results.extend(await _import_archive(request, raw))
            except HTTPException:
                raise
            except (zipfile.BadZipFile, ValueError) as exc:
                results.append({"name": f.filename or "?", "status": "error",
                                "detail": str(exc)})
            continue

        # Bare file: the UI must have told us where it goes.
        if rom_id is None:
            results.append({"name": f.filename or "?", "status": "need_target"})
            continue
        rom = await _get_rom_or_404(rom_id)
        if name.endswith(".srm"):
            status = await _store_battery(request, rom, raw, None)
        elif name.endswith(".state"):
            _slot = slot or 1
            if not 1 <= _slot <= _MAX_SLOT:
                raise HTTPException(status_code=400, detail=f"Slot must be 1-{_MAX_SLOT}")
            status = await _store_state(request, rom, raw, None, _slot, None)
        else:
            results.append({"name": f.filename or "?", "status": "error",
                            "detail": "expected .zip, .state or .srm"})
            continue
        results.append({"name": rom.name or f.filename, "slot": slot,
                        "status": status})

    return {"results": results,
            "imported": sum(1 for r in results if r["status"] in ("imported", "replaced"))}
