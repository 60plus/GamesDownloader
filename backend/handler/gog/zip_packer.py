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

from sqlalchemy import and_, or_, select

from config import BASE_PATH, GAMES_PATH
from handler.config.config_handler import config_handler
from models.download_job import PENDING_STATES as _PENDING_STATES, DownloadJob

logger = logging.getLogger(__name__)

# OS platform subfolders we package. "extras" is intentionally excluded.
PLATFORMS: tuple[str, ...] = ("windows", "mac", "linux")

# Config keys
KEY_ENABLED          = "gog_zip_per_platform"      # bool - master switch
KEY_DELETE_ORIGINALS = "gog_zip_delete_originals"  # bool - remove loose files after zipping
KEY_INCLUDE_EXTRAS   = "gog_zip_include_extras"     # bool - also auto-package extras/dlc folders

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


async def include_extras_enabled() -> bool:
    """When on, GOG auto-packaging also bundles the game's extras/dlc folders
    (via the generic packer), not just the OS platform installers."""
    return await config_handler.get_bool(KEY_INCLUDE_EXTRAS, default=False)


def _sanitize_title(title: str) -> str:
    # Lazy import to avoid a circular import at module load time
    # (gog_download_handler imports this module's hook).
    from handler.gog.gog_download_handler import sanitize_title
    return sanitize_title(title)


def _packable_files(directory: str, *, include_archives: bool = False,
                    exclude_name: str | None = None) -> list[str]:
    """Relative posix arcnames of the real files under `directory` (recursive).
    Temp files are always skipped. By default .zip archives are skipped too (so
    GOG packaging never re-includes the archive it is building). With
    `include_archives=True`, content .zip files are kept - custom games whose
    extras/dlc are already zipped still bundle - while the output archive named
    `exclude_name` is always excluded so re-packing is stable.
    """
    out: list[str] = []
    try:
        for root, _dirs, files in os.walk(directory):
            for name in files:
                if name.endswith(".tmp"):
                    continue
                if not include_archives and name.endswith(".zip"):
                    continue
                full = os.path.join(root, name)
                rel = os.path.relpath(full, directory).replace(os.sep, "/")
                # Exclude only the output archive itself, which is always written
                # at the TOP level of `directory` (rel == exclude_name). A file that
                # merely shares that basename inside a subfolder (e.g. a per-platform
                # {Title}.zip when bundling the whole game) is real content and stays.
                if exclude_name and rel == exclude_name:
                    continue
                out.append(rel)
    except OSError:
        return []
    return sorted(out)


def _pack_dir_sync(
    src_dir: str, archive_name: str, delete_originals: bool, on_progress=None,
    *, include_archives: bool = False,
) -> dict | None:
    """
    Blocking: bundle the loose files in `src_dir` (recursively) into
    `src_dir/archive_name`. No compression (ZIP_STORED) - this is a straight
    copy into one container, not a slow archive. MUST run in a thread.

    `include_archives=True` bundles already-zipped content too (excluding the
    output archive) - used by the generic per-group packer for custom games.

    on_progress(done, total) is called after each file so the caller can report
    live progress. Returns {archive_path, size_bytes, file_count} or None.
    """
    archive_path = os.path.join(src_dir, archive_name)
    tmp_path     = archive_path + ".tmp"

    files = _packable_files(src_dir, include_archives=include_archives, exclude_name=archive_name)
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
    from handler.gog.gog_sync_handler import canonical_gog_stmt
    from models.library_file import LibraryFile

    # `gog_id` is the GOG product id; LibraryGame.gog_game_id references the
    # GogGame DB row id, so resolve product id -> GogGame.id first. (Passing the
    # product id straight to get_by_gog_game_id silently matched nothing, which
    # is why the library kept showing loose files instead of the archive.)
    async with async_session_factory() as session:
        res = await session.execute(canonical_gog_stmt(gog_id))
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
        is_archive=True,
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
    """True if any download job for this game+platform is still unfinished.

    A job counts as unfinished while it is downloading/queued/paused AND while it
    is downloaded but its checksum has not settled yet. The download stream marks
    a job "completed" BEFORE MD5 verification runs, so without the second clause a
    sibling file still being verified would let packaging start before its MD5 is
    confirmed.
    """
    from handler.database.session import async_session_factory

    async with async_session_factory() as session:
        result = await session.execute(
            select(DownloadJob).where(
                DownloadJob.gog_id == gog_id,
                DownloadJob.os_platform == platform,
                or_(
                    DownloadJob.status.in_(_PENDING_STATES),
                    and_(
                        DownloadJob.status == "completed",
                        DownloadJob.verify_checksum == True,   # noqa: E712
                        DownloadJob.checksum_status.is_(None),
                    ),
                ),
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
    # Optionally also bundle extras/dlc, but only once the WHOLE game has finished
    # downloading (so a still-downloading bonus file is never packed half-written).
    if await include_extras_enabled() and not await _gog_has_pending_jobs(gog_id):
        await _package_gog_extras(gog_id, delete_originals)


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

    # When enabled, also bundle the game's extras/dlc folders in the same run.
    if await include_extras_enabled():
        await _package_gog_extras(gog_id, delete_originals)

    return {"packaged": packaged, "skipped": skipped}


# ── Generic packaging: any library game (the plugin-facing API) ───────────────
# The functions above stay GOG-specific. Those below drive the SAME per-platform
# primitive (`_pack_dir_sync`) for ANY LibraryGame - GOG, custom, or an admin
# custom-library game - keyed on the game id + its source instead of a gog_id.
# Exposed to plugins/themes via POST /library/games/{id}/package and
# window.__GD__.library.package(gameId).

# Packable groups: (folder-on-disk, output os, output file_type). Platform
# folders bundle into per-platform game archives; the extras/dlc/bonus type
# folders bundle into their own archive (e.g. {Title}-extras.zip) so a game with
# bonus content packs like its OS installers do. "extras" is no longer excluded
# from the on-demand (manual/API) path - only from the GOG auto-package above.
_PLATFORM_GROUPS: tuple[tuple[str, str, str], ...] = tuple((p, p, "game") for p in PLATFORMS)
_TYPE_GROUPS: tuple[tuple[str, str, str], ...] = (
    ("extras", "all", "extra"),
    ("extra",  "all", "extra"),
    ("bonus",  "all", "extra"),
    ("dlc",    "all", "dlc"),
)
_ALL_GROUPS: tuple[tuple[str, str, str], ...] = _PLATFORM_GROUPS + _TYPE_GROUPS
_GROUP_FOLDERS: frozenset[str] = frozenset(f for f, _o, _t in _ALL_GROUPS)


def _resolve_group_dir(base_dir: str, folder: str) -> str | None:
    """Return the actual-cased path of `base_dir/folder` (matched case-insensitively),
    or None when absent. GOG creates lowercase platform folders, but a custom game
    may ship `Extras/` or `DLC/`; on a case-sensitive filesystem (the Linux server)
    a plain lowercase join would miss those and silently skip the group."""
    direct = os.path.join(base_dir, folder)
    if os.path.isdir(direct):
        return direct
    try:
        for entry in os.listdir(base_dir):
            if entry.lower() == folder and os.path.isdir(os.path.join(base_dir, entry)):
                return os.path.join(base_dir, entry)
    except OSError:
        pass
    return None


def _game_base_dir(files, title: str | None = None) -> str | None:
    """Resolve a game's on-disk base folder (the parent of its platform/type
    subfolders) from its LibraryFile paths. Works for any title-first layout that
    files content under `.../{windows|mac|linux|extras|dlc}/...` - GOG and the
    custom title-first scan convention. None when no such folder is present.

    The game's OWN title folder is never treated as a content group (so a game
    literally titled 'DLC' or 'Windows' cannot collapse the base onto a whole
    library root), the group folder must not sit at the very path root, and the
    resolved base must lie strictly inside GAMES_PATH - guards against a crafted or
    unusual file path causing packaging/deletion outside the game's own directory."""
    own = _sanitize_title(title).lower() if title else None
    games_root = os.path.abspath(GAMES_PATH)
    for f in files:
        parts = (f.file_path or "").replace("\\", "/").split("/")
        for i, part in enumerate(parts):
            pl = part.lower()
            if own and pl == own:
                continue  # the title folder itself is not a content group
            if pl in _GROUP_FOLDERS:
                base_rel = "/".join(parts[:i])
                if not base_rel:
                    return None  # group folder at the path root is not a game layout
                base = os.path.abspath(os.path.join(BASE_PATH, base_rel))
                if base == games_root or not (base + os.sep).startswith(games_root + os.sep):
                    return None  # must be a real subfolder strictly under GAMES_PATH
                return base
    return None


def _group_archive_name(title: str, folder: str, out_type: str) -> str:
    """Game files (per platform) -> `{Title}.zip`; extras -> `extras.zip`;
    dlc -> `dlc.zip`."""
    if out_type == "extra":
        return "extras.zip"
    if out_type == "dlc":
        return "dlc.zip"
    return f"{_sanitize_title(title)}.zip"


async def _sync_archive_for_game(
    game_id: int, folder_rel: str, archive_path: str, size_bytes: int,
    source: str, out_os: str, out_type: str,
) -> None:
    """Replace every loose library file physically under `folder_rel` (this game
    + source) with a single archive row. Path-based, so it works for platform
    folders and extras/dlc folders alike, regardless of how the scan tagged each
    file's os/type."""
    from handler.database.library_handler import LibraryHandler
    from models.library_file import LibraryFile

    lib      = LibraryHandler()
    rel_path = os.path.relpath(archive_path, BASE_PATH).replace(os.sep, "/")
    arc_name = os.path.basename(archive_path)
    prefix   = folder_rel.rstrip("/") + "/"

    for f in await lib.get_files_for_game(game_id):
        fp = (f.file_path or "").replace("\\", "/")
        if f.source == source and (fp.startswith(prefix) or fp == rel_path):
            await lib.delete_file(f)

    await lib.create_file(LibraryFile(
        library_game_id=game_id,
        filename=arc_name,
        display_name=arc_name,
        file_type=out_type,
        os=out_os,
        size_bytes=size_bytes,
        file_path=rel_path,
        source=source,
        is_available=True,
        is_archive=True,
    ))
    logger.info("Library: %s/%s archive synced for game_id=%s (%s)", out_type, out_os, game_id, rel_path)


async def _emit_packaging_game(
    game_id: int, title: str, platform: str, status: str, done: int, total: int
) -> None:
    """Packaging-progress event for a generic (non-GOG) job on the same tray
    channel, keyed on the game id so it cannot collide with a GOG job."""
    payload = {
        "id":           f"pkg-g{game_id}-{platform}",
        "game_id":      game_id,
        "game_title":   title,
        "platform":     platform,
        "status":       status,
        "done":         done,
        "total":        total,
        "progress_pct": round(done / total * 100, 1) if total else 0.0,
    }
    if status == "packaging":
        _active_packaging[payload["id"]] = payload
    else:
        _active_packaging.pop(payload["id"], None)
    try:
        from handler.socket_handler import emit_event
        await emit_event("download:packaging", payload)
    except Exception:
        pass


async def _pack_group_for_game(
    game_id: int, source: str, folder: str, out_os: str, out_type: str,
    src_dir: str, title: str, *, delete_originals: bool,
) -> dict | None:
    """Package one folder (a platform folder, or an extras/dlc type folder) for an
    arbitrary library game (locked, with progress events + generic library sync)."""
    if not os.path.isdir(src_dir):
        return None
    archive_name = _group_archive_name(title, folder, out_type)
    folder_rel   = os.path.relpath(src_dir, BASE_PATH).replace(os.sep, "/")

    # Namespace the lock key so a game id can never collide with a gog id lock.
    async with _lock_for(game_id, f"g:{folder}"):
        loop  = asyncio.get_running_loop()
        total = len(_packable_files(src_dir, include_archives=True, exclude_name=archive_name))
        if total == 0 and not os.path.exists(os.path.join(src_dir, archive_name)):
            return None

        def on_progress(done: int, tot: int) -> None:
            try:
                asyncio.run_coroutine_threadsafe(
                    _emit_packaging_game(game_id, title, folder, "packaging", done, tot), loop
                )
            except Exception:
                pass

        if total > 0:
            await _emit_packaging_game(game_id, title, folder, "packaging", 0, total)
        try:
            result = await loop.run_in_executor(
                None,
                lambda: _pack_dir_sync(
                    src_dir, archive_name, delete_originals, on_progress, include_archives=True,
                ),
            )
        except Exception:
            await _emit_packaging_game(game_id, title, folder, "failed", 0, total)
            raise
        if not result:
            return None

        await _sync_archive_for_game(
            game_id, folder_rel, result["archive_path"], result["size_bytes"],
            source, out_os, out_type,
        )
        fc = result.get("file_count", total) or total
        await _emit_packaging_game(game_id, title, folder, "completed", fc, fc)
        logger.info(
            "Packaged game_id=%s %s/%s → %s", game_id, title, folder,
            os.path.basename(result["archive_path"]),
        )
        return result


def _game_packable_groups(base_dir: str, title: str) -> list[tuple[str, str, str]]:
    """Groups (folder, out_os, out_type) worth bundling: a folder with 2+ real
    files (already-zipped content counts; the output archive does not). A single
    file needs no archive and is skipped."""
    out: list[tuple[str, str, str]] = []
    for folder, out_os, out_type in _ALL_GROUPS:
        src_dir = _resolve_group_dir(base_dir, folder)
        if not src_dir:
            continue
        archive_name = _group_archive_name(title, folder, out_type)
        n = len(_packable_files(src_dir, include_archives=True, exclude_name=archive_name))
        if n >= 2:
            out.append((folder, out_os, out_type))
    return out


async def package_library_game(
    game_id: int, *, groups: list[str] | None = None, delete_originals: bool | None = None,
    single_archive: bool = False,
) -> dict:
    """Package a library game's files into archives and sync the library to show
    one download per archive. Per group by default (each OS platform -> {Title}.zip,
    extras -> extras.zip, dlc -> dlc.zip); `groups` limits which groups. With
    `single_archive=True`, EVERY file goes into one combined {Title}.zip instead.
    `delete_originals` overrides the global 'delete loose files' setting. The
    plugin/theme-facing entry point. Returns {packaged, skipped}."""
    from handler.database.library_handler import LibraryHandler

    lib  = LibraryHandler()
    game = await lib.get_by_id(game_id)
    if not game:
        raise ValueError(f"library game {game_id} not found")

    files    = await lib.get_files_for_game(game_id)
    base_dir = _game_base_dir(files, game.title)
    if not base_dir:
        return {"packaged": [], "skipped": [], "reason": "no packable folders"}

    source   = game.source or "custom"
    title    = game.title
    del_orig = (await delete_originals_enabled()) if delete_originals is None else bool(delete_originals)

    # Never pack a GOG game while any of its files are still downloading. The
    # auto-package path already waits for this; the manual/API path must too, or a
    # half-written file could be zipped and (with delete_originals) removed.
    if source == "gog" and getattr(game, "gog_game_id", None):
        from models.gog_game import GogGame
        from handler.database.session import async_session_factory
        async with async_session_factory() as _s:
            _gg = (await _s.execute(
                select(GogGame).where(GogGame.id == game.gog_game_id)
            )).scalars().first()
        if _gg and await _gog_has_pending_jobs(_gg.id):
            return {"packaged": [], "skipped": [], "reason": "download in progress"}

    # "Everything into one archive": bundle the whole base folder into one
    # {Title}.zip and replace every loose file with that single download.
    if single_archive:
        result = await _pack_group_for_game(
            game_id, source, "all", "all", "game", base_dir, title, delete_originals=del_orig,
        )
        if result and not result.get("noop"):
            return {"packaged": [{
                "group": "all", "os": "all", "type": "game",
                "archive": os.path.basename(result["archive_path"]),
                "size_bytes": result["size_bytes"], "file_count": result["file_count"],
            }], "skipped": []}
        return {"packaged": [], "skipped": ["all"]}

    # None = pack every group; an explicit [] = pack nothing (do NOT collapse an
    # empty selection to "all" - that would be a destructive surprise with delete).
    want     = None if groups is None else {g.lower() for g in groups}
    packaged: list[dict] = []
    skipped:  list[str]  = []

    for folder, out_os, out_type in _ALL_GROUPS:
        if want is not None and folder not in want:
            continue
        src_dir = _resolve_group_dir(base_dir, folder)
        if not src_dir:
            continue
        archive_name = _group_archive_name(title, folder, out_type)
        if len(_packable_files(src_dir, include_archives=True, exclude_name=archive_name)) < 2:
            skipped.append(folder)
            continue
        result = await _pack_group_for_game(
            game_id, source, folder, out_os, out_type, src_dir, title,
            delete_originals=del_orig,
        )
        if result and not result.get("noop"):
            packaged.append({
                "group":      folder,
                "os":         out_os,
                "type":       out_type,
                "archive":    os.path.basename(result["archive_path"]),
                "size_bytes": result["size_bytes"],
                "file_count": result["file_count"],
            })
        else:
            skipped.append(folder)

    return {"packaged": packaged, "skipped": skipped}


async def game_packable_platforms(game_id: int) -> list[str]:
    """Fast check: labels of a game's groups that have something to bundle
    (platform folders plus extras/dlc). The Package button shows when non-empty."""
    from handler.database.library_handler import LibraryHandler

    lib  = LibraryHandler()
    game = await lib.get_by_id(game_id)
    if not game:
        return []
    base_dir = _game_base_dir(await lib.get_files_for_game(game_id), game.title)
    if not base_dir:
        return []
    return [folder for folder, _os, _t in _game_packable_groups(base_dir, game.title)]


async def game_single_archivable(game_id: int) -> bool:
    """True if a game has >=2 packable files across all its folders combined - the
    threshold for 'bundle everything into one archive'. The per-group packable check
    (>=2 in a single folder) hides this for a game with one file per OS folder, so
    the single-archive path is gated on this instead."""
    from handler.database.library_handler import LibraryHandler

    lib  = LibraryHandler()
    game = await lib.get_by_id(game_id)
    if not game:
        return False
    base_dir = _game_base_dir(await lib.get_files_for_game(game_id), game.title)
    if not base_dir:
        return False
    archive_name = f"{_sanitize_title(game.title)}.zip"
    return len(_packable_files(base_dir, include_archives=True, exclude_name=archive_name)) >= 2


async def _gog_has_pending_jobs(gog_id: int) -> bool:
    """True if ANY download job for this GOG game is still unfinished (any platform
    or extras), so auto extras-packaging waits until the whole game is downloaded."""
    from handler.database.session import async_session_factory

    async with async_session_factory() as session:
        result = await session.execute(
            select(DownloadJob).where(
                DownloadJob.gog_id == gog_id,
                or_(
                    DownloadJob.status.in_(_PENDING_STATES),
                    and_(
                        DownloadJob.status == "completed",
                        DownloadJob.verify_checksum == True,   # noqa: E712
                        DownloadJob.checksum_status.is_(None),
                    ),
                ),
            )
        )
        return result.scalars().first() is not None


async def _package_gog_extras(gog_id: int, delete_originals: bool) -> None:
    """Bundle a published GOG game's extras/dlc folders via the generic packer
    (path-based sync). No-op until the game is published as a LibraryGame - the
    manual Package button can still bundle extras at any time before then."""
    from handler.database.session import async_session_factory
    from handler.database.library_handler import LibraryHandler
    from handler.gog.gog_sync_handler import canonical_gog_stmt

    async with async_session_factory() as session:
        gg = (await session.execute(canonical_gog_stmt(gog_id))).scalars().first()
        if not gg:
            return
    lib_game = await LibraryHandler().get_by_gog_game_id(gg.id)
    if not lib_game:
        return
    try:
        await package_library_game(
            lib_game.id, groups=["extras", "extra", "bonus", "dlc"],
            delete_originals=delete_originals,
        )
    except Exception:
        logger.exception("GOG extras packaging failed for gog_id=%s", gog_id)
