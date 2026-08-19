"""Turning a WHDLoad archive into something a browser can boot.

Most of the Amiga catalogue ships as WHDLoad installs: an .lha holding a hard
drive directory rather than a disk image. EmulatorJS cannot run them at all -
its Amiga core aborts - so they go to vAmigaWeb instead, and vAmigaWeb will not
read an .lha either. What it does read is a ZIP of loose files, which it writes
into its own filesystem and hands to the emulator core to format as an FFS hard
drive. So the job here is to unpack the archive and lay the files out the way an
Amiga expects to boot from::

    S/Startup-Sequence          generated: cd into the game and run its slave
    C/WHDLoad                   the WHDLoad executable, supplied by the admin
    Devs/Kickstarts/<rom>       a Kickstart, from the firmware store
    Devs/Kickstarts/<rom>.RTB   its relocation table, supplied by the admin
    <GameDir>/...               straight out of the archive

Two of those the application cannot provide: WHDLoad is not open source, and a
Kickstart is a file somebody owns. Both come from the same store the emulator
BIOS files already use, and until they are there this refuses to build an image
rather than producing one that boots to an error requester.

The Kickstart choice is not free either, and it was the whole difficulty when
this was worked out. WHDLoad emulates whatever Kickstart the *game* wants; the
one picked here is the one the *machine* boots from, and it has to satisfy two
constraints at once:

  * 2.0 or later, because 1.3 has no hard-drive filesystem in ROM and stops at
    "Not a DOS disk";
  * not AGA-only, because an A1200 ROM forces an AGA machine and titles written
    for OCS hardware crash on it.

40.063 (A500/A600/A2000) and 2.04 are the ones that satisfy both. An A1200 ROM
is accepted as a fallback for anyone who has nothing else, together with the AGA
machine it demands - AGA-era titles are fine on it, older ones may not be.
"""

from __future__ import annotations

import asyncio
import io
import logging
import re
import shutil
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

from handler.roms.firmware_handler import firmware_root
from utils.disk_sets import group_disks, sort_key

logger = logging.getLogger(__name__)

# The archive extensions that hold a WHDLoad install.
WHDLOAD_SUFFIXES = frozenset({".lha", ".lzh"})

# An unpacked install is a few megabytes; the largest in the wild are well under
# a hundred. These bound what a malformed or hostile archive can cost us, since
# the whole thing is read into memory to be zipped.
MAX_UNPACKED_BYTES = 512 * 1024 * 1024
MAX_ENTRIES = 20_000
UNPACK_TIMEOUT_S = 180

# What a player's own saves may be. A WHDLoad savegame is written beside the
# slave and is measured in kilobytes, so these are deliberately far tighter than
# the limits on the install itself - the save arrives from a browser, and the
# emulator running there is the only thing that decides what goes into it.
MAX_SAVE_BYTES = 8 * 1024 * 1024
MAX_SAVE_ENTRIES = 200

# Support files the admin supplies once, shared by every WHDLoad title. They sit
# beside the per-core BIOS directories rather than inside one: WHDLoad is not
# firmware for any core, it is an Amiga program.
SUPPORT_DIR = "whdload"
WHDLOAD_BINARY = "WHDLoad"

# Paths a player's save may never occupy. Everything here comes out of the
# firmware store and is put on the drive by GD itself; a save allowed to land on
# one of them would be choosing which Kickstart the machine boots, or what runs
# at startup. Compared lowercased, because AmigaDOS does not care about case and
# neither should the check.
RESERVED_PATHS = ("s/startup-sequence", f"c/{WHDLOAD_BINARY}".lower(), "devs/kickstarts/")

# Where their authors publish them. Both are free of charge and redistributed
# unmodified, which is what makes fetching them reasonable at all; a Kickstart
# is deliberately absent from this list.
WHDLOAD_URL = "https://whdload.de/whdload/WHDLoad_usr.lha"
SKICK_URLS = (
    "https://aminet.net/util/boot/skick346.lha",
    "https://ftp.funet.fi/pub/amiga/aminet/util/boot/skick346.lha",
)
_USER_AGENT = "GamesDownloader (+https://github.com/60plus/GamesDownloader)"

# Kickstarts that can boot a hard drive, best first. The name is the one the
# firmware registry already uses, so a ROM uploaded for the emulator is the same
# file this reads - nobody supplies it twice.
#
# `aga` marks a ROM that forces an AGA machine. Preferring the ECS ones is not a
# nicety: it is the difference between an OCS title running and crashing.
_KICKSTARTS: tuple[tuple[str, bool], ...] = (
    ("kick40063.A600", False),   # 3.1 for A500/A600/A2000 - the one to want
    ("kick37175.A500", False),   # 2.04
    ("kick37350.A600", False),   # 2.05
    ("kick40068.A1200", True),   # 3.1 A1200 - AGA only
    ("kick39106.A1200", True),   # 3.0 A1200 - AGA only
)

# What to configure the emulated machine as, per Kickstart family. These are
# vAmigaWeb's own option names and values.
_ECS_MACHINE = {
    "AGNUS_REVISION": "ECS_2MB",
    "DENISE_REVISION": "ECS",
    "CHIP_RAM": "2048",
    "SLOW_RAM": "0",
    "FAST_RAM": "8192",
    "CPU_REVISION": "0",
    "CPU_OVERCLOCKING": "1",
}
_AGA_MACHINE = {
    "AGNUS_REVISION": "AGA",
    "DENISE_REVISION": "AGA",
    "CHIP_RAM": "2048",
    "SLOW_RAM": "0",
    "FAST_RAM": "8192",
    "CPU_REVISION": "2",
    "CPU_OVERCLOCKING": "2",
}


@dataclass(frozen=True)
class Plan:
    """What it would take to run this ROM, decided before anything is built."""

    mode: str            # "harddrive" for a WHDLoad install, "floppy" otherwise
    ok: bool
    missing: tuple[str, ...]
    kickstart: str | None
    machine: dict[str, str]
    slave: str | None
    warning: str | None = None
    # Disk images inside the ROM when it is an archive of them, in the order a
    # player would insert them. Empty for a bare .adf, which is its own disk.
    disks: tuple[str, ...] = ()


def is_whdload_archive(name: str) -> bool:
    """True when *name* looks like a WHDLoad install rather than a disk image.

    The name alone, which is all some callers have. Prefer looks_like_whdload
    where the file itself is at hand: plenty of WHDLoad installs are published
    as ZIPs, and those are indistinguishable from a ZIP of floppies until
    somebody looks inside.
    """
    return Path(name).suffix.lower() in WHDLOAD_SUFFIXES


def looks_like_whdload(archive: Path) -> bool:
    """True when *archive* holds a WHDLoad install.

    An .lha is taken at its word: that is how WHDLoad has always been shipped,
    and opening every one to check would cost an unpack per library listing.

    A .zip has to be opened, because both things arrive as one. The collections
    GD downloads from publish installs as ZIPs - Another World comes as
    AnotherWorld_v2.4_0425.zip with the slave inside - and judging by extension
    called them floppies, handed the archive to the emulator as a disk image,
    and left the player looking at a machine with nothing in its drive.

    The slave is what decides it: no WHDLoad install lacks one, and no set of
    floppies has one.
    """
    if is_whdload_archive(archive.name):
        return True
    if archive.suffix.lower() != ".zip":
        return False
    try:
        with zipfile.ZipFile(archive) as z:
            return any(n.lower().endswith(".slave") for n in z.namelist())
    except (OSError, zipfile.BadZipFile):
        return False


# ── Support files ─────────────────────────────────────────────────────────────

def support_dir() -> Path:
    return firmware_root() / SUPPORT_DIR


def _kickstart_path(name: str) -> Path:
    # Kickstarts live in the emulator's own firmware directory, named after the
    # libretro core, because that is where the BIOS screen already puts them.
    return firmware_root() / "puae" / name


def available_kickstart() -> tuple[str, bool] | None:
    """The best Kickstart on disk that can boot a hard drive, or None.

    This is the ROM the *machine* runs, which is a different question from the
    ROM a game wants - see kickstarts_on_hand().
    """
    for name, aga_only in _KICKSTARTS:
        if _kickstart_path(name).is_file():
            return name, aga_only
    return None


def kickstarts_on_hand() -> list[str]:
    """Every Kickstart in the store, whatever era.

    All of them go onto the hard drive, because the one WHDLoad wants is the
    one the *game* was written for, not the one the machine boots from. A 1992
    title asks for 1.3 while the machine runs 3.1, and WHDLoad emulates the
    difference - which is the entire reason it exists. Shipping only the boot
    ROM leaves the game asking for a file that is sitting in the store unused.
    """
    d = firmware_root() / "puae"
    if not d.is_dir():
        return []
    return sorted(
        p.name for p in d.iterdir()
        if p.is_file() and re.fullmatch(r"kick\d+\.[A-Za-z0-9]+", p.name)
    )


def read_kickstart(name: str) -> bytes | None:
    """The bytes of one stored Kickstart, or None. Only names we know."""
    if name not in {n for n, _ in _KICKSTARTS} | set(kickstarts_on_hand()):
        return None
    p = _kickstart_path(name)
    return p.read_bytes() if p.is_file() else None


def support_status() -> dict:
    """Which shared pieces are present, for the settings screen."""
    ks = available_kickstart()
    whdload = support_dir() / WHDLOAD_BINARY
    on_hand = kickstarts_on_hand()
    return {
        "whdload": {
            "present": whdload.is_file(),
            "size": whdload.stat().st_size if whdload.is_file() else 0,
        },
        "kickstart": {
            "present": ks is not None,
            "name": ks[0] if ks else None,
            "aga_only": ks[1] if ks else False,
            "accepted": [n for n, _ in _KICKSTARTS],
        },
        # Every ROM in the store goes on the hard drive for WHDLoad to emulate,
        # so the relocation tables are per-ROM rather than one for the boot ROM.
        "relocation_tables": [
            {"kickstart": n, "name": _rtb_name(n),
             "present": (support_dir() / _rtb_name(n)).is_file()}
            for n in on_hand
        ],
    }


def _rtb_name(kickstart: str) -> str:
    return f"{kickstart}.RTB"


def store_support_file(name: str, data: bytes) -> dict:
    """Save a shared WHDLoad file. Only the names this module asks for."""
    if name != WHDLOAD_BINARY and not re.fullmatch(r"kick\d+\.[A-Za-z0-9]+\.RTB", name):
        raise ValueError(f"not a WHDLoad support file: {name!r}")
    if not data:
        raise ValueError("file is empty")
    dest = support_dir() / name
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.name + ".part")
    tmp.write_bytes(data)
    tmp.replace(dest)
    logger.info("Stored WHDLoad support file %s (%d bytes)", name, len(data))
    return {"name": name, "size": len(data)}


def remove_support_file(name: str) -> bool:
    """Drop a stored shared file. False when there was nothing to drop.

    Same names as storing accepts and no others, so a path cannot be walked out
    of the support directory by way of the delete.
    """
    if name != WHDLOAD_BINARY and not re.fullmatch(r"kick\d+\.[A-Za-z0-9]+\.RTB", name):
        raise ValueError(f"not a WHDLoad support file: {name!r}")
    target = support_dir() / name
    if not target.is_file():
        return False
    target.unlink()
    logger.info("Removed WHDLoad support file %s", name)
    return True


# ── Reading the archive ───────────────────────────────────────────────────────

def _lha_binary() -> str:
    exe = shutil.which("lha") or shutil.which("lhasa")
    if exe is None:
        raise RuntimeError(
            "no lha extractor on PATH - install the 'lhasa' package to run "
            "WHDLoad archives"
        )
    return exe


def _unpack(archive: Path, dest: Path) -> list[Path]:
    """Extract *archive* into *dest* and return the files, refusing escapes."""
    if archive.suffix.lower() == ".zip":
        _unpack_zip(archive, dest)
    else:
        subprocess.run(
            [_lha_binary(), f"-xw={dest}", str(archive)],
            check=True,
            capture_output=True,
            timeout=UNPACK_TIMEOUT_S,
        )
    files = _scan(dest)
    if not files:
        raise ValueError("archive is empty")
    return files


def _scan(dest: Path) -> list[Path]:
    """Every real file under *dest*, in order, refusing escapes and bombs."""
    root = dest.resolve()
    files: list[Path] = []
    total = 0
    for p in sorted(dest.rglob("*")):
        if not p.is_file() or p.is_symlink():
            continue
        # lhasa sanitises names, but an archive is untrusted input and the cost
        # of checking is nothing next to writing outside the temp directory.
        if not p.resolve().is_relative_to(root):
            raise ValueError(f"archive entry escapes its directory: {p}")
        total += p.stat().st_size
        if total > MAX_UNPACKED_BYTES or len(files) >= MAX_ENTRIES:
            raise ValueError("archive unpacks to more than a WHDLoad install ever is")
        files.append(p)
    return files


def _unpack_zip(archive: Path, dest: Path) -> None:
    """Extract a ZIPped WHDLoad install, refusing what a ZIP can be made to do.

    Python's extractall does sanitise names these days, but this is untrusted
    input downloaded from a public collection, and the two things worth
    refusing outright are cheap to check: an entry that resolves outside the
    directory, and a declared size that adds up to more than any install is.
    The declared size is checked before extracting, so a bomb is refused rather
    than written out and then noticed.
    """
    root = dest.resolve()
    with zipfile.ZipFile(archive) as z:
        entries = [i for i in z.infolist() if not i.is_dir()]
        if len(entries) > MAX_ENTRIES:
            raise ValueError("archive holds more files than a WHDLoad install ever does")
        if sum(i.file_size for i in entries) > MAX_UNPACKED_BYTES:
            raise ValueError("archive unpacks to more than a WHDLoad install ever is")
        for info in entries:
            target = (dest / info.filename).resolve()
            if not target.is_relative_to(root):
                raise ValueError(f"archive entry escapes its directory: {info.filename}")
            target.parent.mkdir(parents=True, exist_ok=True)
            with z.open(info) as src, open(target, "wb") as out:
                shutil.copyfileobj(src, out)


def _apply_saves(saves: bytes, dest: Path) -> int:
    """Write a player's saved files over the freshly unpacked install.

    This is how a WHDLoad title keeps what it wrote. The hard drive is built from
    the archive on every launch - which is what lets a replaced Kickstart take
    effect - so anything the game saved onto it is gone by the next visit unless
    it is put back. The browser sends only the files that differ from the ones
    GD put there, so this is kilobytes: a savegame, a high-score table.

    The bytes come from a browser, so they are treated as hostile:

    * the declared size is checked before anything is written, so a bomb is
      refused rather than unpacked and then noticed,
    * an entry resolving outside *dest* is refused outright,
    * and the paths GD owns are refused too. Without that last check a save
      could put its own file at Devs/Kickstarts/, and the machine would boot the
      ROM the save chose rather than the one the administrator installed.

    Returns how many files were written.
    """
    root = dest.resolve()
    written = 0
    with zipfile.ZipFile(io.BytesIO(saves)) as z:
        entries = [i for i in z.infolist() if not i.is_dir()]
        if len(entries) > MAX_SAVE_ENTRIES:
            raise ValueError("that is more files than a save ever holds")
        if sum(i.file_size for i in entries) > MAX_SAVE_BYTES:
            raise ValueError("that is larger than a save ever is")
        for info in entries:
            rel = info.filename.replace("\\", "/").lstrip("/")
            low = rel.lower()
            if any(low == r or low.startswith(r) for r in RESERVED_PATHS):
                raise ValueError(f"a save may not write {info.filename}")
            target = (dest / rel).resolve()
            if not target.is_relative_to(root):
                raise ValueError(f"save entry escapes its directory: {info.filename}")
            target.parent.mkdir(parents=True, exist_ok=True)
            with z.open(info) as src, open(target, "wb") as out:
                shutil.copyfileobj(src, out)
            written += 1
    return written


def _find_slave(files: list[Path], root: Path) -> Path | None:
    """The .slave WHDLoad should run.

    An install normally has exactly one. Where there are several - a title with
    a separate CD32 or AGA build - the shallowest wins, and among equals the
    shortest name, which is the plain version rather than a variant.
    """
    slaves = [p for p in files if p.suffix.lower() == ".slave"]
    if not slaves:
        return None
    return min(slaves, key=lambda p: (len(p.relative_to(root).parts), len(p.name)))


# ── Planning and building ─────────────────────────────────────────────────────

def plan(archive: Path) -> Plan:
    """Work out whether this archive can run, without building anything."""
    missing: list[str] = []
    if not (support_dir() / WHDLOAD_BINARY).is_file():
        missing.append("whdload")

    ks = available_kickstart()
    if ks is None:
        missing.append("kickstart")
    kickstart, aga_only = ks if ks else (None, False)

    # A relocation table is needed per Kickstart, not once. Missing ones are a
    # warning rather than a refusal: WHDLoad only wants the table for whichever
    # ROM this particular game asks it to emulate, and we cannot know which
    # without reading the slave.
    without_rtb = [
        n for n in kickstarts_on_hand()
        if not (support_dir() / _rtb_name(n)).is_file()
    ]

    # A floppy needs none of this. The emulator carries AROS, which boots a disk
    # on its own, so a machine with no Kickstart at all still plays one - and a
    # stored Kickstart is used when there is one, because it is the real thing.
    if not looks_like_whdload(archive):
        warning = (
            "the only Kickstart available forces an AGA machine, which titles "
            "written for older hardware can crash on"
            if aga_only else None
        )
        # Three shapes reach here. An archive of disks lists them itself; a
        # loose disk that is one of a set names its siblings, which the image
        # endpoint then packs together; a single floppy is just itself.
        inside = disks_in(archive)
        if inside:
            return Plan("floppyset", True, (), kickstart,
                        dict(_AGA_MACHINE if aga_only else _ECS_MACHINE),
                        None, warning, inside)
        siblings = sibling_disks(archive)
        if siblings:
            return Plan("floppyset", True, (), kickstart,
                        dict(_AGA_MACHINE if aga_only else _ECS_MACHINE),
                        None, warning, tuple(p.name for p in siblings))
        return Plan("floppy", True, (), kickstart,
                    dict(_AGA_MACHINE if aga_only else _ECS_MACHINE),
                    None, warning, ())

    slave: str | None = None
    with tempfile.TemporaryDirectory(prefix="gd-whdload-") as tmp:
        dest = Path(tmp)
        try:
            files = _unpack(archive, dest)
        except Exception as exc:
            logger.warning("Could not read WHDLoad archive %s: %s", archive.name, exc)
            return Plan("harddrive", False, tuple(missing) or ("archive",),
                        kickstart, {}, None, warning=str(exc))
        found = _find_slave(files, dest)
        if found is None:
            return Plan("harddrive", False, ("slave",), kickstart, {}, None,
                        warning="no .slave in the archive - not a WHDLoad install")
        slave = str(found.relative_to(dest)).replace("\\", "/")

    warnings = []
    if aga_only:
        warnings.append(
            "the only Kickstart available forces an AGA machine, which titles "
            "written for older hardware can crash on"
        )
    if without_rtb:
        warnings.append(
            "no relocation table for " + ", ".join(without_rtb)
            + " - a game asking WHDLoad to emulate one of those will stop"
        )
    warning = "; ".join(warnings) or None
    return Plan(
        mode="harddrive",
        ok=not missing,
        missing=tuple(missing),
        kickstart=kickstart,
        machine=dict(_AGA_MACHINE if aga_only else _ECS_MACHINE),
        slave=slave,
        warning=warning,
    )


# Disk images the Amiga can have inserted. Not the same list the scanner uses:
# .lha is a hard drive, not a floppy, and never belongs in a drive.
_DISK_SUFFIXES = frozenset({".adf", ".adz", ".dms", ".ipf", ".exe", ".st"})

# The floppy the player's own saves live on. Named rather than numbered so it
# is obvious in the emulator's drive list which disk is theirs.
SAVE_DISK_NAME = "Saves.adf"


def disks_in(rom: Path) -> tuple[str, ...]:
    """Disk images inside a ZIP ROM, in insertion order.

    A multi-disk Amiga title is normally one .zip holding several .adf files.
    The emulator can auto-insert them and swap between them, but only if it is
    told their names inside the archive - handing it the name of the archive
    itself mounts nothing and leaves a file picker on screen.

    Empty for anything that is not a ZIP, including a bare .adf: that is one
    disk and needs no list.
    """
    if rom.suffix.lower() != ".zip":
        return ()
    try:
        with zipfile.ZipFile(rom) as z:
            names = [
                i.filename for i in z.infolist()
                if not i.is_dir()
                and Path(i.filename).suffix.lower() in _DISK_SUFFIXES
                and not i.filename.startswith("__MACOSX")
            ]
    except (OSError, zipfile.BadZipFile) as exc:
        logger.warning("Could not read disks from %s: %s", rom.name, exc)
        return ()
    return tuple(sorted(names, key=sort_key))


def sibling_disks(rom: Path) -> tuple[Path, ...]:
    """The other disks of a title split across separate files, in order.

    A multi-disk game often arrives as one file per disk, each its own library
    entry, so opening disk 1 would otherwise reach the point where the game asks
    for disk 2 with no way to supply it. Matching is on the disk marker in the
    name and the title around it, both of which the dump already carries.

    Empty when this is not one of a set, which is the answer for a single
    floppy and for anything whose name has no disk marker at all.
    """
    try:
        candidates = [
            p for p in rom.parent.iterdir()
            if p.is_file() and p.suffix.lower() in _DISK_SUFFIXES
        ]
    except OSError as exc:
        logger.warning("Could not look for sibling disks of %s: %s", rom.name, exc)
        return ()

    by_stem: dict[str, Path] = {}
    for p in candidates:
        by_stem.setdefault(p.stem, p)
    grouped = group_disks(by_stem)

    mine = grouped.get(rom.stem)
    if mine is None:
        return ()
    found = {
        number: by_stem[stem]
        for stem, (title, number) in grouped.items() if title == mine[0]
    }
    return tuple(found[n] for n in sorted(found))


def _startup_sequence(slave_rel: str) -> str:
    """The boot script. AROS-free: the Kickstart supplies the shell itself.

    NOWRITECACHE is what makes a savegame survive. WHDLoad caches writes in
    memory by default and, in its own words, defers them until the program
    exits - which is fine on a real Amiga, where quitting the game is how you
    stop playing. Here the tab is closed instead, and the machine goes with it.

    Measured rather than assumed: Cannon Fodder was saved from inside the game
    and showed the save on its own SELECT FILE screen, while the whole drive
    image hashed identically before and after. Not one block had moved.

    The cost is the reason WHDLoad caches at all - each write now goes through
    the operating system as the game makes it, rather than in one burst at the
    end. On an emulated machine with no physical heads to move, that is a
    better trade than losing the save.
    """
    p = Path(slave_rel)
    lines = []
    if str(p.parent) not in (".", ""):
        lines.append(f'cd "{p.parent.as_posix()}"')
    lines.append(f'C:WHDLoad "{p.name}" PRELOAD NOWRITECACHE')
    return "\n".join(lines) + "\n"


async def fetch_support(only: str | None = None) -> dict:
    """Download the freely-published pieces from where their authors put them.

    WHDLoad and the relocation tables are both distributed free of charge and
    unmodified, which is what makes fetching them reasonable at all. A Kickstart
    is not among them and never will be: that one is a file somebody owns, and
    it stays the administrator's to supply.

    Only what is missing is fetched, and the relocation-table archive is pulled
    once no matter how many ROMs need a table out of it.

    *only* narrows it to a single file, for the button beside that one row. It
    is a name from the status, not a path - anything else is nothing to fetch
    rather than an error, so a stale screen asking for a table whose Kickstart
    has since gone simply gets an empty answer.
    """
    fetched: list[str] = []
    skipped: list[str] = []
    failed: dict[str, str] = {}

    if only is not None and only != WHDLOAD_BINARY:
        pass
    elif (support_dir() / WHDLOAD_BINARY).is_file():
        skipped.append(WHDLOAD_BINARY)
    else:
        try:
            blob = await _download(( WHDLOAD_URL, ))
            data = await asyncio.to_thread(_member_of_lha, blob, "C/WHDLoad")
            if data is None:
                raise ValueError("WHDLoad is not in the published archive")
            store_support_file(WHDLOAD_BINARY, data)
            fetched.append(WHDLOAD_BINARY)
        except Exception as exc:
            # whdload.de and Aminet are unrelated hosts. One being unreachable
            # must not throw away what the other already gave us.
            logger.warning("WHDLoad fetch failed: %s", type(exc).__name__)
            failed[WHDLOAD_BINARY] = type(exc).__name__

    tables = [n for n in kickstarts_on_hand()
              if only is None or _rtb_name(n) == only]
    wanted = [n for n in tables if not (support_dir() / _rtb_name(n)).is_file()]
    skipped += [_rtb_name(n) for n in tables
                if (support_dir() / _rtb_name(n)).is_file()]
    if wanted:
        try:
            blob = await _download(SKICK_URLS)
            found = await asyncio.to_thread(
                _members_of_lha, blob,
                {f"Kickstarts/{_rtb_name(n)}": _rtb_name(n) for n in wanted},
            )
            for store_as, data in found.items():
                store_support_file(store_as, data)
                fetched.append(store_as)
            for n in wanted:
                if _rtb_name(n) not in found:
                    # Beta and developer ROMs have no published table. Saying so
                    # beats an admin wondering why one row stayed empty.
                    failed[_rtb_name(n)] = "not published"
        except Exception as exc:
            logger.warning("Relocation table fetch failed: %s", type(exc).__name__)
            for n in wanted:
                failed[_rtb_name(n)] = type(exc).__name__

    return {"fetched": fetched, "already_present": skipped, "failed": failed}


async def _download(urls: tuple[str, ...]) -> bytes:
    """Fetch the first of *urls* that answers, through the outbound guard."""
    import httpx

    from utils.net_guard import assert_fetch_allowed, make_request_guard

    last: Exception | None = None
    for url in urls:
        try:
            assert_fetch_allowed(url)
            async with httpx.AsyncClient(
                follow_redirects=True,
                timeout=90.0,
                # Aminet refuses a default client outright, and a library's
                # version string is not an identity anyone can act on.
                headers={"User-Agent": _USER_AGENT},
                event_hooks={"request": [make_request_guard()]},
            ) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                if len(resp.content) > MAX_UNPACKED_BYTES:
                    raise ValueError("download is implausibly large")
                return resp.content
        except Exception as exc:
            logger.warning("%s unreachable (%s)", url, type(exc).__name__)
            last = exc
    raise last if last else RuntimeError("no source configured")


def _member_of_lha(blob: bytes, member: str) -> bytes | None:
    """Pull one file out of an .lha held in memory, by path suffix."""
    found = _members_of_lha(blob, {member: member})
    return found.get(member)


def _members_of_lha(blob: bytes, wanted: dict[str, str]) -> dict[str, bytes]:
    """Pull several files out of one .lha, mapping archive path -> result key.

    Matching on a path suffix rather than the exact string: publishers wrap
    their archives in a top-level directory named after the version, and the
    version is not something to hard-code against.
    """
    out_by_key: dict[str, bytes] = {}
    with tempfile.TemporaryDirectory(prefix="gd-whdload-src-") as tmp:
        d = Path(tmp)
        archive = d / "src.lha"
        archive.write_bytes(blob)
        out = d / "out"
        out.mkdir()
        for p in _unpack(archive, out):
            rel = str(p.relative_to(out)).replace("\\", "/")
            for member, key in wanted.items():
                if rel == member or rel.endswith("/" + member):
                    out_by_key[key] = p.read_bytes()
    return out_by_key


def build_image(archive: Path, save_disk: bytes | None = None,
                saves: bytes | None = None) -> bytes:
    """The ZIP vAmigaWeb turns into a bootable hard drive.

    Deflated rather than stored: this one is read by JSZip inside the page, not
    by the offset reader the firmware bundle uses, and the archives compress to
    about half their size over what is usually a local network anyway.

    *save_disk*, when given, rides along as a floppy of its own. An Amiga game
    that saves writes to a disk, so that is what the player's saves live on;
    the emulator can only mount what is in this archive, which is why it has to
    be packed here rather than handed over separately. Floppy titles only.

    *saves* answers the same question for a WHDLoad title, and takes a different
    shape because there the drive itself is what gets written to: a small ZIP of
    the files this player's copy differs by, laid over the game before the drive
    is packed. Hard-drive titles only.
    """
    # A set of loose disks needs no hard drive - just the disks together in one
    # archive, so the emulator can fill every drive and swap the rest in.
    if not looks_like_whdload(archive):
        siblings = sibling_disks(archive)
        if not siblings and save_disk is None:
            raise ValueError("this ROM is a single disk - it needs no archive")
        buf = tempfile.SpooledTemporaryFile(max_size=64 * 1024 * 1024)
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=1) as z:
            for p in (siblings or (archive,)):
                z.write(p, p.name)
            if save_disk is not None:
                z.writestr(SAVE_DISK_NAME, save_disk)
        buf.seek(0)
        data = buf.read()
        buf.close()
        logger.info("Packed %d disks%s for %s: %d bytes",
                    len(siblings or (archive,)),
                    " plus a save disk" if save_disk is not None else "",
                    archive.name, len(data))
        return data

    the_plan = plan(archive)
    if not the_plan.ok:
        raise ValueError(f"cannot build a hard drive image: missing {', '.join(the_plan.missing)}")
    assert the_plan.kickstart and the_plan.slave

    whdload = support_dir() / WHDLOAD_BINARY

    buf = tempfile.SpooledTemporaryFile(max_size=64 * 1024 * 1024)
    restored = 0
    with tempfile.TemporaryDirectory(prefix="gd-whdload-") as tmp:
        dest = Path(tmp)
        files = _unpack(archive, dest)
        if saves:
            # Over the game, never under it: a save is by definition the newer
            # version of a file the install shipped. The listing is taken again
            # afterwards because a save usually ADDS files - a savegame that did
            # not exist when the archive was made - and the first listing would
            # not know about them.
            restored = _apply_saves(saves, dest)
            if restored:
                files = _scan(dest)
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            z.writestr("S/Startup-Sequence", _startup_sequence(the_plan.slave))
            z.write(whdload, f"C/{WHDLOAD_BINARY}")
            # Every ROM in the store, not just the one the machine boots. A
            # 1992 title runs on a 3.1 machine and asks WHDLoad to emulate 1.3
            # for it; shipping only the boot ROM leaves that request unanswered
            # while the file sits in the store.
            for name in kickstarts_on_hand():
                z.write(_kickstart_path(name), f"Devs/Kickstarts/{name}")
                rtb = support_dir() / _rtb_name(name)
                if rtb.is_file():
                    z.write(rtb, f"Devs/Kickstarts/{_rtb_name(name)}")
            for p in files:
                z.write(p, str(p.relative_to(dest)).replace("\\", "/"))
    buf.seek(0)
    data = buf.read()
    buf.close()
    logger.info(
        "Built WHDLoad hard drive for %s: %d bytes, slave %s, kickstart %s%s",
        archive.name, len(data), the_plan.slave, the_plan.kickstart,
        f", {restored} saved files restored" if restored else "",
    )
    return data
