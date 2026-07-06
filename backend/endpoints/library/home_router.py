"""Storefront home aggregate.

One response feeds a storefront-style home page (hero carousel + rails)
instead of the client pulling the whole library and slicing it in JS:

  GET /api/home/storefront?featured_limit=8&rail_limit=12

  {
    featured:     [tile + screenshots/videos sample]  - hero carousel; a mix
                  of the newest and the top-rated games that have both a hero
                  (background_path) and a clearlogo (logo_path),
    recent_games: [tile],                             - newest first
    top_rated:    [tile],                             - best rating first
    popular:      [tile + downloads],                 - most downloaded
    genres:       [{name, count, covers[<=3]}],       - WHOLE library, by count
    trailer_games:[slim tile + videos[<=1]],          - random sample of every
                  game with a local trailer copy or a valid YouTube video,
    counts:       { games }
  }

The genre and trailer aggregations scan the whole default library (slim
column-only query) rather than the home rails, so a genre added to any game
and a trailer of any game show up - not just those of the rail sample.

Collections and ROM rails intentionally stay on their existing endpoints
(/api/collections is already aggregate, /api/roms/recent exists) - this
router only removes the games-side fan-out.
"""

from __future__ import annotations

import logging
import random

from fastapi import APIRouter, Request

from decorators.auth import protected_route
from handler.auth.scopes import Scope
from handler.database.library_handler import LibraryHandler

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/home", tags=["home"])
_lib = LibraryHandler()


def _row_fb(row, gog_game, field: str, default=None):
    """GOG metadata fallback for the slim home-meta rows (same semantics as
    _game_to_tile's _fb: a NULL library value falls back to the linked GogGame)."""
    val = getattr(row, field, None)
    if val is not None:
        return val
    if gog_game is not None:
        return getattr(gog_game, field, default)
    return default


@protected_route(router.get, "/storefront", scopes=[Scope.LIBRARY_READ])
async def storefront(
    request: Request,
    featured_limit: int = 8,
    rail_limit: int = 12,
    trailer_limit: int = 16,
) -> dict:
    from endpoints.library.library_router import (
        _game_to_tile,
        _gog_fallback_map,
        aggregate_rating,
    )
    from models.user import Role

    featured_limit = max(1, min(featured_limit, 16))
    rail_limit = max(1, min(rail_limit, 48))
    trailer_limit = max(1, min(trailer_limit, 32))

    user = request.state.user
    denied: set[int] = set()
    if user.role != Role.ADMIN:
        denied = await _lib.get_denied_game_ids_for_user(user.id)

    # Over-fetch each rail so per-game denies and the featured hero/logo filter
    # still leave full rows; the featured mix reuses the same two queries.
    fetch = rail_limit * 2 + len(denied)
    recent = await _lib.get_all_active(in_default_only=True, sort="created_desc", limit=fetch)
    pop    = await _lib.get_popular(limit=rail_limit + len(denied))

    # ── Whole-library meta rows (slim, no files/media columns) ──────────────
    # They feed the aggregations below AND the top-rated ranking: the blended
    # star rating (rating + meta_ratings) must see every game, a rating_desc
    # SQL sample would miss games rated only by RAWG/IGDB/Metacritic.
    meta_rows = await _lib.get_home_meta()
    if denied:
        meta_rows = [r for r in meta_rows if r.id not in denied]
    meta_gog = await _gog_fallback_map(meta_rows)

    def _agg_of(r) -> float:
        gg = meta_gog.get(r.gog_game_id)
        # Same merge as the serializers: GOG scores under library-row keys.
        meta = {**(getattr(gg, "meta_ratings", None) or {}), **(r.meta_ratings or {})}
        return aggregate_rating(_row_fb(r, gg, "rating"), meta) or 0.0

    ranked = sorted(((_agg_of(r), r.id) for r in meta_rows), reverse=True)
    top = await _lib.get_by_ids([rid for score, rid in ranked[:fetch] if score > 0])

    if denied:
        recent = [g for g in recent if g.id not in denied]
        pop    = [(g, c) for g, c in pop if g.id not in denied]

    by_id = {g.id: g for g in recent}
    by_id.update({g.id: g for g in top})
    by_id.update({g.id: g for g, _ in pop})
    gog_map = await _gog_fallback_map(by_id.values())

    def tile(g, **extra):
        return {**_game_to_tile(g, gog_map.get(g.gog_game_id), **extra)}

    # Featured: alternate newest / top-rated, keep only games that can carry a
    # hero slide (hero + clearlogo after the GOG metadata fallback).
    featured: list[dict] = []
    seen: set[int] = set()
    queue: list = []
    for pair in zip(recent, top):
        queue.extend(pair)
    queue.extend(recent[len(top):] or top[len(recent):])
    for g in queue:
        if g.id in seen:
            continue
        seen.add(g.id)
        t = tile(g, with_media=True)
        if t["background_path"] and t["logo_path"]:
            featured.append(t)
        if len(featured) >= featured_limit:
            break

    # Genres: count per genre across the library; the 3 collage covers come
    # from the genre's highest-rated games (aggregate rating).
    genre_map: dict[str, dict] = {}
    for r in meta_rows:
        gg = meta_gog.get(r.gog_game_id)
        cover = _row_fb(r, gg, "cover_path")
        rating = _agg_of(r)
        for name in (_row_fb(r, gg, "genres") or []):
            if not name:
                continue
            e = genre_map.setdefault(name, {"count": 0, "picks": []})
            e["count"] += 1
            if cover:
                e["picks"].append((rating, cover))
    genres = [
        {
            "name": name,
            "count": e["count"],
            "covers": [c for _, c in sorted(e["picks"], key=lambda p: p[0], reverse=True)[:3]],
        }
        for name, e in sorted(genre_map.items(), key=lambda kv: kv[1]["count"], reverse=True)
    ][:24]

    # Trailer pool: every game with a local trailer copy or a valid YouTube
    # video, randomly sampled so the shelf rotates across the whole library.
    trailer_pool = []
    for r in meta_rows:
        gg = meta_gog.get(r.gog_game_id)
        videos = _row_fb(r, gg, "videos") or []
        yt = next(
            (v for v in videos
             if isinstance(v, dict) and v.get("provider") == "youtube" and v.get("video_id")),
            None,
        )
        video_path = _row_fb(r, gg, "video_path")
        if not video_path and yt is None:
            continue
        trailer_pool.append({
            "id":                r.id,
            "title":             r.title,
            "description_short": _row_fb(r, gg, "description_short"),
            "cover_path":        _row_fb(r, gg, "cover_path"),
            "background_path":   _row_fb(r, gg, "background_path"),
            "genres":            _row_fb(r, gg, "genres"),
            "rating":            _row_fb(r, gg, "rating"),
            "rating_agg":        _agg_of(r) or None,
            "hltb_main_s":       r.hltb_main_s,
            "video_path":        video_path,
            "videos":            [yt] if yt else [],
        })
    trailer_games = random.sample(trailer_pool, min(len(trailer_pool), trailer_limit))

    return {
        "featured":      featured,
        "recent_games":  [tile(g) for g in recent[:rail_limit]],
        "top_rated":     [tile(g) for g in top[:rail_limit]],
        "popular":       [{**tile(g), "downloads": c} for g, c in pop[:rail_limit]],
        "genres":        genres,
        "trailer_games": trailer_games,
        "counts": {
            "games": len(meta_rows),
        },
    }
