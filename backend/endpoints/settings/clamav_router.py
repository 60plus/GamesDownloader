"""ClamAV endpoints - scan management, definitions update, quarantine.

All endpoints require SETTINGS_READ (GET) or SETTINGS_WRITE (POST/DELETE).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, field_validator

from decorators.auth import protected_route
from handler.auth.scopes import Scope
from handler.config.config_handler import config_handler
from handler.database.scan_handler import scan_handler
from handler.database.quarantine_handler import quarantine_handler
from handler.clamav import clamav_handler

logger = logging.getLogger(__name__)

clamav_router = APIRouter(prefix="/api/settings/security/clamav", tags=["clamav"])


# ── Pydantic models ────────────────────────────────────────────────────────────

class ClamavConfig(BaseModel):
    enabled:                bool = True
    auto_scan_upload:       bool = False
    auto_scan_download:     bool = False
    action:                 str  = "quarantine"   # "none" | "quarantine" | "delete"
    auto_update:            bool = False
    update_interval_hours:  int  = 24             # 1–168 h

    @field_validator("action")
    @classmethod
    def _validate_action(cls, v: str) -> str:
        if v not in ("none", "quarantine", "delete"):
            raise ValueError("action must be 'none', 'quarantine', or 'delete'")
        return v

    @field_validator("update_interval_hours")
    @classmethod
    def _validate_interval(cls, v: int) -> int:
        if not (1 <= v <= 168):
            raise ValueError("update_interval_hours must be between 1 and 168")
        return v


class ScanRequest(BaseModel):
    paths: list[str]   # subset of ["games", "downloads", "roms"]


# ── Helper ─────────────────────────────────────────────────────────────────────

def _current_user(request: Request) -> str | None:
    return getattr(request.state, "user", None)


def _fmt_entry(r) -> dict:
    return {
        "id":             r.id,
        "original_path":  r.original_path,
        "quarantine_path": r.quarantine_path,
        "threat":         r.threat,
        "filename":       r.filename,
        "file_size":      r.file_size,
        "scan_id":        r.scan_id,
        "triggered_by":   r.triggered_by,
        "created_at":     r.created_at.isoformat() if r.created_at else None,
        # Whether the quarantine file still physically exists
        "file_exists":    os.path.exists(r.quarantine_path),
    }


# ── Config ─────────────────────────────────────────────────────────────────────

def _read_cfg_int(raw: str | None, default: int) -> int:
    try:
        return int(raw) if raw else default
    except (TypeError, ValueError):
        return default


@protected_route(clamav_router.get, "/status", scopes=[Scope.SETTINGS_READ])
async def get_status(request: Request):
    """Return daemon status + current config."""
    status = await clamav_handler.daemon_status()
    cfg = {
        "enabled":               await config_handler.get_bool("clamav_enabled", default=True),
        "auto_scan_upload":      await config_handler.get_bool("clamav_auto_scan_upload", default=False),
        "auto_scan_download":    await config_handler.get_bool("clamav_auto_scan_download", default=False),
        "action":                (await config_handler.get("clamav_action")) or "quarantine",
        "auto_update":           await config_handler.get_bool("clamav_auto_update", default=False),
        "update_interval_hours": _read_cfg_int(await config_handler.get("clamav_update_interval_hours"), 24),
        "last_auto_update":      await config_handler.get("clamav_last_auto_update"),
    }
    return {**status, "config": cfg, "scannable_paths": list(clamav_handler.SCANNABLE_PATHS.keys())}


@protected_route(clamav_router.get, "/config", scopes=[Scope.SETTINGS_READ])
async def get_config(request: Request):
    return {
        "enabled":               await config_handler.get_bool("clamav_enabled", default=True),
        "auto_scan_upload":      await config_handler.get_bool("clamav_auto_scan_upload", default=False),
        "auto_scan_download":    await config_handler.get_bool("clamav_auto_scan_download", default=False),
        "action":                (await config_handler.get("clamav_action")) or "quarantine",
        "auto_update":           await config_handler.get_bool("clamav_auto_update", default=False),
        "update_interval_hours": _read_cfg_int(await config_handler.get("clamav_update_interval_hours"), 24),
        "last_auto_update":      await config_handler.get("clamav_last_auto_update"),
    }


@protected_route(clamav_router.post, "/config", scopes=[Scope.SETTINGS_WRITE])
async def save_config(request: Request, body: ClamavConfig):
    await config_handler.set("clamav_enabled",               str(body.enabled).lower())
    await config_handler.set("clamav_auto_scan_upload",      str(body.auto_scan_upload).lower())
    await config_handler.set("clamav_auto_scan_download",    str(body.auto_scan_download).lower())
    await config_handler.set("clamav_action",                body.action)
    await config_handler.set("clamav_auto_update",           str(body.auto_update).lower())
    await config_handler.set("clamav_update_interval_hours", str(body.update_interval_hours))
    return {"ok": True}


# ── Definitions ────────────────────────────────────────────────────────────────

@protected_route(clamav_router.post, "/update-definitions", scopes=[Scope.SETTINGS_WRITE])
async def update_definitions(request: Request):
    """Trigger freshclam in the background. Progress via Socket.IO: clamav:update_progress"""
    asyncio.create_task(clamav_handler.update_definitions())
    return {"ok": True, "message": "Definition update started"}


# ── Scans ──────────────────────────────────────────────────────────────────────

@protected_route(clamav_router.post, "/scan", scopes=[Scope.SETTINGS_WRITE])
async def start_scan(request: Request, body: ScanRequest):
    """Start a background file scan. Progress via Socket.IO: clamav:scan_progress / clamav:scan_complete"""
    valid_keys = list(clamav_handler.SCANNABLE_PATHS.keys())
    requested  = [p for p in body.paths if p in valid_keys]
    if not requested:
        raise HTTPException(400, f"No valid paths. Choose from: {valid_keys}")

    status = await clamav_handler.daemon_status()
    if not status["running"]:
        raise HTTPException(503, "ClamAV daemon is not running. Update virus definitions first.")

    username = _current_user(request)
    record   = await scan_handler.create(
        scan_type="manual",
        paths=",".join(requested),
        triggered_by=username,
    )
    asyncio.create_task(
        clamav_handler.scan_paths(
            folder_keys=requested,
            scan_id=record.id,
            triggered_by=username,
        )
    )
    return {"ok": True, "scan_id": record.id}


@protected_route(clamav_router.get, "/scans", scopes=[Scope.SETTINGS_READ])
async def list_scans(request: Request, limit: int = 20):
    rows = await scan_handler.get_recent(limit=min(limit, 100))
    return [
        {
            "id":             r.id,
            "scan_type":      r.scan_type,
            "paths":          r.paths,
            "status":         r.status,
            "total_files":    r.total_files,
            "infected_count": r.infected_count,
            "clean_count":    r.clean_count,
            "error_count":    r.error_count,
            "infected_files": json.loads(r.infected_files) if r.infected_files else [],
            "triggered_by":   r.triggered_by,
            "created_at":     r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


@protected_route(clamav_router.get, "/scans/{scan_id}", scopes=[Scope.SETTINGS_READ])
async def get_scan(request: Request, scan_id: int):
    row = await scan_handler.get(scan_id)
    if not row:
        raise HTTPException(404, "Scan not found")
    return {
        "id":             row.id,
        "scan_type":      row.scan_type,
        "paths":          row.paths,
        "status":         row.status,
        "total_files":    row.total_files,
        "infected_count": row.infected_count,
        "clean_count":    row.clean_count,
        "error_count":    row.error_count,
        "infected_files": json.loads(row.infected_files) if row.infected_files else [],
        "error_message":  row.error_message,
        "triggered_by":   row.triggered_by,
        "created_at":     row.created_at.isoformat() if row.created_at else None,
    }


# ── Quarantine ────────────────────────────────────────────────────────────────

@protected_route(clamav_router.get, "/quarantine", scopes=[Scope.SETTINGS_READ])
async def list_quarantine(request: Request):
    """Return all quarantine entries with their physical existence flag."""
    rows = await quarantine_handler.get_all()
    return [_fmt_entry(r) for r in rows]


@protected_route(clamav_router.post, "/quarantine/{entry_id}/restore", scopes=[Scope.SETTINGS_WRITE])
async def restore_quarantine(request: Request, entry_id: int):
    """
    Restore a quarantined file to its original location.
    Fails if the original path already exists (to avoid accidental overwrites).
    """
    import shutil
    entry = await quarantine_handler.get(entry_id)
    if not entry:
        raise HTTPException(404, "Quarantine entry not found")
    if not os.path.exists(entry.quarantine_path):
        raise HTTPException(410, "Quarantine file no longer exists on disk")
    if os.path.exists(entry.original_path):
        raise HTTPException(409, f"Original path already exists: {entry.original_path}")

    # Re-create parent dirs if needed
    os.makedirs(os.path.dirname(entry.original_path), exist_ok=True)

    try:
        shutil.move(entry.quarantine_path, entry.original_path)
    except Exception as exc:
        raise HTTPException(500, f"Failed to restore file: {exc}") from exc

    await quarantine_handler.delete(entry_id)
    logger.info("ClamAV quarantine: restored %s → %s", entry.quarantine_path, entry.original_path)
    return {"ok": True, "restored_to": entry.original_path}


@protected_route(clamav_router.delete, "/quarantine/{entry_id}", scopes=[Scope.SETTINGS_WRITE])
async def delete_quarantine(request: Request, entry_id: int):
    """Permanently delete a quarantined file and remove the DB record."""
    entry = await quarantine_handler.get(entry_id)
    if not entry:
        raise HTTPException(404, "Quarantine entry not found")

    # Remove physical file if it still exists
    if os.path.exists(entry.quarantine_path):
        try:
            os.remove(entry.quarantine_path)
        except Exception as exc:
            raise HTTPException(500, f"Failed to delete file: {exc}") from exc

    await quarantine_handler.delete(entry_id)
    logger.info("ClamAV quarantine: permanently deleted %s (%s)", entry.filename, entry.threat)
    return {"ok": True}
