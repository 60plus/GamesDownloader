"""What a game's folder on disk is called.

One folder per game, `{platform}/{game}/{rom}`, which is what gives mods and
extras somewhere to live beside the ROM. The name comes from the title when
there is one, because that is the name a person recognises, and from the file
name when there is not.

The disc marker comes off either way. Four files called `... (Disc 1)` through
`(Disc 4)` are one game, and they are one game only while they sit in one
directory: the grouping that makes a title out of them reads the names of the
files beside each other, and the playlist the emulator switches discs with is
built from that grouping. Split across four folders they are four games, each
holding a disc the player cannot switch away from.
"""
from __future__ import annotations

import os
from pathlib import Path

from utils.disk_sets import without_disk_marker

# Characters a path cannot hold, or should not. The first group is refused by
# Windows and by SMB shares; the separators are refused everywhere; a colon
# takes a dash rather than nothing, because "Ratchet & Clank - Up Your Arsenal"
# reads and "Ratchet & ClankUp Your Arsenal" does not.
_DASHED = {":"}
_DROPPED = set('<>"|?*\\/') | {chr(c) for c in range(32)}

# Reserved by DOS, still refused by Windows with or without an extension.
_RESERVED = (
    {"con", "prn", "aux", "nul"}
    | {f"com{n}" for n in range(1, 10)}
    | {f"lpt{n}" for n in range(1, 10)}
)

# Names the scan walks past, because they hold something other than a game:
# the shared roms/ shelf and what sits beside a game's ROM. A game's folder
# called one of these would drop off the shelf at the next scan, its files still
# on the disk. Kept in step with rom_scanner._game_folders_in by a test that
# asks the scanner itself.
_NOT_A_GAME = {"roms", "mods", "extras", "_originals"}

# Room for the ROM file's own name inside it. ext4 allows 255 bytes per path
# component and a scraped title can be longer than that on its own; leaving the
# limit at the maximum is also how a folder ends up impossible to reach over a
# protocol with a shorter one.
_MAX = 120


def game_folder_name(*, title: str | None, fs_name: str) -> str:
    """The folder this ROM belongs in, inside its platform's directory."""
    chosen = (title or "").strip() or Path(fs_name).stem
    return _fit_for_a_path(without_disk_marker(chosen)) or "Game"


def game_dir(roms_base, fs_slug: str, fs_name: str, title: str | None = None) -> Path:
    """The full path a ROM of this name belongs at: platform, then game.

    Both roads into the library come through here - the download, which knows
    the file name and learns the title later, and the upload, which knows
    neither until a scrape has run. One rule, or a file uploaded and the same
    file downloaded end up in two folders and the shelf shows the game twice.
    """
    return Path(roms_base) / fs_slug / game_folder_name(title=title, fs_name=fs_name)


def platform_dirs(shelf) -> tuple[Path, ...]:
    """Every folder a platform's games may lie in, its own first.

    New files go into the platform's own folder, and a library put together
    before keeps the folders of the console's other names beside it -
    `megadrive/` next to `genesis/` - which the scan reads into the same
    platform (rom_platform_map.platform_folders).

    And any other folder the scan reads into it. The scan files every directory
    under the root by the platform its name stands for, found by folder name
    and then by URL slug (rom_handler.upsert), so `PlayStation/`, made by
    another program, is the psx platform's too, and `my-hacks/` is the platform
    `My Hacks/` made; a game there that these rules did not count as on a shelf
    split its set, was fetched twice and took the whole shelf for its own
    folder. Looked up on the disk each time rather than kept, because such a
    folder can appear at any moment, and by name first: one listing of the
    root, and a check that it is a folder only for the name that matches.
    """
    from handler.metadata.rom_platform_map import platform_folders, slug_from_fs_slug

    shelf = Path(shelf)
    known = [shelf.parent / name for name in platform_folders(shelf.name)]
    slug = slug_from_fs_slug(shelf.name)
    try:
        names = sorted(os.listdir(shelf.parent))
    except OSError:
        names = []
    for name in names:
        folder = shelf.parent / name
        if folder not in known and slug_from_fs_slug(name) == slug and folder.is_dir():
            known.append(folder)
    return tuple(known)


def shelves_of(shelf) -> tuple[Path, ...]:
    """The shelves a platform's games lie loose on, shared by every game there:
    each of its folders, and `roms/` inside each, the way the scan reads them."""
    return tuple(place for folder in platform_dirs(shelf) for place in (folder, folder / "roms"))


def _fit_for_a_path(name: str) -> str:
    out = "".join(
        " - " if ch in _DASHED else "" if ch in _DROPPED else ch
        for ch in name
    )
    out = " ".join(out.split())[:_MAX]
    # Trailing dots and spaces are legal here and refused by Windows, which is
    # how a folder made on the server becomes one nobody can open over SMB.
    # Leading dots hide the folder from the scan, which skips a tool's directory
    # like .git that way: `.hack//Infection` is a real title.
    out = out.rstrip(" .").lstrip(" .")
    if out.lower() in _RESERVED or out.lower() in _NOT_A_GAME:
        out += " (game)"
    return out
