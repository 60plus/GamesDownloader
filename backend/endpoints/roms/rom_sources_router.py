"""ROM source endpoints - browse remote ROM catalogues and download into roms/.

Prefix: /api/rom-sources

Admin-only in v1 (ROM content is sensitive): every endpoint requires the
LIBRARY_ADMIN scope, mirroring the PC Ports restricted store. The heavy lifting
lives in handler.roms.rom_source_handler; this router is a thin, paginated,
admin-gated surface over it.

IMPORTANT: protected_route always passes `request` first, so every endpoint
function must declare `request: Request` before any path/query/body params.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from decorators.auth import protected_route
from handler.auth.scopes import Scope as Scopes
from handler.roms import rom_source_handler as rsh

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/rom-sources", tags=["rom-sources"])

_MAX_PAGE_SIZE = 200


@protected_route(router.get, "", scopes=[Scopes.LIBRARY_ADMIN])
async def list_sources(request: Request) -> list[dict]:
    return rsh.list_rom_sources()


@protected_route(router.get, "/{source_id}/platforms", scopes=[Scopes.LIBRARY_ADMIN])
async def list_platforms(request: Request, source_id: str) -> list[dict]:
    try:
        return await rsh.get_platforms(source_id)
    except LookupError:
        raise HTTPException(status_code=404, detail="ROM source not found")
    except PermissionError as e:
        raise HTTPException(status_code=409, detail=str(e))


@protected_route(router.get, "/{source_id}/platforms/{fs_slug}/roms", scopes=[Scopes.LIBRARY_ADMIN])
async def list_source_roms(
    request: Request,
    source_id: str,
    fs_slug: str,
    page: int = 1,
    page_size: int = 60,
    query: str | None = None,
    region: str | None = None,
    sort: str | None = None,
    collection: str | None = None,
    fmt: str | None = None,
    kind: str | None = None,
) -> dict:
    page = max(1, page)
    page_size = min(max(1, page_size), _MAX_PAGE_SIZE)
    try:
        return await rsh.list_roms(
            source_id, fs_slug, page, page_size, query, region, sort, collection,
            fmt, kind,
        )
    except LookupError:
        raise HTTPException(status_code=404, detail="ROM source not found")
    except PermissionError as e:
        raise HTTPException(status_code=409, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@protected_route(router.get, "/preview", scopes=[Scopes.LIBRARY_ADMIN])
async def preview_source_rom(
    request: Request,
    fs_slug: str,
    title: str | None = None,
    filename: str | None = None,
    size: int | None = None,
    crc: str | None = None,
    md5: str | None = None,
    sha1: str | None = None,
) -> dict:
    """Cover and facts for ONE browsing row, looked up when the user asks.

    Never called for a whole listing: a platform holds thousands of rows and
    each call costs a scraper request.
    """
    return await rsh.preview_entry(
        fs_slug, title=title, filename=filename, size=size,
        crc=crc, md5=md5, sha1=sha1,
    )


class ImportBody(BaseModel):
    url: str
    fs_slug: str
    filename: str
    force: bool = False


@protected_route(router.post, "/import", scopes=[Scopes.LIBRARY_ADMIN])
async def import_rom(request: Request, body: ImportBody) -> dict:
    """General primitive behind __GD__.roms.import: fetch one ROM by URL into
    roms/<fs_slug>/. Public, SSRF-guarded; authenticated sources use /download."""
    actor = (
        request.state.user.username
        if getattr(request.state, "user", None) else None
    )
    try:
        return await rsh.import_rom(
            body.url, body.fs_slug, body.filename, actor=actor, force=body.force
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


class DownloadBody(BaseModel):
    entry_ids: list[str]
    # Re-download an entry whose file already exists (design doc 8.5); off by
    # default so a download never silently overwrites a ROM the user already has.
    force: bool = False


@protected_route(router.post, "/{source_id}/download", scopes=[Scopes.LIBRARY_ADMIN])
async def download_roms(request: Request, source_id: str, body: DownloadBody) -> dict:
    entry_ids = [e for e in (body.entry_ids or []) if str(e).strip()]
    if not entry_ids:
        raise HTTPException(status_code=400, detail="No entries to download")
    actor = (
        request.state.user.username
        if getattr(request.state, "user", None) else None
    )
    try:
        return await rsh.queue_downloads(source_id, entry_ids, actor=actor, force=body.force)
    except LookupError:
        raise HTTPException(status_code=404, detail="ROM source not found")
    except PermissionError as e:
        raise HTTPException(status_code=409, detail=str(e))


@protected_route(router.post, "/{source_id}/refresh", scopes=[Scopes.LIBRARY_ADMIN])
async def refresh_source(request: Request, source_id: str) -> dict:
    """Drop this source's cached listings so the next one is fetched again.

    A listing that failed, or that came back empty while the archive was down,
    is otherwise served from the source's own cache until it expires - which
    reads, from the platform screen, as a source that has nothing in it.
    """
    try:
        return await rsh.refresh_source(source_id)
    except LookupError:
        raise HTTPException(status_code=404, detail="ROM source not found")


# ── Controlling a download in flight ───────────────────────────────────────────
#
# A ROM download used to be a task nobody kept a handle on: it could be started
# and then only watched. These four give the panel the same controls the GOG
# downloads next to it already had. The queue is held in memory, so a restart
# still forgets it - what a restart leaves behind is the .part file, which a
# retry picks up rather than fetching those bytes a second time.

@protected_route(router.get, "/downloads", scopes=[Scopes.LIBRARY_ADMIN])
async def list_downloads(request: Request) -> dict:
    """Jobs this process still knows about, so a reloaded page finds them again."""
    return {"jobs": rsh.list_jobs()}


@protected_route(router.post, "/downloads/{job_id}/pause", scopes=[Scopes.LIBRARY_ADMIN])
async def pause_download(request: Request, job_id: int) -> dict:
    if not await rsh.pause_job(job_id):
        raise HTTPException(status_code=400, detail="This download cannot be paused")
    return {"ok": True}


@protected_route(router.post, "/downloads/{job_id}/resume", scopes=[Scopes.LIBRARY_ADMIN])
async def resume_download(request: Request, job_id: int) -> dict:
    if not await rsh.resume_job(job_id):
        raise HTTPException(status_code=400, detail="This download is not paused")
    return {"ok": True}


@protected_route(router.post, "/downloads/{job_id}/retry", scopes=[Scopes.LIBRARY_ADMIN])
async def retry_download(request: Request, job_id: int) -> dict:
    if not await rsh.retry_job(job_id):
        raise HTTPException(
            status_code=409,
            detail="This download cannot be retried - it is not finished, or the "
                   "same file is being downloaded already")
    return {"ok": True}


@protected_route(router.delete, "/downloads/{job_id}", scopes=[Scopes.LIBRARY_ADMIN])
async def cancel_download(request: Request, job_id: int) -> dict:
    """Stop and delete a running one, or drop a finished one from the list."""
    if not await rsh.cancel_or_forget_job(job_id):
        raise HTTPException(status_code=404, detail="Download not found")
    return {"ok": True}
