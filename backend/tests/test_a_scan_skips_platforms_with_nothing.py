"""A scan should not do work for a platform that has nothing and never had.

GamesDownloader creates a folder for every platform it knows on first boot, so a
typical install has around a hundred of them and games in a handful. The scan
walked all of them the same way: upsert the platform row, mark every ROM of that
platform missing, then find no files and move on.

Measured on a real install before this changed: 48 ROM files across 11 platforms
produced 515 database statements, and roughly four fifths of them were for the
96 platform folders that hold nothing at all.

The saving is not the point on its own - that scan took a second. The point is
that the work is unconditional, so it grows with the number of platforms GD
knows about rather than with the size of anybody's library, and it is the same
per-platform write on every scheduled scan forever.

WHAT MUST NOT HAPPEN: a platform whose files have been deleted still has rows,
and those rows still have to be marked missing. "No files on disk" is not the
condition. "No files on disk AND no rows in the database" is.
"""
from __future__ import annotations

import pytest

from handler.filesystem.rom_scanner import platform_has_nothing


def test_a_folder_with_no_files_and_no_rows_is_skipped():
    assert platform_has_nothing(files=[], rows=0)


def test_a_folder_with_files_is_scanned():
    assert not platform_has_nothing(files=["Gra.lha"], rows=0)


def test_a_folder_emptied_of_its_files_is_still_scanned():
    """The one that matters. Somebody deleted the files; the rows are still
    there and the scan is what marks them missing. Skipping this platform would
    leave the library claiming games that are gone."""
    assert not platform_has_nothing(files=[], rows=7), (
        "platforma bez plikow, ale z wierszami, zostalaby pominieta i jej gry "
        "nigdy nie zostalyby oznaczone jako zaginione"
    )


def test_both_present_is_obviously_scanned():
    assert not platform_has_nothing(files=["Gra.lha"], rows=7)


@pytest.mark.parametrize("rows", [None, 0])
def test_an_unknown_row_count_is_treated_as_none(rows):
    """A platform that has no row in the counts map has no ROMs."""
    assert platform_has_nothing(files=[], rows=rows)


def test_the_scan_asks_before_touching_a_platform():
    """The helper existing is not the same as the scan using it."""
    import io
    import pathlib

    scanner = (pathlib.Path(__file__).resolve().parent.parent
               / "handler" / "filesystem" / "rom_scanner.py")
    source = io.open(scanner, encoding="utf-8").read()
    walk = source.index("async def scan_roms_path")
    body = source[walk:]
    assert "platform_has_nothing(" in body, "skan nie pyta, czy jest co robic"
    # And it asks BEFORE the platform upsert, or the saving is imaginary.
    assert body.index("platform_has_nothing(") < body.index("rom_platform_handler.upsert("), (
        "pytanie pada po zapisaniu platformy, wiec nie oszczedza niczego"
    )
