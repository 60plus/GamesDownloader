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
from fastapi import APIRouter, BackgroundTasks, File, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
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
from handler.library.metadata_lock import assert_unlocked
from handler.library.ownership import assert_can_delete_rom_set, claim_writes
from handler.metadata.rom_platform_map import PLATFORM_MAP, get_cover_aspect as _get_cover_aspect
from utils import download_tickets
from utils.ranged_file import content_disposition
from utils.ratings import rom_rating_agg_of
from utils.async_utils import note_unscanned
from utils.errors import safe_detail

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/roms", tags=["roms"])

# ── Scan state (single-instance lock) ─────────────────────────────────────────
# The lock moved to the scanner, where the thing it guards lives. It used to be
# here, and a handler two directories away reached across to borrow it; a timed
# scan now needs it too, and two locks would be no lock at all.
from handler.filesystem import rom_scanner as _scanner


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


class MissingRemoveBody(BaseModel):
    """The rows that were on screen. Same rule as the exclusions, same reason.

    The set of missing rows changes without anybody doing anything - a scan
    runs, a drive comes back - so recomputing it at the moment of the click
    would remove rows nobody was shown, including ones that had just stopped
    being missing.
    """

    ids: list[int]


class ExclusionsBody(BaseModel):
    patterns: str = ""


class ExclusionsApplyBody(BaseModel):
    """The rows the person was looking at when they pressed the button.

    Required, and it is the whole safety of this route. Without it the server
    recomputes the match set at the moment of the click, which is NOT the set
    that was confirmed: the saved patterns can widen in between - another tab,
    another administrator - and the click then removes rows nobody ever saw.
    """

    ids: list[int]



async def _platform_root(platform) -> str:
    """The folder this platform's ROMs actually sit in.

    Both halves of the exclusions - the preview and the save - measure patterns
    against a root, and it has to be the folder the SCAN walks or the two are
    judging different text. The scan takes its root from the directory it is
    reading (`platform_dir`, whose name becomes the fs_slug); this used to be
    built as `roms_root / platform.fs_slug` instead.

    Those differ whenever a directory name maps onto a platform by an alias -
    `genesis`, `megadrive` and `md` are one shelf - so a library kept under
    `megadrive/` had its patterns saved against a folder that does not exist and
    matched against one that does. The pattern covered nothing, in silence.

    Read from the rows, because their `fs_path` is what the scan used when it
    made them. The commonest wins when a shelf has been walked under two names
    over the years; with no rows at all there is nothing to read, and the stored
    slug is the same guess the scan will make on its first walk.
    """
    roms_root = await _get_roms_path()
    fallback = str(Path(roms_root) / platform.fs_slug)
    try:
        rows = await rom_handler.all_for_platform(platform.id)
    except Exception:  # noqa: BLE001 - a lookup failure must not lose the screen
        return fallback
    counts: dict[str, int] = {}
    for r in rows:
        path = (r.get("fs_path") or "").strip()
        if path:
            counts[path] = counts.get(path, 0) + 1
    if not counts:
        return fallback
    return max(sorted(counts), key=lambda p: counts[p])


async def _excluded_rows(platform, patterns: list[str]) -> list[dict]:
    """Rows of this platform whose file the patterns say to leave alone.

    One rule, used by both the preview and the apply. Two lists built two ways
    is how somebody confirms one thing and loses another.
    """
    from handler.filesystem.exclusions import is_excluded

    if not patterns:
        return []
    root = await _platform_root(platform)
    rows = await rom_handler.all_for_platform(platform.id)
    return [
        {"id": r["id"], "fs_name": r["fs_name"], "name": r["name"],
         "size_bytes": r["size_bytes"],
         "path": str(Path(r["fs_path"]) / r["fs_name"])}
        for r in rows
        # Same root the walk uses: the platform folder the patterns were
        # typed into. Absolute matching let `roms/` cover everything.
        if is_excluded(str(Path(r["fs_path"]) / r["fs_name"]), patterns,
                       root=root)
    ]


@protected_route(router.put, "/platforms/{slug}/exclusions", scopes=[Scopes.PLATFORMS_WRITE])
async def set_platform_exclusions(request: Request, slug: str, body: ExclusionsBody) -> dict:
    """Paths this platform's scan is told never to look at, one per line.

    Its own route rather than a field on the platform PATCH beside the display
    name: that one writes both fields on every call, so a request carrying only
    this would quietly clear the other.

    Saving changes nothing that is already in the library. It only stops a
    future scan ADDING something, which is reversible by deleting the line.
    Removing what has already slipped in is the apply route below, and it is
    deliberately a separate act.
    """
    from handler.filesystem.exclusions import parse_patterns

    platform = await rom_platform_handler.get_by_slug(slug)
    if platform is None:
        raise HTTPException(status_code=404, detail="Platform not found")
    # The folder this platform is scanned from, for the same reason as on the
    # library side: an absolute path is cut down before the guard sees it, so
    # the guard cannot pass something that matching will read as `*`.
    root = await _platform_root(platform)
    kept = parse_patterns(body.patterns, root=root)
    await rom_platform_handler.update(
        platform, {"scan_exclude": "\n".join(kept) or None}
    )
    # What was dropped, and why, rather than silently saving less than was
    # typed: a pattern that would swallow the whole tree is refused when read.
    typed = [ln.strip() for ln in (body.patterns or "").splitlines()
             if ln.strip() and not ln.strip().startswith("#")]
    # Per line, not by comparing typed text with stored text - see the same
    # spot in libraries_router for why those two are no longer equal.
    return {"patterns": kept,
            "ignored": [ln for ln in typed if not parse_patterns(ln, root=root)]}


def _really_gone(row: dict) -> bool:
    """Is the file actually absent, asked of the disk rather than of a flag.

    `missing_from_fs` is set by a scan and only cleared by another one, so it is
    a claim about the last completed walk rather than about now. Any way a scan
    can end early leaves rows flagged that are perfectly present - and the
    screen this feeds offers every listed row for removal in one act, with saves
    and play history cascading off each.

    One stat per listed row buys the whole class of stale-flag mistakes being
    harmless. It is cheap: this list is short by definition, and if it is not,
    something is wrong that a person needs to see anyway.
    """
    try:
        return not (Path(row["fs_path"]) / row["fs_name"]).is_file()
    except OSError:
        # An unreadable path is not evidence the file is gone. Left alone.
        return False


@protected_route(router.get, "/missing", scopes=[Scopes.ROMS_WRITE])
async def list_missing_roms(request: Request) -> dict:
    """Rows whose file is gone, which nothing else in the application shows.

    Administrator only: it reports filesystem paths, and it is the door to the
    bulk removal below.

    Checked against the disk, so the screen never offers a row it would then
    refuse to remove - and never offers a whole library because a scan happened
    to fall over halfway.
    """
    rows = [r for r in await rom_handler.all_missing() if _really_gone(r)]
    return {
        "count": len(rows),
        "roms": [
            {"id": r["id"],
             "name": r["name"] or r["fs_name"],
             "fs_name": r["fs_name"],
             "platform_slug": r["platform_slug"],
             "platform_name": r["platform_name"],
             "size_bytes": r["size_bytes"],
             "path": str(Path(r["fs_path"]) / r["fs_name"])}
            for r in rows
        ],
    }


@protected_route(router.post, "/missing/remove", scopes=[Scopes.ROMS_WRITE])
async def remove_missing_roms(request: Request, body: MissingRemoveBody) -> dict:
    """Delete the rows that were listed, and only those.

    There is no file to delete - that is what makes a row missing. What goes is
    the entry and everything hanging off it, saves and play history included,
    which is why the screen asks for a tick first.
    """
    shown = set(body.ids)
    # Two conditions, not one. The flag says the last scan did not find it; the
    # disk says whether that is still true. A row whose file is back - or whose
    # flag was set by a scan that fell over - is skipped and reported rather
    # than deleted with its saves.
    still_missing = {
        r["id"]: r for r in await rom_handler.all_missing() if _really_gone(r)
    }
    to_remove = [rom_id for rom_id in body.ids if rom_id in still_missing]
    skipped = sorted(shown - set(still_missing))

    removed = 0
    saves_gone = 0
    failed: list[int] = []
    for rom_id in to_remove:
        try:
            saves_gone += await _take_the_bytes_too(
                rom_id, (still_missing[rom_id] or {}).get("platform_slug"))
            if await rom_handler.delete(rom_id):
                removed += 1
            else:
                failed.append(rom_id)
        except Exception:  # noqa: BLE001 - one row must not decide the rest
            logger.exception("Could not remove missing ROM row %s", rom_id)
            failed.append(rom_id)
    if removed:
        logger.info("Removed %d ROM row(s) whose files are gone", removed)
    return {"removed": removed, "skipped": skipped, "failed": failed}


@protected_route(router.get, "/platforms/{slug}/exclusions",
                 scopes=[Scopes.PLATFORMS_WRITE])
async def get_platform_exclusions(request: Request, slug: str) -> dict:
    """What is saved, without working out what it covers.

    The preview below returns the patterns too, but it reads every row of the
    platform to do it. A settings screen has to show what is already saved
    before anybody edits it, and that must not walk a twenty thousand ROM table.

    It also keeps the preview honest. The preview reports what the SAVED
    patterns cover, so the screen may only offer it once what is typed matches
    what is saved - and it can only know that if it can read what is saved.
    """
    from handler.filesystem.exclusions import parse_patterns

    platform = await rom_platform_handler.get_by_slug(slug)
    if platform is None:
        raise HTTPException(status_code=404, detail="Platform not found")
    return {"patterns": parse_patterns(getattr(platform, "scan_exclude", None))}


@protected_route(router.get, "/platforms/{slug}/exclusions/preview",
                 scopes=[Scopes.PLATFORMS_WRITE])
async def preview_platform_exclusions(request: Request, slug: str) -> dict:
    """What applying the saved patterns would remove, listed before anything is.

    The owner's condition for this feature: nothing already in the library
    changes until it is asked for, and the list is shown first.
    """
    from handler.filesystem.exclusions import parse_patterns

    platform = await rom_platform_handler.get_by_slug(slug)
    if platform is None:
        raise HTTPException(status_code=404, detail="Platform not found")
    patterns = parse_patterns(getattr(platform, "scan_exclude", None))
    matches = await _excluded_rows(platform, patterns)
    return {"patterns": patterns, "count": len(matches), "roms": matches}


@protected_route(router.post, "/platforms/{slug}/exclusions/apply", scopes=[Scopes.ROMS_WRITE])
async def apply_platform_exclusions(
    request: Request, slug: str, body: ExclusionsApplyBody,
) -> dict:
    """Remove the rows the saved patterns match. Files on disk are left alone.

    Every route in this group is administrator-only - PLATFORMS_WRITE and
    ROMS_WRITE both sit in ADMIN_SCOPES and nowhere else. This one still asks
    for the scope that governs deleting ROM rows rather than the one that
    governs platform settings, because that is what it does: saving a pattern
    changes what a future scan adds and is undone by deleting a line, while this
    deletes rows, and the saves and play history hanging off them go too.

    The files stay where they are on purpose. The point of a pattern is that
    something belongs in that folder and is not a game - removing the row is the
    fix, removing the file would be destroying whatever it actually was.
    """
    from handler.filesystem.exclusions import parse_patterns

    platform = await rom_platform_handler.get_by_slug(slug)
    if platform is None:
        raise HTTPException(status_code=404, detail="Platform not found")
    patterns = parse_patterns(getattr(platform, "scan_exclude", None))
    matches = await _excluded_rows(platform, patterns)

    # THE LIST SHOWN IS AN UPPER BOUND. The patterns are still recomputed, so a
    # row that has stopped matching is not removed; but a row that started
    # matching after the list was drawn was confirmed by nobody, and is left
    # alone. Only the intersection goes.
    shown = set(body.ids)
    still_matching = {row["id"] for row in matches}
    to_remove = [row for row in matches if row["id"] in shown]
    skipped = sorted(shown - still_matching)

    # Each delete is its own committed transaction, so an exception partway
    # leaves the earlier ones gone. Reporting that as total failure is the worst
    # available answer, because the obvious response to it is to press the
    # button again.
    removed = 0
    saves_gone = 0
    failed: list[int] = []
    for row in to_remove:
        try:
            saves_gone += await _take_the_bytes_too(row["id"], slug)
            if await rom_handler.delete(row["id"]):
                removed += 1
            else:
                failed.append(row["id"])
        except Exception:  # noqa: BLE001 - one row must not decide the rest
            logger.exception("Could not remove ROM row %s on %s", row["id"], slug)
            failed.append(row["id"])
    if failed:
        logger.warning("%d row(s) on %s could not be removed", len(failed), slug)
    if removed:
        logger.info("Removed %d ROM row(s) on %s matching its scan exclusions "
                    "(files left on disk)", removed, slug)
    if skipped:
        logger.info("Left %d row(s) on %s alone: they no longer match the saved "
                    "patterns", len(skipped), slug)
    return {"removed": removed, "roms": to_remove, "skipped": skipped,
            "failed": failed}


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


@protected_route(router.get, "/convert-chd/jobs", scopes=[Scopes.ROMS_WRITE])
async def list_chd_jobs(request: Request) -> list[dict]:
    """Conversions this server knows about, so a refreshed page finds them.

    For whoever may start one. Every account used to be able to read these,
    failures and chdman's diagnosis included (1.0.34 audit, #17); the tray
    already treats a refusal here as "not an administrator".
    """
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

def _plugin_dir_for_provider(provider_id: str) -> str:
    """Where a metadata provider's plugin lives, and so where its logo is.

    Shared with the settings router, which answers the same question for the
    list of providers the editor draws its header icons from. Two copies of the
    guess disagreed about protondb, and one of them was on screen.
    """
    from plugins.manager import plugin_dir_for_provider

    return plugin_dir_for_provider(provider_id)


def _plugin_search_candidates(per_plugin: list) -> list[dict]:
    """Plugin search answers, in the shape the candidate grid reads.

    >>> BUILT FROM THE SEARCH ANSWER ALONE. `metadata_get_game` is one request
    per candidate, and TheGamesDB's free allowance is about a thousand a month -
    it had already spent a month of it in two days by asking too often. A year
    and a cover appear here only when the provider's own search answer carried
    them, which costs nothing; a provider that sends neither gets a plain tile,
    which is what several built-in results look like already.
    """
    out: list[dict] = []
    for provider_results in per_plugin or []:
        if not isinstance(provider_results, list):
            continue
        for r in provider_results[:8]:
            if not isinstance(r, dict):
                continue
            pid = str(r.get("provider_id") or "")
            gid = str(r.get("provider_game_id") or "")
            name = str(r.get("name") or "")
            # A row with no id cannot be selected and a row with no name is an
            # unlabelled tile. Neither belongs in the grid.
            if not pid or not gid or not name:
                continue
            out.append({
                "source":            "plugin",
                "provider_id":       pid,
                "provider_game_id":  gid,
                "plugin_id":         _plugin_dir_for_provider(pid),
                "ss_id":             None,
                "igdb_id":           None,
                "launchbox_id":      None,
                "sgdb_id":           None,
                "name":              name,
                "year":              r.get("year"),
                "developer":         r.get("developer"),
                "cover_url":         r.get("cover_url") or None,
                "regions":           [],
                "_sourceIcon":       f"/api/plugins/{_plugin_dir_for_provider(pid)}/logo",
            })
    return out


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

    # ── Metadata plugins ──────────────────────────────────────────────────────
    #
    # The header above this list already draws every metadata plugin's logo
    # beside the four built-in ones, and this route asked none of them: an
    # installed, enabled, answering plugin could not appear among the results
    # however well it answered. Reported by the owner with a ring drawn round
    # that row of chips.
    #
    # Off the event loop, each plugin on its own thread with its own time limit
    # (`call_each`). Plugin code is third-party and synchronous, and it goes to
    # the network. It used to be one pluggy call on one thread, and pluggy
    # throws away every answer when one plugin raises - so a broken provider
    # emptied the other providers' chips, and a hung one had no limit at all.
    plugin_results: list[dict] = []
    try:
        from plugins.manager import plugin_manager
        _per_plugin = await plugin_manager.call_each("metadata_search_game", query=query.strip())
        plugin_results = _plugin_search_candidates(_per_plugin)
    except Exception as _e:
        # Only reading the answers can fail here now; a plugin that throws has
        # already cost its own results and nothing else. The four built-in
        # sources are what this editor is for.
        logger.warning("Plugin metadata search failed: %s", _e)

    # ScreenScraper cover URLs carry the server's password; wrap them so the
    # browser only ever sees a credential-free proxy URL. Public covers pass
    # through unchanged.
    from utils.media_proxy import proxy_media_list
    return proxy_media_list(
        ss_results + igdb_results + lb_results + sgdb_results + plugin_results,
        key="cover_url",
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

    # Who owns this ROM and who fetched it, looked up only when there is
    # something to look up. Most ROMs were found on the disk by a scan and have
    # neither, and the page simply leaves both rows out for those.
    owner_name = uploader_name = None
    if rom.published_by or rom.uploaded_by:
        from handler.database.session import async_session_factory as _asf
        from models.user import User as _U
        from sqlalchemy import select as _sel
        wanted = {i for i in (rom.published_by, rom.uploaded_by) if i}
        async with _asf() as _s:
            names = dict((await _s.execute(
                _sel(_U.id, _U.username).where(_U.id.in_(wanted))
            )).all())
        owner_name = names.get(rom.published_by)
        # Only when a claim has parted the two. Before that they are the same
        # account and the page would be printing one person twice.
        if rom.uploaded_by and rom.uploaded_by != rom.published_by:
            uploader_name = names.get(rom.uploaded_by)

    return {
        "disks":           disks,
        "playlist":        playlist,
        "published_by":      rom.published_by,
        "owner_username":    owner_name,
        "uploaded_by":       rom.uploaded_by,
        "uploader_username": uploader_name,
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
        "metadata_locked": bool(getattr(rom, "metadata_locked", False)),
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
    assert_unlocked(request, rom)

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
        # A proxy token, or anything that is plainly somebody else's address.
        # The second half was missing, and each of the editor's media tabs has a
        # box inviting exactly that - its placeholder reads "https://..." - so a
        # pasted address went into the column verbatim and was served from the
        # far end forever after. That breaks the rule every other media path
        # here keeps: fetch it, serve it ourselves. It also means the media
        # disappears the day the far end moves it, and that every render hands
        # the viewer's address to a third party nobody chose.
        if isinstance(_pv, str) and (
            PROXY_PREFIX in _pv or _pv.startswith(("http://", "https://"))
        ):
            setattr(body, _uf, _pv)     # download it via the *_url branch below
            setattr(body, _pf, None)    # never store a foreign address as a path

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
    _failed: list[str] = []
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
            else:
                # It used to end here in silence: the editor reported a saved
                # dialog and the media was exactly as before, which is the one
                # answer nobody can act on.
                _failed.append(fname)
                logger.warning("ROM %s: could not fetch %s from %s",
                               rom_id, fname, url_val[:120])

    if _chosen:
        from handler.metadata.rom_scrape_handler import with_manual
        data["media_source"] = with_manual(rom, *_chosen)

    if data:
        await rom_handler.update_metadata(rom_id, data)

    updated = await rom_handler.get_with_platform(rom_id)
    if updated is None:
        return {"ok": True, "media_failed": _failed}
    return {
        # Which media could not be fetched, so the editor can say so instead of
        # showing a saved dialog over an unchanged picture. Empty on the happy
        # path, which is nearly always.
        "media_failed":    _failed,
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
    assert_unlocked(request, rom)

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

        _search_q = rom.name or rom.fs_name_no_ext or ""
        _resolve_plugin_id = _plugin_dir_for_provider

        def _tag_plugin_results(items: list, target: list) -> None:
            for r in items:
                if not isinstance(r, dict):
                    continue
                pid = (r.get("_source") or "").lower().replace(" ", "")
                r["source"] = "plugin"
                r["_sourceIcon"] = f"/api/plugins/{_resolve_plugin_id(pid)}/logo"
                target.append(r)

        # Covers, heroes and logos, the three asked side by side. Each call asks
        # its plugins on their own threads (`call_each`): these used to run on
        # the event loop, one after another, and a slow upstream stalled every
        # request on the server for as long as it took (1.0.34 audit, #14).
        _covers, _heroes, _logos = await asyncio.gather(
            plugin_manager.call_each("metadata_get_covers", query=_search_q),
            plugin_manager.call_each("metadata_get_heroes", query=_search_q),
            plugin_manager.call_each("metadata_get_logos", query=_search_q),
        )
        for pr in _covers:
            if isinstance(pr, list):
                _tag_plugin_results(pr, plugin_covers)
        for pr in _heroes:
            if isinstance(pr, list):
                _tag_plugin_results(pr, plugin_fanarts)
        for pr in _logos:
            if isinstance(pr, list):
                _tag_plugin_results(pr, plugin_wheels)

        # Screenshots + detail_sources via metadata_search_game -> metadata_get_game
        try:
            all_search = await plugin_manager.call_each("metadata_search_game", query=_search_q)
            for provider_results in all_search:
                if not isinstance(provider_results, list) or not provider_results:
                    continue
                best = provider_results[0]
                pid = best.get("provider_id", "")
                gid = best.get("provider_game_id", "")
                if not pid or not gid:
                    continue
                game_data_list = await plugin_manager.call_each("metadata_get_game", provider_game_id=gid)
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

class RomLockBody(BaseModel):
    locked: bool


@protected_route(router.post, "/{rom_id}/lock", scopes=[Scopes.ROMS_WRITE])
async def set_rom_lock(request: Request, rom_id: int, body: RomLockBody) -> dict:
    """Close a ROM's metadata to everyone but an administrator, or open it.

    The same field and the same rule a library game carries, so one padlock
    behaves the same wherever the editor is opened from.
    """
    rom = await rom_handler.get_with_platform(rom_id)
    if rom is None:
        raise HTTPException(status_code=404, detail="ROM not found")
    await rom_handler.update(rom, {"metadata_locked": bool(body.locked)})
    return {"ok": True, "metadata_locked": bool(body.locked)}


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
    question is the number of files the answer removes. The rule itself lives in
    rom_removal, because a CHD conversion asks it too.
    """
    return await rom_removal.removable_tracks(members)


# The same declaration as the delete below, and the same ownership question
# inside it: you may see what a deletion would take exactly when you could
# perform it. It used to be admin-only, so the one screen where an uploader
# removes their own ROMs could not ask - and asked a one-sentence question
# instead, for an act that takes every disc of the title and every account's
# saves for all of them.
@protected_route(router.get, "/{rom_id}/removal", scopes=[Scopes.ROMS_READ])
async def rom_removal_preview(request: Request, rom_id: int) -> dict:
    """What deleting this ROM would take with it.

    Asked before the question is put to the player, because the two things that
    make this destructive are invisible from the page: a floppy title is
    several rows that only mean anything together, and the saves that go with
    them may belong to people other than whoever is looking.
    """
    named = await rom_handler.get_by_id(rom_id)
    if named is None:
        raise HTTPException(status_code=404, detail="ROM not found")
    members = await rom_handler.disk_set(rom_id)
    if not members:
        raise HTTPException(status_code=404, detail="ROM not found")
    assert_can_delete_rom_set(request, named, members)
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


# ── Trailer: candidates, fetch, and how the fetch is going ───────────────────
#
# A library game has had these three since long before a ROM did, which is what
# the report was about: a retro game could be given a video from ScreenScraper,
# uploaded from a file or pasted as a URL, but never FETCHED from a provider the
# way an ordinary game can. The work is the same on both sides and now literally
# is: the yt-dlp call lives once, in media_handler, and only the directory the
# file lands in differs.

# Both borrowed from the game route rather than retyped: a second copy of the
# id pattern or the quality ladder is a second thing to drift.
from endpoints.library.library_router import _VIDEO_QUALITIES, _YT_ID_RE

_rom_video_jobs: dict[int, dict] = {}
_ROM_VIDEO_JOBS_KEEP = 200


def _remember_rom_video_job(rom_id: int, **fields) -> None:
    job = _rom_video_jobs.setdefault(rom_id, {"rom_id": rom_id})
    job.update(fields)
    # Oldest first: dicts keep insertion order and a re-run re-inserts, so this
    # drops whatever has gone longest without anybody pressing it.
    while len(_rom_video_jobs) > _ROM_VIDEO_JOBS_KEEP:
        _rom_video_jobs.pop(next(iter(_rom_video_jobs)))


class RomVideoDownloadBody(BaseModel):
    video_id: str
    quality: str | None = "1080"


@protected_route(router.get, "/{rom_id}/videos", scopes=[Scopes.LIBRARY_WRITE, Scopes.ROMS_READ])
async def rom_video_options(request: Request, rom_id: int, q: str = "") -> list:
    """Trailer candidates for a ROM, searched live by title.

    A library game reads these from a stored `videos` column that its metadata
    providers filled. A ROM has no such column and does not need one: the game
    route searches the provider by title anyway, so the same search works here
    with the ROM's own name. `q` overrides it, because a ROM's filename is
    often a better search than its scraped title, and sometimes far worse.
    """
    rom = await rom_handler.get_by_id(rom_id)
    if rom is None:
        raise HTTPException(status_code=404, detail="ROM not found")
    from endpoints.library.library_router import _igdb_video_options

    return await _igdb_video_options(q or rom.name or rom.fs_name_no_ext)


@protected_route(router.post, "/{rom_id}/video/download",
                 scopes=[Scopes.LIBRARY_WRITE, Scopes.ROMS_READ])
async def download_rom_video(
    request: Request, rom_id: int, body: RomVideoDownloadBody, bg: BackgroundTasks,
) -> dict:
    """Fetch the chosen trailer onto the server, in the background.

    Into the ROM's own media directory, beside its cover and screenshots, so
    removing that folder removes all of it. The editor polls the status route
    below; without that it would show a spinner that never resolves.
    """
    rom = await rom_handler.get_with_platform(rom_id)
    if rom is None:
        raise HTTPException(status_code=404, detail="ROM not found")
    # An admin closing a ROM's metadata closes all of it. A media route that
    # skipped this would be the way around the padlock.
    assert_unlocked(request, rom)
    if not _YT_ID_RE.match(body.video_id or ""):
        raise HTTPException(status_code=400, detail="Invalid video id")

    quality = body.quality if body.quality in _VIDEO_QUALITIES else "1080"
    slug = rom.platform.slug if rom.platform else "unknown"

    _rom_video_jobs.pop(rom_id, None)
    _remember_rom_video_job(rom_id, state="running", video_id=body.video_id,
                            quality=quality, error=None, url=None)

    async def _task() -> None:
        from handler.library.media_handler import download_youtube_to
        from handler.metadata.rom_scrape_handler import _resource_url, _rom_media_dir
        try:
            name, error = await download_youtube_to(
                _rom_media_dir(slug, rom_id), body.video_id, quality,
            )
        except Exception:
            # download_youtube_to swallows yt-dlp's own failures, so reaching
            # here means our side broke. It still has to reach the editor,
            # otherwise we are back to the silent spinner.
            logger.exception("ROM trailer task crashed rom_id=%s", rom_id)
            _remember_rom_video_job(rom_id, state="failed", error="failed")
            return
        if name:
            url = _resource_url(slug, rom_id, name)
            await rom_handler.update_metadata(rom_id, {"video_path": url})
            _remember_rom_video_job(rom_id, state="done", url=url, error=None)
        else:
            _remember_rom_video_job(rom_id, state="failed", error=error or "failed")

    bg.add_task(_task)
    return {"started": True}


@protected_route(router.get, "/{rom_id}/video/status",
                 scopes=[Scopes.LIBRARY_WRITE, Scopes.ROMS_READ])
async def rom_video_status(request: Request, rom_id: int) -> dict:
    """How the last trailer fetch for this ROM ended.

    `state` is one of running, done, failed or idle. On failure `error` carries
    a stable code the editor turns into a sentence, because yt-dlp's own text is
    three lines of wiki links about exporting browser cookies.
    """
    job = _rom_video_jobs.get(rom_id)
    if not job:
        return {"state": "idle"}
    return {
        "state":    job.get("state", "idle"),
        "error":    job.get("error"),
        "url":      job.get("url"),
        "video_id": job.get("video_id"),
        "quality":  job.get("quality"),
    }


@protected_route(router.post, "/{rom_id}/claim", scopes=[Scopes.ROMS_WRITE])
async def claim_rom(request: Request, rom_id: int, from_user_id: int | None = None) -> dict:
    """Take a ROM over from the account that fetched it.

    The same three effects as claiming a game, and the same two of them happen
    without being written: the uploader loses the delete, because that rule
    reads the owner, and the ROM leaves their quota, because the quota is a sum
    rather than a counter. Only the owner is written, by the shared rule, so a
    ROM keeps the name of whoever brought it in exactly as a game does.
    """
    rom = await rom_handler.get_by_id(rom_id)
    if rom is None:
        raise HTTPException(status_code=404, detail="ROM not found")
    # Whose ROM this was, when the caller says. The screen that sends these
    # draws a list of one account's things and then acts on it a moment later;
    # in between, another administrator can claim one, or an upload can change
    # hands. Without this the click takes it from whoever holds it NOW and
    # reports success, which is the same gap the game claim beside it closed.
    if from_user_id is not None and getattr(rom, "published_by", None) != from_user_id:
        return {"ok": True, "id": rom_id, "skipped": True,
                "owner_username": getattr(getattr(request.state, "user", None),
                                          "username", None)}
    admin = getattr(request.state, "user", None)
    fields = claim_writes(admin_id=getattr(admin, "id", None))
    await rom_handler.set_published_by(rom_id, fields["published_by"])
    return {
        "ok": True,
        "id": rom_id,
        "owner_username": getattr(admin, "username", None),
    }


# Declared against the weaker permission on purpose. An uploader may remove a
# ROM they fetched, to undo their own bad download, and that is not a rule
# scopes can carry: protected_route requires every scope it is given, so
# "an admin, or else the owner" has to be settled in the handler. The
# assert_can_delete_rom below is the other half of this declaration and the
# two belong together.
#
# ROMS_READ, and nothing else. It is an emulation route, so an account with
# emulation switched off loses it. It used to name LIBRARY_UPLOAD as well, which
# is a GAMES permission and is not what the rule inside asks for: can_delete_rom
# says ROMS_WRITE, or the owner. An administrator with the Games chip off is
# still drawn the delete button - that is decided by role - and both this and
# the preview above it could then only answer 403.
@protected_route(router.delete, "/{rom_id}", scopes=[Scopes.ROMS_READ])
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
    named = await rom_handler.get_by_id(rom_id)
    if named is None:
        raise HTTPException(status_code=404, detail="ROM not found")
    disks = await rom_handler.disk_set(rom_id)
    if not disks:
        raise HTTPException(status_code=404, detail="ROM not found")
    # Asked about every row this is going to take, not just the first of them.
    # It used to read disks[0] with a comment calling that "the row the caller
    # named" - but disk_set returns the group sorted by disc number, so it is
    # the lowest disc whichever one was asked for. Fetching disc 1 was enough to
    # delete disc 2, its files and every account's saves for it.
    assert_can_delete_rom_set(request, named, disks)

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



async def _take_the_bytes_too(rom_id: int, slug: str | None) -> int:
    """Remove the files a row is about to stop being able to name. Count saves.

    `rom_handler.delete` drops the row and the database cascades the savestate,
    battery-save and play-history ROWS with it - and that is all it does. The
    bytes stay, and they stay UNREACHABLE: the save path is keyed by the ROM's
    autoincrement id, so a file that comes back on the next scan gets a new id
    and a new directory, and nothing in the interface can name the old one
    again.

    `delete_rom` has done this since it was written; the two mass buttons -
    remove-missing and apply-exclusions - called `delete` on its own, while the
    screen promised "saves, play history, collection membership" go too.

    Called BEFORE the delete, because the lists that name these files are read
    through the row.
    """
    saved = 0
    try:
        states = await save_state_handler.list_states_for_rom(rom_id)
        saves = await save_state_handler.list_saves_for_rom(rom_id)
        saved = await asyncio.to_thread(rom_removal.delete_save_files, states, saves)
        if slug:
            await asyncio.to_thread(rom_removal.delete_media_dir, slug, rom_id)
    except Exception:  # noqa: BLE001 - one row's files must not stop the rest
        logger.exception("Could not remove the files behind ROM row %s", rom_id)
    return saved


# ── ROM Upload ────────────────────────────────────────────────────────────────

def _schedule_registration(background_tasks, fs_slug: str, names: list[str],
                           owner_id: int | None, *,
                           new_names: list[str] | None = None,
                           newer_than: int | None = None,
                           release=None) -> None:
    """Have the files that landed scanned in and stamped, after the response.

    Called on the way out AND on the way out through a refusal, because bytes
    that reached the disk have to be counted whether or not the rest of the
    request succeeded.

    `release` lets go of the upload's quota reservation once that is done: until
    the scan has made the rows and the stamp has charged them, the reservation is
    the only thing counting those bytes against the account. Called whatever
    happens, and at once when nothing landed.
    """
    if not names:
        if release is not None:
            release()
        return
    landed = list(names)
    # Every landed name is scanned in; only names that had no row before the
    # request may be stamped. See _stamp_uploaded.
    stampable = set(new_names) if new_names is not None else None

    async def _run():
        from handler.roms.rom_source_handler import scan_after_write

        # Tried more than once, because the scan that registers these files can
        # be stopped by an administrator halfway - and a stopped scan takes back
        # the rows it created, so the stamp finds nothing and the ROM ends up
        # owned by nobody FOR EVER: the scan is owner-blind by design, so no
        # later scan repairs it, it counts against no quota, and the account
        # that uploaded it cannot delete it.
        #
        # Each call to scan_after_write registers a fresh write and waits for a
        # scan that covers it, so a second call really does run another scan
        # rather than returning satisfied. Bounded, because an administrator who
        # keeps pressing Stop must not have us starting scans for ever.
        pending = list(landed)
        try:
            for _attempt in range(3):
                await scan_after_write()
                pending = await _stamp_uploaded(fs_slug, pending, owner_id, only=stampable,
                                                newer_than=newer_than)
                if not pending:
                    return
            logger.warning(
                "Uploaded ROM(s) %s still have no row after three scans; they are "
                "owned by nobody and count against no quota",
                ", ".join(pending),
            )
        finally:
            if release is not None:
                release()

    background_tasks.add_task(_run)


async def _stamp_uploaded(fs_slug: str, names: list[str], owner_id: int | None,
                          *, only: set[str] | None = None,
                          newer_than: int | None = None) -> list[str]:
    """Record who put these files here, once a scan has made rows for them.

    The scan itself is owner-blind on purpose: it re-walks the whole tree, so
    stamping there would hand one account every ROM on the disk. This is the one
    place that knows a particular file was put here by a particular person, so
    this is where it is recorded - the same shape, and the same reasoning, as
    the download path in rom_source_handler.

    Only onto a row that has no owner yet, which `set_owner` enforces as well:
    uploading over an existing file must not move it from one account to another
    and must not undo an admin's claim.
    """
    if not owner_id or not names:
        return []
    from handler.metadata.rom_platform_map import slug_from_fs_slug

    platform = await rom_platform_handler.get_by_slug(slug_from_fs_slug(fs_slug))
    if platform is None:
        logger.warning("Uploaded ROMs into %s but no platform row to attach them to", fs_slug)
        return list(names)
    shelf_dir = (Path(await _get_roms_path()) / fs_slug).resolve()
    missing: list[str] = []
    for name in names:
        rom = await rom_handler.get_by_fs_name(platform.id, name)
        if rom is None:
            # No row yet. Usually a scan that was stopped before it reached this
            # platform, or one that took back what it had created. Returned to
            # the caller rather than shrugged off, so it can ask for another.
            missing.append(name)
            continue
        # Only a row this upload brought into being: a name that had no row when
        # the request arrived, whose row now carries exactly that name in exactly
        # the folder the file was written to. Anything else is a row the upload
        # merely landed beside - a copy under roms/, the same name in other
        # letter case - and owning it would let this account delete a file that
        # is not the one it sent, along with every account's saves.
        if only is not None and name not in only:
            continue
        if getattr(rom, "fs_name", None) != name:
            continue
        if Path(str(getattr(rom, "fs_path", "") or "")).resolve() != shelf_dir:
            continue
        # And made after the upload asked. The scanner's rename adoption moves a
        # new file's name and folder onto the old row of a ROM whose file went
        # missing, and that row keeps its id - with every account's saves.
        if newer_than is not None and int(getattr(rom, "id", 0) or 0) <= newer_than:
            continue
        if getattr(rom, "published_by", None) is None:
            await rom_handler.set_owner(rom.id, owner_id)
    return missing




def _is_shelf_slug(slug: str) -> bool:
    """Whether this is one shelf name, and not a way out of the ROM tree.

    The upload route builds its destination as `roms_base / slug` with the slug
    taken straight from the URL, and a slug is a path segment like any other:
    `..` walks up, a slash makes a subtree, an empty one lands on the root.
    Asked BEFORE the directory is made, because `mkdir(parents=True)` on a bad
    slug has already created it by the time anything else looks.
    """
    if not slug or slug in (".", ".."):
        return False
    if "/" in slug or "\\" in slug:
        return False
    return Path(slug).name == slug


def _may_replace(request, existing) -> bool:
    """Whether this caller may write over the file that is already here.

    This route asked nothing at all, so a file name was enough to destroy
    somebody else's ROM, while the row kept their name and the bytes stayed on
    their quota.

    Replacing your own is left working: swapping a bad dump for a good one is
    the ordinary reason to send the same name twice. The rule is `can_delete_rom`
    itself rather than a second opinion about ownership, so this and the delete
    button can never disagree - and an unowned row (scanned in years ago,
    carrying other people's saves) is nobody's to overwrite.

    NO ROW IS NOT NOBODY. The first version answered True for `existing is None`
    under the name "a name that is not there yet", but the only call site sits
    inside `if dest_path.exists()`: by then the file IS there, and a missing row
    says the library has not catalogued it, not that the shelf is empty. Reading
    that as free left every uncatalogued file writable by anyone who knew its
    name - permanently so for subchannel files, which are deliberately not ROM
    extensions and therefore never get a row from any scan.

    So it is refused, on the same terms an unowned row already was: an
    administrator may, because somebody has to be able to tidy up a shelf the
    library never catalogued, and ROMS_WRITE is what the rest of the ROM API
    treats as administrative. `can_delete_rom` reads the owner off the object
    with `getattr`, so None arrives at exactly that answer without a branch.
    """
    from handler.library.ownership import can_delete_rom

    user = getattr(request.state, "user", None)
    scopes = getattr(request.state, "scopes", set())
    return can_delete_rom(scopes, getattr(user, "id", None), existing)


#: How large a subchannel file is allowed to be.
#:
#: These are the one kind of file admitted here that can never hold a row, so
#: they never reach `used_bytes` and every request finds the allowance full
#: again. Nothing bounded the size, which made the exception free storage of any
#: size for anybody able to put a file with a ROM extension on a shelf - and
#: that neighbour may be zero bytes long, so the price of unlocking a pair was
#: nothing at all.
#:
#: A real .sbi is 452 bytes. A .sub carries 96 bytes of subchannel data per
#: sector, and an 80 minute disc holds 360,000 sectors, so a full one is about
#: 33 MB. 64 MB leaves that most of a doubling of room and still says no to
#: anything that is plainly not subchannel data.
_MAX_SUBCHANNEL_BYTES = 64 * 1024 * 1024


def _is_this_file(row, dest_path: Path) -> bool:
    """Whether the ROM row is the file at `dest_path`: the same name, exactly,
    in the same folder. What sending a better dump under its name replaces."""
    return (getattr(row, "fs_name", None) == dest_path.name
            and Path(getattr(row, "fs_path", "") or "") == dest_path.parent)


def _sidecar_disc(name: str, directory):
    """The disc this subchannel file belongs to, or None if it names none.

    Returns the disc rather than a yes/no, because both questions this route
    asks about a .sbi are really questions about that disc: whether it may be
    admitted at all, and - since a subchannel file can never have a row of its
    own to carry an owner - who is allowed to write over it.

    Bound to a real disc on purpose. Letting .sbi and .sub through on the
    extension alone would reopen the hole this gate exists to close: they are
    not ROM extensions, so the scan makes no row, so nothing owns them and
    nothing counts them. Tied to a disc, the most anybody can leave behind is
    one .sbi and one .sub per disc they already paid for.

    Matched by stem, case-insensitively, against a file the scanner would
    recognise - the same rule as `subchannel_files_for`, so a file admitted
    here is a file the reader will actually pick up. The disc has to BE a ROM:
    matching any stray neighbour would let two uploads bootstrap each other.
    """
    if Path(name).suffix.lower() not in _scanner.SUBCHANNEL_EXTENSIONS:
        return None
    stem = Path(name).stem.lower()
    try:
        entries = list(Path(directory).iterdir())
    except OSError:
        return None
    for entry in sorted(entries):
        if (entry.is_file()
                and entry.stem.lower() == stem
                and entry.suffix.lstrip(".").lower() in _scanner._ROM_EXTENSIONS):
            return entry
    return None


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
    # Both questions before a single byte moves, and before the directory is
    # made: the slug comes from the URL and is used as a path segment, so `..`
    # reaches out of the ROM tree, and a slug that is merely unknown makes a
    # folder no scan will ever read.
    if not _is_shelf_slug(slug):
        raise HTTPException(status_code=400, detail="That is not a platform.")
    # Asked of the MAP of platforms GD knows, not of the `rom_platforms` table.
    #
    # Those rows are written in exactly one place - the scanner's upsert - and
    # the scan skips a platform whose folder is empty and has no rows. Meanwhile
    # `_init_rom_dirs()` makes a folder for every known platform on first boot.
    # A fresh install therefore has a hundred folders and no rows at all, so
    # asking the database refused an upload to EVERY platform: the one way a
    # person puts their first ROM on a shelf, closed by a check meant to stop a
    # slug reaching out of the ROM tree.
    #
    # The map is what `/roms/platforms/known` already hands the screen, so the
    # list the interface offers and the list this route accepts are the same
    # one. A platform with no row yet is exactly what the screen labels "New".
    from handler.metadata.rom_platform_map import PLATFORM_MAP, canonical_fs_slug

    if slug not in PLATFORM_MAP:
        raise HTTPException(status_code=404, detail="Platform not found")

    # The folder the platform actually keeps its ROMs in, which is not always
    # the name that arrived. Eighteen platforms answer to two or three keys -
    # `psx` and `playstation`, `snes` and `super-nintendo` - and this route used
    # to make a directory out of whichever one was asked for. `_init_rom_dirs`
    # makes only the canonical one and `/roms/platforms/known` offers only the
    # canonical one, so the second folder could only ever be created here.
    #
    # It is not a cosmetic duplicate. The scan walks EVERY directory under the
    # root and upserts the platform by URL slug, so both folders resolve to one
    # platform row, and a ROM is identified by (platform, file name) with no
    # uniqueness constraint. So the same name sent through the alias folder does
    # not overwrite anybody's bytes - it repoints their row at this file on the
    # next scan, and the ownership check below never fired, because in a folder
    # of its own the name was not there yet.
    fs_slug = canonical_fs_slug(slug)
    roms_base = await _get_roms_path()
    dest_dir = Path(roms_base) / fs_slug
    dest_dir.mkdir(parents=True, exist_ok=True)

    saved: list[str] = []
    rejected: list[dict] = []
    # What goes on to be scanned in and stamped. Not the same list as `saved`:
    # a subchannel file lands on the shelf and belongs in the answer, but it can
    # never hold a row, so putting it in the registration queue only buys three
    # full walks of the library and a warning about a state that is intended.
    to_register: list[str] = []

    # Subchannel files last, whatever order they arrived in.
    #
    # One is admitted only beside the disc it names, and that disc is looked for
    # ON THE SHELF - so in a request carrying both, whether it worked depended on
    # which one the browser listed first. Dropping `Game.sbi` and `Game.cue`
    # together is one action to the person doing it, and the refusal is silent:
    # `rejected` comes back in the JSON and no screen in this project shows it.
    # A stable sort, so nothing else about the order changes.
    files = sorted(
        files,
        key=lambda u: Path(u.filename or "").suffix.lower()
        in _scanner.SUBCHANNEL_EXTENSIONS,
    )

    # Pre-resolve once so per-file scanning is cheap when disabled
    try:
        from handler.clamav import clamav_handler as _clam
        scan_uploads = await _clam.is_upload_scanning_enabled()
    except Exception:
        scan_uploads = False

    user = getattr(request.state, "user", None)
    actor = user.username if user else None

    # The body-size middleware lets this route through with no ceiling at all,
    # on the stated grounds that routes streaming to disk "enforce their own
    # limit as they go". This one did not: the loop below counted nothing, so
    # between the exemption and the empty loop there was no limit anywhere and
    # one account could fill the volume. The ceiling is the same one the library
    # upload uses - the per-file maximum, brought down to whatever the account
    # has left of its quota - and it is spent across the whole request rather
    # than per file, because ten files of a gigabyte are a ten gigabyte upload.
    from handler.library import quota

    from handler.roms.rom_source_handler import max_rom_bytes

    remaining = await quota.ceiling_for(user, max_rom_bytes())

    # The bytes this request writes, counted with the account's other streams at
    # every chunk: `remaining` was the room when the request arrived, and the
    # account's other uploads grow while this one runs. Held until the scan has
    # registered the files and the stamp has charged them - see the `release`
    # handed to _schedule_registration - and let go at once if this request
    # dies some other way.
    reservation = await quota.reservation_for(user)
    reservation.open()

    # The platform row, once, before anything is written. A shelf that has never
    # been scanned has no row - the ordinary state of every platform until its
    # first ROM lands - and then no name on it belongs to anybody.
    from handler.metadata.rom_platform_map import slug_from_fs_slug

    _row = await rom_platform_handler.get_by_slug(slug_from_fs_slug(fs_slug))
    # And the newest ROM row so far, asked at the same moment for the same reason.
    # The scan can carry an upload onto an OLD row - a ROM whose file vanished,
    # found again under the uploaded name by its hash - and that row keeps its
    # id. Asked here, before anything is written, and not when registration
    # runs: by then another upload's scan may already have registered this file,
    # and its own row would count as older than the upload.
    newest_before = await rom_handler.max_rom_id()
    # Names that had no row on this platform when the request arrived. Only these
    # can become this account's; see _stamp_uploaded.
    brought_here: list[str] = []

    try:
        for upload in files:
            if not upload.filename:
                continue
            safe_name = Path(upload.filename).name          # strip any directory parts
            # Refused here rather than written and forgotten. The scan only ever
            # registers a file whose extension it recognises, and a file with no row
            # has no owner, so it counts against nobody's quota and can be repeated
            # for ever - the volume fills while My uploads reads zero. Asked of the
            # scanner's own list, so the two cannot drift apart.
            # `Path(...).suffix`, the same question the scanner asks. It used to
            # read the letters after the last dot, and the comment below claimed the
            # two could not drift apart - which was false for a name that is nothing
            # but a dot and an extension. `.iso` gave "iso" here and passed, while
            # the scanner sees a hidden file with no suffix and never makes a row:
            # no row, no owner, no quota, repeatable for ever. Once per extension.
            suffix = Path(safe_name).suffix.lower()
            recognised = suffix.lstrip(".") in _scanner._ROM_EXTENSIONS
            # ...and the files that belong TO a disc rather than being one. A .sbi is
            # 452 bytes of subchannel data that a PAL PlayStation disc needs to boot
            # past its LibCrypt check; the scanner deliberately keeps these out of
            # _ROM_EXTENSIONS, so this gate refused them - and the download path
            # applies the same rule, which left no way at all to put one on the
            # shelf. Admitted here only beside the disc they name, which is the same
            # question `subchannel_files_for` asks when it goes looking for them.
            sidecar_disc = None if recognised else _sidecar_disc(safe_name, dest_dir)
            if sidecar_disc is not None:
                recognised = True
            if not recognised:
                rejected.append({
                    "filename": safe_name,
                    "threat": None,
                    "action": "extension_not_recognised",
                })
                continue
            dest_path = dest_dir / safe_name
            # Asked before the open, because "wb" truncates on the first byte and
            # there is no undoing that. A name nobody holds is free; one somebody
            # else holds is refused rather than silently overwritten.
            #
            # >>> ASKED WHETHER OR NOT A FILE SITS AT THE DESTINATION. It used to be
            # asked only `if dest_path.exists()`, and a ROM is identified by
            # (platform, file name) with no uniqueness: a copy under `roms/`, or the
            # same name in other letter case - the database compares names without
            # regard to case - is the SAME row while `exists()` here saw nothing.
            # The file was written, the scan folded it into that row, and the stamp
            # made the uploader the owner of a ROM carrying other accounts' saves,
            # which the delete button then removed together with the original.
            existing = (
                await rom_handler.get_by_fs_name(_row.id, safe_name)
                if _row is not None else None
            )
            if existing is None and sidecar_disc is None:
                brought_here.append(safe_name)
            if (existing is not None and sidecar_disc is None
                    and not _is_this_file(existing, dest_path)):
                # The database calls it the same ROM, and it is not the same FILE:
                # another spelling of the name, or the copy in the other folder. So
                # it is not a replacement - the original stays and this lands beside
                # it, and the scan folds both into the one row that is already
                # charged. A second copy that counts against nothing, repeatable
                # with every spelling. Refused for everybody: even an administrator
                # making one leaves two files for one row.
                rejected.append({
                    "filename": safe_name,
                    "threat": None,
                    "action": "already_here",
                })
                continue
            if dest_path.exists() or existing is not None:
                # A subchannel file has no row of its own and never will, so asking
                # the database about its name can only ever answer "nobody's". It is
                # not nobody's: it belongs to the disc it is named after, the same
                # disc that let it through the gate two dozen lines up. So the
                # question about a .sbi is a question about that disc's owner, which
                # keeps replacing one exactly as hard as replacing the disc itself.
                if existing is None and sidecar_disc is not None and _row is not None:
                    existing = await rom_handler.get_by_fs_name(
                        _row.id, sidecar_disc.name)
                if not _may_replace(request, existing):
                    rejected.append({
                        "filename": safe_name,
                        "threat": None,
                        "action": "already_here",
                    })
                    continue
                # And give back what this file already costs the account, because it
                # is about to stop existing.
                #
                # The library upload has done this since `room_left = quota - used +
                # replacing`, and for the reason it states there: an account whose
                # allowance is filled by the very file it is swapping is the
                # ordinary reason to send the same name twice. This route counted
                # the replacement on top of the original, so a bad dump could never
                # be swapped for a good one by anybody near their limit.
                #
                # Only the row for THIS file, and only if the bytes are already
                # charged to this account. A subchannel file is governed by its
                # DISC's row, so crediting that would hand back a whole disc's worth
                # of room for replacing 452 bytes.
                if (existing is not None
                        and getattr(existing, "fs_name", None) == safe_name
                        and getattr(existing, "published_by", None)
                        == getattr(user, "id", None)):
                    remaining += int(getattr(existing, "fs_size_bytes", 0) or 0)
                    reservation.give_back(int(getattr(existing, "fs_size_bytes", 0) or 0))
            # Into a .part, never straight onto the destination.
            #
            # `open(dest_path, "wb")` truncates on the first byte, and the length of
            # a streamed body is not known until it ends - so a replacement that
            # turns out not to fit was discovered with the old file already emptied,
            # and the branch below then unlinked what was left of it. An account
            # near its limit sending a better dump of a ROM it already has lost both
            # copies: the refusal destroyed the thing it refused to replace. Every
            # other failure caught here - a full volume, a name the filesystem will
            # not take, a browser that goes away - left the wreckage wearing the
            # name of something that used to work.
            #
            # Same shape and same reason as the library upload, which has done this
            # correctly since `_part_path` was written; this route never got it.
            part_path = dest_path.with_name(dest_path.name + ".part")
            try:
                written = 0
                with open(part_path, "wb") as fh:
                    while chunk := await upload.read(256 * 1024):
                        written += len(chunk)
                        # Not `if remaining and ...`. `remaining` is a byte count,
                        # and it was doubling as the flag saying a limit applies -
                        # so a file that consumed the budget exactly (allowed, the
                        # refusal being "greater than") left it at zero, which is
                        # falsy, and every later file in the same request was
                        # written with nothing checking it. `ceiling_for` never
                        # answers zero: it returns the install-wide ceiling when no
                        # account limit applies and raises when there is no room, so
                        # there is no "no limit" state for this to stand for.
                        if written > remaining:
                            # Stop where the limit is, and take the partial file with
                            # us. Leaving it would cost the disk exactly what the
                            # refusal was meant to save. The .part is all there is to
                            # take: whatever was already on the shelf under this name
                            # has not been touched.
                            fh.close()
                            part_path.unlink(missing_ok=True)
                            raise HTTPException(
                                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                                detail=(f"{safe_name} exceeds the space left for this "
                                        f"account ({remaining} bytes)."),
                            )
                        # And against the account's other uploads, which grow
                        # while this one runs: `remaining` was read when the
                        # request arrived.
                        if not await reservation.take(len(chunk)):
                            fh.close()
                            part_path.unlink(missing_ok=True)
                            raise HTTPException(
                                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                                detail=(f"{safe_name} does not fit beside this account's "
                                        f"other uploads."),
                            )
                        fh.write(chunk)
                # Refused rather than counted, because counting it would not hold:
                # the row that carries a charge is the one thing this file can never
                # have. Rejected like an unrecognised extension rather than ending
                # the whole request - the other files in it are still the right
                # thing to do, and one oversized .sbi is a mistake, not an attack on
                # the rest of the upload.
                if sidecar_disc is not None and written > _MAX_SUBCHANNEL_BYTES:
                    part_path.unlink(missing_ok=True)
                    reservation.give_back(written)
                    rejected.append({
                        "filename": safe_name,
                        "threat": None,
                        "action": "subchannel_too_large",
                    })
                    continue
                remaining -= written

                if scan_uploads:
                    try:
                        # The .part, before it takes the name. A threat never wears
                        # the name of a real ROM even for the moment between the
                        # write and the verdict.
                        res = await _clam.scan_file(str(part_path))
                        note_unscanned(res, "ROM upload", safe_name)
                        if res.get("status") == "FOUND":
                            threat = res.get("threat") or "unknown"
                            action_res = await _clam.quarantine_or_delete(
                                str(part_path), threat, triggered_by=actor
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
                            part_path.unlink(missing_ok=True)
                            reservation.give_back(written)
                            continue
                    except Exception:
                        logger.exception("ClamAV scan failed for %s; allowing upload", part_path)

                # Only here does the upload take the name, and this is the one
                # moment the file that was already there stops existing. Everything
                # above can fail without costing anybody a ROM.
                os.replace(part_path, dest_path)
                saved.append(safe_name)
                if sidecar_disc is None:
                    to_register.append(safe_name)
                logger.info("ROM uploaded: %s -> %s", safe_name, dest_dir)
            except HTTPException as refusal:
                part_path.unlink(missing_ok=True)
                reservation.give_back(written)
                # Our own refusal, already the right answer. Re-wrapping it as a 500
                # below would tell the caller the server broke rather than that they
                # ran out of room.
                #
                # What already landed is registered anyway. Ten files in one request
                # and a refusal on the ninth used to leave eight on the disk with no
                # scan behind them: no rows, so no owner, so nothing counted against
                # the quota that had just refused them.
                _schedule_registration(background_tasks, fs_slug, to_register, getattr(user, "id", None),
                                       new_names=brought_here, newer_than=newest_before,
                                       release=reservation.close)
                # RETURNED, not raised, and that is the whole of this fix.
                #
                # FastAPI attaches the BackgroundTasks object to the response it
                # builds from what the endpoint RETURNS. When the endpoint raises,
                # Starlette's exception handling builds a fresh JSONResponse with no
                # background at all, and the task scheduled one line above is
                # dropped - so the registration this branch exists for never ran,
                # on the one path it was written for.
                #
                # The test that was meant to hold this called `await tasks()` itself,
                # which is exactly what the server does not do here, so it stayed
                # green over a fix that did nothing. The framework's actual behaviour
                # is pinned in test_a_refusal_still_runs_its_background_work.py.
                return JSONResponse(
                    {"detail": refusal.detail},
                    status_code=refusal.status_code,
                    headers=getattr(refusal, "headers", None),
                )
            except Exception as exc:
                # The half-written .part goes; the file that was already on the
                # shelf under this name was never opened and stays as it was.
                part_path.unlink(missing_ok=True)
                reservation.give_back(written)
                # Both halves of what the refusal branch above learned, because the
                # files that landed before this failure are in exactly the state
                # that branch exists to prevent: on the disk, with no row, so owned
                # by nobody and counting against no quota. Registered, and RETURNED
                # rather than raised - FastAPI attaches background tasks only to a
                # response the endpoint returns, so raising here would schedule the
                # work and then throw it away.
                _schedule_registration(background_tasks, fs_slug, to_register,
                                       getattr(user, "id", None), new_names=brought_here, newer_than=newest_before,
                                       release=reservation.close)
                # The reason goes to the log under a reference. Its text is the
                # full path the file could not be written to, which is the
                # server's layout, and this route is an uploader's (1.0.34 audit,
                # #16); an administrator still gets it, to fix it.
                return JSONResponse(
                    {"detail": safe_detail(exc, request, what=f"Failed to save {safe_name}")},
                    status_code=500,
                )

        # Auto-trigger scan so freshly uploaded ROMs show up in the library without
        # requiring a manual Scan click, and then record who put them there.
        #
        # This used to skip its own scan whenever one was already running, on the
        # grounds that the scan in flight would pick the files up. That is true of
        # the ROWS and was never true of the OWNER, which nothing else was recording
        # - so an upload made during a scan, and in fact every upload, belonged to
        # nobody: it counted against no quota, and the account that made it could
        # not delete it, because that rule reads an owner. The coalescing helper the
        # downloader uses handles both cases: it shares one scan across a burst and
        # waits for one that is already under way, under the same scanner lock.
        _schedule_registration(background_tasks, fs_slug, to_register, getattr(user, "id", None),
                               new_names=brought_here, newer_than=newest_before,
                               release=reservation.close)

        return {
            "ok": True,
            "saved": saved,
            "rejected": rejected,
            "platform_slug": slug,
            "scan_triggered": bool(saved),
        }
    except BaseException:
        reservation.close()
        raise


# ── Scan ──────────────────────────────────────────────────────────────────────

@protected_route(router.post, "/scan", scopes=[Scopes.PLATFORMS_WRITE])
async def trigger_scan(request: Request, background_tasks: BackgroundTasks) -> dict:
    if _scanner._scan_lock.locked():
        raise HTTPException(status_code=409, detail="Scan already running")

    roms_path = await _get_roms_path()

    async def _run():
        async with _scanner._scan_lock:
            _scanner._scan_running = True
            try:
                await scan_roms_path(roms_path)
            finally:
                _scanner._scan_running = False

    background_tasks.add_task(_run)
    return {"ok": True, "message": "ROM scan started", "path": roms_path}


# The permissions the two accounts that put things in the library hold, which is
# exactly who the progress events go to (_SCAN_WATCHERS in the scanner). It was
# ROMS_READ, which every account holds, while the identical dict went out over
# the socket to administrators only - so an ordinary player was handed the
# filesystem position the socket was written to keep from them, got a progress
# bar no event would ever advance or clear, and a Stop button beside it that
# answered "Missing scopes".
#
# Wider than the scan and the stop below on purpose, and it is the only one of
# the three that is: an uploader cannot start a scan or stop one, but an upload
# starts one by itself and watching it is how they know their file arrived.
# ROMS_READ alone on the decorator, and the real question a few lines down.
#
# Who may watch a scan is "an account that puts things in the library, or an
# account that can run one", and `protected_route` cannot say that: it requires
# every scope it is given, so an OR has to be settled in the handler - the same
# shape as the ownership rules in handler/library/ownership.py.
#
# It used to declare LIBRARY_UPLOAD, which is a GAMES permission. Switching the
# Games chip off for an administrator revokes it and leaves every emulation
# permission alone, so Start and Stop went on working while the bar between them
# answered 403 - and the composable, which asks about the ROLE, went on drawing
# the bar and quietly swallowing the refusal.
@protected_route(router.get, "/scan/status", scopes=[Scopes.ROMS_READ])
async def scan_status(request: Request) -> dict:
    """Where the scan is, in one call.

    Progress arrives over the socket while a scan runs, but a client that opened
    the page halfway through has missed every event so far. This is how it
    catches up, and it is the same shape the events carry so a view can render
    either without a second code path.

    `running` still comes from the lock rather than from the progress state: the
    lock is what actually decides whether another scan may start, and a status
    that disagreed with it would be a status about nothing.
    """
    held = set(getattr(request.state, "scopes", ()) or ())
    if not held & {Scopes.LIBRARY_UPLOAD, Scopes.PLATFORMS_WRITE}:
        raise HTTPException(
            status_code=403,
            detail="Only an account that can add to the library, or run a scan, "
                   "may follow one.",
        )
    snapshot = _scanner.scan_progress()
    snapshot["running"] = _scanner._scan_lock.locked()
    return snapshot


@protected_route(router.post, "/scan/stop", scopes=[Scopes.PLATFORMS_WRITE])
async def stop_scan(request: Request) -> dict:
    """Ask the running scan to stop between files.

    Cooperative, so it takes effect at the next file rather than instantly, and
    the scan puts the library back exactly as it was before it started - a scan
    that did not finish makes no claim about what is missing.
    """
    asked = _scanner.request_scan_stop()
    if asked:
        logger.info("ROM scan stop requested")
    return {"stopping": asked}


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
    assert_unlocked(request, rom)

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
    # The padlock covers the whole window, not only its Save button.
    assert_unlocked(request, rom)
    from handler.notifications.recently_added import announce_rom
    sent = await announce_rom(rom_id, force=True)
    return {"ok": True, "sent": sent}


# ── Helper ────────────────────────────────────────────────────────────────────

async def _get_roms_path() -> str:
    from handler.filesystem.rom_paths import roms_library_path
    return roms_library_path()
