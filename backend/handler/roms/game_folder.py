"""Keeping a game's folder named after the game.

The folder a ROM lives in is named after its title, and titles change: a scrape
finds the real name of a file called `ff9-eu-d1.chd`, or somebody corrects one
by hand. The files follow, because a shelf that reads one way and a disk that
reads another is the thing folders were supposed to fix.

Two shapes, two ways of moving. A game that already has a folder moves by
renaming it - one operation the filesystem either performs or does not, so
nothing is ever left half moved, and everything inside travels along: the discs,
the mods somebody added over FTP, the originals a CHD conversion put aside. A
game still lying flat on the shelf is moved file by file, because the shelf is
shared with every other game of that platform, and anything already moved goes
back if one of them fails.

What moves is the whole game. Four discs, the track files of any disc kept as a
sheet, the subchannel data a PAL disc needs to boot past its LibCrypt check, and
the playlist the emulator switches discs with - all of them found by sitting
beside each other, which is exactly what a half-finished move destroys.
"""
from __future__ import annotations

import asyncio
import logging
import os
from collections import Counter
from pathlib import Path

from handler.database.rom_handler import rom_handler
from handler.filesystem.rom_scanner import playlists_naming, subchannel_files_for
from utils.disk_sets import marked_disk
from utils.game_folders import game_dir, game_folder_name, shelves_of

logger = logging.getLogger(__name__)

#: Held while a folder is renamed after a title, and while a download chooses
#: the folder it writes into and marks it with its .part. Without it the two
#: cross: a download picks the folder disc 1 is in, that folder takes the title
#: a moment later, and the download writes into a new folder of the old name -
#: two folders, two games, and a disc the player cannot switch to.
folder_moves = asyncio.Lock()


def _shelves(shelf: Path) -> tuple[Path, ...]:
    """The shelves a platform keeps games on, the way the scan reads them: its
    own folder and roms/ inside it, each shared by every game on it - and the
    same two in the folder of each other name of the console."""
    return shelves_of(shelf)


def _scan_reads(folder: Path, shelf: Path, shelves=None) -> bool:
    """Whether the scan reads this folder: either shelf, or a game's folder one
    level inside one. A row naming anywhere else is a library that moved, or a
    folder that holds something other than games. *shelves*, when a caller
    asking about many rows has them already: finding them lists the root."""
    shelves = _shelves(shelf) if shelves is None else shelves
    return folder in shelves or (folder.parent in shelves and folder.name != "roms")


def choose_home(filename: str, rows, shelf: Path) -> Path | None:
    """The folder this file's game already lives in, or None if it lives nowhere.

    *rows* are (file name, folder) pairs from this platform. The same file wins,
    wherever it is. Otherwise another disc of the same title, and when a set is
    already split, the folder holding most of it - the disc that is not there
    yet should not be the one to decide which half is the game.

    Only a place the scan reads counts (_scan_reads).
    """
    shelves = _shelves(shelf)
    places = [(name, Path(path)) for name, path in rows
              if path and _scan_reads(Path(path), shelf, shelves)]
    same = sorted(folder for name, folder in places if name == filename)
    if same:
        return same[0]

    arriving = marked_disk(Path(filename).stem)
    if arriving is None:
        return None
    siblings = []
    for name, folder in places:
        disk = marked_disk(Path(name).stem)
        if disk is not None and disk.title == arriving.title:
            siblings.append((disk.number, folder))
    if not siblings:
        return None
    counts = Counter(folder for _, folder in siblings)
    most = max(counts.values())
    # A tie goes to the folder with the lowest disc in it: the one the set
    # started in.
    _, folder = min(((number, folder) for number, folder in siblings if counts[folder] == most),
                    key=lambda pair: (pair[0], str(pair[1])))
    return folder


async def existing_home(fs_slug: str, filename: str, *, roms_base, session=None) -> Path | None:
    """Where this file's game already is on this platform, or None if the
    library does not have it (choose_home, asked of the library)."""
    disk = marked_disk(Path(filename).stem)
    # What the rows have to start with to be this file or a disc of its set.
    prefix = filename if disk is None else disk.prefix
    shared = {} if session is None else {"session": session}
    rows = await rom_handler.files_starting_with(fs_slug, prefix, **shared)
    # In a worker thread, because it lists the ROM root (utils.game_folders.
    # platform_dirs), and a download asks this for every entry in its queue.
    return await asyncio.to_thread(choose_home, filename, rows, Path(roms_base) / fs_slug)


async def home_for(fs_slug: str, filename: str, *, roms_base, session=None) -> Path:
    """The folder a file of this name is written into on this platform.

    Where its game already is, if the library has it. Otherwise a folder named
    after the file, which is where its title finds it once a scrape has run.
    """
    found = await existing_home(fs_slug, filename, roms_base=roms_base, session=session)
    return found or game_dir(roms_base, fs_slug, filename)


async def folders_holding(fs_slug: str, stem: str, *, roms_base) -> list[Path]:
    """The folders on this platform, of those the scan reads, that hold a file
    whose name starts with *stem*. Where a subchannel file looks for its disc
    once the disc has left the folder its own name points at."""
    shelf = Path(roms_base) / fs_slug
    shelves = _shelves(shelf)
    found: list[Path] = []
    for _, path in await rom_handler.files_starting_with(fs_slug, stem):
        folder = Path(path)
        if path and _scan_reads(folder, shelf, shelves) and folder not in found:
            found.append(folder)
    return found


def files_of_the_game(directory: Path, members) -> list[Path]:
    """Every file in *directory* that belongs to this set.

    The rows say which files are discs and tracks; the two helpers say which
    companion files are theirs. Both are the scanner's own, so a file moved
    here is a file the scan will recognise on the other side.
    """
    names = [m.fs_name for m in members if getattr(m, "fs_name", None)]
    found: list[Path] = []
    seen: set[str] = set()
    for candidate in ([directory / n for n in names]
                      + subchannel_files_for(directory, names)
                      + playlists_naming(directory, names)):
        key = str(candidate).lower()
        if key not in seen and candidate.is_file():
            seen.add(key)
            found.append(candidate)
    return found


def _busy(directory: Path) -> bool:
    """Whether something is writing in here. A `.part` file is a transfer that
    has not finished - in the folder itself, or in the extras/ and mods/ "Add
    file" writes into - and moving the directory out from under it leaves half
    a file under a name nothing will ever complete."""
    try:
        for place in (directory, directory / "extras", directory / "mods"):
            if place.is_dir() and any(p.suffix.lower() == ".part" for p in place.iterdir()):
                return True
        return False
    except OSError:
        return True


async def _what_else_goes(shelf: Path, members, *, session=None) -> list[Path] | None:
    """What else on a shared shelf is this game's, besides its rows and the
    companions files_of_the_game finds - or None when it cannot move at all.

    Found by the 1.0.36 audit, all of it left behind by a move by rows:

      * the tracks a sheet names that never became rows: .ogg, .wav and .raw
        are not ROM extensions, so the sheet arrived in the new folder naming
        files that stayed on the shelf;
      * the files under a disc's own name that a handheld or RetroArch looks
        for beside it - a soft patch, a save, a .mds or .ccd - unless another
        game on the shelf shares that name, and then whose they are is not
        ours to decide.

    None when a file of this game is named by a sheet that is not: two regional
    sheets sharing one data file. Moved, the other sheet names a file that is
    gone; left, this one does. The game stays where it is.
    """
    from handler.filesystem.rom_scanner import (
        _ROM_EXTENSIONS,
        SHEET_EXTENSIONS,
        tracks_referenced_by,
    )
    from handler.roms import rom_removal

    shared = {} if session is None else {"session": session}

    def _read() -> tuple[set[str], set[str], list[Path]]:
        named: set[str] = set()
        for m in members:
            if Path(m.fs_name).suffix.lower() in SHEET_EXTENSIONS:
                named |= tracks_referenced_by(shelf / m.fs_name)
        try:
            beside = [p for p in shelf.iterdir() if p.is_file()]
        except OSError:
            beside = []
        return named, rom_removal.spoken_for_elsewhere(members), beside

    named, spoken_for, beside = await asyncio.to_thread(_read)
    ours = {m.fs_name.lower() for m in members}
    if (ours | named) & spoken_for:
        return None

    others = await rom_handler.names_in_folder(str(shelf), [m.id for m in members], **shared)
    other_stems = {Path(n).stem for n in others}
    stems = {Path(m.fs_name).stem.lower() for m in members if not getattr(m, "track_of", None)}
    found: list[Path] = []
    for path in beside:
        name = path.name.lower()
        if name in ours or name in others or name.startswith(".") or name.endswith(".part"):
            continue
        if name in named:
            found.append(path)
        # A companion by name only: not a file another sheet names (its track),
        # and not a ROM the scan has yet to see (a game of its own) - round 2.
        elif (path.stem.lower() in stems and path.stem.lower() not in other_stems
              and name not in spoken_for
              and path.suffix.lstrip(".").lower() not in _ROM_EXTENSIONS):
            found.append(path)
    return found


async def follow_title(rom_id: int, *, roms_base: str | None = None, session=None) -> str | None:
    """Move this game's files into a folder named after its title.

    Answers with the new folder, or None when nothing moved - which is the
    ordinary case: the folder is already called that, the name belongs to
    another game, or something is being written in there.

    Under the lock a download holds while it chooses its folder, so the two
    never cross (see folder_moves).
    """
    async with folder_moves:
        return await _follow_title(rom_id, roms_base=roms_base, session=session)


async def _follow_title(rom_id: int, *, roms_base: str | None, session) -> str | None:
    shared = {} if session is None else {"session": session}
    # With the platform, because the shelf this game may move within is the
    # platform's folder and nothing else.
    rom = await rom_handler.get_with_platform(rom_id, **shared)
    if rom is None or not rom.fs_path or rom.platform is None:
        return None

    if roms_base is None:
        from handler.filesystem.rom_paths import roms_library_path

        roms_base = roms_library_path()

    current = Path(rom.fs_path)
    shelf = Path(roms_base) / rom.platform.fs_slug
    # The two shelves a platform keeps games on, the way the scan reads them:
    # the platform's own folder and roms/ inside it, RomM's shape. Each is
    # shared by every game on it, and a game's own folder sits one level inside
    # either. roms/ is one level down as well, which is why it is asked about
    # first: taken for a game's folder, it was renamed after one game with
    # every other game still inside.
    shelves = _shelves(shelf)
    if current in shelves:
        home = current
    elif current.parent in shelves:
        home = current.parent
    else:
        # Not a moved library whose rows still name the old place, and not a
        # path that walked out of the tree.
        return None

    want = game_folder_name(title=rom.name, fs_name=rom.fs_name)
    target = home / want
    if current == target or target.exists():
        return None
    if _busy(current):
        logger.info("Not moving %s: something is still being written there", current)
        return None

    members = await rom_handler.disk_set(rom_id, **shared)
    if not members:
        return None
    # A conversion writes nothing into the folder until its last copy, so no
    # .part says it is running; the job does.
    from handler.roms import chd_jobs

    if chd_jobs.converting(m.id for m in members):
        logger.info("Not moving %s: it is being converted", current)
        return None
    moving = files_of_the_game(current, members)
    if not moving:
        return None

    if current in shelves:
        extra = await _what_else_goes(current, members, session=session)
        if extra is None:
            logger.info("Not moving %s: another sheet on the shelf names one of its files",
                        rom.name or rom.fs_name)
            return None
        known = {str(p).lower() for p in moving}
        moving += [p for p in extra if str(p).lower() not in known]
        # Asked before anything moves: where each disc's manual is now. On a
        # shared shelf it sits in the shared extras/ under the game's name, and
        # the row keeps it relative to the ROM's folder - which is about to be
        # a different folder.
        from handler.metadata import manuals

        manuals_now = [(m, manuals.resolve_manual(m, roms_base)) for m in members]
        moved = _move_each(moving, target)
        if moved is None:
            return None
        for member, found in manuals_now:
            if found is not None:
                await rom_handler.update_metadata(
                    member.id, {"manual_path": _bring_manual(found, target)}, **shared)
    else:
        # Only a folder that is this game's alone. From 1.0.36 the scan reads
        # one level below the platform, so a folder a library already had -
        # snes/Hacks/, a Zelda/ holding three regions - holds several games;
        # renamed after one, the others named a folder that was gone (1.0.36
        # audit). A row that lost its file counts: its saves are on it.
        if await rom_handler.another_in_folder(str(current), [m.id for m in members],
                                               **shared) is not None:
            logger.info("Not renaming %s: other games live in it too", current)
            return None
        try:
            os.rename(current, target)
        except OSError as exc:
            logger.warning("Could not rename %s to %s: %s", current, target, exc)
            return None

    for member in members:
        if Path(member.fs_path) == current:
            await rom_handler.move_row_to(member.id, str(target), **shared)
    logger.info("%s moved to %s", rom.name or rom.fs_name, target)
    return str(target)


async def own_folder_held(rom_id: int, *, roms_base: str) -> Path | None:
    """The folder that is this game's own, giving it one first if it lies loose.

    For a file added to the game (the owner, 2026-09-18: "Add file" on a ROM).
    Its extras/ and mods/ are the game's only when the folder is: a loose game
    shares the shelf's with every other loose game, so it is moved into a
    folder of its own first, exactly as a scrape that finds its title moves it.
    A game already in a folder stays where it is; its name is the title rule's
    business, not an upload's.

    None when there is no such folder to be had - the name is another game's,
    something is being written on the shelf, or the row names a place the scan
    does not read. The caller HOLDS folder_moves, and keeps holding it until the
    file it writes has its .part, so no rename comes in between.
    """
    rom = await rom_handler.get_with_platform(rom_id)
    if rom is None or not rom.fs_path or rom.platform is None:
        return None
    current = Path(rom.fs_path)
    shelves = _shelves(Path(roms_base) / rom.platform.fs_slug)
    if current.parent in shelves and current.name != "roms":
        return current
    if current not in shelves:
        return None
    moved = await _follow_title(rom_id, roms_base=roms_base, session=None)
    return Path(moved) if moved else None


def _bring_manual(found: Path, target: Path) -> str:
    """Move a manual from the shared shelf into the game's new folder.

    It becomes that folder's plain Manual.pdf, and the answer is what the row
    keeps from now on. When it cannot be moved - the name is taken, the disk
    refuses - the file stays where it is and the answer is the way to it from
    the new folder, so the row still finds it rather than pointing at nothing.
    """
    from handler.metadata import manuals

    landing = target / "extras" / manuals.MANUAL_NAME
    try:
        if not landing.exists():
            landing.parent.mkdir(parents=True, exist_ok=True)
            os.rename(found, landing)
            return manuals.stored_path(landing, target)
    except OSError as exc:
        logger.warning("Could not move the manual %s: %s", found, exc)
    return Path(os.path.relpath(found, target)).as_posix()


def _move_each(paths, target: Path):
    """Move these files into *target*, or put back what was already moved.

    For the flat shelf only. Half a disc set in a folder and half on the shelf
    is two games, one of which cannot be started.
    """
    target.mkdir(parents=True, exist_ok=True)
    done: list[tuple[Path, Path]] = []
    for path in paths:
        landing = target / path.name
        try:
            os.rename(path, landing)
        except OSError as exc:
            logger.warning("Could not move %s: %s - putting back %d file(s)",
                           path, exc, len(done))
            for was, now in reversed(done):
                try:
                    os.rename(now, was)
                except OSError:
                    logger.error("Could not put %s back to %s", now, was)
            try:
                target.rmdir()
            except OSError:
                pass
            return None
        done.append((path, landing))
    return done
