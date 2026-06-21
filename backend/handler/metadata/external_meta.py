"""Shared external metadata-source search (description / details) by NAME.

Extracted verbatim from the game editor's `meta-sources` endpoint so the SAME
provider logic (GOG, RAWG, IGDB, Steam) is reused for collections. RAWG / IGDB /
Steam search purely by name; GOG is game-row-based (returns a game's stored data
or a fresh fetch by its gog_id), so it is only available when a `game` is passed
(collections have no GOG product and get RAWG / IGDB / Steam descriptions).
"""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)


def _sanitize_search(term: str) -> str:
    """Strip characters that could inject into IGDB Apicalypse query strings."""
    return term.replace('"', '').replace("'", '').replace(';', '').strip()[:128]


async def search_meta_source(
    source: str,
    search_term: str,
    raw_q: str = "",
    *,
    game=None,
) -> dict:
    """Full metadata (description, dev/pub, rating, genres, ...) from one source.

    source: gog | rawg | rawg-detail | igdb | steam
    search_term: the name to search (already resolved from q or title/name)
    raw_q: the original q param (rawg-detail slug/id, steam app id parsing)
    game: optional GogGame row (enables the GOG stored-data path).
    """
    result: dict = {"source": source, "found": False}

    if source == "gog":
        if game is None:
            # Collections have no GOG product - description comes from RAWG/IGDB/Steam.
            return {"source": "gog", "found": False}
        # If metadata is cleared, fetch fresh from GOG API
        has_data = bool(game.developer or game.description or game.genres)
        if not has_data and game.gog_id:
            try:
                from handler.library.library_scrape_handler import _abs_url  # noqa: F401
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
                sr = await c.get(
                    "https://api.rawg.io/api/games",
                    params={"key": api_key, "search": search_term, "page_size": 5},
                )
                if sr.status_code != 200:
                    return {"source": "rawg", "found": False, "error": f"RAWG search returned {sr.status_code}"}
                search_results = sr.json().get("results", [])
                if not search_results:
                    return {"source": "rawg", "found": False, "error": "No results found"}

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
        # Fetch full details for a specific RAWG game id/slug (held in raw_q).
        rawg_id = raw_q
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

                requirements: dict = {}
                for pdata in d.get("platforms", []):
                    pname = (pdata.get("platform") or {}).get("name", "")
                    reqs = pdata.get("requirements") or {}
                    if reqs and ("minimum" in reqs or "recommended" in reqs):
                        requirements[pname] = reqs

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
            app_id: int | None = parse_steam_app_id(raw_q) if raw_q else None
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
