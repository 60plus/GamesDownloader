"""ROM filesystem scanner.

Scans /data/games/roms/{platform_fs_slug}/ and syncs found files
with the database.  Supports ROMM-compatible folder structure:

  Structure A (default):
    /data/games/roms/{platform_fs_slug}/{game}.{ext}

  Structure B (alternative):
    /data/games/roms/{platform_fs_slug}/roms/{game}.{ext}
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import re
import time
import zlib
from pathlib import Path

from handler.database.rom_handler import rom_handler, rom_platform_handler
from handler.filesystem.exclusions import is_excluded, parse_patterns
from handler.metadata.rom_platform_map import (
    PLATFORM_MAP,
    canonical_fs_slug,
    slug_from_fs_slug,
)
from utils.disk_sets import group_disks
from utils.rom_names import region_from_name

logger = logging.getLogger(__name__)

#: The scheduled scan waits this long after boot before its first look, so it
#: never competes with the work of starting up.
_SCAN_LOOP_START_DELAY_S = 120
#: How often to re-read the setting while the feature is switched off. Short
#: enough that turning it on is noticed within the hour, cheap enough to ignore.
_SCAN_LOOP_IDLE_S = 900

# Common ROM extensions - anything outside this list is silently skipped
_ROM_EXTENSIONS = {
    # Nintendo
    "nes", "fds", "smc", "sfc", "fig", "swc",          # NES / SNES
    "n64", "z64", "v64",                                 # N64
    "gb", "gbc", "gba",                                  # Game Boy
    "nds", "3ds", "cci", "cxi",                          # DS / 3DS
    "wbfs", "iso", "wad", "rvz",                         # Wii / Wii U
    # Sega
    "md", "gen", "bin", "sms", "gg", "32x",             # Genesis / SMS / GG / 32X
    "cue", "gdi", "chd",                                 # CD-based (Saturn, Dreamcast, PS)
    # Sony
    "pbp", "psp", "cso",                                 # PSP
    "pkg",                                               # PS3 / PSN
    # Multi-format
    "img", "mdf", "nrg", "xex",                          # Various
    "zip", "7z", "rar",                                  # Compressed ROMs
    "rom", "a26", "a52", "lnx", "pce", "vb",            # Misc classics
    "ws", "wsc", "ngp", "ngc", "dsk", "adf",            # Handheld / Amiga
    # Home computers. Their sets ship disk/tape images rather than cartridge
    # dumps, and without these a C64 or Atari 8-bit library scans as empty.
    "d64", "t64", "g64", "d71", "d81", "crt", "tap", "prg",   # Commodore
    "atr", "atx", "cas", "car",                                # Atari 8-bit
    "st", "msa", "ipf",                                        # Atari ST
    "cdt", "sna", "dmk",                                       # Amstrad / misc
    # Amiga beyond the plain floppy. The Amiga core reads all of these, and
    # .lha in particular is how WHDLoad ships: a hard-drive install rather than
    # a disk image, which is the form most of the Amiga catalogue takes.
    # Left out on purpose: .slave and .info live inside a WHDLoad archive rather
    # than standing alone, .uae is a config file, and .raw is too generic a name
    # to claim as a ROM.
    "lha", "adz", "dms", "hdf", "hdz", "fdi",                  # Amiga
}


def _strip_tags(name: str) -> str:
    """Remove [tags] and (tags) from a ROM filename."""
    name = re.sub(r"\s*[\(\[][^\)\]]*[\)\]]", "", name)
    return name.strip()


# A disc kept as a sheet plus its track files. Both the sheet and the tracks
# carry extensions this scanner recognises, so without reading the sheet a
# single PlayStation title arrives in the library twice - and the copy standing
# for the .bin cannot be launched, because the emulator wants the sheet.
SHEET_EXTENSIONS = {".cue", ".gdi"}

# A sheet is a few kilobytes of text. Anything of this size claiming to be one
# is not, and is not worth reading into memory to find out.
_MAX_SHEET_BYTES = 1024 * 1024

# Separators are spaces and tabs, never `\s`. A gdi opens with a bare track
# count on its own line, and `\s` spans the newline: the count would run into
# the line below it, four fields would be read across the join, and the sector
# size would be taken for the filename.
_CUE_FILE_RE = re.compile(r'^[ \t]*FILE[ \t]+(?:"([^"]+)"|(\S+))', re.IGNORECASE | re.MULTILINE)
# "1 0 4 2352 track01.bin 0", quoted or not.
_GDI_TRACK_RE = re.compile(
    r'^[ \t]*\d+[ \t]+\d+[ \t]+\d+[ \t]+\d+[ \t]+(?:"([^"]+)"|(\S+))', re.MULTILINE
)


def tracks_referenced_by(sheet: Path) -> set[str]:
    """The filenames a .cue or .gdi names as its tracks, lowercased.

    Read out of the sheet rather than guessed from the stem. A multi-track rip
    names its tracks freely - "Game (Track 01).bin" beside "Game.cue" is
    ordinary - so matching on a shared stem would miss most of them.

    Decoded as utf-8-sig, not utf-8. A sheet written by a Windows tool often
    opens with a byte order mark, and read as plain utf-8 that mark stays on
    the front of the first line - so `^FILE` misses it and the first track goes
    unclaimed. On a single-track disc that is the whole sheet and the duplicate
    entry comes back; on a multi-track rip only track one is lost, which is
    worse, because the log still reports the rest as folded.
    """
    try:
        if sheet.stat().st_size > _MAX_SHEET_BYTES:
            return set()
        text = sheet.read_text(encoding="utf-8-sig", errors="ignore")
    except OSError:
        return set()

    pattern = _CUE_FILE_RE if sheet.suffix.lower() == ".cue" else _GDI_TRACK_RE
    names: set[str] = set()
    for quoted, bare in pattern.findall(text):
        raw = (quoted or bare).strip()
        if raw:
            # A sheet may write a path. Only the name is of interest, and one
            # pointing outside its own directory is not somewhere we follow.
            names.add(Path(raw.replace("\\", "/")).name.lower())
    return names


# ── Watching a scan, and asking it to stop ───────────────────────────────────
#
# The whole status of a running scan used to be one boolean, polled every two
# seconds by three views. On a shelf of disc images that is a progress bar that
# says "yes" for two hours, with no way to change your mind.
#
# The state lives here rather than in the router because the walk is what knows
# where it is, and because the periodic loop starts scans nobody clicked.

_progress: dict = {
    "running": False,
    "cancelling": False,
    "platform": None,
    "platform_index": 0,
    "platform_total": 0,
    "files_done": 0,
    "files_total": 0,
    "current": None,
}


def scan_progress() -> dict:
    """Where the scan is now. A copy, so a watcher cannot change it or see it
    move under them halfway through rendering."""
    return dict(_progress)


def reset_scan_progress() -> None:
    _progress.update(running=False, cancelling=False, platform=None,
                     platform_index=0, platform_total=0,
                     files_done=0, files_total=0, current=None)


def begin_scan_progress(*, platform_total: int) -> None:
    """Start counting. Clears any stop left over from the previous scan, which
    would otherwise end this one the moment it began."""
    reset_scan_progress()
    _progress.update(running=True, platform_total=platform_total)


def note_scan_platform(name: str, *, index: int, files_total: int) -> None:
    _progress.update(platform=name, platform_index=index,
                     files_total=files_total, files_done=0, current=None)


def note_scan_file(name: str, *, done: int) -> None:
    _progress.update(current=name, files_done=done)


def request_scan_stop() -> bool:
    """Ask a running scan to stop. False if there was nothing to ask.

    Returning False rather than setting the flag anyway matters: a flag left on
    an idle scanner is a stop request the NEXT scan would trip over.
    """
    if not _progress["running"]:
        return False
    _progress["cancelling"] = True
    return True


def scan_cancelled() -> bool:
    return bool(_progress["cancelling"])


#: How often progress may go out over the socket. A twenty thousand ROM library
#: would otherwise emit twenty thousand events, most of them into the same
#: hundred milliseconds, and the browser would spend the scan re-rendering
#: instead of showing it.
_EMIT_EVERY_S = 0.4
_last_emit = 0.0


#: Who has a reason to watch a scan: the accounts that put things in the
#: library. An uploader cannot START one - that is PLATFORMS_WRITE - but an
#: upload kicks one off by itself, and watching it is the only way to know when
#: what they just added has appeared. Everybody else is not merely uninterested:
#: a client outside these rooms draws a bar from the status call and then sits
#: on the same platform for the rest of the session, because no event will ever
#: advance or clear it.
#:
#: The status route declares the permissions these two roles hold, and the
#: composable draws for the same pair. All three have to agree.
#: Who is sent scan progress. A ROOM named for a capability, not a pair of role
#: names: `_PERM_REVOKE` can take the upload scope off an account without
#: touching its role, so `role:uploader` held accounts the status route refuses
#: - a bar drawn on screen that could never be filled. socket_handler works the
#: room out from effective scopes, and the status route asks the same sentence.
_SCAN_WATCHERS_ROOM = "scan:watchers"


async def _announce_scan_finished(stats: dict) -> None:
    """Tell the watchers the scan ended, whichever way it ended.

    One place, because there are two exits and only one of them used to say
    anything. The views hang their reload on this event and the Classic sidebar
    clears its spinner here, so the silent exit left that spinner turning until
    somebody reloaded the page.

    `stats` carries `cancelled` when it was stopped, so a screen can say so
    instead of reporting a count from a walk that never happened.
    """
    reset_scan_progress()
    try:
        from handler.socket_handler import emit_event

        await emit_event("roms:scan_complete", dict(stats), room=_SCAN_WATCHERS_ROOM)
    except Exception:  # noqa: BLE001 - the scan is done either way
        logger.debug("Could not emit scan completion", exc_info=True)


async def _emit_scan_progress(*, force: bool = False) -> None:
    """Send the current progress, at most a couple of times a second.

    Never lets an error here stop a scan: this is a progress bar, and the walk
    it describes is the part that matters.
    """
    global _last_emit
    now = time.monotonic()
    if not force and now - _last_emit < _EMIT_EVERY_S:
        return
    _last_emit = now
    try:
        from handler.socket_handler import emit_event

        await emit_event("roms:scan_progress", scan_progress(), room=_SCAN_WATCHERS_ROOM)
    except Exception:  # noqa: BLE001 - a progress bar must not end a scan
        logger.debug("Could not emit scan progress", exc_info=True)


def platform_has_nothing(*, files, rows) -> bool:
    """Is there anything for a scan to do on this platform.

    GD creates a folder for every platform it knows on first boot, so a typical
    install has a hundred of them and games in a handful. Every one of them was
    upserted and had all of its ROMs marked missing on every scan, unconditional
    and regardless of being empty - measured at roughly four fifths of the
    database traffic of a real scan.

    "No files on disk" is NOT the condition, and getting that wrong is how a
    library keeps claiming games that were deleted: a platform emptied of its
    files still has rows, and marking those missing is exactly the work this
    scan exists to do. Both have to be nothing.
    """
    return not files and not (rows or 0)


# Directories inside a platform, or inside a game's folder, that are never a
# game themselves. `_originals` holds what a CHD conversion replaced and used to
# be safe only because the scan stopped one level above it; `mods` and `extras`
# are what a game keeps beside its ROM, and both of them routinely hold archives,
# which are ROM extensions. Compared lower-cased, because the name is a
# convention and a person typing it is not a case-sensitive filesystem.
NOT_A_GAME_FOLDER = {"_originals", "mods", "extras"}


def _game_folders_in(base: Path) -> list[Path]:
    """The subdirectories of *base* a scan treats as one game each."""
    try:
        entries = sorted(base.iterdir())
    except OSError:
        return []
    return [
        entry for entry in entries
        if entry.is_dir()
        and entry.name.lower() not in NOT_A_GAME_FOLDER
        # A tool's directory, not a game: .git, .Trash-1000, .stfolder.
        and not entry.name.startswith(".")
        # Named in its own right below, and never a game's folder.
        and entry.name != "roms"
    ]


def scan_dirs_for(platform_dir: Path) -> list[Path]:
    """The directories of this platform a scan reads, in order.

    Two shapes are supported on disk: ROM files sitting directly in
    `{platform}/`, and ROM files one level down in `{platform}/roms/`. They used
    to be an either/or - if `roms/` existed the scan looked there AND NOWHERE
    ELSE - and that turns an ordinary directory name into a way to lose a
    platform. A game titled "roms", an archive unpacked one level too deep, any
    tool that makes the directory: from then on the scan reads an empty platform
    folder, and since a scan opens by marking every row missing and relies on
    the walk to un-mark what it finds, the whole platform reads as missing.
    Silently.

    Both are read now, so the shapes stop being mutually exclusive and a library
    that is half one and half the other stays entirely visible. The platform
    directory itself is always in the list, which is what makes the trap
    impossible rather than merely unlikely.

    A third shape joins them: one folder per game, `{platform}/{game}/{rom}`,
    which is what gives `mods/` and `extras/` somewhere to live beside the ROM
    instead of in one heap with it. Each game folder is read exactly the way the
    platform folder is, so a library half moved stays entirely visible as well.

    ONE LEVEL BELOW EACH ROOT AND NO DEEPER, which is load-bearing rather than
    tidy: zip, 7z, rar, bin, img and iso are all ROM extensions, so a texture
    pack under `{game}/mods/` is a game to anything that recurses. At one level
    it sits two levels down and is out of reach by construction.
    """
    dirs = [platform_dir]
    nested = platform_dir / "roms"
    if nested.is_dir():
        dirs.append(nested)
    for base in list(dirs):
        dirs.extend(_game_folders_in(base))
    return dirs


def moved_row(candidates: list, fs_name: str, still_on_disk) -> int | None:
    """The id of the row a file that turned up here moved out of, or None.

    *candidates* are the rows carrying this file name in the directory one
    level above or one level below - the only two places a move into or out of
    a game folder can come from. *still_on_disk* answers whether a candidate's
    own file is where its row says it is.

    A candidate whose file is still there is a different copy of the same name,
    not this file, and claiming its row would put one game's saves on another's
    file. Two candidates are an ambiguity nothing here can settle. Both answer
    None, which leaves a new row and an old one marked missing: a mess somebody
    can see and fix, rather than a quiet wrong answer.
    """
    live = [c for c in candidates if not still_on_disk(c["fs_path"], fs_name)]
    return live[0]["id"] if len(live) == 1 else None


def _still_on_disk(directory: str, fs_name: str) -> bool:
    """Whether a candidate row's own file is where the row says it is.

    An unreadable directory answers yes, so a permission error or an
    unavailable mount leaves the row alone instead of handing it to a file that
    only looks like the same one.
    """
    try:
        return (Path(directory) / fs_name).exists()
    except OSError:
        return True


def scan_candidates(scan_dir: Path) -> list[Path]:
    """The files in *scan_dir* this scanner treats as ROMs, in name order.

    Shared with everything downstream on purpose. An extension this walk does
    not collect is an extension the rest of the module cannot see, which is how
    the .gdi branch below came to be written and never once run: the sheet was
    never in the list it iterates.
    """
    return [
        entry for entry in sorted(scan_dir.iterdir())
        if entry.is_file() and entry.suffix.lstrip(".").lower() in _ROM_EXTENSIONS
    ]


def playlists_naming(directory, disc_names) -> list[Path]:
    """Every playlist in *directory* that names any of these discs.

    By content rather than by name, because the useful question is whether the
    discs have a playlist, not whether they have ours. One that came down
    beside them, or that somebody wrote by hand on a handheld, counts the same:
    for the button, because writing a second one over the top would be the
    wrong answer; and for deletion, because a playlist naming discs that are
    gone is just as broken whoever wrote it.
    """
    discs = {n.lower() for n in disc_names}
    if len(discs) < 2:
        return []
    try:
        candidates = sorted(Path(directory).glob("*.m3u"))
    except OSError:
        return []
    out = []
    for entry in candidates:
        try:
            lines = entry.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        # A line may carry a `path|Label` suffix, and may be written with
        # either separator by whatever wrote it. Only the file name is
        # compared. GD never writes a label - PCSX-ReARMed hands the whole
        # line to the filesystem - but other tools do.
        named = {
            line.split("|", 1)[0].strip().replace("\\", "/").rsplit("/", 1)[-1].lower()
            for line in lines if line.strip() and not line.startswith("#")
        }
        if named & discs:
            out.append(entry)
    return out


# Subchannel data, which a disc image does not carry and a PAL PlayStation game
# from 1998 onwards may refuse to run without. Matched to a disc by name rather
# than by being named in a sheet, because nothing names them: Redump publishes
# one .sbi per disc called exactly what the image is called, and a rip made
# with the full subchannel has a .sub beside it instead.
#
# Deliberately not ROM extensions. These belong to a disc; on the shelf of
# their own they are 452 bytes of nothing.
SUBCHANNEL_EXTENSIONS = (".sbi", ".sub")


def subchannel_files_for(directory, disc_names) -> list[Path]:
    """The subchannel files sitting beside these discs, if any.

    Without the .sbi a LibCrypt protected disc boots, fails its check and
    hangs on a black screen, and the only word about it is a core log line
    nobody reads. Carrying the file is the whole fix; the core finds it by
    name once it is in the same directory.
    """
    stems = {Path(n).stem.lower() for n in disc_names}
    if not stems:
        return []
    out = []
    try:
        entries = sorted(Path(directory).iterdir())
    except OSError:
        return []
    for entry in entries:
        if entry.suffix.lower() not in SUBCHANNEL_EXTENSIONS:
            continue
        if entry.stem.lower() in stems and entry.is_file():
            out.append(entry)
    return out


def tracks_by_sheet(rom_files) -> dict[str, str]:
    """Which files are track data, and which sheet each one belongs to.

    Read out of the sheets rather than guessed from names, and one-way: a sheet
    is never itself a track. A rip whose sheet names another sheet as its data
    file is malformed, and following that would let two discs swallow each
    other.
    """
    claimed: dict[str, str] = {}
    for rom_file in rom_files:
        if rom_file.suffix.lower() not in SHEET_EXTENSIONS:
            continue
        for track in tracks_referenced_by(rom_file):
            claimed.setdefault(track, rom_file.name)

    return {
        rom_file.name: claimed[rom_file.name.lower()]
        for rom_file in rom_files
        if rom_file.suffix.lower() not in SHEET_EXTENSIONS
        and claimed.get(rom_file.name.lower(), rom_file.name) != rom_file.name
    }


def plan_disk_assignments(rom_files) -> dict[str, tuple[str | None, int | None, bool, str | None]]:
    """Who belongs with whom, decided from one directory listing.

    Two relationships live here, and the whole point is that they are kept
    apart:

      * disks of one title. A player picks between them, the game page lists
        them, and they are numbered.
      * track files of a sheet. Nobody picks one: it is data the sheet points
        at, it travels with the sheet when the disc is downloaded or removed,
        and it has no number because it is not a disk.

    They shared the disk numbering until now and the numbers collided. A track
    was handed the number belonging to the next real disk, so a two-disc game
    offered two buttons both labelled Disk 2 - and one of them handed the
    emulator a raw data file instead of a sheet.

    Returns fs_name -> (disk group, disk number, extra, sheet this is a track of).
    """
    tracks = tracks_by_sheet(rom_files)

    by_stem: dict[str, str] = {}
    for rom_file in rom_files:
        # A track is not a disk, so it takes no part in the grouping. Left in,
        # it claims its own disc's number just as convincingly as the sheet
        # does: "Game (Disc 1) (Track 01).bin" sorts before "Game (Disc 1).cue"
        # and reads as disc 1 either way.
        if rom_file.name in tracks:
            continue
        current = by_stem.get(rom_file.stem)
        # The sheet speaks for its stem. Alphabetically .bin comes first, and a
        # set grouped on its data files leaves every sheet ungrouped - which
        # turned a two-disc game back into two separate titles.
        if current is None or (
            rom_file.suffix.lower() in SHEET_EXTENSIONS
            and Path(current).suffix.lower() not in SHEET_EXTENSIONS
        ):
            by_stem[rom_file.stem] = rom_file.name

    groups: dict[str, list[tuple[int, str]]] = {}
    for stem, (key, number) in group_disks(by_stem).items():
        groups.setdefault(key, []).append((number, by_stem[stem]))

    assignments: dict[str, tuple[str | None, int | None, bool, str | None]] = {
        f.name: (None, None, False, None) for f in rom_files
    }
    for key, members in groups.items():
        primary = min(n for n, _ in members)
        for number, name in members:
            assignments[name] = (key, number, number != primary, None)
    for track, sheet in tracks.items():
        # Extra, so no listing shows it as a game of its own; no group and no
        # number, so no disk selector offers it as something to boot.
        assignments[track] = (None, None, True, sheet)
    return assignments


# Hashing streams rather than buffers, so what a decompression bomb costs here
# is time on every scan rather than memory. Worth a limit even so, because the
# scanner runs unattended and would pay it again every time.
#
# One absolute ceiling, deliberately, and no compression ratio. A ratio is the
# obvious second rule and it is the wrong one here: disc images are mostly
# padding and genuinely compress by factors in the thousands, so any ratio
# tight enough to be useful would start refusing real ISOs. The penalty for
# refusing is that the ROM silently loses its hashes and quietly degrades to
# matching by filename, which is precisely the failure mode worth avoiding.
#
# The ceiling alone is enough. No legitimate ROM is larger, a dual layer disc
# image sits well inside it, and a bomb declares its way past it in the first
# check: 42.zip claims four and a half petabytes.
_MAX_MEMBER_BYTES = 8 * 1024 * 1024 * 1024


_CHD_SIGNATURE = b"MComprHD"
_CHD_HEADER_BYTES = 124          # a full v5 header
_CHD_VERSION_AT = 12             # uint32, big endian
# Offset 84 is the combined raw plus metadata SHA-1, which is the one the
# databases index. The raw-only digest sits at 64 and is the tempting wrong
# answer: the metadata carries the disc's track layout, and two rips that
# differ only there are not the same disc.
_CHD_SHA1_AT = 84


# Said once per file per process rather than on every scan. A scan runs after
# every ROM download, and a line repeated hourly about a file nobody is going to
# re-rip teaches only that the log is not worth reading.
_unreadable_chds: set[str] = set()

# Same reason: a library sitting above the hashing ceiling would otherwise say
# so about every one of its files on every scan.
_unhashed_by_ceiling: set[str] = set()


def hash_ceiling_bytes() -> int:
    """The size above which a scan will not read a file to hash it. 0 = read all.

    Hashing means reading every byte, so seeing a forty gigabyte disc image for
    the first time costs forty gigabytes of reads before anything appears in
    the library, and there was no way to decline. This is that way. It is off
    by default, because a hash is how a ROM gets identified and for a cartridge
    dump the read is free.

    Set in Settings > ROMs. A file skipped this way keeps whatever hashes it
    already had and can be hashed on request from its own page, so the ceiling
    costs nothing that cannot be asked for later.
    """
    from config import config_manager
    try:
        return max(int(config_manager.get_section("roms").get("hash_max_bytes") or 0), 0)
    except Exception:
        # Every failure means "no ceiling", and it has to mean that for every
        # failure. This is the first statement of a scan, and a settings.yaml
        # with a bare `roms:` line makes get_section return None rather than a
        # dict - which is an AttributeError, not a ValueError. Catching only
        # the two obvious types killed the whole scan while the API reported it
        # as started. The sibling ceiling this mirrors catches everything.
        logger.warning("Hashing ceiling unreadable, hashing everything", exc_info=True)
        return 0


def hashing_reads_whole_file(fs_extension: str) -> bool:
    """Whether hashing this format costs a full read.

    A CHD does not: its source hash is written into its own header, so it is
    124 bytes off the front of the file no matter how large the file is. It is
    also the format most likely to be enormous, and exempting it is the
    difference between a ceiling that leaves multi-gigabyte discs identified
    and one that quietly stops identifying exactly the files it was aimed at.
    """
    return (fs_extension or "").lower().lstrip(".") != "chd"


def skip_hashing(fs_size: int, fs_extension: str, ceiling: int) -> bool:
    """Whether the scan should decline to hash this file.

    The whole decision, in one place, so that what the scan does and what the
    tests check cannot drift apart.
    """
    if ceiling <= 0:
        return False
    if not hashing_reads_whole_file(fs_extension):
        return False
    return (fs_size or 0) > ceiling


def _has_hashes(row) -> bool:
    """Whether this row was ever hashed successfully.

    A CRC alone used to stand for that, and a CHD is never going to have one:
    the format is identified by the SHA-1 written into its own header. Reading
    "no CRC" as "not hashed yet" is half of why every .chd was re-read on every
    single scan.
    """
    return bool(row.crc_hash or getattr(row, "sha1_hash", None))


def _chd_header_sha1(path: Path) -> str:
    """The SHA-1 a CHD v5 carries in its own header, or "" if there is none.

    Hashing a CHD like any other file produces the digest of a compressed
    container, and no signature database holds those - so the ROM quietly stops
    being identified by hash and falls back to matching on its filename.

    The container is the wrong thing to measure for a reason worth knowing:
    chdman does not produce byte-identical output for the same source disc, so
    two correct rips of one game have different container hashes. That is
    exactly why the format writes the source hash into the header.
    """
    try:
        with path.open("rb") as fh:
            header = fh.read(_CHD_HEADER_BYTES)
    except OSError:
        return ""
    if len(header) < _CHD_SHA1_AT + 20 or not header.startswith(_CHD_SIGNATURE):
        return ""
    version = int.from_bytes(header[_CHD_VERSION_AT:_CHD_VERSION_AT + 4], "big")
    if version != 5:
        return ""
    return header[_CHD_SHA1_AT:_CHD_SHA1_AT + 20].hex()


def _reject_unsafe_member(name: str) -> None:
    """Refuse an archive member whose own name would write outside the target.

    Same rule, and the same reason, as `utils.save_archive.member_bytes`: the
    name comes from the archive, which is to say from whoever wrote it.
    """
    if not name:
        raise ValueError("empty member name")
    # A backslash is checked separately because this runs on Linux, where
    # `Path("..\\etc")` is one innocent-looking component rather than a walk
    # upwards. An archive written on Windows is exactly where such a name comes
    # from, and no ROM archive has a legitimate use for one.
    if "\\" in name:
        raise ValueError(f"unsafe path in archive: {name}")
    p = Path(name)
    if p.is_absolute() or ".." in p.parts:
        raise ValueError(f"unsafe path in archive: {name}")


def _pick_rom_members(entries, name_of, size_of) -> list:
    """Order an archive's members so the ROM comes first.

    "The largest member" is the obvious rule and it is wrong often enough to
    matter: a set that ships the ROM beside a scanned manual hashes the manual,
    because a PDF of a Super Nintendo booklet outweighs the cartridge dump. The
    hash then matches nothing, and there is no sign of it - the ROM simply
    stops being identified, which looks exactly like a title the databases do
    not carry.

    So prefer the largest member that looks like a ROM, and fall back to the
    largest member overall when none of them do. The fallback is what this
    function did all along, which means an archive holding an extension we do
    not list is no worse off than before.

    (RomM solves the same problem the other way round, with an administrator
    editable list of names and extensions to exclude. Ours is an allow-list we
    already maintain for the directory walk, so it costs nothing to reuse.)
    """
    ordered = sorted(entries, key=size_of, reverse=True)
    roms = [
        e for e in ordered
        if (name_of(e) or "").rsplit(".", 1)[-1].lower() in _ROM_EXTENSIONS
    ]
    return roms or ordered


def _hash_stream(stream, max_bytes: int | None = None) -> tuple[str, str, str]:
    """Hash a readable stream → (crc32_hex_upper, md5_hex, sha1_hex).

    `max_bytes` stops a member that keeps inflating. The declared size is a
    claim by the archive; this is the measurement.
    """
    crc = 0
    md5 = hashlib.md5()
    sha1 = hashlib.sha1()
    total = 0
    while chunk := stream.read(4 * 1024 * 1024):
        total += len(chunk)
        if max_bytes is not None and total > max_bytes:
            raise ValueError(f"member inflates past the {max_bytes} byte ceiling")
        crc = zlib.crc32(chunk, crc)
        md5.update(chunk)
        sha1.update(chunk)
    crc_hex = format(crc & 0xFFFFFFFF, "08X")
    return crc_hex, md5.hexdigest(), sha1.hexdigest()


def _compute_hashes(path: Path, hash_ceiling: int = 0) -> tuple[str, str, str]:
    """Return (crc32_hex_upper, md5_hex, sha1_hex) for ROM content.

    For .zip / .7z archives: hashes the LARGEST file inside (the actual ROM),
    not the archive itself.  This matches how ScreenScraper and EmulationStation
    identify ROMs - by the hash of the uncompressed content.

    `hash_ceiling` is the user's "do not read files larger than this", and it
    has to be applied here as well as in the scan. The scan measures the file
    on disk, which for an archive is the COMPRESSED size: a PlayStation 2 set
    in .7z is a gigabyte on disk and four and a half gigabytes to read, and the
    7z branch below extracts the member to a temporary directory first. So the
    ceiling the operator set to make a first scan finish was ignored by exactly
    the format large ROM sets ship in. Reading the member's declared size costs
    a directory lookup, not a read.

    Returns ('', '', '') on any error.
    """
    suffix = path.suffix.lower()

    try:
        ceiling = _MAX_MEMBER_BYTES
        if hash_ceiling > 0:
            # Two different ceilings meet here: the safety one above, which
            # exists so a bomb cannot spend the scanner's afternoon, and the
            # operator's, which exists so a disc library finishes its first
            # scan. Whichever is lower governs.
            ceiling = min(ceiling, hash_ceiling)

        # ── CHD ──────────────────────────────────────────────────────────
        if suffix == ".chd":
            # Only the SHA-1 in the header is meaningful, and there is no
            # second-best. A digest of the container describes the compression:
            # chdman does not produce byte-identical output for one source disc,
            # so two correct rips of the same game hash differently and neither
            # matches anything in any database.
            #
            # Hashing it anyway was not merely useless, it never stopped. The
            # scan re-hashes a row that has no CRC, this produced a CRC, and the
            # pass that clears a stale CRC would not run while one was there -
            # so every scan read the whole multi-gigabyte file again, forever,
            # and a scan runs after every ROM download.
            embedded = _chd_header_sha1(path)
            if not embedded and str(path) not in _unreadable_chds:
                _unreadable_chds.add(str(path))
                logger.info(
                    "%s is not a CHD v5, so it carries no source hash and cannot "
                    "be identified by one. Hashing the container instead would "
                    "match nothing, so it is left without hashes.",
                    path.name,
                )
            return "", "", embedded

        # ── ZIP archive ──────────────────────────────────────────────────
        if suffix == ".zip":
            import zipfile
            with zipfile.ZipFile(path, "r") as zf:
                entries = _pick_rom_members(
                    zf.infolist(), lambda e: e.filename, lambda e: e.file_size
                )
                if not entries:
                    return "", "", ""
                if entries[0].file_size > ceiling:
                    # The declared size alone is enough to turn this away, and
                    # doing so costs nothing at all.
                    raise ValueError(
                        f"{entries[0].filename} declares {entries[0].file_size} bytes, "
                        f"over the {ceiling} byte ceiling"
                    )
                with zf.open(entries[0]) as rom_stream:
                    logger.debug("Hashing ZIP member: %s (%d bytes)", entries[0].filename, entries[0].file_size)
                    return _hash_stream(rom_stream, ceiling)

        # ── 7z archive ───────────────────────────────────────────────────
        if suffix == ".7z":
            try:
                import py7zr
            except ImportError:
                logger.warning("py7zr not installed - cannot hash .7z contents, hashing archive file instead")
                with path.open("rb") as fh:
                    return _hash_stream(fh)

            with py7zr.SevenZipFile(path, "r") as sz:
                entries = _pick_rom_members(
                    sz.list(), lambda e: e.filename, lambda e: e.uncompressed or 0
                )
                if not entries:
                    return "", "", ""
                target = entries[0].filename
                _reject_unsafe_member(target)
                if (entries[0].uncompressed or 0) > ceiling:
                    raise ValueError(
                        f"{target} declares {entries[0].uncompressed} bytes, "
                        f"over the {ceiling} byte ceiling"
                    )
                logger.debug("Hashing 7z member: %s (%d bytes)", target, entries[0].uncompressed or 0)
                # Extract single file to memory via temporary dir
                import tempfile
                with tempfile.TemporaryDirectory() as tmpdir:
                    sz.extract(tmpdir, [target])
                    extracted = Path(tmpdir) / target
                    # The name was checked above; this checks where it actually
                    # landed, because the guarantee that matters is about the
                    # file we are opening rather than the string we were given.
                    root = os.path.realpath(tmpdir)
                    landed = os.path.realpath(extracted)
                    if not (landed == root or landed.startswith(root + os.sep)):
                        raise ValueError(f"archive member escaped the extraction directory: {target}")
                    with extracted.open("rb") as fh:
                        return _hash_stream(fh, ceiling)

        # ── Regular file ─────────────────────────────────────────────────
        with path.open("rb") as fh:
            return _hash_stream(fh)

    except Exception as e:
        logger.warning("Hash error for %s: %s", path.name, e)
        return "", "", ""


#: Never adopted, whatever their digest says. A sheet is a few hundred bytes of
#: text naming its tracks, and generated ones come out byte-identical across
#: different games; it is also not the game, which the disc grouping decides
#: separately from the filenames. An .m3u is the same argument again.
_NOT_A_GAME = {"cue", "gdi", "m3u"}

#: The digest of nothing. A truncated upload, an interrupted copy or a client
#: that dropped before its first chunk each leave a 0-byte file, and the ceiling
#: only declines files that are too BIG - so every empty file on a platform ends
#: up carrying this digest and a size of zero, which is a pair the rule would
#: otherwise call a rename.
_SHA1_OF_NOTHING = "da39a3ee5e6b4b0d3255bfef95601890afd80709"


def adopt_renamed_files(gone: list[dict], arrived: list[dict]) -> list[tuple[int, int]]:
    """Which vanished row is which arrival, renamed. Pairs of (old_id, new_id).

    Deliberately timid. A pair has to agree on platform, digest and size, be the
    only candidate on either side, carry a digest at all, and not be a companion
    file. Everything else is left as two rows, because two rows is a mess a
    person can fix and two games merged into one is not.

    Each of those conditions is there for a measured reason rather than for
    tidiness. SHA-1 equality is not identity here: an archive's digest is the
    digest of one picked member, so two different zips sharing their largest ROM
    match on content alone - hence the size. Blank disk images are byte-identical
    wherever they appear. And a digest is nullable, written as `sha1_hash or
    None`, so grouping by raw value would make every unhashed row share a key
    with every other one, and unhashed is routine for anything over the ceiling.
    """
    def key(row: dict):
        sha1 = (row.get("sha1") or "").strip()
        if not sha1 or sha1.lower() == _SHA1_OF_NOTHING:
            return None                       # never a shared key
        if not row.get("size"):
            return None                       # no size to agree on
        if row.get("track_of"):
            return None                       # part of a disc, not a game
        if (row.get("ext") or "").lower().lstrip(".") in _NOT_A_GAME:
            return None
        return (row.get("platform_id"), sha1, row.get("size"))

    def index(rows: list[dict]) -> dict:
        out: dict = {}
        for row in rows:
            k = key(row)
            if k is not None:
                out.setdefault(k, []).append(row["id"])
        return out

    donors, takers = index(gone), index(arrived)
    pairs = [
        (olds[0], takers[k][0])
        for k, olds in donors.items()
        if len(olds) == 1 and len(takers.get(k, ())) == 1
    ]
    return sorted(pairs)


async def _renames_this_run(created_ids, present_before, seen_platform_ids) -> list[tuple[int, int]]:
    """The (vanished row, new row) pairs this run would merge, and nothing else.

    Two callers now, and they have to agree: the ordinary exit merges these, and
    the failure exit takes back exactly the new rows in them - because a row
    with a donor is the only kind a later scan cannot make again.

    THE FILTER GOES ON THE RESULT, NOT ON THE INPUT. `adopt_renamed_files`
    refuses a pair unless it is the only candidate on either side, and its
    docstring says why: SHA-1 equality is not identity, so two arrivals sharing
    a key are two rows a person can sort out and one merge that would be a
    guess. Handing it a list already thinned of rows somebody had played turned
    a two-candidate key into a one-candidate key the moment anyone touched one
    of them, and the guess was then made. So the full list decides the match,
    and the guard drops the pairs it lands on afterwards.
    """
    if not created_ids:
        return []
    donors = [
        row for row in await rom_handler.missing_with_hashes(seen_platform_ids)
        if row["id"] in present_before
    ]
    if not donors:
        return []
    pairs = adopt_renamed_files(
        donors, await rom_handler.rows_for_matching(list(created_ids)),
    )
    return pairs


async def _put_back_after_an_unfinished_scan(
    created_ids, present_before, seen_platform_ids,
) -> int:
    """What a scan that did not finish owes the library, on either door out.

    The missing flags go back, and the rows a rename would have absorbed are
    taken back - only those. A new row with no donor is one the next scan finds
    again; a rename row left behind is one no later scan creates again, so the
    old row holding the artwork, the saves and the play history is never paired
    and stays missing for good.

    THE RENAMES ARE READ BEFORE THE FLAGS GO BACK. `_renames_this_run` finds the
    vanished side by its missing flag. Asked after `restore_present`, as the
    failure exit used to, it found no donor and took nothing back, while the log
    said the library was as it was. Reading writes nothing, so it cannot leave
    the shelf half marked; if it fails, or a second cancellation lands in it,
    the renames are given up and the flags still go back.

    One statement to take the rows back, not one per row: the shutdown door is
    on a few-second clock, and this is the only way it can afford the renames.
    Returns how many rows were taken back.
    """
    pairs: list[tuple[int, int]] = []
    try:
        pairs = await _renames_this_run(created_ids, present_before, seen_platform_ids)
    except (Exception, asyncio.CancelledError):
        logger.exception("Could not work out which rows this scan made for renamed files")
    await rom_handler.restore_present(present_before)
    if not pairs:
        return 0
    try:
        # Not the ones somebody has already played or saved against. Taking
        # those back is not undoing our own work, it is deleting theirs - the
        # ordinary exit carries that data across instead, but a scan that did
        # not finish is not the place to start moving rows about.
        touched = await rom_handler.ids_with_player_data([n for _o, n in pairs])
        untouched = [n for _o, n in pairs if n not in touched]
        if not untouched:
            return 0
        return await rom_handler.delete_many(untouched)
    except Exception:  # noqa: BLE001 - the scan's own failure is the one to raise
        logger.exception("Could not take back the rows this scan had added")
        return 0


async def _merge_renamed(pairs: list[tuple[int, int]], touched=frozenset()) -> int:
    """Apply the pairs, oldest row kept. Returns how many were merged.

    Adoption moves the file fields onto the donor and DELETES the row it took
    them from, and rom_saves / rom_save_states / rom_plays hang off that row by
    cascade. A scan of a large library runs for many minutes with every new row
    visible and playable the moment it lands, so somebody can have played and
    saved against one before the walk finished.

    That used to abandon the merge, which reads as caution and is not: the old
    row keeps `missing_from_fs` and is then invisible to every listing, no later
    scan can pair it - the new name is already in the database, so it never
    enters `created_ids` again - and it lands on the missing-entries screen,
    where one click removes the save files as well. One session was protected by
    giving up every save from before the rename.

    So the data comes across first. Where that meets two memory cards for the
    same person, `move_player_data` sets the second one aside for them to choose
    between, and they are told. It used to refuse and leave the pair as two rows,
    which put back the very state described above for the one person with the
    most at stake.
    """
    merged = 0
    for old_id, new_id in pairs:
        set_aside: list[int] = []
        if new_id in touched:
            set_aside = await rom_handler.move_player_data(new_id, old_id)
        if await rom_handler.adopt_renamed(old_id, new_id):
            merged += 1
            logger.info(
                "A file was renamed rather than replaced: row %d keeps its "
                "metadata, saves and play history, and row %d is dropped.",
                old_id, new_id,
            )
        if set_aside:
            logger.info(
                "Row %d had a second memory card for %d account(s); set aside for "
                "them to choose between.", old_id, len(set_aside),
            )
            await _tell_about_set_aside_cards(old_id, set_aside)
    return merged


async def _tell_about_set_aside_cards(rom_id: int, user_ids) -> None:
    """Tell each account that now has two memory cards for this game. Nobody else.

    Over the socket, so a person who is signed in sees the badge at once. It is
    not the only way they find out: the list the badge counts is read again when
    the app starts, so somebody who was away is told the next time they arrive.
    """
    from handler.socket_handler import emit_event

    for user_id in sorted(set(user_ids)):
        try:
            await emit_event("saves:conflict", {"rom_id": rom_id}, to_user=user_id)
        except Exception:  # noqa: BLE001 - the card is safe; the message is a courtesy
            logger.warning("Could not tell account %s about a set-aside card", user_id,
                           exc_info=True)


# ── One scan at a time, and optionally on a timer ────────────────────────────
#
# The lock used to live in the ROM router, and a handler two directories away
# reached across into it to borrow it. It guards scanning, so it lives with the
# scanner and everybody shares the one. Two locks would be no lock: a timed scan
# running beside a manual one gives two passes marking rows missing and clearing
# them in each other's shadow, which is exactly the bug the comment above
# mark_all_missing records having been fixed once already.
_scan_lock = asyncio.Lock()
_scan_running = False   # read-only status flag, set under the lock

#: Key inside the "roms" config section - the same section the ROM settings
#: screen writes, and NOT the database config table the other loops read. Those
#: are two different stores, and putting the field on one while the loop reads
#: the other is a switch that does nothing.
SCAN_INTERVAL_KEY = "scan_interval_hours"


def resolve_scan_interval_hours(raw) -> int:
    """Hours between automatic scans, or 0 for off.

    Off is the reading of anything that cannot be acted on, including a typo and
    a negative number. A scan walks every platform directory and hashes what it
    has not seen, so starting one because a setting was mistyped is worse than
    doing nothing.
    """
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        return 0
    return value if value > 0 else 0


async def periodic_scan_loop() -> None:
    """Re-scan the ROM tree on a timer, when somebody has asked for one.

    Off unless configured, and the setting is read on every turn so switching it
    on takes effect without a restart. A scan already in progress means this turn
    is skipped rather than queued: a timer that fell behind should not spend the
    night running the scans it missed, one after another.
    """
    from config import config_manager
    from handler.filesystem.rom_paths import roms_library_path

    global _scan_running
    await asyncio.sleep(_SCAN_LOOP_START_DELAY_S)
    while True:
        try:
            hours = resolve_scan_interval_hours(
                config_manager.get_section("roms").get(SCAN_INTERVAL_KEY)
            )
            if hours > 0 and not _scan_lock.locked():
                async with _scan_lock:
                    _scan_running = True
                    try:
                        logger.info("Starting the scheduled ROM scan")
                        # Where the library is NOW, asked like the interval
                        # is: a library moved in Settings was never walked.
                        await scan_roms_path(roms_library_path(config_manager))
                    finally:
                        _scan_running = False
        except asyncio.CancelledError:
            raise
        except Exception:
            # One bad scan must not end the timer. Ending quietly would look
            # exactly like the setting never having worked.
            logger.exception("Scheduled ROM scan failed; the next one will try again")
        # Off still means waiting rather than finishing, or turning it on later
        # would do nothing until a restart and the setting would look broken.
        await asyncio.sleep(_SCAN_LOOP_IDLE_S if hours <= 0 else hours * 3600)


async def scan_roms_path(roms_path: str) -> dict:
    """
    Walk *roms_path*, detect platforms and ROMs, upsert into DB.

    Returns a summary dict:
      { platforms_found, roms_found, roms_new, roms_updated }
    """
    root = Path(roms_path)
    if not root.exists():
        # Announced like any other ending, and carrying why. This exit is the
        # likeliest one on a real install - an unmounted drive, a typo in
        # Settings > ROMs - and it used to return in silence: the request
        # answered 200, no completion event was ever emitted, and the indicator
        # sat on "Starting the scan..." for the life of the page with the only
        # explanation in the server log.
        logger.warning("ROM path does not exist: %s", roms_path)
        stats = {"platforms_found": 0, "roms_found": 0, "roms_new": 0,
                 "roms_updated": 0, "error": "path_missing"}
        await _announce_scan_finished(stats)
        return stats

    stats = {"platforms_found": 0, "roms_found": 0, "roms_new": 0, "roms_updated": 0}

    # Read once for the whole walk rather than per file: it is a YAML file on
    # disk, and a library has thousands of them.
    hash_ceiling = hash_ceiling_bytes()

    # Pre-pass: mark every DB-registered ROM as missing.  The directory walk
    # below re-unsets the flag for anything actually found on disk.  Doing
    # this ONCE up-front (instead of per-directory) is important because
    # multiple fs_slug alias directories can resolve to the same DB platform
    # row (e.g. `snes/`, `snesna/`, `super-nintendo/` all -> slug
    # super-nintendo-entertainment-system).  Marking missing inside the loop
    # caused the last-processed empty alias dir to silently re-mark ROMs that
    # the earlier, populated alias had just found.
    # What was on disk when the scan began. Taken BEFORE everything is marked
    # missing, because that is the only moment the distinction exists - and it
    # is the distinction the whole rename rule rests on. Without it "missing at
    # the end" also means "deleted last January", so a file gone for months is
    # the only candidate on its side and the uniqueness rule waves through a
    # brand new game that happens to share its content.
    #
    # Both questions are table-wide, and asking them table-wide is two
    # statements whatever the platform count. Asked per platform they were two
    # HUNDRED and fourteen on a real install, of which a hundred and ninety two
    # were for platform folders holding nothing.
    present_before: set[int] = set(await rom_handler.present_ids())
    await rom_handler.mark_all_missing()

    # EVERYTHING BELOW RUNS WITH THE WHOLE LIBRARY MARKED MISSING, so any way
    # out of it other than the walk finishing has to put that back. A restart,
    # a mount that goes away, one database error among the thousands of
    # independent per-row writes: without this the rows the walk had not
    # reached stay flagged, every listing filters them out, and the library
    # goes dark with nothing to say why. The cancelled path already knew this
    # and did it; the exception path did not exist.
    # Bound before the `try`, not inside it: the failure handler takes these rows
    # back, and an exception raised between the `try` and the assignment would
    # otherwise turn a scan failure into a NameError from the handler meant to
    # clean up after it.
    created_ids: list[int] = []
    # Bound out here for the same reason, and it earned the move: the failure
    # handler asks which of the created rows a rename would have taken, and that
    # question is per platform. Left inside the `try` it would raise NameError
    # from the handler for any failure that happened before the first platform.
    seen_platform_ids: set[int] = set()
    try:

        # Rows this scan itself created, and only those. The delete at the end of a
        # rename is the first row deletion a scan has ever performed, so what it may
        # reach has to be exact: the tempting substitute, "rows that are not
        # missing", would put a row somebody has been playing for months inside it.
        # Ids only. The disc grouping later in the loop decides which of these is a
        # track of a sheet, so what a row IS cannot be known at the moment it is
        # written - it is read back once the walk is over.
        #: (platform_id, directory, assignments) held back until the walk
        #: finishes - one entry per directory, because a plan means nothing
        #: without the folder it was drawn from. See the
        #: comment where they are collected: grouping edits rows that were here
        #: before this scan, so a run that does not finish must not have done it.
        pending_groups: list[tuple] = []

        # One query for the whole tree. It is the half of "is there anything to do
        # here" that the disk cannot answer: a folder emptied of its files still has
        # rows, and marking those missing is the work this scan exists to do.
        known_counts = await rom_platform_handler.rom_counts_by_fs_slug()

        platform_dirs = [d for d in sorted(root.iterdir()) if d.is_dir()]
        begin_scan_progress(platform_total=len(platform_dirs))
        await _emit_scan_progress()

        for platform_index, platform_dir in enumerate(platform_dirs, start=1):
            # Asked between platforms as well as between files, so a stop lands
            # promptly even on a shelf of empty folders.
            if scan_cancelled():
                break

            fs_slug = platform_dir.name
            slug = slug_from_fs_slug(fs_slug)
            # The platform this folder belongs to, under its own name: another
            # name of one console (`megadrive/` beside `genesis/`) is read into
            # that console's platform, and a platform first met through such a
            # folder is still created under the main name.
            home_slug = canonical_fs_slug(fs_slug)
            info = PLATFORM_MAP.get(home_slug, {})
            display_name = info.get("name", fs_slug.upper())

            # Both supported shapes, read as a union rather than as an either/or -
            # see scan_dirs_for for what the either/or cost. Kept per directory as
            # well as flattened, because which files belong to one disc set is a
            # question about ONE directory listing and must not be asked across two.
            #
            # Read BEFORE the platform is touched, so a folder with nothing in it and
            # nothing in the database costs one directory listing instead of a row
            # upsert and a bulk update. GD makes a folder for every platform it knows,
            # so most installs walk a hundred of these and keep games in a handful.
            rom_files: list[Path] = []
            files_by_dir: list[list[Path]] = []
            excluded_files: set[Path] = set()
            scan_dirs = scan_dirs_for(platform_dir)
            # Which of the directories read here sit directly inside which. A
            # file with no row may have moved out of the folder above it or out
            # of one of the folders below it, and those are the only two places
            # a move between the flat shape and a game folder can come from.
            children_of: dict[str, list[str]] = {}
            for scan_dir in scan_dirs:
                children_of.setdefault(str(scan_dir.parent), []).append(str(scan_dir))
            for scan_dir in scan_dirs:
                try:
                    here = scan_candidates(scan_dir)
                except PermissionError as e:
                    logger.warning("Permission error reading %s: %s", scan_dir, e)
                    continue
                if here:
                    files_by_dir.append(here)
                    rom_files.extend(here)

            if platform_has_nothing(files=rom_files, rows=known_counts.get(fs_slug)):
                continue

            # Upsert platform (aliased fs_slugs reuse the existing row by slug)
            platform = await rom_platform_handler.upsert(home_slug, slug, display_name)
            stats["platforms_found"] += 1
            seen_platform_ids.add(platform.id)

            # `display_name` rather than a field off the row: it is already worked
            # out above, and reading more of the platform than the walk needs is how
            # this function grows a dependency on whatever the row happens to carry.
            note_scan_platform(display_name, index=platform_index,
                               files_total=len(rom_files))
            await _emit_scan_progress()

            # What this platform was told never to look at. Read once per platform
            # rather than per file, and only ever used to decline to ADD something.
            excludes = parse_patterns(getattr(platform, "scan_exclude", None))

            for file_index, rom_file in enumerate(rom_files, start=1):
                if scan_cancelled():
                    break
                note_scan_file(rom_file.name, done=file_index)
                await _emit_scan_progress()

                stats["roms_found"] += 1
                fs_name = rom_file.name
                fs_name_no_ext = _strip_tags(rom_file.stem)
                fs_extension = rom_file.suffix.lstrip(".")
                fs_path = str(rom_file.parent)
                try:
                    fs_size = rom_file.stat().st_size
                except OSError:
                    fs_size = 0

                existing = await rom_handler.get_by_fs_name(
                    platform.id, fs_name, fs_path)

                # No row here. Before this becomes a new game, ask whether it is
                # an old one that moved: into its own folder, or back out of it.
                # The rename rule below cannot answer this, because it pairs on
                # the digest and a digest is nullable - unhashed is routine for
                # anything over the ceiling, which is most of a disc library and
                # exactly the files somebody would reorganise.
                if existing is None:
                    near = [str(rom_file.parent.parent)]
                    near += children_of.get(str(rom_file.parent), [])
                    came_from = moved_row(
                        [{"id": r.id, "fs_path": r.fs_path}
                         for r in await rom_handler.rows_named_in(
                             platform.id, fs_name, near)],
                        fs_name, _still_on_disk,
                    )
                    if came_from is not None:
                        await rom_handler.move_row_to(came_from, fs_path)
                        existing = await rom_handler.get_by_fs_name(
                            platform.id, fs_name, fs_path)
                        logger.info(
                            "%s moved to %s and kept its entry", fs_name, fs_path)

                # Deliberately AFTER the lookup, and only for something that is not
                # here yet. Filtering the directory listing instead would mean an
                # excluded file that already has a row is never seen by the scan, so
                # the row would be left marked missing - a pattern quietly deleting
                # part of the library, which is exactly what must not happen without
                # somebody being asked. Removing what already slipped in is a
                # separate and deliberate act.
                if existing is None and excludes and is_excluded(
                        str(rom_file), excludes, root=str(platform_dir)):
                    stats["roms_excluded"] = stats.get("roms_excluded", 0) + 1
                    # Remembered, because the disc grouping below is decided from
                    # the directory listing and a file that is not in the library
                    # must not shape the sets around it. Excluding
                    # "Game (Disc 2).chd" otherwise left "Game (Disc 1).chd" filed
                    # as disc one of a set whose second disc does not exist.
                    excluded_files.add(rom_file)
                    continue

                loop = asyncio.get_running_loop()
                # A CHD hashed under the old scheme carries a CRC of its compressed
                # container, and this format no longer produces one at all. A CRC on
                # a CHD therefore means the row predates the fix and holds digests
                # that match nothing, so it is redone and the stale values cleared.
                stale_chd = (
                    existing is not None
                    and fs_extension.lower() == "chd"
                    and bool(existing.crc_hash)
                )
                # Too large to read for a hash, if a ceiling is set at all. A CHD is
                # exempt: its digest comes out of its own header, not out of the
                # file. Whatever the row already has is kept - the ceiling declines
                # to spend the read, it does not throw away an answer.
                too_big = skip_hashing(fs_size, fs_extension, hash_ceiling)
                drop_stale_hashes = False
                if too_big and str(rom_file) not in _unhashed_by_ceiling:
                    _unhashed_by_ceiling.add(str(rom_file))
                    logger.info(
                        "%s is larger than the %d byte hashing ceiling, so it was not "
                        "read to hash it. Ask for its checksums from its own page if "
                        "you want it identified by hash.", fs_name, hash_ceiling,
                    )

                # A file of no size has nothing to hash, and the digest of nothing
                # is the same for every one of them. Treated like a file over the
                # ceiling: no digest rather than a meaningless one.
                empty = fs_size == 0
                if existing is None:
                    stats["roms_new"] += 1
                    if too_big or empty:
                        crc_hash = md5_hash = sha1_hash = ""
                    else:
                        crc_hash, md5_hash, sha1_hash = await loop.run_in_executor(
                            None, _compute_hashes, rom_file, hash_ceiling
                        )
                        logger.debug("Hashed %s  CRC=%s  MD5=%s  SHA1=%s", fs_name, crc_hash, md5_hash, sha1_hash[:8])
                else:
                    stats["roms_updated"] += 1
                    changed_on_disk = existing.fs_size_bytes != fs_size
                    needs_hashing = (
                        changed_on_disk
                        or not _has_hashes(existing)
                        or stale_chd
                    )
                    if empty:
                        # It shrank to nothing. Whatever digests the row holds
                        # describe a file that is no longer there, so they go rather
                        # than being replaced with the digest of nothing.
                        crc_hash = md5_hash = sha1_hash = ""
                        drop_stale_hashes = True
                    elif needs_hashing and not too_big:
                        crc_hash, md5_hash, sha1_hash = await loop.run_in_executor(
                            None, _compute_hashes, rom_file, hash_ceiling
                        )
                        logger.debug("Re-hashed %s  CRC=%s  MD5=%s  SHA1=%s", fs_name, crc_hash, md5_hash, sha1_hash[:8])
                    elif changed_on_disk:
                        # Over the ceiling AND a different file from the one those
                        # digests describe. Keeping them would be worse than having
                        # none: the scraper stops matching on filename the moment a
                        # hash exists, so the ROM would be confidently identified as
                        # whatever used to sit here. And nothing would ever repair
                        # it, because the size test that spotted the change only
                        # fires once - the row is about to be written with the new
                        # size. Drop them and let the page offer to compute them.
                        crc_hash = md5_hash = sha1_hash = ""
                        drop_stale_hashes = True
                    else:
                        crc_hash = existing.crc_hash
                        md5_hash = existing.md5_hash or ""
                        sha1_hash = getattr(existing, "sha1_hash", None) or ""

                written = await rom_handler.upsert(
                    platform_id=platform.id,
                    fs_name=fs_name,
                    fs_name_no_ext=fs_name_no_ext,
                    fs_extension=fs_extension,
                    fs_path=fs_path,
                    fs_size_bytes=fs_size,
                    crc_hash=crc_hash,
                    md5_hash=md5_hash,
                    sha1_hash=sha1_hash,
                    # The filename usually says. Until now only the remote-source
                    # browser read it, so a ROM the scraper did not recognise ended
                    # up with no region at all while it was written on the file.
                    region_hint=region_from_name(fs_name),
                )
                if existing is None and written is not None:
                    created_ids.append(written.id)

                # The upsert above writes a hash only when it has one, so it cannot
                # express "this format has no container digest" and the old values
                # would survive to be offered to the scraper again. This runs once
                # per affected row: afterwards there is no CRC and nothing is stale.
                #
                # A CHD older than v5 leaves nothing to replace them with, so its
                # container SHA-1 goes too. It described the compression, and the
                # scraper is better told nothing than told that.
                if drop_stale_hashes:
                    await rom_handler.clear_container_hashes(
                        platform.id, fs_name, fs_path, drop_sha1=True
                    )
                    logger.info(
                        "%s changed on disk and is over the hashing ceiling, so its "
                        "old checksums were dropped rather than left describing a "
                        "file that is no longer there.", fs_name,
                    )
                elif stale_chd and not crc_hash:
                    await rom_handler.clear_container_hashes(
                        platform.id, fs_name, fs_path, drop_sha1=not sha1_hash
                    )
                    logger.info(
                        "Cleared container hashes on %s, %s", fs_name,
                        "now identified by its header" if sha1_hash
                        else "which carries no source hash to identify it by",
                    )

            # ── Multi-disk sets and disc tracks ──────────────────────────────────
            # Which files belong together can only be decided once the whole
            # directory has been seen: disk 1 is not part of a set until disk 2
            # shows up beside it. The lowest-numbered disk stands for the game and
            # the rest are marked extra, which is what the library listings filter
            # on - the files stay, they simply stop appearing as separate games.
            # Per directory, then merged. A .cue in the platform folder must not
            # claim a track file that lives in roms/ beside it: the two are separate
            # layouts, and grouping across them would fold unrelated files into one
            # disc set.
            # Kept apart per directory all the way to the write, not merged into
            # one plan. Merging keys the plan on a bare file name, so two folders
            # that each hold a `Disc 1.cue` collapse onto one entry: the folder
            # walked last decides, and the write then hands its membership to the
            # other game and clears it off a third.
            plans: list[tuple[str, dict]] = []
            for here in files_by_dir:
                kept = [f for f in here if f not in excluded_files]
                if not kept:
                    continue
                plans.append((str(kept[0].parent), plan_disk_assignments(kept)))

            # Held until the walk is over rather than written per platform. A
            # stopped scan puts back what it changed, and grouping is a change
            # to rows that were ALREADY HERE: a disc found now can mark a disc
            # found last year as an extra, which the listings filter out. Undone
            # halfway, that game is simply gone from the library with nothing
            # deleted. Applied at the end, a stopped scan never touched it.
            if rom_files:
                for where, plan in plans:
                    pending_groups.append((platform.id, where, plan))

            sets = len({group for _w, plan in plans
                        for group, _n, _e, _t in plan.values() if group})
            tracks = sum(1 for _w, plan in plans
                         for _g, _n, _e, sheet in plan.values() if sheet)
            logger.info(
                "Scanned platform %s - %d ROM(s) found%s%s",
                fs_slug, len(rom_files),
                f", {sets} multi-disk title(s)" if sets else "",
                f", {tracks} track file(s) folded into their sheet" if tracks else "",
            )

        # ── Stopped partway ──────────────────────────────────────────────────────
        # A scan that did not finish makes NO CLAIM about what is missing. It opened
        # by marking everything missing and un-marks what the walk finds, so leaving
        # now would report every platform it had not reached as empty - the library
        # goes half dark and nothing says why. Put back exactly the snapshot taken
        # before it started and let the next complete scan decide.
        if scan_cancelled():
            # And the rows this run created go with it, or "back as it was" is
            # not what happens. They are also the half that cannot be repaired
            # later: the rename adoption below can only pair a donor with a row
            # THIS scan created, so a new row left behind by a stopped scan is a
            # row no future scan will create again, and the old row holding the
            # artwork, the saves and the play history goes missing for good.
            # Rows only, never files - the files are what the next scan finds.
            # ...except one a person has already touched. Deleting a ROM row
            # takes its savestates, memory cards and play history by cascade,
            # and a scan of a large library runs for many minutes with each row
            # visible and playable the moment it lands. Somebody can have played
            # and saved against a row this run created before Stop was pressed;
            # taking that back is not undoing our own work, it is deleting
            # theirs - and the line on screen says "nothing was marked missing"
            # while it happens. Those rows stay, and the rename adoption gives
            # up on them, which is the smaller loss by a wide margin.
            touched = await rom_handler.ids_with_player_data(created_ids)
            undone = 0
            for rom_id in created_ids:
                if rom_id in touched:
                    continue
                if await rom_handler.delete(rom_id):
                    undone += 1
            await rom_handler.restore_present(present_before)
            logger.info(
                "ROM scan stopped on request after %d platform(s); the library is "
                "back as it was, %d row(s) this run had added were taken back, "
                "%d kept because somebody had already played or saved against "
                "them, and nothing was marked missing",
                stats["platforms_found"], undone, len(touched),
            )
            stats["roms_new"] -= undone
            stats["cancelled"] = True
            # Announced on this exit too, and by the same function: the views hang
            # "and now reload the list" on this event and the Classic sidebar clears
            # its spinner there, so the silent exit left that spinner turning until
            # somebody reloaded the page.
            await _announce_scan_finished(stats)
            return stats

        # The walk finished, so the disc grouping worked out along the way is
        # safe to write. Held until here because it edits rows that existed
        # before this scan - see where it is collected.
        for platform_id, where, assignments in pending_groups:
            await rom_handler.apply_disk_groups(platform_id, where, assignments)

        # Clean up platforms whose folder no longer exists
        scanned_fs_slugs = {d.name for d in root.iterdir() if d.is_dir()}
        all_platforms = await rom_platform_handler.get_all_simple()
        for p in all_platforms:
            # A platform the walk actually visited is not gone, whatever its
            # folder is called. Several directory names map to one platform row
            # (snes / snesna / super-nintendo, psx / playstation, dos / ms-dos)
            # and upsert deliberately reuses the row by slug without touching
            # the fs_slug it was created with. So consolidating an alias folder
            # into the canonical one left this loop marking the whole platform
            # missing immediately after the walk had found every one of its
            # files - every scan, for ever, with no error anywhere.
            if p.id in seen_platform_ids:
                continue
            if p.fs_slug not in scanned_fs_slugs:
                logger.info("Platform folder gone for %s - marking all ROMs missing", p.fs_slug)
                await rom_handler.mark_all_missing(p.id)

        # ── Renames, once every directory has been walked ────────────────────────
        # Only here, and not in the per-file loop, because only here is the question
        # answerable. Halfway through a scan a row can look gone and turn up in the
        # next folder: several alias directories feed one platform row, which is the
        # bug the comment above mark_all_missing records having been fixed once
        # already. And in the loop the answer would depend on the order the
        # filesystem happened to list things in, which is not an answer.
        pairs = await _renames_this_run(created_ids, present_before, seen_platform_ids)
        if pairs:
            touched = await rom_handler.ids_with_player_data([n for _o, n in pairs])
            stats["roms_renamed"] = await _merge_renamed(pairs, touched)
            stats["roms_new"] -= stats["roms_renamed"]

        logger.info(
            "ROM scan complete: %d platforms, %d ROMs (%d new, %d updated%s)",
            stats["platforms_found"],
            stats["roms_found"],
            stats["roms_new"],
            stats["roms_updated"],
            f", {stats['roms_renamed']} renamed" if stats.get("roms_renamed") else "",
        )
        await _announce_scan_finished(stats)
        return stats
    except asyncio.CancelledError:
        # Shutting down, and shutting down is on a clock. This is how a container
        # stop reaches a scan running as a background task, and the handler below
        # would answer it with a delete per row, each in its own transaction. On
        # a library of any size that does not finish inside the few seconds the
        # process is given - so the run was undone PARTWAY, with nobody able to
        # find out how far, and the second cancellation went straight through the
        # inner `except Exception`, skipping the progress reset as well.
        #
        # So this exit does the cheap half: one bulk UPDATE putting the missing
        # flags back, which is the half that matters, and one DELETE for the rows
        # a rename would have absorbed - the only rows no later scan makes again.
        # Every other row this run created stays, and the next scan will find
        # its file and make the same decision with time to do it in. Nothing is
        # announced either - the socket is going away with everything else, and
        # the watchdog on the client covers the gap.
        undone = await _put_back_after_an_unfinished_scan(
            created_ids, present_before, seen_platform_ids)
        reset_scan_progress()
        logger.info(
            "ROM scan cancelled while shutting down; the missing flags are back "
            "as they were, %d row(s) a rename would have absorbed were taken back "
            "and the rest were left for the next scan",
            undone,
        )
        raise
    except BaseException:
        # Not swallowed - restored and re-raised. A scan that never works has
        # to look like a scan that failed, not like one that keeps finding
        # nothing.
        #
        # The flags back, and the rows a rename would have absorbed, which is a
        # much shorter list than "everything this run made" and is the whole of
        # the argument for removing any of them. A genuinely new ROM carries none
        # of that: the next scan finds the file and makes the row again, so
        # taking it back buys nothing and costs a full re-read and re-hash of
        # everything the run had got through. One transient database error near
        # the end of a long scan used to do exactly that to the whole library.
        undone = await _put_back_after_an_unfinished_scan(
            created_ids, present_before, seen_platform_ids)
        logger.exception(
            "ROM scan failed; the library is back as it was, %d row(s) this run "
            "had added were taken back and nothing was left marked missing",
            undone,
        )
        # Announced like the other two exits. The views hang their reload on this
        # event and the Classic sidebar clears its spinner there, so the silent
        # exit left the bar turning until the watchdog filled it in - as an
        # ordinary finish, because nothing had said otherwise. `error` says which
        # kind of ending this was; the screens read it and say so.
        stats["error"] = "failed"
        await _announce_scan_finished(stats)
        raise
