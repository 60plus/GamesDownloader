"""Paths a scanner is told never to look at.

There was no way to say "never scan this", so a stray file - a modding folder
kept beside the ROMs, a manual, an editor's working copy - was found and reported
as a game on every scan, forever. Removing it from the library achieved nothing:
the next scan found the file again and put it straight back.

Both scanners consult this, and the patterns are kept per library and per
platform rather than in one list for the server. They are the same thing from a
scanner's point of view - a folder that gets walked - and the case that motivated
this is local: a folder that belongs beside the Amiga ROMs and nowhere else.

The dangerous half is not the matching, it is what a match is allowed to do. A
skipped file looks exactly like a deleted one, so a scanner that simply stops
seeing a path would mark that part of the library missing the moment somebody
saved a slightly wrong pattern. Rows that already exist are therefore left
completely alone; applying a pattern to them is a separate and deliberate act
with the list shown first.
"""

from __future__ import annotations

import fnmatch

#: Patterns that would match the entire tree. Saving one is never what anybody
#: meant, and the cost of being wrong is the whole library going quiet, so they
#: are dropped when the list is read rather than obeyed when it is used.
#:
#: Kept as documentation of the obvious cases. It is NOT the check: a list of
#: shapes is a list of shapes somebody can step around, and `*\*` did exactly
#: that - it is not in this set, and matching turns it into `*/*` afterwards.
_SWALLOWS_EVERYTHING = {"*", "**", "*/*", "**/*", "/", "./", "."}

#: Two paths that share no segment, no stem and no extension. A pattern that
#: matches BOTH is not describing a stray file, it is describing everything.
#: Asking the real matcher rather than comparing text is what makes this hold
#: for shapes nobody thought to list.
_PROBES = ("alpha/one.rom", "beta/two.bin")


def _swallows_everything(pattern: str) -> bool:
    return all(is_excluded(probe, [pattern]) for probe in _PROBES)


def _made_relative(pattern: str, root: str | None) -> str:
    """An absolute pattern naming something inside the scanned folder, cut down.

    The screen beside the box lists full absolute paths, so an absolute pattern
    is the obvious thing to type rather than an odd one, and it has to mean what
    it plainly means.

    IT HAPPENS HERE, WHEN THE PATTERN IS SAVED, AND NOWHERE ELSE. It used to
    happen at match time, and that put the guard above and the matcher on
    different sides of the same rewrite: the guard judged `<root>/*` - which
    matches neither probe, so it was saved - while matching judged the bare `*`
    it turns into, which matches every file and every directory. The preview
    then offered the whole platform for removal and the apply route deleted
    each row, taking every account's savestates and play history with it by
    cascade. Measured on the shipped code before this moved.

    Doing it at save time means a pattern is stored in the form it will be
    matched in, so those two can no longer disagree.

    A pattern naming somewhere else is left exactly as typed. It matches nothing
    under this root, which is the honest answer: it names another place.
    """
    p = pattern.replace("\\", "/")
    # Nothing but slashes names the root of everything, with or without a root
    # to compare against. The documented list of shapes that swallow the tree
    # has always claimed this one is dropped; it was not, and it survived as a
    # saved pattern that matched nothing.
    if not p.strip("/"):
        return ""
    if not root or not pattern.startswith("/"):
        return pattern
    top = str(root).replace("\\", "/").rstrip("/")
    if not top:
        return pattern
    if p.rstrip("/") == top:
        # The scanned folder itself. Not a pattern - it is everything.
        return ""
    if p.lower().startswith(top.lower() + "/"):
        return p[len(top) + 1:]
    return pattern


def parse_patterns(raw: str | None, *, root: str | None = None) -> list[str]:
    """One pattern per line, with blanks and comments dropped.

    People annotate these lists. A line beginning with # is a note, not a file
    called "#something", and reading it as a pattern would be a surprise nobody
    would connect to what they typed.

    `root` is the folder being scanned, and it is passed when a pattern is being
    SAVED. Reading stored patterns back does not need it: they were stored in
    the form they are matched in.
    """
    if not raw:
        return []
    out: list[str] = []
    for line in str(raw).splitlines():
        pattern = line.strip()
        if not pattern or pattern.startswith("#"):
            continue
        # Cut down BEFORE the guard, so the guard judges what matching will
        # judge. The other order is how `<root>/*` got saved and then meant `*`.
        pattern = _made_relative(pattern, root)
        if not pattern:
            continue
        # Asked of the matcher, not of a list of shapes. The old check compared
        # the raw line against a set containing `*/*`, while matching swaps
        # backslashes for slashes afterwards - so `*\*` was saved happily and
        # then covered the whole library, which is the exact outcome the guard
        # exists to prevent. Measured on a running server before this changed.
        if _swallows_everything(pattern):
            continue
        out.append(pattern)
    return out


def _relative_to(path: str, root: str | None) -> str | None:
    """The path as seen from the thing being scanned, or None if it is outside.

    A pattern describes the library, not the road to it. Matched against the
    absolute path, every directory ABOVE the library was a segment a pattern
    could name: on a default install `/data/games/roms/{platform}/...` meant
    `roms/`, `games/` and `data/` each covered everything, and the guard against
    patterns that swallow the tree could not see it because it probes with
    relative paths where those words never appear.

    None rather than the absolute path when the two disagree about where the
    root is: falling back would restore the bug in the one case nobody would
    think to test.
    """
    if not root:
        return path
    # The PATH keeps its trailing slash - that is how is_excluded_dir says "this
    # is a directory", and stripping it here turned every folder pattern on the
    # games side back into a non-match. Only the ROOT is normalised.
    p = path.replace("\\", "/")
    r = str(root).replace("\\", "/").rstrip("/")
    if not r:
        return path
    if p.rstrip("/") == r:
        return "" if not p.endswith("/") else "/"
    return p[len(r) + 1:] if p.startswith(r + "/") else None


def is_excluded(path: str, patterns, *, root: str | None = None) -> bool:
    """Whether this path is one a scanner was told to leave alone.

    Three shapes, because that is what people actually write:

      Thumbs.db      a name, matched anywhere underneath
      *.txt          a glob on the name, same
      _originals/    a folder, matching everything inside it at any depth
      amiga/extra/*  something with a slash in it, matched against the path

    Case is ignored throughout. Names arrive from whatever wrote them, and a fair
    share of the strays in a real library came off a Windows machine.
    """
    if not patterns:
        return False

    relative = _relative_to(str(path), root)
    if relative is None:
        return False

    normalised = relative.replace("\\", "/").lower()
    name = normalised.rsplit("/", 1)[-1]
    segments = normalised.split("/")

    for raw in patterns:
        pattern = str(raw).replace("\\", "/").strip().lower()
        if not pattern:
            continue

        # NOTHING IS REWRITTEN HERE. An absolute pattern naming something inside
        # the scanned folder is cut down when it is SAVED (`_made_relative`), so
        # what is stored is already what gets matched. Doing it here instead put
        # the swallow guard and this loop on opposite sides of the rewrite:
        # `<root>/*` passed the guard as an ordinary path and then arrived here
        # as a bare `*`, covering every file and every directory on the shelf.
        #
        # A pattern that is still absolute at this point therefore names
        # somewhere else, and matches nothing here - which is the honest answer
        # and the same one it gave before absolute patterns were handled at all.

        if pattern.endswith("/"):
            # A folder. Every file inside it, at any depth - naming the folder
            # should not mean naming everything in it. The trailing slash is
            # also what keeps this from matching a FILE of the same name.
            folder = pattern.rstrip("/")
            if folder and folder in segments[:-1]:
                return True
            continue

        if "/" in pattern:
            # Written as a path, so matched as one, at any point in the tree.
            if fnmatch.fnmatch(normalised, pattern) or fnmatch.fnmatch(normalised, f"*/{pattern}"):
                return True
            continue

        if fnmatch.fnmatch(name, pattern):
            return True

    return False


def is_excluded_dir(path: str, patterns, *, root: str | None = None) -> bool:
    """The same question, asked about a DIRECTORY rather than about a file.

    The games scan decides per game FOLDER; the preview beside it decides per
    file inside that folder. Ask `is_excluded` about a bare directory path and
    it answers as if the path were a file, because that is what it is for - the
    trailing-slash rule deliberately refuses to let `mods/` match a FILE called
    `mods`. Correct there, wrong here, and the two sides disagreed about every
    folder pattern anybody typed:

        mods/   preview said covered, the scan did not exclude  -> it comes back
        mods    the scan excluded, the preview found nothing    -> no button

    There was no pattern that worked. Naming the thing as a directory is all it
    takes, and the trailing slash is what has meant "directory" all along.
    """
    return is_excluded(str(path).replace("\\", "/").rstrip("/") + "/", patterns,
                       root=root)
