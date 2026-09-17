"""Where the ROM library lives, answered in one place.

The root is `ROMS_PATH` unless an administrator moved it in Settings > ROMs, in
which case it is `roms.library_path`. Three call sites resolved that correctly
and each carried its own copy of the two lines; a fourth, the code that deletes
ROM files, reached for the bare constant instead.

That fourth one is why this module exists. Every deleter checks a path against
the root before unlinking, so on an install where the library had been moved the
containment check failed for every ROM at once: nothing was deleted from disk,
the endpoint reported `files_deleted: 0`, and the database row went anyway. The
row gone, the file still there, and the next scan bringing it back stripped of
its cover, its identifiers and its history.
"""

from __future__ import annotations

import logging
from pathlib import Path

from config import ROMS_PATH

logger = logging.getLogger(__name__)


def roms_library_path(config_manager=None) -> str:
    """The ROM library root this install is actually using.

    Takes the config manager so it can be handed a fake in a test; left out, it
    asks the real one. A blank setting is somebody clearing the field rather
    than a request to treat `/` as the ROM library, so it falls back too.
    """
    if config_manager is None:
        from config import config_manager as _cm

        config_manager = _cm
    try:
        section = config_manager.get_section("roms") or {}
    except Exception:  # noqa: BLE001 - an unreadable config is not a reason to
        return ROMS_PATH  # start deleting against the wrong root
    configured = (section.get("library_path") or "").strip()
    return configured or ROMS_PATH


def make_platform_folders(root: str, *, create_root: bool) -> dict:
    """One folder per known platform in *root*, so somebody filling the library
    over FTP or a file share knows where each platform's ROMs go.

    Only the canonical folder of a platform with several names: `psx`, not also
    `playstation`, since the scan walks every directory and a second one for the
    same machine is a second shelf for it. Nothing already there is touched.

    *create_root* is for the default library on a fresh install. A library moved
    in Settings that is not there - a typo, a disk not mounted into the
    container - is not made up: folders made there would live inside the
    container, invisible over FTP and gone when it is recreated.
    """
    from handler.metadata.rom_platform_map import PLATFORM_MAP, canonical_fs_slug

    base = Path(root)
    if not base.is_dir():
        if not create_root:
            return {"root_exists": False, "created": 0}
        base.mkdir(parents=True, exist_ok=True)

    created = 0
    for fs_slug in dict.fromkeys(canonical_fs_slug(s) for s in PLATFORM_MAP):
        folder = base / fs_slug
        if folder.exists():
            continue
        try:
            folder.mkdir()
            created += 1
        except OSError as exc:
            logger.warning("Could not make the platform folder %s: %s", folder, exc)
    return {"root_exists": True, "created": created}
