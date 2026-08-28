"""Running chdman, and knowing how far along it is.

CHD is what a disc library wants to be stored as. It is one file per disc
where a rip is a sheet and its tracks, it is about half the size, and the
emulator opens it without unpacking anything: a four disc PlayStation set is
1.6 GB in the browser instead of 2.7 GB, which is the difference between
comfortably inside a tab's memory and up against its ceiling.

chdman comes from the Debian package mame-tools and is run as a separate
program, the way ClamAV and Transmission already are here. NOTICE.md carries
the licence and the command that fetches its source.

No shell is involved anywhere below. The program and each argument are passed
separately, so a filename carrying a quote, a semicolon or a backtick is a
filename and never a command: these paths come from a library the operator
fills, and some of them are named by whoever packed an archive.

Two details in here were found by running it and would not have been guessed:

  * progress updates are separated by a carriage return, not a newline. Read
    a line at a time and nothing arrives until the job is over.
  * the progress line carries two percentages. The compression ratio is the
    second one and it wanders up and down, so matching the wrong one gives a
    bar that goes backwards and never arrives.
"""
from __future__ import annotations

import asyncio
import logging
import re
import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterator

from handler.filesystem.rom_scanner import tracks_referenced_by

logger = logging.getLogger(__name__)

# The disc images chdman can be handed. A sheet is here because chdman reads
# the sheet and finds the tracks itself; the tracks are not, because handed
# one directly it has no table of contents and refuses.
_CONVERTIBLE = {".cue", ".gdi", ".toc", ".iso", ".img"}

# Archives a disc may arrive in and that the conversion can open on the way
# past. The same one the player unpacks in the browser, for the same reason:
# deflate is what there is without shipping a decoder.
_UNPACKABLE = {".zip"}

# Given a whole hunk of a disc, chdman prints its progress as
#   Compressing, 29.1% complete... (ratio=42.1%)
# and the ratio is a percentage too. Anchoring on the word that precedes the
# one we want is what keeps them apart.
_PERCENT = re.compile(r"([0-9]+(?:\.[0-9]+)?)%\s+complete")

_KILL_GRACE_S = 5


class ChdError(RuntimeError):
    """chdman refused, or was stopped. Carries what it said."""


def can_convert(name: str) -> bool:
    """Whether this file is a disc image conversion can be offered for."""
    return Path(name or "").suffix.lower() in _CONVERTIBLE


# Files inside an archive that a core opens as a disc, best first. A sheet
# beats the track it names: handing a core the .bin gets a data file opened as
# a game. Everything after the sheets is a disc in one file, and .bin is last
# because a lone .bin with no sheet beside it is still a disc some cores read.
_DISC_INSIDE_ARCHIVE = (
    ".cue", ".gdi", ".ccd", ".toc",
    ".chd", ".iso", ".img", ".pbp", ".cso", ".exe",
    ".bin",
)


def disc_inside_archive(path) -> str | None:
    """The name of the disc image inside this archive, or None.

    Two callers want this and they want the same answer. The player unpacks an
    archived disc into the emulator's filesystem, so the playlist it is handed
    has to name the .cue and never the .zip the library row is called after;
    and the conversion needs to know whether there is a disc in there at all
    before the page offers a button that would fail on a zipped cartridge ROM.

    Only the central directory is read, which sits at the end of the file, so
    this costs one small seek however large the disc is.

    Blocking work, so a caller runs it off the event loop.
    """
    path = Path(path)
    if path.suffix.lower() not in _UNPACKABLE:
        return None
    try:
        with zipfile.ZipFile(path) as archive:
            names = [
                info.filename for info in archive.infolist()
                if not info.is_dir() and not info.filename.startswith("__MACOSX/")
            ]
    except (OSError, zipfile.BadZipFile):
        return None
    for suffix in _DISC_INSIDE_ARCHIVE:
        for name in names:
            if name.lower().endswith(suffix):
                return name
    return None


def convertible_disc(path) -> bool:
    """Whether this file really is something chdman can be handed.

    Asked of the file rather than of its name, because an archive is only
    convertible if there is a disc in it: a zipped cartridge ROM has exactly
    the same extension and would put a button on the page that fails a minute
    into the job. A disc already in CHD says no, having nothing to gain.

    Blocking work, so a caller runs it off the event loop.
    """
    path = Path(path)
    if can_convert(path.name):
        return True
    if path.suffix.lower() not in _UNPACKABLE:
        return False
    inside = disc_inside_archive(path)
    # Not every disc inside an archive is worth converting: one that is
    # already a CHD is the format this exists to produce.
    return bool(inside) and Path(inside).suffix.lower() != ".chd"


def parse_percent(line: str) -> float | None:
    """How far along, from one line of chdman's output, or None."""
    found = _PERCENT.search(line or "")
    if not found:
        return None
    try:
        return float(found.group(1))
    except ValueError:
        return None


def split_chunks(data: bytes) -> Iterator[str]:
    """The pieces of chdman's output, however it chose to end them.

    Carriage return counts as an ending here. It is how the tool overwrites
    its own progress line in a terminal, and splitting on newlines alone
    leaves the entire compression phase in a single unbroken piece.
    """
    for piece in re.split(rb"[\r\n]+", data):
        text = piece.decode("utf-8", "replace").strip()
        if text:
            yield text


async def _run(args: list[str], on_percent=None, should_stop=None) -> str:
    """Run chdman, following its output, and return everything it said.

    The argument list goes to the process directly, with no shell to
    reinterpret it. Raises ChdError when chdman fails or when *should_stop*
    asks it to end. The child is terminated rather than left running:
    cancelling the task that awaits a subprocess does not stop the
    subprocess, and this one holds a file open in somebody's library.
    """
    try:
        proc = await asyncio.create_subprocess_exec(
            "chdman", *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
    except (OSError, FileNotFoundError) as err:
        raise ChdError(f"chdman could not be started: {err}") from err

    said: list[str] = []
    stopped = False
    try:
        while True:
            data = await proc.stdout.read(4096)
            if not data:
                break
            for line in split_chunks(data):
                said.append(line)
                if on_percent is not None:
                    percent = parse_percent(line)
                    if percent is not None:
                        on_percent(percent)
            if should_stop is not None and should_stop():
                stopped = True
                break
    finally:
        if stopped:
            proc.terminate()
            try:
                await asyncio.wait_for(proc.wait(), timeout=_KILL_GRACE_S)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
        elif proc.returncode is None:
            await proc.wait()

    # Only the tail is worth carrying: chdman's progress is thousands of
    # pieces and the reason for a failure is always at the end.
    tail = " ".join(said[-6:])
    if stopped:
        raise ChdError("cancelled")
    if proc.returncode != 0:
        raise ChdError(tail or f"chdman exited {proc.returncode}")
    return tail


async def convert_to_chd(
    source: Path,
    out: Path,
    on_percent: Callable[[float], None] | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> Path:
    """Convert one disc image to CHD, at *out*.

    Nothing partial is left behind. chdman writes as it goes, so a run that
    fails or is stopped leaves a file that is the right shape and the wrong
    length, and the library is where this output ends up.
    """
    source, out = Path(source), Path(out)
    # createcd for all of them, including a bare .iso: it has no sheet and so
    # no tracks to lay out, and createdvd is for media that is not a CD.
    args = ["createcd", "-i", str(source), "-o", str(out)]
    try:
        await _run(args, on_percent=on_percent, should_stop=should_stop)
    except ChdError:
        _discard(out)
        raise
    if not out.is_file() or out.stat().st_size == 0:
        _discard(out)
        raise ChdError("chdman reported success but wrote nothing")
    return out


async def verify_chd(path: Path) -> bool:
    """Whether chdman is satisfied with this file.

    False rather than an exception for a file that is not a CHD, because the
    caller's next decision is whether to delete somebody's disc and it should
    read as a plain no.
    """
    try:
        said = await _run(["verify", "-i", str(Path(path))])
    except ChdError as err:
        logger.info("chdman could not verify %s: %s", Path(path).name, err)
        return False
    return "verification successful" in said.lower()


# Where a disc goes when the conversion succeeded and the person chose to keep
# it. Inside the platform directory, one level down, because the scan reads the
# files in that directory and does not descend: the disc stays exactly as easy
# to find by hand and stops being something the shelf will claim again.
ORIGINALS_DIR = "_originals"


def retire_sources(sources, directory) -> list[Path]:
    """Move the files a conversion replaced out of the scanned directory.

    The row now names the .chd, so anything left beside it is unclaimed and
    the next scan files it as a second copy of the same game: two identical
    entries, one of them the format the conversion existed to get away from.

    Returns what was actually moved. Anything outside *directory* is refused
    and left alone: fs_path is a stored string, a row can point elsewhere
    through a symlink or after the library path moved under it, and this
    function moves files.
    """
    directory = Path(directory).resolve()
    target = directory / ORIGINALS_DIR
    moved: list[Path] = []
    for source in sources:
        source = Path(source)
        try:
            here = source.resolve()
        except OSError:
            continue
        if here.parent != directory or not here.is_file():
            logger.warning("Refusing to move %s: it is not in %s", source, directory)
            continue
        try:
            target.mkdir(exist_ok=True)
            dest = target / here.name
            # Never write over something already retired under that name: the
            # older copy is somebody's disc too.
            n = 1
            while dest.exists():
                dest = target / f"{here.stem} ({n}){here.suffix}"
                n += 1
            here.replace(dest)
            moved.append(dest)
        except OSError as err:
            logger.warning("Could not move %s aside: %s", here.name, err)
    return moved


# A disc unpacks to a lot, and refusing a bomb has to happen before anything
# is written rather than after. Two discs' worth is room for a rip that puts
# every track in its own file without letting an archive fill the volume.
_MAX_UNPACKED_BYTES = 2 * 1024 * 1024 * 1024
_MAX_ENTRIES = 200


@dataclass(frozen=True)
class ConvertedDisc:
    """One disc, after conversion. Nothing has been deleted yet."""

    path: Path                 # the .chd, in the library beside the old files
    sha1: str                  # from its own header, which is how the scan reads it
    replaced: list[Path]       # what it stands in for, for the caller to dispose of
    was_bytes: int
    now_bytes: int


def _unpack_disc(archive: Path, dest: Path) -> Path:
    """Extract an archived disc and return the image inside it.

    The size is checked from the archive's own table before a byte is written,
    so an archive that claims to unpack to a volume's worth is refused rather
    than written out and then noticed. Entry names are resolved and refused if
    they point outside: this is a file somebody downloaded from a public
    collection, not something GD wrote.
    """
    root = dest.resolve()
    try:
        with zipfile.ZipFile(archive) as z:
            entries = [i for i in z.infolist()
                       if not i.is_dir() and not i.filename.startswith("__MACOSX/")]
            if not entries:
                raise ChdError(f"{archive.name} holds nothing")
            if len(entries) > _MAX_ENTRIES:
                raise ChdError(f"{archive.name} holds more files than a disc does")
            if sum(i.file_size for i in entries) > _MAX_UNPACKED_BYTES:
                raise ChdError(f"{archive.name} unpacks to more than a disc ever is")
            for info in entries:
                target = (dest / info.filename).resolve()
                if not target.is_relative_to(root):
                    raise ChdError(f"{info.filename} points outside the archive")
                target.parent.mkdir(parents=True, exist_ok=True)
                with z.open(info) as src, open(target, "wb") as out:
                    shutil.copyfileobj(src, out)
    except zipfile.BadZipFile as err:
        raise ChdError(f"{archive.name} is not readable: {err}") from err

    inside = sorted(p for p in dest.rglob("*") if p.is_file() and can_convert(p.name))
    if not inside:
        raise ChdError(f"there is no disc image inside {archive.name}")
    # A sheet beats a bare image: an archive holding both has the image as the
    # sheet's track, and handing chdman the track loses the table of contents.
    sheets = [p for p in inside if p.suffix.lower() in {".cue", ".gdi", ".toc"}]
    return (sheets or inside)[0]


async def convert_disc_files(
    source: Path,
    directory: Path,
    on_percent: Callable[[float], None] | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> ConvertedDisc:
    """Convert one disc in the library, and say what it stands in for.

    Nothing is deleted here. The caller decides what happens to the files this
    replaces, because that was the person's choice before the job started, and
    keeping the decision out of the step that writes means a conversion that
    goes wrong cannot take a disc with it.

    The output is built somewhere else and moved in at the end, so a failure
    or a cancellation leaves the directory exactly as it was.
    """
    source, directory = Path(source), Path(directory).resolve()
    try:
        here = source.resolve()
    except OSError as err:
        raise ChdError(f"{source} cannot be read: {err}") from err
    if here.parent != directory or not here.is_file():
        # fs_path is a stored string and a row can point elsewhere. This reads
        # a file and hands back a list of things next to it to be deleted.
        raise ChdError(f"{source.name} is not in {directory}")

    target = directory / f"{here.stem}.chd"
    if target.exists():
        raise ChdError(f"{target.name} is already there")

    archived = here.suffix.lower() in _UNPACKABLE
    if not archived and not can_convert(here.name):
        raise ChdError(f"{here.name} is not a disc image")

    with tempfile.TemporaryDirectory(prefix="gd-chd-") as work:
        work = Path(work)
        if archived:
            image = _unpack_disc(here, work / "in")
            replaced = [here]
        else:
            image = here
            # The sheet stands for its tracks, and after this they are one
            # file. Only what the sheet actually names: a subchannel file is
            # not named by it, is not part of the image, and the converted
            # disc still needs it beside them.
            #
            # tracks_referenced_by lowercases what it finds, because a sheet
            # and its tracks disagree about case more often than not. The
            # files on disk are matched the same way rather than by joining
            # the lowercased name to the path, which finds nothing at all on
            # a case sensitive filesystem and quietly leaves the track behind.
            wanted = tracks_referenced_by(here)
            replaced = [here] + sorted(
                entry for entry in directory.iterdir()
                if entry.is_file() and entry.name.lower() in wanted
                and entry != here
            )

        out = work / f"{here.stem}.chd"
        await convert_to_chd(image, out, on_percent=on_percent, should_stop=should_stop)
        if not await verify_chd(out):
            raise ChdError(f"chdman would not verify the {here.stem} it produced")

        was = sum(p.stat().st_size for p in replaced if p.is_file())
        now = out.stat().st_size
        sha1 = _header_sha1(out)
        if not sha1:
            raise ChdError("the converted disc carries no source hash")
        # Onto the library volume last, and only once it is whole and checked.
        # Across filesystems, so copy and rename rather than trusting a move.
        staged = directory / f".{here.stem}.chd.part"
        try:
            shutil.copyfile(out, staged)
            staged.replace(target)
        except OSError as err:
            _discard(staged)
            raise ChdError(f"could not put the converted disc in place: {err}") from err

    return ConvertedDisc(
        path=target, sha1=sha1, replaced=replaced, was_bytes=was, now_bytes=now,
    )


def rewrite_playlists(directory, renames: dict[str, str]) -> list[Path]:
    """Point the playlists in *directory* at the names the discs now have.

    A playlist is not a library row and no sheet names it, so nothing else
    here would touch it: after a conversion it would name four files that are
    gone, and be exactly as broken on a handheld as in the browser.

    Every line that is not one of the renamed discs is copied through
    untouched, comments and blanks included. Somebody's hand-written playlist
    is still theirs, and a line this conversion knows nothing about is not a
    line to drop.
    """
    lookup = {old.lower(): new for old, new in renames.items()}
    changed: list[Path] = []
    try:
        candidates = sorted(Path(directory).glob("*.m3u"))
    except OSError:
        return []
    for entry in candidates:
        try:
            lines = entry.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        out, touched = [], False
        for line in lines:
            # The same shape _playlists_naming reads: a line may carry a
            # `path|Label` suffix and either separator, and only the file name
            # is ours to change.
            name = line.split("|", 1)[0].strip().replace("\\", "/").rsplit("/", 1)[-1]
            replacement = lookup.get(name.lower())
            if replacement and not line.lstrip().startswith("#"):
                out.append(line.replace(name, replacement, 1))
                touched = True
            else:
                out.append(line)
        if not touched:
            continue
        try:
            entry.write_text("\n".join(out) + "\n", encoding="utf-8")
            changed.append(entry)
        except OSError as err:
            logger.warning("Could not update the playlist %s: %s", entry.name, err)
    return changed


def _header_sha1(path: Path) -> str:
    """The source SHA-1 a CHD v5 carries, which is how the scan identifies it.

    Read through the scanner's own function rather than a second copy of the
    offsets: a converted disc has to be identifiable by exactly the code that
    will look at it later.
    """
    from handler.filesystem.rom_scanner import _chd_header_sha1

    return _chd_header_sha1(path)


def _discard(out: Path) -> None:
    try:
        if out.exists():
            out.unlink()
    except OSError as err:
        logger.warning("Could not remove the unfinished %s: %s", out.name, err)
