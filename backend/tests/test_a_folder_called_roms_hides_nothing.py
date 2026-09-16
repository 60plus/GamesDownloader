"""A directory named `roms` inside a platform folder must not hide the platform.

GamesDownloader accepts two shapes on disk: ROM files sitting directly in
`{platform}/`, or one level deeper in `{platform}/roms/`. The scanner chose
between them with an either/or - if `roms/` existed it looked THERE AND NOWHERE
ELSE - which is fine while the choice is somebody's deliberate layout and
dangerous the moment that directory appears for any other reason.

And it can. A game whose title is "roms". An archive unpacked one level too
deep. Any tool that makes the directory. From that moment the scan reads an
empty platform, and because a scan opens by marking every row of the platform
missing and relies on the walk to un-mark what it finds, the entire platform
reads as missing. Nothing raises, nothing is logged, and the library simply
goes quiet.

Both directories are read now. The two shapes stop being mutually exclusive,
which also means a library that is half one shape and half the other - the state
somebody lands in mid-reorganisation - is no longer a way to lose sight of half
of it.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from handler.filesystem.rom_scanner import scan_candidates, scan_dirs_for


def _platform(*, nested: list[str] = (), flat: list[str] = ()) -> Path:
    root = Path(tempfile.mkdtemp()) / "amiga"
    root.mkdir(parents=True)
    for name in flat:
        (root / name).write_bytes(b"x")
    if nested:
        (root / "roms").mkdir()
        for name in nested:
            (root / "roms" / name).write_bytes(b"x")
    return root


def _found(platform: Path) -> set[str]:
    names: set[str] = set()
    for scan_dir in scan_dirs_for(platform):
        names.update(p.name for p in scan_candidates(scan_dir))
    return names


def test_files_directly_in_the_platform_folder_are_found():
    assert _found(_platform(flat=["Gra.lha"])) == {"Gra.lha"}


def test_files_one_level_down_in_roms_are_found():
    """Structure B, which is documented and which people use."""
    assert _found(_platform(nested=["Gra.lha"])) == {"Gra.lha"}


def test_a_roms_folder_does_not_hide_what_sits_beside_it():
    """The failure this exists for. Before, the whole platform read as missing
    the moment this directory appeared."""
    found = _found(_platform(flat=["Gra A.lha", "Gra B.lha"], nested=["Gra C.lha"]))
    assert found == {"Gra A.lha", "Gra B.lha", "Gra C.lha"}, (
        "folder o nazwie roms ukryl gry lezace obok niego"
    )


def test_a_platform_with_neither_is_simply_empty():
    assert _found(_platform()) == set()


def test_the_platform_folder_itself_is_always_read():
    """Stated on its own because it is the property that makes the trap
    impossible, not merely unlikely: whatever else is on the platform, the
    platform directory is read."""
    platform = _platform(flat=["Gra.lha"], nested=["Inna.lha"])
    assert platform in list(scan_dirs_for(platform))


def test_the_directories_are_not_read_twice():
    """A file counted twice is a file whose row is upserted twice in one pass,
    and on a platform with no `roms/` the naive union does exactly that."""
    platform = _platform(flat=["Gra.lha"])
    dirs = list(scan_dirs_for(platform))
    assert len(dirs) == len(set(dirs))


# ── The scan actually uses it ────────────────────────────────────────────────
#
# Everything above tests the helper. A helper that is correct and never called
# is the same library-wide blackout with better test coverage, so the wiring is
# asserted too.

import io as _io
import pathlib as _pathlib

_SCANNER = (_pathlib.Path(__file__).resolve().parent.parent
            / "handler" / "filesystem" / "rom_scanner.py")


def test_the_scan_asks_for_its_directories_rather_than_choosing_one():
    source = _io.open(_SCANNER, encoding="utf-8").read()
    walk = source.index("async def scan_roms_path")
    body = source[walk:]
    assert "scan_dirs_for(platform_dir)" in body, (
        "skan nadal sam wybiera katalog zamiast pytac scan_dirs_for"
    )
    assert "if roms_subdir.is_dir() else platform_dir" not in body, (
        "stary wybor albo-albo nadal tam jest"
    )


def test_disc_grouping_stays_inside_one_directory():
    """A .cue in the platform folder must not claim a track that lives in roms/
    beside it. The union is for finding files, not for deciding which of them
    are one disc set."""
    source = _io.open(_SCANNER, encoding="utf-8").read()
    at = source.index("assignments.update(plan_disk_assignments(")
    window = source[at - 400:at]
    assert "for here in files_by_dir" in window, (
        "grupowanie plyt liczone na polaczonej liscie z dwoch katalogow"
    )
