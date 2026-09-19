"""Bringing the platforms a library already has for one console together.

One console is one platform (rom_platform_map.SAME_CONSOLE): Mega Drive and
Genesis, Famicom and NES. A library that met them under both names has a
platform row for each, with games on both, and the scan now reads every folder
of the console into one platform. So before any scan, each game is moved onto
the console's row, keeping its id, which its saves, play history, collections
and owner all hang off.

Its artwork moves too, because the media folder is named after the platform's
slug and removing a game looks for the artwork there. Only the files lying in
that folder move: an install without a volume for saves keeps them in folders
inside it, and the save rows point at those paths. A picture that cannot be
moved keeps its old address, which still serves it.

A platform's own settings come along when the console's row has none of its
own: the scan exclusions are joined, a name or cover somebody gave it is kept,
and its scrape preset and stored platform information move to the console.

A PLATFORM ROW TAKES ITS GAMES WITH IT WHEN IT IS DELETED (ON DELETE CASCADE).
So a row is removed only after its games are on the other one, and that is
counted rather than assumed. Runs on every start and does nothing once there
is nothing left to bring together.
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from sqlalchemy import func, select

from config import RESOURCES_PATH, config_manager
from handler.database.session import async_session_factory
from handler.metadata.rom_platform_map import (
    PLATFORM_MAP,
    SAME_CONSOLE,
    canonical_fs_slug,
    slug_from_fs_slug,
)
from models.rom import Rom
from models.rom_platform import RomPlatform

logger = logging.getLogger(__name__)

#: Settings kept per platform under its folder name.
_SECTIONS_BY_FOLDER = ("rom_scrape_presets", "platform_info")


async def merge_console_platforms(*, session=None, resources_path: str | None = None) -> dict:
    """Move every game of a platform row named after another name of a console
    onto that console's row, and remove the emptied row.

    Answers with how many rows were merged, how many were renamed in place (a
    console with no row of its own yet) and how many games moved.
    """
    if session is None:
        async with async_session_factory() as own:
            return await merge_console_platforms(session=own, resources_path=resources_path)

    resources = Path(resources_path or RESOURCES_PATH)
    counts = {"merged": 0, "renamed": 0, "roms_moved": 0}
    renamed_folders: list[tuple[str, str]] = []

    rows = list((await session.execute(select(RomPlatform).order_by(RomPlatform.id))).scalars())
    for row in rows:
        main = canonical_fs_slug(row.fs_slug)
        if main == row.fs_slug:
            continue
        main_slug = slug_from_fs_slug(main)
        main_name = PLATFORM_MAP.get(main, {}).get("name", row.name)
        target = next((r for r in rows if r is not row and r.fs_slug == main), None) \
            or next((r for r in rows if r is not row and r.slug == main_slug), None)

        alias = row.fs_slug
        if target is None:
            # The console has no row of its own yet: this one becomes it.
            old_slug = row.slug
            row.fs_slug, row.slug, row.name = main, main_slug, main_name
            for rom in await _roms_of(session, row.id):
                _move_media(rom, old_slug, main_slug, resources)
            await session.commit()
            renamed_folders.append((alias, main))
            counts["renamed"] += 1
            logger.info("Platform %s is now %s", alias, main)
            continue

        roms = await _roms_of(session, row.id)
        for rom in roms:
            _move_media(rom, row.slug, target.slug, resources)
            rom.platform_id = target.id
        _join_settings(target, row)
        await session.flush()
        left = (await session.execute(
            select(func.count(Rom.id)).where(Rom.platform_id == row.id))).scalar()
        if left:
            # Never delete a row with games on it: they would go with it. What
            # has moved stays moved - its artwork already has - and the row is
            # left for the next start.
            await session.commit()
            logger.error("Platform %s still has %d game(s) after the merge; left as it is",
                         alias, left)
            continue
        await session.delete(row)
        await session.commit()
        renamed_folders.append((alias, main))
        counts["merged"] += 1
        counts["roms_moved"] += len(roms)
        logger.info("Platform %s merged into %s (%d game(s))", alias, main, len(roms))

    for alias, main in renamed_folders:
        _move_settings(alias, main)
    return counts


async def _roms_of(session, platform_id: int) -> list[Rom]:
    return list((await session.execute(
        select(Rom).where(Rom.platform_id == platform_id).order_by(Rom.id))).scalars())


def _move_media(rom: Rom, old_slug: str, new_slug: str, resources: Path) -> None:
    """Move the artwork lying in this game's media folder to the folder named
    after its new platform, and point the row at what moved."""
    if old_slug == new_slug:
        return
    old_dir = resources / "roms" / old_slug / str(rom.id)
    if not old_dir.is_dir():
        return
    new_dir = resources / "roms" / new_slug / str(rom.id)
    moved: set[str] = set()
    for item in sorted(old_dir.iterdir()):
        if not item.is_file():
            continue            # saves on an older install, and anything else
        landing = new_dir / item.name
        if landing.exists():
            continue            # the old address still serves this one
        try:
            new_dir.mkdir(parents=True, exist_ok=True)
            os.replace(item, landing)
            moved.add(item.name)
        except OSError as exc:
            logger.warning("Could not move %s: %s", item, exc)
    if moved:
        old_prefix = f"/resources/roms/{old_slug}/{rom.id}/"
        new_prefix = f"/resources/roms/{new_slug}/{rom.id}/"

        def _moved(value):
            if isinstance(value, str) and value.startswith(old_prefix):
                rest = value[len(old_prefix):]
                if rest.split("?", 1)[0] in moved:
                    return new_prefix + rest
            return value

        for column in Rom.__table__.columns:
            value = getattr(rom, column.key, None)
            if isinstance(value, str):
                changed = _moved(value)
                if changed != value:
                    setattr(rom, column.key, changed)
            elif isinstance(value, list) and any(isinstance(v, str) for v in value):
                changed = [_moved(v) for v in value]
                if changed != value:
                    setattr(rom, column.key, changed)
    for leftover in (old_dir, old_dir.parent):
        try:
            leftover.rmdir()    # only when nothing is left in it
        except OSError:
            break


def _join_settings(target: RomPlatform, row: RomPlatform) -> None:
    """Keep what somebody set on the platform being merged away, where the
    console's own row has nothing of its own."""
    lines = [ln for ln in (target.scan_exclude or "").splitlines() if ln.strip()]
    for line in (row.scan_exclude or "").splitlines():
        if line.strip() and line not in lines:
            lines.append(line)
    target.scan_exclude = "\n".join(lines) or None
    for field in ("custom_name", "cover_path", "igdb_id", "ss_id", "launchbox_id"):
        if not getattr(target, field, None) and getattr(row, field, None):
            setattr(target, field, getattr(row, field))


def _move_settings(alias: str, main: str) -> None:
    """A platform's scrape preset and stored information, kept under its folder
    name, go to the console - unless the console already has its own."""
    for name in _SECTIONS_BY_FOLDER:
        section = config_manager.get_section(name)
        if not isinstance(section, dict) or alias not in section:
            continue
        section = dict(section)
        value = section.pop(alias)
        section.setdefault(main, value)
        config_manager.save_section(name, section)


def tidy_console_folders(library_root: str) -> list[str]:
    """Remove the EMPTY folders of the other names of a console.

    The application used to make a folder for every name it knew, so a library
    has `megadrive/` and `famicom/` beside `genesis/` and `nes/` with nothing in
    them. A folder with anything inside is somebody's, and stays.
    """
    root = Path(library_root)
    removed: list[str] = []
    for group in SAME_CONSOLE:
        for name in group[1:]:
            folder = root / name
            try:
                if folder.is_dir() and not any(folder.iterdir()):
                    folder.rmdir()
                    removed.append(name)
            except OSError:
                continue
    return removed
