"""Where emulator saves live on disk, and how their thumbnails are addressed.

Saves are private user data. They live under SAVES_PATH, which is NOT mounted as
static files - the bytes are only reachable through the authenticated routes in
savestate_router, which check the row belongs to the caller.

Screenshots are the exception. They render in plain <img> tags (the saves panel,
the home rails, the player's load menu, and both theme plugins), and an <img>
request carries no Authorization header - AuthMiddleware reads only that header,
so an authenticated route would 401 every thumbnail. Instead each thumbnail gets
an unguessable URL signed with the server secret: no session needed, but nobody
can enumerate them either. Sharing such a URL shares one thumbnail, deliberately
and nothing else.

Both the savestate router and the dashboard handler build these paths and URLs,
so they live here rather than private to one caller - a lesson from the cover
aspect rule, which drifted while it was hidden inside the dashboard.
"""

from __future__ import annotations

import hmac
import logging
from hashlib import sha256
from pathlib import Path, PurePosixPath

from config import AUTH_SECRET_KEY, RESOURCES_PATH, SAVES_PATH
from utils.volume_check import is_ephemeral

logger = logging.getLogger(__name__)

_SIG_LEN = 24

# Where saves lived before they were moved off the public mount. Still the
# fallback for an install whose compose does not mount the new directory.
LEGACY_ROOT = Path(RESOURCES_PATH) / "roms"


_root_cache: Path | None = None


def saves_root() -> Path:
    """The directory tree holding save files.

    SAVES_PATH normally, but an install that never got the /data/saves mount
    keeps using the legacy location: losing someone's saves is worse than
    leaving them in a directory the static mount now refuses to serve anyway
    (see main.py's guard). Logged loudly, every boot, with the fix.
    """
    global _root_cache
    if _root_cache is not None:
        return _root_cache
    target = Path(SAVES_PATH)
    if is_ephemeral(target):
        logger.error(
            "GD_SAVES_PATH (%s) is not on a mounted volume - saves written there "
            "would be lost the next time the container is recreated. Falling back "
            "to %s. Fix this by adding a volume for it to your docker-compose.yml:"
            "\n    - ${GD_BASE_DIR}/data/saves:/data/saves\n"
            "then restart. Saves stay private either way: the resources mount no "
            "longer serves them.",
            target, LEGACY_ROOT,
        )
        _root_cache = LEGACY_ROOT
    else:
        _root_cache = target
    return _root_cache


def saves_root_is_legacy() -> bool:
    """True when the relocation must not run - there is nowhere safe to move to."""
    return saves_root() == LEGACY_ROOT


def states_dir(platform_slug: str, rom_id: int, user_id: int) -> Path:
    return saves_root() / platform_slug / str(rom_id) / "states" / str(user_id)


def saves_dir(platform_slug: str, rom_id: int, user_id: int) -> Path:
    return saves_root() / platform_slug / str(rom_id) / "saves" / str(user_id)


def superseded_dir() -> Path:
    """Where the startup migration parks battery saves it had to unlink from a
    row. Nothing here is ever read by the app - it exists so an admin can get a
    file back."""
    return saves_root() / "_superseded"


def is_save_path(rel: str) -> bool:
    """True for a path under the resources mount that holds save data.

    The static mount consults this so an install still keeping saves in the
    legacy location does not serve them to anyone who guesses the name. Two
    shapes live under the legacy root and both must be refused:

        roms/<slug>/<rom_id>/{states,saves}/<user_id>/<file>   the live saves
        roms/_superseded/<file>                                battery rows the
                                                               dedupe parked

    The dedupe is NOT gated by the legacy fallback the way the relocation is -
    it runs on every install once - so on an install with no /data/saves volume
    the parked .srm land right here under the public mount. Blocking the whole
    _superseded subtree keeps them private; the only thing an over-match could
    cost is a nonexistent platform whose slug is literally "_superseded", and a
    refused image beats a served save.

    Split with POSIX rules only: the static mount passes a forward-slash URL path
    and the deploy filesystem is Linux, so a backslash is an ordinary filename
    byte, not a separator. Rewriting "\\"->"/" here (as an earlier version did)
    would invent extra segments for a platform folder whose name contains a
    backslash and shift the states/saves marker off its index - serving that save.
    """
    parts = PurePosixPath(rel).parts
    if not parts or parts[0] != "roms":
        return False
    if len(parts) >= 2 and parts[1] == "_superseded":
        return True
    return len(parts) >= 5 and parts[3] in ("states", "saves")


def screenshot_sig(state_id: int) -> str:
    return hmac.new(
        AUTH_SECRET_KEY.encode(), f"shot:{state_id}".encode(), sha256
    ).hexdigest()[:_SIG_LEN]


def screenshot_sig_valid(state_id: int, sig: str) -> bool:
    return hmac.compare_digest(screenshot_sig(state_id), sig or "")


def screenshot_url(state_id: int | None, screenshot_path: str | None) -> str | None:
    """The signed URL for a savestate's thumbnail, or None when there is no file.

    The existence check keeps a blank tile from requesting a 404 on every render.
    """
    if not screenshot_path or state_id is None:
        return None
    if not Path(screenshot_path).exists():
        return None
    return f"/api/savestates/states/{state_id}/screenshot/{screenshot_sig(state_id)}.png"
