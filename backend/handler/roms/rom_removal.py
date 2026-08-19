"""Taking a ROM out of the library, and everything that hangs off it.

Deleting the row is the easy half. What made this worth its own module is the
rest: a ROM row is the anchor for scraped artwork, for every player's saves,
and - when the title arrived on several floppies - for its sibling rows. Drop
the row alone and all of that becomes unreachable bytes nobody can find, let
alone remove.

Three rules decide what goes:

  * the whole set goes together. Deleting disk 1 of a three-disk game leaves
    two entries that cannot be started and cannot be grouped back.
  * saves go with the row, always. They are reached through the ROM and
    through nothing else, so a row that is gone takes them with it. This is
    the destructive part and the caller has to have said so out loud.
  * the ROM file itself goes only when asked. It is the one thing here the
    player supplied rather than GD generated, and putting it back means
    finding the dump again.

Every path is checked against the directory it is supposed to be under before
anything is unlinked. A row's stored path is data, and data that decides what
gets deleted is worth distrusting.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

from config import RESOURCES_PATH, ROMS_PATH, SAVES_PATH

logger = logging.getLogger(__name__)


@dataclass
class Removal:
    """What came off the disk, for the sentence the player is shown."""

    roms: int = 0
    rom_files: int = 0
    saves: int = 0
    media_dirs: int = 0
    names: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "roms_deleted": self.roms,
            "files_deleted": self.rom_files,
            "saves_deleted": self.saves,
            "names": self.names,
        }


def _within(path: str | None, root: str) -> Path | None:
    """The absolute path, but only if it really sits under *root*.

    A stored path is not trusted to stay where it was put: symlinks and "../"
    both lead out of the directory, and this function is the last thing between
    a row in the database and an unlink.
    """
    if not path:
        return None
    try:
        candidate = Path(path).resolve()
        base = Path(root).resolve()
    except OSError:
        return None
    return candidate if candidate == base or base in candidate.parents else None


def _unlink(path: Path) -> bool:
    try:
        path.unlink()
        return True
    except OSError:
        logger.warning("Could not delete %s", path, exc_info=True)
        return False


def _prune_empty(start: Path, root: str) -> None:
    """Walk up removing directories that are now empty, stopping at *root*."""
    base = Path(root).resolve()
    cur = start
    while cur != base and base in cur.parents:
        try:
            cur.rmdir()          # refuses while anything is left inside
        except OSError:
            return
        cur = cur.parent


def delete_save_files(save_states, saves) -> int:
    """Remove the files behind a player's savestates and battery saves.

    Called whichever way the ROM goes, because the rows that point at these are
    cascaded away with it: what is left otherwise is bytes charged against a
    quota with nothing in the interface able to reach them.
    """
    removed = 0
    touched: set[Path] = set()
    for state in save_states:
        target = _within(os.path.join(state.file_path, state.file_name), SAVES_PATH)
        if target and target.is_file() and _unlink(target):
            removed += 1
            touched.add(target.parent)
        # The thumbnail is not counted: it is GD's picture of the save, not the
        # save, and saying "2 saves removed" for one is worse than saying one.
        shot = _within(state.screenshot_path, SAVES_PATH)
        if shot and shot.is_file() and _unlink(shot):
            touched.add(shot.parent)
    for save in saves:
        target = _within(os.path.join(save.file_path, save.file_name), SAVES_PATH)
        if target and target.is_file() and _unlink(target):
            removed += 1
            touched.add(target.parent)
    for d in sorted(touched, key=lambda p: len(str(p)), reverse=True):
        _prune_empty(d, SAVES_PATH)
    return removed


def delete_rom_file(rom) -> bool:
    """Remove the ROM itself, and any directory it leaves empty behind it."""
    target = _within(os.path.join(rom.fs_path, rom.fs_name), ROMS_PATH)
    if not target or not target.is_file():
        return False
    if not _unlink(target):
        return False
    _prune_empty(target.parent, ROMS_PATH)
    return True


def delete_media_dir(platform_slug: str, rom_id: int) -> bool:
    """Remove the scraped artwork GD downloaded for this ROM.

    Always removed: every file in here was fetched by GD and can be fetched
    again, and none of it means anything once the ROM it describes is gone.
    """
    media = _within(str(Path(RESOURCES_PATH) / "roms" / platform_slug / str(rom_id)),
                    RESOURCES_PATH)
    if not media or not media.is_dir():
        return False
    for child in sorted(media.rglob("*"), key=lambda p: len(str(p)), reverse=True):
        if child.is_file() or child.is_symlink():
            _unlink(child)
        elif child.is_dir():
            try:
                child.rmdir()
            except OSError:
                pass
    try:
        media.rmdir()
    except OSError:
        return False
    _prune_empty(media.parent, RESOURCES_PATH)
    return True
