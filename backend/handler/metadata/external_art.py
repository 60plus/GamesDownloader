"""Shared external-art search (covers / heroes / logos / icons) by NAME.

Extracted verbatim from the game metadata editor's cover endpoint so the SAME
provider logic (GOG, IGDB, SteamGridDB, RAWG, LaunchBox, plugins) is reused for
collections. Every source searches by the query string alone - no game id - so
the game route passes `q or game.title` (+ the linked gog id for a precise GOG
lookup) and the collection route passes the collection name.
"""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)

_SGDB_ANIMATED_MIMES = ("video/webm", "image/gif", "image/webp")


async def search_cover_options(
    source: str,
    search_term: str,
    asset_type: str = "grids",
    animated: str = "any",
    *,
    gog_game_id: int | None = None,
) -> list[dict]:
    """Cover/hero/logo image options for a title from one external source.

    source: gog | igdb | steamgriddb | rawg | launchbox | plugins
    asset_type: grids | heroes | logos | icons
    animated: any | only | exclude
    gog_game_id: optional linked GOG game id for a precise GOG lookup.
    """
    search_term = (search_term or "").strip()
    if not search_term:
        return []
    results: list = []

    if source == "gog":
        try:
            from handler.library.library_scrape_handler import _abs_url
            _GOG_CATALOG = "https://catalog.gog.com/v1/catalog"
            _GOG_V2 = "https://api.gog.com/v2/games/{gog_id}?locale=en-US"
            _HDRS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) GOGGalaxy/2.0", "Accept": "application/json"}

            # If a linked GOG game id is supplied, use it for a precise lookup.
            gog_product_id = None
            if gog_game_id:
                from models.gog_game import GogGame
                from handler.database.session import async_session_factory
                async with async_session_factory() as s:
                    gog_game = await s.get(GogGame, gog_game_id)
                    if gog_game:
                        gog_product_id = gog_game.gog_id

            async with httpx.AsyncClient(timeout=10, headers=_HDRS) as c:
                if gog_product_id:
                    r = await c.get(_GOG_V2.format(gog_id=gog_product_id))
                    if r.status_code == 200:
                        data = r.json()
                        links = data.get("_links") or {}
                        box_art = (links.get("boxArtImage") or {}).get("href")
                        bg = ((links.get("galaxyBackgroundImage") or {}).get("href")
                              or (links.get("backgroundImage") or {}).get("href"))
                        logo = (links.get("logo") or {}).get("href")
                        t = data.get("_embedded", {}).get("product", {}).get("title", search_term)
                        if box_art:
                            results.append({"url": _abs_url(box_art), "thumb": _abs_url(box_art),
                                            "type": "static", "label": f"{t} - Box Art"})
                        if bg:
                            results.append({"url": _abs_url(bg), "thumb": _abs_url(bg),
                                            "type": "static", "label": f"{t} - Background"})
                        if logo:
                            results.append({"url": _abs_url(logo), "thumb": _abs_url(logo),
                                            "type": "static", "label": f"{t} - Logo"})

                # Also search the catalog by title for additional results.
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
                        # webm is a video container: <img> cannot play it and the
                        # media downloader would save it with an image extension,
                        # leaving a broken cover - only offer webp/gif animations.
                        if mime == "video/webm":
                            continue
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
