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
from sqlalchemy.orm import selectinload, noload

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

    # Everything hidden from the list views is hidden here too, or the navbar
    # becomes the way to enumerate a restricted library: the per-game deny list
    # was already honoured, library membership was not.
    from handler.library.visibility import visibility_for
    vis = await visibility_for(user) if user is not None else None

    emulation = await _search_emulation(term, limit)
    library   = await _search_library(term, limit, vis)
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
    # Same enrichment as /roms/recent so themes can render their rich tiles.
    from endpoints.roms.roms_router import _rom_rating_agg
    return [
        {
            "id":                    rom.id,
            "name":                  rom.name or rom.fs_name_no_ext,
            "cover_path":            rom.cover_path,
            "cover_type":            rom.cover_type,
            "cover_aspect":          rom.cover_aspect,
            "background_path":       rom.background_path,
            "wheel_path":            rom.wheel_path,
            "steamgrid_path":        rom.steamgrid_path,
            "platform_id":           rom.platform_id,
            "platform_slug":         rom.platform.slug if rom.platform else None,
            "platform_fs_slug":      rom.platform.fs_slug if rom.platform else None,
            "platform_name":         rom.platform.name if rom.platform else None,
            # RomPlatform has no cover_aspect column - the per-platform default
            # is configured in the Vue side (3/4 unless rom overrides). Keep
            # the field in the response so the frontend type-check stays happy.
            "platform_cover_aspect": "3/4",
            "release_year":          rom.release_year,
            "fs_size_bytes":         rom.fs_size_bytes,
            "created_at":            rom.created_at.isoformat() if rom.created_at else None,
            "player_count":          rom.player_count,
            "genres":                (rom.genres or [])[:3],
            "rating_agg":            _rom_rating_agg(rom),
        }
        for rom in rows
    ]


@begin_session
async def _search_library(term: str, limit: int, vis=None, *, session=None) -> list[dict]:
    restricted = vis is not None and not vis.unrestricted
    stmt = (
        select(LibraryGame)
        # The result dict never touches g.files, but the relationship is
        # lazy="selectin", so without this every match drags its whole file list
        # in on a second query for nothing. noload leaves it unloaded.
        .options(noload(LibraryGame.files))
        # Unpublished games are hidden from every list view - keep search
        # consistent so an unpublished title cannot be enumerated here.
        .where(LibraryGame.is_active == True,  # noqa: E712
               LibraryGame.title.ilike(term))
        .order_by(LibraryGame.title.asc())
        # Library membership is decided per row rather than in SQL, so ask for
        # headroom and trim after filtering. Otherwise a restricted user's
        # search returns short whenever a hidden title sorts early.
        .limit(limit * 4 if restricted else limit)
    )
    if restricted and vis.denied_game_ids:
        stmt = stmt.where(LibraryGame.id.not_in(vis.denied_game_ids))
    result = await session.execute(stmt)
    rows = result.scalars().all()

    if restricted:
        from handler.library.visibility import membership_map
        rows = vis.filter(rows, await membership_map([g.id for g in rows]))[:limit]
    # GOG-published games keep most columns NULL on the library row and
    # inherit from the GOG entry (same fallback the list views apply) -
    # without it their covers and ratings come back empty here.
    gog_ids = {g.gog_game_id for g in rows if g.gog_game_id}
    gog_map: dict[int, GogGame] = {}
    if gog_ids:
        gres = await session.execute(select(GogGame).where(GogGame.id.in_(gog_ids)))
        gog_map = {gg.id: gg for gg in gres.scalars().all()}
    from endpoints.library.library_router import aggregate_rating, _merged_meta
    out: list[dict] = []
    for g in rows:
        gg = gog_map.get(g.gog_game_id) if g.gog_game_id else None
        rating = g.rating if g.rating is not None else (gg.rating if gg else None)
        release = g.release_date.isoformat() if g.release_date else (gg.release_date if gg else None)
        out.append({
            "id":              g.id,
            "title":           g.title,
            "slug":            g.slug,
            "cover_path":      g.cover_path or (gg and (gg.cover_path or gg.cover_url)) or None,
            "background_path": g.background_path or (gg and (gg.background_path or gg.background_url)) or None,
            "source":          g.source,
            "release_date":    release,
            "rating":          rating,
            "rating_agg":      aggregate_rating(rating, _merged_meta(g, gg)),
        })
    return out


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
    from endpoints.library.library_router import aggregate_rating
    return [
        {
            "id":           g.id,
            "title":        g.title,
            "slug":         g.slug,
            "cover_path":   g.cover_path,
            "cover_url":    g.cover_url,
            "release_date": g.release_date,
            "rating":       g.rating,
            "rating_agg":   aggregate_rating(g.rating, g.meta_ratings),
        }
        for g in rows
    ]
