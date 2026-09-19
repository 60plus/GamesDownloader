"""A downloaded ROM is written into its game's folder, not onto the shelf.

Every disc of a title has to land in ONE folder or the title stops being one
game. For a game the library does not have yet, the name of that folder is
worked out from the file name, because at that moment there is nothing else: a
download job carries a URL, a file name and a platform, and the title only
exists after the scrape that follows it. A game the library already has is
written where it is (test_a_file_goes_where_its_game_already_is.py).

The destination is one decision used four times over, and that is the point of
having it in one place. The .part file is written beside the finished one, or a
resumed download looks for a fragment that is not there; the free-space check
asks about the disk the file is going to; the "already have this" check has to
look where the file would be; and the stamp that makes the downloader the owner
compares the row's folder against the folder this download wrote to. That last
one fails quietly: no error, no owner, and the ROM counts against nobody's
quota.
"""
from __future__ import annotations

import io
import pathlib

import pytest

from handler.roms import rom_source_handler as rsh

SOURCE = pathlib.Path(rsh.__file__)


@pytest.fixture
def shelf(tmp_path, monkeypatch):
    monkeypatch.setattr(rsh, "_roms_base", lambda: str(tmp_path))
    return tmp_path


def test_a_plain_game_gets_a_folder_of_its_own(shelf):
    assert rsh.rom_dest_dir("psx", "Crash Bandicoot (USA).chd") == (
        shelf / "psx" / "Crash Bandicoot (USA)"
    )


@pytest.mark.parametrize("disc", [1, 2, 3, 4])
def test_every_disc_of_a_title_goes_to_the_same_folder(shelf, disc):
    assert rsh.rom_dest_dir("psx", f"Final Fantasy IX (Europe) (Disc {disc}).chd") == (
        shelf / "psx" / "Final Fantasy IX (Europe)"
    )


def test_the_platform_folder_is_still_the_root_of_it(shelf):
    """One level down and no further: the scan reads a game folder, and would
    read nothing below it."""
    directory = rsh.rom_dest_dir("psx", "Game.chd")
    assert directory.parent == shelf / "psx"


# ── The four places that have to agree ──────────────────────────────────────


def _source() -> str:
    return io.open(SOURCE, encoding="utf-8").read()


def test_the_part_file_is_written_beside_the_finished_one():
    """A resumed download looks for the fragment where it left it."""
    source = _source()
    at = source.index("def part_path")
    assert "rom_dest_dir(" in source[at:at + 260], (
        "plik czesciowy ladem gdzie indziej niz gotowy"
    )


def test_the_transfer_writes_into_the_folder_it_chose():
    """Chosen when the transfer starts, where the game already is or else the
    folder above (test_a_file_goes_where_its_game_already_is.py), and kept on
    the job, which is what the part file and the owner stamp both read."""
    source = _source()
    at = source.index("async def _run_rom_download")
    body = source[at:source.index("\nasync def ", at + 1)]
    assert "job.dest_dir = await _home_for(" in body, (
        "pobieranie nie pyta, gdzie jest jego gra"
    )


def test_the_already_have_it_check_looks_where_the_file_would_go():
    """Asked before a download starts. Looking anywhere but where the game is
    means every ROM downloads a second time."""
    source = _source()
    for at in _each(source, "if not force and"):
        assert "_already_here(" in source[at:at + 200], (
            "sprawdzenie 'juz jest' patrzy w zly katalog"
        )
    # Which asks where the game is, and the shelves as well (1.0.36 audit).
    helper = source[source.index("async def _already_here("):]
    helper = helper[:helper.index("\n\n\n")]
    assert "_home_for(" in helper and "shelves_of(" in helper


def test_the_owner_stamp_compares_against_the_folder_it_wrote_to():
    """The quiet one. A comparison against the platform folder is simply never
    true once the file is a level down, so the account that fetched the ROM is
    not its owner and it counts against nobody."""
    source = _source()
    at = source.index("this_file = (")
    assert "rom_dest_dir(" in source[at:at + 320], (
        "stempel wlasciciela porownuje sie z polka, nie z folderem gry"
    )


def _each(source: str, needle: str):
    at = source.find(needle)
    while at != -1:
        yield at
        at = source.find(needle, at + 1)
