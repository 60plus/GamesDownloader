"""How many bytes a .torrent will bring, read from the file itself.

A torrent counts against the uploader quota, but only once it has landed: the
transfer runs first and the account is billed afterwards, so a 40 GB torrent
onto a 10 GB allowance succeeds and then sits over the limit. Reading the size
out of the file lets the refusal come first.

Only for a .torrent. A magnet link carries a hash and nothing else - the sizes
arrive from peers minutes later - so there is nothing here to answer with, and
refusing one up front would be refusing on a guess.

Bencode is four shapes and about forty lines, so it is decoded here rather than
by adding a dependency for one number. The decoder is deliberately unforgiving:
anything it cannot read with certainty comes back as None, never as zero. Zero
would read as "an empty torrent, let it through" to the caller doing arithmetic
against a limit, which would make a malformed file the way past the check.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Deep enough for any real torrent - the deepest nesting in one is
# info > files > path > string, four levels - and shallow enough that a file
# built to nest forever is refused instead of exhausting the stack.
_MAX_DEPTH = 32


class _Malformed(Exception):
    """Raised anywhere the bytes stop making sense. Caught once, at the top."""


def _decode(data: bytes, at: int, depth: int) -> tuple[object, int]:
    """One value starting at `at`, and the index just past it."""
    if depth > _MAX_DEPTH:
        raise _Malformed("nested too deeply")
    if at >= len(data):
        raise _Malformed("ran off the end")

    lead = data[at:at + 1]

    if lead == b"i":
        end = data.find(b"e", at)
        if end < 0:
            raise _Malformed("unterminated integer")
        try:
            return int(data[at + 1:end]), end + 1
        except ValueError:
            raise _Malformed("integer is not a number")

    if lead == b"l":
        items: list[object] = []
        at += 1
        while at < len(data) and data[at:at + 1] != b"e":
            item, at = _decode(data, at, depth + 1)
            items.append(item)
        if at >= len(data):
            raise _Malformed("unterminated list")
        return items, at + 1

    if lead == b"d":
        out: dict[bytes, object] = {}
        at += 1
        while at < len(data) and data[at:at + 1] != b"e":
            key, at = _decode(data, at, depth + 1)
            if not isinstance(key, bytes):
                raise _Malformed("dictionary key is not a string")
            value, at = _decode(data, at, depth + 1)
            out[key] = value
        if at >= len(data):
            raise _Malformed("unterminated dictionary")
        return out, at + 1

    # A byte string: "<length>:<bytes>". This is also the case that reads the
    # pieces blob, which is arbitrary binary and will contain the characters
    # above; taking it by length rather than by scanning is what stops it being
    # mistaken for structure.
    colon = data.find(b":", at)
    if colon < 0:
        raise _Malformed("string has no length")
    try:
        length = int(data[at:colon])
    except ValueError:
        raise _Malformed("string length is not a number")
    if length < 0 or colon + 1 + length > len(data):
        raise _Malformed("string runs past the end")
    return data[colon + 1:colon + 1 + length], colon + 1 + length


def total_bytes(data: bytes) -> int | None:
    """Total size of everything in this .torrent, or None if it cannot be read.

    None is the answer for a file that is truncated, hostile, or simply not a
    torrent. The caller must treat it as "no idea", which is not the same as
    "nothing", and let the transfer through rather than refuse on a failure to
    parse: a limit that fires on unreadable input would reject valid torrents
    the day some client starts writing a field this decoder does not expect.
    """
    try:
        value, _ = _decode(data, 0, 0)
        if not isinstance(value, dict):
            raise _Malformed("top level is not a dictionary")
        info = value.get(b"info")
        if not isinstance(info, dict):
            raise _Malformed("no info dictionary")

        # Single file: one length. Multi file: a list of them, and the whole
        # set is what lands on the disk.
        if isinstance(info.get(b"length"), int):
            total = info[b"length"]
        elif isinstance(info.get(b"files"), list):
            total = 0
            for entry in info[b"files"]:
                if not isinstance(entry, dict) or not isinstance(entry.get(b"length"), int):
                    raise _Malformed("file entry has no length")
                total += entry[b"length"]
        else:
            raise _Malformed("info has neither a length nor a file list")

        if total < 0:
            raise _Malformed("negative total")
        return total
    except _Malformed as exc:
        logger.debug("Could not read a size from a .torrent: %s", exc)
        return None
    except Exception:
        logger.warning("Unexpected failure reading a .torrent size", exc_info=True)
        return None
