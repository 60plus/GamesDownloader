"""Startup reconciliation: make the database agree with what is on disk.

Almost everything that puts a file on the server, or takes one away, updates the
database in the same breath. The exception is a crash - and one narrow but real
case: the hook that marks a GOG game downloaded runs as a detached task after
the last file lands, so a restart in that moment leaves a complete game flagged
as not downloaded, with nothing to correct it until someone touches that game
again. That is exactly how a fully downloaded Tomb Raider sat in the library
offering no way to download it.

Rather than special-casing GOG, this works from the one fact every library
shares: a file someone can download is a LibraryFile row, and the file it points
at either exists or it does not. Plugin-provided libraries register their files
the same way, so a store added by a plugin is reconciled without knowing
anything about it.

SAFETY: a missing storage mount looks exactly like "the user deleted
everything". The pass refuses to run when the games root is absent, and holds
back any storage area that has nothing left in it at all - see
_group_looks_unmounted, which explains why that, and not a count of missing
files, is the test.
"""

from __future__ import annotations

import asyncio
import logging
import os

from sqlalchemy import select

from config import GAMES_PATH
from handler.database.session import async_session_factory
from models.library_file import LibraryFile

logger = logging.getLogger(__name__)

# Wait a moment so the pass never competes with request handling during boot.
_START_DELAY_S = 45

def _abs_path(rel_path: str) -> str:
    from config import BASE_PATH
    return os.path.normpath(os.path.join(BASE_PATH, rel_path))


def _storage_group(rel_path: str) -> str:
    """The top-level storage area a file lives in: games, downloads, roms..."""
    parts = rel_path.replace("\\", "/").split("/")
    return parts[0] if parts else ""


def _group_looks_unmounted(group: str, all_missing: bool) -> bool:
    """True when a storage area is absent rather than merely emptied.

    Counting how many files disappeared is the wrong test. Packaging a game
    deliberately removes several installers and leaves one archive, and a big
    game can easily be a large share of a small library - a percentage
    threshold would read that as a disaster and refuse to reconcile anything,
    which is worse than doing nothing. What actually distinguishes a missing
    mount is that NOTHING under it survives: no file the database expects, and
    no directory to hold one. As long as a single file is still there, the
    storage is up and the disk can be believed.

    Checked per area so one failed mount cannot suppress reconciliation of the
    others - this project maps games and downloads onto a separate disk.
    """
    if not all_missing:
        return False
    from config import BASE_PATH
    root = os.path.join(BASE_PATH, group)
    if not os.path.isdir(root):
        return True
    try:
        return not any(os.scandir(root))
    except OSError:
        return True


async def reconcile_library_state() -> dict:
    """Bring file availability and the GOG downloaded flag back in line with disk.

    Returns a summary dict; also usable from a one-off script or an admin
    action. Safe to run at any time - it only ever writes what the disk says.
    """
    summary = {"checked": 0, "vanished": 0, "returned": 0, "gog_fixed": 0, "held_back": 0, "skipped": None}

    if not os.path.isdir(GAMES_PATH):
        summary["skipped"] = "games root missing"
        logger.warning(
            "Reconciliation skipped: %s is not a directory. Storage not mounted?", GAMES_PATH
        )
        return summary

    # ── 1. File availability, for every library including plugin ones ────────
    async with async_session_factory() as session:
        files = list((await session.execute(select(LibraryFile))).scalars().all())

    summary["checked"] = len(files)
    vanished, returned = [], []
    for f in files:
        if not f.file_path:
            continue
        on_disk = os.path.isfile(_abs_path(f.file_path))
        if f.is_available and not on_disk:
            vanished.append(f.id)
        elif not f.is_available and on_disk:
            returned.append(f.id)

    # Hold back only the areas that look absent, and only those - a game
    # packaged into a single archive drops several files on purpose, and that
    # must still reconcile.
    per_group: dict[str, list[int]] = {}
    live_groups: set[str] = set()
    for f in files:
        if not f.file_path or not f.is_available:
            continue
        group = _storage_group(f.file_path)
        if f.id in set(vanished):
            per_group.setdefault(group, []).append(f.id)
        else:
            live_groups.add(group)

    held_back = 0
    for group, ids in per_group.items():
        if _group_looks_unmounted(group, all_missing=group not in live_groups):
            vanished = [fid for fid in vanished if fid not in set(ids)]
            held_back += len(ids)
            summary["skipped"] = f"storage area '{group}' is not there"
            logger.error(
                "Reconciliation: storage area '%s' holds nothing at all, so its %d "
                "file(s) are treated as a mount problem, not a deletion. Leaving "
                "them marked available.", group, len(ids),
            )
    summary["held_back"] = held_back

    if vanished or returned:
        async with async_session_factory() as session:
            async with session.begin():
                for fid in vanished:
                    (await session.get(LibraryFile, fid)).is_available = False
                for fid in returned:
                    (await session.get(LibraryFile, fid)).is_available = True
    summary["vanished"] = len(vanished)
    summary["returned"] = len(returned)

    # ── 2. The GOG downloaded flag ───────────────────────────────────────────
    # Its own truth: files present AND the download finished. A game still
    # being fetched is left alone by refresh_downloaded_state.
    from handler.gog.gog_download_handler import refresh_downloaded_state
    from models.gog_game import GogGame

    # One query for every product's current flag instead of one per product.
    # Ordering matches canonical_gog_stmt (admin copy first, then lowest id), so
    # the first row seen per gog_id is the canonical copy that
    # refresh_downloaded_state writes - the exact value the old per-product
    # lookup produced. On a large GOG account that per-product lookup (a session
    # and a query each) was the bulk of the boot-time DB work.
    async with async_session_factory() as session:
        flag_rows = (
            await session.execute(
                select(GogGame.gog_id, GogGame.is_downloaded).order_by(
                    GogGame.gog_id,
                    GogGame.owner_user_id.is_(None).desc(),
                    GogGame.id,
                )
            )
        ).all()
    before_by_id: dict[int, bool] = {}
    for gid, is_dl in flag_rows:
        before_by_id.setdefault(gid, bool(is_dl))

    fixed = 0
    for gog_id, before in before_by_id.items():
        if await refresh_downloaded_state(gog_id=gog_id) != before:
            fixed += 1
    summary["gog_fixed"] = fixed

    product_count = len(before_by_id)
    if vanished or returned or fixed:
        logger.info(
            "Reconciliation: %d file(s) gone from disk, %d back, %d GOG game(s) re-flagged "
            "(of %d files and %d products checked)",
            len(vanished), len(returned), fixed, len(files), product_count,
        )
    else:
        logger.info(
            "Reconciliation: nothing to correct (%d files, %d products)", len(files), product_count
        )
    return summary


async def reconcile_loop() -> None:
    """Run the pass once, shortly after startup."""
    try:
        await asyncio.sleep(_START_DELAY_S)
        await reconcile_library_state()
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("Library reconciliation failed; state stays as it was")
