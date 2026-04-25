"""ROM library endpoints.

Prefix: /api/roms

IMPORTANT: The protected_route decorator always passes `request` as the first
positional argument to the wrapped function.  Therefore every endpoint function
MUST have `request: Request` as its very first parameter, before any path /
query / body params - otherwise FastAPI will receive "multiple values" errors.
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

import httpx
from fastapi import APIRouter, BackgroundTasks, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from config import ROMS_PATH, config_manager
from decorators.auth import protected_route
from handler.auth.scopes import Scope as Scopes
from handler.database.rom_handler import rom_handler, rom_platform_handler
from handler.filesystem.rom_scanner import scan_roms_path
from handler.metadata.rom_scrape_handler import scrape_roms_batch
from handler.metadata.rom_platform_map import PLATFORM_MAP, get_cover_aspect as _get_cover_aspect

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/roms", tags=["roms"])

# ── Scan state (single-instance lock) ─────────────────────────────────────────
_scan_lock = asyncio.Lock()
_scan_running = False  # read-only status flag (set under _scan_lock)


# ── Schemas ───────────────────────────────────────────────────────────────────

class PlatformUpdateBody(BaseModel):
    custom_name: str | None = None


class RomMetadataUpdate(BaseModel):
    name: str | None = None
    summary: str | None = None
    developer: str | None = None
    publisher: str | None = None
    release_year: int | None = None
    genres: list[str] | None = None
    regions: list[str] | None = None
    languages: list[str] | None = None
    rating: float | None = None
    player_count: str | None = None
    hltb_id:         int | None = None
    hltb_main_s:     int | None = None
    hltb_extra_s:    int | None = None
    hltb_complete_s: int | None = None
    cover_url: str | None = None       # if provided, download and set cover_path
    background_url: str | None = None  # if provided, download and set background_path
    cover_path: str | None = None      # direct path override
    background_path: str | None = None
    screenshots: list[str] | None = None  # list of screenshot URLs
    support_path:    str | None = None
    wheel_path:      str | None = None
    bezel_path:      str | None = None
    steamgrid_path:  str | None = None
    video_path:      str | None = None
    picto_path:      str | None = None
    support_url:     str | None = None
    wheel_url:       str | None = None
    bezel_url:       str | None = None
    steamgrid_url:   str | None = None
    video_url:       str | None = None


# ── Platforms ─────────────────────────────────────────────────────────────────

@protected_route(router.get, "/platforms", scopes=[Scopes.LIBRARY_READ])
async def list_platforms(request: Request) -> list[dict]:
    """List all detected ROM platforms with ROM counts."""
    return await rom_platform_handler.get_all_with_counts()


@protected_route(router.get, "/platforms/known", scopes=[Scopes.LIBRARY_READ])
async def list_known_platforms(request: Request) -> list[dict]:
    """Return all platforms defined in PLATFORM_MAP (known slugs, not necessarily in DB).

    Deduplicates by display name - when multiple slugs share a name (e.g. 'atari2600'
    and 'atari-2600') keeps the first entry, which is the canonical short slug.
    """
    seen: set[str] = set()
    result: list[dict] = []
    for fs_slug, info in PLATFORM_MAP.items():
        name = info["name"]
        if name in seen:
            continue
        seen.add(name)
        result.append({"fs_slug": fs_slug, "name": name})
    result.sort(key=lambda x: x["name"])
    return result


@protected_route(router.get, "/platforms/metadata", scopes=[Scopes.LIBRARY_READ])
async def get_platforms_metadata(request: Request) -> dict:
    """Return EmulationStation metadata (colour, descriptions, etc.) for all platforms."""
    from handler.metadata.platform_metadata_handler import get_all as _pm_get_all
    return _pm_get_all()


@protected_route(router.get, "/platforms/{slug}", scopes=[Scopes.LIBRARY_READ])
async def get_platform(request: Request, slug: str) -> dict:
    platform = await rom_platform_handler.get_by_slug(slug)
    if platform is None:
        raise HTTPException(status_code=404, detail="Platform not found")
    rom_count = await rom_handler.count_for_platform(platform.id)
    # Stored platform info (from scrape-platform)
    p_cfg = (config_manager.get_section("platform_info") or {}).get(platform.fs_slug, {})
    return {
        "id":                   platform.id,
        "slug":                 platform.slug,
        "fs_slug":              platform.fs_slug,
        "name":                 platform.custom_name or platform.name,
        "cover_path":           platform.cover_path,
        "is_identified":        platform.is_identified,
        "rom_count":            rom_count,
        "cover_aspect":         _get_cover_aspect(platform.fs_slug),
        # Platform info (may be None if not yet scraped)
        "photo_path":            p_cfg.get("photo_path"),
        "icon_path":             p_cfg.get("icon_path"),
        "bezel_path":            p_cfg.get("bezel_path"),
        "description":           p_cfg.get("description"),
        "wiki_url":              p_cfg.get("wiki_url"),
        "manufacturer":          p_cfg.get("manufacturer"),
        "release_year_platform": p_cfg.get("release_year"),
        "end_year_platform":     p_cfg.get("end_year"),
        "generation":            p_cfg.get("generation"),
    }


@protected_route(router.get, "/platforms/{slug}/stored-info", scopes=[Scopes.LIBRARY_READ])
async def get_platform_stored_info(request: Request, slug: str) -> dict:
    """Return the config-stored platform info (photo, description, etc.) for any fs_slug.

    Works for both real DB platforms and preview-only slugs - reads directly from
    the platform_info config section without requiring a DB record.
    """
    p_cfg = (config_manager.get_section("platform_info") or {}).get(slug, {})
    return {
        "photo_path":            p_cfg.get("photo_path"),
        "icon_path":             p_cfg.get("icon_path"),
        "bezel_path":            p_cfg.get("bezel_path"),
        "description":           p_cfg.get("description"),
        "wiki_url":              p_cfg.get("wiki_url"),
        "manufacturer":          p_cfg.get("manufacturer"),
        "release_year_platform": p_cfg.get("release_year"),
        "end_year_platform":     p_cfg.get("end_year"),
        "generation":            p_cfg.get("generation"),
    }


@protected_route(router.patch, "/platforms/{slug}", scopes=[Scopes.LIBRARY_WRITE])
async def update_platform(request: Request, slug: str, body: PlatformUpdateBody) -> dict:
    platform = await rom_platform_handler.get_by_slug(slug)
    if platform is None:
        raise HTTPException(status_code=404, detail="Platform not found")
    await rom_platform_handler.update(platform, {"custom_name": body.custom_name})
    rom_count = await rom_handler.count_for_platform(platform.id)
    return {
        "id":            platform.id,
        "slug":          platform.slug,
        "fs_slug":       platform.fs_slug,
        "name":          platform.custom_name or platform.name,
        "cover_path":    platform.cover_path,
        "is_identified": platform.is_identified,
        "rom_count":     rom_count,
    }


# ── ROM list ──────────────────────────────────────────────────────────────────

@protected_route(router.get, "", scopes=[Scopes.LIBRARY_READ])
async def list_roms(
    request: Request,
    platform_slug: str | None = None,
    search: str = "",
    sort: str = "name_asc",
    limit: int = 48,
    offset: int = 0,
) -> dict:
    """List ROMs, optionally filtered by platform slug."""
    platform_id = None
    if platform_slug:
        platform = await rom_platform_handler.get_by_slug(platform_slug)
        if platform is None:
            raise HTTPException(status_code=404, detail="Platform not found")
        platform_id = platform.id

    if platform_id is None:
        return {"items": [], "total": 0, "limit": limit, "offset": offset}

    items, total = await rom_handler.list_for_platform(
        platform_id, search=search, sort=sort, limit=limit, offset=offset
    )

    def _serial(rom) -> dict:
        return {
            "id":              rom.id,
            "platform_id":     rom.platform_id,
            "fs_name":         rom.fs_name,
            "fs_name_no_ext":  rom.fs_name_no_ext,
            "fs_extension":    rom.fs_extension,
            "fs_size_bytes":   rom.fs_size_bytes,
            "name":            rom.name or rom.fs_name_no_ext,
            "slug":            rom.slug,
            "cover_path":      rom.cover_path,
            "cover_type":      rom.cover_type,
            "cover_aspect":    rom.cover_aspect,
            "background_path": rom.background_path,
            "wheel_path":      rom.wheel_path,
            "video_path":      rom.video_path,
            "steamgrid_path":  rom.steamgrid_path,
            "genres":          rom.genres,
            "regions":         rom.regions,
            "release_year":    rom.release_year,
            "rating":          rom.rating,
            "ss_score":        rom.ss_score,
            "igdb_rating":     rom.igdb_rating,
            "lb_rating":       rom.lb_rating,
            "plugin_ratings":  rom.plugin_ratings,
            "player_count":    rom.player_count,
            "is_identified":   rom.is_identified,
        }

    return {
        "items":  [_serial(r) for r in items],
        "total":  total,
        "limit":  limit,
        "offset": offset,
    }


# ── ROM streaming for in-browser emulator (literal, before /{rom_id}) ───────────

@protected_route(router.get, "/stream/{rom_id}", scopes=[Scopes.LIBRARY_READ])
async def stream_rom(request: Request, rom_id: int):
    """Stream ROM binary for EmulatorJS. Auth required (Bearer token in header)."""
    rom = await rom_handler.get_by_id(rom_id)
    if not rom:
        raise HTTPException(status_code=404, detail="ROM not found")
    abs_path = Path(rom.fs_path) / rom.fs_name
    if not abs_path.exists():
        raise HTTPException(status_code=404, detail="ROM file not found on disk")
    # Path traversal guard
    roms_base = os.path.realpath(await _get_roms_path())
    if not os.path.realpath(str(abs_path)).startswith(roms_base):
        raise HTTPException(status_code=403, detail="Access denied")
    import mimetypes
    mime, _ = mimetypes.guess_type(rom.fs_name)
    return FileResponse(
        str(abs_path),
        filename=rom.fs_name,
        media_type=mime or "application/octet-stream",
    )


# ── Home literal routes (MUST be before /{rom_id} to avoid route capture) ──────

@protected_route(router.get, "/recent", scopes=[Scopes.LIBRARY_READ])
async def get_recent_roms(request: Request, limit: int = 24) -> list[dict]:
    """Return the most recently added ROMs across all platforms (for home page row)."""
    roms = await rom_handler.get_recent(limit=min(limit, 48))
    return [
        {
            "id":                   rom.id,
            "name":                 rom.name or rom.fs_name_no_ext,
            "cover_path":           rom.cover_path,
            "cover_type":           rom.cover_type,
            "cover_aspect":         rom.cover_aspect,
            "background_path":      rom.background_path,
            "platform_slug":        rom.platform.slug    if rom.platform else None,
            "platform_fs_slug":     rom.platform.fs_slug if rom.platform else None,
            "platform_name":        (rom.platform.custom_name or rom.platform.name) if rom.platform else None,
            "platform_cover_aspect": _get_cover_aspect(rom.platform.fs_slug) if rom.platform else "3/4",
        }
        for rom in roms
    ]


@protected_route(router.get, "/summary", scopes=[Scopes.LIBRARY_READ])
async def get_summary(request: Request) -> dict:
    """Return stats for the home page Emulation Library card."""
    total_roms, platforms, sample = await asyncio.gather(
        rom_platform_handler.total_roms(),
        rom_platform_handler.get_all_with_counts(),
        rom_platform_handler.sample_platform_with_hero(),
    )
    return {
        "total_roms":      total_roms,
        "platform_count":  len(platforms),
        "sample_fs_slug":  sample["fs_slug"]   if sample else None,
        "sample_hero":     sample["hero_path"]  if sample else None,
    }


# ── ROM metadata search ───────────────────────────────────────────────────────

@protected_route(router.get, "/search", scopes=[Scopes.LIBRARY_READ])
async def search_roms_metadata(
    request: Request,
    query: str = "",
    platform_slug: str = "",
) -> list[dict]:
    """Search ScreenScraper and IGDB for ROM metadata candidates."""
    if not query.strip():
        return []
    import asyncio
    from handler.config.config_handler import config_handler
    from handler.metadata import screenscraper_handler, igdb_rom_handler
    from handler.metadata.rom_platform_map import get_ss_id, get_igdb_id

    ss_user = await config_handler.get("screenscraper_username") or ""
    ss_pass = await config_handler.get("screenscraper_password") or ""
    igdb_cid = await config_handler.get("igdb_client_id") or ""
    igdb_sec = await config_handler.get("igdb_client_secret") or ""

    ss_system_id     = get_ss_id(platform_slug)   if platform_slug else None
    igdb_platform_id = get_igdb_id(platform_slug) if platform_slug else None

    async def _empty() -> list:
        return []

    tasks = []
    if ss_user and ss_pass:
        tasks.append(screenscraper_handler.search_games(
            query.strip(), ss_system_id, username=ss_user, password=ss_pass))
    else:
        tasks.append(_empty())

    if igdb_cid and igdb_sec:
        tasks.append(igdb_rom_handler.search_games(
            query.strip(), igdb_platform_id, client_id=igdb_cid, client_secret=igdb_sec))
    else:
        tasks.append(_empty())

    from handler.metadata import launchbox_handler
    from handler.metadata.rom_platform_map import get_launchbox_name

    lb_platform = get_launchbox_name(platform_slug) if platform_slug else None

    async def _lb_search():
        try:
            return await asyncio.wait_for(
                launchbox_handler.search_candidates(query.strip(), lb_platform),
                timeout=10.0,
            )
        except (asyncio.TimeoutError, Exception) as _e:
            logger.debug("LB search skipped: %s", _e)
            return []

    tasks.append(_lb_search())

    results = await asyncio.gather(*tasks, return_exceptions=True)
    ss_results   = results[0] if isinstance(results[0], list) else []
    igdb_results = results[1] if isinstance(results[1], list) else []
    lb_candidates = results[2] if isinstance(results[2], list) else []

    lb_results: list[dict] = []
    for r in lb_candidates:
        _lb_id = r.get("launchbox_id")
        _box = launchbox_handler.get_box_front(_lb_id) if _lb_id and launchbox_handler._db_ready else None
        lb_results.append({
            "source":       "launchbox",
            "ss_id":        None,
            "igdb_id":      None,
            "launchbox_id": _lb_id,
            "name":         r.get("name") or "",
            "year":         r.get("release_year"),
            "developer":    r.get("developer"),
            "cover_url":    _box["url"] if _box else None,
            "regions":      [],
        })

    # ── SteamGridDB search ────────────────────────────────────────────────────
    sgdb_results: list[dict] = []
    try:
        from urllib.parse import quote as _url_quote
        _sgdb_key = await config_handler.get("steamgriddb_api_key")
        if _sgdb_key:
            _hdrs = {"Authorization": f"Bearer {_sgdb_key}"}
            _encoded_query = _url_quote(query.strip())
            async with httpx.AsyncClient(timeout=12) as _c:
                _rs = await _c.get(
                    f"https://www.steamgriddb.com/api/v2/search/autocomplete/{_encoded_query}",
                    headers=_hdrs,
                )
                logger.info("[SGDB search] status=%d query=%s", _rs.status_code, query.strip())
                if _rs.status_code == 200:
                    _games = _rs.json().get("data", [])[:6]
                    logger.info("[SGDB search] found %d games", len(_games))

                    async def _fetch_cover(_gid: int, _gname: str, _gdate: str | None) -> dict:
                        _cover_url = None
                        try:
                            _rg = await _c.get(
                                f"https://www.steamgriddb.com/api/v2/grids/game/{_gid}",
                                params={"dimensions": "342x482,600x900", "limit": 1},
                                headers=_hdrs,
                            )
                            if _rg.status_code == 200:
                                _items = _rg.json().get("data", [])
                                if _items:
                                    _cover_url = _items[0].get("url")
                        except Exception:
                            pass
                        return {
                            "source":    "sgdb",
                            "sgdb_id":   _gid,
                            "ss_id":     None,
                            "igdb_id":   None,
                            "name":      _gname,
                            "year":      (_gdate or "")[:4] or None,
                            "developer": None,
                            "cover_url": _cover_url,
                            "regions":   [],
                        }

                    sgdb_results = list(await asyncio.gather(*[
                        _fetch_cover(g["id"], g.get("name", ""), g.get("release_date"))
                        for g in _games
                    ]))
    except Exception as _e:
        logger.warning("SGDB search error: %s", _e)

    return ss_results + igdb_results + lb_results + sgdb_results


# ── ROM detail ────────────────────────────────────────────────────────────────

@protected_route(router.get, "/{rom_id}", scopes=[Scopes.LIBRARY_READ])
async def get_rom(request: Request, rom_id: int) -> dict:
    rom = await rom_handler.get_with_platform(rom_id)
    if rom is None:
        raise HTTPException(status_code=404, detail="ROM not found")
    return {
        "id":              rom.id,
        "platform_id":     rom.platform_id,
        "platform_slug":    rom.platform.slug    if rom.platform else None,
        "platform_fs_slug": rom.platform.fs_slug if rom.platform else None,
        "platform_name":   (rom.platform.custom_name or rom.platform.name) if rom.platform else None,
        "cover_aspect":    rom.cover_aspect or (_get_cover_aspect(rom.platform.fs_slug) if rom.platform else "3/4"),
        "fs_name":         rom.fs_name,
        "fs_name_no_ext":  rom.fs_name_no_ext,
        "fs_extension":    rom.fs_extension,
        "fs_size_bytes":   rom.fs_size_bytes,
        "name":            rom.name or rom.fs_name_no_ext,
        "slug":            rom.slug,
        "summary":         rom.summary,
        "developer":         rom.developer,
        "developer_ss_id":   rom.developer_ss_id,
        "publisher":         rom.publisher,
        "publisher_ss_id":   rom.publisher_ss_id,
        "release_year":    rom.release_year,
        "genres":          rom.genres,
        "regions":         rom.regions,
        "languages":       rom.languages,
        "tags":            rom.tags,
        "rating":            rom.rating,
        "ss_score":          rom.ss_score,
        "igdb_rating":       rom.igdb_rating,
        "lb_rating":         rom.lb_rating,
        "plugin_ratings":    rom.plugin_ratings,
        "player_count":      rom.player_count,
        "alternative_names": rom.alternative_names,
        "franchises":        rom.franchises,
        "cover_path":      rom.cover_path,
        "cover_type":      rom.cover_type,
        "background_path": rom.background_path,
        "screenshots":     rom.screenshots,
        "support_path":    rom.support_path,
        "wheel_path":      rom.wheel_path,
        "bezel_path":      rom.bezel_path,
        "steamgrid_path":  rom.steamgrid_path,
        "video_path":      rom.video_path,
        "picto_path":      rom.picto_path,
        "is_identified":   rom.is_identified,
        "igdb_id":         rom.igdb_id,
        "ss_id":           rom.ss_id,
        "launchbox_id":    rom.launchbox_id,
        "hltb_id":          rom.hltb_id,
        "hltb_main_s":      rom.hltb_main_s,
        "hltb_extra_s":     rom.hltb_extra_s,
        "hltb_complete_s":  rom.hltb_complete_s,
    }


# ── ROM metadata update ───────────────────────────────────────────────────────

@protected_route(router.patch, "/{rom_id}", scopes=[Scopes.LIBRARY_WRITE])
async def update_rom_metadata(
    request: Request,
    rom_id: int,
    body: RomMetadataUpdate,
) -> dict:
    """Manually update ROM metadata fields."""
    from handler.metadata.rom_scrape_handler import _download_image, _rom_media_dir, _resource_url

    rom = await rom_handler.get_with_platform(rom_id)
    if rom is None:
        raise HTTPException(status_code=404, detail="ROM not found")

    platform_slug = rom.platform.slug if rom.platform else "unknown"
    media_dir = _rom_media_dir(platform_slug, rom_id)

    data: dict = {}
    if body.name is not None:         data["name"] = body.name
    if body.summary is not None:      data["summary"] = body.summary
    if body.developer is not None:    data["developer"] = body.developer
    if body.publisher is not None:    data["publisher"] = body.publisher
    if body.release_year is not None: data["release_year"] = body.release_year
    if body.genres is not None:       data["genres"] = body.genres
    if body.regions is not None:      data["regions"] = body.regions
    if body.languages is not None:    data["languages"] = body.languages
    if body.rating is not None:       data["rating"] = body.rating
    if body.player_count is not None: data["player_count"] = body.player_count
    if body.hltb_id is not None:        data["hltb_id"]        = body.hltb_id
    if body.hltb_main_s is not None:    data["hltb_main_s"]    = body.hltb_main_s
    if body.hltb_extra_s is not None:   data["hltb_extra_s"]   = body.hltb_extra_s
    if body.hltb_complete_s is not None: data["hltb_complete_s"] = body.hltb_complete_s
    if body.cover_path is not None:       data["cover_path"] = body.cover_path
    if body.background_path is not None:  data["background_path"] = body.background_path
    if body.screenshots is not None:      data["screenshots"] = body.screenshots
    if body.support_path is not None:     data["support_path"] = body.support_path
    if body.wheel_path is not None:       data["wheel_path"] = body.wheel_path
    if body.bezel_path is not None:       data["bezel_path"] = body.bezel_path
    if body.steamgrid_path is not None:   data["steamgrid_path"] = body.steamgrid_path
    if body.video_path is not None:       data["video_path"] = body.video_path
    if body.picto_path is not None:       data["picto_path"] = body.picto_path

    # Download cover if URL provided
    if body.cover_url:
        import re
        ext = re.sub(r"\?.*", "", body.cover_url.rsplit(".", 1)[-1]).lower() or "jpg"
        if media_dir.exists():
            for old in media_dir.glob("cover.*"):
                old.unlink(missing_ok=True)
        dest = media_dir / f"cover.{ext}"
        saved = await _download_image(body.cover_url, dest)
        if saved:
            data["cover_path"] = _resource_url(platform_slug, rom_id, saved.name)

    # Download background if URL provided
    if body.background_url:
        import re
        ext = re.sub(r"\?.*", "", body.background_url.rsplit(".", 1)[-1]).lower() or "jpg"
        if media_dir.exists():
            for old in media_dir.glob("background.*"):
                old.unlink(missing_ok=True)
        dest = media_dir / f"background.{ext}"
        saved = await _download_image(body.background_url, dest)
        if saved:
            data["background_path"] = _resource_url(platform_slug, rom_id, saved.name)

    # Download extra media if URLs provided
    _extra_media = [
        ("support_url",   "support"),
        ("wheel_url",     "wheel"),
        ("bezel_url",     "bezel"),
        ("steamgrid_url", "steamgrid"),
        ("video_url",     "video"),
    ]
    for url_field, fname in _extra_media:
        url_val = getattr(body, url_field)
        if url_val:
            import re as _re
            _ext = _re.sub(r"\?.*", "", url_val.rsplit(".", 1)[-1]).lower() or "jpg"
            # Remove existing files so _download_image doesn't skip them
            for _old in media_dir.glob(f"{fname}.*"):
                _old.unlink(missing_ok=True)
            _dest = media_dir / f"{fname}.{_ext}"
            saved = await _download_image(url_val, _dest)
            if saved:
                data[f"{fname}_path"] = _resource_url(platform_slug, rom_id, saved.name)

    if data:
        await rom_handler.update_metadata(rom_id, data)

    updated = await rom_handler.get_with_platform(rom_id)
    if updated is None:
        return {"ok": True}
    return {
        "id":              updated.id,
        "name":            updated.name,
        "cover_path":      updated.cover_path,
        "background_path": updated.background_path,
    }


# ── ROM all-media (SS + IGDB combined) ────────────────────────────────────────

def _empty_all_media() -> dict:
    return {
        "covers": [], "fanarts": [], "screenshots": [],
        "supports": [], "wheels": [], "bezels": [],
        "steamgrids": [], "videos": [], "details": None,
    }


def _extract_ss_details(game: dict) -> dict:
    """Extract human-readable details dict from raw SS jeu."""
    names = game.get("noms") or []
    name = names[0].get("text") if names else None

    synopsis = game.get("synopsis") or []
    description = ""
    for s in synopsis:
        if s.get("langue") in ("en", ""):
            description = s.get("text", "")
            break
    if not description and synopsis:
        description = synopsis[0].get("text", "")

    dev = game.get("developpeur") or {}
    developer = dev.get("text") if isinstance(dev, dict) else (str(dev) if dev else None)
    pub = game.get("editeur") or {}
    publisher = pub.get("text") if isinstance(pub, dict) else (str(pub) if pub else None)

    year = None
    for d in (game.get("dates") or []):
        raw = d.get("text", "")
        if raw and len(raw) >= 4:
            try:
                year = int(raw[:4])
                break
            except ValueError:
                pass

    genres_raw = game.get("genres") or []
    genres: list[str] = []
    for g in genres_raw:
        noms_g = g.get("noms") or []
        for n in noms_g:
            if n.get("langue") in ("en", ""):
                genres.append(n.get("text", ""))
                break
        else:
            if noms_g:
                genres.append(noms_g[0].get("text", ""))

    rating = None
    note = game.get("note") or {}
    if isinstance(note, dict) and note.get("text"):
        try:
            rating = float(str(note["text"]).replace(",", "."))
        except (ValueError, TypeError):
            pass

    regions_raw = game.get("regions") or {}
    regions: list[str] = []
    if isinstance(regions_raw, list):
        regions = [r.get("shortname", "") for r in regions_raw if r.get("shortname")]
    elif isinstance(regions_raw, dict):
        sn = regions_raw.get("shortname")
        if sn:
            regions = [sn]

    players_raw = game.get("joueurs") or {}
    player_count = players_raw.get("text") if isinstance(players_raw, dict) else None

    return {
        "name":         name,
        "description":  description,
        "developer":    developer,
        "publisher":    publisher,
        "release_year": year,
        "genres":       genres,
        "regions":      regions,
        "rating":       rating,
        "player_count": player_count,
    }


def _extract_igdb_details(game: dict) -> dict:
    """Extract human-readable details dict from raw IGDB game."""
    developer = publisher = None
    for ic in (game.get("involved_companies") or []):
        co = (ic.get("company") or {}).get("name")
        if ic.get("developer") and not developer:
            developer = co
        if ic.get("publisher") and not publisher:
            publisher = co

    year = None
    ts = game.get("first_release_date")
    if ts:
        from datetime import datetime, timezone
        year = datetime.fromtimestamp(ts, tz=timezone.utc).year

    genres = [g["name"] for g in (game.get("genres") or [])]

    rating = game.get("rating")
    if rating:
        rating = round(rating, 1)  # keep IGDB 0-100 scale

    return {
        "name":         game.get("name"),
        "description":  game.get("summary") or "",
        "developer":    developer,
        "publisher":    publisher,
        "release_year": year,
        "genres":       genres,
        "regions":      [],
        "rating":       rating,
        "player_count": None,
    }


@protected_route(router.get, "/{rom_id}/all-media", scopes=[Scopes.LIBRARY_READ])
async def get_rom_all_media(
    request: Request,
    rom_id: int,
    ss_id: str | None = None,
    igdb_id: int | None = None,
    igdb_query: str | None = None,
    platform_slug: str | None = None,
    launchbox_id: str | None = None,
    sgdb_id: int | None = None,
) -> dict:
    """Fetch all media (SS + IGDB) for a ROM and merge them.

    Returns all media categories from SS merged with covers/fanarts/screenshots from IGDB.
    SS details are primary; IGDB details used as fallback.
    """
    import asyncio
    from handler.config.config_handler import config_handler
    from handler.metadata import screenscraper_handler, igdb_rom_handler
    from handler.metadata.rom_platform_map import get_ss_id, get_igdb_id as _get_igdb_id

    rom = await rom_handler.get_with_platform(rom_id)
    if rom is None:
        raise HTTPException(status_code=404, detail="ROM not found")

    slug = platform_slug or (rom.platform.slug if rom.platform else None)
    ss_system_id = get_ss_id(slug) if slug else None

    ss_user = await config_handler.get("screenscraper_username") or ""
    ss_pass = await config_handler.get("screenscraper_password") or ""
    devid   = await config_handler.get("screenscraper_devid") or ""
    devpw   = await config_handler.get("screenscraper_devpassword") or ""
    igdb_cid = await config_handler.get("igdb_client_id") or ""
    igdb_sec = await config_handler.get("igdb_client_secret") or ""

    game_ss_id = ss_id or rom.ss_id

    async def _fetch_ss():
        if not game_ss_id or not ss_user or not ss_pass:
            return None
        return await screenscraper_handler.get_game_by_id(
            game_ss_id, username=ss_user, password=ss_pass, devid=devid, devpassword=devpw,
            ss_system_id=ss_system_id,
        )

    async def _fetch_igdb():
        if not igdb_cid or not igdb_sec:
            return None
        # Use explicit igdb_id first, otherwise search by query
        _id = igdb_id
        if _id:
            return await igdb_rom_handler.get_game_by_id(_id, client_id=igdb_cid, client_secret=igdb_sec)
        elif igdb_query:
            igdb_plat_id = _get_igdb_id(slug) if slug else None
            return await igdb_rom_handler.search_game(
                igdb_query, igdb_plat_id, client_id=igdb_cid, client_secret=igdb_sec)
        return None

    ss_game, igdb_game = await asyncio.gather(_fetch_ss(), _fetch_igdb(), return_exceptions=True)
    if isinstance(ss_game, Exception):
        logger.warning("[all-media] SS fetch error: %s", ss_game)
        ss_game = None
    if isinstance(igdb_game, Exception):
        logger.warning("[all-media] IGDB fetch error: %s", igdb_game)
        igdb_game = None

    # Extract media from each source
    ss_media   = screenscraper_handler.extract_media_urls(ss_game)   if ss_game   else {}
    igdb_media = igdb_rom_handler.extract_media_urls(igdb_game)      if igdb_game else {}

    # Debug: log what was found
    if ss_game:
        raw_types = sorted({m.get("type","?") for m in (ss_game.get("medias") or [])})
        logger.info("[all-media] SS game_id=%s found - raw media types: %s", game_ss_id, raw_types)
        logger.info("[all-media] SS categorised - covers:%d fanarts:%d screenshots:%d supports:%d wheels:%d bezels:%d steamgrids:%d videos:%d",
            len(ss_media.get("covers",[])), len(ss_media.get("fanarts",[])),
            len(ss_media.get("screenshots",[])), len(ss_media.get("supports",[])),
            len(ss_media.get("wheels",[])), len(ss_media.get("bezels",[])),
            len(ss_media.get("steamgrids",[])), len(ss_media.get("videos",[])))
        # Debug: log first 3 cover URLs to check format
        for c in ss_media.get("covers", [])[:3]:
            logger.info("[all-media] cover sample: type=%s region=%s url=%s", c.get("type"), c.get("region"), c.get("url","")[:120])
    else:
        logger.info("[all-media] SS returned no data (ss_id=%s ss_user=%s)", game_ss_id, bool(ss_user))
    if igdb_game:
        logger.info("[all-media] IGDB game='%s' found - covers:%d fanarts:%d screenshots:%d",
            igdb_game.get("name"), len(igdb_media.get("covers",[])),
            len(igdb_media.get("fanarts",[])), len(igdb_media.get("screenshots",[])))
    else:
        logger.info("[all-media] IGDB returned no data (igdb_id=%s igdb_query=%s igdb_cid=%s)", igdb_id, igdb_query, bool(igdb_cid))

    # Merge covers, fanarts, screenshots (SS first, then IGDB)
    combined_covers      = (ss_media.get("covers", []))      + (igdb_media.get("covers", []))
    combined_fanarts     = (ss_media.get("fanarts", []))     + (igdb_media.get("fanarts", []))
    combined_screenshots = (ss_media.get("screenshots", [])) + (igdb_media.get("screenshots", []))

    # SS-only categories
    supports   = ss_media.get("supports", [])
    wheels     = list(ss_media.get("wheels", []))
    bezels     = ss_media.get("bezels", [])
    steamgrids = ss_media.get("steamgrids", [])
    videos     = ss_media.get("videos", [])

    # ── LaunchBox: full image + metadata provider ──────────────────────────────
    _lb_game_data: dict | None = None
    try:
        from handler.metadata import launchbox_handler as _lb
        _lb_id = launchbox_id or rom.launchbox_id
        if _lb_id and _lb._db_ready:
            # Covers: Box - Front, Box - 3D, Fanart - Box - Front
            for _cov in _lb.get_box_fronts(_lb_id):
                combined_covers.append({
                    "url":    _cov["url"],
                    "type":   _cov["type"].lower().replace(" ", "-"),
                    "region": "",
                    "label":  _cov["type"],
                    "source": "lb",
                })
            # Heroes: Fanart - Background, Banner
            for _fan in _lb.get_fanarts(_lb_id):
                combined_fanarts.append({
                    "url":    _fan["url"],
                    "type":   "fanart",
                    "region": "",
                    "label":  _fan["type"],
                    "source": "lb",
                })
            # Clear Logo -> wheels
            for _logo in _lb.get_clear_logos(_lb_id):
                wheels.append({
                    "url":    _logo["url"],
                    "type":   "clearlogo",
                    "region": "",
                    "label":  "Clear Logo",
                    "source": "lb",
                })
            # Screenshots
            for _ss in _lb.get_lb_screenshots(_lb_id):
                combined_screenshots.append({
                    "url":    _ss["url"],
                    "type":   _ss["type"],
                    "region": "",
                    "label":  _ss["type"],
                    "source": "lb",
                })
            # Get metadata for detail_sources
            _lb_game_data = _lb._db_get_game_by_id(str(_lb_id))
    except Exception as _e:
        logger.debug("LB image/metadata lookup error: %s", _e)

    # Details: return all sources separately for multi-source UI
    detail_sources: list[dict] = []
    if ss_game:
        ss_det = _extract_ss_details(ss_game)
        ss_det["source"] = "ss"
        ss_det["source_name"] = "ScreenScraper"
        detail_sources.append(ss_det)
    if igdb_game:
        igdb_det = _extract_igdb_details(igdb_game)
        igdb_det["source"] = "igdb"
        igdb_det["source_name"] = f"IGDB - {igdb_game.get('name', '')}"
        detail_sources.append(igdb_det)
    if _lb_game_data:
        import json as _json
        _lb_genres = _lb_game_data.get("genres") or []
        if isinstance(_lb_genres, str):
            try:
                _lb_genres = _json.loads(_lb_genres)
            except Exception:
                _lb_genres = []
        detail_sources.append({
            "source":       "lb",
            "source_name":  f"LaunchBox - {_lb_game_data.get('name', '')}",
            "name":         _lb_game_data.get("name"),
            "description":  _lb_game_data.get("summary") or "",
            "developer":    _lb_game_data.get("developer"),
            "publisher":    _lb_game_data.get("publisher"),
            "release_year": _lb_game_data.get("release_year"),
            "genres":       _lb_genres,
            "regions":      [],
            "rating":       _lb_game_data.get("rating"),
            "player_count": _lb_game_data.get("player_count"),
        })
    # ── Plugins: covers, heroes, logos, screenshots, details ────────────────
    plugin_covers:  list[dict] = []
    plugin_fanarts: list[dict] = []
    plugin_wheels:  list[dict] = []
    try:
        from plugins.manager import plugin_manager
        from pathlib import Path as _Path
        from config import PLUGINS_PATH as _PP

        _search_q = rom.name or rom.fs_name_no_ext or ""

        def _resolve_plugin_id(pid: str) -> str:
            if _Path(_PP, pid).is_dir():
                return pid
            for sfx in ["-metadata", "-scraper", "-plugin"]:
                if _Path(_PP, pid + sfx).is_dir():
                    return pid + sfx
            return pid

        def _tag_plugin_results(items: list, target: list) -> None:
            for r in items:
                if not isinstance(r, dict):
                    continue
                pid = (r.get("_source") or "").lower().replace(" ", "")
                r["source"] = "plugin"
                r["_sourceIcon"] = f"/api/plugins/{_resolve_plugin_id(pid)}/logo"
                target.append(r)

        # Covers
        for pr in plugin_manager.hook.metadata_get_covers(query=_search_q):
            if isinstance(pr, list):
                _tag_plugin_results(pr, plugin_covers)

        # Heroes
        for pr in plugin_manager.hook.metadata_get_heroes(query=_search_q):
            if isinstance(pr, list):
                _tag_plugin_results(pr, plugin_fanarts)

        # Logos
        for pr in plugin_manager.hook.metadata_get_logos(query=_search_q):
            if isinstance(pr, list):
                _tag_plugin_results(pr, plugin_wheels)

        # Screenshots + detail_sources via metadata_search_game -> metadata_get_game
        try:
            all_search = plugin_manager.hook.metadata_search_game(query=_search_q)
            for provider_results in all_search:
                if not isinstance(provider_results, list) or not provider_results:
                    continue
                best = provider_results[0]
                pid = best.get("provider_id", "")
                gid = best.get("provider_game_id", "")
                if not pid or not gid:
                    continue
                game_data_list = plugin_manager.hook.metadata_get_game(provider_game_id=gid)
                for gd in game_data_list:
                    if not isinstance(gd, dict) or gd.get("provider_id") != pid:
                        continue
                    plugin_id = _resolve_plugin_id(pid)
                    # Screenshots
                    for ss_url in (gd.get("screenshots") or []):
                        combined_screenshots.append({
                            "url": ss_url, "type": "screenshot", "region": "",
                            "label": gd.get("title", pid), "source": "plugin",
                            "_sourceIcon": f"/api/plugins/{plugin_id}/logo",
                        })
                    # Detail source
                    _p_desc = gd.get("description") or gd.get("summary") or ""
                    _p_rating = gd.get("rating")
                    if _p_desc or gd.get("developer") or _p_rating is not None:
                        detail_sources.append({
                            "source":       pid,
                            "source_name":  f"{best.get('name', pid)}",
                            "name":         gd.get("title"),
                            "description":  _p_desc,
                            "developer":    gd.get("developer"),
                            "publisher":    gd.get("publisher"),
                            "release_year": gd.get("release_year"),
                            "genres":       gd.get("genres") or [],
                            "regions":      [],
                            "rating":       _p_rating,
                            "player_count": gd.get("player_count"),
                        })
                    break
        except Exception as _pe:
            logger.debug("Plugin search/game fetch error: %s", _pe)

    except Exception as _e:
        logger.debug("Plugin fetch error in ROM all-media: %s", _e)

    # Backward compat: merged details (SS primary, IGDB fallback, LB last)
    details = detail_sources[0] if detail_sources else None

    # ── SteamGridDB: covers, heroes, logos, icons ─────────────────────────────
    sgdb_covers:  list[dict] = []
    sgdb_heroes:  list[dict] = []
    sgdb_logos:   list[dict] = []
    sgdb_icons:   list[dict] = []
    try:
        from handler.config.config_handler import config_handler as _ch
        _sgdb_key = await _ch.get("steamgriddb_api_key")
        if _sgdb_key:
            _hdrs = {"Authorization": f"Bearer {_sgdb_key}"}
            _resolved_sgdb_id: int | None = sgdb_id  # use caller-supplied ID directly if available
            async with httpx.AsyncClient(timeout=15) as _c:
                if not _resolved_sgdb_id:
                    # Resolve game name → SGDB ID via autocomplete
                    from urllib.parse import quote as _uq
                    _game_name = (ss_game or {}).get("noms", [{}])[0].get("text") if ss_game else None
                    if not _game_name and igdb_game:
                        _game_name = igdb_game.get("name")
                    if not _game_name:
                        _rom_obj = await rom_handler.get_with_platform(rom_id)
                        _game_name = (_rom_obj.name or _rom_obj.fs_name_no_ext) if _rom_obj else None
                    if _game_name:
                        _rs = await _c.get(
                            f"https://www.steamgriddb.com/api/v2/search/autocomplete/{_uq(_game_name)}",
                            headers=_hdrs,
                        )
                        if _rs.status_code == 200:
                            _sg = _rs.json().get("data", [])
                            if _sg:
                                _resolved_sgdb_id = _sg[0]["id"]

                if _resolved_sgdb_id:
                    # Run all four asset fetches concurrently
                    async def _sgdb_get(path: str, params: dict) -> list:
                        try:
                            _r = await _c.get(
                                f"https://www.steamgriddb.com/api/v2/{path}/game/{_resolved_sgdb_id}",
                                params=params, headers=_hdrs,
                            )
                            return _r.json().get("data", []) if _r.status_code == 200 else []
                        except Exception:
                            return []

                    _grids, _heroes, _logos, _icons = await asyncio.gather(
                        _sgdb_get("grids",  {"dimensions": "342x482,600x900", "limit": 20}),
                        _sgdb_get("heroes", {"limit": 10}),
                        _sgdb_get("logos",  {"limit": 10}),
                        _sgdb_get("icons",  {"limit": 10}),
                    )
                    for _item in _grids[:12]:
                        sgdb_covers.append({
                            "url":    _item["url"],
                            "type":   "steamgrid",
                            "region": "",
                            "label":  f"SGDB {_item.get('width','?')}×{_item.get('height','?')}",
                            "source": "sgdb",
                        })
                    for _item in _heroes[:8]:
                        sgdb_heroes.append({
                            "url":    _item["url"],
                            "type":   "fanart",
                            "region": "",
                            "label":  f"SGDB hero {_item.get('width','?')}×{_item.get('height','?')}",
                            "source": "sgdb",
                        })
                    for _item in _logos[:8]:
                        sgdb_logos.append({
                            "url":    _item["url"],
                            "type":   "logo",
                            "region": "",
                            "label":  "SGDB Logo",
                            "source": "sgdb",
                        })
                    for _item in _icons[:8]:
                        sgdb_icons.append({
                            "url":    _item["url"],
                            "type":   "icon",
                            "region": "",
                            "label":  f"SGDB icon {_item.get('width','?')}×{_item.get('height','?')}",
                            "source": "sgdb",
                        })
    except Exception as _e:
        logger.debug("SGDB fetch error in all-media: %s", _e)

    return {
        "covers":         combined_covers + plugin_covers + sgdb_covers,
        "fanarts":        combined_fanarts + plugin_fanarts + sgdb_heroes,
        "screenshots":    combined_screenshots,
        "supports":       supports,
        "wheels":         wheels + plugin_wheels + sgdb_logos,
        "bezels":         bezels,
        "steamgrids":     steamgrids + sgdb_icons,
        "videos":         videos,
        "details":        details,
        "detail_sources": detail_sources,
    }


# Backward-compat alias
@protected_route(router.get, "/{rom_id}/ss-media", scopes=[Scopes.LIBRARY_READ])
async def get_rom_ss_media(
    request: Request,
    rom_id: int,
    ss_id: str | None = None,
    platform_slug: str | None = None,
) -> dict:
    """Backward-compat alias for /{rom_id}/all-media (SS only)."""
    return await get_rom_all_media(
        request, rom_id,
        ss_id=ss_id, igdb_id=None, igdb_query=None, platform_slug=platform_slug,
    )


# ── ROM download ──────────────────────────────────────────────────────────────

@protected_route(router.get, "/{rom_id}/download", scopes=[Scopes.LIBRARY_READ])
async def download_rom(request: Request, rom_id: int) -> FileResponse:
    rom = await rom_handler.get_by_id(rom_id)
    if rom is None:
        raise HTTPException(status_code=404, detail="ROM not found")
    file_path = Path(rom.fs_path) / rom.fs_name
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="ROM file not found on disk")
    # Path traversal guard
    roms_base = os.path.realpath(await _get_roms_path())
    if not os.path.realpath(str(file_path)).startswith(roms_base):
        raise HTTPException(status_code=403, detail="Access denied")
    return FileResponse(
        path=str(file_path),
        filename=rom.fs_name,
        media_type="application/octet-stream",
    )


# ── Clear metadata ────────────────────────────────────────────────────────────

@protected_route(router.post, "/{rom_id}/clear-metadata", scopes=[Scopes.LIBRARY_WRITE])
async def clear_rom_metadata(request: Request, rom_id: int) -> dict:
    """Clear all scraped metadata for a single ROM (keeps file info + hashes)."""
    result = await rom_handler.clear_metadata(rom_id)
    if result is None:
        raise HTTPException(status_code=404, detail="ROM not found")
    return {"ok": True}


@protected_route(router.post, "/platforms/{slug}/clear-metadata", scopes=[Scopes.LIBRARY_WRITE])
async def clear_platform_metadata(request: Request, slug: str) -> dict:
    """Clear scraped metadata for ALL ROMs on a platform."""
    platform = await rom_platform_handler.get_by_slug(slug)
    if platform is None:
        raise HTTPException(status_code=404, detail="Platform not found")
    items, _ = await rom_handler.list_for_platform(platform.id, limit=9999)
    count = 0
    for rom_obj in items:
        await rom_handler.clear_metadata(rom_obj.id)
        count += 1
    return {"ok": True, "cleared": count}


@protected_route(router.delete, "/metadata", scopes=[Scopes.LIBRARY_WRITE])
async def clear_all_roms_metadata(request: Request) -> dict:
    """Clear scraped metadata for ALL ROMs across all platforms."""
    count = await rom_handler.clear_all_metadata()
    return {"ok": True, "cleared": count}


# ── ROM Upload ────────────────────────────────────────────────────────────────

@protected_route(router.post, "/platforms/{slug}/upload", scopes=[Scopes.LIBRARY_UPLOAD])
async def upload_roms(
    request: Request,
    slug: str,
    background_tasks: BackgroundTasks,
    files: list[UploadFile] = File(...),
) -> dict:
    """Upload one or more ROM files to a platform directory.

    Creates the directory if it does not exist.  Each file is written in
    256 KB chunks.  After all files land on disk we kick off a ROM scan
    in the background so the uploaded files are inserted into the DB
    without the user having to press "Scan" manually.  Returns the list
    of saved filenames.
    """
    roms_base = await _get_roms_path()
    dest_dir = Path(roms_base) / slug
    dest_dir.mkdir(parents=True, exist_ok=True)

    saved: list[str] = []
    for upload in files:
        if not upload.filename:
            continue
        safe_name = Path(upload.filename).name          # strip any directory parts
        dest_path = dest_dir / safe_name
        try:
            with open(dest_path, "wb") as fh:
                while chunk := await upload.read(256 * 1024):
                    fh.write(chunk)
            saved.append(safe_name)
            logger.info("ROM uploaded: %s → %s", safe_name, dest_dir)
        except Exception as exc:
            logger.error("Failed to save ROM %s: %s", safe_name, exc)
            raise HTTPException(status_code=500, detail=f"Failed to save {safe_name}: {exc}")

    # Auto-trigger scan so freshly uploaded ROMs show up in the library
    # without requiring a manual Scan click.  If a scan is already running
    # skip — the in-flight scan will pick up the new files anyway.
    if saved and not _scan_lock.locked():
        async def _post_upload_scan():
            global _scan_running
            async with _scan_lock:
                _scan_running = True
                try:
                    await scan_roms_path(roms_base)
                finally:
                    _scan_running = False

        background_tasks.add_task(_post_upload_scan)

    return {"ok": True, "saved": saved, "platform_slug": slug, "scan_triggered": bool(saved)}


# ── Scan ──────────────────────────────────────────────────────────────────────

@protected_route(router.post, "/scan", scopes=[Scopes.LIBRARY_WRITE])
async def trigger_scan(request: Request, background_tasks: BackgroundTasks) -> dict:
    global _scan_running
    if _scan_lock.locked():
        raise HTTPException(status_code=409, detail="Scan already running")

    roms_path = await _get_roms_path()

    async def _run():
        global _scan_running
        async with _scan_lock:
            _scan_running = True
            try:
                await scan_roms_path(roms_path)
            finally:
                _scan_running = False

    background_tasks.add_task(_run)
    return {"ok": True, "message": "ROM scan started", "path": roms_path}


@protected_route(router.get, "/scan/status", scopes=[Scopes.LIBRARY_READ])
async def scan_status(request: Request) -> dict:
    return {"running": _scan_lock.locked()}


# ── Scrape metadata ───────────────────────────────────────────────────────────

@protected_route(router.post, "/platforms/{slug}/scrape-platform", scopes=[Scopes.LIBRARY_WRITE])
async def scrape_platform_info(
    request: Request,
    slug: str,
    background_tasks: BackgroundTasks,
) -> dict:
    """Fetch ScreenScraper platform info (photo, description, manufacturer, year).

    Works for both real DB platforms and preview-only slugs - scrape_platform_info
    only needs fs_slug, so we pass a minimal stub when the platform is not in DB.
    """
    platform = await rom_platform_handler.get_by_slug(slug)

    # For preview platforms (not in DB) build a minimal stub - the scraper only
    # uses .fs_slug so this is sufficient.
    if platform is None:
        from types import SimpleNamespace
        platform = SimpleNamespace(fs_slug=slug)  # type: ignore[assignment]

    fs_slug = platform.fs_slug  # capture for closure

    async def _run():
        import logging as _log
        _lg = _log.getLogger("platform_scrape")
        try:
            from handler.metadata.rom_scrape_handler import scrape_platform_info as _scrape_info
            result = await _scrape_info(platform)  # type: ignore[arg-type]
            if result:
                all_info = config_manager.get_section("platform_info") or {}
                all_info[fs_slug] = result
                config_manager.save_section("platform_info", all_info)
                _lg.info("[Platform] Info saved for %s: photo=%s icon=%s", fs_slug, result.get("photo_path"), result.get("icon_path"))
            else:
                _lg.warning("[Platform] scrape_platform_info returned empty for %s", fs_slug)
        except Exception as exc:
            _lg.error("[Platform] scrape_platform_info FAILED for %s: %s", fs_slug, exc, exc_info=True)

    background_tasks.add_task(_run)
    return {"ok": True, "message": "Platform info scrape started"}


@protected_route(router.post, "/platforms/{slug}/scrape", scopes=[Scopes.LIBRARY_WRITE])
async def scrape_platform(
    request: Request,
    slug: str,
    background_tasks: BackgroundTasks,
    limit: int = 100000,
    force: bool = False,
) -> dict:
    """Trigger metadata scraping for all ROMs in a platform.

    By default (``force=False``) only ROMs that have not been identified yet
    (no cover_path AND no ss_id/igdb_id/launchbox_id) are queued, so repeat
    clicks don't re-hammer the APIs for ROMs already scraped.  Pass
    ``force=true`` to re-scrape everything.
    """
    platform = await rom_platform_handler.get_by_slug(slug)
    if platform is None:
        raise HTTPException(status_code=404, detail="Platform not found")

    items, _ = await rom_handler.list_for_platform(platform.id, limit=limit)
    if force:
        rom_ids = [r.id for r in items]
    else:
        rom_ids = [
            r.id for r in items
            if not (r.cover_path or r.ss_id or r.igdb_id or r.launchbox_id)
        ]

    async def _run():
        await scrape_roms_batch(rom_ids, platform)

    background_tasks.add_task(_run)
    return {"ok": True, "queued": len(rom_ids), "total": len(items)}


class ScrapeRomBody(BaseModel):
    forced_ss_id: str | None = None
    forced_launchbox_id: str | None = None


@protected_route(router.post, "/{rom_id}/scrape", scopes=[Scopes.LIBRARY_WRITE])
async def scrape_rom(
    request: Request,
    rom_id: int,
    background_tasks: BackgroundTasks,
    body: ScrapeRomBody = ScrapeRomBody(),
) -> dict:
    """Trigger metadata scraping for a single ROM.

    Optional body: { "forced_ss_id": "12345" } or { "forced_launchbox_id": "67890" }
    bypasses normal search and scrapes directly by source ID.
    """
    rom = await rom_handler.get_with_platform(rom_id)
    if rom is None:
        raise HTTPException(status_code=404, detail="ROM not found")

    from handler.metadata.rom_scrape_handler import scrape_rom as _scrape
    platform = rom.platform
    forced_ss_id = body.forced_ss_id or None
    forced_launchbox_id = body.forced_launchbox_id or None

    async def _run():
        data = await _scrape(rom, platform, forced_ss_id=forced_ss_id, forced_launchbox_id=forced_launchbox_id)
        if data:
            await rom_handler.update_metadata(rom_id, data)

    background_tasks.add_task(_run)
    return {"ok": True, "rom_id": rom_id, "forced_ss_id": forced_ss_id, "forced_launchbox_id": forced_launchbox_id}


@protected_route(router.post, "/hltb-rescrape", scopes=[Scopes.LIBRARY_WRITE])
async def hltb_rescrape_roms(
    request: Request,
    background_tasks: BackgroundTasks,
    force: bool = False,
) -> dict:
    """Bulk-rescrape HowLongToBeat playtime for all ROMs.

    force=False (default) - only ROMs missing hltb_main_s.
    force=True            - rescrape every ROM, overwriting existing data.
    """
    from handler.metadata.hltb_bulk_handler import rescrape_roms as _rescrape

    background_tasks.add_task(_rescrape, force)
    return {"ok": True, "message": "HLTB ROM rescrape started in background", "force": force}


# ── Helper ────────────────────────────────────────────────────────────────────

async def _get_roms_path() -> str:
    from config import config_manager
    cfg = config_manager.get_section("roms")
    return cfg.get("library_path") or ROMS_PATH
