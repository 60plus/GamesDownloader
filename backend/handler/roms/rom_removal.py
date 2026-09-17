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

import asyncio
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

from config import RESOURCES_PATH, ROMS_PATH, SAVES_PATH
from handler.filesystem.rom_paths import roms_library_path

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


def delete_rom_file(rom, *, spoken_for: set[str] = frozenset()) -> bool:
    """Remove the ROM itself, and any directory it leaves empty behind it.

    *spoken_for* names files another sheet still points at. A track that became
    a row of its own is a member of its sheet's set and is deleted with it, so
    without this the file went whichever of the two sheets naming it was deleted
    first - and the survivor was left naming a file that is not there.
    """
    if rom.fs_name.lower() in spoken_for:
        return False
    target = _within(os.path.join(rom.fs_path, rom.fs_name), roms_library_path())
    if not target or not target.is_file():
        return False
    if not _unlink(target):
        return False
    _prune_empty(target.parent, roms_library_path())
    return True


def spoken_for_elsewhere(members) -> set[str]:
    """Lower-cased names of files some *other* sheet in the same directory names.

    Two rips of one game can sit side by side and name the same data file - two
    regional versions of a .cue, or a .gdi and a .cue kept together. The scanner
    hands that file to whichever sheet sorts first and the other one keeps no
    claim on it, which is a reasonable way to decide what the library shows and
    a catastrophic way to decide what a delete may take: the file is the only
    copy and the sheet left holding nothing is unplayable ever after.

    So deletion asks a different question from scanning. Not "whose is it" but
    "is anybody else still pointing at it" - and if anybody is, it stays,
    whichever way the scanner happened to rule.

    Sheets belonging to the set being deleted are not "anybody else". They are
    going too.
    """
    from handler.filesystem.rom_scanner import SHEET_EXTENSIONS, tracks_referenced_by

    ours: dict[Path, set[str]] = {}
    for member in members:
        ours.setdefault(Path(member.fs_path), set()).add(member.fs_name.lower())

    claimed: set[str] = set()
    for directory, mine in ours.items():
        try:
            beside = sorted(directory.iterdir())
        except OSError:
            continue
        for entry in beside:
            if entry.name.lower() in mine:
                continue
            if entry.suffix.lower() not in SHEET_EXTENSIONS:
                continue
            claimed |= tracks_referenced_by(entry)
    return claimed


def unrowed_tracks(members) -> list[Path]:
    """Data files a sheet names that never became library rows of their own.

    A Dreamcast rip is a .gdi beside track01.bin and track02.raw, and .raw is
    not an extension the scanner claims - too generic a name to treat as a ROM
    on sight. That is the right call for the library and the wrong one for
    deletion: nothing else points at those bytes once the sheet is gone, so
    without this they stay on disk forever with no entry to reach them by.

    Read while the sheets are still there. Afterwards there is nothing left to
    say which files belonged to which disc.

    Anything another sheet in the directory still names is left alone. The name
    of this function is a promise the caller has to finish keeping: `known` is
    built from the set being deleted and from nothing else, so a file holding
    somebody else's library row still reads as unrowed here. Callers go through
    removable_tracks below, which asks the database and drops those.
    """
    from handler.filesystem.rom_scanner import SHEET_EXTENSIONS, tracks_referenced_by

    known = {m.fs_name.lower() for m in members}
    known |= spoken_for_elsewhere(members)
    found: list[Path] = []
    for member in members:
        if Path(member.fs_name).suffix.lower() not in SHEET_EXTENSIONS:
            continue
        directory = Path(member.fs_path)
        named = tracks_referenced_by(directory / member.fs_name)
        if not named:
            continue
        try:
            beside = sorted(directory.iterdir())
        except OSError:
            continue
        for entry in beside:
            if entry.name.lower() in named and entry.name.lower() not in known:
                known.add(entry.name.lower())
                found.append(entry)
    return found


async def removable_tracks(members, *, session=None) -> list[Path]:
    """The data files a set may actually take with it when it leaves the folder.

    unrowed_tracks reads the sheets and answers with everything they name that
    is not a member of this set. That is only most of the answer: it knows the
    set being deleted and knows nothing about the rest of the library, so a file
    holding another entry's row looks from there exactly like an orphan. The
    database settles it, and files that turn out to be somebody's entry stay.

    Asked by the delete route, for its preview and for the delete itself, and
    by a CHD conversion before it removes or retires what it replaced. Those are
    the ways a disc's files leave the folder, and one answer keeps them from
    disagreeing about whose a file is.

    *session* only when the caller has one to share; the handlers open their own
    otherwise.
    """
    from handler.database.rom_handler import rom_handler

    candidates = await asyncio.to_thread(unrowed_tracks, members)
    if not candidates:
        return []
    shared = {} if session is None else {"session": session}
    platform_id = members[0].platform_id
    owned = await rom_handler.fs_names_with_rows(
        platform_id, [p.name for p in candidates], **shared
    )
    # And the files that can never hold a row of their own. A .sbi is not a ROM
    # extension, so the name check above never protects one - which is what made
    # a sheet naming somebody else's subchannel file enough to delete it. The
    # stem says which disc a file belongs to; a disc outside this set keeps it.
    # The set's own discs are excluded, or a disc would protect its own .sbi
    # from going with it.
    spoken_for = await rom_handler.stems_with_rows(
        platform_id, [p.stem for p in candidates],
        exclude_ids=[m.id for m in members], **shared
    )
    return [
        p for p in candidates
        if p.name.lower() not in owned and p.stem.lower() not in spoken_for
    ]


async def track_files_that_go_with(members, *, session=None) -> set[str]:
    """Lower-cased names of the track files that leave with this set.

    Two kinds. The set's own track rows, unless a sheet from outside the set
    still names the file - the scanner gave it to whichever sheet sorted first,
    and that is no reason for the other sheet to lose it. And the tracks that
    never became rows, once removable_tracks has asked the database about them.

    Not the discs themselves, and not playlists or subchannel files: those are
    the caller's to decide, because deleting a title and converting it treat
    them differently.
    """
    spoken_for = await asyncio.to_thread(spoken_for_elsewhere, members)
    going = {m.fs_name.lower() for m in members if m.track_of} - spoken_for
    going |= {p.name.lower() for p in await removable_tracks(members, session=session)}
    return going


def delete_paths(paths) -> int:
    """Remove files already decided on, with the same guard as everything else."""
    removed = 0
    touched: set[Path] = set()
    for path in paths:
        target = _within(str(path), roms_library_path())
        if target and target.is_file() and _unlink(target):
            removed += 1
            touched.add(target.parent)
    for directory in touched:
        _prune_empty(directory, roms_library_path())
    return removed


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
