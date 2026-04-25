"""GamesDownloader Library - main router.

Endpoints:
  GET    /library/games                       - list games
  GET    /library/games/{id}                  - game detail
  POST   /library/games                       - create game (admin/uploader)
  PATCH  /library/games/{id}                  - update metadata
  DELETE /library/games/{id}                  - delete game (admin)
  POST   /library/games/publish/{gog_game_id} - publish from GOG library
  POST   /library/scan                        - scan CUSTOM folder
  GET    /library/games/{id}/files            - list files
  POST   /library/games/{id}/files            - add file record
  PATCH  /library/files/{file_id}             - update file (toggle availability etc.)
  DELETE /library/files/{file_id}             - remove file record (admin)
  GET    /library/download/{file_id}          - stream download + record stat
  GET    /library/stats                       - global stats (admin)
  GET    /library/stats/game/{id}             - per-game stats (admin)
  POST   /users/{user_id}/game-access         - set per-game access override (admin)
  DELETE /users/{user_id}/game-access/{game_id} - remove per-game override (admin)
"""

from __future__ import annotations

import logging
import math
import mimetypes
import os
import re
import unicodedata
from pathlib import Path
from typing import Any

import httpx

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from config import BASE_PATH, GAMES_PATH
from decorators.auth import protected_route
from handler.auth.scopes import Scope
from handler.database.library_handler import LibraryHandler
from handler.database.users_handler import UsersHandler
from models.library_file import LibraryFile
from models.library_game import LibraryGame

logger = logging.getLogger(__name__)

library_router = APIRouter(prefix="/library", tags=["library"])
_lib   = LibraryHandler()
_users = UsersHandler()

# ── Helpers ───────────────────────────────────────────────────────────────────


def _sanitize(title: str) -> str:
    """Identical to gog_download_handler.sanitize_title - must stay in sync."""
    t = unicodedata.normalize("NFKD", title)
    t = t.encode("ascii", errors="ignore").decode("ascii")
    t = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", t)
    t = re.sub(r"[_\s]+", " ", t).strip()
    t = t.rstrip(". ")
    return t or "Unknown_Game"


def _slugify(title: str) -> str:
    t = unicodedata.normalize("NFKD", title).lower()
    t = t.encode("ascii", errors="ignore").decode("ascii")
    t = re.sub(r"[^a-z0-9]+", "-", t).strip("-")
    return t



def _abs_path(rel: str) -> str:
    """Resolve file_path (relative to BASE_PATH) to absolute path."""
    return os.path.join(BASE_PATH, rel)


def _rel_path(abs_path: str) -> str:
    """Convert absolute path to path relative to BASE_PATH."""
    return os.path.relpath(abs_path, BASE_PATH)


def _detect_os(folder_name: str) -> str:
    name = folder_name.lower()
    if name in ("windows", "win"):
        return "windows"
    if name in ("mac", "macos", "osx"):
        return "mac"
    if name in ("linux",):
        return "linux"
    return "all"


def _detect_type(folder_name: str) -> str:
    name = folder_name.lower()
    if name in ("extras", "extra", "bonus"):
        return "extra"
    if name in ("dlc",):
        return "dlc"
    return "game"


def _is_game_file(name: str) -> bool:
    return not name.startswith(".") and not name.endswith(".xml")


# Folder names that act as OS/type containers in the OS-first layout
_OS_CONTAINER_NAMES = {"windows", "win", "mac", "macos", "osx", "linux"}
_TYPE_CONTAINER_NAMES = {"extras", "extra", "bonus", "dlc"}
_STRUCTURAL_NAMES = _OS_CONTAINER_NAMES | _TYPE_CONTAINER_NAMES


def _scan_folder_files(
    folder: str,
    game_id: int,
    source: str,
    force_os: str | None = None,
    force_type: str | None = None,
) -> list[LibraryFile]:
    """Recursively scan a game folder and return LibraryFile objects (not yet persisted).

    Supported layouts (both at the same time):
      - Title-first:  CUSTOM/{Title}/{os}/files  → OS detected from subfolder name
      - Flat:         CUSTOM/{Title}/files        → os="all"
      - OS-first:     CUSTOM/{os}/{Title}/files   → OS forced via force_os param
    """
    files: list[LibraryFile] = []
    base = Path(folder)
    if not base.exists():
        return files

    for child in base.iterdir():
        if child.is_dir():
            if force_os is not None:
                # OS-first layout: subfolders inside the game dir may only be
                # type containers (extra/dlc); OS is already known from parent
                os_tag   = force_os
                type_tag = _detect_type(child.name)
            else:
                os_tag   = _detect_os(child.name)
                type_tag = _detect_type(child.name)
            for f in sorted(child.iterdir()):
                if f.is_file() and _is_game_file(f.name):
                    rel = _rel_path(str(f))
                    files.append(LibraryFile(
                        library_game_id=game_id,
                        filename=f.name,
                        display_name=f.name,
                        file_type=force_type or type_tag,
                        os=os_tag,
                        size_bytes=f.stat().st_size,
                        file_path=rel,
                        source=source,
                        is_available=True,
                    ))
        elif child.is_file() and _is_game_file(child.name):
            rel = _rel_path(str(child))
            files.append(LibraryFile(
                library_game_id=game_id,
                filename=child.name,
                display_name=child.name,
                file_type=force_type or "game",
                os=force_os or "all",
                size_bytes=child.stat().st_size,
                file_path=rel,
                source=source,
                is_available=True,
            ))
    return files


def _check_user_can_access(request: Request, game: LibraryGame) -> None:
    """Raise 403 if current user is denied access to this game."""
    user = request.state.user
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    # Admin always can
    from models.user import Role
    if user.role == Role.ADMIN:
        return
    if not game.is_active:
        raise HTTPException(status_code=404, detail="Game not found")


# ── Schemas ───────────────────────────────────────────────────────────────────

class GameCreateBody(BaseModel):
    title: str
    slug: str | None = None
    description: str | None = None
    description_short: str | None = None
    developer: str | None = None
    publisher: str | None = None
    genres: list | None = None
    tags: list | None = None

class GameUpdateBody(BaseModel):
    title: str | None = None
    description: str | None = None
    description_short: str | None = None
    developer: str | None = None
    publisher: str | None = None
    genres: list | None = None
    tags: list | None = None
    features: list | None = None
    languages: dict | None = None
    requirements: dict | None = None
    rating: float | None = None
    meta_ratings: dict | None = None
    release_date: str | None = None
    cover_url: str | None = None
    background_url: str | None = None
    logo_url: str | None = None
    icon_url: str | None = None
    screenshots: list | None = None
    videos: list | None = None
    os_windows: bool | None = None
    os_mac: bool | None = None
    os_linux: bool | None = None
    is_active: bool | None = None

class FileUpdateBody(BaseModel):
    display_name: str | None = None
    file_type: str | None = None
    os: str | None = None
    language: str | None = None
    version: str | None = None
    is_available: bool | None = None

class FileCreateBody(BaseModel):
    filename: str
    display_name: str | None = None
    file_type: str = "game"
    os: str = "all"
    language: str | None = None
    version: str | None = None
    file_path: str
    size_bytes: int | None = None
    source: str = "custom"

class GameAccessBody(BaseModel):
    game_id: int
    access: str  # "deny" | "allow"


def _game_to_dict(game: LibraryGame, owner_username: str | None = None, gog_game=None) -> dict:
    """Convert LibraryGame to API dict.
    For source='gog' games, fallback to GogGame data for any NULL fields
    so we don't duplicate metadata - GOG is the single source of truth.
    """
    g = gog_game  # GogGame object or None

    def _fb(field: str, default=None):
        """Fallback: LibraryGame field → GogGame field → default."""
        val = getattr(game, field, None)
        if val is not None:
            return val
        if g is not None:
            return getattr(g, field, default)
        return default

    rd = _fb("release_date")

    return {
        "id":                game.id,
        "gog_game_id":       game.gog_game_id,
        "source":            game.source,
        "title":             game.title,
        "slug":              game.slug,
        "description":       _fb("description"),
        "description_short": _fb("description_short"),
        "developer":         _fb("developer"),
        "publisher":         _fb("publisher"),
        "release_date":      str(rd) if rd else None,
        "cover_path":        _fb("cover_path"),
        "background_path":   _fb("background_path"),
        "logo_path":         _fb("logo_path"),
        "icon_path":         _fb("icon_path"),
        "genres":            _fb("genres"),
        "tags":              _fb("tags"),
        "features":          _fb("features"),
        "rating":            _fb("rating"),
        "meta_ratings":      _fb("meta_ratings"),
        "os_windows":        _fb("os_windows", False),
        "os_mac":            _fb("os_mac", False),
        "os_linux":          _fb("os_linux", False),
        "languages":         _fb("languages"),
        "requirements":      _fb("requirements"),
        "screenshots":       _fb("screenshots"),
        "videos":            _fb("videos"),
        "hltb_main_s":       game.hltb_main_s,
        "hltb_complete_s":   game.hltb_complete_s,
        "is_active":         game.is_active,
        "published_by":      game.published_by,
        "owner_username":    owner_username,
        "files":             [_file_to_dict(f) for f in game.files],
        "created_at":        game.created_at.isoformat() if game.created_at else None,
        "updated_at":        game.updated_at.isoformat() if game.updated_at else None,
    }


def _file_to_dict(f: LibraryFile) -> dict:
    return {
        "id":           f.id,
        "filename":     f.filename,
        "display_name": f.display_name or f.filename,
        "file_type":    f.file_type,
        "os":           f.os,
        "language":     f.language,
        "version":      f.version,
        "size_bytes":   f.size_bytes,
        "file_path":    f.file_path,
        "checksum_md5": f.checksum_md5,
        "source":       f.source,
        "is_available": f.is_available,
    }


# ── Games - list / detail ─────────────────────────────────────────────────────

@protected_route(library_router.get, "/games", scopes=[Scope.LIBRARY_READ])
async def list_library_games(
    request: Request,
    search: str = "",
    limit: int = 100,
    offset: int = 0,
) -> dict:
    from models.user import Role
    user = request.state.user
    is_admin = user.role == Role.ADMIN

    games = await _lib.get_all_active(search=search or None, limit=limit, offset=offset)
    total = await _lib.count_active(search=search or None)

    # For non-admins, filter out per-game denied games and adjust total accordingly
    if not is_admin:
        denied = await _lib.get_denied_game_ids_for_user(user.id)
        if denied:
            games = [g for g in games if g.id not in denied]
            total = max(0, total - len(denied))

    # Resolve owner usernames for published games
    pub_ids = {g.published_by for g in games if g.published_by}
    from handler.database.session import async_session_factory as _asf
    from models.user import User as _U, Role as _Role
    from sqlalchemy import select as _sel
    # For games with no published_by (FTP/scan), show the first admin as owner
    admin_name = "Admin"
    async with _asf() as _s:
        admin_row = (await _s.execute(
            _sel(_U.username).where(_U.role == _Role.ADMIN).limit(1)
        )).scalar_one_or_none()
        if admin_row:
            admin_name = admin_row
    pub_map: dict[int | None, str] = {None: admin_name}
    if pub_ids:
        async with _asf() as _s:
            rows = (await _s.execute(
                _sel(_U.id, _U.username).where(_U.id.in_(pub_ids))
            )).all()
            pub_map.update({r[0]: r[1] for r in rows})

    # Batch-load GOG games for fallback metadata (source='gog' games)
    from models.gog_game import GogGame as _GG
    gog_ids = {g.gog_game_id for g in games if g.source == 'gog' and g.gog_game_id}
    gog_map: dict[int, object] = {}
    if gog_ids:
        async with _asf() as _s:
            gog_rows = (await _s.execute(
                _sel(_GG).where(_GG.id.in_(gog_ids))
            )).scalars().all()
            gog_map = {gg.id: gg for gg in gog_rows}

    return {
        "items":  [_game_to_dict(g, owner_username=pub_map.get(g.published_by, pub_map[None]),
                                 gog_game=gog_map.get(g.gog_game_id)) for g in games],
        "total":  total,
        "limit":  limit,
        "offset": offset,
    }


@protected_route(library_router.get, "/games/{game_id}", scopes=[Scope.LIBRARY_READ])
async def get_library_game(request: Request, game_id: int) -> dict:
    game = await _lib.get_by_id(game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    _check_user_can_access(request, game)
    # Check per-game access
    from models.user import Role
    user = request.state.user
    if user.role != Role.ADMIN:
        access = await _lib.get_game_access(user.id, game_id)
        if access and access.access == "deny":
            raise HTTPException(status_code=404, detail="Game not found")
    owner_name = None
    if game.published_by:
        from handler.database.session import async_session_factory as _asf
        from models.user import User as _U
        from sqlalchemy import select as _sel
        async with _asf() as _s:
            owner_name = (await _s.execute(_sel(_U.username).where(_U.id == game.published_by))).scalar_one_or_none()
    if not owner_name:
        # FTP/scanned games with no published_by: show first admin as owner
        from handler.database.session import async_session_factory as _asf2
        from models.user import User as _U2, Role as _R2
        from sqlalchemy import select as _sel2
        async with _asf2() as _s2:
            owner_name = (await _s2.execute(_sel2(_U2.username).where(_U2.role == _R2.ADMIN).limit(1))).scalar_one_or_none() or "Admin"
    # Load GOG game for fallback metadata
    gog_game = None
    if game.source == 'gog' and game.gog_game_id:
        from models.gog_game import GogGame as _GG
        async with _asf() as _s:
            gog_game = await _s.get(_GG, game.gog_game_id)
    return _game_to_dict(game, owner_username=owner_name, gog_game=gog_game)


# ── Games - lookup by GOG game ID ─────────────────────────────────────────────

@protected_route(library_router.get, "/games/gog/{gog_game_id}", scopes=[Scope.LIBRARY_READ])
async def get_library_game_by_gog_id(request: Request, gog_game_id: int) -> dict:
    """Return the LibraryGame linked to a specific GOG game (or 404 if not published)."""
    game = await _lib.get_by_gog_game_id(gog_game_id)
    if not game or not game.is_active:
        raise HTTPException(status_code=404, detail="Not published")
    _check_user_can_access(request, game)
    return _game_to_dict(game)


# ── Games - create / update / delete ─────────────────────────────────────────

@protected_route(library_router.post, "/games", scopes=[Scope.LIBRARY_UPLOAD])
async def create_library_game(request: Request, body: GameCreateBody) -> dict:
    base = body.slug or _slugify(body.title)
    slug = base
    n = 1
    while await _lib.get_by_slug(slug):
        slug = f"{base}-{n}"
        n += 1
    game = LibraryGame(
        title=body.title,
        slug=slug,
        description=body.description,
        description_short=body.description_short,
        developer=body.developer,
        publisher=body.publisher,
        genres=body.genres,
        tags=body.tags,
        source="custom",
        published_by=request.state.user.id,
        is_active=True,
    )
    game = await _lib.create(game)
    return _game_to_dict(game)


@protected_route(library_router.patch, "/games/{game_id}", scopes=[Scope.LIBRARY_WRITE])
async def update_library_game(request: Request, game_id: int, body: GameUpdateBody) -> dict:
    game = await _lib.get_by_id(game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    data = body.model_dump(exclude_unset=True)
    # Guard: MySQL DATE column rejects empty string - convert to None
    if "release_date" in data and not data["release_date"]:
        data["release_date"] = None
    # Map URL fields → path fields, download external images to server
    if "cover_url" in data:
        data["cover_path"] = data.pop("cover_url") or None
    if "background_url" in data:
        data["background_path"] = data.pop("background_url") or None
    if "logo_url" in data:
        data["logo_path"] = data.pop("logo_url") or None
    if "icon_url" in data:
        data["icon_path"] = data.pop("icon_url") or None

    # Download external URLs to local server storage
    from handler.library.media_handler import download_all_media
    data = await download_all_media(game.id, data, overwrite=True)

    updated = await _lib.update(game, data)
    return _game_to_dict(updated)


@protected_route(library_router.delete, "/games/{game_id}", scopes=[Scope.LIBRARY_ADMIN])
async def delete_library_game(request: Request, game_id: int) -> dict:
    game = await _lib.get_by_id(game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    await _lib.delete(game)
    return {"ok": True}


# ── Cover / media image search ────────────────────────────────────────────────

from fastapi import Query as _Query

@protected_route(library_router.get, "/games/{game_id}/covers", scopes=[Scope.LIBRARY_WRITE])
async def library_get_cover_options(
    request: Request,
    game_id: int,
    source: str = _Query(default="igdb", description="gog | igdb | steamgriddb | rawg | launchbox | plugins"),
    q: str = _Query(default="", description="Override search query"),
    asset_type: str = _Query(default="grids", description="grids | heroes | logos | icons"),
    animated: str = _Query(default="any", description="any | only | exclude"),
) -> list:
    """Return cover/hero/logo image options for a library game from external sources."""
    game = await _lib.get_by_id(game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    search_term = q or game.title
    results: list = []
    _SGDB_ANIMATED_MIMES = ("video/webm", "image/gif", "image/webp")

    if source == "gog":
        try:
            from handler.library.library_scrape_handler import _abs_url
            _GOG_CATALOG = "https://catalog.gog.com/v1/catalog"
            _GOG_V2 = "https://api.gog.com/v2/games/{gog_id}?locale=en-US"
            _HDRS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) GOGGalaxy/2.0", "Accept": "application/json"}

            # If game was published from GOG, use the linked gog_id for precise lookup
            gog_product_id = None
            if game.gog_game_id:
                from models.gog_game import GogGame
                from handler.database.session import async_session_factory
                async with async_session_factory() as s:
                    gog_game = await s.get(GogGame, game.gog_game_id)
                    if gog_game:
                        gog_product_id = gog_game.gog_id

            async with httpx.AsyncClient(timeout=10, headers=_HDRS) as c:
                if gog_product_id:
                    # Direct lookup by GOG product ID (precise)
                    r = await c.get(_GOG_V2.format(gog_id=gog_product_id))
                    if r.status_code == 200:
                        data = r.json()
                        links = data.get("_links") or {}
                        box_art = (links.get("boxArtImage") or {}).get("href")
                        bg = ((links.get("galaxyBackgroundImage") or {}).get("href")
                              or (links.get("backgroundImage") or {}).get("href"))
                        logo = (links.get("logo") or {}).get("href")
                        t = data.get("_embedded", {}).get("product", {}).get("title", game.title)
                        if box_art:
                            results.append({"url": _abs_url(box_art), "thumb": _abs_url(box_art),
                                            "type": "static", "label": f"{t} - Box Art"})
                        if bg:
                            results.append({"url": _abs_url(bg), "thumb": _abs_url(bg),
                                            "type": "static", "label": f"{t} - Background"})
                        if logo:
                            results.append({"url": _abs_url(logo), "thumb": _abs_url(logo),
                                            "type": "static", "label": f"{t} - Logo"})

                # Also search catalog by title for additional results
                r = await c.get(_GOG_CATALOG, params={
                    "query": search_term, "productType": "in:game,pack",
                    "limit": "10", "locale": "en-US", "order": "desc:score",
                })
                if r.status_code == 200:
                    for p in (r.json().get("products") or []):
                        cover_v = p.get("coverVertical")
                        title = p.get("title", "")
                        if cover_v:
                            url = _abs_url(cover_v)
                            # Skip duplicates from direct lookup
                            if not any(r["url"] == url for r in results):
                                results.append({"url": url, "thumb": url,
                                                "type": "static", "label": f"{title} - Cover"})
        except Exception as exc:
            logger.warning("GOG cover search failed: %s", exc)

    elif source == "igdb":
        try:
            from handler.config.config_handler import config_handler
            client_id     = await config_handler.get("igdb_client_id")
            client_secret = await config_handler.get("igdb_client_secret")
            if not client_id or not client_secret:
                return []
            async with httpx.AsyncClient(timeout=15) as c:
                tr = await c.post("https://id.twitch.tv/oauth2/token", params={
                    "client_id": client_id, "client_secret": client_secret,
                    "grant_type": "client_credentials",
                })
                if tr.status_code != 200:
                    return []
                token = tr.json().get("access_token", "")
                if not token:
                    return []
                headers = {"Client-ID": client_id, "Authorization": f"Bearer {token}"}
                gr = await c.post(
                    "https://api.igdb.com/v4/games",
                    headers=headers,
                    content=f'search "{search_term}"; fields cover.image_id; limit 20;',
                )
                if gr.status_code != 200:
                    return []
                for g in gr.json():
                    cov = g.get("cover")
                    if not cov:
                        continue
                    img_id = cov.get("image_id", "")
                    if not img_id:
                        continue
                    results.append({
                        "url":   f"https://images.igdb.com/igdb/image/upload/t_cover_big_2x/{img_id}.jpg",
                        "thumb": f"https://images.igdb.com/igdb/image/upload/t_cover_small/{img_id}.jpg",
                        "type":  "static",
                        "label": "IGDB Cover",
                    })
        except Exception as exc:
            logger.warning("IGDB cover search failed: %s", exc)

    elif source == "steamgriddb":
        try:
            from handler.config.config_handler import config_handler
            api_key = await config_handler.get("steamgriddb_api_key")
            if not api_key:
                return []
            headers_sgdb = {"Authorization": f"Bearer {api_key}"}
            async with httpx.AsyncClient(timeout=15) as c:
                r = await c.get(
                    f"https://www.steamgriddb.com/api/v2/search/autocomplete/{search_term}",
                    headers=headers_sgdb,
                )
                if r.status_code != 200:
                    return []
                games_list = r.json().get("data", [])
                if not games_list:
                    return []
                sgdb_id = games_list[0]["id"]
                _endpoint_map = {
                    "grids":  (f"https://www.steamgriddb.com/api/v2/grids/game/{sgdb_id}",
                                {"dimensions": "342x482,600x900", "limit": 50}),
                    "heroes": (f"https://www.steamgriddb.com/api/v2/heroes/game/{sgdb_id}",
                                {"limit": 50}),
                    "logos":  (f"https://www.steamgriddb.com/api/v2/logos/game/{sgdb_id}",
                                {"limit": 50}),
                    "icons":  (f"https://www.steamgriddb.com/api/v2/icons/game/{sgdb_id}",
                                {"limit": 50}),
                }
                endpoint_url, base_params = _endpoint_map.get(asset_type, _endpoint_map["grids"])
                types_filter = {"only": "animated", "exclude": "static"}.get(animated, "animated,static")
                r2 = await c.get(endpoint_url, params={**base_params, "types": types_filter}, headers=headers_sgdb)
                if r2.status_code == 200:
                    for item in r2.json().get("data", []):
                        mime  = item.get("mime", "")
                        is_anim = mime in _SGDB_ANIMATED_MIMES
                        if animated == "only" and not is_anim:
                            continue
                        if animated == "exclude" and is_anim:
                            continue
                        dim_label = f"{item.get('width', '?')}×{item.get('height', '?')}"
                        style     = item.get("style", "")
                        results.append({
                            "url":        item["url"],
                            "thumb":      item.get("thumb") or item["url"],
                            "type":       "animated" if is_anim else "static",
                            "label":      dim_label + (f" · {style}" if style else ""),
                            "author":     (item.get("author") or {}).get("name", ""),
                            "asset_type": asset_type,
                        })
        except Exception as exc:
            logger.warning("SteamGridDB search failed: %s", exc)

    elif source == "rawg":
        try:
            from handler.config.config_handler import config_handler
            api_key = await config_handler.get("rawg_api_key")
            if not api_key:
                return []
            async with httpx.AsyncClient(timeout=15) as c:
                r = await c.get(
                    "https://api.rawg.io/api/games",
                    params={"key": api_key, "search": search_term, "page_size": 8},
                )
                if r.status_code != 200:
                    return []
                for item in r.json().get("results", []):
                    bg = item.get("background_image")
                    if not bg:
                        continue
                    results.append({
                        "url": bg, "thumb": bg, "type": "static",
                        "label": item.get("name", ""), "author": "RAWG",
                    })
        except Exception as exc:
            logger.warning("RAWG search failed: %s", exc)

    elif source == "launchbox":
        try:
            from handler.metadata.launchbox_handler import search_candidates, _db_get_images
            candidates = await search_candidates(search_term, None, max_results=5)
            for c in candidates:
                lb_id = c.get("launchbox_id")
                if not lb_id:
                    continue
                name = c.get("name", "")
                images = _db_get_images(str(lb_id))
                for img in images:
                    img_type = img["type"]
                    if img_type in ("Box - Front", "Box - Front - Reconstructed"):
                        results.append({
                            "url": img["url"], "thumb": img["url"],
                            "type": "static", "label": f"{name} - {img_type}",
                        })
                    elif img_type == "Clear Logo":
                        results.append({
                            "url": img["url"], "thumb": img["url"],
                            "type": "static", "label": f"{name} - Clear Logo",
                            "asset_type": "logos",
                        })
        except Exception as exc:
            logger.warning("LaunchBox cover search failed: %s", exc)

    elif source == "plugins":
        search_term = q or game.title
        try:
            from plugins.manager import plugin_manager
            hook_name = {"grids": "metadata_get_covers", "heroes": "metadata_get_heroes",
                         "logos": "metadata_get_logos"}.get(asset_type, "metadata_get_covers")
            hook = getattr(plugin_manager.hook, hook_name, None)
            if hook:
                all_results = hook(query=search_term)
                for provider_results in all_results:
                    if isinstance(provider_results, list):
                        for r in provider_results:
                            pid = (r.get("_source") or "").lower().replace(" ", "")
                            from pathlib import Path
                            from config import PLUGINS_PATH
                            plugin_id = pid
                            if not Path(PLUGINS_PATH, pid).is_dir():
                                for sfx in ["-metadata", "-scraper", "-plugin"]:
                                    if Path(PLUGINS_PATH, pid + sfx).is_dir():
                                        plugin_id = pid + sfx
                                        break
                            r["_sourceIcon"] = f"/api/plugins/{plugin_id}/logo"
                        results.extend(provider_results)
        except Exception as exc:
            logger.warning("Plugin cover search failed: %s", exc)

    return results


# ── Screenshot search for library games ──────────────────────────────────────

@protected_route(library_router.get, "/games/{game_id}/screenshots", scopes=[Scope.LIBRARY_WRITE])
async def library_get_screenshot_options(
    request: Request,
    game_id: int,
    source: str = _Query(default="igdb", description="igdb | rawg | gog | steam | launchbox | all"),
    q: str = _Query(default="", description="Override search query"),
) -> list:
    """Return screenshot options for a library game from external sources."""
    game = await _lib.get_by_id(game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    search_term = q or game.title
    results: list = []

    if source == "igdb":
        try:
            from handler.config.config_handler import config_handler
            client_id     = await config_handler.get("igdb_client_id")
            client_secret = await config_handler.get("igdb_client_secret")
            if not client_id or not client_secret:
                return []
            async with httpx.AsyncClient(timeout=15) as c:
                tr = await c.post("https://id.twitch.tv/oauth2/token", params={
                    "client_id": client_id, "client_secret": client_secret,
                    "grant_type": "client_credentials",
                })
                if tr.status_code != 200:
                    return []
                token = tr.json().get("access_token", "")
                if not token:
                    return []
                headers = {"Client-ID": client_id, "Authorization": f"Bearer {token}"}
                gr = await c.post(
                    "https://api.igdb.com/v4/games",
                    headers=headers,
                    content=f'fields id,name,screenshots.image_id; search "{search_term}"; limit 3;',
                )
                if gr.status_code == 200:
                    for ig_game in gr.json():
                        for ss in (ig_game.get("screenshots") or []):
                            img_id = ss.get("image_id")
                            if img_id:
                                results.append({
                                    "url":    f"https://images.igdb.com/igdb/image/upload/t_1080p/{img_id}.jpg",
                                    "thumb":  f"https://images.igdb.com/igdb/image/upload/t_screenshot_med/{img_id}.jpg",
                                    "type":   "static",
                                    "label":  ig_game.get("name", ""),
                                    "author": "IGDB",
                                })
        except Exception as exc:
            logger.warning("IGDB screenshot search failed: %s", exc)

    elif source == "rawg":
        try:
            from handler.config.config_handler import config_handler
            api_key = await config_handler.get("rawg_api_key")
            if not api_key:
                return []
            async with httpx.AsyncClient(timeout=15) as c:
                sr = await c.get(
                    "https://api.rawg.io/api/games",
                    params={"key": api_key, "search": search_term, "page_size": 5},
                )
                if sr.status_code != 200:
                    return []
                games_list = sr.json().get("results", [])
                if not games_list:
                    return []
                game_slug = games_list[0].get("slug", "")
                if game_slug:
                    ssr = await c.get(
                        f"https://api.rawg.io/api/games/{game_slug}/screenshots",
                        params={"key": api_key},
                    )
                    if ssr.status_code == 200:
                        for ss in ssr.json().get("results", []):
                            if ss.get("image"):
                                results.append({
                                    "url":    ss["image"],
                                    "thumb":  ss["image"],
                                    "type":   "static",
                                    "label":  games_list[0].get("name", ""),
                                    "author": "RAWG",
                                })
        except Exception as exc:
            logger.warning("RAWG screenshot search failed: %s", exc)

    elif source == "gog":
        search_term = q or game.title
        try:
            from handler.library.library_scrape_handler import _abs_url
            _GOG_CATALOG = "https://catalog.gog.com/v1/catalog"
            _GOG_V1 = "https://api.gog.com/products/{gog_id}?expand=screenshots&locale=en-US"
            _HDRS = {"User-Agent": "Mozilla/5.0 GOGGalaxy/2.0", "Accept": "application/json"}
            gog_product_id = None
            if game.gog_game_id:
                from models.gog_game import GogGame
                from handler.database.session import async_session_factory
                async with async_session_factory() as s:
                    gog_game = await s.get(GogGame, game.gog_game_id)
                    if gog_game:
                        gog_product_id = gog_game.gog_id
            if not gog_product_id:
                async with httpx.AsyncClient(timeout=10, headers=_HDRS) as c:
                    r = await c.get(_GOG_CATALOG, params={"query": search_term, "productType": "in:game,pack", "limit": "1", "locale": "en-US", "order": "desc:score"})
                    if r.status_code == 200:
                        products = r.json().get("products", [])
                        if products:
                            gog_product_id = products[0].get("id")
            if gog_product_id:
                async with httpx.AsyncClient(timeout=15, headers=_HDRS) as c:
                    r = await c.get(_GOG_V1.format(gog_id=gog_product_id))
                    if r.status_code == 200:
                        for i, ss in enumerate(r.json().get("screenshots", []) or []):
                            img_id = ss.get("image_id", "")
                            if img_id:
                                url = _abs_url(f"https://images-1.gog-statics.com/{img_id}.jpg" if not img_id.startswith("http") else img_id)
                                results.append({"url": url, "thumb": url, "type": "static", "label": f"Screenshot {i+1}", "author": "GOG"})
        except Exception as exc:
            logger.warning("GOG screenshot search failed: %s", exc)

    elif source == "steam":
        search_term = q or game.title
        try:
            from handler.gog.steam_scraper import search_steam_app, fetch_steam_app_details
            app_id = await search_steam_app(search_term)
            if app_id:
                steam = await fetch_steam_app_details(app_id)
                for i, url in enumerate(steam.get("screenshots", []) if steam else []):
                    results.append({"url": url, "thumb": url, "type": "static", "label": f"Screenshot {i+1}", "author": "Steam"})
        except Exception as exc:
            logger.warning("Steam screenshot search failed: %s", exc)

    elif source == "launchbox":
        search_term = q or game.title
        try:
            from handler.metadata.launchbox_handler import search_candidates, get_lb_screenshots
            candidates = await search_candidates(search_term, None, max_results=3)
            for c in candidates:
                lb_id = c.get("launchbox_id")
                if not lb_id:
                    continue
                for img in get_lb_screenshots(str(lb_id)):
                    results.append({"url": img["url"], "thumb": img["url"], "type": "static", "label": c.get("name", ""), "author": "LaunchBox"})
        except Exception as exc:
            logger.warning("LaunchBox screenshot search failed: %s", exc)

    elif source == "all":
        import asyncio
        search_term = q or game.title
        sub_sources = ["gog", "igdb", "rawg", "steam", "launchbox"]
        tasks = [library_get_screenshot_options(request, game_id, source=s, q=search_term) for s in sub_sources]
        all_results = await asyncio.gather(*tasks, return_exceptions=True)
        source_names = ["GOG", "IGDB", "RAWG", "Steam", "LaunchBox"]
        icons = ["gog.ico", "igdb.ico", "RAWG.ico", "Steam.ico", "launchbox.ico"]
        for i, res in enumerate(all_results):
            if isinstance(res, list):
                for r in res:
                    r["_source"] = source_names[i]
                    r["_sourceIcon"] = icons[i]
                results.extend(res)
        # Plugin screenshots
        try:
            from plugins.manager import plugin_manager
            from pathlib import Path
            from config import PLUGINS_PATH
            all_plugin = plugin_manager.hook.metadata_search_game(query=search_term)
            for provider_results in all_plugin:
                if not isinstance(provider_results, list) or not provider_results:
                    continue
                best = provider_results[0]
                pid = best.get("provider_id", "")
                gid = best.get("provider_game_id", "")
                if not pid or not gid:
                    continue
                game_data_list = plugin_manager.hook.metadata_get_game(provider_game_id=gid)
                for gd in game_data_list:
                    if not isinstance(gd, dict) or gd.get("provider_id") != pid:
                        continue
                    for ss_url in (gd.get("screenshots") or []):
                        plugin_id = pid
                        if not Path(PLUGINS_PATH, pid).is_dir():
                            for sfx in ["-metadata", "-scraper", "-plugin"]:
                                if Path(PLUGINS_PATH, pid + sfx).is_dir():
                                    plugin_id = pid + sfx
                                    break
                        results.append({
                            "url": ss_url, "thumb": ss_url, "type": "static",
                            "label": gd.get("title", ""), "author": pid.upper(),
                            "_source": best.get("name", pid),
                            "_sourceIcon": f"/api/plugins/{plugin_id}/logo",
                        })
                    break
        except Exception as exc:
            logger.warning("Plugin screenshot search failed: %s", exc)

    return results


# ── Video search for library games ────────────────────────────────────────────

@protected_route(library_router.get, "/games/{game_id}/videos", scopes=[Scope.LIBRARY_WRITE])
async def library_get_video_options(
    request: Request,
    game_id: int,
    source: str = _Query(default="igdb", description="igdb | gog | all"),
    q: str = _Query(default="", description="Override search query"),
) -> list:
    """Return trailer/video options for a library game from external sources."""
    game = await _lib.get_by_id(game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    search_term = q or game.title
    results: list = []

    if source == "igdb":
        try:
            from handler.config.config_handler import config_handler
            client_id     = await config_handler.get("igdb_client_id")
            client_secret = await config_handler.get("igdb_client_secret")
            if not client_id or not client_secret:
                return []
            async with httpx.AsyncClient(timeout=15) as c:
                tr = await c.post("https://id.twitch.tv/oauth2/token", params={
                    "client_id": client_id, "client_secret": client_secret,
                    "grant_type": "client_credentials",
                })
                if tr.status_code != 200:
                    return []
                token = tr.json().get("access_token", "")
                if not token:
                    return []
                headers = {"Client-ID": client_id, "Authorization": f"Bearer {token}"}
                gr = await c.post(
                    "https://api.igdb.com/v4/games",
                    headers=headers,
                    content=f'fields id,name,videos.video_id,videos.name; search "{search_term}"; limit 3;',
                )
                if gr.status_code == 200:
                    for ig_game in gr.json():
                        for vid in (ig_game.get("videos") or []):
                            vid_id = vid.get("video_id")
                            if vid_id:
                                results.append({
                                    "video_id": vid_id,
                                    "provider": "youtube",
                                    "thumb":    f"https://img.youtube.com/vi/{vid_id}/hqdefault.jpg",
                                    "label":    vid.get("name") or ig_game.get("name") or "Trailer",
                                    "author":   "IGDB",
                                })
        except Exception as exc:
            logger.warning("IGDB video search failed: %s", exc)

    elif source == "gog":
        try:
            gog_product_id = None
            if game.gog_game_id:
                from models.gog_game import GogGame
                from handler.database.session import async_session_factory
                async with async_session_factory() as s:
                    gog_game = await s.get(GogGame, game.gog_game_id)
                    if gog_game:
                        gog_product_id = gog_game.gog_id
            if not gog_product_id:
                from handler.library.library_scrape_handler import _abs_url
                _GOG_CATALOG = "https://catalog.gog.com/v1/catalog"
                _HDRS = {"User-Agent": "Mozilla/5.0 GOGGalaxy/2.0", "Accept": "application/json"}
                async with httpx.AsyncClient(timeout=10, headers=_HDRS) as c:
                    r = await c.get(_GOG_CATALOG, params={"query": search_term, "productType": "in:game,pack", "limit": "1", "locale": "en-US", "order": "desc:score"})
                    if r.status_code == 200:
                        products = r.json().get("products", [])
                        if products:
                            gog_product_id = products[0].get("id")
            if gog_product_id:
                _GOG_V1 = "https://api.gog.com/products/{gog_id}?expand=videos&locale=en-US"
                _HDRS = {"User-Agent": "Mozilla/5.0 GOGGalaxy/2.0", "Accept": "application/json"}
                async with httpx.AsyncClient(timeout=15, headers=_HDRS) as c:
                    r = await c.get(_GOG_V1.format(gog_id=gog_product_id))
                    if r.status_code == 200:
                        import re
                        for v in (r.json().get("videos") or []):
                            vid_url = v.get("video_url", "")
                            m = re.search(r'(?:youtu\.be/|/embed/|[?&]v=)([a-zA-Z0-9_-]{11})', vid_url)
                            if m:
                                vid_id = m.group(1)
                                results.append({
                                    "video_id": vid_id, "provider": "youtube",
                                    "thumb": f"https://img.youtube.com/vi/{vid_id}/hqdefault.jpg",
                                    "label": "GOG Trailer", "author": "GOG",
                                })
        except Exception as exc:
            logger.warning("GOG video search failed: %s", exc)

    elif source == "all":
        import asyncio
        tasks = [
            library_get_video_options(request, game_id, source="gog", q=search_term),
            library_get_video_options(request, game_id, source="igdb", q=search_term),
        ]
        all_results = await asyncio.gather(*tasks, return_exceptions=True)
        for res in all_results:
            if isinstance(res, list):
                results.extend(res)

    return results


# ── Publish from GOG ──────────────────────────────────────────────────────────

@protected_route(library_router.post, "/games/publish/{gog_game_id}", scopes=[Scope.LIBRARY_ADMIN])
async def publish_from_gog(request: Request, gog_game_id: int) -> dict:
    """Publish a GOG game into the GamesDownloader library.

    Creates (or updates) a LibraryGame and scans the GOG download folder
    for available files.  Existing LibraryFile records are preserved unless
    the file is no longer on disk.
    """
    from handler.database.base_handler import DBBaseHandler
    from models.gog_game import GogGame
    from sqlalchemy import select as sa_select
    from handler.database.session import async_session_factory

    # Fetch GogGame
    async with async_session_factory() as session:
        result = await session.execute(sa_select(GogGame).where(GogGame.id == gog_game_id))
        gog_game = result.scalar_one_or_none()

    if not gog_game:
        raise HTTPException(status_code=404, detail="GOG game not found")

    # Check if already published
    existing = await _lib.get_by_gog_game_id(gog_game_id)

    if existing:
        lib_game = existing
        # Re-activate if previously unpublished; metadata comes from GOG via fallback
        await _lib.update(lib_game, {
            "title":     gog_game.title,
            "is_active": True,
        })
        lib_game = await _lib.get_by_id(lib_game.id)
    else:
        slug = _slugify(gog_game.title)
        if await _lib.get_by_slug(slug):
            slug = f"{slug}-{gog_game_id}"
        # Only store identity + link to GOG; metadata served via fallback from GogGame
        lib_game = LibraryGame(
            gog_game_id=gog_game_id,
            source="gog",
            title=gog_game.title,
            slug=slug,
            os_windows=gog_game.os_windows,
            os_mac=gog_game.os_mac,
            os_linux=gog_game.os_linux,
            is_active=True,
            published_by=gog_game.owner_user_id or request.state.user.id,
        )
        lib_game = await _lib.create(lib_game)

    # Scan GOG folder for files
    gog_folder = os.path.join(GAMES_PATH, "GOG", _sanitize(gog_game.title))
    new_files = _scan_folder_files(gog_folder, lib_game.id, "gog")

    # Get existing file paths to avoid duplicates
    existing_files = await _lib.get_files_for_game(lib_game.id)
    existing_paths = {f.file_path for f in existing_files}

    added = 0
    for f in new_files:
        if f.file_path not in existing_paths:
            await _lib.create_file(f)
            added += 1

    # Mark files no longer on disk as unavailable
    for ef in existing_files:
        if ef.source == "gog" and not os.path.exists(_abs_path(ef.file_path)):
            await _lib.update_file(ef, {"is_available": False})

    lib_game = await _lib.get_by_id(lib_game.id)
    total_files = len(await _lib.get_files_for_game(lib_game.id))
    return {**_game_to_dict(lib_game), "_scanned": added, "_total": total_files}


# ── Unpublish (hide) a game from the library ──────────────────────────────────

@protected_route(library_router.post, "/games/unpublish/{gog_game_id}", scopes=[Scope.LIBRARY_ADMIN])
async def unpublish_gog_game(request: Request, gog_game_id: int) -> dict:
    """Set is_active=False for the LibraryGame linked to this GOG game."""
    game = await _lib.get_by_gog_game_id(gog_game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not in library")
    await _lib.update(game, {"is_active": False})
    return {"ok": True}


# ── Scan CUSTOM folder ────────────────────────────────────────────────────────

@protected_route(library_router.post, "/scan", scopes=[Scope.LIBRARY_ADMIN])
async def scan_custom_library(request: Request) -> dict:
    """Scan /data/games/CUSTOM/ and create LibraryGame entries for new folders.

    Supports two directory layouts simultaneously:

    Title-first (classic):
        CUSTOM/{Title}/                  → game title from folder name
        CUSTOM/{Title}/{os}/files        → OS detected from subfolder
        CUSTOM/{Title}/files             → os="all" (flat)

    OS-first (new):
        CUSTOM/{os}/{Title}/             → OS detected from top folder, title from sub-folder
        CUSTOM/{os}/{Title}/{type}/files → type from innermost folder (extra/dlc)
        CUSTOM/{extra|dlc}/{Title}/files → file_type forced, os="all"

    Games with the same slug from both layouts are merged into one LibraryGame.
    """
    custom_root = Path(GAMES_PATH) / "CUSTOM"
    custom_root.mkdir(parents=True, exist_ok=True)

    created = 0
    updated = 0
    errors: list[str] = []

    # Collect (title, game_dir, force_os, force_type) tuples for all games found
    # using both layout strategies so we can merge by slug.
    pending: dict[str, dict] = {}  # slug → {title, dirs: [(path, force_os, force_type)]}

    for top_dir in sorted(custom_root.iterdir()):
        if not top_dir.is_dir():
            continue

        top_name   = top_dir.name
        top_os     = _detect_os(top_name)
        top_type   = _detect_type(top_name)
        is_os_cont = top_name.lower() in _OS_CONTAINER_NAMES
        is_ty_cont = top_name.lower() in _TYPE_CONTAINER_NAMES

        if is_os_cont or is_ty_cont:
            # ── OS-first layout ───────────────────────────────────────────────
            # top_dir is a container (windows/, mac/, linux/, extras/, dlc/).
            # Its subdirectories are game titles.
            force_os   = top_os   if is_os_cont else None
            force_type = top_type if is_ty_cont else None

            for game_dir in sorted(top_dir.iterdir()):
                if not game_dir.is_dir():
                    continue
                title = game_dir.name
                slug  = _slugify(title)
                if slug not in pending:
                    pending[slug] = {"title": title, "dirs": []}
                pending[slug]["dirs"].append((str(game_dir), force_os, force_type))
        else:
            # ── Title-first layout ────────────────────────────────────────────
            title = top_name
            slug  = _slugify(title)
            if slug not in pending:
                pending[slug] = {"title": title, "dirs": []}
            pending[slug]["dirs"].append((str(top_dir), None, None))

    # Process each unique game slug
    for slug, info in sorted(pending.items()):
        title = info["title"]
        try:
            existing = await _lib.get_by_slug(slug)

            if not existing:
                lib_game = LibraryGame(
                    source="custom",
                    title=title,
                    slug=slug,
                    is_active=True,
                    published_by=request.state.user.id,
                )
                lib_game = await _lib.create(lib_game)
                created += 1
            else:
                lib_game = existing

            # Collect all new files from every directory associated with this slug
            all_new_files: list[LibraryFile] = []
            for game_dir_path, force_os, force_type in info["dirs"]:
                all_new_files.extend(
                    _scan_folder_files(
                        game_dir_path,
                        lib_game.id,
                        "custom",
                        force_os=force_os,
                        force_type=force_type,
                    )
                )

            existing_files = await _lib.get_files_for_game(lib_game.id)
            existing_paths = {f.file_path for f in existing_files}

            for f in all_new_files:
                if f.file_path not in existing_paths:
                    await _lib.create_file(f)

            # Update OS flags on the game record based on discovered files
            all_files = await _lib.get_files_for_game(lib_game.id)
            os_flags: dict[str, bool] = {}
            for f in all_files:
                if f.is_available and f.os in ("windows", "mac", "linux"):
                    os_flags[f"os_{f.os}" if f.os != "mac" else "os_mac"] = True
            # Normalise key: "os_mac" stays, "os_windows"/"os_linux" already correct
            flag_map = {
                "os_windows": any(f.is_available and f.os == "windows" for f in all_files),
                "os_mac":     any(f.is_available and f.os == "mac"     for f in all_files),
                "os_linux":   any(f.is_available and f.os == "linux"   for f in all_files),
            }
            needs_update = {
                k: v for k, v in flag_map.items()
                if v and not getattr(lib_game, k, False)
            }
            if needs_update:
                await _lib.update(lib_game, needs_update)

            # Mark removed files unavailable
            for ef in existing_files:
                if ef.source == "custom" and not os.path.exists(_abs_path(ef.file_path)):
                    await _lib.update_file(ef, {"is_available": False})

            updated += 1

        except Exception as exc:
            logger.exception("Scan error for '%s': %s", title, exc)
            errors.append(f"{title}: {exc}")

    return {"created": created, "updated": updated, "errors": errors}


# ── Scrape metadata ────────────────────────────────────────────────────────────

@protected_route(library_router.post, "/hltb-rescrape", scopes=[Scope.LIBRARY_ADMIN])
async def hltb_rescrape_library(
    request: Request,
    background_tasks: BackgroundTasks,
    force: bool = Query(default=False, description="Rescrape even games that already have HLTB data"),
) -> dict:
    """Bulk-rescrape HowLongToBeat playtime for all Library games."""
    from handler.metadata.hltb_bulk_handler import rescrape_library as _rescrape
    background_tasks.add_task(_rescrape, force)
    return {"ok": True, "message": "HLTB Library rescrape started in background", "force": force}


@protected_route(library_router.post, "/games/{game_id}/scrape", scopes=[Scope.LIBRARY_ADMIN])
async def scrape_library_game_metadata(request: Request, game_id: int) -> dict:
    """Scrape metadata for a library game from GOG public API, Steam, RAWG, IGDB and SRL.

    Searches all sources by game title and fills in missing fields only.
    Does not overwrite existing metadata.
    """
    from handler.library.library_scrape_handler import scrape_library_game
    from handler.database.session import async_session_factory
    from sqlalchemy import select as _sa_select

    async with async_session_factory() as session:
        game = await session.get(LibraryGame, game_id)
        if not game:
            raise HTTPException(status_code=404, detail="Game not found")

        result = await scrape_library_game(game)
        await session.flush()
        await session.commit()

    return {
        "ok":      True,
        "sources": result["sources"],
        "applied": result["applied"],
        "gog_id":  result["gog_id"],
    }


@protected_route(library_router.post, "/games/{game_id}/clear-metadata", scopes=[Scope.LIBRARY_ADMIN])
async def clear_library_game_metadata(request: Request, game_id: int) -> dict:
    """Clear all scraped metadata from a library game.

    Preserves: title, slug, source, is_active, published_by, OS flags, file records.
    Clears: description, ratings, genres, tags, features, screenshots, videos,
            requirements, languages, cover/background/logo paths, developer, publisher,
            release_date.
    """
    from handler.database.session import async_session_factory

    FIELDS_TO_CLEAR = {
        "description":       None,
        "description_short": None,
        "developer":         None,
        "publisher":         None,
        "release_date":      None,
        "genres":            None,
        "tags":              None,
        "features":          None,
        "rating":            None,
        "meta_ratings":      None,
        "screenshots":       None,
        "videos":            None,
        "requirements":      None,
        "languages":         None,
        "cover_path":        None,
        "background_path":   None,
        "logo_path":         None,
        "icon_path":         None,
    }

    async with async_session_factory() as session:
        game = await session.get(LibraryGame, game_id)
        if not game:
            raise HTTPException(status_code=404, detail="Game not found")
        for field, value in FIELDS_TO_CLEAR.items():
            setattr(game, field, value)
        await session.flush()
        await session.commit()

    return {"ok": True}


@protected_route(library_router.post, "/games/refresh-from-gog", scopes=[Scope.LIBRARY_ADMIN])
async def refresh_library_from_gog(request: Request) -> dict:
    """Re-copy metadata from GOG games to their published library entries.
    Only affects library games with source='gog' and a valid gog_game_id.
    """
    from handler.database.session import async_session_factory
    from models.gog_game import GogGame
    from sqlalchemy import select as sa_select

    count = 0
    async with async_session_factory() as session:
        games = (await session.execute(
            sa_select(LibraryGame).where(LibraryGame.source == "gog", LibraryGame.gog_game_id.isnot(None))
        )).scalars().all()

        for lib_game in games:
            gog_game = await session.get(GogGame, lib_game.gog_game_id)
            if not gog_game:
                continue
            lib_game.description       = gog_game.description
            lib_game.description_short  = gog_game.description_short
            lib_game.developer          = gog_game.developer
            lib_game.publisher          = gog_game.publisher
            lib_game.release_date       = gog_game.release_date or None
            lib_game.cover_path         = gog_game.cover_path
            lib_game.background_path    = gog_game.background_path
            lib_game.logo_path          = getattr(gog_game, "logo_path", None)
            lib_game.icon_path          = getattr(gog_game, "icon_path", None)
            lib_game.genres             = gog_game.genres
            lib_game.tags               = gog_game.tags
            lib_game.features           = gog_game.features
            lib_game.rating             = gog_game.rating
            lib_game.meta_ratings       = gog_game.meta_ratings
            lib_game.os_windows         = gog_game.os_windows
            lib_game.os_mac             = gog_game.os_mac
            lib_game.os_linux           = gog_game.os_linux
            lib_game.languages          = gog_game.languages
            lib_game.requirements        = gog_game.requirements
            lib_game.screenshots         = gog_game.screenshots
            lib_game.videos              = gog_game.videos
            count += 1

        await session.commit()

    return {"ok": True, "refreshed": count}


@protected_route(library_router.delete, "/metadata", scopes=[Scope.LIBRARY_ADMIN])
async def clear_all_library_metadata(request: Request) -> dict:
    """Clear all scraped metadata from ALL library games."""
    from handler.database.session import async_session_factory
    from sqlalchemy import update

    FIELDS_TO_CLEAR = {
        "description": None, "description_short": None,
        "developer": None, "publisher": None, "release_date": None,
        "genres": None, "tags": None, "features": None,
        "rating": None, "meta_ratings": None,
        "screenshots": None, "videos": None, "requirements": None, "languages": None,
        "cover_path": None, "background_path": None, "logo_path": None, "icon_path": None,
    }

    async with async_session_factory() as session:
        result = await session.execute(
            update(LibraryGame).values(**FIELDS_TO_CLEAR)
        )
        await session.commit()

    return {"ok": True, "cleared": result.rowcount}


@protected_route(library_router.get, "/games/{game_id}/meta-sources", scopes=[Scope.LIBRARY_READ])
async def library_game_meta_sources(
    request: Request,
    game_id: int,
    source: str = Query(default="rawg", description="gog | rawg | rawg-detail | igdb | steam"),
    q: str = Query(default="", description="Override search query or rawg slug/id"),
) -> dict:
    """Fetch metadata from external sources for a library game (used by Edit Metadata panel)."""
    from handler.database.session import async_session_factory

    async with async_session_factory() as session:
        game = await session.get(LibraryGame, game_id)
        if not game:
            raise HTTPException(status_code=404, detail="Game not found")

    search_term = q or game.title or ""
    result: dict = {"source": source, "found": False}

    # ── GOG public catalog (no auth) ──────────────────────────────────────────
    if source == "gog":
        from handler.library.library_scrape_handler import (
            _HDRS, _abs_url,
            _search_gog_catalog, _fetch_gog_v1, _fetch_gog_v2, _fetch_gog_rating,
        )
        import asyncio as _aio
        try:
            async with httpx.AsyncClient(headers=_HDRS, follow_redirects=True, timeout=20) as c:
                # Use linked gog_id if game was published from GOG
                gog_id = None
                if game.gog_game_id:
                    from models.gog_game import GogGame
                    gog_game = await session.get(GogGame, game.gog_game_id)
                    if gog_game:
                        gog_id = gog_game.gog_id
                if not gog_id:
                    gog_id = await _search_gog_catalog(search_term, c)
                if not gog_id:
                    return {"source": "gog", "found": False, "error": "No GOG match found for this title"}
                v1, v2, rating = await _aio.gather(
                    _fetch_gog_v1(gog_id, c),
                    _fetch_gog_v2(gog_id, c),
                    _fetch_gog_rating(gog_id, c),
                    return_exceptions=True,
                )
                v1     = v1     if not isinstance(v1,     Exception) else {}
                v2     = v2     if not isinstance(v2,     Exception) else {}
                rating = rating if not isinstance(rating, Exception) else None

                desc_data = v1.get("description") or {}
                if isinstance(desc_data, dict):
                    full_desc  = desc_data.get("full")  or ""
                    short_desc = desc_data.get("short") or ""
                elif isinstance(desc_data, str):
                    full_desc  = desc_data
                    short_desc = ""
                else:
                    full_desc = short_desc = ""

                embedded = v2.get("_embedded") or {}
                devs     = embedded.get("developers") or []
                developer = ", ".join(d["name"] for d in devs if isinstance(d, dict) and d.get("name"))
                pub_data  = embedded.get("publisher") or {}
                publisher = pub_data.get("name", "") if isinstance(pub_data, dict) else ""
                all_tags  = embedded.get("tags") or []
                genres    = [t["name"] for t in all_tags
                             if isinstance(t, dict) and t.get("type") == "genre" and t.get("name")]

                links  = v2.get("_links") or {}
                images = v1.get("images")  or {}
                cover  = ((links.get("boxArtImage") or {}).get("href")
                          or images.get("coverLarge") or images.get("cover") or "")
                cover  = _abs_url(str(cover)) if cover else ""

                release = ""
                rd = v1.get("release_date")
                if rd:
                    if isinstance(rd, dict):
                        release = (rd.get("date") or "")[:10]
                    else:
                        release = str(rd)[:10]

                gog_rating = float(rating) if rating is not None else None

                compat = v1.get("content_system_compatibility") or {}
                raw_langs = v1.get("languages") or {}
                result.update({
                    "found":             True,
                    "gog_id":            gog_id,
                    "name":              v2.get("title") or v1.get("title") or search_term,
                    "description":       full_desc,
                    "description_short": short_desc,
                    "developer":         developer,
                    "publisher":         publisher,
                    "release_date":      release,
                    "genres":            genres,
                    "rating":            gog_rating,
                    "cover_url":         cover,
                    "os_windows":        bool(compat.get("windows")),
                    "os_mac":            bool(compat.get("osx")),
                    "os_linux":          bool(compat.get("linux")),
                    "languages":         raw_langs if isinstance(raw_langs, dict) else {},
                })
        except Exception as exc:
            result["error"] = str(exc)

    # ── RAWG search (returns candidates list) ─────────────────────────────────
    elif source == "rawg":
        try:
            from handler.config.config_handler import config_handler
            api_key = await config_handler.get("rawg_api_key")
            if not api_key:
                return {"source": "rawg", "found": False, "error": "RAWG API key not configured"}
            async with httpx.AsyncClient(timeout=20) as c:
                sr = await c.get(
                    "https://api.rawg.io/api/games",
                    params={"key": api_key, "search": search_term, "page_size": 5},
                )
                if sr.status_code != 200:
                    return {"source": "rawg", "found": False, "error": f"RAWG search returned {sr.status_code}"}
                items = sr.json().get("results", [])
                if not items:
                    return {"source": "rawg", "found": False, "error": "No results found"}
                candidates = [
                    {"id": i.get("id"), "slug": i.get("slug", ""), "name": i.get("name", ""),
                     "released": i.get("released", ""), "background_image": i.get("background_image", ""),
                     "rating": i.get("rating")}
                    for i in items
                ]
                result["found"] = True
                result["candidates"] = candidates
        except Exception as exc:
            result["error"] = str(exc)

    # ── RAWG detail fetch (q = slug or numeric id) ────────────────────────────
    elif source == "rawg-detail":
        try:
            from handler.config.config_handler import config_handler
            api_key = await config_handler.get("rawg_api_key")
            if not api_key:
                return {"source": "rawg-detail", "found": False, "error": "RAWG API key not configured"}
            async with httpx.AsyncClient(timeout=20) as c:
                dr = await c.get(f"https://api.rawg.io/api/games/{q}", params={"key": api_key})
                if dr.status_code != 200:
                    return {"source": "rawg-detail", "found": False}
                d = dr.json()
                requirements: dict = {}
                for pdata in d.get("platforms", []):
                    pname = (pdata.get("platform") or {}).get("name", "")
                    reqs  = pdata.get("requirements") or {}
                    if reqs and ("minimum" in reqs or "recommended" in reqs):
                        requirements[pname] = reqs
                developers = [c_i.get("name", "") for c_i in d.get("developers", []) if isinstance(c_i, dict)]
                publishers = [c_i.get("name", "") for c_i in d.get("publishers", []) if isinstance(c_i, dict)]
                platforms  = [p.get("platform", {}).get("slug", "") for p in d.get("platforms", []) if isinstance(p, dict)]
                result.update({
                    "found":             True,
                    "name":              d.get("name", ""),
                    "description":       d.get("description_raw") or d.get("description") or "",
                    "description_short": "",
                    "cover_url":         d.get("background_image") or "",
                    "developer":         ", ".join(developers),
                    "publisher":         ", ".join(publishers),
                    "release_date":      d.get("released") or "",
                    "rating":            (d.get("rating") or 0) * 2,
                    "genres":            [g.get("name", "") for g in d.get("genres", []) if isinstance(g, dict)],
                    "requirements":      requirements,
                    "os_windows":        any("pc" in p or "windows" in p for p in platforms),
                    "os_mac":            any("mac" in p for p in platforms),
                    "os_linux":          any("linux" in p for p in platforms),
                    "languages":         {},
                })
        except Exception as exc:
            result["error"] = str(exc)

    # ── IGDB ─────────────────────────────────────────────────────────────────
    elif source == "igdb":
        try:
            from handler.config.config_handler import config_handler
            client_id     = await config_handler.get("igdb_client_id")
            client_secret = await config_handler.get("igdb_client_secret")
            if not client_id or not client_secret:
                return {"source": "igdb", "found": False, "error": "IGDB keys not configured"}
            safe_q = re.sub(r'["\';]', '', search_term)[:128]
            async with httpx.AsyncClient(timeout=20) as c:
                tr = await c.post("https://id.twitch.tv/oauth2/token", params={
                    "client_id": client_id, "client_secret": client_secret,
                    "grant_type": "client_credentials",
                })
                if tr.status_code != 200:
                    return {"source": "igdb", "found": False, "error": "Twitch auth failed"}
                token = tr.json().get("access_token", "")
                if not token:
                    return {"source": "igdb", "found": False, "error": "No token"}
                gr = await c.post(
                    "https://api.igdb.com/v4/games",
                    headers={"Client-ID": client_id, "Authorization": f"Bearer {token}"},
                    content=(
                        f'fields id,name,summary,storyline,cover.image_id,'
                        f'involved_companies.company.name,involved_companies.developer,involved_companies.publisher,'
                        f'genres.name,first_release_date,total_rating,aggregated_rating;'
                        f' search "{safe_q}"; limit 5;'
                    ),
                )
                if gr.status_code != 200:
                    return {"source": "igdb", "found": False, "error": f"IGDB returned {gr.status_code}"}
                igdb_games = gr.json()
                if not igdb_games:
                    return {"source": "igdb", "found": False, "error": "No results"}
                candidates = []
                for ig in igdb_games:
                    cov     = ig.get("cover") or {}
                    img_id  = cov.get("image_id")
                    cov_url = f"https://images.igdb.com/igdb/image/upload/t_cover_big/{img_id}.jpg" if img_id else ""
                    devs_ig = [ic["company"]["name"] for ic in ig.get("involved_companies", [])
                               if isinstance(ic, dict) and ic.get("developer") and isinstance(ic.get("company"), dict)]
                    pubs_ig = [ic["company"]["name"] for ic in ig.get("involved_companies", [])
                               if isinstance(ic, dict) and ic.get("publisher") and isinstance(ic.get("company"), dict)]
                    genres  = [g["name"] for g in ig.get("genres", []) if isinstance(g, dict)]
                    rel_ts  = ig.get("first_release_date")
                    rel_str = ""
                    if rel_ts:
                        from datetime import datetime, timezone
                        rel_str = datetime.fromtimestamp(rel_ts, tz=timezone.utc).strftime("%Y-%m-%d")
                    candidates.append({
                        "id":                ig.get("id"),
                        "name":              ig.get("name", ""),
                        "summary":           ig.get("summary", ""),
                        "description":       ig.get("storyline") or ig.get("summary") or "",
                        "description_short": ig.get("summary") or "",
                        "cover_url":         cov_url,
                        "developer":         ", ".join(devs_ig),
                        "publisher":         ", ".join(pubs_ig),
                        "release_date":      rel_str,
                        "genres":            genres,
                        "rating":            ig.get("total_rating") or ig.get("aggregated_rating"),
                        "os_windows":        False,
                        "os_mac":            False,
                        "os_linux":          False,
                        "languages":         {},
                    })
                result["found"] = True
                result["candidates"] = candidates
        except Exception as exc:
            result["error"] = str(exc)

    # ── Steam ────────────────────────────────────────────────────────────────
    elif source == "steam":
        try:
            from handler.gog.steam_scraper import search_steam_app, fetch_steam_app_details, parse_steam_app_id
            # If q looks like a Steam App ID or URL, skip title search
            app_id: int | None = parse_steam_app_id(q) if q else None
            if not app_id:
                app_id = await search_steam_app(search_term)
            if not app_id:
                return {"source": "steam", "found": False, "error": "No Steam match found - try entering the Steam App ID or URL directly"}
            steam = await fetch_steam_app_details(app_id)
            if not steam:
                return {"source": "steam", "found": False, "error": f"Steam App {app_id} not found or API error"}
            result.update({
                "found":             True,
                "app_id":            app_id,
                "name":              steam.get("name") or search_term,
                "description":       steam.get("description", ""),
                "description_short": steam.get("description_short", ""),
                "developer":         steam.get("developer", ""),
                "publisher":         steam.get("publisher", ""),
                "release_date":      steam.get("release_date", ""),
                "genres":            steam.get("genres", []),
                "rating":            steam.get("rating"),
                "requirements":      steam.get("requirements", {}),
                "os_windows":        bool(steam.get("os_windows")),
                "os_mac":            bool(steam.get("os_mac")),
                "os_linux":          bool(steam.get("os_linux")),
                "languages":         steam.get("languages", {}),
            })
        except Exception as exc:
            result["error"] = str(exc)

    return result


# ── Files ─────────────────────────────────────────────────────────────────────

@protected_route(library_router.get, "/games/{game_id}/files", scopes=[Scope.LIBRARY_READ])
async def list_game_files(request: Request, game_id: int) -> list:
    game = await _lib.get_by_id(game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    files = await _lib.get_files_for_game(game_id)
    return [_file_to_dict(f) for f in files]


@protected_route(library_router.post, "/games/{game_id}/files", scopes=[Scope.LIBRARY_ADMIN])
async def add_game_file(request: Request, game_id: int, body: FileCreateBody) -> dict:
    game = await _lib.get_by_id(game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    # Validate file_path to prevent path traversal
    if body.file_path and (".." in body.file_path or body.file_path.startswith(("/", "\\"))):
        raise HTTPException(status_code=400, detail="Invalid file_path")
    f = LibraryFile(
        library_game_id=game_id,
        filename=body.filename,
        display_name=body.display_name,
        file_type=body.file_type,
        os=body.os,
        language=body.language,
        version=body.version,
        size_bytes=body.size_bytes,
        file_path=body.file_path,
        source=body.source,
        is_available=True,
    )
    created = await _lib.create_file(f)
    return _file_to_dict(created)


@protected_route(library_router.patch, "/files/{file_id}", scopes=[Scope.LIBRARY_ADMIN])
async def update_library_file(request: Request, file_id: int, body: FileUpdateBody) -> dict:
    f = await _lib.get_file_by_id(file_id)
    if not f:
        raise HTTPException(status_code=404, detail="File not found")
    updated = await _lib.update_file(f, body.model_dump(exclude_unset=True))
    return _file_to_dict(updated)


@protected_route(library_router.delete, "/files/{file_id}", scopes=[Scope.LIBRARY_ADMIN])
async def delete_library_file(request: Request, file_id: int) -> dict:
    f = await _lib.get_file_by_id(file_id)
    if not f:
        raise HTTPException(status_code=404, detail="File not found")
    await _lib.delete_file(f)
    return {"ok": True}


# ── Download (streaming) ──────────────────────────────────────────────────────

@protected_route(library_router.get, "/download/{file_id}", scopes=[Scope.LIBRARY_DOWNLOAD])
async def download_file(request: Request, file_id: int):
    f = await _lib.get_file_by_id(file_id)
    if not f or not f.is_available:
        raise HTTPException(status_code=404, detail="File not available")

    # Per-game access check
    from models.user import Role
    user = request.state.user
    if user.role != Role.ADMIN:
        access = await _lib.get_game_access(user.id, f.library_game_id)
        if access and access.access == "deny":
            raise HTTPException(status_code=403, detail="Access denied")
        game = await _lib.get_by_id(f.library_game_id)
        if not game or not game.is_active:
            raise HTTPException(status_code=404, detail="File not available")

    abs_path = _abs_path(f.file_path)

    # #7 - Security: ensure resolved path stays within BASE_PATH
    # (prevents symlink traversal or crafted file_path escaping the data dir)
    _resolved  = os.path.realpath(abs_path)
    _base_real = os.path.realpath(BASE_PATH)
    if not (_resolved == _base_real or _resolved.startswith(_base_real + os.sep)):
        raise HTTPException(status_code=403, detail="Access denied")

    if not os.path.exists(abs_path):
        # Mark unavailable for future requests
        await _lib.update_file(f, {"is_available": False})
        raise HTTPException(status_code=404, detail="File not found on disk")

    file_size = os.path.getsize(abs_path)
    mime_type, _ = mimetypes.guess_type(f.filename)
    mime_type = mime_type or "application/octet-stream"

    # #8 - Non-blocking file streaming: each read chunk runs in a thread-pool
    # executor so the event loop is never blocked by disk I/O.
    # #10 - Stats are recorded AFTER streaming with the actual bytes sent,
    #        not the file_size upfront. try/finally ensures recording even on
    #        client disconnect mid-download.
    import asyncio as _asyncio
    from utils.throttle import effective_chunk_size, effective_speed_kbps, throttle_sleep

    _user_id   = user.id if user else None
    _username  = user.username if user else None
    _game_id   = f.library_game_id
    _file_id   = f.id
    _filename  = f.filename
    _speed_kbps = await effective_speed_kbps(_username)
    _chunk_size = effective_chunk_size(_speed_kbps)

    async def _stream():
        bytes_sent = 0
        loop = _asyncio.get_running_loop()
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
            # Record only if at least something was transferred
            if bytes_sent > 0:
                try:
                    await _lib.record_download(
                        user_id=_user_id,
                        game_id=_game_id,
                        file_id=_file_id,
                        filename=_filename,
                        bytes_transferred=bytes_sent,
                    )
                except Exception:
                    pass

    headers = {
        "Content-Disposition": "attachment; filename*=UTF-8''" + __import__('urllib.parse', fromlist=['quote']).quote(f.filename, safe=""),
        "Content-Length": str(file_size),
        "Accept-Ranges": "none",
    }
    return StreamingResponse(_stream(), media_type=mime_type, headers=headers)


# ── Native browser download - one-time token flow ─────────────────────────────
# Browser cannot set Authorization headers on <a href> anchor clicks, so we use
# a two-step flow:
#   1. POST /library/download/{file_id}/token  →  short-lived Redis token
#   2. GET  /library/dl/{file_id}?dl_token=xxx  →  stream (no Bearer needed)

import secrets as _secrets
import redis.asyncio as _aioredis
from config import REDIS_URL as _REDIS_URL
from fastapi import Query as _Query

_DL1T_PREFIX = "library_dl1t:"
_DL1T_TTL    = 60  # seconds - enough for browser to open the URL


def _redis_dl1t():
    return _aioredis.from_url(_REDIS_URL, decode_responses=True)


@protected_route(library_router.post, "/download/{file_id}/token", scopes=[Scope.LIBRARY_DOWNLOAD])
async def create_native_download_token(request: Request, file_id: int) -> dict:
    """Generate a 60-second one-time token so the browser can download without Bearer."""
    user = request.state.user
    f = await _lib.get_file_by_id(file_id)
    if not f or not f.is_available:
        raise HTTPException(status_code=404, detail="File not available")

    from models.user import Role
    if user.role != Role.ADMIN:
        access = await _lib.get_game_access(user.id, f.library_game_id)
        if access and access.access == "deny":
            raise HTTPException(status_code=403, detail="Access denied")
        game = await _lib.get_by_id(f.library_game_id)
        if not game or not game.is_active:
            raise HTTPException(status_code=404, detail="File not available")

    token = _secrets.token_urlsafe(32)
    async with _redis_dl1t() as r:
        await r.setex(f"{_DL1T_PREFIX}{token}", _DL1T_TTL, f"{user.username}:{file_id}")
    return {"token": token, "expires_in": _DL1T_TTL}


@library_router.get("/dl/{file_id}")
async def native_download_file(request: Request, file_id: int, dl_token: str = _Query(...)):
    """Stream file using a one-time Redis token - no Authorization header required."""
    key = f"{_DL1T_PREFIX}{dl_token}"
    async with _redis_dl1t() as r:
        stored = await r.get(key)
        if stored:
            await r.delete(key)

    if not stored:
        raise HTTPException(status_code=401, detail="Invalid or expired download token")

    stored_username, stored_file_id = stored.split(":", 1)
    if int(stored_file_id) != file_id:
        raise HTTPException(status_code=403, detail="Token mismatch")

    user = await _users.get_by_username(stored_username)
    f    = await _lib.get_file_by_id(file_id)
    if not f or not f.is_available:
        raise HTTPException(status_code=404, detail="File not available")

    abs_path   = _abs_path(f.file_path)
    _resolved  = os.path.realpath(abs_path)
    _base_real = os.path.realpath(BASE_PATH)
    if not (_resolved == _base_real or _resolved.startswith(_base_real + os.sep)):
        raise HTTPException(status_code=403, detail="Access denied")

    if not os.path.exists(abs_path):
        await _lib.update_file(f, {"is_available": False})
        raise HTTPException(status_code=404, detail="File not found on disk")

    file_size = os.path.getsize(abs_path)
    mime_type, _ = mimetypes.guess_type(f.filename)
    mime_type = mime_type or "application/octet-stream"

    import asyncio as _asyncio
    from utils.throttle import effective_chunk_size, effective_speed_kbps, throttle_sleep

    _username   = user.username if user else stored_username
    _speed_kbps = await effective_speed_kbps(_username)
    _chunk_size = effective_chunk_size(_speed_kbps)
    _user_id    = user.id if user else None
    _game_id    = f.library_game_id
    _file_id    = f.id
    _filename   = f.filename

    async def _stream():
        bytes_sent = 0
        loop = _asyncio.get_running_loop()
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
                    await _lib.record_download(
                        user_id=_user_id,
                        game_id=_game_id,
                        file_id=_file_id,
                        filename=_filename,
                        bytes_transferred=bytes_sent,
                    )
                except Exception:
                    pass

    headers = {
        "Content-Disposition": "attachment; filename*=UTF-8''" + __import__('urllib.parse', fromlist=['quote']).quote(f.filename, safe=""),
        "Content-Length":      str(file_size),
        "Accept-Ranges":       "none",
    }
    return StreamingResponse(_stream(), media_type=mime_type, headers=headers)


# ── Statistics ────────────────────────────────────────────────────────────────

@protected_route(library_router.get, "/stats", scopes=[Scope.LIBRARY_ADMIN])
async def get_library_stats(request: Request) -> dict:
    stats = await _lib.get_global_stats()
    # Enrich top_games with titles
    enriched = []
    for entry in stats["top_games"]:
        g = await _lib.get_by_id(entry["game_id"])
        enriched.append({
            "game_id": entry["game_id"],
            "title":   g.title if g else "Unknown",
            "count":   entry["count"],
        })
    stats["top_games"] = enriched
    return stats


@protected_route(library_router.get, "/stats/game/{game_id}", scopes=[Scope.LIBRARY_ADMIN])
async def get_game_stats(request: Request, game_id: int) -> dict:
    game = await _lib.get_by_id(game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    return await _lib.get_game_stats(game_id)


# ── Per-game access control (admin) ───────────────────────────────────────────

@protected_route(library_router.post, "/users/{user_id}/game-access", scopes=[Scope.USERS_WRITE])
async def set_user_game_access(request: Request, user_id: int, body: GameAccessBody) -> dict:
    user = await _users.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    entry = await _lib.set_game_access(user_id, body.game_id, body.access)
    return {"user_id": user_id, "game_id": body.game_id, "access": entry.access}


@protected_route(library_router.delete, "/users/{user_id}/game-access/{game_id}", scopes=[Scope.USERS_WRITE])
async def delete_user_game_access(request: Request, user_id: int, game_id: int) -> dict:
    await _lib.delete_game_access(user_id, game_id)
    return {"ok": True}
