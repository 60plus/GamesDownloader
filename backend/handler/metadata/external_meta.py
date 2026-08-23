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


from utils.apicalypse import sanitize_search as _sanitize_search
from handler.gog_web import GOG_JSON_HEADERS
from handler.metadata.igdb_auth import igdb_headers


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
                async with httpx.AsyncClient(timeout=15, headers=GOG_JSON_HEADERS) as c:
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

    elif source in ("rawg", "rawg-detail", "igdb", "steam"):
        # These four search by name and know nothing about a game row, so they
        # are the same work in both editors. The implementation lives in
        # meta_sources; it returns a superset of what this caller reads, and
        # the extra keys (the OS flags and the language table a library game
        # can store) are simply ignored here.
        from handler.metadata.meta_sources import fetch_meta_source
        return await fetch_meta_source(source, search_term=search_term, q=raw_q)

    return result
