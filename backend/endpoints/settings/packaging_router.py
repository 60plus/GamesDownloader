"""
GOG download packaging settings.

Controls whether a downloaded GOG game's files are bundled into a single
archive per platform (windows/mac/linux), so users pull one file from the
server instead of dozens.
"""
from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

from decorators.auth import protected_route
from handler.auth.scopes import Scope
from handler.config.config_handler import config_handler
from handler.gog.zip_packer import KEY_DELETE_ORIGINALS, KEY_ENABLED

router = APIRouter(prefix="/api/settings/downloads/packaging", tags=["packaging"])


class PackagingConfig(BaseModel):
    zip_per_platform: bool = False   # master switch
    delete_originals:  bool = False  # remove loose files after a successful zip


@protected_route(router.get, "", scopes=[Scope.LIBRARY_ADMIN])
async def get_packaging_config(request: Request) -> PackagingConfig:
    return PackagingConfig(
        zip_per_platform = await config_handler.get_bool(KEY_ENABLED, default=False),
        delete_originals = await config_handler.get_bool(KEY_DELETE_ORIGINALS, default=False),
    )


@protected_route(router.post, "", scopes=[Scope.LIBRARY_ADMIN])
async def save_packaging_config(request: Request, data: PackagingConfig) -> dict:
    await config_handler.set_many({
        KEY_ENABLED:          (str(data.zip_per_platform).lower(), False),
        KEY_DELETE_ORIGINALS: (str(data.delete_originals).lower(), False),
    })
    return {"ok": True}
