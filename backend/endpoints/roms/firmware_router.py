"""Emulator firmware endpoints.

Prefix: /api/firmware

IMPORTANT: The protected_route decorator always passes `request` as the first
positional argument to the wrapped function.  Therefore every endpoint function
MUST have `request: Request` as its very first parameter, before any path /
query / body params - otherwise FastAPI will receive "multiple values" errors.

On the split of permissions: managing the store is an administrator's job, but
fetching the bundle is not.  The emulator runs in the player's own browser, so
the bytes have to reach whoever is allowed to play; gating the bundle behind
the admin scope would simply mean nobody could start a game that needs a BIOS.
Anyone who can play a ROM can therefore read the firmware for it, which is a
property of running an emulator client-side rather than a decision made here.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response

from decorators.auth import protected_route
from handler.auth.scopes import Scope as Scopes
from handler.roms import firmware_handler
from handler.roms.firmware_registry import FIRMWARE, LIBRETRO_CORE, for_core

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/firmware", tags=["firmware"])


@protected_route(router.get, "", scopes=[Scopes.LIBRARY_ADMIN])
async def list_cores(request: Request) -> list[dict]:
    """Every core that asks for firmware, with how much of it is on hand."""
    out: list[dict] = []
    for core in sorted(FIRMWARE):
        st = firmware_handler.status(core)
        out.append(
            {
                "core": core,
                "libretro_core": LIBRETRO_CORE.get(core),
                "total": len(st),
                "present": sum(1 for s in st if s["present"]),
                "required": sum(1 for s in st if not s["optional"]),
                "missing_required": len(firmware_handler.missing_required(core)),
            }
        )
    return out


@protected_route(router.get, "/{ejs_core}", scopes=[Scopes.LIBRARY_ADMIN])
async def core_status(request: Request, ejs_core: str) -> dict:
    """What *ejs_core* asks for, and which of those files are stored."""
    if ejs_core not in FIRMWARE:
        raise HTTPException(status_code=404, detail="This core does not ask for firmware")
    return {
        "core": ejs_core,
        "libretro_core": LIBRETRO_CORE.get(ejs_core),
        "files": firmware_handler.status(ejs_core),
    }


@protected_route(router.post, "/{ejs_core}", scopes=[Scopes.LIBRARY_ADMIN])
async def upload_firmware(
    request: Request,
    ejs_core: str,
    path: str = Form(...),
    file: UploadFile = File(...),
) -> dict:
    """Store an uploaded file under one of the names *ejs_core* looks for."""
    if ejs_core not in FIRMWARE:
        raise HTTPException(status_code=404, detail="This core does not ask for firmware")
    data = await file.read()
    try:
        return firmware_handler.store(ejs_core, path, data)
    except ValueError as exc:
        # Either the name is not one this core looks for, or the file is
        # implausible as firmware. Both are the caller's mistake, not a fault.
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@protected_route(router.delete, "/{ejs_core}", scopes=[Scopes.LIBRARY_ADMIN])
async def delete_firmware(request: Request, ejs_core: str, path: str) -> dict:
    """Drop a stored file."""
    try:
        removed = firmware_handler.remove(ejs_core, path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not removed:
        raise HTTPException(status_code=404, detail="No such firmware is stored")
    return {"removed": path}


@protected_route(router.get, "/{ejs_core}/bundle", scopes=[Scopes.ROMS_READ])
async def firmware_bundle(request: Request, ejs_core: str) -> Response:
    """Everything stored for *ejs_core*, zipped under the paths the core expects.

    204 when nothing is stored, so the player can skip unpacking rather than
    reason about an empty archive.
    """
    if ejs_core not in FIRMWARE:
        return Response(status_code=204)
    data = firmware_handler.bundle(ejs_core)
    if data is None:
        return Response(status_code=204)
    return Response(
        content=data,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{ejs_core}-firmware.zip"',
            # Firmware changes only when an administrator uploads something, but
            # a stale copy would silently keep a game unplayable after they fix
            # it, which is exactly the confusion this feature exists to end.
            "Cache-Control": "no-store",
        },
    )


@protected_route(router.get, "/{ejs_core}/offers", scopes=[Scopes.LIBRARY_ADMIN])
async def firmware_offers(request: Request, ejs_core: str) -> dict:
    """Missing files an installed plugin says it could fetch.

    Empty when nothing offers anything, which is also the answer when no plugin
    is installed. The screen works either way; this only decides whether a
    "fetch" button appears next to a file.
    """
    if ejs_core not in FIRMWARE:
        raise HTTPException(status_code=404, detail="This core does not ask for firmware")
    return {"core": ejs_core, "offers": firmware_handler.offers(ejs_core)}


@protected_route(router.post, "/{ejs_core}/fetch", scopes=[Scopes.LIBRARY_ADMIN])
async def fetch_firmware(request: Request, ejs_core: str, path: str = Form(...)) -> dict:
    """Have core download a file a plugin offered, and store it."""
    if ejs_core not in FIRMWARE:
        raise HTTPException(status_code=404, detail="This core does not ask for firmware")
    try:
        return await firmware_handler.fetch_from_plugin(ejs_core, path)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        # The plugin's URL, its credentials and the upstream's error text all
        # pass through here; only the shape of the failure is worth reporting.
        logger.warning("firmware fetch failed for %s/%s: %s", ejs_core, path, type(exc).__name__)
        raise HTTPException(status_code=502, detail="The source could not be reached") from exc


@protected_route(router.get, "/{ejs_core}/required", scopes=[Scopes.ROMS_READ])
async def missing_required(request: Request, ejs_core: str) -> dict:
    """Mandatory files still missing, so a player can be told what to ask for."""
    missing = firmware_handler.missing_required(ejs_core)
    return {
        "core": ejs_core,
        "declares_firmware": ejs_core in FIRMWARE,
        "total_declared": len(for_core(ejs_core)),
        "missing": [{"path": f.path, "desc": f.desc} for f in missing],
    }
