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


async def _auto_register_game(td) -> int | None:
    """Scan download_dir, move files to /data/games/CUSTOM/{slug}/, register as LibraryGame."""
    from handler.database.session import async_session_factory
    from models.library_game import LibraryGame
    from models.library_file import LibraryFile
    from config import BASE_PATH
    import unicodedata, re, shutil

    download_dir = td.download_dir
    if not os.path.isdir(download_dir):
        return None

    # Collect files
    files_found = []
    for root, _, fnames in os.walk(download_dir):
        for fname in fnames:
            if not fname.startswith("."):
                files_found.append(os.path.join(root, fname))

    if not files_found:
        return None

    # Slugify title
    title = td.title or "Unknown Game"
    slug_base = re.sub(r"[^a-z0-9]+", "-",
                       unicodedata.normalize("NFKD", title).lower()
                       .encode("ascii", errors="ignore").decode()).strip("-")

    async with async_session_factory() as db:
        from sqlalchemy import select
        # Ensure unique slug
        slug = slug_base
        n = 1
        while (await db.execute(
            select(LibraryGame).where(LibraryGame.slug == slug)
        )).scalar_one_or_none():
            slug = f"{slug_base}-{n}"
            n += 1

        # Move files from torrent download dir → /data/games/CUSTOM/{slug}/
        custom_dir = os.path.join(BASE_PATH, "games", "CUSTOM", slug)
        os.makedirs(custom_dir, exist_ok=True)

        moved_files = []
        for fpath in files_found:
            rel_in_dl = os.path.relpath(fpath, download_dir)
            dest = os.path.join(custom_dir, rel_in_dl)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.move(fpath, dest)
            moved_files.append(dest)
            logger.debug("Moved torrent file %s → %s", fpath, dest)

        # Clean up empty download dir
        try:
            shutil.rmtree(download_dir)
        except Exception:
            pass  # ignore cleanup errors

        game = LibraryGame(
            title=title,
            slug=slug,
            source="torrent",
            is_active=True,
            published_by=None,
        )
        db.add(game)
        await db.flush()

        for fpath in moved_files:
            rel = os.path.relpath(fpath, BASE_PATH)
            size = os.path.getsize(fpath)
            lib_file = LibraryFile(
                library_game_id=game.id,
                filename=os.path.basename(fpath),
                file_path=rel,
                size_bytes=size,
                os=td.os,
                file_type="game",
                source="torrent",
                is_available=True,
            )
            db.add(lib_file)

        await db.commit()
        logger.info("Auto-registered game '%s' (id=%d) from torrent → CUSTOM/%s", title, game.id, slug)
        return game.id
