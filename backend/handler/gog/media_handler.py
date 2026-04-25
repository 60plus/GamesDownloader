"""
GOG game media downloader - async port of the V2 media_handler pattern.

Downloads cover, background, and screenshots to the local resources directory
so the frontend can serve them without repeatedly calling GOG CDN.

Structure:  resources/gog/{gog_id}/
              covers/cover_auto.{ext}
              background/background_auto.{ext}
              shots/auto_NNN.{ext}
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

import httpx

try:
    from config import GD_BASE_PATH
except ImportError:
    GD_BASE_PATH = "/data"

logger = logging.getLogger(__name__)

RESOURCES_PATH = Path(GD_BASE_PATH) / "resources" / "gog"

_HDRS = {
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept":          "image/webp,image/avif,image/*,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer":         "https://www.gog.com/",
    "Origin":          "https://www.gog.com",
}


# GOG CDN (Fastly) no longer supports formatter suffixes - strip them so the
# CDN receives only {hash}.{ext} which returns HTTP 200.
# This covers both game-image suffixes AND avatar suffixes (_glx_av etc.).
_GOG_SUFFIX_RE = re.compile(
    r'_(product_card|product_tile_\d+|aw|logo2x|logo|glx_av|avatar_av|glx_av_bg|av_bg|large2x|large|medium|small)(v2[^.]*)?(?=\.(jpg|png|webp)$)',
    re.IGNORECASE,
)

def _fix_gog_url(url: str) -> str:
    """Normalise and clean a GOG CDN image URL.
    1. Adds https: to protocol-relative URLs (// prefix).
    2. Strips deprecated Fastly formatter suffixes (_product_card, _logo2x, etc.)
       that now return HTTP 400 from GOG CDN.
    """
    if not url:
        return url
    if url.startswith("//"):
        url = "https:" + url
    return _GOG_SUFFIX_RE.sub('', url)


def _game_dir(gog_id: int) -> Path:
    d = RESOURCES_PATH / str(gog_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _ext_from(url: str, content_type: str = "") -> str:
    ct = content_type.lower()
    if "webp" in ct:  return ".webp"
    if "png"  in ct:  return ".png"
    if "gif"  in ct:  return ".gif"
    url_l = url.lower()
    if ".png"  in url_l: return ".png"
    if ".webp" in url_l: return ".webp"
    if ".gif"  in url_l: return ".gif"
    return ".jpg"


async def download_cover(gog_id: int, url: str, overwrite: bool = False) -> str | None:
    """Download cover image → resources/gog/{id}/covers/cover_auto.ext.
    Returns the server-relative URL path or None on failure.
    Skips download if a cached file already exists (unless overwrite=True).
    """
    gdir = _game_dir(gog_id)
    covers_dir = gdir / "covers"
    covers_dir.mkdir(exist_ok=True)

    # Return cached file if it exists (unless overwrite requested)
    if not overwrite:
        for ext in (".jpg", ".png", ".webp", ".gif"):
            p = covers_dir / f"cover_auto{ext}"
            if p.exists() and p.stat().st_size > 0:
                return f"/resources/gog/{gog_id}/covers/cover_auto{ext}"

    try:
        fetch_url = _fix_gog_url(url)
        async with httpx.AsyncClient(headers=_HDRS, follow_redirects=True, timeout=20) as c:
            r = await c.get(fetch_url)
            r.raise_for_status()
            ext = _ext_from(fetch_url, r.headers.get("content-type", ""))
            dest = covers_dir / f"cover_auto{ext}"
            dest.write_bytes(r.content)
            logger.debug("Cover downloaded for gog_id=%s → %s", gog_id, dest)
            return f"/resources/gog/{gog_id}/covers/cover_auto{ext}"
    except Exception as exc:
        logger.warning("Cover download failed gog_id=%s url=%s: %s", gog_id, url, exc)
        return None


async def download_background(gog_id: int, url: str, overwrite: bool = False) -> str | None:
    """Download background image → resources/gog/{id}/background/background_auto.ext."""
    gdir = _game_dir(gog_id)
    bg_dir = gdir / "background"
    bg_dir.mkdir(exist_ok=True)

    if not overwrite:
        for ext in (".jpg", ".png", ".webp"):
            p = bg_dir / f"background_auto{ext}"
            if p.exists() and p.stat().st_size > 0:
                return f"/resources/gog/{gog_id}/background/background_auto{ext}"

    try:
        fetch_url = _fix_gog_url(url)
        async with httpx.AsyncClient(headers=_HDRS, follow_redirects=True, timeout=20) as c:
            r = await c.get(fetch_url)
            r.raise_for_status()
            ext = _ext_from(fetch_url, r.headers.get("content-type", ""))
            dest = bg_dir / f"background_auto{ext}"
            dest.write_bytes(r.content)
            return f"/resources/gog/{gog_id}/background/background_auto{ext}"
    except Exception as exc:
        logger.warning("Background download failed gog_id=%s: %s", gog_id, exc)
        return None


async def download_logo(gog_id: int, url: str, overwrite: bool = False) -> str | None:
    """Download transparent logo → resources/gog/{id}/logo/logo_auto.ext."""
    gdir = _game_dir(gog_id)
    logo_dir = gdir / "logo"
    logo_dir.mkdir(exist_ok=True)

    if not overwrite:
        for ext in (".png", ".webp", ".jpg", ".gif"):
            p = logo_dir / f"logo_auto{ext}"
            if p.exists() and p.stat().st_size > 0:
                return f"/resources/gog/{gog_id}/logo/logo_auto{ext}"

    try:
        async with httpx.AsyncClient(headers=_HDRS, follow_redirects=True, timeout=20) as c:
            r = await c.get(url)
            r.raise_for_status()
            ext = _ext_from(url, r.headers.get("content-type", ""))
            dest = logo_dir / f"logo_auto{ext}"
            dest.write_bytes(r.content)
            return f"/resources/gog/{gog_id}/logo/logo_auto{ext}"
    except Exception as exc:
        logger.warning("Logo download failed gog_id=%s: %s", gog_id, exc)
        return None


async def download_icon(gog_id: int, url: str, overwrite: bool = False) -> str | None:
    """Download game icon → resources/gog/{id}/icon/icon_auto.ext."""
    gdir = _game_dir(gog_id)
    icon_dir = gdir / "icon"
    icon_dir.mkdir(exist_ok=True)

    if not overwrite:
        for ext in (".png", ".jpg", ".webp", ".ico"):
            p = icon_dir / f"icon_auto{ext}"
            if p.exists() and p.stat().st_size > 0:
                return f"/resources/gog/{gog_id}/icon/icon_auto{ext}"

    try:
        fetch_url = _fix_gog_url(url)
        async with httpx.AsyncClient(headers=_HDRS, follow_redirects=True, timeout=20) as c:
            r = await c.get(fetch_url)
            r.raise_for_status()
            ext = _ext_from(fetch_url, r.headers.get("content-type", ""))
            dest = icon_dir / f"icon_auto{ext}"
            dest.write_bytes(r.content)
            return f"/resources/gog/{gog_id}/icon/icon_auto{ext}"
    except Exception as exc:
        logger.warning("Icon download failed gog_id=%s: %s", gog_id, exc)
        return None


async def download_avatar(user_id: str, url: str) -> str | None:
    """Download GOG user avatar → resources/avatars/{user_id}.ext.
    Returns server-relative URL or None on failure.

    _fix_gog_url IS applied here - GOG avatar URLs on images.gog-statics.com
    use the same Fastly CDN that deprecated formatter suffixes (e.g. _glx_av,
    _large2x). Stripping them lets the CDN return the base image (HTTP 200).
    """
    avatars_dir = Path(GD_BASE_PATH) / "resources" / "avatars"
    avatars_dir.mkdir(parents=True, exist_ok=True)

    try:
        fetch_url = _fix_gog_url(url)
        logger.debug("Downloading avatar user_id=%s  url=%s  fixed=%s", user_id, url, fetch_url)
        async with httpx.AsyncClient(headers=_HDRS, follow_redirects=True, timeout=20) as c:
            r = await c.get(fetch_url)
            r.raise_for_status()
            ext = _ext_from(fetch_url, r.headers.get("content-type", ""))
            dest = avatars_dir / f"{user_id}{ext}"
            dest.write_bytes(r.content)
            logger.info("Avatar downloaded for user_id=%s → %s", user_id, dest)
            return f"/resources/avatars/{user_id}{ext}"
    except Exception as exc:
        logger.warning("Avatar download failed user_id=%s url=%s: %s", user_id, url, exc)
        return None


async def download_screenshots(gog_id: int, urls: list[str], overwrite: bool = False) -> list[str]:
    """Download up to 12 screenshots → resources/gog/{id}/shots/auto_NNN.ext.
    Returns list of server-relative URL paths for successfully downloaded shots.
    """
    gdir = _game_dir(gog_id)
    shots_dir = gdir / "shots"
    shots_dir.mkdir(exist_ok=True)

    saved: list[str] = []
    async with httpx.AsyncClient(headers=_HDRS, follow_redirects=True, timeout=20) as c:
        for i, url in enumerate(urls[:12]):
            try:
                # Check for existing cached screenshot (skip if not overwriting)
                if not overwrite:
                    found_cached = False
                    for ext_check in (".jpg", ".png", ".webp", ".gif"):
                        cached = shots_dir / f"auto_{i:03d}{ext_check}"
                        if cached.exists() and cached.stat().st_size > 0:
                            saved.append(f"/resources/gog/{gog_id}/shots/auto_{i:03d}{ext_check}")
                            found_cached = True
                            break
                    if found_cached:
                        continue
                fetch_url = _fix_gog_url(url)
                r = await c.get(fetch_url)
                r.raise_for_status()
                ext = _ext_from(fetch_url, r.headers.get("content-type", ""))
                dest = shots_dir / f"auto_{i:03d}{ext}"
                dest.write_bytes(r.content)
                saved.append(f"/resources/gog/{gog_id}/shots/auto_{i:03d}{ext}")
            except Exception as exc:
                logger.warning("Screenshot %d failed gog_id=%s: %s", i, gog_id, exc)

    return saved
