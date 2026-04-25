"""Public download endpoint - token-based, no auth required.

GET  /api/dl/{token}           - download (no password)
POST /api/dl/{token}/auth      - verify password → short-lived bypass token
GET  /api/dl/{token}?bt=xxx    - download with bypass token (never plain password in URL)
"""
from __future__ import annotations

import asyncio
import mimetypes
import os
import secrets

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from fastapi import Request
from config import BASE_PATH
from handler.auth.passwords import verify_password
from handler.database.download_token_handler import download_token_handler
from handler.database.library_handler import LibraryHandler

_BT_PREFIX = "gd:dl:bt:"   # Redis key: gd:dl:bt:{bypass_token} -> download_token  TTL 60s
_DL_RATE_PREFIX = "gd:dl:rate:"  # Per-IP download rate limit
_AUTH_RATE_PREFIX = "gd:dl:auth:"  # Per-token+IP password attempt rate limit

async def _check_dl_rate(request: Request) -> None:
    """Rate limit downloads: max 20 per IP per 5 minutes."""
    from handler.auth.brute_force import _get_redis
    ip = request.client.host if request.client else "unknown"
    r = await _get_redis()
    if not r:
        return
    key = f"{_DL_RATE_PREFIX}{ip}"
    count = await r.incr(key)
    if count == 1:
        await r.expire(key, 300)
    if count > 20:
        raise HTTPException(status_code=429, detail="Too many downloads. Try again in a few minutes.")


async def _check_auth_rate(request: Request, token: str) -> None:
    """Rate limit password attempts: max 5 per token per IP per 5 minutes."""
    from handler.auth.brute_force import _get_redis
    ip = request.client.host if request.client else "unknown"
    r = await _get_redis()
    if not r:
        return
    key = f"{_AUTH_RATE_PREFIX}{token}:{ip}"
    count = await r.incr(key)
    if count == 1:
        await r.expire(key, 300)
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
    _resolved  = os.path.realpath(abs_path)
    _base_real = os.path.realpath(BASE_PATH)
    if not (_resolved == _base_real or _resolved.startswith(_base_real + os.sep)):
        raise HTTPException(status_code=403, detail="Access denied")

    if not os.path.exists(abs_path):
        raise HTTPException(status_code=404, detail="File not found on disk")

    file_size = os.path.getsize(abs_path)
    mime_type, _ = mimetypes.guess_type(f.filename)
    mime_type = mime_type or "application/octet-stream"

    from utils.throttle import effective_chunk_size, effective_speed_kbps, throttle_sleep
    _speed_kbps = await effective_speed_kbps(None)   # token downloads use global limit only
    _chunk_size = effective_chunk_size(_speed_kbps)
    _token_id = entry.id

    async def _stream():
        bytes_sent = 0
        loop = asyncio.get_running_loop()
        try:
            with open(abs_path, "rb") as fh:
                while True:
                    chunk = await loop.run_in_executor(None, fh.read, _chunk_size)
                    if not chunk:
                        break
                    bytes_sent += len(chunk)
                    yield chunk
                    await throttle_sleep(len(chunk), _speed_kbps)
        finally:
            if bytes_sent > 0:
                try:
                    await download_token_handler.increment_count(_token_id)
                except Exception:
                    logger.warning("Failed to increment download count for token %s", _token_id)

    from urllib.parse import quote as _url_quote
    _safe_fn = _url_quote(f.filename, safe="")
    headers = {
        "Content-Disposition": f"attachment; filename*=UTF-8''{_safe_fn}",
        "Content-Length":      str(file_size),
        "Accept-Ranges":       "none",
    }
    return StreamingResponse(_stream(), media_type=mime_type, headers=headers)
