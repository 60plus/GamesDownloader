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

import httpx

try:
    from config import GD_BASE_PATH
except ImportError:
    GD_BASE_PATH = "/data"

logger = logging.getLogger(__name__)

RESOURCES_PATH = Path(GD_BASE_PATH) / "resources" / "library"

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
        async with httpx.AsyncClient(headers=_HDRS, follow_redirects=True, timeout=30) as c:
            r = await c.get(url)
            r.raise_for_status()
            dest.write_bytes(r.content)
            return True
    except Exception as exc:
        logger.warning("Download failed %s: %s", url, exc)
        return False


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
        async with httpx.AsyncClient(headers=_HDRS, follow_redirects=True, timeout=30) as c:
            r = await c.get(url)
            r.raise_for_status()
            ext = _ext_from(url, r.headers.get("content-type", ""))
            dest = cover_dir / f"cover{ext}"
            dest.write_bytes(r.content)
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
        async with httpx.AsyncClient(headers=_HDRS, follow_redirects=True, timeout=30) as c:
            r = await c.get(url)
            r.raise_for_status()
            ext = _ext_from(url, r.headers.get("content-type", ""))
            dest = bg_dir / f"background{ext}"
            dest.write_bytes(r.content)
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
        async with httpx.AsyncClient(headers=_HDRS, follow_redirects=True, timeout=30) as c:
            r = await c.get(url)
            r.raise_for_status()
            ext = _ext_from(url, r.headers.get("content-type", ""))
            dest = logo_dir / f"logo{ext}"
            dest.write_bytes(r.content)
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
        async with httpx.AsyncClient(headers=_HDRS, follow_redirects=True, timeout=30) as c:
            r = await c.get(url)
            r.raise_for_status()
            ext = _ext_from(url, r.headers.get("content-type", ""))
            dest = icon_dir / f"icon{ext}"
            dest.write_bytes(r.content)
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
            async with httpx.AsyncClient(headers=_HDRS, follow_redirects=True, timeout=30) as c:
                r = await c.get(url)
                r.raise_for_status()
                ext = _ext_from(url, r.headers.get("content-type", ""))
                dest = shots_dir / f"shot_{i:03d}{ext}"
                dest.write_bytes(r.content)
                results.append(f"/resources/library/{game_id}/shots/shot_{i:03d}{ext}")
        except Exception as exc:
            logger.warning("Screenshot %d download failed game_id=%s: %s", i, game_id, exc)
            results.append(url)  # keep external URL as fallback

    return results


async def download_all_media(game_id: int, data: dict, overwrite: bool = False) -> dict:
    """Download all media URLs in a game data dict to local paths.
    Modifies and returns the dict with local paths replacing external URLs.
    """
    if "cover_path" in data and _is_external(data["cover_path"]):
        local = await download_cover(game_id, data["cover_path"], overwrite)
        if local:
            data["cover_path"] = local

    if "background_path" in data and _is_external(data["background_path"]):
        local = await download_background(game_id, data["background_path"], overwrite)
        if local:
            data["background_path"] = local

    if "logo_path" in data and _is_external(data["logo_path"]):
        local = await download_logo(game_id, data["logo_path"], overwrite)
        if local:
            data["logo_path"] = local

    if "icon_path" in data and _is_external(data["icon_path"]):
        local = await download_icon(game_id, data["icon_path"], overwrite)
        if local:
            data["icon_path"] = local

    if "screenshots" in data and isinstance(data["screenshots"], list):
        data["screenshots"] = await download_screenshots(game_id, data["screenshots"], overwrite)

    return data
