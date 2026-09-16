"""ROM source endpoints - browse remote ROM catalogues and download into roms/.

Prefix: /api/rom-sources

Open to any account holding the store permission, not to administrators alone:
that is what lets an uploader fetch their own ROMs, and it is why every route
here declares three permissions rather than one. LIBRARY_UPLOAD and
STORE_ACCESS say who may reach a remote catalogue at all; ROMS_READ is the
emulation permission, and fetching a ROM onto the server is an emulation act -
without naming it, an account with emulation revoked could still pull ROMs
down. The ROM upload route in roms_router declares the same pair for the same
reason.

Permissions are not the whole answer for the download queue. A job belongs to
the account that started it, and the four verbs that stop or destroy one ask
about that as well, in the handler, the way deleting a ROM does. See
handler.library.ownership.

The heavy lifting lives in handler.roms.rom_source_handler; this router is a
thin, paginated surface over it.

IMPORTANT: protected_route always passes `request` first, so every endpoint
function must declare `request: Request` before any path/query/body params.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from decorators.auth import protected_route
from handler.auth.scopes import Scope as Scopes
from handler.library.ownership import assert_can_touch_download
from handler.roms import rom_source_handler as rsh


async def _resolve_usernames(user_ids) -> dict:
    """Map account ids to names, for the owner badge on somebody else's job."""
    from sqlalchemy import select

    from handler.database.session import async_session_factory
    from models.user import User

    ids = {i for i in user_ids if i}
    if not ids:
        return {}
    async with async_session_factory() as session:
        rows = (await session.execute(
            select(User.id, User.username).where(User.id.in_(ids)))).all()
    return {row[0]: row[1] for row in rows}

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/rom-sources", tags=["rom-sources"])

_MAX_PAGE_SIZE = 200


@protected_route(router.get, "", scopes=[Scopes.LIBRARY_UPLOAD, Scopes.STORE_ACCESS, Scopes.ROMS_READ])
async def list_sources(request: Request) -> list[dict]:
    return rsh.list_rom_sources()


@protected_route(router.get, "/{source_id}/platforms", scopes=[Scopes.LIBRARY_UPLOAD, Scopes.STORE_ACCESS, Scopes.ROMS_READ])
async def list_platforms(request: Request, source_id: str) -> list[dict]:
    try:
        return await rsh.get_platforms(source_id)
    except LookupError:
        raise HTTPException(status_code=404, detail="ROM source not found")
    except PermissionError as e:
        raise HTTPException(status_code=409, detail=str(e))


@protected_route(router.get, "/{source_id}/platforms/{fs_slug}/roms", scopes=[Scopes.LIBRARY_UPLOAD, Scopes.STORE_ACCESS, Scopes.ROMS_READ])
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


@protected_route(router.get, "/preview", scopes=[Scopes.LIBRARY_UPLOAD, Scopes.STORE_ACCESS, Scopes.ROMS_READ])
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


@protected_route(router.post, "/import", scopes=[Scopes.LIBRARY_UPLOAD, Scopes.STORE_ACCESS, Scopes.ROMS_READ])
async def import_rom(request: Request, body: ImportBody) -> dict:
    """General primitive behind __GD__.roms.import: fetch one ROM by URL into
    roms/<fs_slug>/. Public, SSRF-guarded; authenticated sources use /download."""
    user = getattr(request.state, "user", None)
    actor = user.username if user else None
    try:
        return await rsh.import_rom(
            body.url, body.fs_slug, body.filename, actor=actor, force=body.force,
            actor_id=getattr(user, "id", None),
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


class DownloadBody(BaseModel):
    entry_ids: list[str]
    # Re-download an entry whose file already exists (design doc 8.5); off by
    # default so a download never silently overwrites a ROM the user already has.
    force: bool = False


@protected_route(router.post, "/{source_id}/download", scopes=[Scopes.LIBRARY_UPLOAD, Scopes.STORE_ACCESS, Scopes.ROMS_READ])
async def download_roms(request: Request, source_id: str, body: DownloadBody) -> dict:
    entry_ids = [e for e in (body.entry_ids or []) if str(e).strip()]
    if not entry_ids:
        raise HTTPException(status_code=400, detail="No entries to download")
    # The name is for the log line; the id is what ends up on the ROM row and can
    # be summed against a quota. Passing only the first is how a fetched ROM came
    # to belong to nobody.
    user = getattr(request.state, "user", None)
    actor = user.username if user else None
    try:
        return await rsh.queue_downloads(
            source_id, entry_ids, actor=actor, force=body.force,
            actor_id=getattr(user, "id", None),
        )
    except LookupError:
        raise HTTPException(status_code=404, detail="ROM source not found")
    except PermissionError as e:
        raise HTTPException(status_code=409, detail=str(e))


@protected_route(router.post, "/{source_id}/refresh", scopes=[Scopes.LIBRARY_UPLOAD, Scopes.STORE_ACCESS, Scopes.ROMS_READ])
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

def _own_job(request: Request, job_id: int):
    """The job, if this caller is allowed to act on it.

    404 before 403 on purpose in one direction only: a job that does not exist
    is not a secret, and a job that does is not confirmed to somebody who may
    not touch it beyond the fact that some job has that number - which they
    could learn by asking for their own. The refusal is the shared one, so a
    caller sees one answer whether the permission or the ownership stopped them.
    """
    job = rsh.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Download not found")
    assert_can_touch_download(request, job)
    return job


@protected_route(router.get, "/downloads", scopes=[Scopes.LIBRARY_UPLOAD, Scopes.STORE_ACCESS, Scopes.ROMS_READ])
async def list_downloads(request: Request) -> dict:
    """Jobs this process still knows about, so a reloaded page finds them again.

    An uploader sees their own. The list used to hand everybody every job on the
    server, which is both somebody else's business and a ready-made list of
    numbers to aim the four routes below at.
    """
    jobs = rsh.list_jobs()
    if Scopes.ROMS_WRITE not in getattr(request.state, "scopes", set()):
        user_id = getattr(getattr(request.state, "user", None), "id", None)
        mine = {j.id for j in rsh.own_jobs(user_id)}
        return {"jobs": [j for j in jobs if j["id"] in mine]}

    # Only for the caller who is being shown OTHER people's transfers. The
    # tray had nothing to say about whose a job was, so an administrator - the
    # one caller who sees them all - read every one of them as their own. For
    # everybody else the list is already narrowed to their own jobs, so a name
    # would be an account name handed over for no purpose.
    #
    # The badge is the only thing in this route that touches the database -
    # the jobs themselves live in this process - so a lookup that fails costs
    # the names and not the tray. Losing the list because a label could not be
    # resolved would be the wrong way round.
    owners = rsh.job_owners()
    try:
        names = await _resolve_usernames(set(owners.values()))
    except Exception:  # noqa: BLE001 - the transfers matter, the labels do not
        logger.debug("Could not resolve who started these downloads", exc_info=True)
        names = {}
    for job in jobs:
        who = names.get(owners.get(job["id"]))
        if who:
            job["started_by"] = who
    return {"jobs": jobs}


@protected_route(router.post, "/downloads/{job_id}/pause", scopes=[Scopes.LIBRARY_UPLOAD, Scopes.STORE_ACCESS, Scopes.ROMS_READ])
async def pause_download(request: Request, job_id: int) -> dict:
    _own_job(request, job_id)
    if not await rsh.pause_job(job_id):
        raise HTTPException(status_code=400, detail="This download cannot be paused")
    return {"ok": True}


@protected_route(router.post, "/downloads/{job_id}/resume", scopes=[Scopes.LIBRARY_UPLOAD, Scopes.STORE_ACCESS, Scopes.ROMS_READ])
async def resume_download(request: Request, job_id: int) -> dict:
    _own_job(request, job_id)
    if not await rsh.resume_job(job_id):
        raise HTTPException(status_code=400, detail="This download is not paused")
    return {"ok": True}


@protected_route(router.post, "/downloads/{job_id}/retry", scopes=[Scopes.LIBRARY_UPLOAD, Scopes.STORE_ACCESS, Scopes.ROMS_READ])
async def retry_download(request: Request, job_id: int) -> dict:
    _own_job(request, job_id)
    if not await rsh.retry_job(job_id):
        raise HTTPException(
            status_code=409,
            detail="This download cannot be retried - it is not finished, or the "
                   "same file is being downloaded already")
    return {"ok": True}


@protected_route(router.delete, "/downloads/{job_id}", scopes=[Scopes.LIBRARY_UPLOAD, Scopes.STORE_ACCESS, Scopes.ROMS_READ])
async def cancel_download(request: Request, job_id: int) -> dict:
    """Stop and delete a running one, or drop a finished one from the list."""
    _own_job(request, job_id)
    if not await rsh.cancel_or_forget_job(job_id):
        raise HTTPException(status_code=404, detail="Download not found")
    return {"ok": True}
