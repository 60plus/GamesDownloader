"""How big a torrent is, read from the file, before anything is downloaded.

A torrent counts against the uploader quota now, but only once it has landed:
the bytes arrive first and the account is billed afterwards, so a 40 GB torrent
onto a 10 GB allowance succeeds and then sits there over the limit. Asked
whether the refusal should come first, the owner said yes.

It can be answered for a .torrent file and not for a magnet link. A .torrent
carries the metadata, so the total is a sum of lengths inside it and can be read
before Transmission is told anything. A magnet carries only a hash: the sizes
arrive from peers minutes later, so refusing one up front would mean refusing on
a guess. That half stays as it is - it lands, it counts, and the next upload is
what runs out of room.

The fixtures below are hand-written bencode, counted by eye, rather than bytes
produced by the reader being tested. A test that builds its input with the same
helper it is checking proves only that the helper agrees with itself, which is
how a floppy-image writer here once passed twenty-two tests and destroyed the
disk on first use.
"""
from __future__ import annotations

import pytest

from handler.torrent.torrent_size import total_bytes

# d 4:info d 6:length i1234e 4:name 8:game.bin e e
SINGLE_FILE = b"d4:infod6:lengthi1234e4:name8:game.binee"

# d 4:info d 5:files l d 6:length i100e 4:path l 5:a.bin e e
#                      d 6:length i250e 4:path l 5:b.bin e e e 4:name 3:dir e e
MULTI_FILE = (
    b"d4:infod5:filesl"
    b"d6:lengthi100e4:pathl5:a.binee"
    b"d6:lengthi250e4:pathl5:b.binee"
    b"e4:name3:diree"
)


def test_a_single_file_torrent_reports_its_length():
    assert total_bytes(SINGLE_FILE) == 1234


def test_a_multi_file_torrent_reports_the_sum():
    """The whole torrent is what lands on the disk, not its largest file."""
    assert total_bytes(MULTI_FILE) == 350


def test_a_real_announce_and_pieces_block_does_not_confuse_it():
    """A real file carries a tracker URL and a pieces blob full of arbitrary
    bytes, including the characters bencode uses for structure."""
    payload = (
        b"d8:announce18:http://tr.example/"
        b"4:infod6:lengthi4096e4:name5:a.bin"
        # A pieces blob of exactly the bytes bencode uses for structure, so a
        # reader that scanned for them instead of taking the declared length
        # would lose its place right here.
        b"12:piece lengthi16384e6:pieces6:eeddll"
        b"ee"
    )
    assert total_bytes(payload) == 4096


@pytest.mark.parametrize("junk", [
    b"", b"not a torrent", b"d", b"de", b"d4:infoe", b"d4:infod4:name3:abcee",
])
def test_anything_it_cannot_read_is_unknown_rather_than_zero(junk):
    """Zero would read as "an empty torrent, let it through" to a caller doing
    arithmetic against a limit. Unknown has to be a different answer from small,
    or a malformed file becomes the way past the check."""
    assert total_bytes(junk) is None


def test_a_negative_or_absurd_length_is_unknown():
    """A length is a claim made by the file. One that cannot be true is not a
    small torrent, it is a broken one."""
    assert total_bytes(b"d4:infod6:lengthi-5e4:name1:aee") is None


def test_it_does_not_recurse_without_end_on_a_hostile_file():
    """Nesting is the cheap way to turn a parser into a crash. A deep file is
    refused as unreadable rather than taking the process with it."""
    payload = b"d4:info" + b"l" * 5000 + b"e" * 5000 + b"e"
    assert total_bytes(payload) is None
