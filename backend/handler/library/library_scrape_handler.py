"""Library game metadata scraper.

Scrapes metadata for LibraryGame records from multiple public sources.
Sources are applied in priority order; each one fills only fields still missing.

Priority:
  1. GOG public API  - description, cover, screenshots, videos, genres, features, requirements
  2. Steam Store API - fallback description, requirements, OS flags, Metacritic rating
  3. RAWG            - rating, requirements fallback
  4. IGDB            - rating
  5. SRL             - last resort for system requirements
"""

from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# ── GOG public endpoints (no auth required) ────────────────────────────────────
_GOG_CATALOG   = "https://catalog.gog.com/v1/catalog"
_GOG_V1        = "https://api.gog.com/products/{gog_id}?expand=description,screenshots,videos,system_requirements&locale=en-US"
_GOG_V2        = "https://api.gog.com/v2/games/{gog_id}?locale=en-US"
_GOG_REVIEWS   = "https://reviews.gog.com/v1/products/{gog_id}/reviews?language=in:en-US&limit=1"

_HDRS = {
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) GOGGalaxy/2.0",
    "Accept":          "application/json",
    "Accept-Language": "en-US,en;q=0.9",
}


# ── Image helpers ──────────────────────────────────────────────────────────────

def _titles_similar(query: str, result: str, threshold: float = 0.55) -> bool:
    """Return True if *result* title is close enough to *query* to be considered a match.

    Uses word-overlap ratio after stripping punctuation.  Handles cases like
    'Terminator 2D - NO FATE' vs 'Terminator 2D: No Fate' (same game, different
    punctuation) and rejects completely unrelated results like 'Agony Unrated'.
    """
    norm = lambda s: re.sub(r"[^\w\s]", " ", s.lower()).split()
    q_words = set(norm(query))
    r_words = set(norm(result))
    if not q_words or not r_words:
        return False
    # Direct containment (after normalisation)
    q_str = " ".join(sorted(q_words))
    r_str = " ".join(sorted(r_words))
    if q_str == r_str or q_str in r_str or r_str in q_str:
        return True
    overlap  = len(q_words & r_words)
    shorter  = min(len(q_words), len(r_words))
    return (overlap / shorter) >= threshold if shorter else False


def _abs_url(url: str) -> str:
    if not url:
        return ""
    if url.startswith("//"):
        return "https:" + url
    if url.startswith("/"):
        return "https://images.gog.com" + url
    return url


def _yt_id(url: str) -> str:
    """Extract YouTube video ID from embed or watch URL."""
    if not url:
        return ""
    m = re.search(r"(?:youtu\.be/|/embed/|[?&]v=)([a-zA-Z0-9_-]{11})", url)
    return m.group(1) if m else ""


# ── GOG catalog search ─────────────────────────────────────────────────────────

async def _search_gog_catalog(title: str, client: httpx.AsyncClient) -> int | None:
    """Search GOG catalog by title. Returns numeric product ID or None."""
    try:
        r = await client.get(
            _GOG_CATALOG,
            params={
                "query":       title,
                "productType": "in:game,pack",
                "limit":       "10",
                "locale":      "en-US",
                "order":       "desc:score",
            },
            timeout=10,
        )
        if r.status_code != 200:
            return None
        products = r.json().get("products") or []
        if not products:
            return None
        # Find the best match: exact title first, then first similar result
        title_lower = title.lower()
        for p in products:
            if (p.get("title") or "").lower() == title_lower:
                return p.get("id")
        # Fall back to first result only if its title is similar enough
        first = products[0]
        if _titles_similar(title, first.get("title") or ""):
            return first.get("id")
        logger.debug("GOG catalog: no similar match for '%s' (first result: '%s')",
                     title, first.get("title"))
        return None
    except Exception as exc:
        logger.debug("GOG catalog search failed for '%s': %s", title, exc)
        return None


async def _fetch_gog_v1(gog_id: int, client: httpx.AsyncClient) -> dict:
    try:
        r = await client.get(_GOG_V1.format(gog_id=gog_id), timeout=15)
        r.raise_for_status()
        return r.json()
    except Exception as exc:
        logger.debug("GOG v1 failed for id=%s: %s", gog_id, exc)
        return {}


async def _fetch_gog_v2(gog_id: int, client: httpx.AsyncClient) -> dict:
    try:
        r = await client.get(_GOG_V2.format(gog_id=gog_id), timeout=15)
        r.raise_for_status()
        return r.json()
    except Exception as exc:
        logger.debug("GOG v2 failed for id=%s: %s", gog_id, exc)
        return {}


async def _fetch_gog_rating(gog_id: int, client: httpx.AsyncClient) -> float | None:
    try:
        r = await client.get(_GOG_REVIEWS.format(gog_id=gog_id), timeout=10)
        if r.status_code == 200:
            data = r.json()
            v = data.get("overallAvgRating") or data.get("filteredAvgRating")
            if v is not None:
                return float(v)
    except Exception as exc:
        logger.debug("GOG reviews failed for id=%s: %s", gog_id, exc)
    return None


# ── Data applier for LibraryGame ───────────────────────────────────────────────

def _apply_gog_v1v2(game: Any, v1: dict, v2: dict, rating: float | None) -> list[str]:
    """Merge GOG v1/v2 data into a LibraryGame ORM instance. Returns list of applied fields."""
    applied: list[str] = []

    # Description
    desc = v1.get("description") or {}
    if isinstance(desc, dict):
        full  = desc.get("full") or ""
        short = desc.get("short") or ""
        if full and not game.description:
            game.description = full
            applied.append("description")
        if short and not game.description_short:
            game.description_short = short
            applied.append("description_short")
    elif isinstance(desc, str) and desc and not game.description:
        game.description = desc
        applied.append("description")

    # Rating (GOG scale 0-5; stored in game.rating)
    if rating is not None and not game.rating:
        try:
            game.rating = float(rating)
            applied.append("rating(gog)")
        except (ValueError, TypeError):
            pass
    elif v1.get("rating") and not game.rating:
        try:
            r = float(v1["rating"])
            if r > 0:
                # GOG v1 rating is stored ×10 (e.g. 45 = 4.5 stars)
                game.rating = r / 10 if r > 10 else r
                applied.append("rating(gog)")
        except (ValueError, TypeError):
            pass

    # Release date
    rd = v1.get("release_date")
    if rd and not game.release_date:
        if isinstance(rd, dict):
            date_str = (rd.get("date") or "")[:10]
        elif isinstance(rd, (int, float)) and rd > 0:
            from datetime import datetime, timezone
            date_str = datetime.fromtimestamp(rd, tz=timezone.utc).strftime("%Y-%m-%d")
        else:
            date_str = str(rd)[:10]
        if date_str and len(date_str) >= 10:
            game.release_date = date_str
            applied.append("release_date")

    # Images - store as URLs (frontend handles both local paths and HTTP URLs)
    images = v1.get("images") or {}
    if not game.background_path:
        bg = (images.get("background")
              or images.get("sidebarGraphicHi")
              or images.get("sidebarGraphicLo"))
        if not bg:
            links = v2.get("_links") or {}
            bg = ((links.get("galaxyBackgroundImage") or {}).get("href")
                  or (links.get("backgroundImage") or {}).get("href"))
        if bg:
            game.background_path = _abs_url(str(bg))
            applied.append("background")

    if not game.cover_path:
        links = v2.get("_links") or {}
        cover = (links.get("boxArtImage") or {}).get("href")
        if not cover:
            cover = (images.get("coverLarge") or images.get("cover")
                     or images.get("logo2x") or images.get("logo") or "")
        if cover:
            game.cover_path = _abs_url(str(cover))
            applied.append("cover")

    # Screenshots
    ss_raw = v1.get("screenshots") or []
    if ss_raw and not game.screenshots:
        img_base = "https://images.gog-statics.com/"

        def _img_url(image_id: str) -> str:
            if not image_id:
                return ""
            if image_id.startswith("http") or image_id.startswith("//"):
                return _abs_url(image_id)
            return f"{img_base}{image_id}.jpg"

        urls = [_img_url(s.get("image_id", "")) for s in ss_raw if s.get("image_id")]
        urls = [u for u in urls if u]
        if urls:
            game.screenshots = urls
            applied.append("screenshots")

    # Videos
    vids_raw = v1.get("videos") or []
    if isinstance(vids_raw, dict):
        vids_raw = vids_raw.get("items") or vids_raw.get("videos") or []
    vids = list(vids_raw) if isinstance(vids_raw, list) else []
    if vids and not game.videos:
        parsed = []
        for v in vids:
            vid_id = (v.get("videoId") or v.get("video_id")
                      or _yt_id(v.get("video_url", ""))
                      or _yt_id(v.get("url", "")))
            if vid_id:
                parsed.append({
                    "provider":     v.get("provider", "youtube"),
                    "video_id":     vid_id,
                    "thumbnail_id": v.get("thumbnailId") or v.get("thumbnail_id", ""),
                })
        if parsed:
            game.videos = parsed
            applied.append("videos")
    # v2 trailer fallback
    if not game.videos:
        links_v2 = v2.get("_links") or {}
        trailer_href = ((links_v2.get("trailer") or {}).get("href")
                        or (links_v2.get("video") or {}).get("href") or "")
        if trailer_href:
            yt_m = re.search(r"(?:v=|youtu\.be/)([a-zA-Z0-9_-]{11})", trailer_href)
            if yt_m:
                game.videos = [{"provider": "youtube", "video_id": yt_m.group(1), "thumbnail_id": ""}]
                applied.append("videos(trailer)")

    # Features
    feats = v1.get("features") or []
    if feats and not game.features:
        game.features = [
            f.get("name") if isinstance(f, dict) else str(f)
            for f in feats if f
        ]
        applied.append("features")

    # Languages
    raw_langs = v1.get("languages")
    if raw_langs and not game.languages:
        if isinstance(raw_langs, dict):
            game.languages = raw_langs
        elif isinstance(raw_langs, list):
            game.languages = {str(l): str(l) for l in raw_langs}
        applied.append("languages")

    # OS support
    compat = v1.get("content_system_compatibility") or {}
    if isinstance(compat, dict):
        if compat.get("windows") and not game.os_windows:
            game.os_windows = True
            applied.append("os_windows")
        if compat.get("osx") and not game.os_mac:
            game.os_mac = True
            applied.append("os_mac")
        if compat.get("linux") and not game.os_linux:
            game.os_linux = True
            applied.append("os_linux")

    # System requirements
    raw_reqs = v1.get("system_requirements")
    if raw_reqs and not game.requirements:
        if isinstance(raw_reqs, dict):
            reqs: dict = {}
            min_req = raw_reqs.get("minimum_system_requirements")
            rec_req = raw_reqs.get("recommended_system_requirements")
            if isinstance(min_req, dict) and min_req:
                reqs["minimum"] = min_req
            if isinstance(rec_req, dict) and rec_req:
                reqs["recommended"] = rec_req
            if "requirement_groups" in raw_reqs:
                reqs["per_os"] = raw_reqs["requirement_groups"]
            elif isinstance(raw_reqs.get("systems"), list):
                reqs["per_os"] = raw_reqs["systems"]
            if reqs:
                game.requirements = reqs
                applied.append("requirements(gog)")
        elif isinstance(raw_reqs, list) and raw_reqs:
            first = raw_reqs[0]
            first_type = first.get("type", "").lower()
            if first_type in ("minimum", "recommended"):
                game.requirements = {"per_os": [{"type": "windows", "requirement_groups": raw_reqs}]}
            elif isinstance(first.get("requirements"), list):
                reqs_flat: dict = {}
                for item in raw_reqs:
                    for r in (item.get("requirements") or []):
                        key = r.get("id") or (r.get("name") or "").lower().rstrip(": ").replace(" ", "_")
                        val = r.get("description") or ""
                        if key and val:
                            reqs_flat[key] = val
                if reqs_flat:
                    game.requirements = {"minimum": reqs_flat}
            else:
                game.requirements = {"per_os": raw_reqs}
            if game.requirements:
                applied.append("requirements(gog)")

    # Genres / tags / developer / publisher (v2 is richer)
    embedded = v2.get("_embedded") or {}
    all_tags = embedded.get("tags") or []
    if all_tags:
        genres = [t.get("name") for t in all_tags
                  if isinstance(t, dict) and t.get("type") == "genre" and t.get("name")]
        other_tags = [t.get("name") for t in all_tags
                      if isinstance(t, dict) and t.get("type") != "genre" and t.get("name")]
        if genres and not game.genres:
            game.genres = genres
            applied.append("genres")
        if other_tags and not game.tags:
            game.tags = other_tags
            applied.append("tags")

    devs = embedded.get("developers") or []
    if devs and not game.developer:
        game.developer = ", ".join(
            d.get("name") for d in devs if isinstance(d, dict) and d.get("name")
        )
        if game.developer:
            applied.append("developer")

    pub = embedded.get("publisher") or {}
    if isinstance(pub, dict) and pub.get("name") and not game.publisher:
        game.publisher = pub["name"]
        applied.append("publisher")

    return applied


# ── Steam fallback ─────────────────────────────────────────────────────────────

async def _apply_steam_fallback(game: Any) -> list[str]:
    """Fill missing fields from Steam Store API. Returns list of applied fields."""
    needs_desc        = not game.description
    needs_dev         = not game.developer
    needs_pub         = not game.publisher
    needs_genres      = not game.genres
    needs_features    = not game.features
    needs_os          = not (game.os_windows or game.os_mac or game.os_linux)
    needs_date        = not game.release_date
    needs_reqs        = not game.requirements
    needs_screenshots = not game.screenshots or len(game.screenshots) < 3
    needs_steam_mc    = not (game.meta_ratings or {}).get("steam")
    needs_langs       = not game.languages

    if not any([needs_desc, needs_dev, needs_pub, needs_genres, needs_features,
                needs_os, needs_date, needs_reqs, needs_screenshots, needs_steam_mc,
                needs_langs]):
        return []

    try:
        from handler.gog.steam_scraper import search_steam_app, fetch_steam_app_details
    except ImportError:
        return []

    try:
        app_id = await search_steam_app(game.title or "")
    except Exception:
        return []
    if not app_id:
        return []

    try:
        steam = await fetch_steam_app_details(app_id)
    except Exception:
        return []
    if not steam:
        return []

    applied: list[str] = []

    if needs_desc and steam.get("description"):
        game.description = steam["description"]
        applied.append("description(steam)")
    if not game.description_short and steam.get("description_short"):
        game.description_short = steam["description_short"]
        applied.append("description_short(steam)")
    if needs_dev and steam.get("developer"):
        game.developer = steam["developer"]
        applied.append("developer(steam)")
    if needs_pub and steam.get("publisher"):
        game.publisher = steam["publisher"]
        applied.append("publisher(steam)")
    if needs_genres and steam.get("genres"):
        game.genres = steam["genres"]
        applied.append("genres(steam)")
    if needs_features and steam.get("features"):
        game.features = steam["features"]
        applied.append("features(steam)")
    if needs_os:
        if steam.get("os_windows"):
            game.os_windows = True
            applied.append("os_windows(steam)")
        if steam.get("os_mac"):
            game.os_mac = True
            applied.append("os_mac(steam)")
        if steam.get("os_linux"):
            game.os_linux = True
            applied.append("os_linux(steam)")
    if needs_date and steam.get("release_date"):
        game.release_date = steam["release_date"]
        applied.append("release_date(steam)")
    if needs_reqs and steam.get("requirements"):
        game.requirements = steam["requirements"]
        applied.append("requirements(steam)")
    if steam.get("rating") is not None:
        existing = dict(game.meta_ratings or {})
        if "steam" not in existing:
            existing["steam"] = steam["rating"]
            game.meta_ratings = existing
            applied.append("rating(metacritic)")
    if needs_screenshots and steam.get("screenshots"):
        existing = game.screenshots or []
        combined = list(existing) + [s for s in steam["screenshots"] if s not in existing]
        game.screenshots = combined[:20]
        applied.append("screenshots(steam)")
    if needs_langs and steam.get("languages"):
        game.languages = steam["languages"]
        applied.append("languages(steam)")

    return applied


# ── RAWG + IGDB ratings ────────────────────────────────────────────────────────

async def _fetch_external_ratings(game: Any) -> list[str]:
    """Fetch RAWG + IGDB ratings into game.meta_ratings. Returns applied fields."""
    try:
        from handler.config.config_handler import config_handler
        rawg_key        = await config_handler.get("rawg_api_key")
        igdb_client_id  = await config_handler.get("igdb_client_id")
        igdb_client_sec = await config_handler.get("igdb_client_secret")
    except Exception:
        return []

    title = game.title or ""
    rawg_rating: float | None = None
    igdb_rating: float | None = None
    applied: list[str] = []

    async with httpx.AsyncClient(headers=_HDRS, follow_redirects=True, timeout=10) as c:
        # ── RAWG ──────────────────────────────────────────────────────────────
        if rawg_key:
            try:
                r = await c.get(
                    "https://api.rawg.io/api/games",
                    params={"key": rawg_key, "search": title, "page_size": 3},
                )
                if r.status_code == 200:
                    results = r.json().get("results", [])
                    # Pick best matching result (skip unrelated titles)
                    top = next(
                        (x for x in results
                         if _titles_similar(title, x.get("name") or x.get("slug") or "")),
                        None,
                    )
                    if top:
                        if top.get("rating"):
                            rawg_rating = float(top["rating"])
                        # RAWG requirements as fallback
                        if not game.requirements and top.get("slug"):
                            try:
                                dr = await c.get(
                                    f"https://api.rawg.io/api/games/{top['slug']}",
                                    params={"key": rawg_key},
                                )
                                if dr.status_code == 200:
                                    reqs: dict = {}
                                    for pdata in dr.json().get("platforms", []):
                                        pname = (pdata.get("platform") or {}).get("name", "")
                                        preqs = pdata.get("requirements") or {}
                                        if preqs and ("minimum" in preqs or "recommended" in preqs):
                                            reqs[pname] = preqs
                                    if reqs:
                                        game.requirements = reqs
                                        applied.append("requirements(rawg)")
                            except Exception:
                                pass
            except Exception as exc:
                logger.debug("RAWG fetch skipped for '%s': %s", title, exc)

        # ── IGDB ──────────────────────────────────────────────────────────────
        if igdb_client_id and igdb_client_sec:
            try:
                tr = await c.post(
                    "https://id.twitch.tv/oauth2/token",
                    params={
                        "client_id":     igdb_client_id,
                        "client_secret": igdb_client_sec,
                        "grant_type":    "client_credentials",
                    },
                )
                if tr.status_code == 200:
                    token = tr.json().get("access_token", "")
                    if token:
                        safe_title = title.replace('"', '').replace("'", '').replace(';', '').strip()[:128]
                        gr = await c.post(
                            "https://api.igdb.com/v4/games",
                            headers={
                                "Client-ID":     igdb_client_id,
                                "Authorization": f"Bearer {token}",
                            },
                            content=(
                                f'fields total_rating,aggregated_rating,summary,first_release_date,'
                                f'genres.name,involved_companies.company.name,involved_companies.developer,'
                                f'involved_companies.publisher,screenshots.url;'
                                f' search "{safe_title}"; limit 3;'
                            ),
                        )
                        if gr.status_code == 200 and gr.json():
                            # Pick the best-matching IGDB result; skip unrelated titles
                            ig_results = gr.json()
                            ig = next(
                                (x for x in ig_results
                                 if _titles_similar(title, x.get("name") or "")),
                                None,
                            )
                            if ig is None:
                                logger.debug(
                                    "IGDB: no similar match for '%s' (best: '%s')",
                                    title, ig_results[0].get("name", ""),
                                )
                            if ig:
                                r_val = ig.get("total_rating") or ig.get("aggregated_rating")
                                if r_val:
                                    igdb_rating = float(r_val)
                                # Fill description from IGDB summary if missing
                                if not game.description and ig.get("summary"):
                                    game.description = ig["summary"]
                                    applied.append("description(igdb)")
                                # Fill genres from IGDB if missing
                                if not game.genres:
                                    ig_genres = ig.get("genres") or []
                                    gnames = [g["name"] for g in ig_genres if isinstance(g, dict) and g.get("name")]
                                    if gnames:
                                        game.genres = gnames
                                        applied.append("genres(igdb)")
                                # Fill release date if missing
                                if not game.release_date and ig.get("first_release_date"):
                                    from datetime import datetime, timezone
                                    try:
                                        dt = datetime.fromtimestamp(ig["first_release_date"], tz=timezone.utc)
                                        game.release_date = dt.strftime("%Y-%m-%d")
                                        applied.append("release_date(igdb)")
                                    except Exception:
                                        pass
                                # Fill developer / publisher from IGDB if missing
                                if not game.developer:
                                    devs = [
                                        ic.get("company", {}).get("name")
                                        for ic in (ig.get("involved_companies") or [])
                                        if ic.get("developer") and isinstance(ic.get("company"), dict)
                                    ]
                                    if devs:
                                        game.developer = ", ".join(filter(None, devs))
                                        applied.append("developer(igdb)")
                                if not game.publisher:
                                    pubs = [
                                        ic.get("company", {}).get("name")
                                        for ic in (ig.get("involved_companies") or [])
                                        if ic.get("publisher") and isinstance(ic.get("company"), dict)
                                    ]
                                    if pubs:
                                        game.publisher = ", ".join(filter(None, pubs))
                                        applied.append("publisher(igdb)")
                                # Screenshots from IGDB if missing
                                if not game.screenshots:
                                    ss = [
                                        "https:" + s["url"].replace("t_thumb", "t_screenshot_huge")
                                        for s in (ig.get("screenshots") or [])
                                        if isinstance(s, dict) and s.get("url")
                                    ]
                                    if ss:
                                        game.screenshots = ss[:12]
                                        applied.append("screenshots(igdb)")
            except Exception as exc:
                logger.debug("IGDB fetch skipped for '%s': %s", title, exc)

    if rawg_rating is not None or igdb_rating is not None:
        existing = dict(game.meta_ratings or {})
        if rawg_rating is not None:
            existing["rawg"] = rawg_rating
            applied.append("rating(rawg)")
        if igdb_rating is not None:
            existing["igdb"] = igdb_rating
            applied.append("rating(igdb)")
        game.meta_ratings = existing

    # SRL - last resort for system requirements
    if not game.requirements:
        try:
            from handler.gog.srl_handler import fetch_requirements as _srl
            srl_reqs = await _srl(game.title)
            if srl_reqs:
                game.requirements = srl_reqs
                applied.append("requirements(srl)")
        except Exception:
            pass

    return applied


# ── Main entry point ───────────────────────────────────────────────────────────

async def scrape_library_game(game: Any) -> dict:
    """Scrape metadata for a LibraryGame ORM instance from all available sources.

    Mutates the game object in-place. The caller is responsible for committing
    the DB session.

    Returns:
        {
            "sources": {"gog": bool, "steam": bool, "rawg": bool, "igdb": bool},
            "applied": [list of field names],
            "gog_id":  int | None,
        }
    """
    all_applied: list[str] = []
    sources: dict[str, bool] = {"gog": False, "steam": False, "rawg": False, "igdb": False}
    gog_id_found: int | None = None

    # ── 1. GOG public API ──────────────────────────────────────────────────────
    async with httpx.AsyncClient(headers=_HDRS, follow_redirects=True, timeout=20) as client:
        gog_id = await _search_gog_catalog(game.title or "", client)
        if gog_id:
            gog_id_found = gog_id
            v1, v2, rating = await asyncio.gather(
                _fetch_gog_v1(gog_id, client),
                _fetch_gog_v2(gog_id, client),
                _fetch_gog_rating(gog_id, client),
                return_exceptions=True,
            )
            v1     = v1     if not isinstance(v1, Exception)     else {}
            v2     = v2     if not isinstance(v2, Exception)     else {}
            rating = rating if not isinstance(rating, Exception) else None

            if v1 or v2:
                sources["gog"] = True
                applied = _apply_gog_v1v2(game, v1, v2, rating)
                all_applied.extend(applied)
                logger.info(
                    "GOG public API applied for '%s' (gog_id=%s): %s",
                    game.title, gog_id, ", ".join(applied) or "nothing new",
                )
        else:
            logger.debug("GOG catalog: no match for '%s'", game.title)

    # ── 2. Steam fallback ──────────────────────────────────────────────────────
    try:
        steam_applied = await _apply_steam_fallback(game)
        if steam_applied:
            sources["steam"] = True
            all_applied.extend(steam_applied)
    except Exception as exc:
        logger.debug("Steam fallback error for '%s': %s", game.title, exc)

    # ── 3. RAWG + IGDB ratings + SRL ──────────────────────────────────────────
    try:
        ext_applied = await _fetch_external_ratings(game)
        if ext_applied:
            for f in ext_applied:
                if "rawg" in f:
                    sources["rawg"] = True
                if "igdb" in f:
                    sources["igdb"] = True
            all_applied.extend(ext_applied)
    except Exception as exc:
        logger.debug("External ratings error for '%s': %s", game.title, exc)

    # ── 4. HLTB ───────────────────────────────────────────────────────────────
    try:
        from handler.metadata import hltb_handler as _hltb
        hltb_data = await _hltb.search_game(game.title or "")
        if hltb_data:
            if hltb_data.get("hltb_main_s"):
                game.hltb_main_s = hltb_data["hltb_main_s"]
                all_applied.append("hltb_main_s")
            if hltb_data.get("hltb_complete_s"):
                game.hltb_complete_s = hltb_data["hltb_complete_s"]
                all_applied.append("hltb_complete_s")
    except Exception as exc:
        logger.debug("HLTB error for '%s': %s", game.title, exc)

    # ── 5. Derive star rating from external meta_ratings when GOG has none ────────
    # RAWG: 0-5, IGDB total_rating: 0-100, Steam metacritic (stored 0-10): /2 → 0-5
    if not game.rating:
        mr = game.meta_ratings or {}
        derived: float | None = None
        if mr.get("rawg") is not None:
            derived = round(float(mr["rawg"]), 1)
        elif mr.get("igdb") is not None:
            derived = round(float(mr["igdb"]) / 20, 1)
        elif mr.get("steam") is not None:
            derived = round(float(mr["steam"]) / 2, 1)
        if derived and derived > 0:
            game.rating = derived
            all_applied.append("rating(derived)")

    logger.info(
        "Scrape complete for '%s' - sources: %s - applied: %s",
        game.title,
        [k for k, v in sources.items() if v],
        all_applied or ["nothing"],
    )

    return {
        "sources": sources,
        "applied": all_applied,
        "gog_id":  gog_id_found,
    }


async def clear_library_game_metadata(game: Any) -> None:
    """Clear all scraped metadata from a LibraryGame, preserving title, source, files."""
    FIELDS_TO_CLEAR = [
        "description", "description_short",
        "developer", "publisher", "release_date",
        "genres", "tags", "features",
        "rating", "meta_ratings",
        "screenshots", "videos",
        "requirements", "languages",
        "cover_path", "background_path", "logo_path",
        "os_windows", "os_mac", "os_linux",
    ]
    # Only clear os_* if they were NOT set by actual file scan (source == 'gog' or 'custom')
    for field in FIELDS_TO_CLEAR:
        if field in ("os_windows", "os_mac", "os_linux"):
            # Keep OS flags - they're often set by file scan, not scraper
            continue
        setattr(game, field, None)
    # Reset rating to None explicitly (it's a float column)
    game.rating = None
