"""Refusals quoted raw byte counts.

    This torrent is 22914307626 bytes and only 0 are left of this account's
    upload quota.

Reported by the owner, watching it work: "przydalo by sie jakos bardziej
czytelne GB MB ale dziala". Twenty-two billion is a number nobody converts in
their head, and the point of the sentence is to let somebody judge how much room
they need to free.

The interface has said this properly all along - `formatBytes` in
frontend/src/utils/format.ts, 1024-based, one decimal below a gigabyte and two
above. These messages are composed on the SERVER, which had no such helper at
all, so every message that wanted a size wrote the integer.

The unit names and the rounding here match that function deliberately. A refusal
that says 21.3 GB while the tray beside it says 21.34 GB for the same file reads
as two different numbers.
"""

from __future__ import annotations

import io
import pathlib

import pytest

from utils.sizes import human_bytes

BACKEND = pathlib.Path(__file__).resolve().parent.parent


@pytest.mark.parametrize("size,expected", [
    (0, "0 B"),
    (512, "512 B"),
    (1024, "1.0 KB"),
    (1536, "1.5 KB"),
    (1024 ** 2, "1.0 MB"),
    (22_914_307_626, "21.34 GB"),      # the one from the owner's screen
    (56_373_525_225, "52.50 GB"),      # and the magnet before it
    (1024 ** 4, "1.00 TB"),
])
def test_a_size_is_written_the_way_the_interface_writes_it(size, expected):
    assert human_bytes(size) == expected


@pytest.mark.parametrize("odd", [None, -1, "nonsense"])
def test_something_that_is_not_a_size_does_not_break_the_message(odd):
    """These land in refusals, and a refusal that raises on its own wording
    turns a clear "no" into a 500."""
    assert human_bytes(odd) == "0 B"


def test_the_rounding_matches_the_interface_exactly():
    """Below a kilobyte no decimals, below a gigabyte one, above it two - the
    same three rules `formatBytes` applies, read off that file rather than
    remembered."""
    source = io.open(BACKEND.parent / "frontend" / "src" / "utils" / "format.ts",
                     encoding="utf-8").read() if (
        BACKEND.parent / "frontend" / "src" / "utils" / "format.ts").is_file() else ""
    if not source:
        pytest.skip("frontend tree not present")
    assert "const UNITS = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']" in source, (
        "nazwy jednostek w interfejsie sie zmienily, a serwer nadal pisze stare"
    )


# ── The messages that were quoting integers ──────────────────────────────────

def _body(path: pathlib.Path, marker: str, span: int | None = None) -> str:
    """The function that starts at `marker`, to the next one.

    A fixed slice was the first version and it stopped short of the code it
    was about, so the assertion failed on a function that was already right.
    """
    import re as _re

    source = io.open(path, encoding="utf-8").read()
    at = source.index(marker)
    if span is not None:
        return source[at:at + span]
    nxt = _re.search(r"\n(async )?def ", source[at + len(marker):])
    return source[at:at + len(marker) + nxt.start()] if nxt else source[at:]


def test_the_torrent_file_refusal_says_gigabytes():
    """The message the owner quoted. Its numbers came straight from the
    quota arithmetic. The refusal moved into a helper when the address route
    began weighing the .torrent it fetches (1.0.34 audit, finding #18)."""
    router = BACKEND / "endpoints" / "torrent" / "torrent_router.py"
    assert "_refuse_if_it_does_not_fit(" in _body(router, "async def add_torrent_file("), (
        "trasa wgrania .torrenta juz nie wazy pliku"
    )
    body = _body(router, "async def _refuse_if_it_does_not_fit(")
    assert "human_bytes(" in body, (
        "odmowa wgrania .torrenta nadal podaje surowa liczbe bajtow"
    )
    assert "{size} bytes" not in body


def test_the_resume_refusal_says_gigabytes_too():
    body = _body(BACKEND / "endpoints" / "torrent" / "torrent_router.py",
                 "async def resume_download(")
    assert "human_bytes(" in body


def test_the_monitor_says_how_much_the_transfer_wanted():
    """"larger than what is left" was true and useless: it never said larger by
    how much, so the account could not tell whether to delete one game or
    twenty."""
    from handler.torrent import seed_monitor as M

    message = M._refusal_message(56_373_525_225, 4 * 1024 ** 3)
    assert "52.50 GB" in message, f"komunikat nie podaje rozmiaru: {message}"
    assert "4.00 GB" in message, f"komunikat nie podaje, ile zostalo: {message}"


def test_the_catalogue_refusal_was_doing_the_same_thing():
    """Found while writing this one: the same sentence, the same integers, on a
    different way in. Left as it was, the two paths would disagree about how a
    size is written the moment either changed."""
    body = _body(BACKEND / "handler" / "library" / "catalog_sync_handler.py",
                 "these builds come to", span=300)
    assert "bytes and only" not in body, (
        "odmowa przy synchronizacji katalogu nadal podaje surowe bajty"
    )
