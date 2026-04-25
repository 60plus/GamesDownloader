"""IGDB metadata scraper for ROM games.

Uses the IGDB (Twitch) API v4.  Credentials (client_id + client_secret)
are stored via config_handler (same keys used by the regular library scraper).
"""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_TOKEN_URL  = "https://id.twitch.tv/oauth2/token"
_IGDB_URL   = "https://api.igdb.com/v4"

_token_cache: dict[str, Any] = {}   # { access_token, expires_at }


async def _get_access_token(client_id: str, client_secret: str) -> str:
    now = time.time()
    if _token_cache.get("access_token") and _token_cache.get("expires_at", 0) > now + 60:
        return _token_cache["access_token"]

    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.post(_TOKEN_URL, params={
            "client_id":     client_id,
            "client_secret": client_secret,
            "grant_type":    "client_credentials",
        })
        r.raise_for_status()
        data = r.json()

    _token_cache["access_token"] = data["access_token"]
    _token_cache["expires_at"]   = now + data.get("expires_in", 3600)
    return _token_cache["access_token"]


async def _igdb_post(endpoint: str, body: str, client_id: str, client_secret: str) -> list[dict]:
    token = await _get_access_token(client_id, client_secret)
    headers = {
        "Client-ID":     client_id,
        "Authorization": f"Bearer {token}",
        "Accept":        "application/json",
    }
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(f"{_IGDB_URL}/{endpoint}", content=body, headers=headers)
        if r.status_code != 200:
            logger.warning("IGDB %s returned %d: %s", endpoint, r.status_code, r.text[:200])
            return []
        return r.json()


async def search_game(
    name: str,
    igdb_platform_id: int | None,
    *,
    client_id: str,
    client_secret: str,
) -> dict | None:
    """Search IGDB for a game by name (+ optional platform filter).

    Returns the best match as a raw IGDB game dict, or None.
    """
    platform_filter = f" & platforms = ({igdb_platform_id})" if igdb_platform_id else ""
    query = (
        f'fields name, slug, summary, cover.url, '
        f'screenshots.url, genres.name, first_release_date, '
        f'involved_companies.company.name, involved_companies.developer, '
        f'involved_companies.publisher, rating, platforms.id, '
        f'artworks.url, player_perspectives.name;'
        f' where name ~ *"{name}"*{platform_filter};'
        f' limit 5;'
    )
    results = await _igdb_post("games", query, client_id, client_secret)
    if not results:
        # Retry without platform filter if no results
        if igdb_platform_id:
            query2 = query.replace(f" & platforms = ({igdb_platform_id})", "")
            results = await _igdb_post("games", query2, client_id, client_secret)

    if not results:
        return None

    # Pick closest name match
    name_lower = name.lower()
    best = min(
        results,
        key=lambda g: _name_distance(name_lower, g.get("name", "").lower()),
    )
    return best


def _name_distance(a: str, b: str) -> int:
    """Simple Levenshtein distance for picking best title match."""
    if a == b:
        return 0
    la, lb = len(a), len(b)
    if la == 0: return lb
    if lb == 0: return la
    prev = list(range(lb + 1))
    for i, ca in enumerate(a):
        curr = [i + 1]
        for j, cb in enumerate(b):
            curr.append(min(prev[j + 1] + 1, curr[j] + 1, prev[j] + (ca != cb)))
        prev = curr
    return prev[lb]


def extract_metadata(game: dict) -> dict:
    """Convert raw IGDB game dict into normalised ROM metadata."""
    # Cover URL: https: prefixed, use t_cover_big size
    cover_url = None
    if game.get("cover"):
        raw = game["cover"].get("url", "")
        cover_url = _fix_igdb_url(raw, "t_cover_big")

    # Background: prefer artworks, fallback to first screenshot
    bg_url = None
    if game.get("artworks"):
        bg_url = _fix_igdb_url(game["artworks"][0].get("url", ""), "t_screenshot_big")
    elif game.get("screenshots"):
        bg_url = _fix_igdb_url(game["screenshots"][0].get("url", ""), "t_screenshot_big")

    screenshots = []
    for ss in (game.get("screenshots") or [])[:6]:
        u = _fix_igdb_url(ss.get("url", ""), "t_screenshot_big")
        if u:
            screenshots.append(u)

    genres = [g["name"] for g in (game.get("genres") or [])]

    developer  = None
    publisher  = None
    for ic in (game.get("involved_companies") or []):
        co = ic.get("company", {}).get("name")
        if ic.get("developer") and not developer:
            developer = co
        if ic.get("publisher") and not publisher:
            publisher = co

    rating = game.get("rating")
    if rating:
        rating = round(rating / 10, 1)   # IGDB 0–100 → 0–10

    release_year = None
    ts = game.get("first_release_date")
    if ts:
        from datetime import datetime, timezone
        release_year = datetime.fromtimestamp(ts, tz=timezone.utc).year

    return {
        "igdb_id":        game.get("id"),
        "name":           game.get("name"),
        "slug":           game.get("slug"),
        "summary":        game.get("summary"),
        "developer":      developer,
        "publisher":      publisher,
        "release_year":   release_year,
        "genres":         genres,
        "rating":         rating,
        "cover_url":      cover_url,
        "background_url": bg_url,
        "screenshots":    screenshots,
        "igdb_metadata":  game,
        "is_identified":  True,
    }


async def search_games(
    name: str,
    igdb_platform_id: int | None = None,
    *,
    client_id: str,
    client_secret: str,
) -> list[dict]:
    """Search IGDB, return up to 10 simplified results for the panel search grid."""
    platform_filter = f" & platforms = ({igdb_platform_id})" if igdb_platform_id else ""
    query = (
        f'fields id, name, url, cover.url, first_release_date, '
        f'involved_companies.company.name, involved_companies.developer;'
        f' where name ~ *"{name}"*{platform_filter}; limit 10;'
    )
    results = await _igdb_post("games", query, client_id, client_secret)
    if not results and igdb_platform_id:
        query2 = query.replace(f" & platforms = ({igdb_platform_id})", "")
        results = await _igdb_post("games", query2, client_id, client_secret)

    out = []
    for game in results:
        cover_url = None
        if game.get("cover"):
            cover_url = _fix_igdb_url(game["cover"].get("url", ""), "t_cover_big")
        year = None
        ts = game.get("first_release_date")
        if ts:
            from datetime import datetime, timezone
            year = datetime.fromtimestamp(ts, tz=timezone.utc).year
        dev = None
        for ic in (game.get("involved_companies") or []):
            if ic.get("developer"):
                dev = (ic.get("company") or {}).get("name")
                break
        out.append({
            "source":    "igdb",
            "ss_id":     None,
            "igdb_id":   game.get("id"),
            "name":      game.get("name", ""),
            "year":      year,
            "developer": dev,
            "cover_url": cover_url,
            "url":       game.get("url"),
            "regions":   [],
        })
    return out


async def get_game_by_id(
    igdb_id: int,
    *,
    client_id: str,
    client_secret: str,
) -> dict | None:
    """Fetch full IGDB game data by ID."""
    query = (
        f'fields name, slug, summary, cover.url, screenshots.url, artworks.url, '
        f'genres.name, first_release_date, involved_companies.company.name, '
        f'involved_companies.developer, involved_companies.publisher, rating;'
        f' where id = {igdb_id};'
    )
    results = await _igdb_post("games", query, client_id, client_secret)
    return results[0] if results else None


def extract_media_urls(game: dict) -> dict:
    """Extract covers, fanarts, screenshots from an IGDB game dict.

    Returns same structure as screenscraper_handler.extract_media_urls()
    but only covers/fanarts/screenshots (IGDB has no support/wheel/bezel/steamgrid/video).
    Each item has source='igdb'.
    """
    covers = []
    if game.get("cover"):
        url = _fix_igdb_url(game["cover"].get("url", ""), "t_cover_big")
        if url:
            covers.append({"url": url, "type": "cover", "label": "Cover", "source": "igdb"})

    fanarts = []
    for aw in (game.get("artworks") or [])[:12]:
        url = _fix_igdb_url(aw.get("url", ""), "t_1080p")
        if url:
            fanarts.append({"url": url, "type": "artwork", "label": "Artwork", "source": "igdb"})

    screenshots = []
    for ss in (game.get("screenshots") or [])[:12]:
        url = _fix_igdb_url(ss.get("url", ""), "t_screenshot_big")
        if url:
            screenshots.append({"url": url, "type": "screenshot", "label": "Screenshot", "source": "igdb"})

    return {"covers": covers, "fanarts": fanarts, "screenshots": screenshots}


def _fix_igdb_url(url: str, size: str) -> str | None:
    if not url:
        return None
    url = url.replace("//", "https://", 1) if url.startswith("//") else url
    # Replace any existing size token
    import re
    url = re.sub(r"/t_[a-z_]+/", f"/{size}/", url)
    return url
