"""Dashboard aggregation - assembles the role-aware Dashboard payloads.

Two entry points:
  get_user_dashboard(user_id) - any authenticated user's own numbers
  get_admin_dashboard()       - server-wide operational overview (admin only)

Every section is defensive: a failing query yields a safe default for that
section instead of failing the whole dashboard, so a missing column or a
provider-less install still renders something useful.
"""

from __future__ import annotations

import asyncio
import os
import shutil
import time
from datetime import datetime, timedelta

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from decorators.database import begin_session
from handler.database.base_handler import DBBaseHandler
from handler.database.session import async_session_factory
from handler.auth import brute_force
from handler.email.email_stats import get_email_stats
from models.download_stat import DownloadStat
from models.game_request import GameRequest
from models.gog_game import GogGame
from models.library_file import LibraryFile
from models.library_game import LibraryGame
from handler.metadata.rom_platform_map import rom_cover_aspect as _rom_cover_aspect
from models.rom import Rom
from models.rom_play import RomPlay
from models.rom_platform import RomPlatform
from models.rom_save_state import RomSave, RomSaveState
from models.user import Role, User
from utils.ratings import rom_rating_agg
from utils.save_paths import screenshot_url as _screenshot_url

try:
    from config import BASE_PATH, DOWNLOADS_PATH, GAMES_PATH
except ImportError:  # pragma: no cover
    BASE_PATH = "/data"
    GAMES_PATH = "/data/games"
    DOWNLOADS_PATH = "/data/downloads"


# Static asset root (SPA build) - platform NAME wordmarks live under it, mirroring
# the digest mailer. fs_slug -> logo asset slug (same map as digest / platformMap.ts).
_STATIC_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "static")
_NAME_LOGO_SLUG = {
    "sfc": "snes", "snesna": "snes", "famicom": "nes", "megadrive": "genesis",
    "megacdjp": "megacd", "saturnjp": "saturn", "neogeocdjp": "neogeocd",
}


def _platform_logo(fs_slug: str | None) -> str | None:
    """Same-origin URL for a platform's white NAME wordmark, or None when the
    asset is absent (the UI then shows the plain platform name)."""
    if not fs_slug:
        return None
    slug = _NAME_LOGO_SLUG.get(fs_slug, fs_slug)
    if os.path.isfile(os.path.join(_STATIC_DIR, "platforms", "names-png", f"{slug}.png")):
        return f"/platforms/names-png/{slug}.png"
    return None


def _avg_speed_bps(total_bytes: int | None, total_ms: int | None) -> int:
    """Effective throughput in bytes/second from summed bytes and summed
    duration. 0 when no timed transfers are on record yet."""
    if total_ms and total_ms > 0:
        return int((total_bytes or 0) * 1000 / total_ms)
    return 0


def _disk_usage() -> list[dict]:
    """Free/total space for the data volumes, de-duplicated by mount so a
    single-disk install reports one row and a split-disk install (games/roms on
    another mount) reports each real volume once."""
    out: list[dict] = []
    seen: set = set()
    for label, path in (("games", GAMES_PATH), ("downloads", DOWNLOADS_PATH), ("data", BASE_PATH)):
        try:
            dev = os.stat(path).st_dev
            if dev in seen:
                continue
            seen.add(dev)
            u = shutil.disk_usage(path)
            out.append({
                "label": label, "path": path,
                "total_bytes": u.total, "free_bytes": u.free, "used_bytes": u.used,
            })
        except OSError:
            pass
    return out


def _resolve_range(days: int | None, start: str | None, end: str | None) -> tuple[datetime, datetime, str]:
    """Turn the dashboard window controls into a concrete [start, end) span and
    a bucket granularity. A custom `start`..`end` (YYYY-MM-DD, end inclusive)
    wins over `days`; `days<=1` means the last 24h. Buckets are hourly for spans
    up to 48h, daily otherwise, so the activity chart always reads well."""
    now = datetime.utcnow()
    if start and end:
        try:
            s0 = datetime.fromisoformat(start)
            e0 = datetime.fromisoformat(end)
            s = datetime(s0.year, s0.month, s0.day)
            e = datetime(e0.year, e0.month, e0.day) + timedelta(days=1)  # end inclusive
            if e <= s:
                e = s + timedelta(days=1)
            bucket = "hour" if (e - s).total_seconds() <= 48 * 3600 else "day"
            return s, e, bucket
        except ValueError:
            pass
    d = days or 30
    if d <= 1:
        return now - timedelta(hours=24), now, "hour"
    today = now.date()
    start_day = today - timedelta(days=d - 1)
    return datetime(start_day.year, start_day.month, start_day.day), now, "day"


async def _download_series(
    session: AsyncSession, start_dt: datetime, end_dt: datetime, bucket: str, user_id: int | None = None
) -> list[dict]:
    """Contiguous per-bucket download counts + bytes across [start_dt, end_dt),
    gap-filled with zeros (oldest first) so the sparkline always has one bar per
    bucket. `bucket` is 'hour' or 'day'. Scoped to a user when given."""
    if bucket == "hour":
        key_expr = func.date_format(DownloadStat.created_at, "%Y-%m-%d %H")
        cur = start_dt.replace(minute=0, second=0, microsecond=0)
        step = timedelta(hours=1)
        label_fmt = "%Hh"
        key_of = lambda dt: dt.strftime("%Y-%m-%d %H")  # noqa: E731
    else:
        key_expr = func.date(DownloadStat.created_at)
        cur = datetime(start_dt.year, start_dt.month, start_dt.day)
        step = timedelta(days=1)
        label_fmt = "%m-%d"
        key_of = lambda dt: dt.date().isoformat()  # noqa: E731

    q = (
        select(key_expr.label("k"), func.count(DownloadStat.id),
               func.coalesce(func.sum(DownloadStat.bytes_transferred), 0))
        .where(DownloadStat.created_at >= start_dt, DownloadStat.created_at < end_dt)
        .group_by(key_expr)
    )
    if user_id is not None:
        q = q.where(DownloadStat.user_id == user_id)
    rows = (await session.execute(q)).all()
    m: dict[str, dict] = {}
    for r in rows:
        k0 = r[0]
        k = k0.isoformat() if hasattr(k0, "isoformat") else str(k0)
        m[k] = {"count": int(r[1] or 0), "bytes": int(r[2] or 0)}

    out: list[dict] = []
    guard = 0
    while cur < end_dt and guard < 400:
        cell = m.get(key_of(cur), {"count": 0, "bytes": 0})
        out.append({"date": cur.strftime(label_fmt), "count": cell["count"], "bytes": cell["bytes"]})
        cur += step
        guard += 1
    return out


async def _download_totals(
    session: AsyncSession, start_dt: datetime, end_dt: datetime, user_id: int | None = None
) -> dict:
    """Count / distinct games / bytes / effective speed for downloads inside the
    window, server-wide or for one user."""
    base = [DownloadStat.created_at >= start_dt, DownloadStat.created_at < end_dt]
    if user_id is not None:
        base.append(DownloadStat.user_id == user_id)
    row = (await session.execute(
        select(func.count(DownloadStat.id),
               func.count(func.distinct(DownloadStat.library_game_id)),
               func.coalesce(func.sum(DownloadStat.bytes_transferred), 0)).where(*base)
    )).one()
    spd = (await session.execute(
        select(func.coalesce(func.sum(DownloadStat.bytes_transferred), 0),
               func.coalesce(func.sum(DownloadStat.duration_ms), 0))
        .where(*base, DownloadStat.duration_ms > 0)
    )).one()
    return {
        "count": int(row[0] or 0),
        "games": int(row[1] or 0),
        "bytes": int(row[2] or 0),
        "avg_speed_bps": _avg_speed_bps(spd[0], spd[1]),
    }


def _server_health() -> dict:
    """Host CPU / memory / uptime read straight from /proc (no psutil dependency).
    Every field degrades to a safe default if /proc is unavailable (non-Linux)."""
    out: dict = {"cpu_percent": None, "load1": None, "mem_used": 0, "mem_total": 0,
                 "uptime_seconds": 0, "cores": os.cpu_count() or 0}
    try:
        with open("/proc/loadavg") as f:
            out["load1"] = float(f.read().split()[0])
    except Exception:
        pass
    try:
        mem: dict[str, int] = {}
        with open("/proc/meminfo") as f:
            for line in f:
                k, _, rest = line.partition(":")
                try:
                    mem[k.strip()] = int(rest.strip().split()[0]) * 1024  # kB -> B
                except (ValueError, IndexError):
                    pass
        total = mem.get("MemTotal", 0)
        avail = mem.get("MemAvailable", mem.get("MemFree", 0))
        out["mem_total"] = total
        out["mem_used"] = max(0, total - avail)
    except Exception:
        pass
    try:
        with open("/proc/uptime") as f:
            out["uptime_seconds"] = int(float(f.read().split()[0]))
    except Exception:
        pass
    try:
        def _cpu_idle_total() -> tuple[int, int]:
            with open("/proc/stat") as f:
                vals = list(map(int, f.readline().split()[1:]))
            idle = vals[3] + (vals[4] if len(vals) > 4 else 0)  # idle + iowait
            return idle, sum(vals)
        i1, t1 = _cpu_idle_total()
        time.sleep(0.12)
        i2, t2 = _cpu_idle_total()
        dt = t2 - t1
        if dt > 0:
            out["cpu_percent"] = round(max(0.0, 100.0 * (1 - (i2 - i1) / dt)), 1)
    except Exception:
        pass
    return out


# Everything a ROM cover strip renders. Labelled because Rom.name and
# RomPlatform.name would otherwise collide in the row mapping.
_ROM_TILE_COLS = (
    Rom.id.label("rom_id"),
    Rom.name.label("rom_name"),
    Rom.fs_name_no_ext.label("fs_name_no_ext"),
    Rom.cover_path.label("cover_path"),
    Rom.cover_type.label("cover_type"),
    Rom.cover_aspect.label("cover_aspect"),
    Rom.ss_score.label("ss_score"),
    Rom.igdb_rating.label("igdb_rating"),
    Rom.lb_rating.label("lb_rating"),
    Rom.plugin_ratings.label("plugin_ratings"),
    # A theme's ROM tile draws more than a cover - the wheel logo, hero backdrop
    # and the year/genre/players chips. Same query, so the strips can render as
    # first-class tiles beside the recently-added rail instead of bare covers.
    Rom.wheel_path.label("wheel_path"),
    Rom.background_path.label("background_path"),
    Rom.steamgrid_path.label("steamgrid_path"),
    Rom.release_year.label("release_year"),
    Rom.genres.label("genres"),
    Rom.player_count.label("player_count"),
    RomPlatform.name.label("platform_name"),
    RomPlatform.slug.label("platform_slug"),
    RomPlatform.fs_slug.label("fs_slug"),
)


def _rom_tile(r) -> dict:
    """One cover-strip entry from a `_ROM_TILE_COLS` row.

    `rating` is the blended 0-5 score, NOT roms.rating - that column is the
    ScreenScraper note over 20, i.e. a 0-1 fraction that renders as "0.8".
    `platform_slug` is the routable slug (/emulation/<slug>/<id>), not fs_slug.
    """
    return {
        "rom_id":        r["rom_id"],
        "name":          r["rom_name"] or r["fs_name_no_ext"],
        "cover":         r["cover_path"],
        "platform":      r["platform_name"],
        "platform_slug": r["platform_slug"],
        # The asset key, for /platforms/names/<fs_slug>.svg wordmarks - the home
        # rails these strips sit beside draw them, and without it a new strip
        # would look foreign next to its neighbour.
        "platform_fs_slug": r["fs_slug"],
        "aspect":        _rom_cover_aspect(r["cover_type"], r["cover_aspect"], r["fs_slug"]),
        "rating":        rom_rating_agg(
            r["ss_score"], r["igdb_rating"], r["lb_rating"], r["plugin_ratings"]
        ),
        "wheel":         r["wheel_path"],
        "background":    r["background_path"] or r["steamgrid_path"],
        "release_year":  r["release_year"],
        "genres":        (r["genres"] or [])[:3],
        "player_count":  r["player_count"],
    }


async def _saves_for(session: AsyncSession, user_id: int, rom_ids: list[int]) -> dict[int, list[dict]]:
    """The savestates these ROMs hold, keyed by rom_id, newest first.

    One query for the whole strip rather than one per tile: the slot rail on a
    Continue-playing tile needs this the moment it renders, and a fetch per hover
    would be a request storm on a home page.

    Savestates only, deliberately. Every entry here becomes something the player
    can click to resume from, and a battery save cannot answer for that: it is
    the memory inside the cartridge, so it puts the save back in the machine but
    leaves the game at its title screen, waiting to be told to load. It travels
    with the ROM on every launch either way. A ROM whose only save is a battery
    one still appears in Continue playing - see _continue_playing, which reads
    both tables - it just opens instead of promising a resume.
    """
    out: dict[int, list[dict]] = {}
    if not rom_ids:
        return out
    states = (await session.execute(
        select(RomSaveState)
        .where(RomSaveState.user_id == user_id, RomSaveState.rom_id.in_(rom_ids))
        .order_by(desc(RomSaveState.updated_at))
    )).scalars().all()
    for s in states:
        out.setdefault(s.rom_id, []).append({
            # `save` is what the player wants on the URL: ?resume=1&save=<this>
            "save": f"state:{s.id}",
            # Always "state" now. Kept because themes read it, and a field that
            # quietly disappears breaks one written against an earlier GD.
            "kind": "state",
            "slot": s.slot,
            "screenshot": _screenshot_url(s.id, s.screenshot_path),
            "updated_at": s.updated_at.isoformat() if s.updated_at else None,
        })
    return out


async def _continue_playing(session: AsyncSession, user_id: int, limit: int = 8) -> list[dict]:
    """ROMs the user has a save for, newest activity first. Click-through resumes
    them; each entry carries its saves so a tile can offer the slots directly."""
    latest: dict[int, datetime] = {}
    for model in (RomSaveState, RomSave):
        rows = (await session.execute(
            select(model.rom_id, func.max(model.updated_at))
            .where(model.user_id == user_id).group_by(model.rom_id)
        )).all()
        for rid, ts in rows:
            if ts and (rid not in latest or ts > latest[rid]):
                latest[rid] = ts
    if not latest:
        return []
    top = sorted(latest.items(), key=lambda kv: kv[1], reverse=True)[:limit]
    ids = [rid for rid, _ in top]
    rmap = {r["rom_id"]: r for r in (await session.execute(
        select(*_ROM_TILE_COLS)
        .join(RomPlatform, Rom.platform_id == RomPlatform.id)
        .where(Rom.id.in_(ids))
    )).mappings().all()}
    smap = await _saves_for(session, user_id, ids)
    out: list[dict] = []
    for rid, ts in top:
        r = rmap.get(rid)
        if not r:
            continue
        out.append({
            **_rom_tile(r),
            "last_played": ts.isoformat() if ts else None,
            "saves": smap.get(rid, []),
        })
    return out


async def _recently_played(session: AsyncSession, user_id: int, limit: int = 8) -> list[dict]:
    """ROMs the user most recently LAUNCHED (any play, with a save or not), newest
    first - from rom_plays. Powers the dashboard "Recently played" strip; distinct
    from save-based Continue playing. Click-through opens the ROM. platform_slug is
    the routable slug (/emulation/<slug>/<id>), not the fs asset slug."""
    rows = (await session.execute(
        select(*_ROM_TILE_COLS, RomPlay.last_played_at.label("last_played_at"))
        .join(RomPlay, RomPlay.rom_id == Rom.id)
        .join(RomPlatform, Rom.platform_id == RomPlatform.id)
        .where(RomPlay.user_id == user_id)
        .order_by(desc(RomPlay.last_played_at))
        .limit(limit)
    )).mappings().all()
    return [{
        **_rom_tile(r),
        "last_played": r["last_played_at"].isoformat() if r["last_played_at"] else None,
    } for r in rows]


async def _recently_added(session: AsyncSession, limit: int = 12) -> list[dict]:
    """Newest library games + ROMs, merged by created_at (newest first)."""
    items: list[dict] = []
    lg = (await session.execute(
        select(LibraryGame.id, LibraryGame.title,
               func.coalesce(LibraryGame.cover_path, GogGame.cover_path, GogGame.cover_url).label("cover"),
               LibraryGame.source, LibraryGame.created_at)
        .outerjoin(GogGame, LibraryGame.gog_game_id == GogGame.id)
        .where(LibraryGame.is_active == True)  # noqa: E712
        .order_by(desc(LibraryGame.created_at)).limit(limit)
    )).all()
    for r in lg:
        # Library games (gog/custom) route to /games/<id>; no platform slug needed.
        items.append({"kind": r[3] or "custom", "id": r[0], "title": r[1], "cover": r[2],
                      "platform_slug": None, "created_at": r[4]})
    roms = (await session.execute(
        select(Rom.id, Rom.name, Rom.fs_name_no_ext, Rom.cover_path, Rom.created_at, RomPlatform.slug)
        .join(RomPlatform, Rom.platform_id == RomPlatform.id)
        .order_by(desc(Rom.created_at)).limit(limit)
    )).all()
    for r in roms:
        # ROMs route to /emulation/<platform_slug>/<id>.
        items.append({"kind": "rom", "id": r[0], "title": r[1] or r[2], "cover": r[3],
                      "platform_slug": r[5], "created_at": r[4]})
    items.sort(key=lambda x: x["created_at"] or datetime.min, reverse=True)
    for it in items:
        it["created_at"] = it["created_at"].isoformat() if it["created_at"] else None
    return items[:limit]


async def _top_downloaded(session: AsyncSession, start_dt: datetime, end_dt: datetime, limit: int = 5) -> list[dict]:
    """Most-downloaded library games inside the window."""
    rows = (await session.execute(
        select(LibraryGame.id, LibraryGame.title,
               func.coalesce(LibraryGame.cover_path, GogGame.cover_path, GogGame.cover_url).label("cover"),
               LibraryGame.source,
               func.count(DownloadStat.id).label("cnt"),
               func.coalesce(func.sum(DownloadStat.bytes_transferred), 0))
        .join(DownloadStat, DownloadStat.library_game_id == LibraryGame.id)
        .outerjoin(GogGame, LibraryGame.gog_game_id == GogGame.id)
        .where(DownloadStat.created_at >= start_dt, DownloadStat.created_at < end_dt)
        .group_by(LibraryGame.id).order_by(desc("cnt")).limit(limit)
    )).all()
    return [{
        "id": r[0], "title": r[1], "cover": r[2], "source": r[3] or "custom",
        "downloads": int(r[4]), "bytes": int(r[5] or 0),
    } for r in rows]


class DashboardHandler(DBBaseHandler):
    model = DownloadStat

    # ── User dashboard ──────────────────────────────────────────────────────────

    @begin_session
    async def get_user_dashboard(
        self, user_id: int, *, days: int = 30, start: str | None = None, end: str | None = None,
        sections: set[str] | None = None,
        session: AsyncSession = None,
    ) -> dict:
        """The signed-in user's own dashboard.

        `sections` narrows the work to what the caller will actually render - a
        theme's home wants the two play strips and none of the download series
        or request list, and paying for the whole thing on every home load, in
        every theme, is waste. None = everything (the dashboard itself).
        """
        def want(name: str) -> bool:
            return sections is None or name in sections

        start_dt, end_dt, bucket = _resolve_range(days, start, end)
        data: dict = {"downloads": {"count": 0, "games": 0, "bytes": 0, "avg_speed_bps": 0, "series": []},
                      "continue_playing": [], "recently_played": [],
                      "requests": {"items": [], "counts": {}}}

        if want("downloads"):
            try:
                totals = await _download_totals(session, start_dt, end_dt, user_id)
                totals["series"] = await _download_series(session, start_dt, end_dt, bucket, user_id)
                data["downloads"] = totals
            except Exception:
                pass

        if want("continue_playing"):
            try:
                data["continue_playing"] = await _continue_playing(session, user_id)
            except Exception:
                pass

        if want("recently_played"):
            try:
                data["recently_played"] = await _recently_played(session, user_id)
            except Exception:
                pass

        if not want("requests"):
            return data

        try:
            reqs = (await session.execute(
                select(GameRequest.title, GameRequest.status, GameRequest.platform, GameRequest.created_at)
                .where(GameRequest.user_id == user_id)
                .order_by(desc(GameRequest.created_at)).limit(25)
            )).all()
            data["requests"]["items"] = [{
                "title": r.title, "status": r.status, "platform": r.platform,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            } for r in reqs]
            counts = (await session.execute(
                select(GameRequest.status, func.count()).where(GameRequest.user_id == user_id)
                .group_by(GameRequest.status)
            )).all()
            data["requests"]["counts"] = {row[0]: int(row[1]) for row in counts}
        except Exception:
            pass

        return data

    # ── Admin dashboard ─────────────────────────────────────────────────────────

    @begin_session
    async def get_admin_dashboard(
        self, *, days: int = 30, start: str | None = None, end: str | None = None,
        session: AsyncSession = None,
    ) -> dict:
        start_dt, end_dt, bucket = _resolve_range(days, start, end)
        data: dict = {
            "library": {"gog": 0, "custom": 0, "rom": 0, "total": 0, "size_bytes": 0},
            "downloads": {"count": 0, "games": 0, "bytes": 0, "avg_speed_bps": 0, "series": []},
            "users": {"total": 0, "admins": 0},
            "top_user": None, "top_platforms": [],
            "recently_added": [], "top_downloaded": [], "server_health": {},
            "requests": {"counts": {}, "pending": 0},
            "security": {"banned": [], "failures": {"ips": 0, "attempts": 0}},
            "antivirus": {
                "enabled": False, "upload_scan": False, "download_scan": False,
                "running": False, "db_version": None, "db_date": None,
                "quarantined": 0, "recent": [],
            },
            "email": {"total": 0, "in_range": 0, "series": []},
            "disk": [],
        }

        try:
            gog = (await session.execute(select(func.count()).select_from(LibraryGame)
                   .where(LibraryGame.source == "gog", LibraryGame.is_active == True))).scalar_one()  # noqa: E712
            custom = (await session.execute(select(func.count()).select_from(LibraryGame)
                      .where(LibraryGame.source == "custom", LibraryGame.is_active == True))).scalar_one()  # noqa: E712
            rom = (await session.execute(select(func.count()).select_from(Rom))).scalar_one()
            size_lib = (await session.execute(select(func.coalesce(func.sum(LibraryFile.size_bytes), 0)))).scalar_one()
            size_rom = (await session.execute(select(func.coalesce(func.sum(Rom.fs_size_bytes), 0)))).scalar_one()
            data["library"] = {
                "gog": int(gog), "custom": int(custom), "rom": int(rom),
                "total": int(gog) + int(custom) + int(rom),
                "size_bytes": int(size_lib or 0) + int(size_rom or 0),
            }
        except Exception:
            pass

        try:
            totals = await _download_totals(session, start_dt, end_dt)
            totals["series"] = await _download_series(session, start_dt, end_dt, bucket)
            data["downloads"] = totals
        except Exception:
            pass

        try:
            total_users = (await session.execute(select(func.count()).select_from(User))).scalar_one()
            admin_users = (await session.execute(
                select(func.count()).select_from(User).where(User.role == "admin"))).scalar_one()
            data["users"] = {"total": int(total_users or 0), "admins": int(admin_users or 0)}
        except Exception:
            pass

        try:
            top = (await session.execute(
                select(User.username, User.avatar_path,
                       func.count(DownloadStat.id).label("cnt"),
                       func.coalesce(func.sum(DownloadStat.bytes_transferred), 0))
                .join(DownloadStat, DownloadStat.user_id == User.id)
                .where(DownloadStat.created_at >= start_dt, DownloadStat.created_at < end_dt)
                .group_by(User.id).order_by(desc("cnt")).limit(1)
            )).first()
            if top:
                data["top_user"] = {
                    "username": top[0], "avatar_path": top[1],
                    "downloads": int(top[2]), "bytes": int(top[3] or 0),
                }
        except Exception:
            pass

        try:
            plats = (await session.execute(
                select(RomPlatform.name, RomPlatform.slug, RomPlatform.fs_slug, func.count(Rom.id).label("cnt"),
                       func.coalesce(func.sum(Rom.fs_size_bytes), 0))
                .join(Rom, Rom.platform_id == RomPlatform.id)
                .group_by(RomPlatform.id).order_by(desc("cnt")).limit(8)
            )).all()
            # slug = routable library slug (/emulation/<slug>); fs_slug = asset key.
            data["top_platforms"] = [
                {"name": p[0], "slug": p[1], "logo": _platform_logo(p[2]), "count": int(p[3]), "bytes": int(p[4] or 0)}
                for p in plats
            ]
        except Exception:
            pass

        try:
            data["recently_added"] = await _recently_added(session)
        except Exception:
            pass

        try:
            data["top_downloaded"] = await _top_downloaded(session, start_dt, end_dt)
        except Exception:
            pass

        try:
            data["server_health"] = await asyncio.get_running_loop().run_in_executor(None, _server_health)
        except Exception:
            pass

        try:
            counts = (await session.execute(
                select(GameRequest.status, func.count()).group_by(GameRequest.status)
            )).all()
            cmap = {row[0]: int(row[1]) for row in counts}
            data["requests"] = {"counts": cmap, "pending": cmap.get("pending", 0)}
        except Exception:
            pass

        try:
            data["security"] = {
                "banned": await brute_force.get_banned_ips(),
                "failures": await brute_force.get_recent_failures(),
            }
        except Exception:
            pass

        try:
            from handler.clamav import clamav_handler
            from handler.database.quarantine_handler import quarantine_handler
            status = await clamav_handler.daemon_status()
            up_scan = await clamav_handler.is_upload_scanning_enabled()
            dn_scan = await clamav_handler.is_download_scanning_enabled()
            entries = await quarantine_handler.get_all()
            data["antivirus"] = {
                "enabled": bool(up_scan or dn_scan),
                "upload_scan": bool(up_scan),
                "download_scan": bool(dn_scan),
                "running": bool(status.get("running")),
                "db_version": status.get("db_version"),
                "db_date": status.get("db_date"),
                "quarantined": len(entries),
                "recent": [{
                    "filename": e.filename,
                    "threat": e.threat,
                    "file_size": e.file_size,
                    "triggered_by": e.triggered_by,
                    "created_at": e.created_at.isoformat() if e.created_at else None,
                } for e in entries[:6]],
            }
        except Exception:
            pass

        try:
            data["email"] = await get_email_stats(start_dt.date(), (end_dt - timedelta(seconds=1)).date())
        except Exception:
            pass

        try:
            data["disk"] = _disk_usage()
        except Exception:
            pass

        return data

    # ── Live download queue (admin) ─────────────────────────────────────────────

    async def get_download_queue(self) -> dict:
        """Active server-side downloads right now: in-flight GOG download jobs and
        in-flight torrents, normalised to a common shape for a live panel. Both
        sources are DB rows kept fresh by their background workers, so polling
        this endpoint reflects real progress. Point-in-time, ignores the window."""
        downloads: list[dict] = []
        try:
            from handler.gog.gog_download_handler import gog_download_handler
            for j in await gog_download_handler.list_jobs():
                if j.status in ("pending", "queued", "downloading", "paused"):
                    downloads.append({
                        "kind": "gog", "title": j.game_title, "file": j.file_name,
                        "status": j.status, "progress": round(float(j.progress_pct or 0), 1),
                        "speed_bps": int(j.speed_bps or 0),
                        "downloaded": int(j.downloaded_size or 0), "total": int(j.total_size or 0),
                        "eta": None,
                    })
        except Exception:
            pass
        try:
            from models.torrent_download import TorrentDownload
            async with async_session_factory() as db:
                rows = (await db.execute(
                    select(TorrentDownload).where(TorrentDownload.status == "downloading")
                    .order_by(TorrentDownload.id.desc())
                )).scalars().all()
            for tr in rows:
                frac = float(tr.percent_done or 0)
                downloads.append({
                    "kind": "torrent", "title": tr.title, "file": None,
                    "status": tr.status, "progress": round(frac * 100, 1),
                    "speed_bps": int(tr.rate_download or 0),
                    "downloaded": int(frac * (tr.total_size or 0)), "total": int(tr.total_size or 0),
                    "eta": int(tr.eta) if (tr.eta is not None and tr.eta >= 0) else None,
                })
        except Exception:
            pass

        # Uploads = server -> user: in-flight file downloads, attributed to the user.
        uploads: list[dict] = []
        try:
            from handler.dashboard import active_downloads
            uploads = active_downloads.snapshot()
        except Exception:
            pass

        # Seeding = server -> peers: live upload rate for each seeded library file.
        seeding: list[dict] = []
        try:
            from models.library_torrent import LibraryTorrent
            from models.library_file import LibraryFile
            async with async_session_factory() as db:
                seeds = (await db.execute(
                    select(LibraryTorrent.transmission_id, LibraryFile.filename)
                    .join(LibraryFile, LibraryTorrent.file_id == LibraryFile.id)
                    .where(LibraryTorrent.status == "seeding")
                )).all()
            if seeds:
                from handler.torrent.transmission_handler import transmission_handler
                by_id = {t.get("id"): t for t in await transmission_handler.get_all_torrents()}
                for tid, fname in seeds:
                    t = by_id.get(tid) or {}
                    seeding.append({
                        "filename": fname,
                        "upload_bps": int(t.get("rateUpload") or 0),
                        "peers": int(t.get("peersGettingFromUs") or 0),
                    })
        except Exception:
            pass

        return {
            "downloads": downloads, "uploads": uploads, "seeding": seeding,
            "active": len(downloads) + len(uploads) + len(seeding),
        }

    # ── Drill-down: who downloaded a given library game (admin) ─────────────────

    @begin_session
    async def get_game_downloaders(self, game_id: int, *, session: AsyncSession = None) -> dict:
        """Per-user download counts for one library game, most downloads first -
        the 'who downloaded this' drill-down from the Top downloaded panel."""
        out: dict = {"title": None, "downloaders": []}
        try:
            out["title"] = (await session.execute(
                select(LibraryGame.title).where(LibraryGame.id == game_id)
            )).scalar_one_or_none()
            rows = (await session.execute(
                select(User.username,
                       func.count(DownloadStat.id).label("cnt"),
                       func.coalesce(func.sum(DownloadStat.bytes_transferred), 0),
                       func.max(DownloadStat.created_at))
                .join(User, DownloadStat.user_id == User.id)
                .where(DownloadStat.library_game_id == game_id)
                .group_by(User.id).order_by(desc("cnt")).limit(50)
            )).all()
            out["downloaders"] = [{
                "username": r[0], "count": int(r[1]), "bytes": int(r[2] or 0),
                "last": r[3].isoformat() if r[3] else None,
            } for r in rows]
        except Exception:
            pass
        return out


dashboard_handler = DashboardHandler()
