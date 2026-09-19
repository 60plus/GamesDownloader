"""A ROM sent through the browser goes into its game's folder too.

The download already does, and the two roads have to agree: a file uploaded and
the same file downloaded landing in two different folders is the same game
twice on the shelf, and the second copy counts against somebody's quota.

An upload is the harder half of the pair. One request carries several files,
each with its own game and therefore its own folder, and among them can be a
subchannel file - a .sbi that is not a ROM, never gets a row of its own, and is
admitted only beside the disc it is named after. That disc now lives in a game
folder, so the question "is the disc here" has to be asked in the same folder
the .sbi is being written to. Both are named after the same game, so they agree
by construction: `Game (Disc 1).sbi` and `Game (Disc 1).chd` both answer
`Game`.

And the ownership stamp, which is the quiet one on this road as well: it only
claims a row whose folder is the folder this upload wrote to.
"""
from __future__ import annotations

import io
import pathlib

from utils.game_folders import game_dir

ROUTER = (pathlib.Path(__file__).resolve().parent.parent
          / "endpoints" / "roms" / "roms_router.py")


def _source() -> str:
    return io.open(ROUTER, encoding="utf-8").read()


def test_a_disc_and_its_subchannel_file_answer_the_same_folder():
    """Not an implementation detail: it is what lets the gate find the disc."""
    disc = game_dir("/roms", "psx", "Game (Disc 1).chd")
    sidecar = game_dir("/roms", "psx", "Game (Disc 1).sbi")
    assert disc == sidecar == pathlib.Path("/roms/psx/Game")


def test_two_games_in_one_request_go_to_two_folders():
    a = game_dir("/roms", "psx", "Crash Bandicoot (USA).chd")
    b = game_dir("/roms", "psx", "Silent Hill (Europe).chd")
    assert a != b
    assert a.parent == b.parent == pathlib.Path("/roms/psx")


def test_the_upload_route_asks_per_file_where_to_write():
    """One destination for the whole request was right while every ROM of a
    platform shared a directory. It is not: two files in one request are two
    games."""
    source = _source()
    at = source.index("dest_dir = _upload_dest_dir(")
    assert "safe_name" in source[at:at + 200], (
        "trasa wgrywania nadal liczy jeden katalog na cale zadanie"
    )
    rule = source.index("def _upload_dest_dir(")
    assert "game_dir(" in source[rule:rule + 1800], (
        "regula miejsca zapisu nie pyta o folder gry"
    )


def test_the_subchannel_gate_looks_in_the_folder_the_file_is_going_to():
    import re
    source = _source()
    at = re.search(r"_sidecar_disc\(\s*safe_name,\s*\(", source).start()
    window = source[at:at + 200]
    assert "game_dir(" in window and "fs_slug" in window, (
        "plik podkanalowy nie szuka swojej plyty w folderze gry"
    )
    # ...and in the platform folder as well, because a library is moved a game
    # at a time and the disc may not have been moved yet.
    assert "Path(roms_base) / fs_slug" in window, (
        "plik podkanalowy nie szuka plyty, ktora lezy jeszcze plasko na polce"
    )


def test_the_upload_owner_stamp_compares_against_the_game_folder():
    """The same silent failure the download had: a comparison against the
    platform folder is never true for a file a level below it, so the account
    that sent the ROM never becomes its owner."""
    source = _source()
    at = source.index("shelf_dir")
    assert "game_dir(" in source[at - 200:at + 600], (
        "stempel wlasciciela przy wgrywaniu porownuje sie z polka platformy"
    )
