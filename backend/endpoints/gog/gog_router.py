"""
GOG endpoints - requires authentication.
"""

from __future__ import annotations

import logging

import httpx
from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request
from pydantic import BaseModel

from handler.auth.scopes import Scope
from handler.gog.gog_auth_handler import gog_auth_handler

logger = logging.getLogger(__name__)

gog_router = APIRouter(prefix="/api/gog", tags=["gog"])

# Shared sync status (in-memory, resets on restart)
_sync_status: dict = {"running": False, "synced": 0, "error": None, "phase": None}


class GogCodeRequest(BaseModel):
    code: str


class GameMetadataUpdate(BaseModel):
    cover_url: str | None = None
    background_url: str | None = None
    icon_url: str | None = None
    logo_url: str | None = None          # transparent logo (SteamGridDB)
    description: str | None = None
    description_short: str | None = None
    developer: str | None = None
    publisher: str | None = None
    release_date: str | None = None
    genres: list[str] | None = None
    tags: list[str] | None = None
    features: list[str] | None = None
    rating: float | None = None
    requirements: dict | None = None
    meta_ratings: dict | None = None   # {"rawg": float|null, "igdb": float|null}
    screenshots: list[str] | None = None
    videos: list[dict] | None = None     # [{"provider": "youtube", "video_id": "...", "thumbnail_id": ""}]
    os_windows: bool | None = None
    os_mac: bool | None = None
    os_linux: bool | None = None
    languages: dict | None = None        # {code: code} e.g. {"en": "en", "pl": "pl"}


def _require_auth(request: Request) -> None:
    if not getattr(request.state, "user", None):
        raise HTTPException(status_code=401, detail="Not authenticated")


def _require_scope(request: Request, *scopes: Scope) -> None:
    """Check authentication and required scopes. Raises 401/403 on failure."""
    _require_auth(request)
    if scopes:
        user_scopes = getattr(request.state, "scopes", set())
        missing = [s for s in scopes if s not in user_scopes]
        if missing:
            raise HTTPException(
                status_code=403,
                detail=f"Missing scopes: {', '.join(str(s) for s in missing)}",
            )



def _sanitize_search(term: str) -> str:
    """Strip characters that could inject into IGDB Apicalypse query strings."""
    # Remove quotes and semicolons which terminate/inject Apicalypse fields/queries
    return term.replace('"', '').replace("'", '').replace(';', '').strip()[:128]


def _game_dict(g, owner_username: str | None = None) -> dict:
    """Serialise a GogGame ORM object to a dict for API responses."""
    d = {
        "id":                g.id,
        "gog_id":            g.gog_id,
        "title":             g.title,
        "slug":              g.slug,
        "owner_user_id":     g.owner_user_id,
        "cover_url":         g.cover_url,
        "cover_path":        g.cover_path,
        "background_url":    g.background_url,
        "background_path":   g.background_path,
        "icon_url":          g.icon_url,
        "icon_path":         g.icon_path,
        "logo_url":          g.logo_url,
        "logo_path":         g.logo_path,
        "developer":         g.developer,
        "publisher":         g.publisher,
        "release_date":      g.release_date,
        "genres":            g.genres or [],
        "tags":              g.tags or [],
        "rating":            g.rating,
        "summary":           g.summary,
        "description":       g.description,
        "description_short": g.description_short,
        "features":          g.features or [],
        "languages":         g.languages or {},
        "videos":            g.videos or [],
        "screenshots":       g.screenshots or [],
        "os_windows":        g.os_windows,
        "os_mac":            g.os_mac,
        "os_linux":          g.os_linux,
        "installers":        g.installers or {},
        "extras":            g.extras or [],
        "version":           g.version,
        "changelog":         g.changelog,
        "is_downloaded":     g.is_downloaded,
        "download_status":   "completed" if g.is_downloaded else "none",
        "file_size":         g.file_size,
        "scraped":           g.scraped,
        "scraped_at":        g.scraped_at.isoformat() if g.scraped_at else None,
        "requirements":      g.requirements or {},
        "meta_ratings":      g.meta_ratings or {},
        "hltb_main_s":       g.hltb_main_s,
        "hltb_complete_s":   g.hltb_complete_s,
    }
    d["owner_user_id"] = g.owner_user_id
    d["owner_username"] = owner_username
    d["is_admin_game"] = g.owner_user_id is None
    return d


# ── Auth ──────────────────────────────────────────────────────────────────────

@gog_router.get("/auth/url")
async def get_auth_url(request: Request) -> dict:
    _require_scope(request, Scope.GOG_READ)
    return {"url": gog_auth_handler.get_auth_url()}


@gog_router.post("/auth/callback")
async def auth_callback(req: GogCodeRequest, request: Request) -> dict:
    _require_scope(request, Scope.GOG_WRITE)
    try:
        result = await gog_auth_handler.exchange_code(req.code)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"GOG authentication failed: {str(e)}")


@gog_router.get("/auth/status")
async def auth_status(request: Request) -> dict:
    _require_scope(request, Scope.GOG_READ)
    status = await gog_auth_handler.get_status()
    if status.get("authenticated"):
        from handler.gog.gog_sync_handler import gog_sync_handler
        status["game_count"] = await gog_sync_handler.count()
    return status


@gog_router.delete("/auth")
async def disconnect(request: Request) -> dict:
    _require_scope(request, Scope.GOG_WRITE)
    await gog_auth_handler.disconnect()
    return {"ok": True}


# ── Library ───────────────────────────────────────────────────────────────────

@gog_router.get("/library/games")
async def get_library(request: Request) -> list:
    _require_scope(request, Scope.GOG_READ)
    from handler.gog.gog_sync_handler import gog_sync_handler
    games = await gog_sync_handler.get_all_deduped()
    # Build user_id -> username map for games with owners
    owner_ids = {g.owner_user_id for g in games if g.owner_user_id is not None}
    username_map: dict[int | None, str] = {}
    admin_name = getattr(request.state.user, "username", "Admin") if hasattr(request.state, "user") else "Admin"
    username_map[None] = admin_name
    if owner_ids:
        from handler.database.session import async_session_factory
        from sqlalchemy import select as _sel
        from models.user import User
        async with async_session_factory() as session:
            rows = (await session.execute(
                _sel(User.id, User.username).where(User.id.in_(owner_ids))
            )).all()
            username_map.update({r[0]: r[1] for r in rows})
    return [_game_dict(g, owner_username=username_map.get(g.owner_user_id)) for g in games]


@gog_router.get("/library/games/{game_id}")
async def get_game(game_id: int, request: Request) -> dict:
    """Return full details for a single game by DB id."""
    _require_scope(request, Scope.GOG_READ)
    from handler.gog.gog_sync_handler import gog_sync_handler
    game = await gog_sync_handler.get_by_id(game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    # Resolve owner username
    owner_username: str | None = None
    if game.owner_user_id is not None:
        from handler.database.session import async_session_factory
        from sqlalchemy import select as _sel
        from models.user import User
        async with async_session_factory() as session:
            owner_username = (await session.execute(
                _sel(User.username).where(User.id == game.owner_user_id)
            )).scalar_one_or_none()
    else:
        # Admin game (owner_user_id is None) - use requesting user's name as admin
        owner_username = getattr(request.state.user, "username", "Admin") if hasattr(request.state, "user") else "Admin"
    return _game_dict(game, owner_username=owner_username)


@gog_router.post("/library/games/{game_id}/scrape")
async def scrape_game(
    game_id: int,
    request: Request,
    background_tasks: BackgroundTasks,
    preserve_external: bool = Query(default=False, description="Keep existing RAWG/IGDB ratings, only refresh GOG data"),
) -> dict:
    """Trigger a metadata scrape for a single game."""
    _require_scope(request, Scope.GOG_WRITE)
    from handler.gog.gog_sync_handler import gog_sync_handler
    from handler.gog.gog_scrape_handler import gog_scrape_handler
    game = await gog_sync_handler.get_by_id(game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    background_tasks.add_task(gog_scrape_handler.scrape_game, game.gog_id, True, preserve_external)
    return {"ok": True, "message": f"Scraping metadata for '{game.title}'"}


@gog_router.delete("/library/games/{game_id}/metadata")
async def clear_game_metadata(game_id: int, request: Request) -> dict:
    """Clear all scraped metadata for a single game (title/gog_id are preserved)."""
    _require_scope(request, Scope.GOG_WRITE)
    from handler.gog.gog_sync_handler import gog_sync_handler
    from handler.gog.gog_scrape_handler import gog_scrape_handler
    game = await gog_sync_handler.get_by_id(game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    ok = await gog_scrape_handler.clear_game_metadata(game.gog_id)
    return {"ok": ok}


@gog_router.delete("/library/metadata")
async def clear_all_metadata(request: Request) -> dict:
    """Clear all scraped metadata for every game in the library."""
    _require_scope(request, Scope.GOG_WRITE)
    from handler.gog.gog_scrape_handler import gog_scrape_handler
    count = await gog_scrape_handler.clear_all_metadata()
    return {"ok": True, "cleared": count}


@gog_router.post("/library/scrape")
async def scrape_all(
    request: Request,
    background_tasks: BackgroundTasks,
    force: bool = Query(default=False, description="Force rescrape already-scraped games"),
) -> dict:
    """Scrape metadata for all games in the background."""
    _require_scope(request, Scope.GOG_WRITE)
    from handler.gog.gog_scrape_handler import gog_scrape_handler
    background_tasks.add_task(gog_scrape_handler.scrape_all_unscraped, force)
    return {"ok": True, "message": "Background metadata scrape started"}


@gog_router.post("/library/hltb-rescrape")
async def hltb_rescrape_gog(
    request: Request,
    background_tasks: BackgroundTasks,
    force: bool = Query(default=False, description="Rescrape even games that already have HLTB data"),
) -> dict:
    """Bulk-rescrape HowLongToBeat playtime for all GOG library games."""
    _require_scope(request, Scope.GOG_WRITE)
    from handler.metadata.hltb_bulk_handler import rescrape_gog as _rescrape
    background_tasks.add_task(_rescrape, force)
    return {"ok": True, "message": "HLTB GOG rescrape started in background", "force": force}


@gog_router.post("/library/sync")
async def sync_library(
    request: Request,
    background_tasks: BackgroundTasks,
    auto_scrape: bool = Query(default=True, description="Automatically scrape metadata after sync"),
    force_rescrape: bool = Query(default=False, description="Force rescrape even already-scraped games"),
) -> dict:
    _require_scope(request, Scope.GOG_WRITE)
    global _sync_status
    if _sync_status["running"]:
        return {"ok": True, "message": "Sync already in progress", "running": True}

    async def _do_sync(do_scrape: bool, force: bool = False):
        global _sync_status
        _sync_status = {"running": True, "synced": 0, "error": None, "phase": "sync"}
        from handler.gog.gog_sync_handler import gog_sync_handler
        from handler.gog.gog_scrape_handler import gog_scrape_handler

        async def progress(current, total, title):
            _sync_status["synced"] = current

        try:
            result = await gog_sync_handler.sync_library(progress_cb=progress)
            _sync_status["synced"] = result.get("synced", 0)
            if not result.get("ok"):
                _sync_status["running"] = False
                _sync_status["error"] = result.get("error")
                return

            count = result.get("synced", 0)
            from handler.notifications.webhook_handler import notify_if_configured
            await notify_if_configured(
                "sync",
                title="Library Synced",
                description=f"GOG library sync complete - {count} games in library.",
            )
            if do_scrape:
                # Await scrape directly - keep running=True until metadata is fetched.
                # Using create_task caused the frontend to refresh before metadata was ready.
                _sync_status["phase"] = "scrape"
                await gog_scrape_handler.scrape_all_unscraped(force=force)

            _sync_status["running"] = False
        except Exception as e:
            _sync_status["running"] = False
            _sync_status["error"] = str(e)

    background_tasks.add_task(_do_sync, auto_scrape, force_rescrape)
    _sync_status["running"] = True
    return {"ok": True, "message": "Sync started"}


@gog_router.get("/library/sync/status")
async def sync_status(request: Request) -> dict:
    _require_scope(request, Scope.GOG_READ)
    return _sync_status


@gog_router.patch("/library/games/{game_id}")
async def update_game_metadata(game_id: int, req: GameMetadataUpdate, request: Request, bg: BackgroundTasks) -> dict:
    """Manually update metadata fields for a game."""
    _require_scope(request, Scope.GOG_WRITE)
    from handler.gog.gog_sync_handler import gog_sync_handler
    game = await gog_sync_handler.get_by_id(game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")
    fields = req.model_dump(exclude_none=True)
    if not fields:
        return {"ok": True}
    # Clear cached local paths when source URLs are manually updated so the
    # frontend re-downloads the new image instead of showing the stale file.
    _url_to_path = {
        "cover_url":      "cover_path",
        "background_url": "background_path",
        "logo_url":       "logo_path",
        "icon_url":       "icon_path",
    }
    for url_field, path_field in _url_to_path.items():
        if url_field in fields:
            fields[path_field] = None
    await gog_sync_handler.update_fields(game_id, fields)

    # Immediately download new images in background so they're cached locally
    media_urls = {k: fields[k] for k in _url_to_path if k in fields and fields.get(k)}
    if media_urls:
        gog_id = game.gog_id
        async def _download_updated_media():
            from handler.gog.media_handler import (
                download_cover, download_background, download_logo, download_icon,
            )
            _downloaders = {
                "cover_url":      (download_cover,      "cover_path"),
                "background_url": (download_background, "background_path"),
                "logo_url":       (download_logo,       "logo_path"),
                "icon_url":       (download_icon,        "icon_path"),
            }
            update = {}
            for url_field, (dl_func, path_field) in _downloaders.items():
                if url_field in media_urls:
                    path = await dl_func(gog_id, media_urls[url_field], overwrite=True)
                    if path:
                        update[path_field] = path
            if update:
                await gog_sync_handler.update_fields(game_id, update)

        bg.add_task(_download_updated_media)

    return {"ok": True}


@gog_router.get("/library/games/{game_id}/covers")
async def get_cover_options(
    game_id: int,
    request: Request,
    source: str = Query(default="gog", description="gog | igdb | steamgriddb | rawg | launchbox | plugins"),
    q: str = Query(default="", description="Override search query"),
    asset_type: str = Query(default="grids", description="steamgriddb asset type: grids | heroes | logos | icons"),
    animated: str = Query(default="any", description="any | only | exclude - filter animated results"),
) -> list:
    """Return cover image options for a game from various sources."""
    _require_scope(request, Scope.GOG_READ)
    from handler.gog.gog_sync_handler import gog_sync_handler
    game = await gog_sync_handler.get_by_id(game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    results = []

    if source == "gog":
        # Always fetch from GOG API v2 by gog_id (works even after Clear Metadata)
        if game.gog_id:
            try:
                from handler.library.library_scrape_handler import _abs_url
                _HDRS = {"User-Agent": "Mozilla/5.0 GOGGalaxy/2.0", "Accept": "application/json"}
                async with httpx.AsyncClient(timeout=10, headers=_HDRS) as c:
                    r = await c.get(f"https://api.gog.com/v2/games/{game.gog_id}?locale=en-US")
                    if r.status_code == 200:
                        links = r.json().get("_links") or {}
                        box_art = (links.get("boxArtImage") or {}).get("href")
                        bg = ((links.get("galaxyBackgroundImage") or {}).get("href")
                              or (links.get("backgroundImage") or {}).get("href"))
                        logo_href = (links.get("logo") or {}).get("href")
                        if box_art:
                            results.append({"url": _abs_url(box_art), "thumb": _abs_url(box_art), "type": "static", "label": "GOG Cover"})
                        if bg:
                            results.append({"url": _abs_url(bg), "thumb": _abs_url(bg), "type": "static", "label": "GOG Background"})
                        if logo_href:
                            results.append({"url": _abs_url(logo_href), "thumb": _abs_url(logo_href), "type": "static", "label": "GOG Logo", "asset_type": "logos"})
            except Exception as exc:
                logger.warning("GOG API v2 fetch failed: %s", exc)

    elif source == "gog-logo":
        # Fetch logo from GOG API v2
        if game.gog_id:
            try:
                from handler.library.library_scrape_handler import _abs_url
                _HDRS = {"User-Agent": "Mozilla/5.0 GOGGalaxy/2.0", "Accept": "application/json"}
                async with httpx.AsyncClient(timeout=10, headers=_HDRS) as c:
                    r = await c.get(f"https://api.gog.com/v2/games/{game.gog_id}?locale=en-US")
                    if r.status_code == 200:
                        logo_href = (r.json().get("_links") or {}).get("logo", {}).get("href")
                        if logo_href:
                            results = [{"url": _abs_url(logo_href), "thumb": _abs_url(logo_href),
                                        "type": "static", "label": "GOG Logo", "asset_type": "logos"}]
            except Exception:
                pass

    elif source == "gog-icon":
        base = game.cover_url or game.icon_url or ""
        for sfx in ("_product_card.jpg", "_aw.webp", "_logo2x.png", "_logo.png",
                    "_product_tile_256.jpg", ".jpg", ".png", ".webp"):
            if base.endswith(sfx):
                base = base[:-len(sfx)]
                break
        if base:
            results = [
                {"url": f"{base}_product_tile_256.jpg", "thumb": f"{base}_product_tile_256.jpg",
                 "type": "static", "label": "GOG Icon (256x256)"},
            ]
        if game.icon_url:
            results.insert(0, {"url": game.icon_url, "thumb": game.icon_url,
                               "type": "static", "label": "GOG Icon"})

    elif source == "igdb":
        search_term = q or (game.title if game else "")
        try:
            from handler.config.config_handler import config_handler
            client_id     = await config_handler.get("igdb_client_id")
            client_secret = await config_handler.get("igdb_client_secret")
            if not client_id or not client_secret:
                return []
            async with httpx.AsyncClient(timeout=15) as c:
                # Get Twitch OAuth token
                tr = await c.post("https://id.twitch.tv/oauth2/token", params={
                    "client_id":     client_id,
                    "client_secret": client_secret,
                    "grant_type":    "client_credentials",
                })
                if tr.status_code != 200:
                    return []
                token = tr.json().get("access_token", "")
                if not token:
                    return []
                headers = {"Client-ID": client_id, "Authorization": f"Bearer {token}"}
                # Search IGDB
                gr = await c.post(
                    "https://api.igdb.com/v4/games",
                    headers=headers,
                    content=f'fields id,name,cover.image_id; search "{_sanitize_search(search_term)}"; limit 5;',
                )
                if gr.status_code != 200:
                    return []
                for ig in gr.json():
                    cov = ig.get("cover") or {}
                    img_id = cov.get("image_id")
                    if not img_id:
                        continue
                    results.append({
                        "url":   f"https://images.igdb.com/igdb/image/upload/t_cover_big/{img_id}.jpg",
                        "thumb": f"https://images.igdb.com/igdb/image/upload/t_cover_big/{img_id}.jpg",
                        "type":  "static",
                        "label": f"{ig.get('name', '')} - cover_big (264×352)",
                        "author": "IGDB",
                    })
                    results.append({
                        "url":   f"https://images.igdb.com/igdb/image/upload/t_1080p/{img_id}.jpg",
                        "thumb": f"https://images.igdb.com/igdb/image/upload/t_cover_big/{img_id}.jpg",
                        "type":  "static",
                        "label": f"{ig.get('name', '')} - 1080p",
                        "author": "IGDB",
                    })
        except Exception as exc:
            logger.warning("IGDB cover search failed: %s", exc)

    elif source == "steamgriddb":
        search_term = q or (game.title if game else "")
        _SGDB_ANIMATED_MIMES = ("video/webm", "image/gif", "image/webp")
        try:
            from handler.config.config_handler import config_handler
            api_key = await config_handler.get("steamgriddb_api_key")
            if not api_key:
                return []
            headers_sgdb = {"Authorization": f"Bearer {api_key}"}
            async with httpx.AsyncClient(timeout=15) as c:
                # Search for game to get SGDB id
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

                # Map asset_type to SGDB endpoint + params
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
                # Pass animation type filter directly to SGDB API
                types_filter = {"only": "animated", "exclude": "static"}.get(animated, "animated,static")
                params = {**base_params, "types": types_filter}
                r2 = await c.get(endpoint_url, params=params, headers=headers_sgdb)
                if r2.status_code == 200:
                    for item in r2.json().get("data", []):
                        mime = item.get("mime", "")
                        is_anim = mime in _SGDB_ANIMATED_MIMES
                        # Respect animated filter
                        if animated == "only" and not is_anim:
                            continue
                        if animated == "exclude" and is_anim:
                            continue
                        dim_label = f"{item.get('width', '?')}×{item.get('height', '?')}"
                        style     = item.get("style", "")
                        label     = f"{dim_label}" + (f" · {style}" if style else "")
                        results.append({
                            "url":        item["url"],
                            "thumb":      item.get("thumb") or item["url"],
                            "type":       "animated" if is_anim else "static",
                            "label":      label,
                            "author":     (item.get("author") or {}).get("name", ""),
                            "asset_type": asset_type,
                            "mime":       mime,
                            "style":      style,
                        })
        except Exception as exc:
            logger.warning("SteamGridDB %s search failed: %s", asset_type, exc)

    elif source == "rawg":
        search_term = q or (game.title if game else "")
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
                games_list = r.json().get("results", [])
                for item in games_list:
                    bg = item.get("background_image")
                    if not bg:
                        continue
                    results.append({
                        "url": bg,
                        "thumb": bg,
                        "type": "static",
                        "label": item.get("name", ""),
                        "author": "RAWG",
                    })
        except Exception as exc:
            logger.warning("RAWG cover search failed: %s", exc)

    elif source == "launchbox":
        search_term = q or (game.title if game else "")
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
        # Query all metadata provider plugins for covers/heroes/logos
        search_term = q or (game.title if game else "")
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
                            # Use plugin logo as source icon - resolve plugin_id
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


@gog_router.get("/library/games/{game_id}/meta-sources")
async def get_meta_sources(
    game_id: int,
    request: Request,
    source: str = Query(default="rawg", description="rawg | igdb"),
    q: str = Query(default="", description="Override search query"),
) -> dict:
    """Fetch full metadata (description, requirements, cover) from an external source."""
    _require_scope(request, Scope.GOG_READ)
    from handler.gog.gog_sync_handler import gog_sync_handler
    game = await gog_sync_handler.get_by_id(game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    search_term = q or game.title
    result: dict = {"source": source, "found": False}

    if source == "gog":
        # If metadata is cleared, fetch fresh from GOG API
        has_data = bool(game.developer or game.description or game.genres)
        if not has_data and game.gog_id:
            try:
                from handler.library.library_scrape_handler import _abs_url
                _HDRS = {"User-Agent": "Mozilla/5.0 GOGGalaxy/2.0", "Accept": "application/json"}
                async with httpx.AsyncClient(timeout=15, headers=_HDRS) as c:
                    r1 = await c.get(f"https://api.gog.com/products/{game.gog_id}?expand=description&locale=en-US")
                    if r1.status_code == 200:
                        d = r1.json()
                        desc = d.get("description", {})
                        result = {
                            "source": "gog", "found": True,
                            "name": d.get("title", game.title),
                            "developer": (d.get("developers") or [""])[0] if d.get("developers") else "",
                            "publisher": (d.get("publishers") or [""])[0] if d.get("publishers") else "",
                            "release_date": d.get("release_date", ""),
                            "rating": d.get("rating"),
                            "description": desc.get("full", ""),
                            "description_short": desc.get("lead", ""),
                            "genres": [g.get("name", "") for g in (d.get("genres") or [])],
                            "os_windows": "windows" in str(d.get("content_system_compatibility", {})),
                            "os_mac": "osx" in str(d.get("content_system_compatibility", {})),
                            "os_linux": "linux" in str(d.get("content_system_compatibility", {})),
                            "languages": d.get("languages", {}) or {},
                        }
                        return result
            except Exception:
                pass
        raw_langs = game.languages or {}
        result = {
            "source": "gog", "found": bool(has_data),
            "name": game.title,
            "developer": game.developer or "",
            "publisher": game.publisher or "",
            "release_date": game.release_date or "",
            "rating": game.rating,
            "description": game.description or "",
            "description_short": game.description_short or "",
            "genres": game.genres or [],
            "os_windows": game.os_windows or False,
            "os_mac": game.os_mac or False,
            "os_linux": game.os_linux or False,
            "languages": raw_langs,
        }

    elif source == "rawg":
        try:
            from handler.config.config_handler import config_handler
            api_key = await config_handler.get("rawg_api_key")
            if not api_key:
                return {"source": "rawg", "found": False, "error": "RAWG API key not configured"}
            async with httpx.AsyncClient(timeout=20) as c:
                # Search for game
                sr = await c.get(
                    "https://api.rawg.io/api/games",
                    params={"key": api_key, "search": search_term, "page_size": 5},
                )
                if sr.status_code != 200:
                    return {"source": "rawg", "found": False, "error": f"RAWG search returned {sr.status_code}"}
                search_results = sr.json().get("results", [])
                if not search_results:
                    return {"source": "rawg", "found": False, "error": "No results found"}

                # Return search results list so frontend can let user pick
                candidates = []
                for item in search_results:
                    candidates.append({
                        "id": item.get("id"),
                        "slug": item.get("slug", ""),
                        "name": item.get("name", ""),
                        "released": item.get("released", ""),
                        "background_image": item.get("background_image", ""),
                        "rating": item.get("rating"),
                    })
                result["found"] = True
                result["candidates"] = candidates
        except Exception as exc:
            result["error"] = str(exc)

    elif source == "rawg-detail":
        # Fetch full details for a specific RAWG game id/slug
        rawg_id = q  # q holds the slug or numeric id
        try:
            from handler.config.config_handler import config_handler
            api_key = await config_handler.get("rawg_api_key")
            if not api_key:
                return {"source": "rawg-detail", "found": False, "error": "RAWG API key not configured"}
            async with httpx.AsyncClient(timeout=20) as c:
                dr = await c.get(
                    f"https://api.rawg.io/api/games/{rawg_id}",
                    params={"key": api_key},
                )
                if dr.status_code != 200:
                    return {"source": "rawg-detail", "found": False}
                d = dr.json()

                # Extract requirements from platforms
                requirements: dict = {}
                for pdata in d.get("platforms", []):
                    pname = (pdata.get("platform") or {}).get("name", "")
                    reqs = pdata.get("requirements") or {}
                    if reqs and ("minimum" in reqs or "recommended" in reqs):
                        requirements[pname] = reqs

                # Developers and publishers
                developers = [
                    c_item.get("name", "")
                    for c_item in d.get("developers", [])
                    if isinstance(c_item, dict)
                ]
                publishers = [
                    c_item.get("name", "")
                    for c_item in d.get("publishers", [])
                    if isinstance(c_item, dict)
                ]
                genres = [g.get("name", "") for g in d.get("genres", []) if isinstance(g, dict)]

                result["found"] = True
                result["name"] = d.get("name", "")
                result["description"] = d.get("description_raw") or d.get("description") or ""
                result["description_short"] = ""
                result["cover_url"] = d.get("background_image") or ""
                result["developer"] = ", ".join(developers) if developers else ""
                result["publisher"] = ", ".join(publishers) if publishers else ""
                result["release_date"] = d.get("released") or ""
                result["rating"] = (d.get("rating") or 0) * 2  # RAWG uses 1-5, convert to 1-10
                result["genres"] = genres
                result["requirements"] = requirements
        except Exception as exc:
            result["error"] = str(exc)

    elif source == "igdb":
        try:
            from handler.config.config_handler import config_handler
            client_id     = await config_handler.get("igdb_client_id")
            client_secret = await config_handler.get("igdb_client_secret")
            if not client_id or not client_secret:
                return {"source": "igdb", "found": False, "error": "IGDB keys not configured"}
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
                headers = {"Client-ID": client_id, "Authorization": f"Bearer {token}"}
                gr = await c.post(
                    "https://api.igdb.com/v4/games",
                    headers=headers,
                    content=(
                        f'fields id,name,summary,storyline,cover.image_id,'
                        f'involved_companies.company.name,involved_companies.developer,involved_companies.publisher,'
                        f'genres.name,themes.name,first_release_date,total_rating,aggregated_rating;'
                        f' search "{_sanitize_search(search_term)}"; limit 5;'
                    ),
                )
                if gr.status_code != 200:
                    return {"source": "igdb", "found": False, "error": f"IGDB returned {gr.status_code}"}
                igdb_games = gr.json()
                if not igdb_games:
                    return {"source": "igdb", "found": False, "error": "No results"}

                candidates = []
                for ig in igdb_games:
                    cov = ig.get("cover") or {}
                    img_id = cov.get("image_id")
                    cover_url = f"https://images.igdb.com/igdb/image/upload/t_cover_big/{img_id}.jpg" if img_id else ""

                    devs = [
                        ic["company"]["name"]
                        for ic in ig.get("involved_companies", [])
                        if isinstance(ic, dict) and ic.get("developer") and isinstance(ic.get("company"), dict)
                    ]
                    pubs = [
                        ic["company"]["name"]
                        for ic in ig.get("involved_companies", [])
                        if isinstance(ic, dict) and ic.get("publisher") and isinstance(ic.get("company"), dict)
                    ]
                    genres = [g["name"] for g in ig.get("genres", []) if isinstance(g, dict)]
                    release_ts = ig.get("first_release_date")
                    release_date = ""
                    if release_ts:
                        from datetime import datetime, timezone
                        release_date = datetime.fromtimestamp(release_ts, tz=timezone.utc).strftime("%Y-%m-%d")
                    candidates.append({
                        "id": ig.get("id"),
                        "name": ig.get("name", ""),
                        "summary": ig.get("summary", ""),
                        "storyline": ig.get("storyline", ""),
                        "description": ig.get("storyline") or ig.get("summary") or "",
                        "description_short": ig.get("summary") or "",
                        "cover_url": cover_url,
                        "developer": ", ".join(devs),
                        "publisher": ", ".join(pubs),
                        "release_date": release_date,
                        "genres": genres,
                        "rating": ig.get("total_rating") or ig.get("aggregated_rating"),
                    })
                result["found"] = True
                result["candidates"] = candidates
        except Exception as exc:
            result["error"] = str(exc)

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
            result["found"]             = True
            result["app_id"]            = app_id
            result["name"]              = steam.get("name") or search_term
            result["description"]       = steam.get("description", "")
            result["description_short"] = steam.get("description_short", "")
            result["developer"]         = steam.get("developer", "")
            result["publisher"]         = steam.get("publisher", "")
            result["release_date"]      = steam.get("release_date", "")
            result["genres"]            = steam.get("genres", [])
            result["rating"]            = steam.get("rating")
            result["requirements"]      = steam.get("requirements", {})
        except Exception as exc:
            result["error"] = str(exc)

    return result


@gog_router.get("/library/games/{game_id}/screenshots")
async def get_screenshot_options(
    game_id: int,
    request: Request,
    source: str = Query(default="gog", description="gog | igdb | rawg | steam | launchbox | all"),
    q: str = Query(default="", description="Override search query"),
) -> list:
    """Return screenshot options from various metadata sources."""
    _require_scope(request, Scope.GOG_READ)
    from handler.gog.gog_sync_handler import gog_sync_handler
    game = await gog_sync_handler.get_by_id(game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    results = []

    if source == "gog":
        ss_list = game.screenshots or []
        if not ss_list and game.gog_id:
            # Fallback: fetch from GOG API v1
            try:
                from handler.library.library_scrape_handler import _abs_url
                _HDRS = {"User-Agent": "Mozilla/5.0 GOGGalaxy/2.0", "Accept": "application/json"}
                async with httpx.AsyncClient(timeout=15, headers=_HDRS) as c:
                    r = await c.get(f"https://api.gog.com/products/{game.gog_id}?expand=screenshots&locale=en-US")
                    if r.status_code == 200:
                        for ss in (r.json().get("screenshots") or []):
                            img_id = ss.get("image_id", "")
                            if img_id:
                                url = _abs_url(f"https://images-1.gog-statics.com/{img_id}.jpg" if not img_id.startswith("http") else img_id)
                                ss_list.append(url)
            except Exception:
                pass
        for i, ss_url in enumerate(ss_list):
            results.append({
                "url":    ss_url,
                "thumb":  ss_url,
                "type":   "static",
                "label":  f"Screenshot {i + 1}",
                "author": "GOG",
            })

    elif source == "igdb":
        search_term = q or (game.title if game else "")
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
                    content=f'fields id,name,screenshots.image_id; search "{_sanitize_search(search_term)}"; limit 3;',
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
        search_term = q or (game.title if game else "")
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

    elif source == "steam":
        search_term = q or (game.title if game else "")
        try:
            from handler.gog.steam_scraper import search_steam_app, fetch_steam_app_details
            app_id = await search_steam_app(search_term)
            if app_id:
                steam = await fetch_steam_app_details(app_id)
                for i, url in enumerate(steam.get("screenshots", []) if steam else []):
                    results.append({
                        "url":    url,
                        "thumb":  url,
                        "type":   "static",
                        "label":  f"Screenshot {i + 1}",
                        "author": "Steam",
                    })
        except Exception as exc:
            logger.warning("Steam screenshot search failed: %s", exc)

    elif source == "launchbox":
        search_term = q or (game.title if game else "")
        try:
            from handler.metadata.launchbox_handler import search_candidates, get_lb_screenshots
            candidates = await search_candidates(search_term, None, max_results=3)
            for c in candidates:
                lb_id = c.get("launchbox_id")
                if not lb_id:
                    continue
                for img in get_lb_screenshots(str(lb_id)):
                    results.append({
                        "url": img["url"], "thumb": img["url"],
                        "type": "static", "label": c.get("name", ""),
                        "author": "LaunchBox",
                    })
        except Exception as exc:
            logger.warning("LaunchBox screenshot search failed: %s", exc)

    elif source == "all":
        # Parallel search across all sources
        import asyncio
        search_term = q or (game.title if game else "")
        sub_sources = ["gog", "igdb", "rawg", "steam", "launchbox"]
        tasks = [
            get_screenshot_options(game_id, request, source=s, q=search_term)
            for s in sub_sources
        ]
        all_results = await asyncio.gather(*tasks, return_exceptions=True)
        source_names = ["GOG", "IGDB", "RAWG", "Steam", "LaunchBox"]
        for i, res in enumerate(all_results):
            if isinstance(res, list):
                for r in res:
                    r["_source"] = source_names[i]
                    r["_sourceIcon"] = ["gog.ico", "igdb.ico", "RAWG.ico", "Steam.ico", "launchbox.ico"][i]
                results.extend(res)
        # Plugin screenshots (via metadata_get_game -> screenshots field)
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


@gog_router.get("/library/games/{game_id}/videos")
async def get_video_options(
    game_id: int,
    request: Request,
    source: str = Query(default="gog", description="gog | igdb | all"),
    q: str = Query(default="", description="Override search query"),
) -> list:
    """Return trailer/video options from various metadata sources."""
    _require_scope(request, Scope.GOG_READ)
    from handler.gog.gog_sync_handler import gog_sync_handler
    game = await gog_sync_handler.get_by_id(game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    results = []

    if source == "gog":
        vid_list = game.videos or []
        if not vid_list and game.gog_id:
            # Fallback: fetch from GOG API v1
            try:
                import re as _re
                _HDRS = {"User-Agent": "Mozilla/5.0 GOGGalaxy/2.0", "Accept": "application/json"}
                async with httpx.AsyncClient(timeout=15, headers=_HDRS) as c:
                    r = await c.get(f"https://api.gog.com/products/{game.gog_id}?expand=videos&locale=en-US")
                    if r.status_code == 200:
                        for v in (r.json().get("videos") or []):
                            vid_url = v.get("video_url", "")
                            m = _re.search(r'(?:youtu\.be/|/embed/|[?&]v=)([a-zA-Z0-9_-]{11})', vid_url)
                            if m:
                                vid_list.append({"video_id": m.group(1), "provider": "youtube"})
            except Exception:
                pass
        for v in vid_list:
            vid_id = v.get("video_id") if isinstance(v, dict) else None
            if vid_id:
                results.append({
                    "video_id": vid_id,
                    "provider": v.get("provider", "youtube") if isinstance(v, dict) else "youtube",
                    "thumb":    f"https://img.youtube.com/vi/{vid_id}/hqdefault.jpg",
                    "label":    "GOG Trailer",
                    "author":   "GOG",
                })

    elif source == "igdb":
        search_term = q or (game.title if game else "")
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
                    content=f'fields id,name,videos.video_id,videos.name; search "{_sanitize_search(search_term)}"; limit 3;',
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

    elif source == "all":
        import asyncio
        tasks = [
            get_video_options(game_id, request, source="gog", q=q),
            get_video_options(game_id, request, source="igdb", q=q or (game.title if game else "")),
        ]
        all_results = await asyncio.gather(*tasks, return_exceptions=True)
        for res in all_results:
            if isinstance(res, list):
                results.extend(res)

    return results


@gog_router.post("/library/games/{game_id}/upload")
async def upload_media(
    game_id: int,
    request: Request,
    media_type: str = Query(description="cover | background | logo | icon | screenshot"),
) -> dict:
    """Upload a local image file for a game (cover, background, logo, icon, screenshot)."""
    _require_scope(request, Scope.GOG_WRITE)
    import os, uuid, shutil, asyncio
    from fastapi import UploadFile
    from fastapi.datastructures import UploadFile as FUploadFile

    allowed = {"cover", "background", "logo", "icon", "screenshot"}
    if media_type not in allowed:
        raise HTTPException(status_code=400, detail=f"media_type must be one of: {', '.join(allowed)}")

    from handler.gog.gog_sync_handler import gog_sync_handler
    game = await gog_sync_handler.get_by_id(game_id)
    if not game:
        raise HTTPException(status_code=404, detail="Game not found")

    # Read multipart body
    content_type = request.headers.get("content-type", "")
    if "multipart/form-data" not in content_type:
        raise HTTPException(status_code=400, detail="Multipart/form-data expected")

    form = await request.form()
    file_obj = form.get("file")
    if not file_obj or not hasattr(file_obj, "read"):
        raise HTTPException(status_code=400, detail="No file uploaded")

    filename: str = getattr(file_obj, "filename", "upload.bin") or "upload.bin"
    ext = os.path.splitext(filename)[1].lower() or ".jpg"
    if ext not in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {ext}")

    from config import GD_BASE_PATH
    game_dir = os.path.join(GD_BASE_PATH, "resources", "games", str(game_id))
    os.makedirs(game_dir, exist_ok=True)

    if media_type == "screenshot":
        filename_out = f"screenshot_{uuid.uuid4().hex[:8]}{ext}"
    else:
        filename_out = f"{media_type}{ext}"

    dest = os.path.join(game_dir, filename_out)
    data = await file_obj.read()
    with open(dest, "wb") as f:
        f.write(data)

    local_path = f"/resources/games/{game_id}/{filename_out}"

    # Update DB
    if media_type == "cover":
        fields = {"cover_path": local_path, "cover_url": None}
    elif media_type == "background":
        fields = {"background_path": local_path}
    elif media_type == "logo":
        fields = {"logo_url": local_path}
    elif media_type == "icon":
        fields = {"icon_path": local_path}
    elif media_type == "screenshot":
        existing = list(game.screenshots or [])
        existing.append(local_path)
        fields = {"screenshots": existing}
    else:
        fields = {}

    if fields:
        await gog_sync_handler.update_fields(game_id, fields)

    return {"ok": True, "path": local_path}


@gog_router.get("/library/count")
async def library_count(request: Request) -> dict:
    _require_scope(request, Scope.GOG_READ)
    from handler.gog.gog_sync_handler import gog_sync_handler
    n = await gog_sync_handler.count()
    return {"count": n}


# ── SRL (System Requirements Lab) ─────────────────────────────────────────────

@gog_router.get("/srl/search")
async def srl_search(request: Request, q: str = Query(..., description="Game title to search")) -> dict:
    """Search SRL for a game title. Returns top matches (title + URL + score)."""
    _require_scope(request, Scope.GOG_READ)
    import re as _re
    from urllib.parse import urljoin
    import httpx as _httpx
    from bs4 import BeautifulSoup

    BASE = "https://www.systemrequirementslab.com"
    HDRS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

    def _norm(t: str) -> str:
        t = t.lower().strip().replace("&", "and")
        t = _re.sub(r"[^a-z0-9\s-]", " ", t)
        return _re.sub(r"\s+", " ", t).strip()

    def _score(query: str, candidate: str) -> float:
        q, c = _norm(query), _norm(candidate)
        if not q or not c: return 0.0
        if q == c: return 1.0
        qs, cs = set(q.split()), set(c.split())
        s = len(qs & cs) / max(len(qs), 1) * 0.6
        if qs.issubset(cs): s += 0.25
        if q in c:          s += 0.15
        if c.startswith(q): s += 0.10
        s -= min(len(cs - qs) * 0.03, 0.15)
        s -= min(len(qs - cs) * 0.20, 0.60)
        return max(min(s, 0.99), 0.0)

    norm = _norm(q)
    filter_val = norm[0] if norm and norm[0].isalnum() else "a"

    try:
        async with _httpx.AsyncClient(headers=HDRS, follow_redirects=True, timeout=20) as client:
            r = await client.get(f"{BASE}/all-games-list/?filter={filter_val}")
            r.raise_for_status()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"SRL unreachable: {exc}")

    soup = BeautifulSoup(r.text, "html.parser")
    games: list[dict] = []
    seen: set[tuple] = set()
    for a in soup.find_all("a", href=True):
        href   = (a.get("href") or "").strip()
        gtitle = a.get_text(" ", strip=True)
        if not href or not gtitle: continue
        full = urljoin(BASE, href)
        if "/requirements/" not in full: continue
        if not _re.search(r"/requirements/.+/\d+$", full): continue
        key = (_norm(gtitle), full)
        if key in seen: continue
        seen.add(key)
        if "/cyri/" not in full:
            full = full.replace("/requirements/", "/cyri/requirements/", 1)
        games.append({"title": gtitle, "url": full})

    scored = sorted(
        [(_score(q, g["title"]), g) for g in games],
        key=lambda x: x[0], reverse=True,
    )[:8]

    return {
        "query":   q,
        "matches": [
            {"title": g["title"], "url": g["url"], "score": round(s, 3)}
            for s, g in scored
        ],
    }


@gog_router.get("/srl/fetch")
async def srl_fetch(request: Request, url: str = Query(..., description="SRL requirements page URL")) -> dict:
    """Fetch and parse requirements from a given SRL URL."""
    _require_scope(request, Scope.GOG_READ)
    from handler.gog.srl_handler import fetch_requirements, _BASE

    # Validate URL is from SRL
    if not url.startswith(_BASE):
        raise HTTPException(status_code=400, detail="URL must be from systemrequirementslab.com")

    # Use a dummy title (we already have the URL, skip search step)
    import httpx as _httpx
    from bs4 import BeautifulSoup
    from handler.gog.srl_handler import _find_container, _extract_section, _HDRS

    try:
        async with _httpx.AsyncClient(headers=_HDRS, follow_redirects=True, timeout=20) as client:
            pr = await client.get(url)
            pr.raise_for_status()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"SRL fetch failed: {exc}")

    page = BeautifulSoup(pr.text, "html.parser")
    min_cont = _find_container(page, ["minimum", "min-req", "minreq"])
    minimum  = _extract_section(min_cont) if min_cont else _extract_section(page)
    rec_cont = _find_container(page, ["recommended", "rec-req", "recreq", "suggest"])
    recommended = (
        _extract_section(rec_cont)
        if rec_cont and rec_cont is not min_cont else {}
    )

    if not minimum:
        raise HTTPException(status_code=404, detail="No requirements found on this page")

    return {"minimum": minimum, "recommended": recommended}


# ── Per-user GOG endpoints (any authenticated user) ──────────────────────────

@gog_router.get("/user/auth/url")
async def user_gog_auth_url(request: Request) -> dict:
    """Return GOG auth URL for the user to open in browser."""
    _require_auth(request)
    return {"url": gog_auth_handler.get_auth_url()}


@gog_router.get("/user/auth/status")
async def user_gog_status(request: Request) -> dict:
    """Get current user's GOG connection status."""
    _require_auth(request)
    user_id = request.state.user.id
    status = await gog_auth_handler.get_status(user_id=user_id)
    if status.get("authenticated"):
        from handler.database.session import async_session_factory
        from sqlalchemy import func, select as _sel
        from models.gog_game import GogGame
        async with async_session_factory() as session:
            count = (await session.execute(
                _sel(func.count(GogGame.id)).where(GogGame.owner_user_id == user_id)
            )).scalar() or 0
        status["game_count"] = count
    return status


@gog_router.post("/user/auth/callback")
async def user_gog_callback(request: Request, req: GogCodeRequest) -> dict:
    """User connects their GOG account."""
    _require_auth(request)
    user_id = request.state.user.id
    try:
        result = await gog_auth_handler.exchange_code(req.code, user_id=user_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"GOG authentication failed: {str(e)}")


@gog_router.delete("/user/auth")
async def user_gog_disconnect(request: Request) -> dict:
    """User disconnects GOG - removes their non-downloaded games and requests."""
    _require_auth(request)
    user_id = request.state.user.id
    await gog_auth_handler.disconnect(user_id=user_id)
    # Also delete user's non-downloaded GOG games and gog_user requests
    from handler.database.session import async_session_factory
    from sqlalchemy import delete as _del
    from models.gog_game import GogGame
    from models.game_request import GameRequest
    async with async_session_factory() as session:
        async with session.begin():
            await session.execute(
                _del(GogGame).where(
                    GogGame.owner_user_id == user_id,
                    GogGame.is_downloaded == False,
                )
            )
            await session.execute(
                _del(GameRequest).where(
                    GameRequest.user_id == user_id,
                    GameRequest.platform == "gog_user",
                )
            )
    return {"ok": True}


@gog_router.post("/user/library/sync")
async def user_gog_sync(request: Request) -> dict:
    """Sync current user's GOG library."""
    _require_auth(request)
    user_id = request.state.user.id
    from handler.gog.gog_sync_handler import gog_sync_handler
    result = await gog_sync_handler.sync_library(user_id=user_id)
    return result


@gog_router.get("/user/library/games")
async def user_gog_games(request: Request) -> list:
    """Get current user's GOG games list."""
    _require_auth(request)
    user_id = request.state.user.id
    from handler.database.session import async_session_factory
    from sqlalchemy import select as _sel
    from models.gog_game import GogGame
    async with async_session_factory() as session:
        rows = (await session.execute(
            _sel(GogGame)
            .where(GogGame.owner_user_id == user_id)
            .order_by(GogGame.title)
        )).scalars().all()
        return [
            {
                "id":           g.id,
                "gog_id":       g.gog_id,
                "title":        g.title,
                "slug":         g.slug,
                "cover_url":    g.cover_url,
                "release_date": g.release_date,
            }
            for g in rows
        ]
