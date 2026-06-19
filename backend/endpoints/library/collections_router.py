"""Collections endpoints.

Prefix: /api/collections

Collections are admin-curated groupings of related games (e.g. a franchise).
They are browsed inside the built-in "collections" index library. A collection
has game-like metadata (cover / description / year range / rating); when no
custom cover is set the UI renders an auto-stack of the member covers, so the
list endpoint also returns the newest member covers, member count, average
rating and year range computed from the members.
"""

from __future__ import annotations

import glob
import logging
import os
import re

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from pydantic import BaseModel
from sqlalchemy import select

from config import RESOURCES_PATH
from decorators.auth import protected_route
from handler.auth.scopes import Scope as Scopes
from handler.database.collection_handler import collection_handler
from handler.database.library_registry_handler import library_registry_handler
from handler.database.session import async_session_factory
from models.gog_game import GogGame
from models.library_game import LibraryGame

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/collections", tags=["collections"])

# Collection covers - raster only (uploaded files never carry script).
_COVER_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
_MAX_COVER_BYTES = 5 * 1024 * 1024  # 5 MB (covers are larger than library icons)

# How many member covers to expose for the auto-stack visual.
_STACK_COVERS = 4


def _slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
    return s or "collection"


def _year_of(d) -> int | None:
    """Best-effort year from a date/datetime object OR a date-ish string (GOG
    stores release dates as free text). None when unknown."""
    if d is None:
        return None
    if hasattr(d, "year"):
        return d.year
    m = re.search(r"\b(\d{4})\b", str(d))
    return int(m.group(1)) if m else None


def _unique(vals) -> list[str]:
    """Order-preserving de-dup, dropping blanks."""
    seen: set = set()
    out: list[str] = []
    for v in vals:
        if v and v not in seen:
            seen.add(v)
            out.append(v)
    return out


def _norm_rating(r) -> float | None:
    """Normalise any rating scale to 0-5. LibraryGame.rating is already 0-5;
    this is defensive for future sources on a 0-10 or 0-100 scale (e.g. ROMs)."""
    if r is None:
        return None
    r = float(r)
    if r <= 5:
        return r
    if r <= 10:
        return r / 2.0
    return r / 20.0


def _collection_brief(c, library_slug: str | None = None) -> dict:
    """Serialise a collection without the (expensive) member aggregation - used
    by create / update / cover responses; the grid endpoint adds member meta."""
    return {
        "slug":        c.slug,
        "name":        c.name,
        "library":     library_slug,
        "description":       c.description,
        "description_short": c.description_short,
        "cover_path":  c.cover_path,
        "start_year":  c.start_year,
        "end_year":    c.end_year,
        "start_year_auto": c.start_year is None,
        "end_year_auto":   c.end_year is None,
        "rating":      c.rating,
        "rating_auto": c.rating is None,
        "hltb_main_s":     c.hltb_main_s,
        "hltb_complete_s": c.hltb_complete_s,
        "hltb_auto":   c.hltb_main_s is None and c.hltb_complete_s is None,
        "sort_order":  c.sort_order,
    }


async def _library_slug_of(coll) -> str | None:
    """The container library slug a collection belongs to (for nav / routing)."""
    if getattr(coll, "library_id", None) is None:
        return None
    libs = await library_registry_handler.get_all()
    return next((l.slug for l in libs if l.id == coll.library_id), None)


async def _serialize_member_games(games: list[LibraryGame]) -> list[dict]:
    """Reuse the library game serialiser (with GOG metadata fallback) for the
    detail view's member list."""
    from endpoints.library.library_router import _game_to_dict
    if not games:
        return []
    gog_ids = {g.gog_game_id for g in games if g.source == "gog" and g.gog_game_id}
    gog_map: dict[int, object] = {}
    if gog_ids:
        async with async_session_factory() as s:
            rows = (await s.execute(select(GogGame).where(GogGame.id.in_(gog_ids)))).scalars().all()
            gog_map = {gg.id: gg for gg in rows}
    return [_game_to_dict(g, gog_game=gog_map.get(g.gog_game_id)) for g in games]


def _agg_meta(coll, *, covers: list[str], ratings: list[float], years: list[int],
             count: int, heroes: list[str] | None = None,
             developers: list[str] | None = None, publishers: list[str] | None = None,
             sources: list[str] | None = None, platforms: dict | None = None,
             library_slug: str | None = None, genres: list[str] | None = None,
             languages: dict | None = None,
             hltb_main_s: int | None = None, hltb_complete_s: int | None = None) -> dict:
    """Merge a collection's stored fields with the member-derived aggregates,
    letting manual overrides win over the computed values. `hltb_main_s` /
    `hltb_complete_s` here are the member averages; a stored override wins."""
    avg = round(sum(ratings) / len(ratings), 1) if ratings else None
    return {
        "slug":          coll.slug,
        "name":          coll.name,
        "library":       library_slug,
        "description":       coll.description,
        "description_short": coll.description_short,
        "cover_path":    coll.cover_path,
        "member_covers": covers[:_STACK_COVERS],
        "member_heroes": (heroes or [])[:6],
        "developers":    developers or [],
        "publishers":    publishers or [],
        "genres":        genres or [],
        "languages":     languages or {},
        "sources":       sources or [],
        "platforms":     platforms or {"windows": False, "mac": False, "linux": False},
        "member_count":  count,
        "rating":        coll.rating if coll.rating is not None else avg,
        "rating_auto":   coll.rating is None,
        "hltb_main_s":     coll.hltb_main_s if coll.hltb_main_s is not None else hltb_main_s,
        "hltb_complete_s": coll.hltb_complete_s if coll.hltb_complete_s is not None else hltb_complete_s,
        "hltb_auto":     coll.hltb_main_s is None and coll.hltb_complete_s is None,
        "start_year":    coll.start_year if coll.start_year is not None else (min(years) if years else None),
        "end_year":      coll.end_year if coll.end_year is not None else (max(years) if years else None),
        "start_year_auto": coll.start_year is None,
        "end_year_auto":   coll.end_year is None,
        "sort_order":    coll.sort_order,
    }


# ── List (grid) ───────────────────────────────────────────────────────────────


@protected_route(router.get, "")
async def list_collections(request: Request, library: str | None = None) -> list[dict]:
    """Collections with member count, newest member covers (for the auto stack),
    average rating and year range. Scoped to one container library when `library`
    (its slug) is given; otherwise every collection across all containers (used
    by the theme store / membership picker)."""
    lib_id: int | None = None
    if library is not None:
        lib = await library_registry_handler.get_by_slug(library)
        if lib is None or lib.kind != "collections":
            return []
        lib_id = lib.id

    colls = await collection_handler.get_for_library(lib_id) if lib_id is not None else await collection_handler.get_all()
    if not colls:
        return []

    # Container slug per collection (for nav / routing).
    all_libs = await library_registry_handler.get_all()
    id_to_slug = {l.id: l.slug for l in all_libs}

    rows = await collection_handler.grid_rows(lib_id)
    # GOG-source members keep most metadata on the GogGame row.
    gog_ids = {r[8] for r in rows if r[7] == "gog" and r[8]}
    gog_map: dict[int, object] = {}
    if gog_ids:
        async with async_session_factory() as s:
            gg = (await s.execute(select(GogGame).where(GogGame.id.in_(gog_ids)))).scalars().all()
            gog_map = {g.id: g for g in gg}

    by_coll: dict[int, list[dict]] = {}
    for (cid, _gid, _title, cover, bg, rating, rd, source, gog_id, dev, pub, ow, om, ol) in rows:
        g = gog_map.get(gog_id) if source == "gog" else None
        by_coll.setdefault(cid, []).append({
            "cover":  cover  or (getattr(g, "cover_path", None) if g else None),
            "hero":   bg     or (getattr(g, "background_path", None) if g else None),
            "rating": rating if rating is not None else (getattr(g, "rating", None) if g else None),
            "date":   rd     or (getattr(g, "release_date", None) if g else None),
            "developer": dev or (getattr(g, "developer", None) if g else None),
            "publisher": pub or (getattr(g, "publisher", None) if g else None),
            "os_windows": bool(ow) or bool(getattr(g, "os_windows", False)) if g else bool(ow),
            "os_mac":     bool(om) or bool(getattr(g, "os_mac", False)) if g else bool(om),
            "os_linux":   bool(ol) or bool(getattr(g, "os_linux", False)) if g else bool(ol),
            "source": source,
        })

    out: list[dict] = []
    for c in colls:
        members = by_coll.get(c.id, [])
        for m in members:
            m["year"] = _year_of(m["date"])
        # Newest first, undated last - for the cover stack. Integer key so dates
        # of any type (date object or GOG string) never crash the comparison.
        ordered = sorted(members, key=lambda m: m["year"] or 0, reverse=True)
        covers  = [m["cover"] for m in ordered if m["cover"]]
        heroes  = [m["hero"] for m in ordered if m["hero"]]
        ratings = [_norm_rating(m["rating"]) for m in members if m["rating"] is not None]
        years   = [m["year"] for m in members if m["year"]]
        out.append(_agg_meta(
            c, covers=covers, heroes=heroes,
            library_slug=id_to_slug.get(c.library_id),
            ratings=[r for r in ratings if r is not None],
            years=years, count=len(members),
            developers=_unique(m["developer"] for m in members),
            publishers=_unique(m["publisher"] for m in members),
            sources=_unique((m["source"] or "").upper() for m in members),
            platforms={
                "windows": any(m["os_windows"] for m in members),
                "mac":     any(m["os_mac"] for m in members),
                "linux":   any(m["os_linux"] for m in members),
            },
        ))
    return out


# ── Membership (per game) - declared before /{slug} so the two-segment path is
# matched unambiguously ───────────────────────────────────────────────────────


class CollectionMembershipBody(BaseModel):
    collections: list[str] = []   # collection slugs this game belongs to


@protected_route(router.get, "/membership/{game_id}", scopes=[Scopes.LIBRARY_READ])
async def get_game_collections(request: Request, game_id: int) -> dict:
    """The collection slugs a game belongs to."""
    colls = await collection_handler.get_collections_for_game(game_id)
    return {"collections": [c.slug for c in colls]}


@protected_route(router.put, "/membership/{game_id}", scopes=[Scopes.LIBRARY_WRITE])
async def set_game_collections(request: Request, game_id: int, body: CollectionMembershipBody) -> dict:
    """Replace the set of collections a game belongs to."""
    all_colls = await collection_handler.get_all()
    slug_to_id = {c.slug: c.id for c in all_colls}
    wanted = [slug_to_id[s] for s in body.collections if s in slug_to_id]

    async with async_session_factory() as s:
        game = await s.get(LibraryGame, game_id)
    if game is None:
        raise HTTPException(status_code=404, detail="Game not found")

    await collection_handler.set_collections_for_game(game_id, wanted)
    kept = {c.slug for c in all_colls if c.id in set(wanted)}
    return {"ok": True, "collections": [s for s in body.collections if s in kept]}


# ── Detail ────────────────────────────────────────────────────────────────────


@protected_route(router.get, "/{slug}")
async def get_collection(request: Request, slug: str) -> dict:
    """A collection's metadata plus its member games (newest first)."""
    coll = await collection_handler.get_by_slug(slug)
    if coll is None:
        raise HTTPException(status_code=404, detail="Collection not found")

    members = await collection_handler.get_members(coll.id)
    games = await _serialize_member_games(members)
    games.sort(key=lambda g: (g.get("release_date") is not None, g.get("release_date") or ""), reverse=True)

    covers  = [g["cover_path"] for g in games if g.get("cover_path")]
    heroes  = [g["background_path"] for g in games if g.get("background_path")]
    ratings = [r for r in (_norm_rating(g.get("rating")) for g in games) if r is not None]
    years: list[int] = []
    for g in games:
        rd = g.get("release_date")
        if rd:
            try:
                years.append(int(str(rd)[:4]))
            except (ValueError, TypeError):
                pass

    # Aggregated quickfacts for the detail "Details" panel (same idea as the grid
    # list-row, plus languages and an average Time to Beat).
    genres: list[str] = []
    languages: dict = {}
    for g in games:
        genres.extend(g.get("genres") or [])
        lg = g.get("languages")
        if isinstance(lg, dict):
            languages.update(lg)
    mains = [g["hltb_main_s"] for g in games if g.get("hltb_main_s")]
    comps = [g["hltb_complete_s"] for g in games if g.get("hltb_complete_s")]

    data = _agg_meta(
        coll, covers=covers, heroes=heroes, ratings=ratings, years=years, count=len(games),
        library_slug=await _library_slug_of(coll),
        developers=_unique(g.get("developer") for g in games),
        publishers=_unique(g.get("publisher") for g in games),
        sources=_unique((g.get("source") or "").upper() for g in games),
        platforms={
            "windows": any(g.get("os_windows") for g in games),
            "mac":     any(g.get("os_mac") for g in games),
            "linux":   any(g.get("os_linux") for g in games),
        },
        genres=_unique(genres), languages=languages,
        hltb_main_s=round(sum(mains) / len(mains)) if mains else None,
        hltb_complete_s=round(sum(comps) / len(comps)) if comps else None,
    )
    data["games"] = games
    return data


# ── Create / update / delete (admin) ──────────────────────────────────────────


class CollectionCreateBody(BaseModel):
    name: str
    library: str                       # container library slug (kind 'collections')
    description: str | None = None


@protected_route(router.post, "", scopes=[Scopes.SETTINGS_WRITE])
async def create_collection(request: Request, body: CollectionCreateBody) -> dict:
    """Create a collection inside a container library (admin)."""
    name = (body.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name is required")
    container = await library_registry_handler.get_by_slug(body.library or "")
    if container is None or container.kind != "collections":
        raise HTTPException(status_code=400, detail="Invalid collection library")
    slug = _slugify(name)
    if await collection_handler.get_by_slug(slug) is not None:
        raise HTTPException(status_code=409, detail="A collection with this name already exists")
    user = getattr(request.state, "user", None)
    coll = await collection_handler.create(
        name=name, slug=slug, library_id=container.id, description=(body.description or None),
        created_by=getattr(user, "id", None),
    )
    return _collection_brief(coll, container.slug)


class CollectionUpdateBody(BaseModel):
    name:        str | None = None
    description: str | None = None
    description_short: str | None = None
    cover_path:  str | None = None   # set null to revert to the auto stack
    start_year:  int | None = None   # null -> auto (min member year)
    end_year:    int | None = None   # null -> auto (max member year)
    rating:      float | None = None  # null -> auto (member average)
    hltb_main_s:     int | None = None  # null -> auto (member average, seconds)
    hltb_complete_s: int | None = None  # null -> auto (member average, seconds)
    sort_order:  int | None = None


@protected_route(router.patch, "/{slug}", scopes=[Scopes.SETTINGS_WRITE])
async def update_collection(request: Request, slug: str, body: CollectionUpdateBody) -> dict:
    """Update collection metadata (admin). Only the fields actually present in
    the request are touched; an explicit null clears that override."""
    provided = body.model_fields_set if hasattr(body, "model_fields_set") else body.__fields_set__
    fields: dict = {}
    for key in ("name", "description", "description_short", "cover_path", "start_year",
                "end_year", "rating", "hltb_main_s", "hltb_complete_s", "sort_order"):
        if key in provided:
            val = getattr(body, key)
            if key == "name":
                val = (val or "").strip() or None
                if val is None:
                    continue  # never blank out the name
            fields[key] = val

    if not fields:
        coll = await collection_handler.get_by_slug(slug)
        if coll is None:
            raise HTTPException(status_code=404, detail="Collection not found")
        return _collection_brief(coll, await _library_slug_of(coll))

    coll = await collection_handler.update(slug, **fields)
    if coll is None:
        raise HTTPException(status_code=404, detail="Collection not found")
    return _collection_brief(coll, await _library_slug_of(coll))


@protected_route(router.delete, "/{slug}", scopes=[Scopes.SETTINGS_WRITE])
async def delete_collection(request: Request, slug: str) -> dict:
    """Delete a collection (admin). Member games are left untouched."""
    ok = await collection_handler.delete(slug)
    if not ok:
        raise HTTPException(status_code=404, detail="Collection not found")
    return {"ok": True}


@protected_route(router.post, "/{slug}/cover", scopes=[Scopes.SETTINGS_WRITE])
async def upload_collection_cover(
    request: Request, slug: str, file: UploadFile = File(...),
) -> dict:
    """Upload a custom cover (PNG, JPG, WEBP, max 5 MB). Overrides the auto stack."""
    coll = await collection_handler.get_by_slug(slug)
    if coll is None:
        raise HTTPException(status_code=404, detail="Collection not found")

    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in _COVER_EXTS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported format. Allowed: {', '.join(sorted(_COVER_EXTS))}",
        )
    content = await file.read()
    if len(content) > _MAX_COVER_BYTES:
        raise HTTPException(status_code=413, detail="Cover too large (max 5 MB)")

    covers_dir = os.path.join(RESOURCES_PATH, "collection-covers")
    os.makedirs(covers_dir, exist_ok=True)
    for old in glob.glob(os.path.join(covers_dir, f"{slug}.*")):
        try:
            os.remove(old)
        except OSError:
            pass
    dest = os.path.join(covers_dir, f"{slug}{ext}")
    with open(dest, "wb") as fh:
        fh.write(content)

    cover_url = f"/resources/collection-covers/{slug}{ext}?v={int(os.path.getmtime(dest))}"
    coll = await collection_handler.update(slug, cover_path=cover_url)
    return _collection_brief(coll, await _library_slug_of(coll))
