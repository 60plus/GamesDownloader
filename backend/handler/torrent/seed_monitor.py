"""Background tasks for torrent lifecycle management.

seed_monitor_loop():
  Runs every 60 s. For each "seeding" LibraryTorrent:
    - Asks Transmission for current stats.
    - If uploadedEver >= file_size → the file has been fully delivered to at
      least one peer → mark torrent as expired and remove it from Transmission.
    - If Transmission no longer knows about the torrent → mark as error.

download_monitor_loop():
  Runs every 10 s. For each "downloading" TorrentDownload:
    - Updates percent_done / rate / eta / total_size in DB.
    - If percentDone == 1.0 → auto-register as LibraryGame+LibraryFile, mark complete.
    - If error → mark as error.
    - Emits Socket.IO events for real-time UI updates.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


async def seed_monitor_loop() -> None:
    """Check seeding torrents every 60 s and expire when fully uploaded."""
    await asyncio.sleep(30)   # give Transmission time to settle on startup
    while True:
        try:
            await _check_seeds()
        except Exception as exc:
            logger.warning("seed_monitor error: %s", exc)
        await asyncio.sleep(60)


async def download_monitor_loop() -> None:
    """Poll in-progress admin torrent downloads every 10 s."""
    await asyncio.sleep(15)
    while True:
        try:
            await _check_downloads()
        except Exception as exc:
            logger.warning("download_monitor error: %s", exc)
        await asyncio.sleep(10)


# ── Seed monitor ──────────────────────────────────────────────────────────────

async def _check_seeds() -> None:
    from handler.database.session import async_session_factory
    from handler.torrent.transmission_handler import transmission_handler
    from models.library_torrent import LibraryTorrent
    from sqlalchemy import select

    async with async_session_factory() as db:
        rows = (await db.execute(
            select(LibraryTorrent).where(LibraryTorrent.status == "seeding")
        )).scalars().all()

    for lt in rows:
        if lt.transmission_id is None:
            continue
        info = await transmission_handler.get_torrent(lt.transmission_id)
        if info is None:
            # Transmission no longer tracking this - mark error
            await _update_seed_status(lt.id, "error")
            logger.info("Seed torrent %d lost from Transmission - marked error", lt.id)
            continue

        uploaded = info.get("uploadedEver", 0)
        file_size = lt.file_size or 1

        if uploaded >= file_size:
            # Full upload detected - expire torrent
            await transmission_handler.remove_torrent(lt.transmission_id, delete_data=False)
            await _update_seed_status(lt.id, "expired")
            if lt.torrent_path and os.path.exists(lt.torrent_path):
                try:
                    os.remove(lt.torrent_path)
                except OSError:
                    pass
            logger.info(
                "Seed torrent %d expired (uploaded %d / %d bytes)",
                lt.id, uploaded, file_size,
            )


async def _update_seed_status(torrent_id: int, status: str) -> None:
    from handler.database.session import async_session_factory
    from models.library_torrent import LibraryTorrent
    from sqlalchemy import update

    async with async_session_factory() as db:
        await db.execute(
            update(LibraryTorrent)
            .where(LibraryTorrent.id == torrent_id)
            .values(status=status)
        )
        await db.commit()


# ── Download monitor ──────────────────────────────────────────────────────────

async def _check_downloads() -> None:
    from handler.database.session import async_session_factory
    from handler.torrent.transmission_handler import transmission_handler
    from handler.socket_handler import sio
    from models.torrent_download import TorrentDownload
    from sqlalchemy import select, update

    async with async_session_factory() as db:
        rows = (await db.execute(
            select(TorrentDownload).where(TorrentDownload.status == "downloading")
        )).scalars().all()

    for td in rows:
        if td.transmission_id is None:
            continue

        info = await transmission_handler.get_torrent(td.transmission_id)
        if info is None:
            await _update_download(td.id, {"status": "error", "error_msg": "Torrent lost from Transmission"})
            await sio.emit("torrent:download_error", {"id": td.id, "error": "Torrent lost"})
            continue

        tr_status = info.get("status", 0)
        percent   = float(info.get("percentDone", 0.0))
        updates: dict = {
            "percent_done":  percent,
            "total_size":    info.get("totalSize", 0),
            "rate_download": info.get("rateDownload", 0),
            "eta":           info.get("eta", -1),
        }

        if info.get("error", 0) != 0:
            updates["status"]    = "error"
            updates["error_msg"] = info.get("errorString", "Unknown error")
            await _update_download(td.id, updates)
            await sio.emit("torrent:download_error", {"id": td.id, "error": updates["error_msg"]})
            continue

        if percent >= 1.0:
            updates["status"]       = "complete"
            updates["completed_at"] = datetime.now(timezone.utc)
            await _update_download(td.id, updates)
            game_id = await _auto_register_game(td)
            if game_id:
                await _update_download(td.id, {"game_id": game_id})
            await sio.emit("torrent:download_complete", {"id": td.id, "game_id": game_id})
            continue

        await _update_download(td.id, updates)
        await sio.emit("torrent:download_progress", {
            "id":      td.id,
            "percent": round(percent * 100, 1),
            "speed":   info.get("rateDownload", 0),
            "eta":     info.get("eta", -1),
            "status":  transmission_handler.STATUS.get(tr_status, "unknown"),
        })


async def _update_download(torrent_id: int, values: dict) -> None:
    from handler.database.session import async_session_factory
    from models.torrent_download import TorrentDownload
    from sqlalchemy import update

    async with async_session_factory() as db:
        await db.execute(
            update(TorrentDownload)
            .where(TorrentDownload.id == torrent_id)
            .values(**values)
        )
        await db.commit()


async def _resolve_target_library(td):
    """Resolve the finished torrent's destination.

    Returns (storage_folder, target_lib_id) where:
      - a folder-backed custom library (kind "custom_lib" with a storage_folder)
        routes files into that folder and yields its id for a membership row;
      - anything else (no library, "games", GOG, emulation, or a folder-less lib)
        falls back to the built-in Games library (CUSTOM), target_lib_id=None.
    """
    slug = (getattr(td, "library", None) or "").strip()
    if not slug or slug == "games":
        return "CUSTOM", None
    try:
        from handler.database.library_registry_handler import library_registry_handler
        lib = await library_registry_handler.get_by_slug(slug)
    except Exception as exc:
        logger.warning("Torrent target library lookup failed for '%s': %s", slug, exc)
        return "CUSTOM", None
    if lib is not None and lib.kind == "custom_lib" and lib.storage_folder:
        return lib.storage_folder, lib.id
    return "CUSTOM", None


def _collect_files(download_dir: str) -> list[str]:
    """Every real file the torrent left behind. Blocking; call in a thread."""
    found = []
    for root, _, fnames in os.walk(download_dir):
        for fname in fnames:
            if not fname.startswith("."):
                found.append(os.path.join(root, fname))
    return found


def _move_into_library(
    files: list[str], download_dir: str, dest_root: str,
) -> list[tuple[str, int]]:
    """Move a finished torrent into the library and drop its download dir.

    Blocking, and not briefly: docker-compose mounts /data/games and
    /data/downloads as separate binds, so rename(2) between them returns EXDEV
    and shutil.move always degrades to a full copy. On a 60 GB torrent that is
    minutes of solid I/O, which is why this belongs in a thread and not on the
    event loop where it used to sit - holding a database session open the whole
    time and stopping every request, the health check and Socket.IO with it.
    """
    import shutil

    os.makedirs(dest_root, exist_ok=True)
    moved = []
    for fpath in files:
        dest = os.path.join(dest_root, os.path.relpath(fpath, download_dir))
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.move(fpath, dest)
        # Sized here, in the thread, so the caller does not stat every file
        # back on the event loop.
        moved.append((dest, os.path.getsize(dest)))
        logger.debug("Moved torrent file %s -> %s", fpath, dest)
    try:
        shutil.rmtree(download_dir)
    except Exception:
        pass  # ignore cleanup errors
    return moved


async def _auto_register_game(td) -> int | None:
    """Scan download_dir, move files to /data/games/{storage_folder}/{slug}/,
    register as LibraryGame. When the download targets a folder-backed custom
    library, files land in that library's folder and the game is added to it
    (membership) instead of the default Games library."""
    from handler.database.session import async_session_factory
    from models.library_game import LibraryGame
    from models.library_file import LibraryFile
    from config import BASE_PATH
    import unicodedata, re

    download_dir = td.download_dir
    if not os.path.isdir(download_dir):
        return None

    files_found = await asyncio.to_thread(_collect_files, download_dir)
    if not files_found:
        return None

    # Resolve destination library (folder + optional membership target).
    storage_folder, target_lib_id = await _resolve_target_library(td)
    is_custom_lib = target_lib_id is not None

    # Slugify title
    title = td.title or "Unknown Game"
    slug_base = re.sub(r"[^a-z0-9]+", "-",
                       unicodedata.normalize("NFKD", title).lower()
                       .encode("ascii", errors="ignore").decode()).strip("-")

    # Claim the slug and the row first, in a session that closes immediately.
    # The copy below can run for minutes, and it used to run inside this
    # session, which meant a database connection sat open and idle for all of
    # it. Owning the row up front also means the slug cannot be taken by a
    # second torrent finishing while this one is still copying.
    async with async_session_factory() as db:
        from sqlalchemy import select
        slug = slug_base
        n = 1
        while (await db.execute(
            select(LibraryGame).where(LibraryGame.slug == slug)
        )).scalar_one_or_none():
            slug = f"{slug_base}-{n}"
            n += 1

        game = LibraryGame(
            title=title,
            slug=slug,
            source="torrent",
            is_active=True,
            published_by=None,
            # A game routed into a custom library lives only there by default.
            in_default_library=not is_custom_lib,
        )
        db.add(game)
        await db.commit()
        game_id = game.id

    # Move files from torrent download dir → /data/games/{storage_folder}/{slug}/
    dest_root = os.path.join(BASE_PATH, "games", storage_folder, slug)
    try:
        moved_files = await asyncio.to_thread(
            _move_into_library, files_found, download_dir, dest_root
        )
    except Exception as exc:
        # Never leave a game row behind with no files under it: it would show on
        # the shelf as a title that cannot be downloaded and cannot be explained.
        logger.error("Torrent files could not be moved into %s: %s", dest_root, exc)
        async with async_session_factory() as db:
            orphan = await db.get(LibraryGame, game_id)
            if orphan is not None:
                await db.delete(orphan)
                await db.commit()
        return None

    async with async_session_factory() as db:
        game = await db.get(LibraryGame, game_id)
        for fpath, size in moved_files:
            lib_file = LibraryFile(
                library_game_id=game.id,
                filename=os.path.basename(fpath),
                file_path=os.path.relpath(fpath, BASE_PATH),
                size_bytes=size,
                os=td.os,
                file_type="game",
                source="torrent",
                is_available=True,
            )
            db.add(lib_file)

        await db.commit()
        from plugins import events as _plugin_events
        _plugin_events.game_added(game)
        _plugin_events.download_complete(
            game, os.path.dirname(moved_files[0][0]) if moved_files else dest_root
        )
        # Recently-added card: no-op unless the torrent game already has a cover
        # (usually it does not until an admin scrapes it, which announces then).
        try:
            from handler.notifications.recently_added import schedule_library_game
            schedule_library_game(game_id)
        except Exception:
            pass

    # Membership is written through the registry handler (its own session), so
    # it must happen after the game row is committed above.
    if is_custom_lib:
        try:
            from handler.database.library_registry_handler import library_registry_handler
            await library_registry_handler.set_memberships(game_id, [target_lib_id])
        except Exception as exc:
            logger.warning("Torrent membership assignment failed for game %d: %s", game_id, exc)

    logger.info(
        "Auto-registered game '%s' (id=%d) from torrent → %s/%s%s",
        title, game_id, storage_folder, slug,
        " (custom library)" if is_custom_lib else "",
    )
    return game_id
