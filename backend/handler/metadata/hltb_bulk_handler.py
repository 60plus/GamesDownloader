"""Bulk HLTB rescrape - fills playtime data for ROMs, GOG games, and Library games.

Each function queries items missing HLTB data (or all items when force=True),
calls hltb_handler.search_game(), and commits updates one-by-one so a single
failure doesn't roll back the whole batch.
"""
from __future__ import annotations

import asyncio
import logging

from sqlalchemy import select

from handler.database.session import async_session_factory
from handler.metadata import hltb_handler
from models.gog_game import GogGame
from models.library_game import LibraryGame
from models.rom import Rom
from models.rom_platform import RomPlatform

logger = logging.getLogger(__name__)

# Delay between HLTB requests - be polite to their servers
_DELAY = 1.2


async def rescrape_roms(force: bool = False) -> dict:
    """Bulk-rescrape HLTB playtime for ROMs.

    force=False  → only ROMs where hltb_main_s IS NULL
    force=True   → all ROMs (overwrites existing data)
    """
    from handler.metadata.rom_platform_map import get_hltb_name

    # Collect (rom_id, rom_name, fs_slug) tuples in a short-lived session
    async with async_session_factory() as session:
        q = (
            select(Rom.id, Rom.name, RomPlatform.fs_slug)
            .join(RomPlatform, Rom.platform_id == RomPlatform.id)
        )
        if not force:
            q = q.where(Rom.hltb_main_s.is_(None))
        rows = (await session.execute(q)).all()

    stats = {"found": len(rows), "updated": 0, "not_found": 0, "errors": 0}
    logger.info("HLTB bulk ROM rescrape: %d ROMs to process (force=%s)", len(rows), force)

    for rom_id, rom_name, fs_slug in rows:
        hltb_platform = get_hltb_name(fs_slug)
        try:
            data = await hltb_handler.search_game(rom_name, hltb_platform)
            if data:
                async with async_session_factory() as session:
                    async with session.begin():
                        rom = await session.get(Rom, rom_id)
                        if rom:
                            for k, v in data.items():
                                setattr(rom, k, v)
                stats["updated"] += 1
                logger.debug("HLTB ROM '%s' → main=%s 100%%=%s",
                             rom_name, data.get("hltb_main_s"), data.get("hltb_complete_s"))
            else:
                stats["not_found"] += 1
        except Exception as exc:
            logger.error("HLTB bulk ROM error for '%s': %s", rom_name, exc)
            stats["errors"] += 1
        await asyncio.sleep(_DELAY)

    logger.info("HLTB bulk ROM rescrape done: %s", stats)
    return stats


async def rescrape_gog(force: bool = False) -> dict:
    """Bulk-rescrape HLTB playtime for GOG games.

    force=False  → only games where hltb_main_s IS NULL
    force=True   → all games
    """
    async with async_session_factory() as session:
        q = select(GogGame.id, GogGame.title)
        if not force:
            q = q.where(GogGame.hltb_main_s.is_(None))
        rows = (await session.execute(q)).all()

    stats = {"found": len(rows), "updated": 0, "not_found": 0, "errors": 0}
    logger.info("HLTB bulk GOG rescrape: %d games to process (force=%s)", len(rows), force)

    for game_id, title in rows:
        try:
            data = await hltb_handler.search_game(title or "")
            if data:
                async with async_session_factory() as session:
                    async with session.begin():
                        game = await session.get(GogGame, game_id)
                        if game:
                            if data.get("hltb_main_s"):
                                game.hltb_main_s = data["hltb_main_s"]
                            if data.get("hltb_complete_s"):
                                game.hltb_complete_s = data["hltb_complete_s"]
                stats["updated"] += 1
            else:
                stats["not_found"] += 1
        except Exception as exc:
            logger.error("HLTB bulk GOG error for '%s': %s", title, exc)
            stats["errors"] += 1
        await asyncio.sleep(_DELAY)

    logger.info("HLTB bulk GOG rescrape done: %s", stats)
    return stats


async def rescrape_library(force: bool = False) -> dict:
    """Bulk-rescrape HLTB playtime for Library games.

    force=False  → only games where hltb_main_s IS NULL
    force=True   → all games
    """
    async with async_session_factory() as session:
        q = select(LibraryGame.id, LibraryGame.title)
        if not force:
            q = q.where(LibraryGame.hltb_main_s.is_(None))
        rows = (await session.execute(q)).all()

    stats = {"found": len(rows), "updated": 0, "not_found": 0, "errors": 0}
    logger.info("HLTB bulk Library rescrape: %d games to process (force=%s)", len(rows), force)

    for game_id, title in rows:
        try:
            data = await hltb_handler.search_game(title or "")
            if data:
                async with async_session_factory() as session:
                    async with session.begin():
                        game = await session.get(LibraryGame, game_id)
                        if game:
                            if data.get("hltb_main_s"):
                                game.hltb_main_s = data["hltb_main_s"]
                            if data.get("hltb_complete_s"):
                                game.hltb_complete_s = data["hltb_complete_s"]
                stats["updated"] += 1
            else:
                stats["not_found"] += 1
        except Exception as exc:
            logger.error("HLTB bulk Library error for '%s': %s", title, exc)
            stats["errors"] += 1
        await asyncio.sleep(_DELAY)

    logger.info("HLTB bulk Library rescrape done: %s", stats)
    return stats
