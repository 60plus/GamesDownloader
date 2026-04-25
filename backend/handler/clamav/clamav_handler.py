"""ClamAV integration handler.

Responsibilities:
  - daemon_status()       : check if clamd is reachable, return version + DB date
  - scan_paths()          : recursive scan with per-file Socket.IO progress
  - update_definitions()  : run freshclam as a subprocess, stream output via Socket.IO
  - _start_daemon_async() : (re)start clamd after definitions are downloaded

Action on infected file (configured via clamav_action in app config):
  "none"       - report only, file is untouched
  "quarantine" - move file to /data/clamav/quarantine/, record in DB (default)
  "delete"     - permanently remove file, record deletion in DB

Socket.IO events emitted:
  clamav:scan_progress    {scan_id, current, total, path, status}
  clamav:scan_complete    {scan_id, total, infected, clean, errors, infected_files, action_taken}
  clamav:update_progress  {status: "running"|"complete"|"error", message}
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

_SOCKET_PATH    = "/tmp/clamd.sock"
_CLAMD_CONF     = "/etc/clamav/clamd.conf"
_FRESHCLAM_CONF = "/etc/clamav/freshclam.conf"

# Base data directory - same as GD_BASE_PATH inside the container
_DATA_DIR   = os.environ.get("GD_BASE_PATH", "/data")
_GAMES_DIR  = os.environ.get("GD_GAMES_PATH", os.path.join(_DATA_DIR, "games"))

_QUARANTINE_DIR = os.path.join(_DATA_DIR, "clamav", "quarantine")

# Map friendly folder keys to absolute container paths.
# GOG and Custom are both under /data/games but in separate subdirectories.
SCANNABLE_PATHS: dict[str, str] = {
    "gog":       os.path.join(_GAMES_DIR, "GOG"),
    "custom":    os.path.join(_GAMES_DIR, "CUSTOM"),
    "downloads": os.path.join(_DATA_DIR, "downloads"),
}


# ── helpers ───────────────────────────────────────────────────────────────────

def _get_clamd():
    """Return a connected ClamdUnixSocket or raise RuntimeError."""
    try:
        import clamd
        cd = clamd.ClamdUnixSocket(path=_SOCKET_PATH)
        cd.ping()  # raises ConnectionError if not running
        return cd
    except ImportError:
        raise RuntimeError("clamd Python library not installed")
    except Exception as exc:
        raise RuntimeError(f"clamd not reachable: {exc}") from exc


def _collect_files(paths: list[str]) -> list[str]:
    """Walk directories and return sorted list of regular file paths."""
    files: list[str] = []
    for root_path in paths:
        p = Path(root_path)
        if not p.exists():
            continue
        if p.is_file():
            files.append(str(p))
        else:
            for f in sorted(p.rglob("*")):
                if f.is_file() and not f.is_symlink():
                    files.append(str(f))
    return files


async def _get_action() -> str:
    """Load clamav_action from config. Defaults to 'quarantine'."""
    from handler.config.config_handler import config_handler
    val = await config_handler.get("clamav_action")
    if val in ("none", "quarantine", "delete"):
        return val
    return "quarantine"


def _quarantine_file(fpath: str) -> str:
    """
    Move fpath into the quarantine directory.
    Returns the new quarantine path.
    Raises OSError on failure.
    """
    os.makedirs(_QUARANTINE_DIR, exist_ok=True)
    filename   = os.path.basename(fpath)
    unique_name = f"{uuid.uuid4().hex}__{filename}"
    dest = os.path.join(_QUARANTINE_DIR, unique_name)
    shutil.move(fpath, dest)
    return dest


# ── public API ────────────────────────────────────────────────────────────────

async def daemon_status() -> dict:
    """
    Return current ClamAV daemon status.

    Returns dict:
      running       bool
      version       str | None
      db_version    str | None   (virus database version number)
      db_date       str | None   (ISO-8601 date of virus DB)
      socket_path   str
      error         str | None
    """
    loop = asyncio.get_running_loop()

    def _check():
        try:
            import clamd
            cd = clamd.ClamdUnixSocket(path=_SOCKET_PATH)
            version_str = cd.version()   # e.g. "ClamAV 1.0.3/27123/Thu Mar 27 10:00:00 2026"
            # Parse version string
            parts = version_str.split("/")
            clamav_ver  = parts[0].strip()
            db_version  = parts[1].strip() if len(parts) > 1 else None
            db_date_raw = parts[2].strip() if len(parts) > 2 else None
            db_date = None
            if db_date_raw:
                try:
                    dt = datetime.strptime(db_date_raw, "%a %b %d %H:%M:%S %Y")
                    db_date = dt.replace(tzinfo=timezone.utc).isoformat()
                except ValueError:
                    db_date = db_date_raw
            return {
                "running":    True,
                "version":    clamav_ver,
                "db_version": db_version,
                "db_date":    db_date,
                "socket_path": _SOCKET_PATH,
                "error":      None,
            }
        except Exception as exc:
            return {
                "running":    False,
                "version":    None,
                "db_version": None,
                "db_date":    None,
                "socket_path": _SOCKET_PATH,
                "error":      str(exc),
            }

    return await loop.run_in_executor(None, _check)


async def scan_paths(
    folder_keys: list[str],
    scan_id: int,
    triggered_by: str | None = None,
    scan_type: str = "manual",
) -> None:
    """
    Scan the given folder keys (subset of SCANNABLE_PATHS) file by file.
    For each infected file, applies the configured action (none/quarantine/delete).
    Updates the ScanResult DB record and emits Socket.IO progress events.
    """
    from handler.socket_handler import emit_event
    from handler.database.scan_handler import scan_handler
    from handler.database.quarantine_handler import quarantine_handler

    abs_paths = [SCANNABLE_PATHS[k] for k in folder_keys if k in SCANNABLE_PATHS]
    loop      = asyncio.get_running_loop()
    action    = await _get_action()

    # Collect files (blocking I/O → executor)
    files = await loop.run_in_executor(None, _collect_files, abs_paths)
    total = len(files)
    await scan_handler.update(scan_id, total_files=total)

    infected:    list[dict] = []
    clean_count  = 0
    error_count  = 0

    # Get clamd connection (blocking)
    try:
        cd = await loop.run_in_executor(None, _get_clamd)
    except RuntimeError as exc:
        await scan_handler.update(scan_id, status="error", error_message=str(exc))
        await emit_event("clamav:scan_complete", {"scan_id": scan_id, "error": str(exc)})
        return

    for idx, fpath in enumerate(files, start=1):
        await emit_event("clamav:scan_progress", {
            "scan_id": scan_id,
            "current": idx,
            "total":   total,
            "path":    os.path.basename(fpath),
        })

        def _scan_one(path: str):
            try:
                result = cd.scan(path)
                if result is None:
                    return "ok", None
                status, name = result.get(path, ("ok", None))
                return status, name
            except Exception as exc:
                return "error", str(exc)

        status, threat = await loop.run_in_executor(None, _scan_one, fpath)

        if status == "FOUND":
            entry: dict = {"path": fpath, "threat": threat, "action": action}

            if action == "quarantine":
                try:
                    file_size      = os.path.getsize(fpath)
                    quarantine_path = await loop.run_in_executor(None, _quarantine_file, fpath)
                    q_entry = await quarantine_handler.create(
                        original_path=fpath,
                        quarantine_path=quarantine_path,
                        threat=threat or "unknown",
                        filename=os.path.basename(fpath),
                        file_size=file_size,
                        scan_id=scan_id,
                        triggered_by=triggered_by,
                    )
                    entry["quarantine_id"] = q_entry.id
                    entry["quarantine_path"] = quarantine_path
                    logger.warning("ClamAV: quarantined %s (%s) → %s", fpath, threat, quarantine_path)
                except Exception as exc:
                    logger.error("ClamAV: failed to quarantine %s: %s", fpath, exc)
                    entry["action"] = "quarantine_failed"
                    entry["error"]  = str(exc)

            elif action == "delete":
                try:
                    await loop.run_in_executor(None, os.remove, fpath)
                    logger.warning("ClamAV: deleted infected file %s (%s)", fpath, threat)
                except Exception as exc:
                    logger.error("ClamAV: failed to delete %s: %s", fpath, exc)
                    entry["action"] = "delete_failed"
                    entry["error"]  = str(exc)

            infected.append(entry)

        elif status == "error":
            error_count += 1
        else:
            clean_count += 1

        # Flush to DB every 50 files
        if idx % 50 == 0 or idx == total:
            await scan_handler.update(
                scan_id,
                infected_count=len(infected),
                clean_count=clean_count,
                error_count=error_count,
                infected_files=json.dumps(infected) if infected else None,
            )

    # Finalise
    await scan_handler.update(
        scan_id,
        status="complete",
        total_files=total,
        infected_count=len(infected),
        clean_count=clean_count,
        error_count=error_count,
        infected_files=json.dumps(infected) if infected else None,
    )
    await scan_handler._trim()

    await emit_event("clamav:scan_complete", {
        "scan_id":       scan_id,
        "total":         total,
        "infected":      len(infected),
        "clean":         clean_count,
        "errors":        error_count,
        "infected_files": infected,
        "action_taken":  action,
    })


async def update_definitions() -> None:
    """
    Run freshclam and stream stdout/stderr back via Socket.IO.
    After a successful update, (re)start clamd so it loads the new DB.
    """
    from handler.socket_handler import emit_event

    async def _emit(msg: str, status: str = "running") -> None:
        await emit_event("clamav:update_progress", {"status": status, "message": msg})

    await _emit("Starting freshclam...")

    try:
        proc = await asyncio.create_subprocess_exec(
            "freshclam",
            "--config-file", _FRESHCLAM_CONF,
            "--stdout",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        async for line in proc.stdout:
            text = line.decode(errors="replace").rstrip()
            if text:
                await _emit(text)
        await proc.wait()

        if proc.returncode == 0:
            await _emit("Definitions updated successfully. Starting ClamAV daemon...")
            ok = await _start_daemon_async(_emit)
            if ok:
                await _emit("ClamAV ready.", "complete")
            # else: _start_daemon_async already emitted an error
        elif proc.returncode == 1:
            # freshclam exit 1 = already up to date
            await _emit("Virus definitions are already up to date.")
            ok = await _start_daemon_async(_emit)
            if ok:
                await _emit("ClamAV ready.", "complete")
        else:
            await _emit(f"freshclam exited with code {proc.returncode}", "error")

    except FileNotFoundError:
        await _emit("freshclam not found - ClamAV not installed in this container", "error")
    except Exception as exc:
        await _emit(f"Update failed: {exc}", "error")


async def auto_update_loop() -> None:
    """
    Background task started at app startup.
    Wakes every hour, checks whether auto-update is enabled and whether
    the configured interval has elapsed since the last successful update,
    then runs freshclam if needed.

    Stores the timestamp of the last successful run in config key
    'clamav_last_auto_update' (ISO-8601 UTC string).
    """
    from handler.config.config_handler import config_handler

    # Wait 90 s after startup so the DB / config handler is fully ready
    await asyncio.sleep(90)
    logger.info("ClamAV auto-update loop started")

    while True:
        try:
            enabled    = (await config_handler.get("clamav_enabled")    or "true" ).lower() == "true"
            auto_upd   = (await config_handler.get("clamav_auto_update") or "false").lower() == "true"

            if enabled and auto_upd:
                interval_h = 24
                try:
                    raw = await config_handler.get("clamav_update_interval_hours")
                    interval_h = max(1, int(raw)) if raw else 24
                except (TypeError, ValueError):
                    pass

                due      = True
                last_str = await config_handler.get("clamav_last_auto_update")
                if last_str:
                    try:
                        last_dt = datetime.fromisoformat(last_str)
                        elapsed = (datetime.now(timezone.utc) - last_dt).total_seconds() / 3600
                        due     = elapsed >= interval_h
                    except ValueError:
                        pass

                if due:
                    logger.info(
                        "ClamAV: scheduled auto-update starting (interval=%dh)…", interval_h
                    )
                    await update_definitions()
                    await config_handler.set(
                        "clamav_last_auto_update",
                        datetime.now(timezone.utc).isoformat(),
                    )
                    logger.info("ClamAV: auto-update complete")

        except Exception as exc:
            logger.error("ClamAV auto-update loop error: %s", exc)

        await asyncio.sleep(3600)   # re-check every hour


async def _start_daemon_async(emit_fn=None) -> bool:
    """
    Start clamd if it is not already running.

    ClamAV loads 3.5M+ signatures which takes 30–60 s on first start.
    We launch the process, then poll the Unix socket every 2 s for up to
    90 s, emitting progress messages so the UI stays responsive.

    Returns True if the daemon is ready, False on failure/timeout.
    """
    # Already up?
    status = await daemon_status()
    if status["running"]:
        return True

    async def _emit(msg: str, lvl: str = "running") -> None:
        if emit_fn:
            await emit_fn(msg, lvl)
        logger.info("ClamAV: %s", msg)

    await _emit("Launching clamd - loading virus signatures (may take 30–60 s)…")

    try:
        proc = await asyncio.create_subprocess_exec(
            "clamd", "--config-file", _CLAMD_CONF,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
    except FileNotFoundError:
        await _emit("clamd binary not found - ClamAV not installed", "error")
        return False
    except Exception as exc:
        await _emit(f"Failed to launch clamd: {exc}", "error")
        return False

    # Poll until socket responds or process exits / times out
    _POLL_INTERVAL = 2    # seconds between checks
    _TIMEOUT       = 120  # seconds max wait (3.5M sigs can be slow on low RAM)

    for attempt in range(_TIMEOUT // _POLL_INTERVAL):
        await asyncio.sleep(_POLL_INTERVAL)

        # Check if the process exited (with Foreground yes this means a real crash,
        # not a daemonize fork - code 0 here would also be unexpected)
        if proc.returncode is not None:
            # First check whether clamd actually started successfully despite the exit
            # (shouldn't happen with Foreground yes, but be defensive)
            st = await daemon_status()
            if st["running"]:
                return True
            # Drain output for a useful error message
            try:
                out, _ = await asyncio.wait_for(proc.communicate(), timeout=2)
                snippet = out.decode(errors="replace").strip()[-400:]
            except Exception:
                snippet = "(no output)"
            await _emit(
                f"clamd exited unexpectedly (code {proc.returncode}): {snippet}",
                "error",
            )
            return False

        # Check if socket is ready
        st = await daemon_status()
        if st["running"]:
            elapsed = (attempt + 1) * _POLL_INTERVAL
            await _emit(f"ClamAV daemon ready (loaded in ~{elapsed}s)")
            return True

        # Periodic heartbeat message every 10 s
        elapsed = (attempt + 1) * _POLL_INTERVAL
        if elapsed % 10 == 0:
            await _emit(f"Still loading signatures… ({elapsed}s elapsed)")

    await _emit(
        f"ClamAV daemon did not become ready within {_TIMEOUT}s. "
        "Check container logs for errors.",
        "error",
    )
    return False
