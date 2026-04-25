"""ROM metadata scraper - orchestrates IGDB, ScreenScraper, LaunchBox.

Priority order (fills only fields still missing after each source):
  1. ScreenScraper - ROM-specific, best for box art and regional info
  2. IGDB          - game database, covers, screenshots, genres, ratings
  3. LaunchBox     - large community database, good descriptions and genres

Images are downloaded to /data/resources/roms/{platform_slug}/{rom_id}/
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import httpx

from config import RESOURCES_PATH
from config import config_manager
from handler.config.config_handler import config_handler
from handler.database.rom_handler import rom_handler
from handler.metadata import hltb_handler, igdb_rom_handler, launchbox_handler, screenscraper_handler
from handler.metadata.rom_platform_map import (
    get_hltb_name, get_igdb_id, get_launchbox_name, get_ss_id,
)
from models.rom import Rom
from models.rom_platform import RomPlatform

logger = logging.getLogger(__name__)


def _detect_cover_aspect(path: Path) -> str | None:
    """Read image dimensions and snap to the nearest standard CSS aspect-ratio string."""
    try:
        from PIL import Image
        with Image.open(path) as img:
            w, h = img.size
        if h == 0:
            return None
        ratio = w / h
        # Snap to nearest standard box-art proportions
        if   ratio > 1.55: return "16/9"    # widescreen / box-3D perspective
        elif ratio > 1.25: return "4/3"     # Genesis/MD, old consoles (landscape)
        elif ratio > 1.05: return "16/11"   # SNES horizontal box
        elif ratio > 0.92: return "1/1"     # square (GB, GBC, Atari)
        elif ratio > 0.72: return "4/5"     # slightly portrait
        elif ratio > 0.57: return "3/4"     # standard modern portrait
        else:              return "2/3"     # tall movie-style box
    except Exception as e:
        logger.debug("Could not detect cover aspect from %s: %s", path, e)
        return None


_CT_EXT = {
    "image/png":  "png", "image/jpeg": "jpg", "image/jpg": "jpg",
    "image/webp": "webp", "image/gif": "gif", "image/bmp": "bmp",
    "video/mp4":  "mp4", "video/webm": "webm",
}

async def _download_image(url: str, dest: Path) -> Path | None:
    """Download *url* to *dest*.

    If the destination extension looks ambiguous (e.g. '.php', '.aspx'),
    the actual extension is detected from the response Content-Type header
    and the file is written with the correct extension instead.

    Returns the actual Path where the file was saved, or None on failure.
    """
    _REAL_EXTS = {"png", "jpg", "jpeg", "webp", "gif", "bmp", "mp4", "webm", "svg"}
    if not url:
        return None
    if dest.exists():
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as c:
            r = await c.get(url, headers={"User-Agent": "GamesDownloader/3.0"})
            r.raise_for_status()
            # Detect real extension from Content-Type when URL ext is ambiguous
            url_ext = dest.suffix.lstrip(".").lower()
            if url_ext not in _REAL_EXTS:
                ct = r.headers.get("content-type", "").split(";")[0].strip()
                real_ext = _CT_EXT.get(ct)
                if real_ext:
                    dest = dest.with_suffix(f".{real_ext}")
            dest.write_bytes(r.content)
        return dest
    except Exception as e:
        logger.warning("Failed to download %s: %s", url, e)
        return None


def _rom_media_dir(platform_slug: str, rom_id: int) -> Path:
    return Path(RESOURCES_PATH) / "roms" / platform_slug / str(rom_id)


def _resource_url(platform_slug: str, rom_id: int, filename: str) -> str:
    return f"/resources/roms/{platform_slug}/{rom_id}/{filename}"


async def scrape_rom(
    rom: Rom,
    platform: RomPlatform,
    forced_ss_id: str | None = None,
    forced_launchbox_id: str | None = None,
) -> dict:
    """Scrape metadata for *rom* from all configured scrapers.

    If *forced_ss_id* or *forced_launchbox_id* is provided, the respective
    source is queried directly by ID (bypassing hash/name search) - used by
    the "Scrape this version" flow in Edit Metadata.  When a forced source
    is specified, it is inserted first so it wins the merge.

    Merges results (first scraper wins for each field) and downloads images.
    Returns a dict suitable for rom_handler.update_metadata().
    """
    # Load API credentials
    ss_user  = await config_handler.get("screenscraper_username") or ""
    ss_pass  = await config_handler.get("screenscraper_password") or ""
    ss_devid = await config_handler.get("screenscraper_devid") or ""
    ss_devpw = await config_handler.get("screenscraper_devpassword") or ""
    igdb_id  = await config_handler.get("igdb_client_id") or ""
    igdb_sec = await config_handler.get("igdb_client_secret") or ""
    lb_en_raw = await config_handler.get("launchbox_enabled") or "true"
    lb_enabled = lb_en_raw.lower() in ("1", "true", "yes")

    search_name   = rom.fs_name_no_ext or rom.fs_name
    fs_slug       = platform.fs_slug
    igdb_platform = get_igdb_id(fs_slug)
    ss_system     = get_ss_id(fs_slug)
    lb_platform   = get_launchbox_name(fs_slug)
    hltb_platform = get_hltb_name(fs_slug)

    # ── Load per-platform scrape preset ──────────────────────────────────────
    all_presets = config_manager.get_section("rom_scrape_presets") or {}
    preset      = all_presets.get(platform.fs_slug, {})
    ss_cover_type = preset.get("cover_type", "box-2D")
    ss_region     = preset.get("region",     "ss")
    ss_extras     = preset.get("extras",     [])

    results: list[dict] = []

    # ── 1. ScreenScraper ──────────────────────────────────────────────────────
    if ss_user and ss_pass:
        try:
            if forced_ss_id:
                # Direct lookup by SS game ID - skips hash/name search entirely
                logger.info("[SS] Forced ss_id=%s for ROM %s", forced_ss_id, search_name)
                ss_raw = await screenscraper_handler.get_game_by_id(
                    forced_ss_id,
                    username=ss_user,
                    password=ss_pass,
                    devid=ss_devid,
                    devpassword=ss_devpw,
                    ss_system_id=ss_system,
                )
            else:
                ss_raw = await screenscraper_handler.search_game(
                    search_name,
                    ss_system,
                    fs_name=rom.fs_name,
                    file_size=rom.fs_size_bytes,
                    crc=rom.crc_hash or "",
                    md5=rom.md5_hash or "",
                    sha1=getattr(rom, "sha1_hash", None) or "",
                    username=ss_user,
                    password=ss_pass,
                    devid=ss_devid,
                    devpassword=ss_devpw,
                )
            if ss_raw:
                results.append(screenscraper_handler.extract_metadata(
                    ss_raw,
                    cover_type=ss_cover_type,
                    region=ss_region,
                    extras=ss_extras,
                ))
        except Exception as e:
            logger.warning("[SS] Error scraping %s: %s", search_name, e)

    # ── 2. IGDB ───────────────────────────────────────────────────────────────
    if igdb_id and igdb_sec:
        try:
            igdb_raw = await igdb_rom_handler.search_game(
                search_name,
                igdb_platform,
                client_id=igdb_id,
                client_secret=igdb_sec,
            )
            if igdb_raw:
                results.append(igdb_rom_handler.extract_metadata(igdb_raw))
        except Exception as e:
            logger.warning("[IGDB] Error scraping %s: %s", search_name, e)

    # ── 3. LaunchBox ──────────────────────────────────────────────────────────
    if lb_enabled or forced_launchbox_id:
        try:
            if forced_launchbox_id:
                logger.info("[LB] Forced launchbox_id=%s for ROM %s", forced_launchbox_id, search_name)
                lb_data = await launchbox_handler.get_game_by_id(forced_launchbox_id)
            else:
                lb_data = await launchbox_handler.search_game(
                    search_name, lb_platform, enabled=lb_enabled
                )
            if lb_data:
                if forced_launchbox_id:
                    # Forced LB wins merge - insert at beginning
                    results.insert(0, lb_data)
                else:
                    results.append(lb_data)
        except Exception as e:
            logger.warning("[LaunchBox] Error scraping %s: %s", search_name, e)

    if not results:
        logger.info("No metadata found for ROM id=%d name=%s", rom.id, search_name)
        return {}

    # ── Extract per-source ratings before merge ─────────────────────────────
    # Each scraper returns a generic "rating" key - extract to separate fields
    for r in results:
        _src_rating = r.get("rating")
        if _src_rating is not None:
            if r.get("igdb_metadata") or r.get("igdb_id"):
                # IGDB handler already divided by 10 (0-100 -> 0-10), restore to 0-100
                r["igdb_rating"] = round(float(_src_rating) * 10, 1)
            elif r.get("launchbox_metadata") or r.get("launchbox_id"):
                r["lb_rating"] = round(float(_src_rating), 1)

    # ── Merge: first scraper wins for scalar fields; lists are combined ──────
    merged: dict = {}
    all_screenshots: list[str] = []
    for r in results:
        # Collect screenshots from ALL scrapers (SS + IGDB)
        src_ss = r.pop("screenshots", None) or []
        logger.debug("[scrape] source screenshots: %d urls", len(src_ss))
        for ss_url in src_ss:
            if ss_url and ss_url not in all_screenshots:
                all_screenshots.append(ss_url)
        for k, v in r.items():
            if v and k not in merged:
                merged[k] = v

    # ── 4. HowLongToBeat ──────────────────────────────────────────────────────
    try:
        hltb_data = await hltb_handler.search_game(search_name, hltb_platform)
        if hltb_data:
            for k, v in hltb_data.items():
                merged[k] = v
    except Exception as e:
        logger.warning("[HLTB] Error scraping %s: %s", search_name, e)

    # ── 5. Plugin ratings ────────────────────────────────────────────────────
    try:
        from plugins.manager import plugin_manager
        _p_search = plugin_manager.hook.metadata_search_game(query=search_name)
        _p_ratings: dict = {}
        for _pr in _p_search:
            if not isinstance(_pr, list) or not _pr:
                continue
            _best = _pr[0]
            _pid = _best.get("provider_id", "")
            _gid = _best.get("provider_game_id", "")
            if not _pid or not _gid:
                continue
            _gd_list = plugin_manager.hook.metadata_get_game(provider_game_id=_gid)
            for _gd in _gd_list:
                if isinstance(_gd, dict) and _gd.get("provider_id") == _pid:
                    _r = _gd.get("rating")
                    if _r is not None:
                        from pathlib import Path as _P
                        from config import PLUGINS_PATH as _PP2
                        _plid = _pid
                        if not _P(_PP2, _pid).is_dir():
                            for _sfx in ["-metadata", "-scraper", "-plugin"]:
                                if _P(_PP2, _pid + _sfx).is_dir():
                                    _plid = _pid + _sfx
                                    break
                        _p_ratings[_pid] = {
                            "name": _best.get("name", _pid).upper(),
                            "rating": round(float(_r), 1),
                            "logo_url": f"/api/plugins/{_plid}/logo",
                        }
                    break
        if _p_ratings:
            merged["plugin_ratings"] = _p_ratings
    except Exception as _pe:
        logger.debug("[Plugins] Rating extraction error: %s", _pe)

    # ── Download images ───────────────────────────────────────────────────────
    media_dir  = _rom_media_dir(platform.slug, rom.id)
    cover_url  = merged.pop("cover_url", None)
    bg_url     = merged.pop("background_url", None)
    ss_urls    = all_screenshots[:8]  # Combined SS + IGDB screenshots (max 8)
    merged.pop("extra_urls", None)  # no longer used - replaced by ES-style download below

    if cover_url:
        ext = cover_url.rsplit(".", 1)[-1].split("?")[0] or "jpg"
        dest = media_dir / f"cover.{ext}"
        if media_dir.exists():
            for old in media_dir.glob("cover.*"):
                old.unlink(missing_ok=True)
        saved = await _download_image(cover_url, dest)
        if saved:
            merged["cover_path"] = _resource_url(platform.slug, rom.id, saved.name)
            merged["cover_type"] = ss_cover_type
            detected = _detect_cover_aspect(saved)
            if detected:
                merged["cover_aspect"] = detected

    if bg_url:
        ext = bg_url.rsplit(".", 1)[-1].split("?")[0] or "jpg"
        dest = media_dir / f"background.{ext}"
        saved = await _download_image(bg_url, dest)
        if saved:
            merged["background_path"] = _resource_url(platform.slug, rom.id, saved.name)

    saved_ss: list[str] = []
    for idx, ss_url in enumerate(ss_urls[:6]):
        ext  = ss_url.rsplit(".", 1)[-1].split("?")[0] or "jpg"
        dest = media_dir / f"screenshot_{idx}.{ext}"
        saved = await _download_image(ss_url, dest)
        if saved:
            saved_ss.append(_resource_url(platform.slug, rom.id, saved.name))
    if saved_ss:
        merged["screenshots"] = saved_ss

    # ── ES-style: always download support, wheel, steamgrid, video, bezel ────
    # Use extract_media_urls to get all categorised media from raw SS response,
    # then pick the best item per category and save to proper DB columns.
    # This mirrors what EmulationStation downloads automatically.
    ss_raw_for_extra = None
    for r in results:
        if r.get("is_identified") and r.get("ss_metadata"):
            ss_raw_for_extra = r["ss_metadata"]
            break

    if ss_raw_for_extra:
        region_pref = screenscraper_handler._build_region_pref(ss_region)
        all_media   = screenscraper_handler.extract_media_urls(ss_raw_for_extra)

        # (category_in_extract, filename_base, merged_key)
        _es_media = [
            ("supports",      "support",   "support_path"),
            ("bezels",        "bezel",     "bezel_path"),
            ("steamgrids",    "steamgrid", "steamgrid_path"),
            ("videos",        "video",     "video_path"),
            ("pictos",        "pictoliste","picto_path"),
        ]
        downloaded = 0

        # ── Wheel: wheel-hd (wor→ss→usa→eu) then wheel (same order) ─────────
        if not merged.get("wheel_path"):
            _wheel_region_pref = ["wor", "ss", "usa", "eu"]
            wheels = all_media.get("wheels", [])
            wheel_best = None
            for wtype in ("wheel-hd", "wheel"):
                typed = [w for w in wheels if w.get("type") == wtype]
                if typed:
                    wheel_best = next(
                        (w for rp in _wheel_region_pref for w in typed if w.get("region") == rp),
                        typed[0],
                    )
                    break
            if not wheel_best and wheels:
                wheel_best = wheels[0]
            if wheel_best:
                url = wheel_best.get("url", "")
                if url:
                    ext  = url.rsplit(".", 1)[-1].split("?")[0] or "png"
                    dest = media_dir / f"wheel.{ext}"
                    saved = await _download_image(url, dest)
                    if saved:
                        merged["wheel_path"] = _resource_url(platform.slug, rom.id, saved.name)
                        downloaded += 1

        for cat, fname, col in _es_media:
            if merged.get(col):
                continue
            items = all_media.get(cat, [])
            if not items:
                continue
            best = next(
                (m for rp in region_pref for m in items if m.get("region") == rp),
                items[0],
            )
            url = best.get("url", "")
            if not url:
                continue
            ext  = url.rsplit(".", 1)[-1].split("?")[0] or "jpg"
            dest = media_dir / f"{fname}.{ext}"
            saved = await _download_image(url, dest)
            if saved:
                merged[col] = _resource_url(platform.slug, rom.id, saved.name)
                downloaded += 1
        if downloaded:
            logger.info("[ROM] Downloaded %d ES-style media files for rom id=%d", downloaded, rom.id)

    # ── SteamGridDB fallback - grid cover + hero background ──────────────────
    # Runs when SS didn't provide steamgrid_path and/or background_path.
    need_grid = not merged.get("steamgrid_path")
    need_bg   = not merged.get("background_path")
    if need_grid or need_bg:
        try:
            _sgdb_key = await config_handler.get("steamgriddb_api_key")
            if _sgdb_key:
                _hdrs = {"Authorization": f"Bearer {_sgdb_key}"}
                async with httpx.AsyncClient(timeout=15) as _c:
                    _rs = await _c.get(
                        f"https://www.steamgriddb.com/api/v2/search/autocomplete/{search_name}",
                        headers=_hdrs,
                    )
                    if _rs.status_code == 200 and _rs.json().get("data"):
                        _sgdb_id = _rs.json()["data"][0]["id"]
                        if need_grid:
                            _rg = await _c.get(
                                f"https://www.steamgriddb.com/api/v2/grids/game/{_sgdb_id}",
                                params={"dimensions": "342x482,600x900", "limit": 5},
                                headers=_hdrs,
                            )
                            if _rg.status_code == 200:
                                _items = _rg.json().get("data", [])
                                if _items:
                                    _url  = _items[0]["url"]
                                    _ext  = _url.rsplit(".", 1)[-1].split("?")[0] or "jpg"
                                    _dest = media_dir / f"steamgrid.{_ext}"
                                    _saved = await _download_image(_url, _dest)
                                    if _saved:
                                        merged["steamgrid_path"] = _resource_url(platform.slug, rom.id, _saved.name)
                                        logger.info("[ROM] SGDB grid downloaded for rom id=%d", rom.id)
                        if need_bg:
                            _rh = await _c.get(
                                f"https://www.steamgriddb.com/api/v2/heroes/game/{_sgdb_id}",
                                params={"limit": 5},
                                headers=_hdrs,
                            )
                            if _rh.status_code == 200:
                                _items = _rh.json().get("data", [])
                                if _items:
                                    _url  = _items[0]["url"]
                                    _ext  = _url.rsplit(".", 1)[-1].split("?")[0] or "jpg"
                                    _dest = media_dir / f"background.{_ext}"
                                    _saved = await _download_image(_url, _dest)
                                    if _saved:
                                        merged["background_path"] = _resource_url(platform.slug, rom.id, _saved.name)
                                        logger.info("[ROM] SGDB hero downloaded as background for rom id=%d", rom.id)
        except Exception as _e:
            logger.debug("[SGDB] ROM scrape fallback error for rom id=%d: %s", rom.id, _e)

    return merged


async def scrape_roms_batch(rom_ids: list[int], platform: RomPlatform) -> dict:
    """Scrape a list of ROMs sequentially (rate-limit friendly).

    Returns { scraped, skipped, errors }.
    """
    stats = {"scraped": 0, "skipped": 0, "errors": 0}
    for rom_id in rom_ids:
        rom = await rom_handler.get_by_id(rom_id)
        if rom is None:
            stats["skipped"] += 1
            continue
        try:
            data = await scrape_rom(rom, platform)
            if data:
                await rom_handler.update_metadata(rom_id, data)
                stats["scraped"] += 1
            else:
                stats["skipped"] += 1
        except Exception as e:
            logger.error("Error scraping ROM id=%d: %s", rom_id, e)
            stats["errors"] += 1
        # Small delay between requests to be polite to scrapers
        await asyncio.sleep(0.5)

    return stats


async def scrape_platform_info(platform: RomPlatform) -> dict:
    """Fetch ScreenScraper system info (photo, description, etc.) for a platform.

    Downloads the platform photo to
    ``/data/resources/platforms/{fs_slug}/photo.{ext}``
    and returns a dict suitable for storing in config_manager["platform_info"].
    """
    from handler.metadata.rom_platform_map import get_ss_id

    ss_user  = await config_handler.get("screenscraper_username") or ""
    ss_pass  = await config_handler.get("screenscraper_password") or ""
    ss_devid = await config_handler.get("screenscraper_devid") or ""
    ss_devpw = await config_handler.get("screenscraper_devpassword") or ""
    if not ss_user or not ss_pass:
        logger.warning("[Platform] SS credentials not configured - cannot scrape platform info")
        return {}

    ss_id = get_ss_id(platform.fs_slug)
    if not ss_id:
        logger.info("[Platform] No SS system ID for fs_slug=%s", platform.fs_slug)
        return {}

    system_raw = await screenscraper_handler.get_system_info(
        ss_id, username=ss_user, password=ss_pass,
        devid=ss_devid, devpassword=ss_devpw,
    )
    if not system_raw:
        logger.warning("[Platform] SS returned no system info for id=%d fs_slug=%s", ss_id, platform.fs_slug)
        return {}

    info = screenscraper_handler.extract_system_info(system_raw)

    # ── Wikipedia description ─────────────────────────────────────────────────
    # Use LaunchBox name (most complete) → eu → fallback name for best title match
    noms = system_raw.get("noms") or {}
    wiki_name = (
        noms.get("nom_launchbox") or noms.get("nom_eu") or noms.get("nom_us") or info.get("name") or ""
    )
    wiki_description: str | None = None
    wiki_url: str | None = None
    if wiki_name:
        try:
            import urllib.parse as _up
            _title = _up.quote(wiki_name.replace(" ", "_"), safe="")
            _wiki_api = f"https://en.wikipedia.org/api/rest_v1/page/summary/{_title}"
            async with httpx.AsyncClient(timeout=10, follow_redirects=True,
                                          headers={"User-Agent": "GamesDownloader/3.0 (emulation library)"}) as _c:
                _r = await _c.get(_wiki_api)
                if _r.status_code == 200:
                    _data = _r.json()
                    wiki_description = _data.get("extract") or None
                    _page_url = (_data.get("content_urls") or {}).get("desktop", {}).get("page")
                    wiki_url = _page_url or None
                    logger.info("[Platform] Wikipedia description fetched for %r (%d chars)",
                                wiki_name, len(wiki_description or ""))
                else:
                    logger.info("[Platform] Wikipedia 404/error for %r (status=%d)", wiki_name, _r.status_code)
        except Exception as _e:
            logger.warning("[Platform] Wikipedia fetch failed for %r: %s", wiki_name, _e)

    # Common media dir for this platform
    photo_dir = Path(RESOURCES_PATH) / "platforms" / platform.fs_slug
    photo_dir.mkdir(parents=True, exist_ok=True)

    async def _dl_platform_media(url: str | None, fname: str) -> str | None:
        if not url:
            return None
        ext = url.rsplit(".", 1)[-1].split("?")[0] or "jpg"
        dest = photo_dir / f"{fname}.{ext}"
        dest.unlink(missing_ok=True)
        saved = await _download_image(url, dest)
        if saved:
            return f"/resources/platforms/{platform.fs_slug}/{saved.name}"
        return None

    # Download platform photo (world > ss/Monde > usa > japan)
    photo_path = await _dl_platform_media(info.get("photo_url"), "photo")

    # Download platform icon (logo-monochrome or logo) - in background, no rush
    icon_path  = await _dl_platform_media(info.get("icon_url"),  "icon")

    # Download platform bezel - may be None if SS doesn't include it
    bezel_path = await _dl_platform_media(info.get("bezel_url"), "bezel")

    result = {
        "photo_path":   photo_path,
        "icon_path":    icon_path,
        "bezel_path":   bezel_path,
        "description":  wiki_description or info.get("description"),
        "wiki_url":     wiki_url,
        "manufacturer": info.get("manufacturer"),
        "release_year": info.get("release_year"),
        "end_year":     info.get("end_year"),
        "generation":   info.get("generation"),
    }
    logger.info("[Platform] Scraped info for %s: manufacturer=%s year=%s",
                platform.fs_slug, result["manufacturer"], result["release_year"])
    return result
