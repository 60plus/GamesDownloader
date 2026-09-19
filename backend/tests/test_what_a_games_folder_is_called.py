"""The name a game's folder gets, decided from the title and the file name.

The title a scrape found is the name a person recognises, so it goes first.
Without one - a ROM nobody has scraped, a disc whose row carries no name - the
file name answers instead, which is what the shelf already shows for those.

Whatever the source, the disc marker comes off. `Final Fantasy IX (Europe)
(Disc 1)` and `(Disc 2)` have to land in ONE folder: what makes four files one
game is the grouping worked out from the names of the files sitting in a single
directory, so discs split across four folders are four games on the shelf, each
with a disc the player cannot switch away from. The marker is recognised by the
same expressions the grouping uses, because two spellings of that rule would be
one too many.

A trailing letter is deliberately not stripped. `Ishar 2 (Silmarils) A` is disk
A of a set only when B and C are there beside it, and that is a question about
a directory, not about a name - so the folder for one file never guesses it.

Then the filesystem has its say. Titles carry characters a path cannot: a colon
in `Ratchet & Clank: Up Your Arsenal`, a slash in `Marvel vs. Capcom 2 / X-Men`.
A name ending in a space or a dot is legal here and refused by Windows, which
matters for a library reached over SMB, and so are the device names DOS reserved
and Windows still honours.
"""
from __future__ import annotations

import pytest

from utils.game_folders import game_folder_name


def _folder(fs_name: str, title: str | None = None) -> str:
    return game_folder_name(title=title, fs_name=fs_name)


# ── Where the name comes from ───────────────────────────────────────────────


def test_the_title_is_used_when_there_is_one():
    assert _folder("ff9-eu-d1.chd", "Final Fantasy 9") == "Final Fantasy 9"


def test_the_file_name_answers_when_there_is_no_title():
    assert _folder("Crash Bandicoot (USA).chd") == "Crash Bandicoot (USA)"


def test_a_blank_title_is_no_title():
    assert _folder("Crash Bandicoot (USA).chd", "   ") == "Crash Bandicoot (USA)"


# ── The discs of one title share one folder ─────────────────────────────────


@pytest.mark.parametrize("fs_name", [
    "Final Fantasy IX (Europe) (Disc 1).chd",
    "Final Fantasy IX (Europe) (Disc 2).chd",
    "Final Fantasy IX (Europe) (Disc 3).chd",
    "Final Fantasy IX (Europe) (Disc 4).chd",
])
def test_every_disc_of_a_title_answers_the_same(fs_name):
    """Straight off the owner's shelf. Four files, one folder, or the title
    stops being one game."""
    assert _folder(fs_name) == "Final Fantasy IX (Europe)"


def test_the_amiga_spelling_of_the_marker_too():
    """Also from the shelf: `(Disk 1 of 2)`, with the tags that follow it kept."""
    assert _folder("Legion (1996)(Gobi)(PL)(Disk 1 of 2)[cr WT].adf") == (
        "Legion (1996)(Gobi)(PL)[cr WT]"
    )


def test_a_marker_in_the_title_comes_off_as_well():
    """A scrape can put the disc into the title, and a title is not checked by
    anybody before it becomes a folder."""
    assert _folder("d2.chd", "Parasite Eve II (Disc 2)") == "Parasite Eve II"


def test_a_trailing_letter_is_left_alone():
    """Disk A of a lettered set is a guess that only a full A-B-C run
    corroborates, and one file cannot see the run."""
    assert _folder("Ishar 2 (Silmarils) A.adf") == "Ishar 2 (Silmarils) A"


# ── What a path cannot hold ─────────────────────────────────────────────────


def test_a_colon_and_a_slash_do_not_reach_the_path():
    assert _folder("rc3.iso", "Ratchet & Clank: Up Your Arsenal") == (
        "Ratchet & Clank - Up Your Arsenal"
    )
    assert "/" not in _folder("mvc2.chd", "Marvel vs. Capcom 2 / X-Men")
    assert "\\" not in _folder("x.chd", "AC\\DC Live")


def test_a_name_never_ends_in_a_dot_or_a_space():
    """Legal on ext4, refused by Windows, and the library is reached over SMB."""
    assert _folder("x.chd", "Mr. Do!. ") == "Mr. Do!"
    assert not _folder("x.chd", "Sonic 3 ").endswith(" ")


def test_a_reserved_device_name_is_not_used_bare():
    """CON, PRN, AUX, NUL, COM1..9 and LPT1..9 cannot be directory names on
    Windows, whatever the extension."""
    for reserved in ("CON", "con", "NUL", "COM1", "lpt9"):
        assert _folder("x.chd", reserved).lower() != reserved.lower()


def test_a_very_long_title_is_cut_to_something_a_filesystem_accepts():
    folder = _folder("x.chd", "A" * 400)
    assert 0 < len(folder) <= 120


@pytest.mark.parametrize("title", [
    ".hack//Infection", "Extras", "MODS", "roms", "_originals", ".Trash-1000",
])
def test_the_scan_can_see_every_folder_this_names(tmp_path, title):
    """The scan walks past a directory whose name starts with a dot - a tool's,
    like .git - and past roms/, mods/, extras/ and _originals/, which hold
    something other than a game. A game whose folder got one of those names
    would drop off the shelf at the next scan, marked missing with its files
    still on the disk. `.hack//Infection` is a real title."""
    from handler.filesystem.rom_scanner import _game_folders_in

    folder = tmp_path / _folder("x.chd", title)
    folder.mkdir()

    assert _game_folders_in(tmp_path) == [folder], (
        f"skan nie zobaczy folderu {folder.name!r}, gra zniknie z polki"
    )


def test_there_is_always_a_name():
    """A title of nothing but punctuation, and a file name that is all
    extension, still have to produce a folder."""
    assert _folder(".chd", "///").strip()
    assert _folder("").strip()
