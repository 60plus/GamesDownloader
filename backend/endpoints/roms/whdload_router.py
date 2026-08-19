"""WHDLoad endpoints - the Amiga hard-drive installs EmulatorJS cannot run.

Prefix: /api/whdload

IMPORTANT: The protected_route decorator always passes `request` as the first
positional argument to the wrapped function.  Therefore every endpoint function
MUST have `request: Request` as its very first parameter, before any path /
query / body params - otherwise FastAPI will receive "multiple values" errors.

The permission split follows the firmware router's, and for the same reason:
assembling the shared pieces is an administrator's job, but the hard-drive image
is read by the emulator running in the player's own browser, so it has to reach
whoever is allowed to play the ROM.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response

from decorators.auth import protected_route
from handler.auth.scopes import Scope as Scopes
from handler.database.rom_handler import rom_handler
from handler.database.save_state_handler import save_state_handler
from handler.roms import amiga_disk, whdload_handler

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/whdload", tags=["whdload"])


async def _rom_file(rom_id: int) -> Path:
    rom = await rom_handler.get_by_id(rom_id)
    if not rom:
        raise HTTPException(status_code=404, detail="ROM not found")
    path = Path(rom.fs_path) / rom.fs_name
    if not path.is_file():
        raise HTTPException(status_code=404, detail="ROM file not found on disk")
    return path


# ── Shared pieces ─────────────────────────────────────────────────────────────

@protected_route(router.get, "/support", scopes=[Scopes.LIBRARY_ADMIN])
async def support(request: Request) -> dict:
    """What WHDLoad needs beyond the game itself, and what is already stored."""
    return await asyncio.to_thread(whdload_handler.support_status)


@protected_route(router.post, "/support", scopes=[Scopes.LIBRARY_ADMIN])
async def upload_support(
    request: Request,
    name: str = Form(...),
    file: UploadFile = File(...),
) -> dict:
    """Store the WHDLoad executable or a relocation table."""
    data = await file.read()
    try:
        return whdload_handler.store_support_file(name, data)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@protected_route(router.delete, "/support", scopes=[Scopes.LIBRARY_ADMIN])
async def delete_support(request: Request, name: str) -> dict:
    """Drop a stored WHDLoad file, so a bad one can be replaced."""
    try:
        removed = await asyncio.to_thread(whdload_handler.remove_support_file, name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not removed:
        raise HTTPException(status_code=404, detail="No such file is stored")
    return {"removed": name}


@protected_route(router.post, "/support/fetch", scopes=[Scopes.LIBRARY_ADMIN])
async def fetch_support(request: Request, name: str | None = None) -> dict:
    """Download the freely-published pieces. Never the Kickstart.

    Without *name* everything missing is fetched; with it, just that one, which
    is what the button beside a single row asks for.
    """
    try:
        return await whdload_handler.fetch_support(name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        # Upstream error text can carry a URL or a redirect chain; the shape of
        # the failure is all the caller needs.
        logger.warning("WHDLoad support fetch failed: %s", type(exc).__name__)
        raise HTTPException(status_code=502, detail="The source could not be reached") from exc


# ── Per-ROM ───────────────────────────────────────────────────────────────────

@protected_route(router.get, "/{rom_id}/plan", scopes=[Scopes.LIBRARY_READ])
async def rom_plan(request: Request, rom_id: int) -> dict:
    """Whether this title can run, and how the machine should be configured.

    Answers for any Amiga ROM, not only a WHDLoad one: a floppy comes back as
    mode "floppy" and always runs, because the emulator carries AROS. Asked
    before the emulator starts so a missing Kickstart is a sentence on screen
    rather than a requester inside a booted Amiga.
    """
    rom_file = await _rom_file(rom_id)
    p = await asyncio.to_thread(whdload_handler.plan, rom_file)
    return {
        "mode": p.mode,
        "ok": p.ok,
        "missing": list(p.missing),
        "kickstart": p.kickstart,
        "machine": p.machine,
        "slave": p.slave,
        "warning": p.warning,
        "disks": list(p.disks),
        # Floppy titles get a disk of their own to save onto; a WHDLoad install
        # writes its saves to the hard drive it runs from.
        "save_disk": None if p.mode == "harddrive" else whdload_handler.SAVE_DISK_NAME,
    }


@protected_route(router.get, "/kickstart", scopes=[Scopes.LIBRARY_READ])
async def boot_kickstart(request: Request) -> Response:
    """The ROM the emulated machine boots from, as bytes.

    204 when there is none, which is not a failure: the emulator carries AROS
    and plays a floppy without any Kickstart at all. Reachable by anyone who can
    play, for the same reason the firmware bundle is - the emulator runs in
    their browser, so the bytes have to get there.
    """
    ks = await asyncio.to_thread(whdload_handler.available_kickstart)
    if ks is None:
        return Response(status_code=204)
    data = await asyncio.to_thread(whdload_handler.read_kickstart, ks[0])
    if data is None:
        return Response(status_code=204)
    return Response(
        content=data,
        media_type="application/octet-stream",
        headers={"X-GD-Kickstart": ks[0], "Cache-Control": "no-store"},
    )


async def _save_disk_for(user_id: int, rom_id: int, name: str) -> bytes:
    """The floppy this player's saves live on, or a fresh one.

    An Amiga game writes its saves to a disk, so GD's battery slot holds one.
    Handing back a blank on the first run is what lets the game write at all -
    an unformatted image gets refused as "not a DOS disk", and there is no
    Workbench in the browser to format it with.

    The name matters as much as the format: a title asks for its save disk by
    name and ignores anything else. But the name on a disk the player has
    already used belongs to the game, not to GD - Dungeon Master calls its own
    disk "DungeonSave" and stops recognising it the moment anything else does.
    So a name is only ever put on a disk GD named itself: correcting the
    setting still reaches a disk nobody has written to, and a disk the game has
    claimed is left exactly as it is.
    """
    saves = await save_state_handler.list_saves(user_id, rom_id)
    for save in saves:
        path = Path(save.file_path) / save.file_name
        if path.is_file():
            data = await asyncio.to_thread(path.read_bytes)
            if len(data) != amiga_disk.ADF_SIZE:
                logger.warning("Ignoring save %s: %d bytes is not a floppy", save.id, len(data))
                continue
            if amiga_disk.volume_name(data) != name and amiga_disk.untouched(data):
                data = await asyncio.to_thread(amiga_disk.rename, data, name)
            return data
    return await asyncio.to_thread(amiga_disk.blank_adf, name)


async def _hd_saves_for(user_id: int, rom_id: int) -> bytes | None:
    """What this player's WHDLoad install differs by, or nothing saved yet.

    WHDLoad writes its saves onto the hard drive it runs from, and that drive is
    rebuilt from the archive on every launch - so the browser sends back the
    files that changed, and they are laid over the game the next time it is
    built.

    Kept in the same slot a floppy title uses for its save disk, so the quota,
    the upload button, the download and the delete all already know about it.
    The two are told apart by shape rather than a flag: a floppy save is exactly
    one ADF, this is a ZIP.
    """
    for save in await save_state_handler.list_saves(user_id, rom_id):
        path = Path(save.file_path) / save.file_name
        if not path.is_file():
            continue
        data = await asyncio.to_thread(path.read_bytes)
        if data[:2] != b"PK":
            logger.warning("Ignoring save %s for a WHDLoad title: not a ZIP", save.id)
            continue
        # Checked here rather than left to the builder, which refuses outright.
        # Refusing there would mean an oversized save stops the title from
        # starting at all, and a game the player can still play beats a game
        # held hostage by one bad upload.
        if len(data) > whdload_handler.MAX_SAVE_BYTES:
            logger.warning(
                "Ignoring save %s for a WHDLoad title: %d bytes is past the limit",
                save.id, len(data),
            )
            continue
        return data
    return None


@protected_route(router.get, "/{rom_id}/image", scopes=[Scopes.LIBRARY_READ])
async def rom_image(request: Request, rom_id: int) -> Response:
    """The ZIP the emulator turns into a hard drive, or a set of floppies."""
    archive = await _rom_file(rom_id)
    save_disk = None
    saves = None
    if whdload_handler.looks_like_whdload(archive):
        saves = await _hd_saves_for(request.state.user.id, rom_id)
    else:
        # A floppy title saves to a disk, so it gets one of its own.
        rom = await rom_handler.get_by_id(rom_id)
        name = (rom.save_disk_name or "").strip() if rom else ""
        save_disk = await _save_disk_for(request.state.user.id, rom_id, name or "Saves")
    try:
        data = await asyncio.to_thread(whdload_handler.build_image, archive, save_disk, saves)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    return Response(
        content=data,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{archive.stem}.zip"',
            # Rebuilt from the archive and the current support files every time.
            # A cached copy would keep serving a hard drive built around the
            # Kickstart that was there before the admin replaced it.
            "Cache-Control": "no-store",
        },
    )
