"""Global search endpoint - one query, results from every library at once.

The Home view's navbar search calls /api/search/global with a query string;
the response groups hits by source so the UI can render three concise rows:

- emulation : ROMs across all platforms (matches name and fs_name_no_ext)
- gog       : GOG library entries (title) - admin-only, the same scope as
              the Home GOG card
- library   : LibraryGame entries (title) the user has access to

The per-library views (EmulationLibrary, GogLibrary, GamesLibrary) keep
their existing search behaviour. This router serves only the cross-library
case so callers do not have to fan out to three endpoints themselves.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Query, Request
from sqlalchemy import or_, select
from sqlalchemy.orm import selectinload

from decorators.auth import protected_route
from decorators.database import begin_session
from handler.auth.scopes import Scope
from models.gog_game import GogGame
from models.library_game import LibraryGame
from models.rom import Rom
from models.user import Role

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/search", tags=["search"])

_PER_GROUP_LIMIT = 50  # cap each bucket independently so one library cannot
                       # crowd out the others on a generic query like "the".


@protected_route(router.get, "/global", scopes=[Scope.LIBRARY_READ])
async def search_global(
    request: Request,
    q: str = Query("", description="Free-text query, applied to game/ROM titles"),
    limit: int = Query(_PER_GROUP_LIMIT, ge=1, le=200),
) -> dict:
    """Search across emulation ROMs, GOG library and the local game library.

    Results are grouped by source. Empty / very short queries return empty
    buckets to avoid scanning the whole catalog while the user is still
    typing the first character.
    """
    query = (q or "").strip()
    if len(query) < 2:
        return {"q": query, "emulation": [], "gog": [], "library": []}

    user = request.state.user
    is_admin = user is not None and getattr(user, "role", None) == Role.ADMIN

    term = f"%{query}%"

    emulation = await _search_emulation(term, limit)
    library   = await _search_library(term, limit)
    # GOG library is admin-only on the Home view, mirror that here so a
    # non-admin token cannot use the global search to enumerate the admin's
    # private GOG list.
    gog = await _search_gog(term, limit) if is_admin else []

    return {
        "q":         query,
        "emulation": emulation,
        "gog":       gog,
        "library":   library,
    }


@begin_session
async def _search_emulation(term: str, limit: int, *, session=None) -> list[dict]:
    stmt = (
        select(Rom)
        .options(selectinload(Rom.platform))
        .where(
            ~Rom.missing_from_fs,
            or_(Rom.name.ilike(term), Rom.fs_name_no_ext.ilike(term)),
        )
        .order_by(Rom.name.asc(), Rom.fs_name_no_ext.asc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    rows = result.scalars().all()
    return [
        {
            "id":                    rom.id,
            "name":                  rom.name or rom.fs_name_no_ext,
            "cover_path":            rom.cover_path,
            "cover_type":            rom.cover_type,
            "cover_aspect":          rom.cover_aspect,
            "platform_id":           rom.platform_id,
            "platform_slug":         rom.platform.slug if rom.platform else None,
            "platform_fs_slug":      rom.platform.fs_slug if rom.platform else None,
            "platform_name":         rom.platform.name if rom.platform else None,
            # RomPlatform has no cover_aspect column - the per-platform default
            # is configured in the Vue side (3/4 unless rom overrides). Keep
            # the field in the response so the frontend type-check stays happy.
            "platform_cover_aspect": "3/4",
            "release_year":          rom.release_year,
        }
        for rom in rows
    ]


@begin_session
async def _search_library(term: str, limit: int, *, session=None) -> list[dict]:
    stmt = (
        select(LibraryGame)
        .where(LibraryGame.title.ilike(term))
        .order_by(LibraryGame.title.asc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    rows = result.scalars().all()
    return [
        {
            "id":              g.id,
            "title":           g.title,
            "slug":            g.slug,
            "cover_path":      g.cover_path,
            "background_path": g.background_path,
            "source":          g.source,
        }
        for g in rows
    ]


@begin_session
async def _search_gog(term: str, limit: int, *, session=None) -> list[dict]:
    stmt = (
        select(GogGame)
        .where(GogGame.title.ilike(term))
        .order_by(GogGame.title.asc())
        .limit(limit)
    )
    result = await session.execute(stmt)
    rows = result.scalars().all()
    return [
        {
            "id":         g.id,
            "title":      g.title,
            "slug":       g.slug,
            "cover_path": g.cover_path,
            "cover_url":  g.cover_url,
        }
        for g in rows
    ]
