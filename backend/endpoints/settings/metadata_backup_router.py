"""Metadata backup / export / restore endpoint.

Exports the user's whole metadata investment (scraped game info + cover art +
API keys + plugin config) to a single ZIP and restores it on demand.

Archive layout (schema version 2):

    metadata-backup-YYYYMMDD-HHMM.zip
        manifest.json          - schema version, options, counts, generated_at
        tables/
            gog_games.json
            library_games.json
            library_files.json
            library_torrents.json
            rom_platforms.json
            roms.json
            game_requests.json
            plugin_config.json
            app_config.json    - only when include_settings=true
        media/
            <original-relative-path>     - e.g. resources/gog/123/covers/cover_auto.jpg

Behaviour notes
- Media files are streamed file-by-file into the ZIP; the response itself is
  written to a NamedTemporaryFile to avoid loading multi-GB libraries in RAM.
- `app_config` is only included when the admin opts in. Values are encrypted
  at rest with `AUTH_SECRET_KEY` so the backup is portable only between
  installations that share the same secret.
- Restore is upsert-by-external-id where possible (gog_id, igdb_id, ss_id,
  fs_slug, platform_id+fs_path) so re-running it on the same install is safe.
"""

from __future__ import annotations

import io
import json
import logging
import os
import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import inspect, select
from starlette.background import BackgroundTask

from config import BASE_PATH
from decorators.auth import protected_route
from handler.auth.scopes import Scope
from handler.database.session import async_session_factory

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/settings/metadata-backup", tags=["metadata-backup"])

# Bump when the export format changes incompatibly. Restore reads `manifest.schema_version`
# and refuses to run if it is unknown.
SCHEMA_VERSION = 2
SUPPORTED_VERSIONS = {1, 2}


# ── Path helpers ─────────────────────────────────────────────────────────────

def _abs_media(rel: str | None) -> str | None:
    """Convert a DB-stored relative path (e.g. `/resources/...`) to absolute."""
    if not rel or not isinstance(rel, str):
        return None
    rel = rel.strip()
    if not rel:
        return None
    # Already absolute and inside BASE_PATH
    if rel.startswith(BASE_PATH):
        return rel
    # Stored with leading slash -> relative to BASE_PATH
    if rel.startswith("/"):
        return os.path.join(BASE_PATH, rel.lstrip("/"))
    # Plain relative path
    return os.path.join(BASE_PATH, rel)


def _zip_arc_for(abs_path: str) -> str | None:
    """Convert an absolute on-disk path to its archive-relative path.

    Returns None if the path escapes BASE_PATH (defence in depth).
    """
    try:
        rel = os.path.relpath(abs_path, BASE_PATH)
    except ValueError:
        return None
    if rel.startswith(".."):
        return None
    # Always forward slashes inside the archive (matches Linux deployments)
    return "media/" + rel.replace("\\", "/")


def _safe_extract_to(target_root: str, member: str) -> str | None:
    """Resolve archive member -> safe absolute destination under target_root.

    Returns None when the member would escape via .. or absolute paths.
    """
    if not member.startswith("media/"):
        return None
    rel = member[len("media/"):]
    if not rel or rel.endswith("/"):
        return None
    rel_path = Path(rel)
    if rel_path.is_absolute() or any(p == ".." for p in rel_path.parts):
        return None
    dest = (Path(target_root) / rel_path).resolve()
    if not str(dest).startswith(str(Path(target_root).resolve())):
        return None
    return str(dest)


# ── Row serialisation ────────────────────────────────────────────────────────

def _row_to_dict(row: Any) -> dict:
    """Serialise a SQLAlchemy ORM row to a JSON-safe dict.

    Datetimes -> ISO strings, sets -> lists, bytes -> hex. Relationships are
    not expanded - only column attributes.
    """
    out: dict[str, Any] = {}
    mapper = inspect(row.__class__)
    for col in mapper.columns:
        v = getattr(row, col.key, None)
        if isinstance(v, datetime):
            out[col.key] = v.isoformat()
        elif isinstance(v, set):
            out[col.key] = sorted(v)
        elif isinstance(v, bytes):
            out[col.key] = v.hex()
        else:
            out[col.key] = v
    return out


async def _dump_table(model: type, session) -> list[dict]:
    """Fetch every row of `model` and convert to a list of dicts."""
    result = await session.execute(select(model))
    return [_row_to_dict(r) for r in result.scalars().all()]


# ── Media discovery ──────────────────────────────────────────────────────────

# Per-table list of column names that hold a single file path.
_SINGLE_PATH_COLUMNS: dict[str, list[str]] = {
    "gog_games":     ["cover_path", "background_path", "icon_path", "logo_path"],
    "library_games": ["cover_path", "background_path", "logo_path", "icon_path"],
    "rom_platforms": ["cover_path"],
    "roms": [
        "cover_path", "background_path", "support_path", "wheel_path",
        "bezel_path", "steamgrid_path", "video_path", "picto_path",
    ],
}

# Per-table list of column names whose value is a JSON list of paths.
_LIST_PATH_COLUMNS: dict[str, list[str]] = {
    "gog_games":     ["screenshots"],
    "library_games": ["screenshots"],
    "roms":          ["screenshots"],
}


def _collect_media_for(table: str, rows: list[dict]) -> list[str]:
    """Return absolute paths for every media file referenced by `rows`."""
    out: list[str] = []
    for row in rows:
        for col in _SINGLE_PATH_COLUMNS.get(table, []):
            ap = _abs_media(row.get(col))
            if ap:
                out.append(ap)
        for col in _LIST_PATH_COLUMNS.get(table, []):
            val = row.get(col)
            if isinstance(val, list):
                for item in val:
                    if isinstance(item, str):
                        ap = _abs_media(item)
                        if ap:
                            out.append(ap)
                    elif isinstance(item, dict):
                        # Some screenshots are stored as {url, path}
                        for k in ("path", "local_path", "url"):
                            v = item.get(k)
                            if v:
                                ap = _abs_media(v)
                                if ap:
                                    out.append(ap)
                                    break
    return out


# ── Models registry (load lazily for clean unit-test boundaries) ─────────────

@dataclass(frozen=True)
class BackupTable:
    name: str
    model_path: tuple[str, str]   # ("models.gog_game", "GogGame")
    upsert_keys: tuple[str, ...]  # column tuple used as the natural key
    primary_id_col: str = "id"


_TABLES: tuple[BackupTable, ...] = (
    BackupTable("rom_platforms",   ("models.rom_platform",   "RomPlatform"),   ("fs_slug",)),
    BackupTable("gog_games",       ("models.gog_game",       "GogGame"),       ("gog_id",)),
    BackupTable("library_games",   ("models.library_game",   "LibraryGame"),   ("igdb_id", "slug")),
    BackupTable("library_files",   ("models.library_file",   "LibraryFile"),   ("library_game_id", "file_path")),
    BackupTable("library_torrents",("models.library_torrent","LibraryTorrent"),("library_game_id", "magnet")),
    BackupTable("roms",            ("models.rom",            "Rom"),           ("platform_id", "fs_path")),
    BackupTable("game_requests",   ("models.game_request",   "GameRequest"),   ("title", "platform")),
    BackupTable("plugin_config",   ("models.plugin_config",  "PluginConfig"),  ("plugin_id", "key")),
)


def _import_model(path: tuple[str, str]):
    import importlib
    try:
        mod = importlib.import_module(path[0])
        return getattr(mod, path[1])
    except Exception:
        return None


# ── Preview ──────────────────────────────────────────────────────────────────

@protected_route(router.get, "/preview", scopes=[Scope.SETTINGS_READ])
async def preview_backup(request: Request) -> dict:
    """Return row counts, media file count and estimated archive size."""
    counts: dict[str, int] = {}
    all_paths: list[str] = []

    async with async_session_factory() as session:
        for tbl in _TABLES:
            model = _import_model(tbl.model_path)
            if not model:
                continue
            try:
                rows = await _dump_table(model, session)
            except Exception:
                continue
            counts[tbl.name] = len(rows)
            all_paths.extend(_collect_media_for(tbl.name, rows))

        # app_config
        try:
            from models.app_config import AppConfig
            counts["app_config"] = len((await session.execute(select(AppConfig))).scalars().all())
        except Exception:
            pass

    media_files = 0
    media_bytes = 0
    seen: set[str] = set()
    for p in all_paths:
        if p in seen:
            continue
        seen.add(p)
        try:
            st = os.stat(p)
            if not os.path.isfile(p):
                continue
            media_files += 1
            media_bytes += st.st_size
        except OSError:
            continue

    return {
        "schema_version": SCHEMA_VERSION,
        "counts":         counts,
        "total_rows":     sum(counts.values()),
        "media_files":    media_files,
        "media_bytes":    media_bytes,
    }


# ── Export ───────────────────────────────────────────────────────────────────

def _coerce_bool(v: str | bool | None) -> bool:
    if isinstance(v, bool):
        return v
    if v is None:
        return False
    return str(v).strip().lower() in ("1", "true", "yes", "on")


@protected_route(router.get, "/export", scopes=[Scope.SETTINGS_WRITE])
async def export_backup(
    request: Request,
    include_media:    bool = True,
    include_settings: bool = False,
) -> FileResponse:
    """Build a backup archive. Streams to a temp file, then `FileResponse`
    serves it and a BackgroundTask deletes the temp file when the response is done.

    Query params:
      include_media     true  - bundle every cover/background/screenshot/etc. (default)
      include_settings  false - bundle app_config + plugin secrets (sensitive!)
    """
    include_media    = _coerce_bool(include_media)
    include_settings = _coerce_bool(include_settings)

    # Dump all tables first so we can list referenced media and write JSON
    payload: dict[str, list[dict]] = {}
    async with async_session_factory() as session:
        for tbl in _TABLES:
            model = _import_model(tbl.model_path)
            if not model:
                continue
            try:
                payload[tbl.name] = await _dump_table(model, session)
            except Exception as exc:
                logger.warning("Backup: skipped table %s: %s", tbl.name, exc)
                payload[tbl.name] = []
        if include_settings:
            try:
                from models.app_config import AppConfig
                payload["app_config"] = await _dump_table(AppConfig, session)
            except Exception as exc:
                logger.warning("Backup: app_config dump failed: %s", exc)
                payload["app_config"] = []

    # Collect media paths (deduplicated)
    media_paths: list[str] = []
    if include_media:
        seen: set[str] = set()
        for tbl in _TABLES:
            for p in _collect_media_for(tbl.name, payload.get(tbl.name, [])):
                if p in seen:
                    continue
                seen.add(p)
                if os.path.isfile(p):
                    media_paths.append(p)

    counts = {k: len(v) for k, v in payload.items()}
    now    = datetime.now(timezone.utc)
    manifest = {
        "schema_version":   SCHEMA_VERSION,
        "generated_at":     now.isoformat(),
        "tool":             "GamesDownloader",
        "include_media":    include_media,
        "include_settings": include_settings,
        "counts":           counts,
        "media_files":      len(media_paths),
    }

    # Stream into a temp file so multi-GB libraries don't blow RAM
    tmp = tempfile.NamedTemporaryFile(prefix="gd-backup-", suffix=".zip", delete=False)
    tmp_path = tmp.name
    tmp.close()
    try:
        with zipfile.ZipFile(tmp_path, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
            zf.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))
            for name, rows in payload.items():
                zf.writestr(
                    f"tables/{name}.json",
                    json.dumps(rows, indent=2, ensure_ascii=False, default=str),
                )
            # Write media files - already-compressed formats (jpg/png/webp/mp4) get STORED
            # to skip pointless deflate work. JSONs above stay ZIP_DEFLATED.
            for ap in media_paths:
                arcname = _zip_arc_for(ap)
                if not arcname:
                    continue
                ext = os.path.splitext(ap)[1].lower()
                method = (
                    zipfile.ZIP_STORED
                    if ext in (".jpg", ".jpeg", ".png", ".webp", ".gif", ".mp4", ".webm", ".mp3", ".ogg")
                    else zipfile.ZIP_DEFLATED
                )
                try:
                    zf.write(ap, arcname=arcname, compress_type=method)
                except OSError:
                    logger.warning("Backup: skipped unreadable media %s", ap)
    except Exception:
        try: os.unlink(tmp_path)
        except OSError: pass
        raise

    fname = f"metadata-backup-{now.strftime('%Y%m%d-%H%M')}.zip"
    actor = (request.state.user.username
             if getattr(request.state, "user", None) else "?")
    logger.info(
        "Metadata backup export by '%s' (rows=%d, media=%d, size=%d B, settings=%s)",
        actor, sum(counts.values()), len(media_paths), os.path.getsize(tmp_path), include_settings,
    )

    def _cleanup(p: str = tmp_path):
        try:
            os.unlink(p)
        except OSError:
            pass

    return FileResponse(
        tmp_path,
        media_type="application/zip",
        filename=fname,
        background=BackgroundTask(_cleanup),
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


# ── Restore ──────────────────────────────────────────────────────────────────

def _coerce_value(model: type, col_name: str, value: Any) -> Any:
    """Reverse the JSON serialisation done in `_row_to_dict` so SQLAlchemy
    accepts the value when assigning to the ORM column.

    Datetime columns are read back from ISO strings; other columns pass through.
    """
    if value is None:
        return None
    try:
        col = inspect(model).columns.get(col_name)
        if col is None:
            return value
        coltype = str(col.type).upper()
        if "DATETIME" in coltype or "TIMESTAMP" in coltype:
            if isinstance(value, str):
                try:
                    return datetime.fromisoformat(value)
                except ValueError:
                    return None
            return value
        return value
    except Exception:
        return value


async def _upsert_row(session, tbl: BackupTable, model: type, row: dict) -> str:
    """Insert or update a single row by the table's natural key.

    Returns "inserted", "updated" or "skipped".
    """
    key_cols = [c for c in tbl.upsert_keys if c in row and row[c] is not None]
    if not key_cols:
        return "skipped"
    stmt = select(model)
    for c in key_cols:
        stmt = stmt.where(getattr(model, c) == row[c])
    existing = (await session.execute(stmt)).scalars().first()

    payload = {k: _coerce_value(model, k, v) for k, v in row.items() if k != "id"}

    if existing is None:
        try:
            obj = model(**payload)
            session.add(obj)
            await session.flush()
            return "inserted"
        except Exception as exc:
            logger.warning("Restore: insert into %s failed: %s", tbl.name, exc)
            return "skipped"
    else:
        for k, v in payload.items():
            try:
                setattr(existing, k, v)
            except Exception:
                pass
        await session.flush()
        return "updated"


@protected_route(router.post, "/restore", scopes=[Scope.SETTINGS_WRITE])
async def restore_backup(
    request: Request,
    file:             UploadFile = File(...),
    restore_metadata: str | None = Form("true"),
    restore_media:    str | None = Form("true"),
    restore_settings: str | None = Form("false"),
) -> dict:
    """Restore an archive previously produced by `/export`.

    `restore_metadata` upserts table rows by their natural key.
    `restore_media`    extracts files under `media/` to BASE_PATH (overwriting).
    `restore_settings` overwrites `app_config` rows by key. Off by default
                       because secrets in the archive only decrypt with the
                       same `AUTH_SECRET_KEY` used at backup time.
    """
    do_meta     = _coerce_bool(restore_metadata)
    do_media    = _coerce_bool(restore_media)
    do_settings = _coerce_bool(restore_settings)

    if not (do_meta or do_media or do_settings):
        raise HTTPException(status_code=400, detail="Nothing selected to restore")

    # Stream upload to disk so we don't fill RAM
    tmp = tempfile.NamedTemporaryFile(prefix="gd-restore-", suffix=".zip", delete=False)
    tmp_path = tmp.name
    try:
        while chunk := await file.read(1024 * 1024):
            tmp.write(chunk)
        tmp.close()

        try:
            zf = zipfile.ZipFile(tmp_path, "r")
        except zipfile.BadZipFile:
            raise HTTPException(status_code=400, detail="Not a ZIP archive")

        with zf:
            try:
                manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
            except KeyError:
                raise HTTPException(status_code=400, detail="manifest.json missing - not a GamesDownloader backup")
            except Exception:
                raise HTTPException(status_code=400, detail="manifest.json is not valid JSON")

            sv = manifest.get("schema_version")
            if sv not in SUPPORTED_VERSIONS:
                raise HTTPException(status_code=400, detail=f"Unsupported schema version: {sv}")

            stats = {
                "schema_version": sv,
                "tables":         {},
                "media_extracted": 0,
                "media_skipped":   0,
                "settings_applied": 0,
            }

            # ── Metadata ──────────────────────────────────────────────────
            if do_meta:
                async with async_session_factory() as session:
                    async with session.begin():
                        for tbl in _TABLES:
                            model = _import_model(tbl.model_path)
                            if not model:
                                continue
                            arc = f"tables/{tbl.name}.json"
                            try:
                                raw = zf.read(arc).decode("utf-8")
                            except KeyError:
                                continue
                            try:
                                rows = json.loads(raw)
                            except Exception:
                                stats["tables"][tbl.name] = {"error": "bad json"}
                                continue
                            inserted = updated = skipped = 0
                            for row in rows:
                                r = await _upsert_row(session, tbl, model, row)
                                if r == "inserted":
                                    inserted += 1
                                elif r == "updated":
                                    updated += 1
                                else:
                                    skipped += 1
                            stats["tables"][tbl.name] = {
                                "inserted": inserted,
                                "updated":  updated,
                                "skipped":  skipped,
                            }

            # ── Media ─────────────────────────────────────────────────────
            if do_media:
                for member in zf.namelist():
                    if not member.startswith("media/"):
                        continue
                    if member.endswith("/"):
                        continue
                    dest = _safe_extract_to(BASE_PATH, member)
                    if dest is None:
                        stats["media_skipped"] += 1
                        continue
                    try:
                        os.makedirs(os.path.dirname(dest), exist_ok=True)
                        with zf.open(member, "r") as src, open(dest, "wb") as out:
                            shutil.copyfileobj(src, out)
                        stats["media_extracted"] += 1
                    except Exception as exc:
                        logger.warning("Restore: failed media %s: %s", member, exc)
                        stats["media_skipped"] += 1

            # ── Settings (app_config) ─────────────────────────────────────
            if do_settings:
                try:
                    raw = zf.read("tables/app_config.json").decode("utf-8")
                    rows = json.loads(raw)
                except KeyError:
                    rows = []
                except Exception:
                    rows = []
                if rows:
                    from models.app_config import AppConfig
                    async with async_session_factory() as session:
                        async with session.begin():
                            for row in rows:
                                key = row.get("key")
                                if not key:
                                    continue
                                existing = (await session.execute(
                                    select(AppConfig).where(AppConfig.key == key)
                                )).scalars().first()
                                if existing is None:
                                    obj = AppConfig(
                                        key=key,
                                        value=row.get("value"),
                                        is_sensitive=bool(row.get("is_sensitive", False)),
                                    )
                                    session.add(obj)
                                else:
                                    existing.value = row.get("value")
                                    existing.is_sensitive = bool(row.get("is_sensitive", existing.is_sensitive))
                                stats["settings_applied"] += 1

        actor = (request.state.user.username
                 if getattr(request.state, "user", None) else "?")
        logger.info("Metadata restore by '%s': %s", actor, stats)
        return {"ok": True, "stats": stats, "manifest": manifest}

    finally:
        try: os.unlink(tmp_path)
        except OSError: pass
