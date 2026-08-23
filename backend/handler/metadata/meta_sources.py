"""Fetch game metadata from one external source by title.

Extracted from the library router's Edit-Metadata endpoint so a catalogue entry
(PC Ports and the like) can offer the same "search all sources" the GOG and
Games editors do, without duplicating the per-source request logic. The library
game endpoint and the catalogue-entry endpoint both call fetch_meta_source; the
only thing they resolve differently is the optional linked GOG id.

source: gog | rawg | rawg-detail | igdb | steam
search_term: the title to look up (already resolved from q or the record title)
q: the raw override the caller typed - used directly as a RAWG slug/id or a
   Steam app id/URL, where a title search is not what was meant
gog_id: a known GOG id to skip the catalogue search (a published GOG game has one)
"""

from __future__ import annotations

from typing import Any

import httpx

from utils.apicalypse import sanitize_search
from handler.metadata.igdb_auth import igdb_headers


async def fetch_meta_source(
    source: str, *, search_term: str, q: str = "", gog_id: int | None = None,
) -> dict[str, Any]:
    search_term = (search_term or "").strip()
    result: dict = {"source": source, "found": False}

    # ── GOG public catalog (no auth) ──────────────────────────────────────────
    if source == "gog":
        from handler.gog_web import GOG_GALAXY_HEADERS, gog_image_url
        from handler.library.library_scrape_handler import (
            _search_gog_catalog, _fetch_gog_v1, _fetch_gog_v2, _fetch_gog_rating,
        )
        import asyncio as _aio
        try:
            async with httpx.AsyncClient(headers=GOG_GALAXY_HEADERS, follow_redirects=True, timeout=20) as c:
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
                cover  = gog_image_url(str(cover)) if cover else ""

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
            safe_q = sanitize_search(search_term)
            async with httpx.AsyncClient(timeout=20) as c:
                headers = await igdb_headers(client_id, client_secret)
                if headers is None:
                    return {"source": "igdb", "found": False, "error": "Twitch auth failed"}
                gr = await c.post(
                    "https://api.igdb.com/v4/games",
                    headers=headers,
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
                        # The collection editor shows the storyline on its own,
                        # separately from the description it is folded into here.
                        "storyline":         ig.get("storyline", ""),
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
