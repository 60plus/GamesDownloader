"""The extras and mods a game keeps beside it, in its own folder.

`{game}/extras/` holds its manual and whatever else belongs to it - maps, box
scans, a soundtrack - and `{game}/mods/` the patches and packs somebody added.
Both are put there over FTP, subfolders and all, and the scan never reads
either, so what they hold is read off the disk when a game's page asks rather
than kept in the database. The page shows them the way a GOG or custom game
shows its extras (the owner's decision, 2026-09-19).

The folder is one people write to, so nothing in it is taken on trust: only
files are offered, never a hidden one or a transfer still being written, never
a link out of the folder, and a path is served only if it is one of those.

A game lying loose on a shared shelf has no folder of its own. The shelf's
extras/ belong to every loose game there, so the only extra such a game has is
its own manual, named after it.
"""
from __future__ import annotations

from pathlib import Path

from utils.game_folders import shelves_of

#: The two folders beside a game, and what their files are called on its page.
KINDS: dict[str, str] = {"extras": "extra", "mods": "mod"}

#: A folder dropped in by mistake - a whole collection - should not turn one
#: game's page into a listing of thousands.
MAX_FILES = 500


def _own_folder(rom, library_root: str, fs_slug: str) -> Path | None:
    """The game's own folder, or None for a game lying loose on a shelf."""
    folder = Path(str(getattr(rom, "fs_path", "") or ""))
    if not folder.parts or folder in shelves_of(Path(library_root) / fs_slug):
        return None
    return folder


def _loose_manual(rom, library_root: str) -> tuple[str, Path] | None:
    from handler.metadata import manuals

    found = manuals.resolve_manual(rom, library_root)
    if found is None:
        return None
    return str(rom.manual_path), found


def _offered(path: Path, root: Path) -> bool:
    """A file somebody meant to be there: not hidden, not half-written, and
    really inside *root* rather than reached through a link out of it."""
    if path.is_symlink() or not path.is_file():
        return False
    relative = path.relative_to(root)
    if any(part.startswith(".") for part in relative.parts):
        return False
    if path.suffix.lower() == ".part":
        return False
    try:
        return root.resolve() in path.resolve().parents
    except OSError:
        return False


def extras_of(rom, *, library_root: str, fs_slug: str) -> list[dict]:
    """What the game's page offers besides the game: [{kind, path, name, size}].

    *path* is relative to the game's folder, which is what a ticket names and
    all the page is told - never where the folder is on the server's disk.
    """
    folder = _own_folder(rom, library_root, fs_slug)
    if folder is None:
        loose = _loose_manual(rom, library_root)
        if loose is None:
            return []
        relative, found = loose
        return [{"kind": "extra", "path": relative, "name": found.name,
                 "size": found.stat().st_size}]

    listed: list[dict] = []
    for sub, kind in KINDS.items():
        root = folder / sub
        if not root.is_dir() or root.is_symlink():
            continue
        for path in sorted(root.rglob("*"), key=lambda p: p.as_posix().lower()):
            if len(listed) >= MAX_FILES:
                return listed
            if not _offered(path, root):
                continue
            listed.append({
                "kind": kind,
                "path": path.relative_to(folder).as_posix(),
                "name": path.relative_to(root).as_posix(),
                "size": path.stat().st_size,
            })
    return listed


def extra_path(rom, relative: str, *, library_root: str, fs_slug: str) -> Path | None:
    """The file *relative* names, if it is one this game's page offers."""
    wanted = str(relative or "")
    for offered in extras_of(rom, library_root=library_root, fs_slug=fs_slug):
        if offered["path"] == wanted:
            folder = _own_folder(rom, library_root, fs_slug)
            if folder is None:
                loose = _loose_manual(rom, library_root)
                return loose[1] if loose else None
            return folder / wanted
    return None


def removable_extras(rom, *, library_root: str, fs_slug: str, folder_shared: bool) -> list[Path]:
    """What goes with the game when it is deleted with its files (the owner's
    decision D): everything in its extras/ and mods/, the hidden and unfinished
    included, or an emptied folder stays on the disk for good.

    Nothing when another game shares the folder - then they are not only this
    game's. A loose game takes only its own manual from the shared extras/.
    """
    folder = _own_folder(rom, library_root, fs_slug)
    if folder is None:
        loose = _loose_manual(rom, library_root)
        return [loose[1]] if loose else []
    if folder_shared:
        return []
    found: list[Path] = []
    for sub in KINDS:
        root = folder / sub
        if root.is_dir() and not root.is_symlink():
            found += [p for p in sorted(root.rglob("*")) if _really_here(p, root)]
    return found


def _really_here(path: Path, root: Path) -> bool:
    """A file that is itself inside *root*, not a link to one somewhere else.

    Deleting resolves a path before it unlinks it, so a link dropped into mods/
    pointing at another game's ROM would take THAT file. A link is left where
    it is, and so is anything reached through one.
    """
    if path.is_symlink() or not path.is_file():
        return False
    try:
        return root.resolve() in path.resolve().parents
    except OSError:
        return False
