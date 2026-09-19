"""The scan reads one level below the platform, and not one more.

Games are getting folders: `{platform}/{game}/{rom}`, with `mods/` and
`extras/` inside them for what people add by hand. That means the walk has to
go a level deeper than the two directories it reads today, and it means the
depth is not a detail to be generous about.

Exactly one level, because `zip`, `7z`, `rar`, `bin`, `img` and `iso` are all
ROM extensions. A texture pack in an archive under `{game}/mods/` is, to a
walk that recurses, a game - and it would be given a row, a cover, a place on
the shelf and a share of somebody's quota. At one level `mods/` sits two
levels down and is out of reach by construction rather than by a rule that has
to be remembered.

`_originals/` is the same shape of problem from the other side. A conversion
to CHD parks the disc it replaced there, and the only reason those files stop
being games is that the scan does not descend. The name is skipped explicitly
now: exclusions cannot do it, because they are consulted only for a file that
has no row yet, and a parked disc kept its row until the conversion ended it.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from handler.filesystem.rom_scanner import scan_candidates, scan_dirs_for


def _tree(*paths: str) -> Path:
    """Build a platform folder. A path ending in / is a directory, otherwise a
    file (with the directories above it)."""
    root = Path(tempfile.mkdtemp()) / "psx"
    root.mkdir(parents=True)
    for path in paths:
        target = root / path.rstrip("/")
        if path.endswith("/"):
            target.mkdir(parents=True, exist_ok=True)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"x")
    return root


def _found(platform: Path) -> set[str]:
    names: set[str] = set()
    for scan_dir in scan_dirs_for(platform):
        names.update(p.name for p in scan_candidates(scan_dir))
    return names


def test_a_rom_in_its_own_game_folder_is_found():
    assert _found(_tree("Silent Hill/Silent Hill.chd")) == {"Silent Hill.chd"}


def test_the_flat_shape_still_works_beside_it():
    """Nobody has to move anything. A library that is half moved is the state
    people will actually be in, so both shapes are read at once."""
    found = _found(_tree("Loose.chd", "Silent Hill/Silent Hill.chd"))
    assert found == {"Loose.chd", "Silent Hill.chd"}


def test_a_game_folder_under_roms_is_found_too():
    """Structure B with game folders: {platform}/roms/{game}/{rom}."""
    assert _found(_tree("roms/Suikoden/Suikoden.chd")) == {"Suikoden.chd"}


def test_what_a_game_keeps_beside_its_rom_is_not_a_game():
    """The whole reason for one level and no more. Both of these are archives,
    and an archive is a ROM extension."""
    platform = _tree(
        "Silent Hill/Silent Hill.chd",
        "Silent Hill/mods/hd-textures.zip",
        "Silent Hill/extras/soundtrack.7z",
    )
    assert _found(platform) == {"Silent Hill.chd"}


def test_a_folder_inside_a_game_folder_is_never_read():
    """Not only mods and extras by name: the depth itself is the rule, so a
    folder nobody anticipated cannot smuggle a file in either."""
    platform = _tree("Silent Hill/Silent Hill.chd", "Silent Hill/whatever/Another.chd")
    assert _found(platform) == {"Silent Hill.chd"}


def test_a_disc_put_aside_by_a_conversion_does_not_come_back():
    """`_originals/` holds what a CHD conversion replaced. Read, every one of
    those files is a second copy of a game already on the shelf."""
    platform = _tree("Game.chd", "_originals/Game.cue", "_originals/Game.bin")
    assert _found(platform) == {"Game.chd"}


def test_the_originals_of_a_game_folder_are_left_alone_as_well():
    """The conversion parks them beside the disc, so once the disc lives in a
    game folder that is where the folder appears."""
    platform = _tree("Silent Hill/Silent Hill.chd", "Silent Hill/_originals/Silent Hill.cue")
    assert _found(platform) == {"Silent Hill.chd"}


def test_mods_and_extras_directly_under_the_platform_are_not_games_either():
    """They are not a game's folder there, and reading them would file whatever
    somebody parked there as titles."""
    platform = _tree("Game.chd", "mods/pack.zip", "extras/manual.7z")
    assert _found(platform) == {"Game.chd"}


def test_a_hidden_folder_is_not_read():
    """`.git`, `.Trash-1000`, `@eaDir` and friends: directories that belong to
    a tool rather than to the library."""
    platform = _tree("Game.chd", ".Trash-1000/deleted.chd")
    assert _found(platform) == {"Game.chd"}


def test_the_platform_folder_is_still_read_first():
    platform = _tree("Game.chd", "Silent Hill/Silent Hill.chd")
    assert scan_dirs_for(platform)[0] == platform


def test_no_directory_is_read_twice():
    """A file counted twice is a row upserted twice in one pass, and `roms/` is
    both a directory of the platform and a directory the walk names outright."""
    platform = _tree("roms/Game.chd", "Silent Hill/Silent Hill.chd")
    dirs = list(scan_dirs_for(platform))
    assert len(dirs) == len(set(dirs))


def test_an_empty_platform_is_still_empty():
    assert _found(_tree()) == set()
