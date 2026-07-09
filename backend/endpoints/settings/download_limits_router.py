"""Upload/quota limits + GOG auto-adopt settings (Settings > Downloads).

These are global defaults, stored in app_config. Per-user upload/quota overrides
live on User.permissions and are managed from Settings > Users; the read paths
(upload_router / savestate_router) resolve per-user override -> this global ->
hardcoded default.
"""
from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel

from decorators.auth import protected_route
from handler.auth.scopes import Scope
from handler.config.config_handler import config_handler

router = APIRouter(prefix="/api/settings/downloads/limits", tags=["download-limits"])

_DEFAULT_UPLOAD = 50 * 1024 ** 3       # 50 GB
_DEFAULT_QUOTA  = 100 * 1024 * 1024    # 100 MB


async def _int(key: str, default: int) -> int:
    raw = await config_handler.get(key)
    try:
        return int(raw) if raw else default
    except ValueError:
        return default


class LimitsConfig(BaseModel):
    max_upload_bytes:            int  = _DEFAULT_UPLOAD   # 0/unset falls back to the default (not unlimited)
    saves_quota_bytes:          int  = _DEFAULT_QUOTA
    gog_auto_publish_downloaded: bool = True


@protected_route(router.get, "", scopes=[Scope.LIBRARY_ADMIN])
async def get_limits(request: Request) -> LimitsConfig:
    return LimitsConfig(
        max_upload_bytes            = await _int("max_upload_bytes", _DEFAULT_UPLOAD),
        saves_quota_bytes           = await _int("saves_quota_bytes", _DEFAULT_QUOTA),
        gog_auto_publish_downloaded = await config_handler.get_bool("gog_auto_publish_downloaded", default=True),
    )


@protected_route(router.post, "", scopes=[Scope.LIBRARY_ADMIN])
async def set_limits(request: Request, data: LimitsConfig) -> dict:
    await config_handler.set_many({
        "max_upload_bytes":            (str(max(0, data.max_upload_bytes)),  False),
        "saves_quota_bytes":           (str(max(0, data.saves_quota_bytes)), False),
        "gog_auto_publish_downloaded": (str(bool(data.gog_auto_publish_downloaded)).lower(), False),
    })
    return {"ok": True}
