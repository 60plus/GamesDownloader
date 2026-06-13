"""
GOG per-platform packaging.

When enabled (Settings → Downloads → Packaging), a downloaded GOG game's
loose files are bundled into a single archive per platform:

    /data/games/GOG/{Title}/windows/{Title}.zip
    /data/games/GOG/{Title}/linux/{Title}.zip
    /data/games/GOG/{Title}/mac/{Title}.zip

Why: a published game can have dozens of files (installer parts, patches).
Downloading them from the server then opens one browser download per file.
One archive per platform = one click, one download.

Notes:
  * The "extras" folder is never packaged - only the OS platform folders.
  * ZIP_STORED (no compression): GOG installers are already compressed, so
    we only "glue" the files together. This is fast and disk-bound, not CPU.
  * The archive is built to a .tmp sibling then atomically os.replace()'d, so
    a crash mid-build never corrupts an existing archive.
  * When delete_originals is on and a NEW file later lands in an already
    packaged folder, the previously-packaged (now deleted) files are streamed
    back out of the old archive into the new one - nothing is ever lost.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import zipfile

from sqlalchemy import select

from config import BASE_PATH, GAMES_PATH
from handler.config.config_handler import config_handler
from models.download_job import DownloadJob

logger = logging.getLogger(__name__)

# OS platform subfolders we package. "extras" is intentionally excluded.
PLATFORMS: tuple[str, ...] = ("windows", "mac", "linux")

# Config keys
KEY_ENABLED          = "gog_zip_per_platform"      # bool - master switch
KEY_DELETE_ORIGINALS = "gog_zip_delete_originals"  # bool - remove loose files after zipping

# Job states that mean "this file is not finished yet".
_PENDING_STATES = ("pending", "queued", "downloading", "paused")

# Per-(gog_id, platform) locks so two file-completions can't race to build the
# same archive at the same time.
_locks: dict[tuple[int, str], asyncio.Lock] = {}


def _lock_for(gog_id: int, platform: str) -> asyncio.Lock:
    key = (gog_id, platform)
    lock = _locks.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _locks[key] = lock
    return lock


async def packaging_enabled() -> bool:
    return await config_handler.get_bool(KEY_ENABLED, default=False)


async def delete_originals_enabled() -> bool:
    return await config_handler.get_bool(KEY_DELETE_ORIGINALS, default=False)


def _sanitize_title(title: str) -> str:
    # Lazy import to avoid a circular import at module load time
    # (gog_download_handler imports this module's hook).
    from handler.gog.gog_download_handler import sanitize_title
    return sanitize_title(title)


def _packable_files(directory: str) -> list[str]:
    """
    Relative paths (posix arcnames) of every real game file under `directory`,
    recursively - so subfolders are bundled too, not just the top level.
    Archives and temp files are skipped.
    """
    out: list[str] = []
    try:
        for root, _dirs, files in os.walk(directory):
            for name in files:
                if name.endswith(".zip") or name.endswith(".tmp"):
                    continue
                full = os.path.join(root, name)
                rel = os.path.relpath(full, directory).replace(os.sep, "/")
                out.append(rel)
    except OSError:
        return []
    return sorted(out)


def _pack_dir_sync(
    src_dir: str, archive_name: str, delete_originals: bool, on_progress=None
) -> dict | None:
    """
    Blocking: bundle the loose files in `src_dir` (recursively) into
    `src_dir/archive_name`. No compression (ZIP_STORED) - this is a straight
    copy into one container, not a slow archive. MUST run in a thread.

    on_progress(done, total) is called after each file so the caller can report
    live progress. Returns {archive_path, size_bytes, file_count} or None.
    """
    archive_path = os.path.join(src_dir, archive_name)
    tmp_path     = archive_path + ".tmp"

    files = _packable_files(src_dir)
    total = len(files)
    existing_archive = archive_path if os.path.exists(archive_path) else None

    # Nothing to do: no loose files and no archive, or only an archive and no
    # new loose files to merge.
    if not files and not existing_archive:
        return None
    if not files:
        # Archive already exists and there is nothing new to add.
        try:
            size = os.path.getsize(existing_archive)  # type: ignore[arg-type]
        except OSError:
            size = 0
        return {"archive_path": archive_path, "size_bytes": size, "file_count": 0, "noop": True}

    seen: set[str] = set()
    try:
        with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_STORED, allowZip64=True) as zf:
            # 1. Add the current loose files (preserving subfolder structure).
            for idx, rel in enumerate(files):
                zf.write(os.path.join(src_dir, rel), arcname=rel)
                seen.add(rel)
                if on_progress:
                    try:
                        on_progress(idx + 1, total)
                    except Exception:
                        pass
            # 2. Merge any previously-packaged files that are not superseded
            #    (only matters when delete_originals removed them earlier).
            if existing_archive:
                with zipfile.ZipFile(existing_archive, "r") as old:
                    for info in old.infolist():
                        if info.filename in seen or info.is_dir():
                            continue
                        with old.open(info, "r") as src, zf.open(info.filename, "w") as dst:
                            shutil.copyfileobj(src, dst, 1024 * 1024)
                        seen.add(info.filename)
    except Exception:
        # Never leave a half-written temp file behind.
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except OSError:
            pass
        raise

    os.replace(tmp_path, archive_path)

    if delete_originals:
        for rel in files:
            try:
                os.remove(os.path.join(src_dir, rel))
            except OSError:
                logger.warning("Could not delete original after packaging: %s", rel)
        # Drop any now-empty subdirectories (bottom-up), but keep src_dir itself.
        for root, _dirs, _files in os.walk(src_dir, topdown=False):
            if os.path.abspath(root) == os.path.abspath(src_dir):
                continue
            try:
                os.rmdir(root)
            except OSError:
                pass

    try:
        size = os.path.getsize(archive_path)
    except OSError:
        size = 0
    return {"archive_path": archive_path, "size_bytes": size, "file_count": len(seen)}


async def _sync_archive_into_library(
    gog_id: int, platform: str, archive_path: str, size_bytes: int, title: str
) -> None:
    """
    Replace the platform's loose installer rows with a single row pointing at
    the new zip - so the library shows one download per platform. The archive
    keeps file_type "game" because the games detail pages only render the
    'game'/'dlc'/'extra' groups; a custom type would be hidden from users.
    No-op if the game is not published.
    """
    from handler.database.library_handler import LibraryHandler
    from handler.database.session import async_session_factory
    from models.gog_game import GogGame
    from models.library_file import LibraryFile

    # `gog_id` is the GOG product id; LibraryGame.gog_game_id references the
    # GogGame DB row id, so resolve product id -> GogGame.id first. (Passing the
    # product id straight to get_by_gog_game_id silently matched nothing, which
    # is why the library kept showing loose files instead of the archive.)
    async with async_session_factory() as session:
        res = await session.execute(select(GogGame).where(GogGame.gog_id == gog_id))
        gg = res.scalars().first()
        if not gg:
            return
        gog_db_id = gg.id

    lib = LibraryHandler()
    lib_game = await lib.get_by_gog_game_id(gog_db_id)
    if not lib_game:
        return

    rel_path = os.path.relpath(archive_path, BASE_PATH).replace(os.sep, "/")
    arc_name = os.path.basename(archive_path)

    # Drop this platform's loose game installers (and any prior archive row) -
    # the single .zip supersedes them.
    files = await lib.get_files_for_game(lib_game.id)
    for f in files:
        if f.os == platform and f.file_type == "game" and f.source == "gog":
            await lib.delete_file(f)

    await lib.create_file(LibraryFile(
        library_game_id=lib_game.id,
        filename=arc_name,
        display_name=arc_name,
        file_type="game",
        os=platform,
        size_bytes=size_bytes,
        file_path=rel_path,
        source="gog",
        is_available=True,
    ))
    logger.info("Library: %s archive synced for gog_id=%s (%s)", platform, gog_id, rel_path)


# In-memory snapshot of packaging jobs currently in progress, keyed by event id.
# Packaging runs inside this process and does not survive a restart, so a DB
# table would buy nothing; an in-memory dict lets the download tray rehydrate
# after a page refresh (the WebSocket event alone is lost on reload).
_active_packaging: dict[str, dict] = {}


def active_packaging() -> list[dict]:
    """Snapshot of packaging jobs that are still running (for tray rehydration)."""
    return list(_active_packaging.values())


async def _emit_packaging(
    gog_id: int, title: str, platform: str, status: str, done: int, total: int
) -> None:
    """Push a packaging-progress event to the download tray (best-effort)."""
    payload = {
        "id":           f"pkg-{gog_id}-{platform}",
        "gog_id":       gog_id,
        "game_title":   title,
        "platform":     platform,
        "status":       status,                 # packaging | completed | failed
        "done":         done,
        "total":        total,
        "progress_pct": round(done / total * 100, 1) if total else 0.0,
    }
    # Track only in-progress jobs; drop them once finished so the rehydration
    # endpoint never resurrects a completed/failed job. All mutations run on the
    # event loop thread (direct await or via run_coroutine_threadsafe), so no
    # lock is needed.
    if status == "packaging":
        _active_packaging[payload["id"]] = payload
    else:
        _active_packaging.pop(payload["id"], None)
    try:
        from handler.socket_handler import emit_event
        await emit_event("download:packaging", payload)
    except Exception:
        pass


async def pack_platform(
    gog_id: int, platform: str, src_dir: str, title: str, *, delete_originals: bool
) -> dict | None:
    """Package one platform folder (guarded by a per-platform lock)."""
    if not os.path.isdir(src_dir):
        return None
    archive_name = f"{_sanitize_title(title)}.zip"

    async with _lock_for(gog_id, platform):
        loop  = asyncio.get_running_loop()
        total = len(_packable_files(src_dir))

        # Nothing to bundle and no archive to refresh - stay silent.
        if total == 0 and not os.path.exists(os.path.join(src_dir, archive_name)):
            return None

        # Schedule progress emits from the worker thread onto the event loop.
        def on_progress(done: int, tot: int) -> None:
            try:
                asyncio.run_coroutine_threadsafe(
                    _emit_packaging(gog_id, title, platform, "packaging", done, tot), loop
                )
            except Exception:
                pass

        if total > 0:
            await _emit_packaging(gog_id, title, platform, "packaging", 0, total)

        try:
            result = await loop.run_in_executor(
                None, _pack_dir_sync, src_dir, archive_name, delete_originals, on_progress
            )
        except Exception:
            await _emit_packaging(gog_id, title, platform, "failed", 0, total)
            raise

        if not result:
            return None

        if result.get("noop"):
            # Archive already current on disk, but still reconcile the library so
            # it presents the single zip (repairs games packaged before this).
            await _sync_archive_into_library(
                gog_id, platform, result["archive_path"], result["size_bytes"], title
            )
            if total > 0:
                await _emit_packaging(gog_id, title, platform, "completed", total, total)
            return result

        await _sync_archive_into_library(
            gog_id, platform, result["archive_path"], result["size_bytes"], title
        )
        await _emit_packaging(
            gog_id, title, platform, "completed", result["file_count"], result["file_count"]
        )
        logger.info(
            "Packaged %s/%s → %s (%d files, %d bytes)",
            title, platform, os.path.basename(result["archive_path"]),
            result["file_count"], result["size_bytes"],
        )
        return result


async def _platform_has_pending_jobs(gog_id: int, platform: str) -> bool:
    """True if any download job for this game+platform is still unfinished."""
    from handler.database.session import async_session_factory

    async with async_session_factory() as session:
        result = await session.execute(
            select(DownloadJob).where(
                DownloadJob.gog_id == gog_id,
                DownloadJob.os_platform == platform,
                DownloadJob.status.in_(_PENDING_STATES),
            )
        )
        return result.scalars().first() is not None


async def maybe_package_after_job(job_id: int) -> None:
    """
    Auto-package hook. Called after a single GOG file download completes.
    Packages the file's platform folder once every file for that platform
    is finished - but only when the feature is enabled.
    """
    if not await packaging_enabled():
        return

    from handler.database.session import async_session_factory

    async with async_session_factory() as session:
        result = await session.execute(select(DownloadJob).where(DownloadJob.id == job_id))
        job = result.scalars().first()
        if not job:
            return
        gog_id      = job.gog_id
        title       = job.game_title
        dest_dir    = job.dest_dir
        os_platform = (job.os_platform or "").lower()
        file_type   = (job.file_type or "").lower()

    # Only OS platform installers get packaged (extras/bonus stay loose).
    if os_platform not in PLATFORMS or file_type in ("bonus", "extras", "extra"):
        return
    if not dest_dir:
        return
    # Wait until every file for this platform is done.
    if await _platform_has_pending_jobs(gog_id, os_platform):
        return

    delete_originals = await delete_originals_enabled()
    await pack_platform(gog_id, os_platform, dest_dir, title, delete_originals=delete_originals)


def packable_platforms(title: str, base_dir: str | None = None) -> list[str]:
    """
    Platforms that would actually produce/refresh an archive (fast, sync).
    Used to tell the user up front whether 'Package now' has anything to do.
    A platform has work when it has >=2 loose files, or >=1 loose file next to
    an existing archive (the new file gets merged in).
    """
    if base_dir is None:
        base_dir = os.path.join(GAMES_PATH, "GOG", _sanitize_title(title))
    archive_name = f"{_sanitize_title(title)}.zip"
    out: list[str] = []
    for platform in PLATFORMS:
        src_dir = os.path.join(base_dir, platform)
        if not os.path.isdir(src_dir):
            continue
        loose = len(_packable_files(src_dir))
        has_archive = os.path.exists(os.path.join(src_dir, archive_name))
        # >=2 loose files -> bundle; an existing archive -> (re)merge and/or
        # reconcile the library so it shows the single zip.
        if loose >= 2 or has_archive:
            out.append(platform)
    return out


async def package_game(gog_id: int, title: str, base_dir: str | None = None) -> dict:
    """
    Manually (re)package every platform folder of an already-downloaded game.
    Used by the 'Package now' admin action. Honours the delete-originals
    setting. Returns a summary of what was packaged / skipped.
    """
    if base_dir is None:
        base_dir = os.path.join(GAMES_PATH, "GOG", _sanitize_title(title))

    delete_originals = await delete_originals_enabled()
    packaged: list[dict] = []
    skipped:  list[str]  = []

    for platform in PLATFORMS:
        src_dir = os.path.join(base_dir, platform)
        if not os.path.isdir(src_dir):
            continue
        if len(_packable_files(src_dir)) < 2 and not os.path.exists(
            os.path.join(src_dir, f"{_sanitize_title(title)}.zip")
        ):
            # 0-1 loose files and no existing archive: zipping gains nothing.
            skipped.append(platform)
            continue
        result = await pack_platform(
            gog_id, platform, src_dir, title, delete_originals=delete_originals
        )
        if result and not result.get("noop"):
            packaged.append({
                "platform": platform,
                "archive": os.path.basename(result["archive_path"]),
                "size_bytes": result["size_bytes"],
                "file_count": result["file_count"],
            })
        else:
            skipped.append(platform)

    return {"packaged": packaged, "skipped": skipped}
