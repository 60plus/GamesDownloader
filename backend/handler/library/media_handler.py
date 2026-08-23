"""
Library game media downloader.

Downloads cover, background, logo, icon, and screenshots from external URLs
(IGDB, SteamGridDB, RAWG, etc.) to the local resources directory so the
frontend serves them without hitting external CDNs.

Structure:  resources/library/{game_id}/
              cover/cover.{ext}
              background/background.{ext}
              logo/logo.{ext}
              icon/icon.{ext}
              shots/shot_NNN.{ext}
"""

from __future__ import annotations

import logging
from pathlib import Path

from utils.http import fetch_media_bytes

from config import BASE_PATH

logger = logging.getLogger(__name__)

RESOURCES_PATH = Path(BASE_PATH) / "resources" / "library"
COLLECTION_COVERS_PATH = Path(BASE_PATH) / "resources" / "collection-covers"
REQUEST_COVERS_PATH = Path(BASE_PATH) / "resources" / "request-covers"

_HDRS = {
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept":          "image/webp,image/avif,image/*,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def _game_dir(game_id: int) -> Path:
    d = RESOURCES_PATH / str(game_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _ext_from(url: str, content_type: str = "") -> str:
    ct = content_type.lower()
    if "webp" in ct:  return ".webp"
    if "png"  in ct:  return ".png"
    if "gif"  in ct:  return ".gif"
    url_l = url.lower().split("?")[0]
    if ".png"  in url_l: return ".png"
    if ".webp" in url_l: return ".webp"
    if ".gif"  in url_l: return ".gif"
    return ".jpg"


def _is_external(url: str | None) -> bool:
    """Check if a path is an external URL (not local resource)."""
    if not url:
        return False
    return url.startswith("http://") or url.startswith("https://")


async def _download(url: str, dest: Path) -> bool:
    """Download a URL to a file. Returns True on success."""
    try:
        content, _ctype = await fetch_media_bytes(url, headers=_HDRS, timeout=30)
        dest.write_bytes(content)
        return True
    except Exception as exc:
        logger.warning("Download failed %s: %s", url, exc)
        return False


async def download_request_cover(request_id: int, url: str | None) -> str | None:
    """Download a game request's suggested cover -> resources/request-covers/.

    The suggestion's URL comes straight out of a scraper search. A ScreenScraper
    one carries ssid/sspassword/devpassword in its query string, so rendering it
    in an <img> sent the server's scraper password to screenscraper.fr from every
    admin's browser and left it in history and DevTools. Fetching it here once,
    server-side, keeps the credential on the server and serves the art locally
    like every other cover.

    Returns the local path, or None when there is nothing usable to store.
    """
    # The picked suggestion now arrives as an opaque /api/media/proxy URL, which
    # is neither local nor external - resolve it back to the real scraper URL so
    # the _is_external gate lets it through and we fetch it server-side.
    from utils.media_proxy import resolve_proxy_url
    url = resolve_proxy_url(url)
    if not _is_external(url):
        return url  # already local, or nothing
    REQUEST_COVERS_PATH.mkdir(parents=True, exist_ok=True)
    try:
        content, ctype = await fetch_media_bytes(url, headers=_HDRS, timeout=20)
        ext = _ext_from(url, ctype)
        dest = REQUEST_COVERS_PATH / f"{request_id}{ext}"
        dest.write_bytes(content)
        return f"/resources/request-covers/{request_id}{ext}"
    except Exception as exc:
        # A cover is decoration; a request without one is fine. What must not
        # happen is falling back to the remote URL.
        logger.warning("Request cover download failed id=%s: %s", request_id, exc)
        return None


async def download_cover(game_id: int, url: str, overwrite: bool = False) -> str | None:
    """Download cover → resources/library/{id}/cover/cover.ext"""
    if not _is_external(url):
        return url  # already local
    gdir = _game_dir(game_id)
    cover_dir = gdir / "cover"
    cover_dir.mkdir(exist_ok=True)

    if not overwrite:
        for ext in (".jpg", ".png", ".webp", ".gif"):
            p = cover_dir / f"cover{ext}"
            if p.exists() and p.stat().st_size > 0:
                return f"/resources/library/{game_id}/cover/cover{ext}"

    try:
        content, ctype = await fetch_media_bytes(url, headers=_HDRS, timeout=30)
        ext = _ext_from(url, ctype)
        dest = cover_dir / f"cover{ext}"
        dest.write_bytes(content)
        logger.debug("Cover downloaded for game_id=%s → %s", game_id, dest)
        return f"/resources/library/{game_id}/cover/cover{ext}"
    except Exception as exc:
        logger.warning("Cover download failed game_id=%s url=%s: %s", game_id, url, exc)
        return None


async def download_background(game_id: int, url: str, overwrite: bool = False) -> str | None:
    """Download background → resources/library/{id}/background/background.ext"""
    if not _is_external(url):
        return url
    gdir = _game_dir(game_id)
    bg_dir = gdir / "background"
    bg_dir.mkdir(exist_ok=True)

    if not overwrite:
        for ext in (".jpg", ".png", ".webp"):
            p = bg_dir / f"background{ext}"
            if p.exists() and p.stat().st_size > 0:
                return f"/resources/library/{game_id}/background/background{ext}"

    try:
        content, ctype = await fetch_media_bytes(url, headers=_HDRS, timeout=30)
        ext = _ext_from(url, ctype)
        dest = bg_dir / f"background{ext}"
        dest.write_bytes(content)
        return f"/resources/library/{game_id}/background/background{ext}"
    except Exception as exc:
        logger.warning("Background download failed game_id=%s: %s", game_id, exc)
        return None


async def download_logo(game_id: int, url: str, overwrite: bool = False) -> str | None:
    """Download logo → resources/library/{id}/logo/logo.ext"""
    if not _is_external(url):
        return url
    gdir = _game_dir(game_id)
    logo_dir = gdir / "logo"
    logo_dir.mkdir(exist_ok=True)

    if not overwrite:
        for ext in (".png", ".webp", ".jpg"):
            p = logo_dir / f"logo{ext}"
            if p.exists() and p.stat().st_size > 0:
                return f"/resources/library/{game_id}/logo/logo{ext}"

    try:
        content, ctype = await fetch_media_bytes(url, headers=_HDRS, timeout=30)
        ext = _ext_from(url, ctype)
        dest = logo_dir / f"logo{ext}"
        dest.write_bytes(content)
        return f"/resources/library/{game_id}/logo/logo{ext}"
    except Exception as exc:
        logger.warning("Logo download failed game_id=%s: %s", game_id, exc)
        return None


async def download_icon(game_id: int, url: str, overwrite: bool = False) -> str | None:
    """Download icon → resources/library/{id}/icon/icon.ext"""
    if not _is_external(url):
        return url
    gdir = _game_dir(game_id)
    icon_dir = gdir / "icon"
    icon_dir.mkdir(exist_ok=True)

    if not overwrite:
        for ext in (".png", ".webp", ".jpg", ".ico"):
            p = icon_dir / f"icon{ext}"
            if p.exists() and p.stat().st_size > 0:
                return f"/resources/library/{game_id}/icon/icon{ext}"

    try:
        content, ctype = await fetch_media_bytes(url, headers=_HDRS, timeout=30)
        ext = _ext_from(url, ctype)
        dest = icon_dir / f"icon{ext}"
        dest.write_bytes(content)
        return f"/resources/library/{game_id}/icon/icon{ext}"
    except Exception as exc:
        logger.warning("Icon download failed game_id=%s: %s", game_id, exc)
        return None


async def download_screenshots(game_id: int, urls: list[str], overwrite: bool = False) -> list[str]:
    """Download screenshots → resources/library/{id}/shots/shot_NNN.ext
    Returns list of local paths for successfully downloaded screenshots.
    """
    if not urls:
        return []
    gdir = _game_dir(game_id)
    shots_dir = gdir / "shots"
    shots_dir.mkdir(exist_ok=True)

    results: list[str] = []
    for i, url in enumerate(urls):
        if not _is_external(url):
            results.append(url)
            continue

        # Check cache
        if not overwrite:
            cached = False
            for ext in (".jpg", ".png", ".webp"):
                p = shots_dir / f"shot_{i:03d}{ext}"
                if p.exists() and p.stat().st_size > 0:
                    results.append(f"/resources/library/{game_id}/shots/shot_{i:03d}{ext}")
                    cached = True
                    break
            if cached:
                continue

        try:
            content, ctype = await fetch_media_bytes(url, headers=_HDRS, timeout=30)
            ext = _ext_from(url, ctype)
            dest = shots_dir / f"shot_{i:03d}{ext}"
            dest.write_bytes(content)
            results.append(f"/resources/library/{game_id}/shots/shot_{i:03d}{ext}")
        except Exception as exc:
            logger.warning("Screenshot %d download failed game_id=%s: %s", i, game_id, exc)
            results.append(url)  # keep external URL as fallback

    return results


_VIDEO_EXTS = (".mp4", ".webm")


def _clear_video_dir(game_id: int) -> Path:
    """Video directory for a game with any previous local copy removed."""
    vdir = _game_dir(game_id) / "video"
    vdir.mkdir(exist_ok=True)
    for old in vdir.glob("video.*"):
        try:
            old.unlink()
        except OSError:
            pass
    return vdir


def _video_format(quality: str) -> str:
    """yt-dlp format string for the requested quality, falling back down the
    ladder (e.g. 1080 -> 720 -> 480 -> whatever is left) when the source has
    no stream at that height. Merged streams need ffmpeg (in the image)."""
    if quality == "best":
        return "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best"
    try:
        want = int(quality)
    except ValueError:
        want = 1080
    ladder = [h for h in (2160, 1440, 1080, 720, 480, 360) if h <= want]
    parts: list[str] = []
    for h in ladder:
        parts.append(f"bestvideo[height<={h}][ext=mp4]+bestaudio[ext=m4a]")
        parts.append(f"bestvideo[height<={h}]+bestaudio")
        parts.append(f"best[height<={h}]")
    parts.append("best")
    return "/".join(parts)


# yt-dlp needs a JavaScript engine to read YouTube's player, and as of the 2026
# releases it only reaches for deno unless told otherwise. Deno is not in our
# image; node is. Without naming it, every fetch logs "No supported JavaScript
# runtime could be found" and a deprecation notice. Both are listed so the
# entry keeps working if the image ever gains deno.
#
# Measured before changing it: a 1080p trailer came down to the same byte count
# either way, so this is future proofing, not a fix for anything failing today.
#
# yt-dlp will additionally ask for its "challenge solver script", which it wants
# to DOWNLOAD FROM GITHUB AT RUNTIME (--remote-components ejs:github). That is
# fetching and executing third party code on every deploy, and nothing needs it
# yet, so it stays off deliberately. Revisit only if trailers actually start
# failing or arriving at a throttled speed.
_JS_RUNTIMES = {"node": {}, "deno": {}}

# What went wrong, in words the person who pressed the button can act on. The
# raw yt-dlp text is three lines of wiki links about exporting cookies, which is
# not an answer for someone looking at a game page.
_TRAILER_ERRORS = (
    ("sign in to confirm your age", "age_restricted"),
    ("confirm your age",            "age_restricted"),
    ("age-restricted",              "age_restricted"),
    ("private video",               "private"),
    ("members-only",                "private"),
    ("video unavailable",           "unavailable"),
    ("this video is unavailable",   "unavailable"),
    ("has been removed",            "unavailable"),
    ("account associated",          "unavailable"),
    ("not available in your country", "geo_blocked"),
    ("blocked it in your country",  "geo_blocked"),
    ("requested format is not available", "no_format"),
    ("sign in to confirm you",      "bot_check"),
    ("unable to download",          "network"),
    ("timed out",                   "network"),
    ("connection",                  "network"),
)


def _classify_trailer_error(message: str) -> str:
    """Map a yt-dlp failure onto a stable code the frontend can translate.

    Codes are matched in order because YouTube's age message also contains the
    word "sign in", which would otherwise be read as the bot check.
    """
    low = (message or "").lower()
    for needle, code in _TRAILER_ERRORS:
        if needle in low:
            return code
    return "failed"


async def download_youtube_video(
    game_id: int, video_id: str, quality: str = "1080",
) -> tuple[str | None, str | None]:
    """Download a trailer to resources/library/{id}/video/video.{ext} via
    yt-dlp so players serve it locally (same rule as covers: never hotlink).
    Runs the blocking yt-dlp call in a thread.

    Returns (local_url, None) on success and (None, error_code) on failure.
    It used to return None either way, which meant a trailer YouTube refuses to
    hand over was indistinguishable from one still downloading: the editor
    polled for five minutes and then gave up without telling anyone anything.
    """
    import asyncio

    def _dl() -> str | None:
        from yt_dlp import YoutubeDL
        vdir = _clear_video_dir(game_id)
        opts = {
            "format": _video_format(quality),
            "merge_output_format": "mp4",
            "outtmpl": str(vdir / "video.%(ext)s"),
            "quiet": True,
            "noprogress": True,
            "noplaylist": True,
            "js_runtimes": _JS_RUNTIMES,
        }
        with YoutubeDL(opts) as ydl:
            ydl.download([f"https://www.youtube.com/watch?v={video_id}"])
        for ext in _VIDEO_EXTS:
            p = vdir / f"video{ext}"
            if p.exists() and p.stat().st_size > 0:
                return f"/resources/library/{game_id}/video/video{ext}?v={int(p.stat().st_mtime)}"
        return None

    try:
        url = await asyncio.to_thread(_dl)
    except Exception as exc:
        code = _classify_trailer_error(str(exc))
        logger.warning(
            "Trailer download failed game_id=%s video=%s (%s): %s",
            game_id, video_id, code, exc,
        )
        return None, code

    if url:
        return url, None

    # yt-dlp reported success but left nothing behind. Rare, and worth its own
    # code rather than being folded into the generic failure.
    logger.warning(
        "Trailer download produced no file game_id=%s video=%s", game_id, video_id,
    )
    return None, "no_file"


async def save_uploaded_video(game_id: int, upload, ext: str, max_bytes: int) -> str | None:
    """Stream an uploaded video file to the game's video dir (no full read
    into memory). Returns the local URL, or None when the size cap is hit."""
    vdir = _clear_video_dir(game_id)
    dest = vdir / f"video{ext}"
    total = 0
    try:
        with dest.open("wb") as out:
            while True:
                chunk = await upload.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    out.close()
                    dest.unlink(missing_ok=True)
                    return None
                out.write(chunk)
        return f"/resources/library/{game_id}/video/video{ext}?v={int(dest.stat().st_mtime)}"
    except Exception as exc:
        logger.warning("Video upload failed game_id=%s: %s", game_id, exc)
        dest.unlink(missing_ok=True)
        return None


async def download_collection_image(slug: str, url: str, kind: str = "cover") -> str | None:
    """Download a scraped collection image (cover/hero/logo) to
    resources/collection-covers/. Mirrors the manual cover-upload path so the
    frontend serves it locally (rule: never hotlink scraped media). The cover
    keeps the bare `{slug}.{ext}` name used by the upload endpoint; hero/logo
    use `{slug}-{kind}.{ext}`. Returns the local path with a cache-busting
    ?v=<mtime>, or None on failure / a non-external url."""
    if not _is_external(url):
        return url
    COLLECTION_COVERS_PATH.mkdir(parents=True, exist_ok=True)
    stem = slug if kind == "cover" else f"{slug}-{kind}"
    for old in COLLECTION_COVERS_PATH.glob(f"{stem}.*"):
        try:
            old.unlink()
        except OSError:
            pass
    try:
        content, ctype = await fetch_media_bytes(url, headers=_HDRS, timeout=30)
        ext = _ext_from(url, ctype)
        dest = COLLECTION_COVERS_PATH / f"{stem}{ext}"
        dest.write_bytes(content)
        return f"/resources/collection-covers/{stem}{ext}?v={int(dest.stat().st_mtime)}"
    except Exception as exc:
        logger.warning("Collection %s download failed slug=%s url=%s: %s", kind, slug, url, exc)
        return None


async def download_all_media(game_id: int, data: dict, overwrite: bool = False) -> dict:
    """Download all media URLs in a game data dict to local paths.
    Modifies and returns the dict with local paths replacing external URLs.
    """
    from handler.config.config_handler import config_handler
    from utils.async_utils import gather_bounded

    async def _dl_cover():
        if "cover_path" in data and _is_external(data["cover_path"]):
            local = await download_cover(game_id, data["cover_path"], overwrite)
            if local:
                data["cover_path"] = local

    async def _dl_bg():
        if "background_path" in data and _is_external(data["background_path"]):
            local = await download_background(game_id, data["background_path"], overwrite)
            if local:
                data["background_path"] = local

    async def _dl_logo():
        if "logo_path" in data and _is_external(data["logo_path"]):
            local = await download_logo(game_id, data["logo_path"], overwrite)
            if local:
                data["logo_path"] = local

    async def _dl_icon():
        if "icon_path" in data and _is_external(data["icon_path"]):
            local = await download_icon(game_id, data["icon_path"], overwrite)
            if local:
                data["icon_path"] = local

    parallel = await config_handler.get_bool("metadata_parallel_media", default=True)
    await gather_bounded([_dl_cover(), _dl_bg(), _dl_logo(), _dl_icon()], parallel=parallel)

    # Keep the animated flag in sync with whatever cover this update leaves
    # behind (multi-frame webp/gif); clearing the cover clears the flag too.
    # Runs after the downloads so it sees the final local cover path.
    if "cover_path" in data:
        from utils.images import detect_cover_animated
        data["cover_animated"] = detect_cover_animated(data["cover_path"])

    if "screenshots" in data and isinstance(data["screenshots"], list):
        data["screenshots"] = await download_screenshots(game_id, data["screenshots"], overwrite)

    return data
