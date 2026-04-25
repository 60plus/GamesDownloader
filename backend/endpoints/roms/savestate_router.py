"""Savestate and battery-save endpoints for the in-browser ROM emulator.

Prefix: /api/savestates

Routes:
  POST   /{rom_id}/states            upload savestate
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
import logging
import os
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse

from config import RESOURCES_PATH
from decorators.auth import protected_route
from handler.auth.scopes import Scope as Scopes
from handler.config.config_handler import config_handler
from handler.database.rom_handler import rom_handler
from handler.database.save_state_handler import save_state_handler
from models.rom_save_state import RomSave, RomSaveState

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/savestates", tags=["savestates"])

_DEFAULT_QUOTA = 100 * 1024 * 1024   # 100 MB
_MAX_FILE_SIZE  = 64 * 1024 * 1024   # 64 MB per file


# ── Helpers ───────────────────────────────────────────────────────────────────

def _states_dir(platform_slug: str, rom_id: int, user_id: int) -> Path:
    return Path(RESOURCES_PATH) / "roms" / platform_slug / str(rom_id) / "states" / str(user_id)


def _saves_dir(platform_slug: str, rom_id: int, user_id: int) -> Path:
    return Path(RESOURCES_PATH) / "roms" / platform_slug / str(rom_id) / "saves" / str(user_id)


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


async def _quota_limit() -> int:
    raw = await config_handler.get("saves_quota_bytes")
    try:
        return int(raw) if raw else _DEFAULT_QUOTA
    except ValueError:
        return _DEFAULT_QUOTA


async def _check_quota(user_id: int, extra: int) -> None:
    limit = await _quota_limit()
    used = await save_state_handler.get_user_total_size(user_id)
    if used + extra > limit:
        raise HTTPException(
            status_code=413,
            detail=(
                f"Save quota exceeded. Used {used // (1024 * 1024)} MB "
                f"of {limit // (1024 * 1024)} MB."
            ),
        )


def _screenshot_url(screenshot_path: str | None) -> str | None:
    if not screenshot_path:
        return None
    p = Path(screenshot_path)
    if not p.exists():
        return None
    try:
        rel = p.relative_to(RESOURCES_PATH)
        return "/resources/" + str(rel).replace("\\", "/")
    except ValueError:
        return None


def _state_dict(s: RomSaveState) -> dict:
    return {
        "id":             s.id,
        "rom_id":         s.rom_id,
        "file_name":      s.file_name,
        "file_size_bytes": s.file_size_bytes,
        "emulator_core":  s.emulator_core,
        "screenshot_url": _screenshot_url(s.screenshot_path),
        "created_at":     s.created_at.isoformat() if s.created_at else None,
        "updated_at":     s.updated_at.isoformat() if s.updated_at else None,
        "download_url":   f"/api/savestates/states/{s.id}/content",
    }


def _save_dict(s: RomSave) -> dict:
    return {
        "id":             s.id,
        "rom_id":         s.rom_id,
        "file_name":      s.file_name,
        "file_size_bytes": s.file_size_bytes,
        "emulator_core":  s.emulator_core,
        "slot":           s.slot,
        "created_at":     s.created_at.isoformat() if s.created_at else None,
        "updated_at":     s.updated_at.isoformat() if s.updated_at else None,
        "download_url":   f"/api/savestates/saves/{s.id}/content",
    }


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
    limit = await _quota_limit()
    return {"used_bytes": used, "limit_bytes": limit}


@protected_route(router.get, "/my", scopes=[Scopes.LIBRARY_READ])
async def my_data(request: Request) -> dict:
    """All saves and states for the current user - used by the profile page."""
    user_id = request.state.user.id
    states = await save_state_handler.list_all_states_for_user(user_id)
    saves  = await save_state_handler.list_all_saves_for_user(user_id)
    used   = await save_state_handler.get_user_total_size(user_id)
    limit  = await _quota_limit()
    return {
        "states":      [_state_dict(s) for s in states],
        "saves":       [_save_dict(s)  for s in saves],
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
    stateFile: UploadFile = File(...),
    screenshotFile: UploadFile | None = File(None),
) -> dict:
    user_id = request.state.user.id
    rom = await _get_rom_or_404(rom_id)

    data = await stateFile.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty state file")
    if len(data) > _MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="State file too large (max 64 MB)")
    await _check_quota(user_id, len(data))

    platform_slug = rom.platform.fs_slug if rom.platform else "unknown"
    save_dir = _states_dir(platform_slug, rom_id, user_id)
    save_dir.mkdir(parents=True, exist_ok=True)

    ts       = datetime.utcnow().strftime("%Y-%m-%d %H-%M-%S")
    rom_name = (rom.name or rom.fs_name_no_ext or f"rom_{rom_id}")[:80]
    filename = f"{rom_name} [{ts}].state"
    state_fp = save_dir / filename
    state_fp.write_bytes(data)

    actor = request.state.user.username if getattr(request.state, "user", None) else None
    await _scan_or_reject(state_fp, username=actor)

    screenshot_path = None
    if screenshotFile:
        ss_data = await screenshotFile.read()
        if ss_data:
            ss_name = filename.replace(".state", ".png")
            ss_fp   = save_dir / ss_name
            ss_fp.write_bytes(ss_data)
            await _scan_or_reject(ss_fp, username=actor)
            screenshot_path = str(ss_fp)

    state = await save_state_handler.create_state(RomSaveState(
        rom_id=rom_id,
        user_id=user_id,
        file_name=filename,
        file_path=str(save_dir),
        file_size_bytes=len(data),
        emulator_core=emulator_core,
        screenshot_path=screenshot_path,
    ))
    return _state_dict(state)


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
    user_id = request.state.user.id
    rom = await _get_rom_or_404(rom_id)

    data = await saveFile.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty save file")
    if len(data) > _MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="Save file too large (max 64 MB)")
    await _check_quota(user_id, len(data))

    content_hash  = hashlib.md5(data).hexdigest()
    platform_slug = rom.platform.fs_slug if rom.platform else "unknown"

    # Dedup: same content hash → just touch updated_at
    existing = await save_state_handler.get_save_by_hash(user_id, rom_id, content_hash)
    if existing:
        existing = await save_state_handler.update_save(existing.id, {"updated_at": datetime.utcnow()})
        return _save_dict(existing)

    save_dir = _saves_dir(platform_slug, rom_id, user_id)
    save_dir.mkdir(parents=True, exist_ok=True)

    ts       = datetime.utcnow().strftime("%Y-%m-%d %H-%M-%S")
    rom_name = (rom.name or rom.fs_name_no_ext or f"rom_{rom_id}")[:80]
    filename = f"{rom_name} [{ts}].srm"
    srm_fp = save_dir / filename
    srm_fp.write_bytes(data)

    actor = request.state.user.username if getattr(request.state, "user", None) else None
    await _scan_or_reject(srm_fp, username=actor)

    save = await save_state_handler.create_save(RomSave(
        rom_id=rom_id,
        user_id=user_id,
        file_name=filename,
        file_path=str(save_dir),
        file_size_bytes=len(data),
        emulator_core=emulator_core,
        slot=slot,
        content_hash=content_hash,
    ))
    return _save_dict(save)


@protected_route(router.get, "/{rom_id}/saves", scopes=[Scopes.LIBRARY_READ])
async def list_saves(request: Request, rom_id: int) -> list[dict]:
    user_id = request.state.user.id
    await _get_rom_or_404(rom_id)
    saves = await save_state_handler.list_saves(user_id, rom_id)
    return [_save_dict(s) for s in saves]
