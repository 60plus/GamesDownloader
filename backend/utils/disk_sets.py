"""Recognising a title that arrived as several disks.

Games too big for one floppy shipped on several, and dumps keep that: one file
per disk, each with its number written into the name. The library scans them as
separate entries, which is honest about the files but wrong about the game -
somebody browsing sees "Legion" twice and starting either one reaches the point
where it asks for the disk they did not pick.

Grouping them needs only what the name already carries, and the rules below all
come from getting it wrong first:

  * a bare number is never a disk number, or "1943 - The Battle of Midway"
    becomes disk 1943 of something. The word "disk" has to be there.
  * a bare trailing letter usually is one: dumps of the era name their disks
    "Ishar 2 (Silmarils) A", "... B", "... C" with no marker at all. But a
    single letter is also how roman numerals look, so a lettered set is only
    believed when the letters run A, B, C with none missing - which "Ultima I"
    beside "Ultima V" does not.
  * ordering is numeric. Alphabetically disk 10 sits between 1 and 2, and a
    game handed its disks in that order asks for one already in a drive.

This lives outside any one platform's handler because multi-disk sets are not
an Amiga peculiarity - the Atari ST, the C64 and DOS all did the same thing.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import NamedTuple

# "(Disk 1 of 2)", "[Disk 2]", "Disk 3", "Disc 1". The separators around it are
# swallowed too, so removing the marker does not leave "Game  ()" behind.
_MARKER = re.compile(
    r"[\s._-]*[\(\[]?\s*dis[kc]\s*(\d+)(?:\s*(?:of|z|/)\s*\d+)?\s*[\)\]]?",
    re.IGNORECASE,
)

# The same thing lettered: "(Disk A)", "Disk B of C". The letter has to stand
# apart as its own word, or "Diskette" reads as disk E and "Disco Fever" as
# disk O.
_LETTER_MARKER = re.compile(
    r"[\s._-]*[\(\[]?\s*dis[kc]\s+([A-Za-z])(?![A-Za-z])(?:\s*(?:of|z|/)\s*[A-Za-z])?\s*[\)\]]?",
    re.IGNORECASE,
)

# "Ishar 2 (Silmarils) A" - no marker, just a letter hanging off the end.
_TRAILING_LETTER = re.compile(r"[\s._-]([A-Za-z])$")


def _norm(title: str) -> str:
    return " ".join(title.lower().split())


def _identify(stem: str) -> tuple[str, int, bool] | None:
    """(title, disk number, said-the-word-disk), or None for a lone game.

    The last element is what decides how much the answer is trusted: a name
    carrying the word "disk" means what it says, a bare trailing letter is a
    guess that has to be corroborated by the rest of the set.
    """
    # A file called just "Disk 1" says nothing about what it is, so it is not one.
    disk = marked_disk(stem)
    if disk is not None:
        return disk.title, disk.number, True
    m = _TRAILING_LETTER.search(stem)
    if m:
        title = stem[: m.start()].strip()
        if title:
            return _norm(title), _letter_number(m.group(1)), False
    return None


def _letter_number(letter: str) -> int:
    return ord(letter.lower()) - ord("a") + 1


def group_disks(stems: Iterable[str]) -> dict[str, tuple[str, int]]:
    """Which of these names are disks of a shared title, and in what order.

    Names that are nothing to do with a set are simply absent from the result,
    as is a title with only one disk present: one disk of a set is just a game.
    """
    groups: dict[tuple[str, bool], dict[int, str]] = {}
    for stem in stems:
        ident = _identify(stem)
        if ident is None:
            continue
        title, number, marked = ident
        # First file to claim a number keeps it. A set with two disk 2s is a
        # naming accident, not two disks.
        groups.setdefault((title, marked), {}).setdefault(number, stem)

    out: dict[str, tuple[str, int]] = {}
    for (title, marked), members in groups.items():
        if len(members) < 2:
            continue
        if not marked:
            if (title, True) in groups:
                # The same title also has disks that say so. Those are the set;
                # a bare letter beside them is something else entirely.
                continue
            if set(members) != set(range(1, len(members) + 1)):
                # Letters with a gap in them are not disks A..C of anything;
                # far more likely two titles ending in roman numerals.
                continue
        for number, stem in members.items():
            out[stem] = (title, number)
    return out


class MarkedDisk(NamedTuple):
    title: str    # normalised, what disks of one set share
    number: int
    prefix: str   # the name as written up to the marker, for finding the rest


def marked_disk(stem: str) -> MarkedDisk | None:
    """What a name that SAYS it is a disk is a disk of, or None.

    Only a name carrying the word. A bare trailing letter is a guess that needs
    the rest of its set in view to be believed, and a file arriving on its own
    has nothing in view.
    """
    for pattern, to_number in ((_MARKER, int), (_LETTER_MARKER, _letter_number)):
        m = pattern.search(stem)
        if m:
            title = (stem[: m.start()] + stem[m.end():]).strip()
            if title:
                return MarkedDisk(_norm(title), to_number(m.group(1)), stem[: m.start()])
    return None


def without_disk_marker(name: str) -> str:
    """*name* with `(Disc 2)`, `Disk 1 of 2` and the like taken out of it.

    The same two expressions the grouping identifies a disk with, so the folder
    a disc goes in and the set it belongs to cannot drift apart. Case and the
    rest of the name are left exactly as they were: this answers what a folder
    is called, not what sorts with what.

    A bare trailing letter is left alone on purpose. `Ishar 2 (Silmarils) A` is
    disk A only when B and C are beside it, which is a question about a
    directory - a name on its own has no way to tell that from a title ending
    in a roman numeral.
    """
    for pattern in (_MARKER, _LETTER_MARKER):
        m = pattern.search(name)
        if m:
            without = (name[: m.start()] + name[m.end():]).strip()
            # A file called nothing but "Disk 1" keeps its name: there is no
            # title in there to fall back to.
            if without:
                return without
    return name.strip()


def sort_key(name: str) -> tuple:
    """Sort key that puts Disk 2 before Disk 10."""
    parts = re.split(r"(\d+)", name.lower())
    return tuple(int(p) if p.isdigit() else p for p in parts)
