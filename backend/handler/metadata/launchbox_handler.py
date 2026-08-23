"""LaunchBox metadata handler for ROMs - SQLite-backed on-disk index.

LaunchBox provides a downloadable XML database (no API key required).
The database is downloaded once and parsed into a SQLite file cached in
/data/config/launchbox_cache/launchbox.db (persistent volume).

The old in-memory dict approach required ~3 GB of Python heap for
719 K image entries and 189 platform game indexes.  With SQLite the
resident memory drops to < 50 MB (just the sqlite3 page cache).

Source: https://gamesdb.launchbox-app.com/Metadata.zip
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shutil
import sqlite3
import threading
import time
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

import httpx

logger = logging.getLogger(__name__)

_METADATA_URL  = "https://gamesdb.launchbox-app.com/Metadata.zip"
_CACHE_TTL_SEC = 7 * 24 * 3600   # re-download every 7 days

_cache_dir: Path | None = None
_db_conn:   sqlite3.Connection | None = None
_db_ready   = False          # True once the DB file exists and connection is open
_index_lock = asyncio.Lock()
_query_lock = threading.Lock()   # serialize SQLite writes / protect connection swap

# Image types to persist in DB (same set as before)
_WANTED_IMAGE_TYPES = {
    "Clear Logo",
    "Box - Front",
    "Box - Front - Reconstructed",
    "Box - 3D",
    "Banner",
    "Fanart - Background",
    "Fanart - Box - Front",
    "Screenshot - Gameplay",
    "Screenshot - Game Title",
    "Screenshot - Game Select",
    "Screenshot - Game Over",
    "Screenshot - High Scores",
}


# ── path helpers ─────────────────────────────────────────────────────────────

def _get_cache_dir() -> Path:
    global _cache_dir
    if _cache_dir is None:
        from config import CONFIG_PATH
        _cache_dir = Path(CONFIG_PATH) / "launchbox_cache"
        _cache_dir.mkdir(parents=True, exist_ok=True)
    return _cache_dir


def _zip_path() -> Path:
    return _get_cache_dir() / "Metadata.zip"


def _db_path() -> Path:
    return _get_cache_dir() / "launchbox.db"


# ── normalisation ─────────────────────────────────────────────────────────────

def _normalise(title: str) -> str:
    title = title.lower()
    title = re.sub(r"^(the|a|an)\s+", "", title)
    title = re.sub(r"[^\w\s]", " ", title)
    return re.sub(r"\s+", " ", title).strip()


# ── SQLite connection ─────────────────────────────────────────────────────────

def _open_connection(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA cache_size=-8192")   # 8 MB page cache
    conn.row_factory = sqlite3.Row
    return conn


# ── download ─────────────────────────────────────────────────────────────────

# The archive is about 150 MB. The ceiling is for a server that answers with
# something else entirely - an error page, a captcha, a redirect loop.
_MAX_ZIP_BYTES = 512 * 1024 * 1024


async def _download_zip(dest: Path) -> None:
    """Fetch the metadata archive straight to *dest*.

    It used to come back as `r.content` and be held in memory for the whole
    parse - 150 MB alongside the complete ElementTree of the uncompressed XML,
    which is the difference between a finished rebuild and an OOM kill on a
    2 GB container. A kill is quiet and expensive: nothing awaits this task, and
    the database is left unwritten, so every ROM lookup answers None until the
    next cycle seven days later.

    Written to a .part first and only moved into place once it is really a ZIP.
    A body that is not one - an error page with a fresh timestamp - would
    otherwise sit in the cache and suppress the next attempt for a week.
    """
    part = dest.with_name(dest.name + ".part")
    logger.info("Downloading LaunchBox metadata ZIP (~150 MB)…")
    try:
        free = shutil.disk_usage(dest.parent).free
        if free < _MAX_ZIP_BYTES // 2:
            raise RuntimeError(
                f"only {free // (1024 ** 2)} MB free where the LaunchBox cache lives"
            )
        written = 0
        async with httpx.AsyncClient(timeout=120, follow_redirects=True) as c:
            async with c.stream("GET", _METADATA_URL) as r:
                r.raise_for_status()
                with part.open("wb") as fh:
                    async for chunk in r.aiter_bytes(1 << 20):
                        written += len(chunk)
                        if written > _MAX_ZIP_BYTES:
                            raise RuntimeError("LaunchBox archive is implausibly large")
                        fh.write(chunk)
        if not zipfile.is_zipfile(part):
            raise RuntimeError("what came back is not a ZIP archive")
        os.replace(part, dest)
    finally:
        part.unlink(missing_ok=True)


# ── DB build (runs in thread pool) ───────────────────────────────────────────

def _build_db(zip_path: Path, target: Path) -> None:
    """Parse the Metadata.zip at *zip_path* → SQLite DB at *target*.

    Builds into a .tmp file and atomically renames to avoid a partially-built
    DB being opened on a crash. The ElementTree is deleted after use so CPython
    can reclaim it promptly.

    Takes a path rather than bytes: the archive used to be passed in as 150 MB
    of memory that stayed resident for the whole parse, alongside the tree
    itself. zipfile reads what it needs from the file.
    """
    tmp_p = Path(f"{target}.tmp")
    # A build that was interrupted - a container restart, a power cut - leaves
    # this file behind with its tables already created, and only the rename at
    # the end ever removes it. Opening it again would fail on CREATE TABLE and
    # wedge every future rebuild, silently: nobody awaits this task, so the
    # only symptom is one line in the log.
    tmp_p.unlink(missing_ok=True)
    tmp = str(tmp_p)
    conn = sqlite3.connect(tmp)
    built = False
    try:
        # Bulk-insert pragmas (safe because we rename atomically at the end)
        conn.execute("PRAGMA journal_mode=OFF")
        conn.execute("PRAGMA synchronous=OFF")
        conn.execute("PRAGMA cache_size=-16384")   # 16 MB during build

        conn.execute("""
            CREATE TABLE games (
                database_id      TEXT PRIMARY KEY,
                platform         TEXT NOT NULL,
                normalised_title TEXT NOT NULL,
                name             TEXT,
                summary          TEXT,
                developer        TEXT,
                publisher        TEXT,
                genres           TEXT,
                release_year     INTEGER,
                rating           REAL,
                player_count     TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE images (
                database_id TEXT NOT NULL,
                type        TEXT NOT NULL,
                url         TEXT NOT NULL
            )
        """)

        # ── open ZIP and parse XML ───────────────────────────────────────────
        with zipfile.ZipFile(str(zip_path)) as zf:
            names = zf.namelist()
            games_xml = next(
                (n for n in names if n.endswith("Metadata.xml") or n == "Games.xml"), None
            )
            if games_xml is None:
                games_xml = next(
                    (n for n in names if "game" in n.lower() and n.endswith(".xml")), None
                )
            if games_xml is None:
                logger.error("LaunchBox ZIP does not contain a recognisable games XML.")
                return
            logger.info("Parsing LaunchBox XML (%s)…", games_xml)
            with zf.open(games_xml) as f:
                tree = ET.parse(f)

        root = tree.getroot()

        # ── games ─────────────────────────────────────────────────────────────
        BATCH = 5_000
        rows: list[tuple] = []
        game_count = 0
        for el in root.findall("Game"):
            title    = (el.findtext("Name") or "").strip()
            platform = (el.findtext("Platform") or "").strip().lower()
            if not title or not platform:
                continue
            gid          = el.findtext("DatabaseID") or ""
            overview     = el.findtext("Overview") or ""
            developer    = el.findtext("Developer") or ""
            publisher    = el.findtext("Publisher") or ""
            genres_raw   = el.findtext("Genres") or ""
            genres       = [g.strip() for g in genres_raw.split(";") if g.strip()]
            year_raw     = el.findtext("ReleaseYear") or ""
            try:
                release_year: int | None = int(year_raw[:4]) if year_raw else None
            except ValueError:
                release_year = None
            rating: float | None = None
            try:
                rating_raw = el.findtext("CommunityRating") or ""
                rating = round(float(rating_raw), 1) if rating_raw else None
            except ValueError:
                pass
            player_count = (el.findtext("MaxPlayers") or "").strip() or None

            rows.append((
                gid, platform, _normalise(title), title,
                overview, developer, publisher, json.dumps(genres),
                release_year, rating, player_count,
            ))
            game_count += 1
            if len(rows) >= BATCH:
                conn.executemany(
                    "INSERT OR REPLACE INTO games VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows
                )
                rows.clear()

        if rows:
            conn.executemany(
                "INSERT OR REPLACE INTO games VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows
            )
        logger.info("LaunchBox: %d games written", game_count)

        # ── images ────────────────────────────────────────────────────────────
        img_rows: list[tuple] = []
        img_count = 0
        for el in root.findall("GameImage"):
            img_type = (el.findtext("Type") or "").strip()
            if img_type not in _WANTED_IMAGE_TYPES:
                continue
            db_id    = (el.findtext("DatabaseID") or "").strip()
            filename = (el.findtext("FileName") or "").strip()
            if db_id and filename:
                img_rows.append((db_id, img_type, f"https://images.launchbox-app.com/{filename}"))
                img_count += 1
                if len(img_rows) >= BATCH:
                    conn.executemany("INSERT INTO images VALUES (?,?,?)", img_rows)
                    img_rows.clear()

        if img_rows:
            conn.executemany("INSERT INTO images VALUES (?,?,?)", img_rows)
        logger.info("LaunchBox: %d image entries written", img_count)

        # Release ElementTree before creating indexes (saves peak memory)
        del root, tree

        # Indexes after bulk insert (orders of magnitude faster than before)
        conn.execute("CREATE INDEX idx_g_platform   ON games(platform)")
        conn.execute("CREATE INDEX idx_g_norm_title ON games(normalised_title)")
        conn.execute("CREATE INDEX idx_g_plat_title ON games(platform, normalised_title)")
        conn.execute("CREATE INDEX idx_i_dbid       ON images(database_id)")
        conn.commit()
        logger.info("LaunchBox SQLite index complete")
        built = True
    finally:
        conn.close()
        if not built:
            # Leave nothing for the next attempt to trip over.
            tmp_p.unlink(missing_ok=True)

    # Atomic replace
    if target.exists():
        target.unlink()
    shutil.move(tmp, str(target))


# ── ensure index ──────────────────────────────────────────────────────────────

async def _ensure_index() -> None:
    """Open (or rebuild) the SQLite index as needed."""
    global _db_conn, _db_ready

    db = _db_path()
    now = time.time()

    # Fast path: DB is open and fresh
    need_rebuild = not db.exists() or (now - db.stat().st_mtime) > _CACHE_TTL_SEC
    if _db_ready and not need_rebuild:
        return

    async with _index_lock:
        # Re-check inside lock
        need_rebuild = not db.exists() or (now - db.stat().st_mtime) > _CACHE_TTL_SEC
        if _db_ready and not need_rebuild:
            return

        zip_p = _zip_path()
        need_download = (
            not zip_p.exists()
            or (now - zip_p.stat().st_mtime) > _CACHE_TTL_SEC
        )

        if need_rebuild:
            if need_download:
                try:
                    await _download_zip(zip_p)
                except Exception as exc:
                    logger.error("Failed to download LaunchBox metadata: %s", exc)
                    if zip_p.exists():
                        logger.info("Using stale cached LaunchBox ZIP.")
                    else:
                        return

            # Close existing connection before rebuild
            with _query_lock:
                if _db_conn is not None:
                    _db_conn.close()
                    _db_conn = None
                _db_ready = False

            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, _build_db, zip_p, db)

        # Open connection (or re-open after rebuild)
        with _query_lock:
            if _db_conn is None:
                _db_conn = _open_connection(db)
            _db_ready = True


# ── query helpers (run in thread pool) ───────────────────────────────────────

def _row_to_game(row: sqlite3.Row) -> dict:
    try:
        genres = json.loads(row["genres"] or "[]")
    except Exception:
        genres = []
    return {
        "launchbox_id": row["database_id"],
        "name":         row["name"],
        "summary":      row["summary"],
        "developer":    row["developer"],
        "publisher":    row["publisher"],
        "genres":       genres,
        "release_year": row["release_year"],
        "rating":       row["rating"],
        "player_count": row["player_count"],
    }


def _format(raw: dict) -> dict:
    return {
        "launchbox_id":       raw.get("launchbox_id"),
        "name":               raw.get("name"),
        "summary":            raw.get("summary"),
        "developer":          raw.get("developer"),
        "publisher":          raw.get("publisher"),
        "genres":             raw.get("genres"),
        "release_year":       raw.get("release_year"),
        "rating":             raw.get("rating"),
        "player_count":       raw.get("player_count"),
        "launchbox_metadata": raw,
        "is_identified":      True,
    }


def _db_search_game(normalised: str, platform: str | None) -> dict | None:
    """Synchronous SQLite search - called via run_in_executor."""
    with _query_lock:
        conn = _db_conn
    if conn is None:
        return None

    params_exact = (normalised,)
    params_plat  = (platform.lower(), normalised) if platform else None

    # 1. Exact match on target platform
    if params_plat:
        row = conn.execute(
            "SELECT * FROM games WHERE platform=? AND normalised_title=? LIMIT 1",
            params_plat,
        ).fetchone()
        if row:
            return _row_to_game(row)

    # 2. Exact match any platform
    row = conn.execute(
        "SELECT * FROM games WHERE normalised_title=? LIMIT 1", params_exact
    ).fetchone()
    if row:
        return _row_to_game(row)

    # 3. Prefix match on target platform
    prefix = normalised + "%"
    if platform:
        row = conn.execute(
            "SELECT * FROM games WHERE platform=? AND normalised_title LIKE ? LIMIT 1",
            (platform.lower(), prefix),
        ).fetchone()
        if row:
            return _row_to_game(row)

    # 4. Prefix match any platform
    row = conn.execute(
        "SELECT * FROM games WHERE normalised_title LIKE ? LIMIT 1", (prefix,)
    ).fetchone()
    if row:
        return _row_to_game(row)

    # 5. Starts-with (query is prefix of title) - normalised starts with query
    like_rev = normalised[:10] + "%"   # use first 10 chars for index hint
    if platform:
        row = conn.execute(
            "SELECT * FROM games WHERE platform=? AND normalised_title LIKE ? LIMIT 1",
            (platform.lower(), like_rev),
        ).fetchone()
        if row and row["normalised_title"].startswith(normalised):
            return _row_to_game(row)

    return None


def _db_search_candidates(normalised: str, platform: str | None, max_results: int) -> list[dict]:
    """Synchronous SQLite candidate search - called via run_in_executor."""
    with _query_lock:
        conn = _db_conn
    if conn is None:
        return []

    results: list[dict] = []
    seen: set[str] = set()
    like_pat = f"%{normalised}%"
    plat_lower = platform.lower() if platform else None

    def _add(row: sqlite3.Row) -> None:
        gid = row["database_id"]
        if gid not in seen:
            seen.add(gid)
            results.append(_row_to_game(row))

    # Priority 1: exact match, target platform
    if plat_lower:
        for r in conn.execute(
            "SELECT * FROM games WHERE platform=? AND normalised_title=? LIMIT ?",
            (plat_lower, normalised, max_results),
        ):
            _add(r)

    # Priority 2: substring match, target platform
    if plat_lower and len(results) < max_results:
        for r in conn.execute(
            "SELECT * FROM games WHERE platform=? AND normalised_title LIKE ? LIMIT ?",
            (plat_lower, like_pat, max_results - len(results)),
        ):
            _add(r)

    # Priority 3: exact match, all platforms
    if len(results) < max_results:
        for r in conn.execute(
            "SELECT * FROM games WHERE normalised_title=? LIMIT ?",
            (normalised, max_results - len(results)),
        ):
            _add(r)

    # Priority 4: substring match, all platforms
    if len(results) < max_results:
        for r in conn.execute(
            "SELECT * FROM games WHERE normalised_title LIKE ? LIMIT ?",
            (like_pat, max_results - len(results)),
        ):
            _add(r)

    return results


def _db_get_images(db_id: str) -> list[dict]:
    with _query_lock:
        conn = _db_conn
    if conn is None:
        return []
    rows = conn.execute(
        "SELECT type, url FROM images WHERE database_id=?", (str(db_id),)
    ).fetchall()
    return [{"type": r["type"], "url": r["url"]} for r in rows]


# ── public API ────────────────────────────────────────────────────────────────

async def search_game(
    name: str,
    launchbox_platform: str | None,
    *,
    enabled: bool = True,
) -> dict | None:
    """Search LaunchBox for a single best-match game (used during auto-scrape)."""
    if not enabled:
        return None
    try:
        await _ensure_index()
    except Exception as exc:
        logger.warning("LaunchBox index error: %s", exc)
        return None
    if not _db_ready:
        return None

    normalised = _normalise(name)
    loop = asyncio.get_running_loop()
    raw = await loop.run_in_executor(None, _db_search_game, normalised, launchbox_platform)
    return _format(raw) if raw else None


async def search_candidates(
    name: str,
    launchbox_platform: str | None,
    max_results: int = 8,
) -> list[dict]:
    """Search LaunchBox for multiple candidates (used by the Edit Metadata search UI)."""
    try:
        await _ensure_index()
    except Exception as exc:
        logger.warning("LaunchBox index error: %s", exc)
        return []
    if not _db_ready:
        return []

    normalised = _normalise(name)
    if not normalised:
        return []

    loop = asyncio.get_running_loop()
    raws = await loop.run_in_executor(
        None, _db_search_candidates, normalised, launchbox_platform, max_results
    )
    return [_format(r) for r in raws]


def get_box_front(launchbox_id: str | int) -> dict | None:
    """Return the first Box - Front (or reconstructed) entry for the given ID."""
    entries = _db_get_images(str(launchbox_id))
    for e in entries:
        if e["type"] == "Box - Front":
            return e
    for e in entries:
        if e["type"] == "Box - Front - Reconstructed":
            return e
    return None


def get_clear_logos(launchbox_id: str | int) -> list[dict]:
    """Return Clear Logo image URLs for the given LaunchBox DatabaseID."""
    entries = _db_get_images(str(launchbox_id))
    return [e for e in entries if e["type"] == "Clear Logo"]


def get_lb_screenshots(launchbox_id: str | int) -> list[dict]:
    """Return screenshot image URLs for the given LaunchBox DatabaseID."""
    entries = _db_get_images(str(launchbox_id))
    return [e for e in entries if e["type"].startswith("Screenshot")]


def get_box_fronts(launchbox_id: str | int) -> list[dict]:
    """Return ALL cover-type images: Box - Front, Reconstructed, Box - 3D, Fanart - Box - Front."""
    _cover_types = {"Box - Front", "Box - Front - Reconstructed", "Box - 3D", "Fanart - Box - Front"}
    entries = _db_get_images(str(launchbox_id))
    return [e for e in entries if e["type"] in _cover_types]


def get_fanarts(launchbox_id: str | int) -> list[dict]:
    """Return hero/background images: Fanart - Background, Banner."""
    _hero_types = {"Fanart - Background", "Banner"}
    entries = _db_get_images(str(launchbox_id))
    return [e for e in entries if e["type"] in _hero_types]


def _db_get_game_by_id(db_id: str) -> dict | None:
    """Synchronous SQLite lookup by database_id."""
    with _query_lock:
        conn = _db_conn
    if conn is None:
        return None
    row = conn.execute(
        "SELECT * FROM games WHERE database_id=? LIMIT 1", (db_id,)
    ).fetchone()
    return _row_to_game(row) if row else None


async def get_game_by_id(launchbox_id: str | int) -> dict | None:
    """Lookup a LaunchBox game by its DatabaseID (for forced scraping)."""
    try:
        await _ensure_index()
    except Exception as exc:
        logger.warning("LaunchBox index error: %s", exc)
        return None
    if not _db_ready:
        return None

    loop = asyncio.get_running_loop()
    raw = await loop.run_in_executor(None, _db_get_game_by_id, str(launchbox_id))
    return _format(raw) if raw else None
