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
import zlib
from pathlib import Path

from handler.database.rom_handler import rom_handler, rom_platform_handler
from handler.metadata.rom_platform_map import PLATFORM_MAP, slug_from_fs_slug
from utils.disk_sets import group_disks
from utils.rom_names import region_from_name

logger = logging.getLogger(__name__)

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


async def scan_roms_path(roms_path: str) -> dict:
    """
    Walk *roms_path*, detect platforms and ROMs, upsert into DB.

    Returns a summary dict:
      { platforms_found, roms_found, roms_new, roms_updated }
    """
    root = Path(roms_path)
    if not root.exists():
        logger.warning("ROM path does not exist: %s", roms_path)
        return {"platforms_found": 0, "roms_found": 0, "roms_new": 0, "roms_updated": 0}

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
    for p in await rom_platform_handler.get_all_simple():
        await rom_handler.mark_all_missing(p.id)

    for platform_dir in sorted(root.iterdir()):
        if not platform_dir.is_dir():
            continue

        fs_slug = platform_dir.name
        slug = slug_from_fs_slug(fs_slug)
        info = PLATFORM_MAP.get(fs_slug, {})
        display_name = info.get("name", fs_slug.upper())

        # Upsert platform (aliased fs_slugs reuse the existing row by slug)
        platform = await rom_platform_handler.upsert(fs_slug, slug, display_name)
        stats["platforms_found"] += 1

        # Support both structure A (roms directly) and B (roms/ subdir)
        roms_subdir = platform_dir / "roms"
        scan_dir = roms_subdir if roms_subdir.is_dir() else platform_dir

        # Walk ROM files
        try:
            rom_files = scan_candidates(scan_dir)
        except PermissionError as e:
            logger.warning("Permission error reading %s: %s", scan_dir, e)
            continue

        for rom_file in rom_files:
            stats["roms_found"] += 1
            fs_name = rom_file.name
            fs_name_no_ext = _strip_tags(rom_file.stem)
            fs_extension = rom_file.suffix.lstrip(".")
            fs_path = str(rom_file.parent)
            try:
                fs_size = rom_file.stat().st_size
            except OSError:
                fs_size = 0

            existing = await rom_handler.get_by_fs_name(platform.id, fs_name)
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

            if existing is None:
                stats["roms_new"] += 1
                if too_big:
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
                if needs_hashing and not too_big:
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

            await rom_handler.upsert(
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
                    platform.id, fs_name, drop_sha1=True
                )
                logger.info(
                    "%s changed on disk and is over the hashing ceiling, so its "
                    "old checksums were dropped rather than left describing a "
                    "file that is no longer there.", fs_name,
                )
            elif stale_chd and not crc_hash:
                await rom_handler.clear_container_hashes(
                    platform.id, fs_name, drop_sha1=not sha1_hash
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
        assignments = plan_disk_assignments(rom_files)

        if rom_files:
            await rom_handler.apply_disk_groups(platform.id, assignments)

        sets = len({group for group, _n, _e, _t in assignments.values() if group})
        tracks = sum(1 for _g, _n, _e, sheet in assignments.values() if sheet)
        logger.info(
            "Scanned platform %s - %d ROM(s) found%s%s",
            fs_slug, len(rom_files),
            f", {sets} multi-disk title(s)" if sets else "",
            f", {tracks} track file(s) folded into their sheet" if tracks else "",
        )

    # Clean up platforms whose folder no longer exists
    scanned_fs_slugs = {d.name for d in root.iterdir() if d.is_dir()}
    all_platforms = await rom_platform_handler.get_all_simple()
    for p in all_platforms:
        if p.fs_slug not in scanned_fs_slugs:
            logger.info("Platform folder gone for %s - marking all ROMs missing", p.fs_slug)
            await rom_handler.mark_all_missing(p.id)

    logger.info(
        "ROM scan complete: %d platforms, %d ROMs (%d new, %d updated)",
        stats["platforms_found"],
        stats["roms_found"],
        stats["roms_new"],
        stats["roms_updated"],
    )
    return stats
