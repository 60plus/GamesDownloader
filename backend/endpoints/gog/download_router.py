"""
GOG Download endpoints.

Routes:
  GET    /api/gog/games/{gog_id}/download-options   - available installers + bonus
  POST   /api/gog/downloads                          - queue a download job
  GET    /api/gog/downloads                          - list all jobs
  GET    /api/gog/downloads/{job_id}                 - single job detail
  GET    /api/gog/downloads/{job_id}/progress        - SSE progress stream
  POST   /api/gog/downloads/{job_id}/pause           - pause active download
  POST   /api/gog/downloads/{job_id}/resume          - resume paused download
  DELETE /api/gog/downloads/{job_id}                 - cancel or delete a job
"""

from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from decorators.auth import protected_route
from handler.auth.scopes import Scope
from handler.gog.gog_download_handler import (
    gog_download_handler,
    get_max_parallel,
    set_max_parallel,
)

logger = logging.getLogger(__name__)

download_router = APIRouter(prefix="/api/gog", tags=["gog-downloads"])


def _job_dict(job) -> dict:
    return {
        "id":             job.id,
        "gog_id":         job.gog_id,
        "game_title":     job.game_title,
        "file_name":      job.file_name,
        "file_type":      job.file_type,
        "os_platform":    job.os_platform,
        "language":       job.language,
        "version":        job.version,
        "dest_dir":       job.dest_dir,
        "dest_path":      job.dest_path,
        "status":         job.status,
        "total_size":     job.total_size,
        "downloaded_size": job.downloaded_size,
        "speed_bps":      job.speed_bps,
        "progress_pct":   job.progress_pct,
        "error_msg":       job.error_msg,
        "verify_checksum": job.verify_checksum,
        "checksum":        job.checksum,
        "checksum_status": job.checksum_status,
        "started_at":      job.started_at.isoformat() if job.started_at else None,
        "finished_at":     job.finished_at.isoformat() if job.finished_at else None,
        "created_at":      job.created_at.isoformat() if job.created_at else None,
    }


# ── 1. Get download options ───────────────────────────────────────────────────

@protected_route(download_router.get, "/games/{gog_id}/download-options", scopes=[Scope.DOWNLOADS_READ])
async def get_download_options(request: Request, gog_id: int):
    try:
        options = await gog_download_handler.get_download_options(gog_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Failed to fetch download options for gog_id=%s", gog_id)
        raise HTTPException(status_code=500, detail=f"GOG API error: {e}")
    return options


# ── 1b. Package a downloaded game into one archive per platform ───────────────

@protected_route(download_router.post, "/games/{gog_id}/package", scopes=[Scope.LIBRARY_ADMIN])
async def package_game_files(request: Request, gog_id: int):
    """
    Bundle an already-downloaded GOG game's loose files into a single archive
    per platform (windows/mac/linux). Honours the delete-originals setting.

    Runs in the background because large games can take minutes to repackage;
    the resulting archives appear in the Games Library when done.
    """
    from handler.database.session import async_session_factory
    from handler.gog.gog_sync_handler import canonical_gog_stmt
    from handler.gog.zip_packer import package_game, packable_platforms

    async with async_session_factory() as session:
        result = await session.execute(canonical_gog_stmt(gog_id))
        gg = result.scalars().first()
        if not gg:
            raise HTTPException(status_code=404, detail="Game not found")
        if not gg.is_downloaded:
            raise HTTPException(status_code=400, detail="Game has no downloaded files to package")
        title = gg.title

    # Fast pre-check so the UI can say "nothing to do" instead of a silent no-op
    # (e.g. the game is already packaged, or each platform has a single file).
    platforms = packable_platforms(title)
    if not platforms:
        return {"started": False, "nothing": True}

    async def _run() -> None:
        try:
            summary = await package_game(gog_id, title)
            logger.info("Manual packaging of gog_id=%s done: %s", gog_id, summary)
        except Exception:
            logger.exception("Manual packaging failed for gog_id=%s", gog_id)

    asyncio.create_task(_run())
    return {"started": True, "platforms": platforms}


@protected_route(download_router.get, "/packaging/active", scopes=[Scope.LIBRARY_READ])
async def list_active_packaging(request: Request) -> list:
    """Return packaging jobs still in progress so the download tray can rehydrate
    after a page refresh (WebSocket progress events are lost on reload)."""
    from handler.gog.zip_packer import active_packaging
    return active_packaging()


# ── 2. Start a download ───────────────────────────────────────────────────────

class StartDownloadRequest(BaseModel):
    gog_id: int
    game_title: str
    file_name: str
    file_type: str = "installer"         # installer | bonus
    os_platform: str | None = None
    language: str | None = None
    version: str | None = None
    installer_id: str | None = None
    file_id: str | None = None
    downlink_url: str | None = None      # GOG downlink path/URL (None = not available)
    total_size: int | None = None
    verify_checksum: bool = False
    checksum: str | None = None          # MD5 hash provided by GOG API


@protected_route(download_router.post, "/downloads", scopes=[Scope.DOWNLOADS_WRITE])
async def start_download(request: Request, body: StartDownloadRequest):
    if not body.downlink_url:
        raise HTTPException(
            status_code=400,
            detail="No download link available for this file. "
                   "GOG may not provide a direct downlink for this item."
        )
    try:
        job = await gog_download_handler.create_job(
            gog_id=body.gog_id,
            game_title=body.game_title,
            file_name=body.file_name,
            file_type=body.file_type,
            os_platform=body.os_platform,
            language=body.language,
            version=body.version,
            installer_id=body.installer_id,
            file_id=body.file_id,
            downlink_url=body.downlink_url,
            total_size=body.total_size,
            verify_checksum=body.verify_checksum,
            checksum=body.checksum,
        )
        gog_download_handler.enqueue(job.id)
        return _job_dict(job)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("Failed to create download job")
        raise HTTPException(status_code=500, detail=str(e))


# ── 3. List all jobs ──────────────────────────────────────────────────────────

@protected_route(download_router.get, "/downloads", scopes=[Scope.DOWNLOADS_READ])
async def list_downloads(request: Request):
    jobs = await gog_download_handler.list_jobs()
    return [_job_dict(j) for j in jobs]


# ── 3b. Download config (concurrency) ────────────────────────────────────────
# Must be defined BEFORE /downloads/{job_id} to avoid the path param matching "config"

class DownloadConfigRequest(BaseModel):
    max_parallel: int = Field(..., ge=1, le=20)


@protected_route(download_router.get, "/downloads/config", scopes=[Scope.DOWNLOADS_READ])
async def get_download_config(request: Request):
    """Return current download concurrency setting."""
    return {"max_parallel": get_max_parallel()}


@protected_route(download_router.post, "/downloads/config", scopes=[Scope.DOWNLOADS_WRITE])
async def set_download_config(request: Request, body: DownloadConfigRequest):
    """Set maximum number of simultaneous downloads (1–10)."""
    set_max_parallel(body.max_parallel)
    return {"max_parallel": get_max_parallel()}


# ── 4. Single job ─────────────────────────────────────────────────────────────

@protected_route(download_router.get, "/downloads/{job_id}", scopes=[Scope.DOWNLOADS_READ])
async def get_download(request: Request, job_id: int):
    job = await gog_download_handler.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Download job not found")
    return _job_dict(job)


# ── 5. SSE progress stream ────────────────────────────────────────────────────

@protected_route(download_router.get, "/downloads/{job_id}/progress", scopes=[Scope.DOWNLOADS_READ])
async def download_progress_sse(request: Request, job_id: int):
    """Server-Sent Events stream for live download progress."""

    async def event_stream():
        terminal = {"completed", "failed", "cancelled"}
        while True:
            if await request.is_disconnected():
                break

            job = await gog_download_handler.get_job(job_id)
            if not job:
                yield f"data: {json.dumps({'error': 'not_found'})}\n\n"
                break

            payload = _job_dict(job)
            yield f"data: {json.dumps(payload)}\n\n"

            if job.status in terminal:
                break

            await asyncio.sleep(1.5)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ── 6. Pause ─────────────────────────────────────────────────────────────────

@protected_route(download_router.post, "/downloads/{job_id}/pause", scopes=[Scope.DOWNLOADS_WRITE])
async def pause_download(request: Request, job_id: int):
    """Pause an active download. Progress is preserved for resume."""
    ok = await gog_download_handler.pause_job(job_id)
    if not ok:
        raise HTTPException(status_code=400, detail="Job cannot be paused (not active or not found)")
    return {"ok": True}


# ── 7. Resume ─────────────────────────────────────────────────────────────────

@protected_route(download_router.post, "/downloads/{job_id}/resume", scopes=[Scope.DOWNLOADS_WRITE])
async def resume_download(request: Request, job_id: int):
    """Resume a paused download from where it left off (HTTP Range)."""
    ok = await gog_download_handler.resume_job(job_id)
    if not ok:
        raise HTTPException(status_code=400, detail="Job cannot be resumed (not paused or not found)")
    return {"ok": True}


# ── 8. Cancel / delete a job ─────────────────────────────────────────────────

@protected_route(download_router.delete, "/downloads/{job_id}", scopes=[Scope.DOWNLOADS_WRITE])
async def delete_download(
    request: Request,
    job_id: int,
    action: str = "cancel",   # cancel | delete
):
    """
    action=cancel  → stop the download, mark as cancelled (keeps record)
    action=delete  → remove the record entirely (only for finished jobs)
    """
    if action == "delete":
        ok = await gog_download_handler.delete_job(job_id)
    else:
        ok = await gog_download_handler.cancel_job(job_id)

    if not ok:
        raise HTTPException(status_code=404, detail="Download job not found")
    return {"ok": True}
