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

from config import ROMS_PATH


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
