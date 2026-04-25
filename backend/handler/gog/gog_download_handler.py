"""
GogDownloadHandler - resolves GOG download URLs and streams files to disk.

Flow:
  1. get_download_options(gog_id)  → available installers + bonus content
  2. create_job(...)               → stores job record, returns id
  3. enqueue(job_id)               → starts or queues download
  4. execute_job(job_id, resume_from)
       a. resolve_downlink()        → CDN URL (handles 302 redirect OR JSON)
       b. extract real filename from CDN URL → update job record
       c. stream file with optional Range header (for resume)

GOG downlink endpoints respond with either:
  - HTTP 302  →  Location header contains CDN URL
  - HTTP 200  →  JSON body: {"downlink": "https://...cdn..."}
We MUST use follow_redirects=False to detect the redirect correctly;
following it would land on a CDN binary, not JSON.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from urllib.parse import urlparse, unquote

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config import BASE_PATH, GAMES_PATH
from decorators.database import begin_session
from handler.database.base_handler import DBBaseHandler
from handler.gog.gog_auth_handler import _HDRS, gog_auth_handler
from models.download_job import DownloadJob

logger = logging.getLogger(__name__)

GOG_PRODUCTS_URL = "https://api.gog.com/products/{gog_id}?expand=downloads"

# Language code → display name map (most common GOG languages)
LANG_NAMES: dict[str, str] = {
    "en":     "English",
    "de":     "German",
    "fr":     "French",
    "es":     "Spanish",
    "es-419": "Spanish (Latin America)",
    "it":     "Italian",
    "pt":     "Portuguese",
    "pt-BR":  "Portuguese (Brazil)",
    "ru":     "Russian",
    "pl":     "Polish",
    "nl":     "Dutch",
    "cs":     "Czech",
    "hu":     "Hungarian",
    "ro":     "Romanian",
    "sk":     "Slovak",
    "tr":     "Turkish",
    "zh":     "Chinese (Simplified)",
    "zh-Hans":"Chinese (Simplified)",
    "zh-Hant":"Chinese (Traditional)",
    "ko":     "Korean",
    "ja":     "Japanese",
    "uk":     "Ukrainian",
    "sv":     "Swedish",
    "no":     "Norwegian",
    "da":     "Danish",
    "fi":     "Finnish",
    "gog-all":"All Languages",
    "multi":  "Multi-language",
}


def _md5_sync(path: str) -> str:
    """Compute MD5 of a file synchronously (run in thread pool)."""
    h = hashlib.md5()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


async def _fetch_cdn_md5(cdn_url: str) -> str:
    """
    GOG CDN serves an XML sidecar at <cdn_url>.xml that contains the MD5 hash.
    Example: https://cdn.gog.com/.../setup_game_1.0.exe.xml
    Response looks like: <file md5="abc123..." .../>

    Returns the MD5 hex string, or "" if not found / unreachable.
    """
    xml_url = cdn_url.split("?")[0] + ".xml"   # strip query params, append .xml
    try:
        async with httpx.AsyncClient(headers=_HDRS, follow_redirects=True, timeout=15) as client:
            resp = await client.get(xml_url)
        if resp.status_code != 200:
            return ""
        # Parse md5 attribute from XML - avoid full XML parser for speed
        m = re.search(r'\bmd5\s*=\s*["\']([0-9a-fA-F]{32})["\']', resp.text)
        return m.group(1).lower() if m else ""
    except Exception:
        return ""


async def _md5_async(path: str) -> str:
    """Compute MD5 without blocking the event loop."""
    loop = asyncio.get_running_loop()
    with ThreadPoolExecutor(max_workers=1) as pool:
        return await loop.run_in_executor(pool, _md5_sync, path)


def sanitize_title(title: str) -> str:
    """Convert a game title to a safe directory name."""
    title = unicodedata.normalize("NFKD", title)
    title = title.encode("ascii", errors="ignore").decode("ascii")
    title = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", title)
    title = re.sub(r"[_\s]+", " ", title).strip()
    title = title.rstrip(". ")
    return title or "Unknown_Game"


async def _on_file_downloaded(job_id: int) -> None:
    """Post-completion hook: mark GogGame.is_downloaded and sync the file into LibraryGame."""
    try:
        from handler.database.session import async_session_factory as _sf
        from handler.database.library_handler import LibraryHandler
        from models.gog_game import GogGame
        from models.library_file import LibraryFile
        from sqlalchemy import select as _sel

        # Load the completed job
        async with _sf() as session:
            result = await session.execute(_sel(DownloadJob).where(DownloadJob.id == job_id))
            job = result.scalars().first()
            if not job or job.status != "completed":
                return
            gog_id_val  = job.gog_id
            dest_path   = job.dest_path
            os_platform = (job.os_platform or "").lower()
            file_type   = job.file_type or "installer"
            file_name   = job.file_name

        # Map to standard tags
        os_map = {
            "windows": "windows", "win": "windows", "win32": "windows", "win64": "windows",
            "mac": "mac", "macos": "mac", "osx": "mac",
            "linux": "linux",
        }
        os_tag = os_map.get(os_platform, "all")
        ft_map = {"bonus": "extra", "extras": "extra", "extra": "extra", "dlc": "dlc"}
        file_type_tag = ft_map.get(file_type, "game")

        # Update GogGame.is_downloaded
        async with _sf() as session:
            async with session.begin():
                result = await session.execute(_sel(GogGame).where(GogGame.gog_id == gog_id_val))
                gg = result.scalar_one_or_none()
                if not gg:
                    return
                gg.is_downloaded = True
                if dest_path:
                    gg.download_path = os.path.dirname(dest_path)
                gog_db_id = gg.id

        # Add file to LibraryGame if this game is already published
        if not dest_path or not os.path.exists(dest_path):
            return

        lib = LibraryHandler()
        lib_game = await lib.get_by_gog_game_id(gog_db_id)
        if not lib_game:
            return

        rel_path = os.path.relpath(dest_path, BASE_PATH).replace(os.sep, "/")
        existing_files = await lib.get_files_for_game(lib_game.id)
        if rel_path in {f.file_path for f in existing_files}:
            return  # already registered

        try:
            file_size = os.path.getsize(dest_path)
        except OSError:
            file_size = 0

        await lib.create_file(LibraryFile(
            library_game_id=lib_game.id,
            filename=file_name,
            display_name=file_name,
            file_type=file_type_tag,
            os=os_tag,
            size_bytes=file_size,
            file_path=rel_path,
            source="gog",
            is_available=True,
        ))
        logger.info("Auto-synced file to library: %s → LibraryGame id=%s", rel_path, lib_game.id)

    except Exception:
        logger.exception("_on_file_downloaded failed for job_id=%s", job_id)


def game_dest_dir(title: str, file_type: str = "installer", os_platform: str | None = None) -> str:
    """
    Return destination directory for a download.

    Installers  → /data/games/GOG/{title}/{os}/      e.g. .../windows/
    Bonus/extras → /data/games/GOG/{title}/extras/
    Unknown type → /data/games/GOG/{title}/
    """
    base = os.path.join(GAMES_PATH, "GOG", sanitize_title(title))
    if file_type in ("bonus", "extras", "extra"):
        return os.path.join(base, "extras")
    if os_platform:
        return os.path.join(base, os_platform.lower())
    return base


def filename_from_cdn_url(cdn_url: str) -> str:
    """
    Extract real filename from CDN URL.
    GOG CDN URLs look like:
      https://gog-cdn-fastly.gog.com/.../setup_game_1.0.exe?...
    We strip query string and take the last path segment.
    """
    try:
        path = urlparse(cdn_url).path          # e.g. /path/to/setup_game_1.3.1_%2862814%29.bin
        name = path.rstrip("/").split("/")[-1] # last segment
        name = unquote(name)                   # decode %28 → ( etc.
        if name and "." in name:
            return name
    except Exception:
        pass
    return ""


# ── In-process download queue ──────────────────────────────────────────────
# Supports N parallel downloads.  _max_parallel can be changed at runtime.

_max_parallel:  int = 1
_active_tasks:  dict[int, asyncio.Task] = {}   # job_id → Task
_pending_queue: list[tuple[int, int]]   = []   # (job_id, resume_from)


def _active_count() -> int:
    return sum(1 for t in _active_tasks.values() if not t.done())


def get_max_parallel() -> int:
    """Return the current concurrency limit."""
    return _max_parallel


def set_max_parallel(n: int) -> None:
    """Change concurrency limit (1–10). Takes effect for next launches."""
    global _max_parallel
    _max_parallel = max(1, min(n, 10))
    logger.info("Download concurrency set to %d", _max_parallel)
    # If slots opened up, start pending jobs immediately
    _try_launch_pending(gog_download_handler)


class GogDownloadHandler(DBBaseHandler):
    model = DownloadJob

    @staticmethod
    async def _emit_job_status(job: DownloadJob) -> None:
        """Emit WebSocket event for job status change."""
        try:
            from handler.socket_handler import emit_event
            await emit_event("download:progress", {
                "id": job.id,
                "gog_id": job.gog_id,
                "game_title": job.game_title,
                "file_name": job.file_name,
                "status": job.status,
                "progress_pct": job.progress_pct,
                "downloaded_size": job.downloaded_size,
                "total_size": job.total_size,
                "speed_bps": job.speed_bps,
            })
        except Exception:
            pass

    # ── 1. Fetch download options ────────────────────────────────────────────

    async def get_download_options(self, gog_id: int, owner_user_id: int | None = None) -> dict:
        """
        Calls GOG API and returns structured installer + bonus options.

        Each file entry includes:
          "id"       - GOG internal file identifier (e.g. "en1installer")
          "size"     - declared size in bytes (may be 0 if GOG omits it)
          "downlink" - URL to resolve for actual CDN link

        owner_user_id: use this user's GOG token. None = admin's token.
        """
        token = await gog_auth_handler.get_access_token(user_id=owner_user_id)
        if not token:
            raise ValueError("GOG account not connected")

        headers = {**_HDRS, "Authorization": f"Bearer {token}"}
        url = GOG_PRODUCTS_URL.format(gog_id=gog_id)

        async with httpx.AsyncClient(
            headers=headers, follow_redirects=True, timeout=30
        ) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()

        downloads     = data.get("downloads") or {}
        raw_installers = downloads.get("installers") or []
        raw_bonus      = downloads.get("bonus_content") or []

        installers: list[dict] = []
        for inst in raw_installers:
            lang_code = inst.get("language", "")
            files = [
                {
                    "id":       f.get("id", ""),
                    "size":     int(f.get("size", 0)),
                    "downlink": f.get("downlink", ""),
                    "md5":      f.get("md5") or "",
                }
                for f in (inst.get("files") or [])
            ]
            installers.append({
                "id":            inst.get("id", ""),
                "name":          inst.get("name", ""),
                "os":            inst.get("os", ""),
                "language":      lang_code,
                "language_full": LANG_NAMES.get(lang_code, lang_code.capitalize()),
                "version":       inst.get("version") or "",
                "total_size":    int(inst.get("total_size", 0)),
                "files":         files,
            })

        bonus: list[dict] = []
        for b in raw_bonus:
            # Build files list from the nested files array
            files = [
                {
                    "id":       str(f.get("id") or ""),
                    "size":     int(f.get("size") or 0),
                    "downlink": str(f.get("downlink") or ""),
                    "md5":      str(f.get("md5") or ""),
                }
                for f in (b.get("files") or [])
                if f.get("downlink")   # skip entries with null/empty downlink
            ]

            # Some GOG bonus items don't have a files[] array - they carry
            # the downlink directly at the bonus level (older API format).
            if not files:
                top_link = b.get("downlink") or b.get("url") or ""
                if top_link:
                    files = [{
                        "id":       str(b.get("id") or ""),
                        "size":     int(b.get("total_size") or 0),
                        "downlink": str(top_link),
                    }]

            bonus.append({
                "id":         str(b.get("id") or ""),
                "name":       b.get("name") or "",
                "type":       b.get("type") or "",
                "total_size": int(b.get("total_size") or 0),
                "files":      files,
            })

        return {"installers": installers, "bonus_content": bonus}

    # ── 2. Resolve downlink → actual CDN URL ─────────────────────────────────

    async def resolve_downlink(self, downlink_path: str, owner_user_id: int | None = None) -> str:
        """
        Resolves a GOG downlink path/URL to the actual CDN download URL.

        GOG downlink endpoint can respond in two ways:
          HTTP 302  →  Location header  (older pattern)
          HTTP 200  →  JSON { "downlink": "https://cdn..." }

        IMPORTANT: must use follow_redirects=False - if we follow the 302
        we land directly on the CDN binary and cannot parse it as JSON.

        owner_user_id: use this user's GOG token. None = admin's token.
        """
        token = await gog_auth_handler.get_access_token(user_id=owner_user_id)
        if not token:
            raise ValueError("GOG account not connected")

        # Normalise to full URL
        if downlink_path.startswith("http"):
            url = downlink_path
        else:
            url = "https://api.gog.com" + downlink_path

        # GOG downlink API requires the access_token as query param
        sep = "&" if "?" in url else "?"
        url_with_token = f"{url}{sep}access_token={token}"

        headers = {**_HDRS, "Authorization": f"Bearer {token}"}

        async with httpx.AsyncClient(
            headers=headers,
            follow_redirects=False,   # ← CRITICAL: catch the redirect ourselves
            timeout=30,
        ) as client:
            resp = await client.get(url_with_token)

        # Handle 302 redirect (Location header is the CDN URL)
        if resp.status_code in (301, 302, 303, 307, 308):
            cdn_url = resp.headers.get("location", "")
            if not cdn_url:
                raise ValueError("GOG downlink redirect had no Location header")
            return cdn_url

        # Handle 200 JSON response
        resp.raise_for_status()
        try:
            data = resp.json()
        except Exception:
            raise ValueError(
                f"GOG downlink returned non-JSON (status {resp.status_code}): "
                f"{resp.text[:200]}"
            )
        cdn_url = data.get("downlink") or data.get("url") or ""
        if not cdn_url:
            raise ValueError(f"GOG downlink JSON had no URL field: {data}")
        return cdn_url

    # ── 3. CRUD for jobs ─────────────────────────────────────────────────────

    @begin_session
    async def create_job(
        self,
        gog_id: int,
        game_title: str,
        file_name: str,          # placeholder - overwritten with real name after CDN resolve
        file_type: str,
        os_platform: str | None,
        language: str | None,
        version: str | None,
        installer_id: str | None,
        file_id: str | None,
        downlink_url: str,
        total_size: int | None,
        verify_checksum: bool = False,
        checksum: str | None = None,
        *,
        session: AsyncSession = None,
    ) -> DownloadJob:
        dest_dir  = game_dest_dir(game_title, file_type=file_type, os_platform=os_platform)
        dest_path = os.path.join(dest_dir, file_name)  # will be updated after CDN resolve

        job = DownloadJob(
            gog_id=gog_id,
            game_title=game_title,
            file_name=file_name,
            file_type=file_type,
            os_platform=os_platform,
            language=language,
            version=version,
            installer_id=installer_id,
            file_id=file_id,
            downlink_url=downlink_url,
            total_size=total_size,
            dest_dir=dest_dir,
            dest_path=dest_path,
            status="queued",
            verify_checksum=verify_checksum,
            checksum=checksum or None,
            checksum_status=None,
        )
        session.add(job)
        await session.flush()
        logger.info("Created DownloadJob id=%s gog_id=%s file=%s", job.id, gog_id, file_name)
        return job

    @begin_session
    async def get_job(self, job_id: int, *, session: AsyncSession = None) -> DownloadJob | None:
        result = await session.execute(
            select(DownloadJob).where(DownloadJob.id == job_id)
        )
        return result.scalars().first()

    @begin_session
    async def list_jobs(self, *, session: AsyncSession = None) -> list[DownloadJob]:
        result = await session.execute(
            select(DownloadJob).order_by(DownloadJob.created_at.desc())
        )
        return list(result.scalars().all())

    @begin_session
    async def cancel_job(self, job_id: int, *, session: AsyncSession = None) -> bool:
        """Cancel an active or queued download. Marks status=cancelled."""
        result = await session.execute(
            select(DownloadJob).where(DownloadJob.id == job_id)
        )
        job = result.scalars().first()
        if not job:
            return False

        # Cancel running asyncio task if active
        task = _active_tasks.get(job_id)
        if task and not task.done():
            task.cancel()

        # Remove from pending queue
        _pending_queue[:] = [(jid, rf) for jid, rf in _pending_queue if jid != job_id]

        job.status      = "cancelled"
        job.finished_at = datetime.now(timezone.utc)
        job.speed_bps   = 0
        await self._emit_job_status(job)
        return True

    @begin_session
    async def pause_job(self, job_id: int, *, session: AsyncSession = None) -> bool:
        """
        Pause an active download: cancel the asyncio task and set status=paused.
        downloaded_size is preserved so resume can use Range header.
        """
        result = await session.execute(
            select(DownloadJob).where(DownloadJob.id == job_id)
        )
        job = result.scalars().first()
        if not job:
            return False
        if job.status not in ("downloading", "queued"):
            return False

        # Cancel the running task (triggers CancelledError in execute_job)
        task = _active_tasks.get(job_id)
        if task and not task.done():
            task.cancel()
            await asyncio.sleep(0.1)

        # Remove from pending queue
        _pending_queue[:] = [(jid, rf) for jid, rf in _pending_queue if jid != job_id]

        job.status    = "paused"
        job.speed_bps = 0
        await self._emit_job_status(job)
        return True

    @begin_session
    async def resume_job(self, job_id: int, *, session: AsyncSession = None) -> bool:
        """Resume a paused download using HTTP Range header."""
        result = await session.execute(
            select(DownloadJob).where(DownloadJob.id == job_id)
        )
        job = result.scalars().first()
        if not job or job.status != "paused":
            return False

        resume_from = job.downloaded_size or 0
        job.status  = "queued"
        # Flush before launching so the new status is visible immediately
        await session.flush()

        self.enqueue(job_id, resume_from=resume_from)
        return True

    @begin_session
    async def delete_job(self, job_id: int, *, session: AsyncSession = None) -> bool:
        result = await session.execute(
            select(DownloadJob).where(DownloadJob.id == job_id)
        )
        job = result.scalars().first()
        if not job:
            return False
        await session.delete(job)
        return True

    # ── 4. Actual download execution ─────────────────────────────────────────

    async def execute_job(self, job_id: int, resume_from: int = 0) -> None:
        """
        Resolve CDN URL, determine real filename, stream file to disk.
        Updates DB: status, file_name, dest_path, downloaded_size, speed_bps, progress_pct.

        resume_from > 0  →  sends Range: bytes=N- header (HTTP resume).
        """
        from handler.database.session import async_session_factory

        async def _update(session: AsyncSession, **kwargs) -> None:
            result = await session.execute(
                select(DownloadJob).where(DownloadJob.id == job_id)
            )
            job = result.scalars().first()
            if job:
                for k, v in kwargs.items():
                    setattr(job, k, v)
                # Emit WebSocket event for real-time UI updates
                try:
                    from handler.socket_handler import emit_event
                    await emit_event("download:progress", {
                        "id": job.id,
                        "gog_id": job.gog_id,
                        "game_title": job.game_title,
                        "file_name": job.file_name,
                        "status": job.status,
                        "progress_pct": job.progress_pct,
                        "downloaded_size": job.downloaded_size,
                        "total_size": job.total_size,
                        "speed_bps": job.speed_bps,
                    })
                except Exception:
                    pass  # don't break download on socket failure

        # Mark as downloading
        async with async_session_factory() as session:
            async with session.begin():
                await _update(session, status="downloading", started_at=datetime.now(timezone.utc))

        try:
            # Load job state
            async with async_session_factory() as session:
                async with session.begin():
                    result = await session.execute(
                        select(DownloadJob).where(DownloadJob.id == job_id)
                    )
                    job = result.scalars().first()
                    if not job or job.status == "cancelled":
                        return
                    downlink         = job.downlink_url
                    dest_dir         = job.dest_dir
                    dest_path        = job.dest_path
                    file_name        = job.file_name
                    total_size       = job.total_size
                    verify_checksum  = job.verify_checksum
                    expected_md5     = job.checksum
                    gog_id_val_for_owner = job.gog_id

            # Look up the game's owner so we use their GOG token for download
            _owner_user_id: int | None = None
            try:
                from models.gog_game import GogGame as _GG
                async with async_session_factory() as session:
                    async with session.begin():
                        row = await session.execute(
                            select(_GG.owner_user_id).where(_GG.gog_id == gog_id_val_for_owner).limit(1)
                        )
                        _owner_user_id = row.scalar_one_or_none()
            except Exception:
                pass  # fallback to admin token

            # ── Step 1: Resolve downlink → CDN URL ───────────────────────────
            logger.info("Resolving downlink for job %s …", job_id)
            cdn_url = await self.resolve_downlink(downlink, owner_user_id=_owner_user_id)
            logger.info("CDN URL for job %s: %.80s", job_id, cdn_url)

            # ── Step 2: Extract REAL filename from CDN URL ────────────────────
            # GOG internal file IDs (e.g. "en1installer", "en2installer") are NOT
            # filenames. The real name (e.g. "setup_game_1.0.exe") lives in the CDN path.
            real_name = filename_from_cdn_url(cdn_url)
            if real_name and real_name != file_name:
                dest_path = os.path.join(dest_dir, real_name)
                logger.info("Real filename for job %s: %s", job_id, real_name)
                async with async_session_factory() as session:
                    async with session.begin():
                        await _update(session, file_name=real_name, dest_path=dest_path)
                file_name = real_name

            # ── Step 2b: Fetch MD5 from CDN XML sidecar (if not from API) ────────
            # GOG CDN serves <url>.xml with md5 attribute when the products API
            # doesn't include it (common for offline installers & bonus content).
            if verify_checksum and not expected_md5:
                cdn_md5 = await _fetch_cdn_md5(cdn_url)
                if cdn_md5:
                    expected_md5 = cdn_md5
                    async with async_session_factory() as session:
                        async with session.begin():
                            await _update(session, checksum=cdn_md5)
                    logger.info("Job %s: got MD5 from CDN XML: %s", job_id, cdn_md5)

            # ── Step 3: Create destination directory ──────────────────────────
            os.makedirs(dest_dir, exist_ok=True)

            # ── Step 4: Stream to disk ────────────────────────────────────────
            token   = await gog_auth_handler.get_access_token(user_id=_owner_user_id)
            headers = {**_HDRS}
            if token:
                headers["Authorization"] = f"Bearer {token}"

            # Support HTTP range resume
            open_mode = "wb"
            downloaded = 0
            if resume_from > 0:
                headers["Range"] = f"bytes={resume_from}-"
                open_mode        = "ab"   # append to existing partial file
                downloaded       = resume_from
                logger.info("Resuming job %s from byte %s", job_id, resume_from)

            last_speed_time  = asyncio.get_running_loop().time()
            last_speed_bytes = downloaded
            last_update_time = asyncio.get_running_loop().time()
            UPDATE_INTERVAL  = 1.5   # seconds between DB writes

            async with httpx.AsyncClient(
                headers=headers,
                follow_redirects=True,
                timeout=httpx.Timeout(connect=30, read=300, write=300, pool=60),
            ) as client:
                async with client.stream("GET", cdn_url) as resp:
                    # 206 = Partial Content (range accepted), 200 = full file
                    if resp.status_code not in (200, 206):
                        resp.raise_for_status()

                    # Update total_size from CDN headers - CDN is authoritative.
                    # The GOG manifest `size` field is often slightly off (compressed
                    # vs raw, outdated metadata, etc.), so we always prefer the actual
                    # Content-Length reported by the CDN response.
                    cl = resp.headers.get("content-length")
                    cr = resp.headers.get("content-range")  # "bytes 500-1000/1234"
                    cdn_size: int | None = None
                    if cr:
                        m = re.search(r"/(\d+)$", cr)
                        if m:
                            cdn_size = int(m.group(1))
                    elif cl:
                        cdn_size = resume_from + int(cl)

                    if cdn_size and cdn_size != total_size:
                        total_size = cdn_size
                        async with async_session_factory() as session:
                            async with session.begin():
                                await _update(session, total_size=total_size)
                    elif cdn_size and not total_size:
                        total_size = cdn_size
                        async with async_session_factory() as session:
                            async with session.begin():
                                await _update(session, total_size=total_size)

                    # MD5 hasher - compute incrementally while streaming,
                    # so no extra I/O pass is needed after download.
                    # We hash whenever verify is on AND we have (or just fetched) an MD5.
                    md5_hasher = hashlib.md5() if (verify_checksum and expected_md5) else None

                    with open(dest_path, open_mode) as fh:
                        async for chunk in resp.aiter_bytes(chunk_size=1024 * 256):
                            fh.write(chunk)
                            downloaded += len(chunk)
                            if md5_hasher:
                                md5_hasher.update(chunk)

                            now     = asyncio.get_running_loop().time()
                            elapsed = now - last_speed_time
                            if elapsed >= 1.0:
                                speed            = (downloaded - last_speed_bytes) / elapsed
                                last_speed_time  = now
                                last_speed_bytes = downloaded
                                pct = (downloaded / total_size * 100.0) if total_size else 0.0

                                if now - last_update_time >= UPDATE_INTERVAL:
                                    last_update_time = now
                                    async with async_session_factory() as session:
                                        async with session.begin():
                                            await _update(
                                                session,
                                                downloaded_size=downloaded,
                                                speed_bps=int(speed),
                                                progress_pct=round(pct, 2),
                                            )

            # ── Completed ────────────────────────────────────────────────────
            pct = (downloaded / total_size * 100.0) if total_size else 100.0
            async with async_session_factory() as session:
                async with session.begin():
                    await _update(
                        session,
                        status="completed",
                        downloaded_size=downloaded,
                        speed_bps=0,
                        progress_pct=round(min(pct, 100.0), 2),
                        finished_at=datetime.now(timezone.utc),
                    )
            logger.info("Download job %s completed: %s (%d bytes)", job_id, file_name, downloaded)

            # ── Step 5: Verify checksum (optional) ───────────────────────────
            # MD5 was computed incrementally during streaming - zero extra I/O.
            # Fallback to file-size check when GOG didn't supply an MD5.
            if verify_checksum:
                if md5_hasher and expected_md5:
                    # MD5 already computed - just compare
                    actual_md5 = md5_hasher.hexdigest()
                    ok = actual_md5.lower() == expected_md5.lower()
                    cstatus = "ok" if ok else "failed"
                    async with async_session_factory() as session:
                        async with session.begin():
                            await _update(session, checksum_status=cstatus)
                    if ok:
                        logger.info("Job %s: MD5 OK (%s)", job_id, actual_md5)
                    else:
                        logger.warning(
                            "Job %s: MD5 MISMATCH - expected=%s actual=%s",
                            job_id, expected_md5, actual_md5,
                        )
                else:
                    # No MD5 from GOG - fallback: compare file size on disk vs CDN size
                    if total_size:
                        try:
                            actual_size = os.path.getsize(dest_path)
                            size_ok = actual_size == total_size
                            cstatus = "size_ok" if size_ok else "size_fail"
                            async with async_session_factory() as session:
                                async with session.begin():
                                    await _update(session, checksum_status=cstatus)
                            if size_ok:
                                logger.info("Job %s: size OK (%d bytes)", job_id, actual_size)
                            else:
                                logger.warning(
                                    "Job %s: size MISMATCH - expected=%d actual=%d",
                                    job_id, total_size, actual_size,
                                )
                        except Exception as exc:
                            logger.warning("Job %s: size check error: %s", job_id, exc)
                            async with async_session_factory() as session:
                                async with session.begin():
                                    await _update(session, checksum_status="skipped")
                    else:
                        async with async_session_factory() as session:
                            async with session.begin():
                                await _update(session, checksum_status="skipped")
                        logger.info("Job %s: checksum skipped (no MD5 or size from GOG)", job_id)

            # Mark game downloaded and sync file into library (best-effort, non-blocking)
            asyncio.create_task(_on_file_downloaded(job_id))

        except asyncio.CancelledError:
            # Don't overwrite "paused" status set by pause_job()
            async with async_session_factory() as session:
                async with session.begin():
                    result = await session.execute(
                        select(DownloadJob).where(DownloadJob.id == job_id)
                    )
                    existing = result.scalars().first()
                    if existing and existing.status not in ("paused", "cancelled"):
                        existing.status      = "cancelled"
                        existing.finished_at = datetime.now(timezone.utc)
                        existing.speed_bps   = 0
            logger.info("Download job %s cancelled/paused", job_id)

        except Exception as exc:
            logger.exception("Download job %s failed: %s", job_id, exc)
            async with async_session_factory() as session:
                async with session.begin():
                    await _update(
                        session,
                        status="failed",
                        error_msg=str(exc)[:1024],
                        speed_bps=0,
                        finished_at=datetime.now(timezone.utc),
                    )

        finally:
            # Remove this task from the active dict, then try to start pending jobs
            _active_tasks.pop(job_id, None)
            _try_launch_pending(gog_download_handler)

    # ── Queue management ──────────────────────────────────────────────────────

    def enqueue(self, job_id: int, resume_from: int = 0) -> None:
        """Start immediately if a slot is free, otherwise add to pending queue."""
        if _active_count() < _max_parallel:
            _launch(job_id, self, resume_from)
        else:
            _pending_queue.append((job_id, resume_from))
            logger.info(
                "Job %s queued (running=%d, max=%d)",
                job_id, _active_count(), _max_parallel,
            )


def _launch(job_id: int, handler: GogDownloadHandler, resume_from: int = 0) -> None:
    """Create an asyncio Task for execute_job and track it in _active_tasks."""
    loop = asyncio.get_running_loop()
    task = loop.create_task(handler.execute_job(job_id, resume_from=resume_from))
    _active_tasks[job_id] = task
    logger.info(
        "Launched download job %s (resume_from=%s) - active=%d/%d",
        job_id, resume_from, _active_count(), _max_parallel,
    )


def _try_launch_pending(handler: GogDownloadHandler) -> None:
    """Launch as many pending jobs as available concurrency slots allow."""
    while _active_count() < _max_parallel and _pending_queue:
        job_id, resume_from = _pending_queue.pop(0)
        _launch(job_id, handler, resume_from)


gog_download_handler = GogDownloadHandler()
