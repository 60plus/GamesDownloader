"""Download speed limit settings - global and per-user."""
from __future__ import annotations

import json

from fastapi import APIRouter, Request
from pydantic import BaseModel

from decorators.auth import protected_route
from handler.auth.scopes import Scope
from handler.config.config_handler import config_handler
from handler.database.users_handler import UsersHandler

router = APIRouter(prefix="/api/settings/downloads/speed", tags=["speed-limit"])
_users = UsersHandler()

_KEY_GLOBAL = "dl_speed_global_kbps"   # "0" = no limit
_KEY_USERS  = "dl_user_speeds"         # JSON: {"username": kbps_int, ...}


async def _get_user_speeds() -> dict[str, int]:
    raw = await config_handler.get(_KEY_USERS)
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except Exception:
        return {}


class SpeedConfig(BaseModel):
    global_kbps:  int             = 0    # 0 = no limit
    user_limits:  dict[str, int]  = {}   # username → kbps (0 = use global)


@protected_route(router.get, "", scopes=[Scope.LIBRARY_ADMIN])
async def get_speed_config(request: Request) -> SpeedConfig:
    raw = await config_handler.get(_KEY_GLOBAL) or "0"
    try:
        global_kbps = int(raw)
    except ValueError:
        global_kbps = 0
    return SpeedConfig(
        global_kbps = global_kbps,
        user_limits = await _get_user_speeds(),
    )


@protected_route(router.post, "", scopes=[Scope.LIBRARY_ADMIN])
async def save_speed_config(request: Request, data: SpeedConfig) -> dict:
    clean_limits = {u: max(0, v) for u, v in data.user_limits.items()}
    await config_handler.set_many({
        _KEY_GLOBAL: (str(max(0, data.global_kbps)), False),
        _KEY_USERS:  (json.dumps(clean_limits),       False),
    })
    return {"ok": True}
