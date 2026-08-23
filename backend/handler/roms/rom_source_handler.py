"""ROM source framework - the engine behind the RomSourceSpec hookspec.

A ROM source plugin describes a remote catalogue of ROMs (archive.org, Myrient,
lolroms, a local directory, ...). This engine enumerates the loaded sources,
proxies their live paginated listings, marks entries the library already owns,
and - the reusable core - downloads a single ROM into roms/<fs_slug>/, then runs
the existing scan + scrape pipeline so the ROM becomes a first-class Rom row.

Unlike the library-catalogue engine, a ROM source owns no persistent shelf and
writes no bespoke tables: nothing is pre-synced, listings are fetched live, and
a downloaded ROM is an ordinary Rom (see the design doc). Auth is the plugin's
own concern - it returns ready-to-use request headers from
rom_source_resolve_download, and those never leave the backend or land in a log.
"""

from __future__ import annotations

import asyncio
import inspect
import itertools
import logging
from dataclasses import dataclass
import os
import re
import shutil
import time
from pathlib import Path
from typing import Any, Iterable

import httpx

from config import PLUGINS_PATH, ROMS_PATH, config_manager
from handler.database.rom_handler import rom_handler, rom_platform_handler
from handler.filesystem.rom_scanner import _ROM_EXTENSIONS, scan_roms_path
from handler.metadata.rom_platform_map import PLATFORM_MAP, slug_from_fs_slug
from plugins.manager import plugin_manager
from utils.async_utils import fire_task
from utils.http import loggable_error
from utils.net_guard import assert_fetch_allowed, make_request_guard

logger = logging.getLogger(__name__)

# Streaming write chunk and the coarse per-file size backstop. The plugin is
# responsible for resolving to a single ROM (never a whole multi-GB archive);
# this ceiling only stops a mis-resolved whole-platform archive from filling a
# disk, so it has to clear the largest single disc image in circulation. That is
# a dual-layer Blu-ray, not a DVD: the earlier 16 GiB ceiling was picked from a
# dual-layer DVD (~8.5 GB) and a packaged Xbox 360 title (~13 GB), which put
# every PS3 and Wii U disc above it - a PS3 rip runs past 40 GB - and rejected
# the lot. 64 GiB clears a full 50 GB disc with room to spare and still sits far
# below the platform-sized archives it is there to catch, which run to hundreds
# of GB. Settings > ROMs overrides it per install.
_CHUNK_WRITE = 256 * 1024
_DEFAULT_MAX_ROM_BYTES = 64 * 1024 ** 3

# Region tags parsed from a No-Intro filename, kept out of the displayed title.
_REGION_TAGS = {
    "usa": "USA", "us": "USA", "u": "USA",
    "europe": "Europe", "eu": "Europe", "e": "Europe",
    "japan": "Japan", "jp": "Japan", "jpn": "Japan", "j": "Japan",
    "world": "World", "w": "World",
    "korea": "Korea", "china": "China", "brazil": "Brazil",
    "australia": "Australia", "spain": "Spain", "france": "France",
    "germany": "Germany", "italy": "Italy",
}
_PAREN_TAG = re.compile(r"\s*\(([^()]*)\)")
_BAD_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')

_job_seq = itertools.count(1)
# Dedup guards. _in_flight keys a (source_id, entry_id) so a double click on one
# entry does not re-queue it; _dest_locks keys the destination (fs_slug, filename)
# so two different entries that resolve to the same file never write it at once
# (which would corrupt the ROM). Both are released in the download job's finally.
_in_flight: set[tuple[str, str]] = set()
_dest_locks: set[tuple[str, str]] = set()


@dataclass
class _RomJob:
    """One download, and enough about it to stop, resume or repeat it.

    These used to be bare tasks with nothing kept but a number, which is why
    there was no way to ask one to stop. The queue lives in memory only: a
    restart forgets it, exactly as it did before. What survives a restart is
    the .part file, and a retry picks that up rather than starting over.
    """

    id: int
    source_id: str
    entry_id: str
    url: str
    filename: str
    fs_slug: str
    headers: dict[str, str] | None
    cookies: dict[str, str] | None
    actor: str | None
    entry_key: tuple[str, str] | None
    dest_key: tuple[str, str]
    status: str = "queued"     # queued|downloading|paused|completed|failed|cancelled
    want: str | None = None    # "pause" or "cancel", read by the writing loop
    received: int = 0
    total: int = 0
    error: str | None = None
    task: asyncio.Task | None = None

    @property
    def terminal(self) -> bool:
        return self.status in ("completed", "failed", "cancelled")

    @property
    def part_path(self) -> Path:
        return Path(_roms_base()) / self.fs_slug / (self.filename + ".part")

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "source_id": self.source_id, "entry_id": self.entry_id,
            "filename": self.filename, "fs_slug": self.fs_slug,
            "status": self.status, "received": self.received, "total": self.total,
            "percent": round(self.received / self.total * 100, 1) if self.total else -1,
            "error": self.error,
        }


# Live and recently finished jobs, keyed by the id the UI already knows from the
# progress events. A paused job keeps its destination lock: the file is half
# written and nothing else may claim that name.
_jobs: dict[int, _RomJob] = {}
_KEEP_FINISHED = 200   # finished jobs remembered, so the list cannot grow forever

# Post-download scans are coalesced: a burst of downloads shares one full ROM
# scan instead of each running its own (see _coalesced_scan_after_write).
_scan_cv = asyncio.Condition()
_writes_seen = 0      # bumped as each downloaded file lands, under _scan_cv
_writes_covered = 0   # highest _writes_seen a completed scan has included
_scan_busy = False


# ── Source enumeration ─────────────────────────────────────────────────────────

def _has(inst: Any, attr: str) -> bool:
    return callable(getattr(inst, attr, None))


def _source_instance_for(source_id: str) -> Any | None:
    """The loaded plugin instance whose rom_source_id() equals source_id."""
    for inst in plugin_manager.get_plugin_instances():
        fn = getattr(inst, "rom_source_id", None)
        if not callable(fn):
            continue
        try:
            if fn() == source_id:
                return inst
        except Exception:
            continue
    return None


def _source_meta(inst: Any) -> dict[str, Any]:
    fn = getattr(inst, "rom_source_meta", None)
    if not callable(fn):
        return {}
    try:
        return fn() or {}
    except Exception:
        logger.warning("rom_source_meta raised for a source; treating as empty", exc_info=True)
        return {}


def _source_icon(plugin_id: str | None, meta: dict[str, Any]) -> str | None:
    """URL of the icon the source's own plugin ships, or None.

    Preference order: an explicit `icon_asset` from rom_source_meta, then the
    plugin's logo.png/logo.svg (the same file Settings shows). A theme renders
    this next to the source instead of inventing a generic glyph.
    """
    if not plugin_id:
        return None
    asset = str(meta.get("icon_asset") or "").strip().lstrip("/")
    if asset and ".." not in asset:
        return f"/api/plugins/{plugin_id}/assets/{asset}"
    root = Path(PLUGINS_PATH) / plugin_id
    try:
        if (root / "logo.png").exists() or (root / "logo.svg").exists():
            return f"/api/plugins/{plugin_id}/logo"
    except OSError:
        pass
    return None


def list_rom_sources() -> list[dict[str, Any]]:
    """Every loaded ROM source, with presentation and configured/auth state.

    Enumerated per instance (like the catalogue engine) so each source keeps its
    identity and owning plugin; a blanket hook call would lose the pairing.
    """
    out: list[dict[str, Any]] = []
    for inst in plugin_manager.get_plugin_instances():
        id_fn = getattr(inst, "rom_source_id", None)
        if not callable(id_fn):
            continue
        try:
            sid = id_fn()
        except Exception:
            continue
        if not sid:
            continue
        try:
            name = inst.rom_source_name() if _has(inst, "rom_source_name") else str(sid)
        except Exception:
            name = str(sid)
        meta = _source_meta(inst)
        plugin_id = plugin_manager.id_for_instance(inst)
        tile_asset = meta.get("tile_asset")
        tile_bg = (
            f"/api/plugins/{plugin_id}/assets/{tile_asset}"
            if tile_asset and plugin_id else None
        )
        manifest = plugin_manager.manifest_for(plugin_id) if plugin_id else None
        out.append({
            "id": str(sid),
            "name": str(name),
            "plugin_id": plugin_id,
            # The owning plugin as the user knows it (manifest name + its own
            # icon), so a theme heads the source with the feature's identity and
            # keeps the source name as the "which catalogue" detail.
            "plugin_name": str((manifest or {}).get("name") or "").strip() or None,
            "icon": _source_icon(plugin_id, meta),
            "tile_bg": tile_bg,
            "requires_auth": bool(meta.get("requires_auth", False)),
            "configured": bool(meta.get("configured", True)),
        })
    return out


def _require_source(source_id: str) -> Any:
    inst = _source_instance_for(source_id)
    if inst is None:
        raise LookupError(f"No loaded plugin offers the ROM source {source_id!r}")
    meta = _source_meta(inst)
    if meta.get("requires_auth") and not meta.get("configured", True):
        raise PermissionError(f"ROM source {source_id!r} is not configured")
    return inst


# ── Platforms ──────────────────────────────────────────────────────────────────

async def get_platforms(source_id: str) -> list[dict[str, Any]]:
    """Platforms a source offers, filtered to slugs GD's scanner recognizes.

    An unmapped slug is dropped and logged, never guessed into a random folder.
    """
    inst = _require_source(source_id)
    fn = getattr(inst, "rom_source_platforms", None)
    if not callable(fn):
        return []
    raw = await asyncio.to_thread(fn) or []
    out: list[dict[str, Any]] = []
    for p in raw:
        fs_slug = str((p or {}).get("fs_slug") or "").strip()
        if not fs_slug:
            continue
        info = PLATFORM_MAP.get(fs_slug)
        if info is None:
            logger.warning(
                "ROM source %s offers unmapped platform %r - hidden", source_id, fs_slug
            )
            continue
        out.append({
            "fs_slug": fs_slug,
            "display": str(p.get("display") or info.get("name") or fs_slug),
            "count": p.get("count"),
        })
    return out


# ── Listing + owned-state ──────────────────────────────────────────────────────

async def refresh_source(source_id: str, scope: str = "listings") -> dict[str, Any]:
    """Ask a source to forget what it has cached, so the next listing refetches.

    A source that reads a remote catalogue caches its listings, and a listing
    that failed - or came back empty because the archive was having a bad
    afternoon - keeps being served from that cache until it expires. This is
    the way to say "try again, properly" from the screen showing the empty
    list.

    The hook is optional, so a source that has nothing to forget reports that
    plainly rather than failing.
    """
    inst = _require_source(source_id)
    fn = getattr(inst, "rom_source_refresh", None)
    if not callable(fn):
        return {"refreshed": False, "reason": "This source does not cache anything"}
    try:
        # Blocking work (files, locks) belongs off the event loop, like the
        # listing and resolve hooks next door.
        done = await asyncio.to_thread(fn, scope)
    except TypeError:
        # An older signature that predates the scope argument.
        done = await asyncio.to_thread(fn)
    logger.info("ROM source %s refreshed (scope=%s, dropped=%s)", source_id, scope, bool(done))
    return {"refreshed": bool(done)}


def _region_from_name(filename: str) -> str | None:
    """Best-effort region parsed from a No-Intro filename's parenthesised tags."""
    for tag in _PAREN_TAG.findall(filename or ""):
        for part in re.split(r"[,/]", tag):
            key = part.strip().lower()
            if key in _REGION_TAGS:
                return _REGION_TAGS[key]
    return None


def _is_region_part(part: str) -> bool:
    """Whether one comma-separated part of a tag is nothing but region names."""
    bits = [b.strip().lower() for b in part.split("/") if b.strip()]
    return bool(bits) and all(b in _REGION_TAGS for b in bits)


def _strip_region_from_title(title: str) -> str:
    """Drop region tags from a display title, keep the name and everything else.

    Only the region parts of a tag go, not the whole parenthesis: an arcade set
    is described as "DoDonPachi II - Bee Storm (World, ver. 102)", where the
    region belongs in its own column but the version is the only thing telling
    that row apart from its siblings. Dropping the lot collapsed a dozen sets
    into a dozen identical rows.
    """
    def _keep(m: re.Match) -> str:
        rest = [p.strip() for p in m.group(1).split(",")
                if p.strip() and not _is_region_part(p)]
        return f" ({', '.join(rest)})" if rest else ""
    cleaned = _PAREN_TAG.sub(_keep, title or "")
    return re.sub(r"\s{2,}", " ", cleaned).strip() or (title or "")


async def _owned_lookup(fs_slug: str, items: list[dict[str, Any]]) -> dict[str, set[str]]:
    empty = {"crc": set(), "md5": set(), "sha1": set(), "fs_name": set()}
    platform = await rom_platform_handler.get_by_slug(slug_from_fs_slug(fs_slug))
    if platform is None:
        return empty
    return await rom_handler.owned_signatures(
        platform.id,
        crcs={str(it.get("crc")) for it in items if it.get("crc")},
        md5s={str(it.get("md5")) for it in items if it.get("md5")},
        sha1s={str(it.get("sha1")) for it in items if it.get("sha1")},
        fs_names={str(it.get("filename")) for it in items if it.get("filename")},
    )


def _accepted_filters(fn: Any, offered: dict[str, Any]) -> dict[str, Any]:
    """The optional filters a plugin's rom_source_list actually declares.

    The hook grew filters after its first release, and it will grow more. Each
    one is passed by keyword only to a plugin that names it, so an older plugin
    keeps being called exactly as it was written instead of erroring on an
    argument it never heard of.
    """
    try:
        params = inspect.signature(fn).parameters
    except (TypeError, ValueError):
        return {}
    if any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values()):
        return dict(offered)
    return {k: v for k, v in offered.items() if k in params}


async def list_roms(
    source_id: str,
    fs_slug: str,
    page: int,
    page_size: int,
    query: str | None,
    region: str | None,
    sort: str | None,
    collection: str | None = None,
    fmt: str | None = None,
    kind: str | None = None,
) -> dict[str, Any]:
    """Live, paginated ROM listing for one platform, with owned-state stamped on.

    Titles have their region tag stripped for display (region rides its own
    field); owned is set when a hash or, failing that, the filename already
    exists in this platform. A source that merges several catalogues stamps each
    entry with its `collection`, and `collection` filters the listing down to one;
    `fmt` narrows to one container and `kind` to one sort of release (a retail
    game, a prototype, a translation...).
    """
    inst = _require_source(source_id)
    if PLATFORM_MAP.get(fs_slug) is None:
        raise ValueError(f"Unknown platform {fs_slug!r}")
    fn = getattr(inst, "rom_source_list", None)
    if not callable(fn):
        return {"items": [], "total": 0, "page": page, "collections": [],
                "formats": [], "kinds": []}

    extra = _accepted_filters(fn, {"collection": collection, "fmt": fmt, "kind": kind})
    raw = await asyncio.to_thread(
        lambda: fn(fs_slug, page, page_size, query, region, sort, **extra)
    ) or {}
    items = list(raw.get("items") or [])
    total = int(raw.get("total") or 0)
    collections = [str(c) for c in (raw.get("collections") or []) if str(c or "").strip()]
    formats = [str(f).lower() for f in (raw.get("formats") or []) if str(f or "").strip()]
    kinds = [str(k).lower() for k in (raw.get("kinds") or []) if str(k or "").strip()]
    owned = await _owned_lookup(fs_slug, items)

    out_items: list[dict[str, Any]] = []
    for it in items:
        filename = str(it.get("filename") or "")
        crc = str(it.get("crc") or "").lower()
        md5 = str(it.get("md5") or "").lower()
        sha1 = str(it.get("sha1") or "").lower()
        is_owned = (
            (crc and crc in owned["crc"])
            or (md5 and md5 in owned["md5"])
            or (sha1 and sha1 in owned["sha1"])
            or (filename and filename in owned["fs_name"])
        )
        # The container the ROM arrives in. Derived here when the source does
        # not say, so the format filter works the same for every source.
        fmt = (
            str(it.get("format") or "").lower()
            or (filename.rsplit(".", 1)[-1].lower() if "." in filename else None)
            or None
        )
        # A source that names its rows is taken at its word; one that does not is
        # falling back to the filename, and there the container is already shown
        # in its own column, so it is dropped from the title.
        raw_title = str(it.get("title") or "")
        if not raw_title:
            raw_title = filename
            if fmt and raw_title.lower().endswith("." + fmt):
                raw_title = raw_title[: -(len(fmt) + 1)]
        out_items.append({
            "id": str(it.get("id")),
            "title": _strip_region_from_title(raw_title),
            "filename": filename,
            "region": it.get("region") or _region_from_name(filename),
            "size": it.get("size"),
            "collection": str(it.get("collection") or "") or None,
            "format": fmt,
            # What sort of release this is (retail, prototype, hack...). Only the
            # source can tell, since it comes from naming conventions.
            "kind": str(it.get("kind") or "").lower() or None,
            "owned": bool(is_owned),
        })
    return {
        "items": out_items, "total": total, "page": page,
        "collections": collections, "formats": formats, "kinds": kinds,
    }


# ── Preview (one row, on demand) ───────────────────────────────────────────────

_TAGS = re.compile(r"\s*[\(\[][^()\[\]]*[\)\]]")


def preview_phrase(title: str | None, filename: str | None) -> str:
    """The phrase a browsing row should be looked up by.

    Set names, regions, revisions and translation credits all live in brackets
    that no metadata provider indexes, so they go: "3x3 Eyes (Japan) [T-En by
    Atomizer_Zero]" is looked up as "3x3 Eyes".
    """
    base = (title or filename or "").strip()
    if not title and "." in base:
        base = base.rsplit(".", 1)[0]
    return _TAGS.sub("", base).strip(" -_") or base


async def preview_entry(
    fs_slug: str,
    *,
    title: str | None = None,
    filename: str | None = None,
    size: int | None = None,
    crc: str | None = None,
    md5: str | None = None,
    sha1: str | None = None,
) -> dict[str, Any]:
    """Cover and facts for ONE browsing row, fetched only when asked for.

    Deliberately not `scrape_rom`: that one downloads artwork onto the server
    for a ROM the library owns. Nothing here is written or persisted - this is a
    look at a game before deciding to download it, so it stays a pure read.

    ScreenScraper is asked first because it is the only provider that can
    identify a ROM rather than guess at a name: it takes the hashes when the
    entry has them, otherwise the filename and byte size, and only falls back to
    the name. IGDB answers when ScreenScraper does not.
    """
    from handler.config.config_handler import config_handler
    from handler.metadata import igdb_rom_handler, screenscraper_handler
    from handler.metadata.rom_platform_map import get_igdb_id, get_ss_id
    from utils.media_proxy import proxy_url

    phrase = preview_phrase(title, filename)
    out: dict[str, Any] = {"found": False, "query": phrase, "source": None}
    if not phrase:
        return out

    preset = (config_manager.get_section("rom_scrape_presets") or {}).get(fs_slug, {})
    ss_user = await config_handler.get("screenscraper_username") or ""
    ss_pass = await config_handler.get("screenscraper_password") or ""

    def _shape(meta: dict[str, Any], source: str, matched: str) -> dict[str, Any]:
        return {
            "found": True,
            "query": phrase,
            "source": source,
            "matched_by": matched,
            "name": meta.get("name"),
            "summary": meta.get("summary"),
            "developer": meta.get("developer"),
            "publisher": meta.get("publisher"),
            "genres": meta.get("genres") or [],
            "release_year": meta.get("release_year"),
            # A ScreenScraper media URL carries the account in its query string,
            # so it is wrapped before it can reach a browser.
            "cover_url": proxy_url(meta.get("cover_url")) or meta.get("cover_url"),
        }

    if ss_user and ss_pass:
        try:
            raw = await screenscraper_handler.search_game(
                phrase,
                get_ss_id(fs_slug),
                fs_name=filename or "",
                file_size=int(size or 0),
                crc=crc or "", md5=md5 or "", sha1=sha1 or "",
                username=ss_user, password=ss_pass,
                devid=await config_handler.get("screenscraper_devid") or "",
                devpassword=await config_handler.get("screenscraper_devpassword") or "",
            )
            if raw:
                meta = screenscraper_handler.extract_metadata(
                    raw,
                    cover_type=preset.get("cover_type", "box-2D"),
                    region=preset.get("region", "ss"),
                )
                return _shape(meta, "screenscraper",
                              "hash" if (crc or md5 or sha1) else "name")
        except Exception as e:
            logger.warning("preview: ScreenScraper failed for %r: %s", phrase, e)

    igdb_id = await config_handler.get("igdb_client_id") or ""
    igdb_secret = await config_handler.get("igdb_client_secret") or ""
    if igdb_id and igdb_secret:
        try:
            raw = await igdb_rom_handler.search_game(
                phrase, get_igdb_id(fs_slug),
                client_id=igdb_id, client_secret=igdb_secret,
            )
            if raw:
                return _shape(igdb_rom_handler.extract_metadata(raw), "igdb", "name")
        except Exception as e:
            # Never the exception itself: the IGDB token call passes client_id
            # and client_secret as query parameters, and httpx puts the whole
            # URL into the message of an HTTP error.
            logger.warning("preview: IGDB failed for %r: %s", phrase, loggable_error(e))

    return out


# ── Download (the reusable delivery primitive) ─────────────────────────────────

# Left unwritten on the volume a ROM lands on. The default compose puts the
# library and the database on one disk, so a download that fills it to the last
# byte does not merely fail itself, it takes MariaDB down with it. A gigabyte is
# enough for the database to keep writing while somebody clears space.
_DISK_HEADROOM_BYTES = 1024 ** 3


def assert_room_for(dest_dir: Path, need: int) -> None:
    """Refuse a download that would not fit, before a byte is written.

    Only possible when the source declares a length. One that does not still has
    the running size cap, which stops a runaway, just not a disk that was nearly
    full to begin with.
    """
    try:
        free = shutil.disk_usage(dest_dir).free
    except OSError:
        return          # cannot tell: carry on rather than refuse a good download
    if need + _DISK_HEADROOM_BYTES > free:
        raise ValueError(
            f"Not enough free space: this ROM needs {need / 1024 ** 3:.1f} GB "
            f"and only {free / 1024 ** 3:.1f} GB is free."
        )


def max_rom_bytes() -> int:
    """The per-file ceiling in force, honouring the Settings > ROMs override.

    Public because the settings endpoint shows the effective value: a screen
    that displayed a stale default while the download used something else would
    be worse than no screen at all.
    """
    try:
        cfg = config_manager.get_section("roms")
        val = int(cfg.get("max_rom_bytes") or 0)
        return val if val > 0 else _DEFAULT_MAX_ROM_BYTES
    except Exception:
        return _DEFAULT_MAX_ROM_BYTES


# How many ROM downloads may be in flight at once. The browser ships a
# select-all over a sixty-row page, and every selected entry used to get its own
# task immediately: sixty sockets against one host, sixty .part files growing in
# parallel, and sixty disk-space checks all asking the same instant whether
# there was room for one more four-gigabyte file - so all sixty passed and the
# volume filled. With a cap, each job asks about free space when its turn comes,
# by which time the ones before it have actually landed, and the question means
# something again.
_DEFAULT_MAX_PARALLEL_ROM_DOWNLOADS = 3
_download_gate: asyncio.Semaphore | None = None
_download_gate_limit = 0


def max_parallel_rom_downloads() -> int:
    """The concurrency cap in force, honouring the Settings > ROMs override."""
    try:
        cfg = config_manager.get_section("roms")
        val = int(cfg.get("max_parallel_downloads") or 0)
        return val if val > 0 else _DEFAULT_MAX_PARALLEL_ROM_DOWNLOADS
    except Exception:
        return _DEFAULT_MAX_PARALLEL_ROM_DOWNLOADS


def _gate() -> asyncio.Semaphore:
    """The shared slot counter, rebuilt if an admin changed the limit.

    Rebuilding while downloads hold permits on the previous one can briefly
    allow more than the new limit; the alternative is a limit that only takes
    effect after a restart. Queued jobs simply stay `queued`, which is a status
    the downloads panel already renders.
    """
    global _download_gate, _download_gate_limit
    limit = max_parallel_rom_downloads()
    if _download_gate is None or limit != _download_gate_limit:
        _download_gate = asyncio.Semaphore(limit)
        _download_gate_limit = limit
    return _download_gate


def _roms_base() -> str:
    try:
        cfg = config_manager.get_section("roms")
        return cfg.get("library_path") or ROMS_PATH
    except Exception:
        return ROMS_PATH


def _safe_rom_filename(raw: str) -> str:
    """A filesystem-safe basename for a downloaded ROM, or "" if unusable.

    Keeps No-Intro punctuation (spaces, parentheses) but strips path separators,
    control characters, and traversal; requires a recognized ROM extension.
    """
    name = Path(str(raw or "")).name.strip()
    if not name or name in (".", "..") or name.startswith(("/", "\\")):
        return ""
    name = _BAD_FILENAME_CHARS.sub("_", name)
    ext = Path(name).suffix.lstrip(".").lower()
    if ext not in _ROM_EXTENSIONS:
        return ""
    return name


def _resolve_entry(inst: Any, entry_id: str) -> dict[str, Any] | None:
    """Resolve one entry to {url, filename, fs_slug, headers} or None if invalid."""
    fn = getattr(inst, "rom_source_resolve_download", None)
    if not callable(fn):
        return None
    try:
        spec = fn(entry_id) or {}
    except Exception:
        logger.warning("resolve_download raised for entry %r", entry_id, exc_info=True)
        return None
    # A plugin that returns the URL bare instead of the documented dict is a
    # plausible mistake, and reading .get() off a string would raise OUTSIDE the
    # guard above - taking the rest of the batch with it and stranding this
    # entry's in-flight reservation. Treat any non-dict as "could not resolve".
    if not isinstance(spec, dict):
        logger.warning(
            "resolve_download returned %s, not a dict, for entry %r",
            type(spec).__name__, entry_id,
        )
        return None

    url = str(spec.get("url") or "").strip()
    filename = _safe_rom_filename(spec.get("filename") or "")
    fs_slug = str(spec.get("fs_slug") or "").strip()
    headers = dict(spec["headers"]) if isinstance(spec.get("headers"), dict) else {}
    cookies = dict(spec["cookies"]) if isinstance(spec.get("cookies"), dict) else {}
    # Fold any raw Cookie header into the jar. httpx drops a Cookie *header* on
    # every redirect hop (archive.org member URLs redirect to a datanode), but it
    # re-applies its cookie jar - so cookie auth must ride `cookies`, not headers.
    for hk in list(headers):
        if hk.lower() == "cookie":
            for part in str(headers.pop(hk)).split(";"):
                if "=" in part:
                    ck, cv = part.split("=", 1)
                    if ck.strip():
                        cookies[ck.strip()] = cv.strip()

    if not url:
        logger.warning("resolve_download for %r returned no URL", entry_id)
        return None
    if not filename:
        logger.warning("resolve_download for %r returned an unusable filename", entry_id)
        return None
    if PLATFORM_MAP.get(fs_slug) is None:
        logger.warning("resolve_download for %r returned unmapped slug %r", entry_id, fs_slug)
        return None
    try:
        # Rejects non-http(s) schemes and SSRF targets (localhost / metadata /
        # link-local / private). ROM sources are public services, so - unlike a
        # self-hoster's NAS upload - LAN is off.
        assert_fetch_allowed(url, allow_private_lan=False)
    except Exception as e:
        logger.warning("resolve_download for %r returned a blocked URL: %s", entry_id, e)
        return None
    return {
        "url": url, "filename": filename, "fs_slug": fs_slug,
        "headers": headers or None, "cookies": cookies or None,
    }


async def queue_downloads(
    source_id: str, entry_ids: Iterable[str], actor: str | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Resolve and queue single-ROM downloads. Returns the accepted jobs.

    Each entry is resolved through the plugin (off the event loop), validated
    (URL, filename, slug, SSRF), de-duplicated against in-flight jobs, then run
    as a background download -> scan -> scrape. An entry whose destination file
    already exists is skipped unless `force` is set, so a re-download never
    silently clobbers a ROM the user already has (design doc 8.5).
    """
    inst = _require_source(source_id)
    if not _has(inst, "rom_source_resolve_download"):
        raise LookupError(f"ROM source {source_id!r} cannot resolve downloads")

    queued: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for eid in entry_ids:
        entry_id = str(eid)
        ekey = (source_id, entry_id)
        # Reserve the entry key BEFORE the resolve await, so a double click that
        # arrives while the first resolve is still in flight is rejected here
        # rather than racing to a second download.
        if ekey in _in_flight:
            skipped.append({"entry_id": entry_id, "reason": "already downloading"})
            continue
        _in_flight.add(ekey)
        # The reservation is taken from here until the job owns it, so EVERY
        # path out of this block has to give it back. A stranded key reports the
        # entry as "already downloading" for the life of the process - and
        # force=True does not bypass the check above, so not even a deliberate
        # retry can clear it. An escaping exception would also drop every entry
        # queued behind this one without a word, so the whole body is guarded,
        # not just the resolve: `.exists()` re-raises on EACCES, ESTALE and
        # ENAMETOOLONG, all reachable on a bind-mounted ROM directory.
        try:
            spec = await asyncio.to_thread(_resolve_entry, inst, entry_id)
            if spec is None:
                _in_flight.discard(ekey)
                skipped.append({"entry_id": entry_id, "reason": "could not resolve"})
                continue
            # Never overwrite an existing ROM unless the caller explicitly forces
            # it: a stale listing (owned-state computed before the file landed)
            # or a duplicate click could otherwise os.replace a good,
            # hand-verified dump.
            if not force and (Path(_roms_base()) / spec["fs_slug"] / spec["filename"]).exists():
                _in_flight.discard(ekey)
                skipped.append({"entry_id": entry_id, "reason": "already downloaded"})
                continue
            dkey = (spec["fs_slug"], spec["filename"])
            if dkey in _dest_locks:
                _in_flight.discard(ekey)
                skipped.append({"entry_id": entry_id, "reason": "file already downloading"})
                continue
            _dest_locks.add(dkey)
        except Exception as exc:
            _in_flight.discard(ekey)
            logger.warning(
                "could not queue entry %d of this batch: %s", len(queued) + len(skipped) + 1,
                loggable_error(exc),
            )
            skipped.append({"entry_id": entry_id, "reason": "could not resolve"})
            continue
        job = _RomJob(
            id=next(_job_seq), source_id=source_id, entry_id=entry_id,
            url=spec["url"], filename=spec["filename"], fs_slug=spec["fs_slug"],
            headers=spec["headers"], cookies=spec["cookies"], actor=actor,
            entry_key=ekey, dest_key=dkey,
        )
        job_id = job.id
        _jobs[job_id] = job
        job.task = asyncio.create_task(_rom_download_job(job))
        queued.append({
            "id": job_id,
            "entry_id": entry_id,
            "filename": spec["filename"],
            "fs_slug": spec["fs_slug"],
        })
    return {"queued": queued, "skipped": skipped}


async def import_rom(
    url: str, fs_slug: str, filename: str, actor: str | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """General primitive: download one ROM by direct URL into roms/<fs_slug>/.

    For plugins that hold a URL rather than a full source adapter. This is a
    public fetch (SSRF-guarded, no source credentials); an authenticated source
    downloads through queue_downloads, where its headers stay server-side.
    Raises ValueError on bad input (the caller maps it to a 400). An existing
    destination file is left untouched unless `force` is set.
    """
    safe_name = _safe_rom_filename(filename)
    if not safe_name:
        raise ValueError("Unusable or non-ROM filename")
    if PLATFORM_MAP.get(fs_slug) is None:
        raise ValueError(f"Unknown platform {fs_slug!r}")
    url = str(url or "").strip()
    if not url:
        raise ValueError("Missing URL")
    # Raises UnsafeURLError (a ValueError) on a non-http(s) or SSRF target.
    assert_fetch_allowed(url, allow_private_lan=False)

    if not force and (Path(_roms_base()) / fs_slug / safe_name).exists():
        return {"queued": False, "reason": "already downloaded", "filename": safe_name}

    dkey = (fs_slug, safe_name)
    # No await between this check and the add, so the guard is race-free here.
    if dkey in _dest_locks:
        return {"queued": False, "reason": "already downloading", "filename": safe_name}
    _dest_locks.add(dkey)
    job = _RomJob(
        id=next(_job_seq), source_id="import", entry_id=safe_name, url=url,
        filename=safe_name, fs_slug=fs_slug, headers=None, cookies=None,
        actor=actor, entry_key=None, dest_key=dkey,
    )
    _jobs[job.id] = job
    job.task = asyncio.create_task(_rom_download_job(job))
    return {"queued": True, "id": job.id, "filename": safe_name, "fs_slug": fs_slug}


def _failed_host(e: Exception, job: _RomJob) -> str:
    """The host that actually refused, for the log. Host only - never the path.

    archive.org answers a download with a redirect to one of hundreds of data
    nodes, so the address that failed is usually not the one that was asked
    for, and the difference is the whole diagnosis: the archive being down
    looks nothing like one node being unreachable. httpx hangs the request on
    its transport errors and the response on status errors, so both are tried.
    """
    for owner in (getattr(e, "response", None), getattr(e, "request", None)):
        host = getattr(getattr(owner, "url", None), "host", None)
        if host:
            return str(host)
    from urllib.parse import urlparse
    return urlparse(job.url).hostname or "?"


def _safe_error(e: Exception) -> str:
    """A user-facing error that never echoes the URL or auth headers back."""
    if isinstance(e, httpx.HTTPStatusError):
        return f"Source returned HTTP {e.response.status_code}."
    if isinstance(e, ValueError):
        return str(e)[:200] or "Download failed."
    if isinstance(e, (httpx.ConnectError, httpx.ConnectTimeout)):
        return "Could not reach the source."
    if isinstance(e, httpx.TimeoutException):
        return "The source timed out."
    return "Download failed."


def _release_job_locks(job: _RomJob) -> None:
    """Give back the entry and destination claims, unless the job is paused.

    A paused job still owns its half-written file, so it keeps both until it is
    resumed, cancelled or thrown away. Mirrors the tail of _run_rom_download.
    """
    if job.status != "paused":
        if job.entry_key is not None:
            _in_flight.discard(job.entry_key)
        _dest_locks.discard(job.dest_key)


async def _rom_download_job(job: _RomJob, resume_from: int = 0) -> None:
    """Wait for a free download slot, then transfer.

    A job waiting here stays `queued`, which is a status the downloads panel
    already renders, so a select-all over sixty entries now reads as a queue
    rather than sixty simultaneous transfers.
    """
    from handler.socket_handler import sio

    gate = _gate()
    try:
        await gate.acquire()
    except asyncio.CancelledError:
        # Stopped before it ever held a slot. Nothing was opened and nothing
        # written, but the job still has to leave "queued" and hand back its
        # claims, or the panel keeps showing a queued download with no task
        # behind it and its destination stays reserved forever. Settled without
        # awaiting: this task is already being cancelled.
        job.status = "paused" if job.want == "pause" else "cancelled"
        job.want = None
        job.task = None
        _release_job_locks(job)
        fire_task(sio.emit("romsource:download_state", job.as_dict()))
        raise
    landed = False
    try:
        if job.want in ("pause", "cancel"):
            # The request arrived while this was queued: honour it without
            # opening a connection at all.
            await _settle_stopped(job, job.part_path)
            job.task = None
            _release_job_locks(job)
            return
        landed = await _run_rom_download(job, resume_from)
    finally:
        gate.release()

    # Registering the file walks the whole ROM tree and the scrape is a network
    # call to ScreenScraper. Both used to run inside _run_rom_download, which
    # means they ran while this job still held one of the three download slots
    # - and because the scan coalesces, every other finishing job waited on
    # _scan_cv holding *its* slot too, so all three could sit idle behind a
    # single scan. The slot goes back first; then the file is registered.
    if landed:
        await _register_after_download(job)


async def _register_after_download(job: _RomJob) -> None:
    """Scan and scrape the file that just landed, with the slot already free.

    The completion event is emitted afterwards because it carries the rom_id
    the browser needs to open the game's page; announcing first would hand it
    a null.
    """
    from handler.socket_handler import sio

    rom_id = await _register_and_scrape(job.fs_slug, job.filename)
    await sio.emit("romsource:download_complete", {
        "id": job.id,
        "source_id": job.source_id,
        "entry_id": job.entry_id,
        "fs_slug": job.fs_slug,
        "filename": job.filename,
        "rom_id": rom_id,
    })


async def _run_rom_download(job: _RomJob, resume_from: int = 0) -> bool:
    """Transfer the bytes. True when a file landed and needs registering."""
    from handler.socket_handler import sio

    dest_dir = Path(_roms_base()) / job.fs_slug
    dest_path = dest_dir / job.filename
    part_path = dest_dir / (job.filename + ".part")
    max_bytes = max_rom_bytes()
    size = resume_from
    started = time.monotonic()
    last_emit = 0.0
    job.status = "downloading"
    job.want = None
    job.error = None
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
        # Scope credential cookies to the URL's registrable domain (with a leading
        # dot) so a redirect to another host - an open redirect, a compromised hop,
        # a future source resolving off-site - never replays the source's session
        # cookies elsewhere. archive.org's own datanode redirect (ia*.archive.org)
        # still matches ".archive.org"; net_guard only blocks private targets, not
        # cross-domain public ones, so this is the layer that keeps the cookie home.
        cookie_jar: Any = None
        if job.cookies:
            from urllib.parse import urlparse
            host = (urlparse(job.url).hostname or "").lower()
            parts = [p for p in host.split(".") if p]
            # Widen to the parent domain ONLY when the URL already sits on a
            # two-label apex, which is the archive.org case the redirect needs
            # (archive.org -> ia902.us.archive.org). "Last two labels" is not a
            # registrable domain: on a shared apex like s3.amazonaws.com or
            # github.io it would name the whole estate, and a redirect to a
            # neighbouring tenant would be handed this source's session. A host
            # that is already a subdomain keeps its cookie to itself.
            if len(parts) == 2:
                domain = "." + host
            else:
                domain = host
            cookie_jar = httpx.Cookies()
            for _ck, _cv in job.cookies.items():
                cookie_jar.set(_ck, _cv, domain=domain)
        req_headers = dict(job.headers or {})
        if resume_from:
            req_headers["Range"] = f"bytes={resume_from}-"
        timeout = httpx.Timeout(30.0, read=600.0)
        async with httpx.AsyncClient(
            follow_redirects=True,
            timeout=timeout,
            headers=req_headers or None,
            cookies=cookie_jar,
            event_hooks={"request": [make_request_guard(allow_private_lan=False)]},
        ) as client:
            async with client.stream("GET", job.url) as resp:
                resp.raise_for_status()
                # A source that cannot resume answers 200 with the whole file
                # instead of 206 with the tail. Appending that to what we already
                # have would produce a file of the right length made of the wrong
                # bytes, so the partial one is dropped and this starts over.
                resuming = resume_from > 0 and resp.status_code == 206
                if resume_from and not resuming:
                    logger.info(
                        "ROM download #%d: source ignored Range, starting over", job.id)
                    size = 0
                total = int(resp.headers.get("content-length") or 0)
                if resuming and total:
                    total += resume_from
                if total and total > max_bytes:
                    raise ValueError("ROM exceeds the maximum allowed size.")
                if total:
                    assert_room_for(dest_dir, total - size)
                job.total = total
                with open(part_path, "ab" if resuming else "wb") as fh:
                    async for chunk in resp.aiter_bytes(_CHUNK_WRITE):
                        if job.want:
                            break
                        fh.write(chunk)
                        size += len(chunk)
                        job.received = size
                        if size > max_bytes:
                            raise ValueError("ROM exceeds the maximum allowed size.")
                        now = time.monotonic()
                        if now - last_emit >= 1.0:
                            last_emit = now
                            elapsed = max(now - started, 0.001)
                            await sio.emit("romsource:download_progress", {
                                "id": job.id,
                                "source_id": job.source_id,
                                "entry_id": job.entry_id,
                                "fs_slug": job.fs_slug,
                                "filename": job.filename,
                                "percent": round(size / total * 100, 1) if total else -1,
                                "received": size,
                                "total": total,
                                "speed": int((size - resume_from) / elapsed),
                            })
        if job.want:
            await _settle_stopped(job, part_path)
            return
        os.replace(part_path, dest_path)

        job.status = "completed"
        job.received = size
        logger.info(
            "ROM download #%d complete: %s/%s -> %s (%d B)%s",
            job.id, job.source_id, job.entry_id, job.filename, size,
            f", actor={job.actor}" if job.actor else "",
        )
        # The scan and the scrape happen after the caller hands back its
        # download slot; see _rom_download_job.
        return True
    except asyncio.CancelledError:
        # Only reachable when a stop was asked for and the connection had gone
        # quiet enough that the flag between chunks was never read.
        await _settle_stopped(job, part_path, forced=True)
        raise
    except Exception as e:
        # Keep what arrived when the failure is one a retry could get past.
        # This used to unlink unconditionally, which made retry_job's
        # `start_at = part_path.stat().st_size` dead code: a forty gigabyte
        # transfer that died at thirty-nine started again from zero. A size cap
        # or a permanent refusal is different - retrying those gets the same
        # answer, and the bytes are of no use to anybody.
        wznawialne = isinstance(e, (httpx.TimeoutException, httpx.TransportError))
        if isinstance(e, httpx.HTTPStatusError):
            wznawialne = e.response.status_code in (408, 429, 500, 502, 503, 504)
        if not wznawialne:
            try:
                part_path.unlink(missing_ok=True)
            except Exception:
                pass
        job.status = "failed"
        job.error = _safe_error(e)
        # Neither the exception message nor the entry id: httpx puts the full
        # request URL in the message of an HTTP error, and an entry id IS a URL
        # for a source that keys its listing on one (the shipping archive.org
        # adapter does), so printing it hands back exactly the query string the
        # redaction just removed.
        #
        # What does go in is the kind of exception and the host that refused,
        # because without them "Could not reach the source" is unanswerable:
        # it reads the same whether the network is down, the archive is
        # overloaded, or one data node out of hundreds is unreachable. A host
        # carries no path, no query and no credential.
        logger.warning(
            "ROM download #%d failed (%s -> %s/%s): %s [%s from %s]",
            job.id, job.source_id, job.fs_slug, job.filename, job.error,
            type(e).__name__, _failed_host(e, job),
        )
        await sio.emit("romsource:download_error", {
            "id": job.id,
            "source_id": job.source_id,
            "entry_id": job.entry_id,
            "fs_slug": job.fs_slug,
            "filename": job.filename,
            "error": job.error,
        })
    finally:
        job.task = None
        _release_job_locks(job)
        _prune_jobs()


def _prune_jobs() -> None:
    """Keep the finished ones from piling up for the life of the process.

    A record is a few hundred bytes, but somebody downloading a platform set
    would accumulate thousands of them and nothing ever removed one. Live and
    paused jobs are never touched; the oldest finished ones go first.
    """
    finished = [j for j in _jobs.values() if j.terminal]
    for job in sorted(finished, key=lambda j: j.id)[:max(0, len(finished) - _KEEP_FINISHED)]:
        _jobs.pop(job.id, None)


async def _settle_stopped(job: _RomJob, part_path: Path, forced: bool = False) -> None:
    """Finish a job that was asked to stop: paused keeps the file, cancel does not."""
    from handler.socket_handler import sio

    if job.want == "cancel":
        job.status = "cancelled"
        try:
            part_path.unlink(missing_ok=True)
        except Exception:
            pass
    else:
        job.status = "paused"
        try:
            job.received = part_path.stat().st_size
        except OSError:
            job.received = 0
    job.want = None
    logger.info(
        "ROM download #%d %s: %s/%s%s", job.id, job.status, job.fs_slug, job.filename,
        " (connection was idle)" if forced else "")
    await sio.emit("romsource:download_state", job.as_dict())


# ── Controlling a download in flight ───────────────────────────────────────────

def list_jobs() -> list[dict[str, Any]]:
    """Every job this process still knows about, newest first."""
    return [j.as_dict() for j in sorted(_jobs.values(), key=lambda j: -j.id)]


def get_job(job_id: int) -> _RomJob | None:
    return _jobs.get(job_id)


async def _request_stop(job: _RomJob, tryb: str) -> None:
    """Ask the writing loop to stop, and insist if it is not listening.

    The flag is read between chunks, which is immediate on a healthy transfer
    and never on a stalled one - a request that has gone quiet can sit in a
    600 s read timeout. So the flag comes first, politely, and the task is
    cancelled outright if the loop has not noticed within a few seconds.
    """
    job.want = tryb
    task = job.task
    if task is None or task.done():
        return
    try:
        await asyncio.wait_for(asyncio.shield(task), timeout=3.0)
    except asyncio.TimeoutError:
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):
            pass
    except Exception:
        pass


async def pause_job(job_id: int) -> bool:
    """Stop writing but keep what has been written. False if not pausable."""
    job = _jobs.get(job_id)
    if job is None:
        return False
    if job.status == "paused":
        return True
    if job.status not in ("downloading", "queued"):
        return False
    await _request_stop(job, "pause")
    return job.status == "paused"


async def resume_job(job_id: int) -> bool:
    """Carry on from the end of the .part file. False if not paused."""
    job = _jobs.get(job_id)
    if job is None or job.status != "paused":
        return False
    try:
        start_at = job.part_path.stat().st_size
    except OSError:
        start_at = 0
    job.task = asyncio.create_task(_rom_download_job(job, start_at))
    return True


async def cancel_or_forget_job(job_id: int) -> bool:
    """Stop and delete a live job, or drop a finished one from the list."""
    from handler.socket_handler import sio

    job = _jobs.get(job_id)
    if job is None:
        return False
    if job.status in ("downloading", "queued"):
        await _request_stop(job, "cancel")
        return True
    if job.status == "paused":
        # Nothing is running, so there is no loop to notice a flag: this is the
        # end of the job, and the half-written file goes with it.
        job.status = "cancelled"
        try:
            job.part_path.unlink(missing_ok=True)
        except Exception:
            pass
        if job.entry_key is not None:
            _in_flight.discard(job.entry_key)
        _dest_locks.discard(job.dest_key)
        await sio.emit("romsource:download_state", job.as_dict())
        return True
    # Finished, failed or already cancelled: forget it, and sweep up any
    # fragment a hard stop may have left behind.
    _jobs.pop(job_id, None)
    try:
        job.part_path.unlink(missing_ok=True)
    except Exception:
        pass
    return True


async def retry_job(job_id: int) -> bool:
    """Run a failed or cancelled job again. False if it is not repeatable."""
    from handler.socket_handler import sio

    job = _jobs.get(job_id)
    if job is None or job.status not in ("failed", "cancelled"):
        return False
    # The locks were given back when it stopped, so they have to be taken again -
    # and somebody else may have claimed the same destination in the meantime.
    if job.dest_key in _dest_locks:
        return False
    if job.entry_key is not None and job.entry_key in _in_flight:
        return False
    _dest_locks.add(job.dest_key)
    if job.entry_key is not None:
        _in_flight.add(job.entry_key)
    job.received = 0
    job.error = None
    job.status = "queued"
    try:
        start_at = job.part_path.stat().st_size
    except OSError:
        start_at = 0
    job.task = asyncio.create_task(_rom_download_job(job, start_at))
    await sio.emit("romsource:download_state", job.as_dict())
    return True


async def _coalesced_scan_after_write() -> None:
    """Run a full ROM scan that includes this just-written file, sharing one scan
    across a burst of concurrent downloads instead of running N of them.

    Each caller records its write; a single worker runs the scan (still under
    roms_router's lock, so it never overlaps a manual scan) and reports the
    highest write it covered. Callers whose write is covered return; the rest
    trigger the next scan. Without this, N bulk downloads would each run their
    own full-tree scan back-to-back.
    """
    global _writes_seen, _writes_covered, _scan_busy
    import endpoints.roms.roms_router as _rr

    async with _scan_cv:
        _writes_seen += 1
        mine = _writes_seen
        while _writes_covered < mine:
            if not _scan_busy:
                _scan_busy = True
                snapshot = _writes_seen
                _scan_cv.release()
                try:
                    async with _rr._scan_lock:
                        _rr._scan_running = True
                        try:
                            await scan_roms_path(_roms_base())
                        finally:
                            _rr._scan_running = False
                except Exception:
                    logger.warning("Coalesced ROM scan failed", exc_info=True)
                finally:
                    await _scan_cv.acquire()
                    _scan_busy = False
                    # Mark covered even on failure so waiters do not spin; an
                    # unregistered file is caught by the next scan or a manual one.
                    if snapshot > _writes_covered:
                        _writes_covered = snapshot
                    _scan_cv.notify_all()
            else:
                await _scan_cv.wait()


async def _register_and_scrape(fs_slug: str, filename: str) -> int | None:
    """Ensure the just-downloaded file is scanned in (coalesced with any
    concurrent downloads), then best-effort auto-scrape the new Rom."""
    await _coalesced_scan_after_write()

    platform = await rom_platform_handler.get_by_slug(slug_from_fs_slug(fs_slug))
    if platform is None:
        return None
    rom = await rom_handler.get_by_fs_name(platform.id, filename)
    if rom is None:
        logger.warning("Downloaded ROM %s not found after scan (platform %s)", filename, fs_slug)
        return None

    try:
        full = await rom_handler.get_with_platform(rom.id)
        from handler.metadata.rom_scrape_handler import scrape_rom as _scrape
        data = await _scrape(full, full.platform)
        if data:
            await rom_handler.update_metadata(rom.id, data)
            try:
                from handler.notifications.recently_added import schedule_rom
                schedule_rom(rom.id)
            except Exception:
                pass
    except Exception as e:
        logger.warning("Auto-scrape after ROM download failed for %s: %s", filename, e)
    return rom.id
