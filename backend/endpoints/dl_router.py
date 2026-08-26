"""Public download endpoint - token-based, no auth required.

GET  /api/dl/{token}           - download (no password)
POST /api/dl/{token}/auth      - verify password → short-lived bypass token
GET  /api/dl/{token}?bt=xxx    - download with bypass token (never plain password in URL)
"""
from __future__ import annotations

import logging
import mimetypes
import os
import secrets

from fastapi import APIRouter, HTTPException, Query

logger = logging.getLogger(__name__)
from pydantic import BaseModel

from fastapi import Request
from config import BASE_PATH
from utils.paths import is_within_allowed_roots
from handler.auth.passwords import verify_password
from handler.database.download_token_handler import download_token_handler
from handler.database.library_handler import LibraryHandler

_BT_PREFIX = "gd:dl:bt:"   # Redis key: gd:dl:bt:{bypass_token} -> download_token  TTL 60s
_DL_RATE_PREFIX = "gd:dl:rate:"  # Per-IP download rate limit
_AUTH_RATE_PREFIX = "gd:dl:auth:"  # Per-token+IP password attempt rate limit

async def _check_dl_rate(request: Request) -> None:
    """Rate limit downloads: max 20 per IP per 5 minutes."""
    from handler.auth.brute_force import _carry_on_without_redis, _get_redis
    ip = request.client.host if request.client else "unknown"
    # `_get_redis` builds a client rather than connecting, so it never returns
    # anything falsy and the guard that used to stand here never once ran. A
    # Redis that was down surfaced as a 500 on the download instead.
    try:
        r = await _get_redis()
        key = f"{_DL_RATE_PREFIX}{ip}"
        count = await r.incr(key)
        if count == 1:
            await r.expire(key, 300)
    except Exception as exc:
        _carry_on_without_redis("the download rate limit", exc)
        return
    if count > 20:
        raise HTTPException(status_code=429, detail="Too many downloads. Try again in a few minutes.")


async def _check_auth_rate(request: Request, token: str) -> None:
    """Rate limit password attempts: max 5 per token per IP per 5 minutes."""
    from handler.auth.brute_force import _carry_on_without_redis, _get_redis
    ip = request.client.host if request.client else "unknown"
    try:
        r = await _get_redis()
        key = f"{_AUTH_RATE_PREFIX}{token}:{ip}"
        count = await r.incr(key)
        if count == 1:
            await r.expire(key, 300)
    except Exception as exc:
        _carry_on_without_redis("the share-link password rate limit", exc)
        return
    if count > 5:
        raise HTTPException(status_code=429, detail="Too many password attempts. Try again later.")


router = APIRouter(prefix="/api/dl", tags=["download-tokens"])
_lib = LibraryHandler()

_CHUNK = 1024 * 512  # 512 KB


class _AuthRequest(BaseModel):
    password: str


@router.post("/{token}/auth")
async def token_auth(token: str, req: _AuthRequest, request: Request = None):
    """Verify password and return a short-lived single-use bypass token (60 s TTL).

    The bypass token is passed as ?bt= on the subsequent GET - the plain
    password never appears in a URL, browser history or server access log.
    """
    await _check_auth_rate(request, token)
    entry = await download_token_handler.get_by_token(token)
    if not entry:
        raise HTTPException(status_code=404, detail="Download link not found")
    if not download_token_handler.is_valid(entry):
        raise HTTPException(status_code=410, detail="This download link has expired or been exhausted")
    if not entry.password_hash:
        raise HTTPException(status_code=400, detail="This link is not password-protected")
    if not verify_password(req.password, entry.password_hash):
        raise HTTPException(status_code=401, detail="Incorrect password")

    from handler.auth.brute_force import _get_redis
    bt = secrets.token_urlsafe(32)
    r = _get_redis()
    await r.setex(f"{_BT_PREFIX}{bt}", 60, token)
    return {"bypass_token": bt}


@router.get("/{token}/info")
async def token_info(token: str):
    """Return token metadata without serving the file - used by the download page UI.
    Only reveals file info if token is valid (prevents enumeration of expired tokens)."""
    entry = await download_token_handler.get_by_token(token)
    if not entry:
        raise HTTPException(status_code=404, detail="Download link not found")
    valid = download_token_handler.is_valid(entry)
    if not valid:
        return {"valid": False, "password_required": False, "file_name": None, "game_title": None}
    return {
        "valid":             True,
        "password_required": entry.password_hash is not None,
        "file_name":         entry.file_name,
        "game_title":        entry.game_title,
    }


@router.get("/{token}")
async def token_download(token: str, bt: str | None = Query(default=None), request: Request = None):
    await _check_dl_rate(request)
    entry = await download_token_handler.get_by_token(token)
    if not entry:
        raise HTTPException(status_code=404, detail="Download link not found")

    if not download_token_handler.is_valid(entry):
        raise HTTPException(status_code=410, detail="This download link has expired or been exhausted")

    # Password check via short-lived bypass token (issued by POST /{token}/auth)
    if entry.password_hash:
        if not bt:
            raise HTTPException(
                status_code=401,
                detail="Password required",
                headers={"X-Password-Required": "true"},
            )
        from handler.auth.brute_force import _get_redis
        r = _get_redis()
        stored = await r.get(f"{_BT_PREFIX}{bt}")
        if stored != token:
            raise HTTPException(status_code=401, detail="Invalid or expired bypass token")
        await r.delete(f"{_BT_PREFIX}{bt}")  # single-use

    # Resolve file
    f = await _lib.get_file_by_id(entry.file_id)
    if not f or not f.is_available:
        raise HTTPException(status_code=404, detail="File is no longer available")

    abs_path = os.path.join(BASE_PATH, f.file_path)

    # Path traversal guard
    if not is_within_allowed_roots(abs_path):
        raise HTTPException(status_code=403, detail="Access denied")

    if not os.path.exists(abs_path):
        raise HTTPException(status_code=404, detail="File not found on disk")

    file_size = os.path.getsize(abs_path)
    mime_type, _ = mimetypes.guess_type(f.filename)
    mime_type = mime_type or "application/octet-stream"

    from utils.throttle import effective_chunk_size, effective_speed_kbps
    from utils.ranged_file import ranged_file_response
    _speed_kbps = await effective_speed_kbps(None)   # token downloads use global limit only
    _chunk_size = effective_chunk_size(_speed_kbps)
    _token_id = entry.id
    # A limit on how many times a link may be used and the ability to resume a
    # download cannot both be had. Counting on the way out - once the file had
    # gone over in full - is what a resumable link allows, and it does not hold
    # a limit at all: ask for byte nought, then ask for the rest, and the whole
    # file arrives as two requests of which neither took the file, so neither
    # spends a use. A link limited to one download and never expiring was a
    # permanent public address for the file behind it.
    #
    # So a limited link is served whole or not at all, and the use is taken
    # before a byte moves. An unlimited link keeps resuming, and its count is
    # bookkeeping rather than a limit. Which one you get follows from whether
    # you set a limit, and the response says so through Accept-Ranges.
    _limited = entry.max_downloads is not None
    if _limited and not await download_token_handler.reserve_use(_token_id):
        raise HTTPException(status_code=410, detail="This download link has expired or been exhausted")

    async def _settle(moved) -> None:
        if _limited:
            # Taken up front, so what is left here is giving it back when the
            # file did not go over: a link limited to one download must not be
            # spent by a transfer that dropped at four percent.
            if not moved.whole_file:
                try:
                    await download_token_handler.release_use(_token_id)
                except Exception:
                    logger.warning("Failed to release the reserved use of token %s", _token_id)
            return
        # No limit to enforce, so this is only a record of what happened, and it
        # records a download that actually completed. Counting every request
        # that moved bytes would count a dropped transfer; counting every one
        # that ended on the last byte counts a request for a single trailing
        # byte, which is what the last segment of a multi-threaded downloader
        # asks for first.
        if moved.whole_file:
            try:
                await download_token_handler.increment_count(_token_id)
            except Exception:
                logger.warning("Failed to increment download count for token %s", _token_id)

    return ranged_file_response(
        path=abs_path,
        file_size=file_size,
        filename=f.filename,
        media_type=mime_type,
        range_header=request.headers.get("range") if request else None,
        allow_ranges=not _limited,
        speed_kbps=_speed_kbps,
        chunk_size=_chunk_size,
        # A share link has no user behind it, so the link itself is the
        # budget: parallel connections to one link share a cap, and two
        # different links do not compete.
        budget_key=f"token:{_token_id}",
        on_finish=_settle,
    )
