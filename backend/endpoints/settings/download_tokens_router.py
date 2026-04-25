"""Download token management - admin CRUD + file listing."""
from __future__ import annotations

from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from decorators.auth import protected_route
from handler.auth.scopes import Scope
from handler.auth.passwords import hash_password
from handler.database.download_token_handler import download_token_handler
from handler.database.library_handler import LibraryHandler

router = APIRouter(prefix="/api/settings/downloads", tags=["download-tokens"])
_lib = LibraryHandler()


# ── Schemas ───────────────────────────────────────────────────────────────────

class TokenCreate(BaseModel):
    file_id:       int
    expires_in_hours: int | None = None   # None = never expires
    max_downloads: int | None = None      # None = unlimited
    password:      str | None = None      # None = no password
    note:          str | None = None


class TokenOut(BaseModel):
    id:             int
    token:          str
    file_id:        int
    file_name:      str
    game_title:     str | None
    created_by:     str
    created_at:     str
    expires_at:     str | None
    max_downloads:  int | None
    download_count: int
    has_password:   bool
    note:           str | None
    is_active:      bool
    status:         str   # "active" | "expired" | "exhausted" | "revoked"


def _token_status(t) -> str:
    if not t.is_active:
        return "revoked"
    if t.expires_at is not None:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        if t.expires_at < now:
            return "expired"
    if t.max_downloads is not None and t.download_count >= t.max_downloads:
        return "exhausted"
    return "active"


def _token_out(t) -> TokenOut:
    return TokenOut(
        id             = t.id,
        token          = t.token,
        file_id        = t.file_id,
        file_name      = t.file_name,
        game_title     = t.game_title,
        created_by     = t.created_by,
        created_at     = t.created_at.isoformat() if t.created_at else "",
        expires_at     = t.expires_at.isoformat() if t.expires_at else None,
        max_downloads  = t.max_downloads,
        download_count = t.download_count,
        has_password   = t.password_hash is not None,
        note           = t.note,
        is_active      = t.is_active,
        status         = _token_status(t),
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────

@protected_route(router.get, "/tokens", scopes=[Scope.LIBRARY_ADMIN])
async def list_tokens(request: Request) -> list[TokenOut]:
    tokens = await download_token_handler.get_all()
    return [_token_out(t) for t in tokens]


@protected_route(router.post, "/tokens", scopes=[Scope.LIBRARY_ADMIN])
async def create_token(request: Request, data: TokenCreate) -> TokenOut:
    # Resolve file info
    f = await _lib.get_file_by_id(data.file_id)
    if not f:
        raise HTTPException(status_code=404, detail="File not found")

    game = await _lib.get_by_id(f.library_game_id)
    game_title = game.title if game else None

    expires_at = None
    if data.expires_in_hours is not None:
        expires_at = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=data.expires_in_hours)

    pw_hash = hash_password(data.password) if data.password else None

    user = request.state.user
    entry = await download_token_handler.create(
        file_id       = data.file_id,
        file_name     = f.filename,
        game_title    = game_title,
        created_by    = user.username,
        expires_at    = expires_at,
        max_downloads = data.max_downloads,
        password_hash = pw_hash,
        note          = data.note,
    )
    return _token_out(entry)


@protected_route(router.delete, "/tokens/{token_id}", scopes=[Scope.LIBRARY_ADMIN])
async def delete_token(request: Request, token_id: int) -> dict:
    await download_token_handler.delete(token_id)
    return {"ok": True}


@protected_route(router.get, "/tokens/files", scopes=[Scope.LIBRARY_ADMIN])
async def list_files_for_token(request: Request) -> list[dict]:
    """Return a flat list of all library files (id, filename, game_title) for the token create form.
    Uses a single JOIN query instead of N+1 per-game queries."""
    from sqlalchemy import select as sa_select
    from models.library import LibraryGame, LibraryFile
    from handler.database.session import async_session_factory

    async with async_session_factory() as session:
        stmt = (
            sa_select(LibraryFile, LibraryGame.title)
            .join(LibraryGame, LibraryFile.library_game_id == LibraryGame.id)
            .where(LibraryGame.is_active == True, LibraryFile.is_available == True)  # noqa: E712
            .order_by(LibraryGame.title, LibraryFile.filename)
        )
        rows = await session.execute(stmt)
        return [
            {
                "file_id":    f.id,
                "filename":   f.filename,
                "game_title": title,
                "os":         f.os,
                "file_type":  f.file_type,
                "size_bytes": f.size_bytes,
            }
            for f, title in rows.all()
        ]
