"""ROM library endpoints.

Prefix: /api/roms

IMPORTANT: The protected_route decorator always passes `request` as the first
positional argument to the wrapped function.  Therefore every endpoint function
MUST have `request: Request` as its very first parameter, before any path /
query / body params - otherwise FastAPI will receive "multiple values" errors.
"""

from __future__ import annotations

import asyncio
import io
import logging
import os
import zipfile
from datetime import datetime, timezone
from functools import partial
from pathlib import Path

import httpx
from fastapi import APIRouter, BackgroundTasks, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, Response, StreamingResponse
from pydantic import BaseModel

from config import ROMS_PATH, config_manager
from decorators.auth import protected_route
from handler.auth.scopes import Scope as Scopes
from handler.database.rom_handler import rom_handler, rom_platform_handler
from handler.database.save_state_handler import save_state_handler
from handler.filesystem.rom_scanner import (
    SHEET_EXTENSIONS,
    scan_roms_path,
    subchannel_files_for,
    tracks_referenced_by,
)
from handler.roms import chd_jobs, rom_removal
from handler.roms.chd_convert import convertible_disc, disc_inside_archive
from handler.metadata.rom_scrape_handler import scrape_roms_batch
from handler.metadata.rom_platform_map import PLATFORM_MAP, get_cover_aspect as _get_cover_aspect
from utils import download_tickets
from utils.ranged_file import content_disposition
from utils.ratings import rom_rating_agg_of
from utils.async_utils import note_unscanned

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
    ss_score: float | None = None       # ScreenScraper 0-20
    igdb_rating: float | None = None    # IGDB 0-100
    lb_rating: float | None = None      # LaunchBox 0-10
    plugin_ratings: dict | None = None  # {provider_id: {name, rating, logo_url}}
    player_count: str | None = None
    save_disk_name: str | None = None
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

@protected_route(router.get, "/platforms", scopes=[Scopes.PLATFORMS_READ])
async def list_platforms(request: Request) -> list[dict]:
    """List all detected ROM platforms with ROM counts."""
    return await rom_platform_handler.get_all_with_counts()


@protected_route(router.get, "/platforms/known", scopes=[Scopes.PLATFORMS_READ])
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


@protected_route(router.get, "/platforms/metadata", scopes=[Scopes.PLATFORMS_READ])
async def get_platforms_metadata(request: Request) -> dict:
    """Return EmulationStation metadata (colour, descriptions, etc.) for all platforms."""
    from handler.metadata.platform_metadata_handler import get_all as _pm_get_all
    return _pm_get_all()


@protected_route(router.get, "/platforms/{slug}", scopes=[Scopes.PLATFORMS_READ])
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


@protected_route(router.get, "/platforms/{slug}/stored-info", scopes=[Scopes.PLATFORMS_READ])
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


@protected_route(router.patch, "/platforms/{slug}", scopes=[Scopes.PLATFORMS_WRITE])
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

@protected_route(router.get, "", scopes=[Scopes.ROMS_READ])
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
            "rating_agg":      _rom_rating_agg(rom),
            "created_at":      rom.created_at.isoformat() if rom.created_at else None,
        }

    return {
        "items":  [_serial(r) for r in items],
        "total":  total,
        "limit":  limit,
        "offset": offset,
    }


# ── ROM streaming for in-browser emulator (literal, before /{rom_id}) ───────────

@protected_route(router.get, "/stream/{rom_id}", scopes=[Scopes.ROMS_READ])
async def stream_rom(request: Request, rom_id: int):
    """Stream ROM binary for EmulatorJS. Auth required (Bearer token in header)."""
    rom = await rom_handler.get_by_id(rom_id)
    if not rom:
        raise HTTPException(status_code=404, detail="ROM not found")
    abs_path = Path(rom.fs_path) / rom.fs_name
    if not abs_path.exists():
        raise HTTPException(status_code=404, detail="ROM file not found on disk")
    # Path traversal guard. startswith alone compares text, so a sibling whose
    # name merely begins with the base ("/data/games/roms_backup") would pass.
    # Require the base exactly, or the base followed by a separator.
    roms_base = os.path.realpath(await _get_roms_path())
    _resolved = os.path.realpath(str(abs_path))
    if not (_resolved == roms_base or _resolved.startswith(roms_base + os.sep)):
        raise HTTPException(status_code=403, detail="Access denied")
    import mimetypes
    mime, _ = mimetypes.guess_type(rom.fs_name)
    return FileResponse(
        str(abs_path),
        filename=rom.fs_name,
        media_type=mime or "application/octet-stream",
    )


# ── CHD conversion (literal paths, before /{rom_id}) ──────────────────────────

class _ConvertRequest(BaseModel):
    # Asked before the work starts rather than offered afterwards: converting
    # a four disc set with both copies on disk is 3.5 GB where the answer is
    # 1.9 GB, and nobody wants to find that out at the end. False keeps the
    # discs, moved one directory down so the next scan does not file them as
    # a second copy of the same game.
    delete_source: bool = False


@protected_route(router.get, "/convert-chd/jobs", scopes=[Scopes.ROMS_READ])
async def list_chd_jobs(request: Request) -> list[dict]:
    """Conversions this server knows about, so a refreshed page finds them."""
    return chd_jobs.list_jobs()


@protected_route(router.delete, "/convert-chd/jobs/{job_id}", scopes=[Scopes.ROMS_WRITE])
async def cancel_chd_job(request: Request, job_id: int) -> dict:
    return await chd_jobs.cancel(job_id)


@protected_route(router.post, "/{rom_id}/convert-chd", scopes=[Scopes.ROMS_WRITE])
async def convert_rom_to_chd(
    request: Request, rom_id: int, body: _ConvertRequest | None = None,
) -> dict:
    """Convert this title's discs to CHD, as one job for the whole set.

    CHD is one file per disc where a rip is a sheet and its tracks, about half
    the size, and the emulator opens it without unpacking anything: a four
    disc PlayStation set is 1.6 GB in the browser rather than 2.7 GB, which is
    the difference between comfortable and up against the tab's ceiling.

    Returns at once with the job. It runs in the background and reports itself
    to the download tray, because a disc takes half a minute and a set takes
    several, and a request held open for that long is a request that dies on
    somebody's proxy.
    """
    return await chd_jobs.start(
        rom_id, delete_source=bool(body and body.delete_source))


# ── Home literal routes (MUST be before /{rom_id} to avoid route capture) ──────

def _rom_rating_agg(rom) -> float | None:
    """Aggregate 0-5 score across the ROM's rating sources - the emulation twin
    of the library's aggregate_rating. Shared with the dashboard via utils."""
    return rom_rating_agg_of(rom)


# Fields the fill-missing scrape mode treats as "gaps": a ROM missing ANY of
# them gets queued and only those fields are filled in.
_GAP_FIELDS = (
    "cover_path", "background_path", "screenshots", "support_path", "wheel_path",
    "bezel_path", "steamgrid_path", "video_path", "summary", "developer",
    "publisher", "release_year", "genres", "player_count",
)


def _rom_has_gaps(rom) -> bool:
    for f in _GAP_FIELDS:
        v = getattr(rom, f, None)
        if v is None or v == "" or v == []:
            return True
    return False


@protected_route(router.get, "/recent", scopes=[Scopes.ROMS_READ])
async def get_recent_roms(request: Request, limit: int = 24) -> list[dict]:
    """Return the most recently added ROMs across all platforms (for home page row)."""
    roms = await rom_handler.get_recent(limit=min(limit, 48))
    return [_rom_tile_dict(rom) for rom in roms]


def _rom_tile_dict(rom) -> dict:
    """The slim tile payload shared by /recent and /top-rated."""
    return {
        "id":                   rom.id,
        "name":                 rom.name or rom.fs_name_no_ext,
        "cover_path":           rom.cover_path,
        "cover_type":           rom.cover_type,
        "cover_aspect":         rom.cover_aspect,
        "background_path":      rom.background_path,
        "wheel_path":           rom.wheel_path,
        "platform_slug":        rom.platform.slug    if rom.platform else None,
        "platform_fs_slug":     rom.platform.fs_slug if rom.platform else None,
        "platform_name":        (rom.platform.custom_name or rom.platform.name) if rom.platform else None,
        "platform_cover_aspect": _get_cover_aspect(rom.platform.fs_slug) if rom.platform else "3/4",
        "fs_size_bytes":        rom.fs_size_bytes,
        "created_at":           rom.created_at.isoformat() if rom.created_at else None,
        "release_year":         rom.release_year,
        "player_count":         rom.player_count,
        "genres":               (rom.genres or [])[:3],
        "rating_agg":           _rom_rating_agg(rom),
    }


@protected_route(router.get, "/top-rated", scopes=[Scopes.ROMS_READ])
async def get_top_rated_roms(request: Request, limit: int = 24) -> list[dict]:
    """Best-rated ROMs across ALL platforms, ranked by the aggregate score."""
    roms = await rom_handler.get_rated()
    ranked = sorted(roms, key=lambda r: _rom_rating_agg(r) or 0, reverse=True)
    out: list[dict] = []
    for rom in ranked[: min(limit, 48)]:
        d = _rom_tile_dict(rom)
        if not d["rating_agg"]:
            break
        out.append(d)
    return out


@protected_route(router.get, "/summary", scopes=[Scopes.ROMS_READ])
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

@protected_route(router.get, "/search", scopes=[Scopes.ROMS_READ])
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

                    def _sgdb_year(_raw) -> str | None:
                        """SteamGridDB dates release_date as a Unix timestamp, not a
                        string - slicing it raised and, since gather propagates,
                        took every SGDB result down with it."""
                        if not _raw:
                            return None
                        try:
                            return str(datetime.fromtimestamp(int(_raw), tz=timezone.utc).year)
                        except (TypeError, ValueError, OSError, OverflowError):
                            return str(_raw)[:4] or None

                    async def _fetch_cover(_gid: int, _gname: str, _gdate) -> dict:
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
                            "year":      _sgdb_year(_gdate),
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

    # ScreenScraper cover URLs carry the server's password; wrap them so the
    # browser only ever sees a credential-free proxy URL. Public covers pass
    # through unchanged.
    from utils.media_proxy import proxy_media_list
    return proxy_media_list(
        ss_results + igdb_results + lb_results + sgdb_results, key="cover_url"
    )


# ── ROM detail ────────────────────────────────────────────────────────────────

@protected_route(router.get, "/{rom_id}", scopes=[Scopes.ROMS_READ])
async def get_rom(request: Request, rom_id: int) -> dict:
    rom = await rom_handler.get_with_platform(rom_id)
    if rom is None:
        raise HTTPException(status_code=404, detail="ROM not found")
    # A title split across floppies shows as one game; its other disks are
    # hidden from every listing, so this is the only place they can be offered.
    # Most of them just boot the same game, but not all - a fair few sets put a
    # level editor or a second scenario on a later disk, which is worth being
    # able to start directly.
    disks: list[dict] = []
    if rom.disk_group:
        disks = [
            {
                "id": d.id,
                "number": d.disk_number,
                "name": d.fs_name,
                # What loading the whole set would cost. The page puts it on
                # the button, because holding every disc at once is the price
                # of letting the emulator switch between them.
                "size": d.fs_size_bytes,
                "current": d.id == rom.id,
            }
            for d in await rom_handler.get_disk_set(rom.platform_id, rom.disk_group)
        ]
    # Whether these discs already have a playlist, which is what decides if the
    # page offers to write one. Only asked for a title that has discs to switch
    # between, so an ordinary game costs no filesystem call at all.
    playlist = None
    if len(disks) > 1:
        playlist = await asyncio.to_thread(
            _existing_playlist, Path(rom.fs_path), [d["name"] for d in disks]
        )

    # Whether the page may offer to convert this to CHD. Asked of the files
    # rather than of their names: a zipped cartridge ROM has the extension of
    # an archived disc and nothing inside worth converting, and finding that
    # out a minute into the job is the wrong moment. One small read per disc,
    # off the event loop, and only the discs this title actually has.
    convert_names = [d["name"] for d in disks] or [rom.fs_name]
    chd_convertible = await asyncio.to_thread(
        lambda: all(convertible_disc(Path(rom.fs_path) / n) for n in convert_names)
    )

    return {
        "disks":           disks,
        "playlist":        playlist,
        # Whether the page may offer to load the whole set. False for archived
        # discs and for sheets, which cannot reach the emulator that way and
        # would fail only after the entire set had downloaded.
        "set_loads_whole": _set_loads_whole([d["name"] for d in disks]),
        "chd_convertible": chd_convertible,
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
        # Whether this file is identified by hash at all, which is what decides
        # if the page offers to compute them.
        "has_hashes":      bool(rom.crc_hash or rom.sha1_hash or rom.md5_hash),
        # And the digests themselves, listed among the file's other facts. They
        # are what a person checks a dump against, so the answer to "did that
        # button do anything" should be readable rather than inferred from the
        # button going away. For an archive these describe the ROM inside it,
        # which is the thing the databases are keyed on.
        "crc_hash":        rom.crc_hash,
        "md5_hash":        rom.md5_hash,
        "sha1_hash":       rom.sha1_hash,
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
        "save_disk_name":    rom.save_disk_name,
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
        "rating_agg":       _rom_rating_agg(rom),
    }


# ── ROM metadata update ───────────────────────────────────────────────────────

def _media_ext(url: str) -> str:
    """File extension to save a picked media URL under.

    A picked scraper image now arrives as an opaque /api/media/proxy/<token>
    URL, which carries no ".ext" - so resolve it back to the real source first
    (the download itself resolves the token again inside fetch_media_bytes).

    The result is then reduced to plain alphanumerics. Without that, a URL with
    no dot at all yields the whole URL as the "extension", and a path built from
    it turns every slash into a directory: a proxy URL once produced a
    "background./api/media/proxy/" tree, which then broke every later save,
    because the cleanup below tried to unlink a directory.
    """
    import re
    from utils.media_proxy import resolve_proxy_url
    src = resolve_proxy_url(url) or url
    last = re.sub(r"[?#].*", "", src).rsplit("/", 1)[-1]
    # No dot in the filename means no extension to read - guessing one out of
    # the rest of the URL is what produced "background./api/media/proxy/".
    if "." not in last:
        return "jpg"
    return re.sub(r"[^a-z0-9]", "", last.rsplit(".", 1)[-1].lower())[:5] or "jpg"


def _clear_media(media_dir, stem: str) -> None:
    """Drop the existing files for one media slot, so the download does not skip
    them. Only files: a stray directory that happens to match must not take the
    whole request down with it."""
    for old in media_dir.glob(f"{stem}.*"):
        if old.is_file():
            old.unlink(missing_ok=True)


@protected_route(router.patch, "/{rom_id}", scopes=[Scopes.LIBRARY_WRITE, Scopes.ROMS_READ])
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

    # A scraper thumbnail the user picked in the editor arrives as an opaque
    # /api/media/proxy path (it is not "http://", so the editor routed it to a
    # *_path field, not a *_url one). That is REMOTE media, not a stored local
    # file: route it to the download branch so it is fetched to disk and served
    # locally. A proxy token must NEVER be persisted - it would serve live
    # through the unauthenticated proxy on every render (hitting the scraper with
    # the account password each time) and would break for good if the app secret
    # were ever rotated. The cover especially goes into Discord/email, where a
    # root-relative proxy path is useless.
    from utils.media_proxy import PROXY_PREFIX
    for _pf, _uf in (
        ("cover_path", "cover_url"), ("background_path", "background_url"),
        ("support_path", "support_url"), ("wheel_path", "wheel_url"),
        ("bezel_path", "bezel_url"), ("steamgrid_path", "steamgrid_url"),
        ("video_path", "video_url"),
    ):
        _pv = getattr(body, _pf, None)
        if isinstance(_pv, str) and PROXY_PREFIX in _pv:
            setattr(body, _uf, _pv)     # download it via the *_url branch below
            setattr(body, _pf, None)    # never store the token as a path

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
    if body.ss_score is not None:       data["ss_score"] = body.ss_score
    if body.igdb_rating is not None:    data["igdb_rating"] = body.igdb_rating
    if body.lb_rating is not None:      data["lb_rating"] = body.lb_rating
    if body.plugin_ratings is not None: data["plugin_ratings"] = body.plugin_ratings
    if body.player_count is not None: data["player_count"] = body.player_count
    # An Amiga title asks for its save disk by name; blank means GD picks one.
    if body.save_disk_name is not None:
        data["save_disk_name"] = body.save_disk_name.strip()[:30] or None
    if body.hltb_id is not None:        data["hltb_id"]        = body.hltb_id
    if body.hltb_main_s is not None:    data["hltb_main_s"]    = body.hltb_main_s
    if body.hltb_extra_s is not None:   data["hltb_extra_s"]   = body.hltb_extra_s
    if body.hltb_complete_s is not None: data["hltb_complete_s"] = body.hltb_complete_s
    if body.cover_path is not None:       data["cover_path"] = body.cover_path; data["cover_url"] = None
    if body.background_path is not None:  data["background_path"] = body.background_path
    if body.screenshots is not None:      data["screenshots"] = body.screenshots
    if body.support_path is not None:     data["support_path"] = body.support_path
    if body.wheel_path is not None:       data["wheel_path"] = body.wheel_path
    if body.bezel_path is not None:       data["bezel_path"] = body.bezel_path
    if body.steamgrid_path is not None:   data["steamgrid_path"] = body.steamgrid_path
    if body.video_path is not None:       data["video_path"] = body.video_path
    if body.picto_path is not None:       data["picto_path"] = body.picto_path

    # An EMPTY string on a *_path field means "remove this media": the column
    # goes NULL and the file leaves the disk (None still means "no change").
    _media_cols = [
        ("cover_path", "cover"), ("background_path", "background"),
        ("support_path", "support"), ("wheel_path", "wheel"),
        ("bezel_path", "bezel"), ("steamgrid_path", "steamgrid"),
        ("video_path", "video"), ("picto_path", "pictoliste"),
    ]
    for _field, _fname in _media_cols:
        if getattr(body, _field) == "":
            data[_field] = None
            if _field == "cover_path":
                data["cover_url"] = None   # drop the notification fallback too
                data["cover_source"] = None  # and stop claiming anybody chose it
            if media_dir.exists():
                _clear_media(media_dir, _fname)

    # Replaced media keeps its filename (cover.png -> cover.png), so the URL
    # alone would let the browser serve the STALE cached image and the save
    # looks like it never happened - version the URL with the save time.
    import time as _time
    _bust = f"?v={int(_time.time())}"

    # Download cover if URL provided
    if body.cover_url:
        ext = _media_ext(body.cover_url)
        dest = media_dir / f"cover.{ext}"
        # The old cover used to be deleted here, before the request went out, so
        # a URL that turned out to be dead cost the cover that was there. This is
        # the worst place for that to happen: somebody sat in the editor and
        # picked this one. _download_image now clears the slot only once the new
        # bytes are in hand.
        saved = await _download_image(body.cover_url, dest, replace=True)
        if saved:
            data["cover_path"] = _resource_url(platform_slug, rom_id, saved.name) + _bust
            # Somebody sat in the editor and picked this one out of the sources
            # panel or typed the address in, which is a choice, not a scrape.
            data["cover_source"] = "manual"
            # And the provider's word for what kind of picture it was goes with
            # it: it described the cover this one replaced. See upload_rom_media.
            data["cover_type"] = None
            # Re-read the proportions from the file we just wrote. Leaving the
            # previous value behind means the grid keeps drawing the old box
            # shape around new art, and crops whatever does not fit.
            from handler.metadata.rom_scrape_handler import _detect_cover_aspect
            _asp = _detect_cover_aspect(saved)
            if _asp:
                data["cover_aspect"] = _asp
            # Persist the (credential-free) source URL so a recently-added
            # notification can fall back to it when public_base_url is unset.
            # A credentialed source (ScreenScraper) is never stored/sent - and
            # the picked cover now arrives as an opaque /api/media/proxy URL, so
            # resolve it back to the real source before judging leakiness (else a
            # useless relative proxy path would be stored as the fallback).
            from handler.notifications.recently_added import _is_leaky_url
            from utils.media_proxy import resolve_proxy_url
            _src = resolve_proxy_url(body.cover_url)
            data["cover_url"] = None if (not _src or _is_leaky_url(_src)) else _src

    # Which slots this request has been told a person picked. Collected and
    # written once at the end: with_manual reads the row, so two branches each
    # building the map from it would have the second forget the first.
    _chosen: list[str] = []

    # Download background if URL provided
    if body.background_url:
        ext = _media_ext(body.background_url)
        dest = media_dir / f"background.{ext}"
        saved = await _download_image(body.background_url, dest, replace=True)
        if saved:
            data["background_path"] = _resource_url(platform_slug, rom_id, saved.name) + _bust
            # Somebody typed this address in or picked it out of the sources
            # panel, exactly like the cover above.
            _chosen.append("background_path")

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
            _ext = _media_ext(url_val)
            _dest = media_dir / f"{fname}.{_ext}"
            # replace does what the deletion here used to do - get past the
            # "already there, nothing to do" check - without the part where a
            # failed fetch left the slot empty.
            saved = await _download_image(url_val, _dest, replace=True)
            if saved:
                data[f"{fname}_path"] = _resource_url(platform_slug, rom_id, saved.name) + _bust
                _chosen.append(f"{fname}_path")

    if _chosen:
        from handler.metadata.rom_scrape_handler import with_manual
        data["media_source"] = with_manual(rom, *_chosen)

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


# ── ROM media upload (local file from the metadata editor) ───────────────────

_UPLOAD_KINDS = {
    "cover": "cover_path", "background": "background_path", "support": "support_path",
    "wheel": "wheel_path", "bezel": "bezel_path", "steamgrid": "steamgrid_path",
    "video": "video_path",
}
# Raster and video only. An SVG carries script, and uploaded art is served
# from the unauthenticated /resources mount as image/svg+xml from our own
# origin - today the Content-Security Policy blocks it, but /player and
# /emulatorjs are already exempt from that policy. The libraries router
# states the same rule for icons: raster only, SVG through the built-in
# picker instead.
#
# This is an allow-list: anything absent is refused, not renamed. The route
# used to force the extension instead, which meant an SVG was written to
# cover.png and served as image/png behind nosniff, so it rendered nowhere
# while the previous cover had already been deleted to make room for it.
_UPLOAD_EXTS = {"png", "jpg", "jpeg", "webp", "gif", "bmp", "mp4", "webm"}


@protected_route(router.post, "/{rom_id}/media/{kind}/upload", scopes=[Scopes.LIBRARY_WRITE, Scopes.ROMS_READ])
async def upload_rom_media(
    request: Request,
    rom_id: int,
    kind: str,
    file: UploadFile = File(...),
) -> dict:
    """Store a locally uploaded media file for the ROM (editor upload button).

    ``kind`` is one of cover/background/support/wheel/bezel/steamgrid/video
    or ``screenshot`` (appended to the screenshots list)."""
    if kind not in _UPLOAD_KINDS and kind != "screenshot":
        raise HTTPException(status_code=400, detail="Unknown media kind")
    rom = await rom_handler.get_with_platform(rom_id)
    if rom is None:
        raise HTTPException(status_code=404, detail="ROM not found")

    from handler.metadata.rom_scrape_handler import _rom_media_dir, _resource_url
    import time as _time

    platform_slug = rom.platform.slug if rom.platform else "unknown"
    media_dir = _rom_media_dir(platform_slug, rom_id)
    media_dir.mkdir(parents=True, exist_ok=True)

    ext = (file.filename or "").rsplit(".", 1)[-1].lower()
    if ext not in _UPLOAD_EXTS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported format. Allowed: {', '.join(sorted(_UPLOAD_EXTS))}",
        )

    if kind == "screenshot":
        idx = 0
        while list(media_dir.glob(f"screenshot_{idx}.*")):
            idx += 1
        dest = media_dir / f"screenshot_{idx}.{ext}"
    else:
        dest = media_dir / f"{kind}.{ext}"

    # The bytes land beside the target first. Emptying the slot before they
    # have arrived means an upload that fails half way through leaves the ROM
    # with no artwork at all, and the leading dot keeps the partial file out of
    # the {kind}.* glob that the clearing step walks.
    staged = media_dir / f".{dest.name}.part"
    try:
        with staged.open("wb") as out:
            while chunk := await file.read(1024 * 1024):
                out.write(chunk)
        if kind != "screenshot":
            _clear_media(media_dir, kind)
        staged.replace(dest)
    except Exception:
        staged.unlink(missing_ok=True)
        raise

    url = _resource_url(platform_slug, rom_id, dest.name) + f"?v={int(_time.time())}"
    if kind == "screenshot":
        shots = list(rom.screenshots or [])
        shots.append(url)
        # One picture somebody added makes the set theirs. There is nowhere to
        # record which of six a person put there, and a forced re-scrape writes
        # the whole list from screenshot_0 up - so the choice is between keeping
        # all of them and losing theirs among the rest.
        from handler.metadata.rom_scrape_handler import with_manual
        await rom_handler.update_metadata(rom_id, {
            "screenshots": shots,
            "media_source": with_manual(rom, "screenshots"),
        })
    else:
        _upd = {_UPLOAD_KINDS[kind]: url}
        if kind == "cover":
            _upd["cover_url"] = None   # an uploaded file has no clean remote source
            # And said outright, so a forced re-scrape leaves it alone. The
            # empty cover_url above used to be the only sign, and a
            # ScreenScraper cover leaves the same one.
            _upd["cover_source"] = "manual"
            # box-2D, box-3D and the rest describe a picture a provider sent.
            # This is not that picture, and leaving the old word behind claims
            # it is: box-3D renders 16/9, so a scraped 3D box replaced by hand
            # with a flat one went on being drawn wide and cropped. It was also
            # the only trace by which a migration could tell a scraped cover
            # from a chosen one, and it outlived the cover it described.
            _upd["cover_type"] = None
            # Same reason as the download path: new art, new proportions.
            from handler.metadata.rom_scrape_handler import _detect_cover_aspect
            _asp = _detect_cover_aspect(dest)
            if _asp:
                _upd["cover_aspect"] = _asp
        else:
            # Every other slot says the same thing the cover says, in the map
            # that holds the rest. Without it a forced re-scrape treated a
            # background or a wheel somebody had gone and found as the
            # provider's, replaced it, and deleted the file.
            from handler.metadata.rom_scrape_handler import with_manual
            _upd["media_source"] = with_manual(rom, _UPLOAD_KINDS[kind])
        await rom_handler.update_metadata(rom_id, _upd)
    return {"ok": True, "path": url}


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


@protected_route(router.get, "/{rom_id}/all-media", scopes=[Scopes.ROMS_READ])
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
                    # Only a number leaves here. A provider whose rating field
                    # means something else - TheGamesDB answers "E - Everyone",
                    # its age rating - used to be passed through raw, and the
                    # metadata editor formats a detail source's rating with
                    # .toFixed(). On a string that throws during render, which
                    # takes the whole editor down: the panel vanishes and will
                    # not reopen until the page is reloaded.
                    from handler.metadata.rom_scrape_handler import _numeric_rating
                    _p_rating = _numeric_rating(pid, gd.get("rating"))
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

    # ScreenScraper media URLs (covers/fanarts/screenshots/supports/wheels/
    # bezels/videos...) carry the server's password in their query string. Wrap
    # every list so the metadata editor renders credential-free proxy URLs;
    # public IGDB/LB/SGDB/plugin URLs pass through untouched.
    from utils.media_proxy import proxy_media_list
    return {
        "covers":         proxy_media_list(combined_covers + plugin_covers + sgdb_covers),
        "fanarts":        proxy_media_list(combined_fanarts + plugin_fanarts + sgdb_heroes),
        "screenshots":    proxy_media_list(combined_screenshots),
        "supports":       proxy_media_list(supports),
        "wheels":         proxy_media_list(wheels + plugin_wheels + sgdb_logos),
        "bezels":         proxy_media_list(bezels),
        "steamgrids":     proxy_media_list(steamgrids + sgdb_icons),
        "videos":         proxy_media_list(videos),
        "details":        details,
        "detail_sources": detail_sources,
    }


# Backward-compat alias
@protected_route(router.get, "/{rom_id}/ss-media", scopes=[Scopes.ROMS_READ])
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

async def _rom_file_response(rom_id: int) -> FileResponse:
    rom = await rom_handler.get_by_id(rom_id)
    if rom is None:
        raise HTTPException(status_code=404, detail="ROM not found")
    file_path = Path(rom.fs_path) / rom.fs_name
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="ROM file not found on disk")
    # Path traversal guard - see the note on the other guard in this file.
    roms_base = os.path.realpath(await _get_roms_path())
    _resolved = os.path.realpath(str(file_path))
    if not (_resolved == roms_base or _resolved.startswith(roms_base + os.sep)):
        raise HTTPException(status_code=403, detail="Access denied")
    return FileResponse(
        path=str(file_path),
        filename=rom.fs_name,
        media_type="application/octet-stream",
    )


@protected_route(router.get, "/{rom_id}/download", scopes=[Scopes.ROMS_READ])
async def download_rom(request: Request, rom_id: int) -> FileResponse:
    """Download a ROM with an Authorization header - for API clients.

    The interface cannot use this: saving a file means navigating the browser to
    a URL, and a navigation sends no header. It asks for a ticket instead.
    """
    return await _rom_file_response(rom_id)


@protected_route(router.post, "/{rom_id}/download-ticket", scopes=[Scopes.ROMS_READ])
async def issue_download_ticket(request: Request, rom_id: int, whole_set: bool = False) -> dict:
    """A short-lived link the browser can be pointed at.

    Access is decided here, on an authenticated request; the link that comes out
    only proves that decision was made, for this user, a few minutes ago.

    *whole_set* asks for every disk of a title that was split across floppies,
    as one archive: downloading a two-disk game one file at a time is not what
    anybody means by "download this game".

    Without it the answer is this ROM alone - unless the ROM is a sheet, in
    which case it is the sheet and its track files. A .cue on its own is two
    kilobytes naming data the download did not include, so nobody asking for
    one disc means only the sheet.
    """
    rom = await rom_handler.get_by_id(rom_id)
    if rom is None:
        raise HTTPException(status_code=404, detail="ROM not found")
    user_id = request.state.user.id
    members = (
        await rom_handler.disk_set(rom_id) if whole_set
        else await rom_handler.rom_with_tracks(rom_id)
    )
    if len(members) > 1:
        kind = "set" if whole_set else "files"
        expires_at, sig = download_tickets.issue(rom_id, user_id, kind=kind)
        return {
            "url": f"/api/roms/{rom_id}/download-{kind}/{user_id}/{expires_at}/{sig}",
            "expires_at": expires_at,
        }
    expires_at, sig = download_tickets.issue(rom_id, user_id)
    return {
        "url": f"/api/roms/{rom_id}/download/{user_id}/{expires_at}/{sig}",
        "expires_at": expires_at,
    }


# Deliberately NOT @protected_route: this is the URL the browser navigates to,
# and a navigation carries no Authorization header. The ticket takes the place
# of the session - it names one ROM and one user, and it stops working within
# minutes of being issued.
@router.get("/{rom_id}/download/{user_id}/{expires_at}/{sig}")
async def download_rom_with_ticket(
    rom_id: int, user_id: int, expires_at: int, sig: str
) -> FileResponse:
    if not download_tickets.valid(rom_id, user_id, expires_at, sig):
        raise HTTPException(status_code=403, detail="This download link has expired")
    return await _rom_file_response(rom_id)


class _ZipStream:
    """A sink zipfile writes into that hands the bytes straight on.

    Packing into a BytesIO first meant the whole title sat in memory before the
    download could start. That was tolerable while this route only ever saw
    floppies - ten disks of 880 kB - and stopped being tolerable the moment a
    disc kept as a sheet plus its data started coming through here, where the
    .bin alone is most of a gigabyte.

    No `seek`, deliberately: zipfile notices, and writes a data descriptor after
    each member instead of seeking back to patch its header.
    """

    def __init__(self) -> None:
        self._buf = bytearray()
        self._pos = 0

    def write(self, data) -> int:
        self._buf += data
        self._pos += len(data)
        return len(data)

    def tell(self) -> int:
        return self._pos

    def flush(self) -> None:
        pass

    def seekable(self) -> bool:
        return False

    def drain(self) -> bytes:
        out = bytes(self._buf)
        self._buf.clear()
        return out


# What the disc inside an archive is called. Lives with the rest of the disc
# format knowledge rather than here: the conversion asks the same question, of
# the same files, and two answers to it would be one answer too many. Kept
# under the old private name so the playlist below reads as it always did.
_disc_inside_archive = disc_inside_archive


def _playlist_for(members, resolve_in=None) -> str:
    """A .m3u naming the discs of a multi-disc title, in order, or "".

    Without one, a two-disc game arrives as a folder of files and the emulator
    has no idea they belong together: the player gets to disc two and has to go
    and find it. With one, RetroArch and the cores GD runs offer disc switching
    from the menu.

    One line per disc and never per file. A line pointing at a raw .bin track
    is not a disc, and an emulator told to load one gets a data file instead of
    a game. RomM filters its list down to the .cue files to avoid exactly that;
    here the rows already say which is which, so a track simply never appears.

    Nothing for a single disc, however many files it takes: there is nothing to
    switch between.

    With *resolve_in* set to the directory the discs live in, an archived disc
    is named by the image inside it rather than by the archive. The two callers
    want different answers and both are right: the copy written into the
    library describes that folder, where the file really is a .zip, and the
    copy handed to the browser describes the emulator's filesystem, where the
    player will have unpacked it.
    """
    discs = [m.fs_name for m in members if not m.track_of]
    if len(discs) < 2:
        return ""
    if resolve_in is not None:
        discs = [
            _disc_inside_archive(Path(resolve_in) / name) or name
            for name in discs
        ]
    return "".join(f"{name}\n" for name in discs)


def _zip_chunks(members: list[tuple[Path, str]], extra: list[tuple[str, bytes]] | None = None):
    """A stored ZIP of *members*, a piece at a time.

    Synchronous on purpose: Starlette runs a sync iterator in a worker thread,
    so reading gigabytes off disk here does not stall the event loop.

    Stored rather than deflated, as before: a disc image is already about as
    small as it gets, and compressing it to save nothing only makes the player
    wait longer for the download to begin.
    """
    stream = _ZipStream()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_STORED) as archive:
        for path, arcname in members:
            info = zipfile.ZipInfo.from_file(path, arcname)
            info.compress_type = zipfile.ZIP_STORED
            # force_zip64 because the size is not declared up front and a disc
            # image is well past the four gigabyte mark that needs it.
            with path.open("rb") as src, archive.open(info, "w", force_zip64=True) as dest:
                while chunk := src.read(1024 * 1024):
                    dest.write(chunk)
                    if data := stream.drain():
                        yield data
            if data := stream.drain():
                yield data
        # Written from memory rather than read off the disk, because it does
        # not exist there: it is made for this archive out of what the set is.
        for arcname, content in extra or ():
            archive.writestr(arcname, content)
            if data := stream.drain():
                yield data
    if data := stream.drain():
        yield data


def _member_files(members, roms_base: str) -> list[tuple[Path, str]]:
    """The real files behind these rows, and anything a sheet names besides.

    Two kinds of file end up here. The rows are the ones the scanner collected,
    and the rest are files a sheet points at that never became rows at all: a
    Dreamcast rip is a .gdi beside track01.bin and track02.raw, and .raw is not
    an extension this library claims - far too generic a name to treat as a ROM
    on sight. It is still part of the disc, and a download without it will not
    boot.

    Blocking work, so a caller runs it off the event loop.
    """
    out: list[tuple[Path, str]] = []
    seen: set[str] = set()

    def offer(path: Path, name: str) -> None:
        if name.lower() in seen or not path.is_file():
            return
        # The same guard the single-file download applies. A stored path is
        # data, and data that decides what gets read is worth distrusting.
        resolved = os.path.realpath(str(path))
        if not (resolved == roms_base or resolved.startswith(roms_base + os.sep)):
            return
        seen.add(name.lower())
        out.append((path, name))

    for row in members:
        offer(Path(row.fs_path) / row.fs_name, row.fs_name)
    for row in members:
        if Path(row.fs_name).suffix.lower() not in SHEET_EXTENSIONS:
            continue
        directory = Path(row.fs_path)
        named = tracks_referenced_by(directory / row.fs_name)
        if not named:
            continue
        try:
            beside = sorted(directory.iterdir())
        except OSError:
            continue
        for entry in beside:
            if entry.name.lower() in named:
                offer(entry, entry.name)

    # And the subchannel data, which no sheet names because nothing names it:
    # it is matched to a disc by having the same name. A PAL PlayStation disc
    # protected with LibCrypt boots and hangs on a black screen without it, so
    # a download that leaves it behind is a download that does not run.
    # getattr, not row.track_of: this function has only ever needed a path and
    # a name, and callers - including its tests - build rows with just those.
    discs = [row.fs_name for row in members
             if not getattr(row, "track_of", None)]
    for directory in {Path(row.fs_path) for row in members}:
        for entry in subchannel_files_for(directory, discs):
            offer(entry, entry.name)
    return out


async def _zip_response(rom, members) -> Response:
    roms_base = os.path.realpath(await _get_roms_path())
    files = await asyncio.to_thread(_member_files, members, roms_base)
    if not files:
        raise HTTPException(status_code=404, detail="ROM file not found on disk")
    stem = _safe_download_name(rom.name or rom.fs_name_no_ext or str(rom.id))
    name = stem + ".zip"
    # A playlist only when the title really is several discs; the helper answers
    # with nothing for a single disc, whatever it takes to store it.
    playlist = _playlist_for(members)
    extra = [(f"{stem}.m3u", playlist.encode("utf-8"))] if playlist else []
    return StreamingResponse(
        _zip_chunks(files, extra),
        media_type="application/zip",
        # Through the RFC 5987 helper rather than into the header raw. Headers
        # are latin-1, and a title written in Japanese or Cyrillic survives
        # _safe_download_name untouched - str.isalnum() is true for every letter
        # in every script - so putting it straight into the header raised
        # inside the server and the download answered 500.
        headers={"Content-Disposition": content_disposition(name)},
    )


@router.get("/{rom_id}/download-set/{user_id}/{expires_at}/{sig}")
async def download_disk_set_with_ticket(
    rom_id: int, user_id: int, expires_at: int, sig: str
) -> Response:
    """Every disk of a title split across floppies, as one archive."""
    if not download_tickets.valid(rom_id, user_id, expires_at, sig, kind="set"):
        raise HTTPException(status_code=403, detail="This download link has expired")
    rom = await rom_handler.get_by_id(rom_id)
    if rom is None:
        raise HTTPException(status_code=404, detail="ROM not found")
    return await _zip_response(rom, await rom_handler.disk_set(rom_id))


@router.get("/{rom_id}/download-files/{user_id}/{expires_at}/{sig}")
async def download_rom_files_with_ticket(
    rom_id: int, user_id: int, expires_at: int, sig: str
) -> Response:
    """One disc that is more than one file: the sheet and the data it names."""
    if not download_tickets.valid(rom_id, user_id, expires_at, sig, kind="files"):
        raise HTTPException(status_code=403, detail="This download link has expired")
    rom = await rom_handler.get_by_id(rom_id)
    if rom is None:
        raise HTTPException(status_code=404, detail="ROM not found")
    return await _zip_response(rom, await rom_handler.rom_with_tracks(rom_id))


def _safe_download_name(name: str) -> str:
    """A file name a browser will accept without argument."""
    keep = "".join(c for c in name if c.isalnum() or c in " ._-()[]")
    return keep.strip() or "disks"


# ── Clear metadata ────────────────────────────────────────────────────────────

@protected_route(router.post, "/{rom_id}/clear-metadata", scopes=[Scopes.ROMS_WRITE])
async def clear_rom_metadata(request: Request, rom_id: int) -> dict:
    """Clear all scraped metadata for a single ROM (keeps file info + hashes)."""
    result = await rom_handler.clear_metadata(rom_id)
    if result is None:
        raise HTTPException(status_code=404, detail="ROM not found")
    return {"ok": True}


#: ROMs whose checksums are being computed right now. Each one holds a thread
#: from the default executor for the length of a whole-file read, and that is
#: the same pool the scanner and every other `to_thread` in the app share, so a
#: handful of unguarded clicks on 40 GB discs would stop the application's
#: filesystem work rather than merely slow it. The scan route next door refuses
#: a second run the same way.
_hashing_roms: set[int] = set()


@protected_route(router.post, "/{rom_id}/hashes", scopes=[Scopes.ROMS_WRITE])
async def compute_rom_hashes(request: Request, rom_id: int) -> dict:
    """Read this one file and record its checksums, whatever the ceiling says.

    The hashing ceiling in Settings > ROMs stops a scan from reading enormous
    files, which is what makes a first scan of a disc library finish. This is
    the other half of it: when you do want a particular file identified by
    hash, you ask here and that size limit does not apply, because you asked.

    The archive guard still does. A member that declares more than
    MAX_MEMBER_BYTES is refused here as everywhere else: that ceiling is about
    what an archive is allowed to make us read, not about what the operator
    would rather not spend, and asking politely does not make a bomb safe.
    """
    from handler.filesystem.rom_scanner import _compute_hashes

    rom = await rom_handler.get_with_platform(rom_id)
    if rom is None:
        raise HTTPException(status_code=404, detail="ROM not found")

    path = Path(rom.fs_path) / rom.fs_name
    if not path.is_file():
        raise HTTPException(status_code=404, detail="ROM file not found on disk")

    # Same guard, and the same reason, as the download route above: fs_path is
    # a stored string, and a row can point outside the ROM directory through a
    # symlink or after the library path was changed under it. Reading a file we
    # would refuse to serve, and publishing its digest to a scraper, is not a
    # smaller thing than serving it.
    roms_base = os.path.realpath(await _get_roms_path())
    resolved = os.path.realpath(str(path))
    if not (resolved == roms_base or resolved.startswith(roms_base + os.sep)):
        raise HTTPException(status_code=403, detail="Access denied")

    if rom_id in _hashing_roms:
        raise HTTPException(
            status_code=409, detail="This file is already being read"
        )
    _hashing_roms.add(rom_id)
    try:
        crc, md5, sha1 = await asyncio.to_thread(_compute_hashes, path)
    finally:
        _hashing_roms.discard(rom_id)

    if not (crc or md5 or sha1):
        # Nothing came back, and the row is left exactly as it was. The two
        # cases behind this are a read that failed and a format that carries no
        # usable digest, and `_compute_hashes` cannot tell them apart - but
        # writing empties would be wrong for both. It would null good values on
        # a transient read error, and the answer here is a refusal, not a
        # result. Saying so is what stops the button reappearing in silence.
        raise HTTPException(
            status_code=422,
            detail="Could not compute checksums for this file",
        )

    await rom_handler.set_hashes(rom_id, crc, md5, sha1)
    return {"ok": True, "has_hashes": True}


# A disc the emulator can be handed as one file, exactly as it sits on disk.
_SELF_CONTAINED_DISC = {".chd", ".iso", ".img", ".pbp", ".cso", ".exe"}

# And a disc the player can open on the way in. DecompressionStream is built
# into the browser and speaks deflate, which is a zip and nothing else: a .7z
# or a .rar would mean shipping a decoder, so those stay out.
_UNPACKABLE_ARCHIVE = {".zip"}


def _set_loads_whole(disc_names) -> bool:
    """Whether the player can put every disc of this set in place.

    Loading the whole set is what lets the core change discs on its own, and
    it works by putting one file per disc into the emulator's filesystem. A
    zip is fine, because the player unpacks it there; a .7z is not, and
    neither is a sheet, because the .cue is a library row and its .bin is not,
    so only the sheet would arrive.

    Either failure lands after the entire set has downloaded, which is the
    worst possible place to find out, so the page asks this before offering
    the button.
    """
    names = list(disc_names)
    if not names:
        return False
    allowed = _SELF_CONTAINED_DISC | _UNPACKABLE_ARCHIVE
    return all(Path(n).suffix.lower() in allowed for n in names)


def _playlists_naming(directory, disc_names) -> list[Path]:
    """Every playlist in *directory* that names any of these discs.

    By content rather than by name, because the useful question is whether the
    discs have a playlist, not whether they have ours. One that came down
    beside them, or that somebody wrote by hand on a handheld, counts the same:
    for the button, because writing a second one over the top would be the
    wrong answer; and for deletion, because a playlist naming discs that are
    gone is just as broken whoever wrote it.
    """
    discs = {n.lower() for n in disc_names}
    if len(discs) < 2:
        return []
    try:
        candidates = sorted(Path(directory).glob("*.m3u"))
    except OSError:
        return []
    out = []
    for entry in candidates:
        try:
            lines = entry.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        # A line may carry a `path|Label` suffix, and may be written with
        # either separator by whatever wrote it. Only the file name is
        # compared. GD never writes a label - PCSX-ReARMed hands the whole
        # line to the filesystem - but other tools do.
        named = {
            line.split("|", 1)[0].strip().replace("\\", "/").rsplit("/", 1)[-1].lower()
            for line in lines if line.strip() and not line.startswith("#")
        }
        if named & discs:
            out.append(entry)
    return out


def _existing_playlist(directory, disc_names) -> str | None:
    """The name of a playlist naming these discs, or None. For the page."""
    found = _playlists_naming(directory, disc_names)
    return found[0].name if found else None


@protected_route(router.get, "/{rom_id}/sidecars.zip", scopes=[Scopes.ROMS_READ])
async def rom_sidecars(request: Request, rom_id: int, whole_set: bool = False) -> Response:
    """Subchannel data for this disc, or for the whole set, as a small archive.

    A disc reaches the emulator's filesystem because it is a library row and
    the player fetches it by id. Its subchannel file is not a row - it is 452
    bytes matched to the disc by name - so nothing would carry it, and a PAL
    PlayStation disc protected with LibCrypt hangs on a black screen without
    it, saying so only in a core log line nobody sees.

    204 when there is nothing, which is most discs, so the player skips the
    transfer entirely rather than unpacking an archive to find it empty. The
    firmware bundle already answers that way.
    """
    rom = await rom_handler.get_by_id(rom_id)
    if rom is None:
        raise HTTPException(status_code=404, detail="ROM not found")

    if whole_set:
        members = await rom_handler.disk_set(rom_id)
        names = [m.fs_name for m in members if not m.track_of]
    else:
        names = [rom.fs_name]

    directory = Path(rom.fs_path)
    roms_base = os.path.realpath(await _get_roms_path())
    resolved = os.path.realpath(str(directory))
    if not (resolved == roms_base or resolved.startswith(roms_base + os.sep)):
        raise HTTPException(status_code=403, detail="Access denied")

    found = await asyncio.to_thread(subchannel_files_for, directory, names)
    if not found:
        return Response(status_code=204)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as archive:
        for entry in found:
            archive.write(entry, arcname=entry.name)
    return Response(content=buf.getvalue(), media_type="application/zip")


@protected_route(router.get, "/{rom_id}/playlist.zip", scopes=[Scopes.ROMS_READ])
async def rom_playlist_archive(request: Request, rom_id: int) -> Response:
    """The playlist alone, zipped, as the thing the browser loads as the game.

    EmulatorJS recognises a playlist by its extension and only sees extensions
    on the members of an archive, so the playlist has to arrive inside one.
    Putting the discs in there as well is the thing to avoid: its extractor
    copies every extracted byte out of the worker's heap one at a time from
    JavaScript, which for a four disc PlayStation set is 2.65 GiB and several
    full-size copies. The discs reach the emulator's filesystem by another
    road, written there directly; this is a few hundred bytes.

    The names in it are the ones the emulator will see, which for an archived
    disc is the image inside rather than the .zip: the player unpacks on the
    way in, so the .zip never exists on that side.
    """
    rom = await rom_handler.get_by_id(rom_id)
    if rom is None:
        raise HTTPException(status_code=404, detail="ROM not found")

    # Reading inside the archives means touching files, so this route needs the
    # same guard as the ones that serve them.
    directory = Path(rom.fs_path)
    roms_base = os.path.realpath(await _get_roms_path())
    resolved = os.path.realpath(str(directory))
    if not (resolved == roms_base or resolved.startswith(roms_base + os.sep)):
        raise HTTPException(status_code=403, detail="Access denied")

    members = await rom_handler.disk_set(rom_id)
    body = await asyncio.to_thread(_playlist_for, members, directory)
    if not body:
        raise HTTPException(
            status_code=422,
            detail="This title is a single disc; there is nothing to switch between",
        )

    stem = _safe_download_name(rom.name or rom.fs_name_no_ext or str(rom.id))
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as archive:
        archive.writestr(f"{stem}.m3u", body)
    return Response(
        content=buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": content_disposition(f"{stem}.zip")},
    )


@protected_route(router.post, "/{rom_id}/playlist", scopes=[Scopes.ROMS_WRITE])
async def write_rom_playlist(request: Request, rom_id: int) -> dict:
    """Write an .m3u naming this title's discs, into the library beside them.

    GD has been able to put a playlist inside a download since 1.0.32, but that
    copy exists for the length of one transfer. This one is part of the
    library: it survives the next scan, it travels when the shelf is copied to
    a handheld, and RetroArch finds it without being told.

    Deliberately plain, one filename per line. Some frontends read a
    `path|Label` syntax and some hand the whole line to the filesystem and find
    nothing, so a file written into someone's library is the compatible kind.
    Labels belong where we know they are read.
    """
    rom = await rom_handler.get_by_id(rom_id)
    if rom is None:
        raise HTTPException(status_code=404, detail="ROM not found")

    members = await rom_handler.disk_set(rom_id)
    body = _playlist_for(members)
    if not body:
        raise HTTPException(
            status_code=422,
            detail="This title is a single disc; there is nothing to switch between",
        )

    directory = Path(rom.fs_path)
    name = _safe_download_name(rom.name or rom.fs_name_no_ext or str(rom.id)) + ".m3u"
    target = directory / name

    # The same guard, and the same reason, as the download and hashing routes:
    # fs_path is a stored string, and a row can point outside the ROM directory
    # through a symlink or after the library path was changed under it. This
    # one writes, so it matters more here than anywhere else.
    roms_base = os.path.realpath(await _get_roms_path())
    resolved = os.path.realpath(str(directory))
    if not (resolved == roms_base or resolved.startswith(roms_base + os.sep)):
        raise HTTPException(status_code=403, detail="Access denied")

    await asyncio.to_thread(target.write_text, body, encoding="utf-8")
    return {"ok": True, "name": name, "discs": len(body.splitlines())}


@protected_route(router.post, "/platforms/{slug}/clear-metadata", scopes=[Scopes.ROMS_WRITE])
async def clear_platform_metadata(request: Request, slug: str) -> dict:
    """Clear scraped metadata for ALL ROMs on a platform."""
    platform = await rom_platform_handler.get_by_slug(slug)
    if platform is None:
        raise HTTPException(status_code=404, detail="Platform not found")
    count = await rom_handler.clear_metadata_for_platform(platform.id)
    return {"ok": True, "cleared": count}


@protected_route(router.delete, "/metadata", scopes=[Scopes.ROMS_WRITE])
async def clear_all_roms_metadata(request: Request) -> dict:
    """Clear scraped metadata for ALL ROMs across all platforms."""
    count = await rom_handler.clear_all_metadata()
    return {"ok": True, "cleared": count}


async def removable_tracks(members) -> list[Path]:
    """The data files a delete of *members* may actually take with it.

    unrowed_tracks reads the sheets and answers with everything they name that
    is not a member of this set. That is only most of the answer: it knows the
    set being deleted and knows nothing about the rest of the library, so a file
    holding another entry's row looks from there exactly like an orphan. The
    database settles it, and files that turn out to be somebody's entry stay.

    Both the preview and the delete go through here, so the number in the
    question is the number of files the answer removes.
    """
    candidates = await asyncio.to_thread(rom_removal.unrowed_tracks, members)
    if not candidates:
        return []
    owned = await rom_handler.fs_names_with_rows(
        members[0].platform_id, [p.name for p in candidates]
    )
    return [p for p in candidates if p.name.lower() not in owned]


@protected_route(router.get, "/{rom_id}/removal", scopes=[Scopes.ROMS_WRITE])
async def rom_removal_preview(request: Request, rom_id: int) -> dict:
    """What deleting this ROM would take with it.

    Asked before the question is put to the player, because the two things that
    make this destructive are invisible from the page: a floppy title is
    several rows that only mean anything together, and the saves that go with
    them may belong to people other than whoever is looking.
    """
    members = await rom_handler.disk_set(rom_id)
    if not members:
        raise HTTPException(status_code=404, detail="ROM not found")
    states, saves = 0, 0
    for member in members:
        states += len(await save_state_handler.list_states_for_rom(member.id))
        saves += len(await save_state_handler.list_saves_for_rom(member.id))
    # Track files are not disks and must not be counted as any: the warning
    # says "this title is N disks", and a single-disc rip kept as a sheet plus
    # its data is one disc however many files it takes.
    spoken_for = await asyncio.to_thread(rom_removal.spoken_for_elsewhere, members)
    extra = [m.fs_name for m in members
             if m.track_of and m.fs_name.lower() not in spoken_for]
    extra += [p.name for p in await removable_tracks(members)]
    # A playlist naming these discs goes with them. It is not a library row and
    # no sheet names it, so nothing else here would reach it, and one left
    # behind names discs that are not there.
    extra += [p.name for p in await asyncio.to_thread(
        _playlists_naming, Path(members[0].fs_path),
        [m.fs_name for m in members if not m.track_of],
    )]
    # And the subchannel data, which belongs to these discs and to nothing
    # else. It has no row, so nothing else would list it either.
    extra += [p.name for p in await asyncio.to_thread(
        subchannel_files_for, Path(members[0].fs_path),
        [m.fs_name for m in members if not m.track_of],
    )]
    return {
        "disks": [
            {"id": d.id, "name": d.fs_name, "number": d.disk_number}
            for d in members if not d.track_of
        ],
        "files": extra,
        "saves": states + saves,
        "on_disk": any((Path(m.fs_path) / m.fs_name).is_file() for m in members),
    }


@protected_route(router.delete, "/{rom_id}", scopes=[Scopes.ROMS_WRITE])
async def delete_rom(request: Request, rom_id: int, delete_files: bool = False) -> dict:
    """Take a ROM out of the library, and its whole set when it has one.

    Saves go either way: they are reached through the ROM and through nothing
    else, so a row that is gone takes them with it rather than leaving bytes
    charged against a quota that nothing can reach. The ROM file is different -
    it is the one thing here the player supplied rather than GD fetched - so it
    stays unless *delete_files* says otherwise.

    Note that a file left on disk comes back as a library entry on the next
    scan. That is the honest behaviour of a library that reads a directory, and
    it is why the screen asks about the file rather than deciding alone.
    """
    disks = await rom_handler.disk_set(rom_id)
    if not disks:
        raise HTTPException(status_code=404, detail="ROM not found")

    result = rom_removal.Removal()
    # Worked out while the sheets are still on disk. Once the .cue is unlinked
    # nothing is left to say which data files belonged to it, and those files
    # have no row of their own to be reached by.
    orphans = await removable_tracks(disks) if delete_files else []
    # And the playlist naming this set, on the same terms as the discs: it is
    # neither a row nor a file any sheet names, so nothing else would reach it,
    # and one left behind points at discs that have gone.
    if delete_files:
        names = [d.fs_name for d in disks if not d.track_of]
        orphans = list(orphans) + await asyncio.to_thread(
            _playlists_naming, Path(disks[0].fs_path), names,
        ) + await asyncio.to_thread(
            subchannel_files_for, Path(disks[0].fs_path), names,
        )
    # Files another sheet in the directory still names. A track that became a row
    # of its own is a member of this set and would otherwise go with it, leaving
    # the sheet that survives naming a file that is not there.
    spoken_for = await asyncio.to_thread(rom_removal.spoken_for_elsewhere, disks)
    for disk in disks:
        platform = await rom_platform_handler.get_by_id(disk.platform_id)
        slug = platform.slug if platform else "unknown"

        states = await save_state_handler.list_states_for_rom(disk.id)
        saves = await save_state_handler.list_saves_for_rom(disk.id)
        result.saves += await asyncio.to_thread(rom_removal.delete_save_files, states, saves)

        if await asyncio.to_thread(rom_removal.delete_media_dir, slug, disk.id):
            result.media_dirs += 1
        if delete_files and await asyncio.to_thread(
            partial(rom_removal.delete_rom_file, disk, spoken_for=spoken_for)
        ):
            result.rom_files += 1

        if await rom_handler.delete(disk.id):
            result.roms += 1
            result.names.append(disk.fs_name)

    if orphans:
        result.rom_files += await asyncio.to_thread(rom_removal.delete_paths, orphans)

    logger.info("Deleted %d ROM row(s), %d file(s), %d save(s): %s",
                result.roms, result.rom_files, result.saves, ", ".join(result.names))
    return {"ok": True, **result.as_dict()}


# ── ROM Upload ────────────────────────────────────────────────────────────────

@protected_route(router.post, "/platforms/{slug}/upload", scopes=[Scopes.LIBRARY_UPLOAD, Scopes.ROMS_READ])
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
    rejected: list[dict] = []

    # Pre-resolve once so per-file scanning is cheap when disabled
    try:
        from handler.clamav import clamav_handler as _clam
        scan_uploads = await _clam.is_upload_scanning_enabled()
    except Exception:
        scan_uploads = False

    actor = (request.state.user.username
             if getattr(request.state, "user", None) else None)

    for upload in files:
        if not upload.filename:
            continue
        safe_name = Path(upload.filename).name          # strip any directory parts
        dest_path = dest_dir / safe_name
        try:
            with open(dest_path, "wb") as fh:
                while chunk := await upload.read(256 * 1024):
                    fh.write(chunk)

            if scan_uploads:
                try:
                    res = await _clam.scan_file(str(dest_path))
                    note_unscanned(res, "ROM upload", safe_name)
                    if res.get("status") == "FOUND":
                        threat = res.get("threat") or "unknown"
                        action_res = await _clam.quarantine_or_delete(
                            str(dest_path), threat, triggered_by=actor
                        )
                        logger.warning(
                            "ClamAV blocked ROM upload '%s' (threat=%s, action=%s)",
                            safe_name, threat, action_res.get("action"),
                        )
                        rejected.append({
                            "filename": safe_name,
                            "threat":   threat,
                            "action":   action_res.get("action"),
                        })
                        continue
                except Exception:
                    logger.exception("ClamAV scan failed for %s; allowing upload", dest_path)

            saved.append(safe_name)
            logger.info("ROM uploaded: %s -> %s", safe_name, dest_dir)
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

    return {
        "ok": True,
        "saved": saved,
        "rejected": rejected,
        "platform_slug": slug,
        "scan_triggered": bool(saved),
    }


# ── Scan ──────────────────────────────────────────────────────────────────────

@protected_route(router.post, "/scan", scopes=[Scopes.PLATFORMS_WRITE])
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


@protected_route(router.get, "/scan/status", scopes=[Scopes.ROMS_READ])
async def scan_status(request: Request) -> dict:
    return {"running": _scan_lock.locked()}


# ── Scrape metadata ───────────────────────────────────────────────────────────

@protected_route(router.post, "/platforms/{slug}/scrape-platform", scopes=[Scopes.ROMS_WRITE])
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


@protected_route(router.post, "/platforms/{slug}/scrape", scopes=[Scopes.ROMS_WRITE])
async def scrape_platform(
    request: Request,
    slug: str,
    background_tasks: BackgroundTasks,
    limit: int = 100000,
    force: bool = False,
    mode: str | None = None,
) -> dict:
    """Trigger metadata scraping for all ROMs in a platform.

    Modes (``mode`` wins over the legacy ``force`` flag):
    - ``new``     (default): only ROMs never identified (no cover AND no ids).
    - ``missing``: every ROM with ANY gap (a missing wheel, description, ...)
      is queued, and the scrape fills ONLY those gaps - existing fields and
      media files stay untouched.
    - ``force``  : re-scrape everything, overwriting existing data.
    """
    platform = await rom_platform_handler.get_by_slug(slug)
    if platform is None:
        raise HTTPException(status_code=404, detail="Platform not found")

    m = mode or ("force" if force else "new")
    items, _ = await rom_handler.list_for_platform(platform.id, limit=limit)
    fill_missing = False
    if m == "force":
        rom_ids = [r.id for r in items]
    elif m == "missing":
        rom_ids = [r.id for r in items if _rom_has_gaps(r)]
        fill_missing = True
    else:
        rom_ids = [
            r.id for r in items
            if not (r.cover_path or r.ss_id or r.igdb_id or r.launchbox_id)
        ]

    async def _run():
        await scrape_roms_batch(rom_ids, platform, fill_missing=fill_missing)

    background_tasks.add_task(_run)
    return {"ok": True, "queued": len(rom_ids), "total": len(items), "mode": m}


class ScrapeRomBody(BaseModel):
    forced_ss_id: str | None = None
    forced_launchbox_id: str | None = None


@protected_route(router.post, "/{rom_id}/scrape", scopes=[Scopes.LIBRARY_WRITE, Scopes.ROMS_READ])
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
            # ROM now has a cover -> one-shot recently-added card (idempotent).
            try:
                from handler.notifications.recently_added import schedule_rom
                schedule_rom(rom_id)
            except Exception:
                pass

    background_tasks.add_task(_run)
    return {"ok": True, "rom_id": rom_id, "forced_ss_id": forced_ss_id, "forced_launchbox_id": forced_launchbox_id}


@protected_route(router.post, "/hltb-rescrape", scopes=[Scopes.ROMS_WRITE])
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


# ── Play tracking (fires plugin lifecycle_on_play_start / _on_play_end) ────────

class _RomPlayEnd(BaseModel):
    seconds: int | None = None


@protected_route(router.post, "/{rom_id}/play/start", scopes=[Scopes.ROMS_READ])
async def rom_play_start(request: Request, rom_id: int) -> dict:
    """Record play history + fire lifecycle_on_play_start when the in-browser
    player launches a ROM. Called by player.html once EmulatorJS reports start.
    The play-history row is what powers the dashboard "Recently played" section
    (every launched ROM, save or not - distinct from save-based Continue playing)."""
    from plugins import events as _pe
    from handler.database.play_handler import play_handler
    try:
        await play_handler.record_start(request.state.user.id, rom_id)
    except Exception:
        logger.exception("play/start: failed to record play for rom %s", rom_id)
    title = None
    try:
        rom = await rom_handler.get_by_id(rom_id)
        title = (getattr(rom, "name", None) or getattr(rom, "fs_name_no_ext", None)) if rom else None
    except Exception:
        pass
    _pe.play_start({"id": rom_id, "title": title, "source": "rom"})
    return {"ok": True}


@protected_route(router.post, "/{rom_id}/play/end", scopes=[Scopes.ROMS_READ])
async def rom_play_end(request: Request, rom_id: int, body: _RomPlayEnd | None = None) -> dict:
    """Record elapsed play time + fire lifecycle_on_play_end when a session ends.
    `seconds` is the elapsed play time reported by player.html. last_played_at is
    already set at play/start, so Recently played survives a lost play/end POST."""
    from plugins import events as _pe
    from handler.database.play_handler import play_handler
    secs = (body.seconds if body else 0) or 0
    try:
        await play_handler.record_end(request.state.user.id, rom_id, secs)
    except Exception:
        logger.exception("play/end: failed to record play time for rom %s", rom_id)
    _pe.play_end({"id": rom_id, "source": "rom"}, secs)
    return {"ok": True}


@protected_route(router.post, "/{rom_id}/announce", scopes=[Scopes.LIBRARY_WRITE, Scopes.ROMS_READ])
async def announce_rom_added(request: Request, rom_id: int) -> dict:
    """Manually (re)send the rich "recently added" notification for this ROM -
    the "(Re)send notification" button in the ROM metadata editor. Landscape box
    art is preserved by Discord's big image; bypasses the once-only guards."""
    rom = await rom_handler.get_with_platform(rom_id)
    if rom is None:
        raise HTTPException(status_code=404, detail="ROM not found")
    from handler.notifications.recently_added import announce_rom
    sent = await announce_rom(rom_id, force=True)
    return {"ok": True, "sent": sent}


# ── Helper ────────────────────────────────────────────────────────────────────

async def _get_roms_path() -> str:
    from config import config_manager
    cfg = config_manager.get_section("roms")
    return cfg.get("library_path") or ROMS_PATH
