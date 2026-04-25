"""ScreenScraper metadata scraper for ROMs.

API docs: https://www.screenscraper.fr/api2doc.php
Credentials stored in config_handler as:
  screenscraper_username, screenscraper_password
"""

from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_BASE = "https://api.screenscraper.fr/api2"
_SOFT = "GD"

# Default region order for box art (user preset overrides the first entry)
_REGION_PREF = ["ss", "wor", "us", "eu", "uk", "jp", "fr", "de", "es"]

# Box/cover art types (go to covers)
# Note: SS API returns "box-2D-back" (back cover), "box-2D-side" (spine),
#       "box-3D" (3D render), "box-texture" (full-box texture scan)
_COVER_SS_TYPES = {"box-2D", "box-2D-back", "box-3D", "box-2D-side", "box-texture"}

# Box type priority for sorting covers (Box Front first)
_BOX_TYPE_PRIORITY = ["box-2D", "box-3D", "box-2D-side", "box-2D-back", "box-texture"]

# Other media categories
_SUPPORT_SS_TYPES   = {"support-2D", "support-texture", "support-2D-side"}
# SS API returns "screenmarquee"/"screenmarqueesmall" (not "marquee")
_WHEEL_SS_TYPES     = {"screenmarquee", "screenmarqueesmall", "wheel", "wheel-hd", "wheel-carbon", "wheel-steel"}
_BEZEL_SS_TYPES     = {"bezel-16-9", "bezel-4-3"}
_STEAMGRID_SS_TYPES = {"steamgrid"}
_VIDEO_SS_TYPES     = {"video", "video-normalized"}
_PICTO_SS_TYPES     = {"pictoliste", "pictocouleur", "pictomonochrome"}

# SS screenshot types - SS API returns "sstitle" (not "ss-titre")
_SCREENSHOT_SS_TYPES = {"ss", "sstitle"}

# Human-readable labels for ALL SS types
_ALL_TYPE_LABELS: dict[str, str] = {
    "box-2D":              "Box Front",
    "box-2D-back":         "Box Back",
    "box-3D":              "Box 3D",
    "box-2D-side":         "Box Spine",
    "box-texture":         "Box Texture",
    "support-2D":          "Cart. Front",
    "support-texture":     "Cart. Back",
    "support-2D-side":     "Cart. Side",
    "screenmarquee":       "Marquee",
    "screenmarqueesmall":  "Marquee (sm)",
    "wheel":               "Wheel",
    "wheel-hd":            "Wheel HD",
    "wheel-carbon":        "Wheel Carbon",
    "wheel-steel":         "Wheel Steel",
    "bezel-16-9":          "Bezel 16:9",
    "bezel-4-3":           "Bezel 4:3",
    "steamgrid":           "Steam Grid",
    "video":               "Video",
    "video-normalized":    "Video (HD)",
    "ss":                  "Screenshot",
    "sstitle":             "Title Screen",
    "fanart":              "Fanart",
    "background":          "Background",
}

# Backward compat aliases
_BOX_TYPE_LABELS = _ALL_TYPE_LABELS
_COVER_TYPES = _COVER_SS_TYPES

# SS media types that are stored as background_path
_BG_TYPES = {"fanart", "background"}

# All known downloadable extras the user can enable
_EXTRA_SS_TYPES = {
    "box-texture", "manuel", "maps", "ss", "sstitle",
    "video", "video-normalized",
    "support-2D", "support-texture", "support-2D-side",
    "bezel-16-9", "bezel-4-3",
    "screenmarquee", "screenmarqueesmall",
    "wheel", "wheel-hd", "wheel-carbon", "wheel-steel",
    "steamgrid", "fanart", "background",
}


# Built-in developer credentials - registered with ScreenScraper for GamesDownloader
# Priority: user-configured (DB/UI) → env var → these hardcoded defaults
_SS_DEFAULT_DEVID = "60plus"
_SS_DEFAULT_DEVPW = "G9qbeO5QJ5M"


def _ss_params(username: str, password: str, devid: str = "", devpassword: str = "") -> dict:
    """Build ScreenScraper API params.

    devid/devpassword priority: user-configured → SCREENSCRAPER_DEVID env var → built-in default.
    """
    _devid = devid or os.environ.get("SCREENSCRAPER_DEVID") or _SS_DEFAULT_DEVID
    _devpw = devpassword or os.environ.get("SCREENSCRAPER_DEVPASSWORD") or _SS_DEFAULT_DEVPW
    return {
        "devid":       _devid,
        "devpassword": _devpw,
        "softname":    _SOFT,
        "output":      "json",
        "ssid":        username,
        "sspassword":  password,
    }


async def _ss_jeu_infos(
    params: dict,
    label: str,
) -> dict | None:
    """Call jeuInfos.php with *params*, return parsed jeu dict or None."""
    try:
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.get(f"{_BASE}/jeuInfos.php", params=params)
        if r.status_code == 200:
            data = r.json()
            jeu = data.get("response", {}).get("jeu")
            if jeu:
                logger.debug("ScreenScraper matched via %s", label)
                return jeu
        elif r.status_code not in (404, 400):
            logger.warning("ScreenScraper %d for %s - %s", r.status_code, label, r.text[:200])
    except Exception as e:
        logger.warning("ScreenScraper error (%s): %s", label, e)
    return None


async def search_game(
    rom_name: str,
    ss_system_id: int | None,
    fs_name: str = "",
    file_size: int = 0,
    crc: str = "",
    md5: str = "",
    sha1: str = "",
    *,
    username: str,
    password: str,
    devid: str = "",
    devpassword: str = "",
) -> dict | None:
    """Search ScreenScraper for a game - cascade fallback like EmulationStation.

    Identification order (most → least accurate):
      1. All hashes at once (CRC+MD5+SHA1) - like ES-DE sends everything
      2. Filename + size (jeuInfos.php) - good for clean filenames
      3. cleaned name search (jeuRecherche.php) - last resort, pick best result

    Always includes systemeid when available - critical for full media.
    Returns raw SS jeu dict or None.
    """
    base = _ss_params(username, password, devid=devid, devpassword=devpassword)
    if ss_system_id:
        base["systemeid"] = str(ss_system_id)
    base["romtype"] = "rom"

    logger.info("[search_game] START name=%s sys=%s crc=%s md5=%s sha1=%s fs=%s",
                rom_name, ss_system_id, crc[:8] if crc else "-", md5[:8] if md5 else "-",
                sha1[:8] if sha1 else "-", fs_name)

    # ── 1. Hash lookup (send ALL hashes at once, like ES-DE) ─────────────────
    # When we have hashes, do NOT send romnom/romtaille - they may refer to
    # the archive (.7z) not the ROM inside.  SS uses hash alone when available.
    if crc or md5 or sha1:
        p = dict(base)
        if crc:
            p["crc"] = crc.upper()
        if md5:
            p["md5"] = md5.lower()
        if sha1:
            p["sha1"] = sha1.lower()
        result = await _ss_jeu_infos(p, f"hashes(CRC={crc[:8] if crc else '-'},MD5={md5[:8] if md5 else '-'},SHA1={sha1[:8] if sha1 else '-'})")
        if result:
            return result

    # ── 2. Filename + size (works well for No-Intro / Redump sets) ───────────
    if fs_name:
        p = dict(base, romnom=fs_name)
        if file_size:
            p["romtaille"] = str(file_size)
        result = await _ss_jeu_infos(p, f"filename={fs_name}")
        if result:
            return result

    # ── 4. Name search fallback (jeuRecherche.php → jeuInfos.php full fetch) ──
    clean_name = rom_name or fs_name
    if not clean_name:
        return None

    # Strip common ROM tags: (USA), [!], (Rev 1), etc.
    import re as _re
    clean_name = _re.sub(r"\s*[\(\[][^\)\]]*[\)\]]", "", clean_name).strip(" .-_")
    if not clean_name:
        return None

    try:
        sp = dict(base, recherche=clean_name)
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.get(f"{_BASE}/jeuRecherche.php", params=sp)
        if r.status_code == 200:
            jeux = r.json().get("response", {}).get("jeux") or []
            if not isinstance(jeux, list):
                jeux = [jeux]
            if jeux:
                best = jeux[0]
                game_id = best.get("id")
                logger.debug("ScreenScraper name-search '%s' → %d results, id=%s",
                             clean_name, len(jeux), game_id)
                # Fetch full game data (with all medias) via jeuInfos.php
                if game_id:
                    full_p = dict(base, gameid=str(game_id))
                    full = await _ss_jeu_infos(full_p, f"gameid={game_id} (after name-search)")
                    if full:
                        return full
                # Fall back to the search result (partial data, fewer medias)
                return best
    except Exception as e:
        logger.warning("ScreenScraper name-search error for %s: %s", clean_name, e)

    return None


async def search_games(
    query: str,
    ss_system_id: int | None,
    *,
    username: str,
    password: str,
    devid: str = "",
    devpassword: str = "",
) -> list[dict]:
    """Search ScreenScraper for games matching *query*.

    Uses jeuRecherche.php which returns up to 30 results.
    Returns list of simplified candidate dicts.
    """
    params = _ss_params(username, password, devid=devid, devpassword=devpassword)
    params["recherche"] = query
    if ss_system_id:
        params["systemeid"] = str(ss_system_id)

    try:
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.get(f"{_BASE}/jeuRecherche.php", params=params)
            if r.status_code != 200:
                logger.warning("SS jeuRecherche returned %d: %s", r.status_code, r.text[:200])
                return []
            data = r.json()
            jeux = data.get("response", {}).get("jeux") or []
            if not isinstance(jeux, list):
                jeux = [jeux]
            results = []
            for jeu in jeux[:30]:
                # Extract cover URL - apply region preference, prefer Box Front
                medias = jeu.get("medias") or []
                cover_url = None
                for box_type in ("box-2D", "box-3D", "box-2D-side"):
                    candidates = [m for m in medias if m.get("type") == box_type]
                    best = _pick_region(candidates, "region", _REGION_PREF)
                    if best:
                        cover_url = best.get("url")
                        break
                # Name
                noms = jeu.get("noms") or []
                name = noms[0].get("text") if noms else jeu.get("nom", "")
                # Year
                year = None
                for d in (jeu.get("dates") or []):
                    raw = d.get("text", "")
                    if raw and len(raw) >= 4:
                        try:
                            year = int(raw[:4])
                            break
                        except ValueError:
                            pass
                # Developer
                dev = jeu.get("developpeur") or {}
                developer = dev.get("text") if isinstance(dev, dict) else str(dev) if dev else None
                # Regions
                regions_raw = jeu.get("regions") or {}
                regions = []
                if isinstance(regions_raw, list):
                    regions = [r.get("shortname", "") for r in regions_raw if r.get("shortname")]
                elif isinstance(regions_raw, dict):
                    sn = regions_raw.get("shortname")
                    if sn:
                        regions = [sn]
                results.append({
                    "source":    "ss",
                    "ss_id":     str(jeu.get("id")) if jeu.get("id") else None,
                    "igdb_id":   None,
                    "name":      name,
                    "year":      year,
                    "developer": developer,
                    "cover_url": cover_url,
                    "regions":   regions,
                })
            return results
    except Exception as e:
        logger.warning("SS jeuRecherche error for %s: %s", query, e)
        return []


async def get_game_by_id(
    ss_game_id: str,
    *,
    username: str,
    password: str,
    devid: str = "",
    devpassword: str = "",
    ss_system_id: int | None = None,
) -> dict | None:
    """Fetch full game data from ScreenScraper using gameid parameter.

    ss_system_id should be provided whenever possible - SS returns richer
    media data (all box variants, fanarts, screenshots) when systemeid is
    included alongside gameid.
    """
    params = _ss_params(username, password, devid=devid, devpassword=devpassword)
    params["gameid"] = str(ss_game_id)
    # Include systemeid when available - required for full media payload
    if ss_system_id:
        params["systemeid"] = str(ss_system_id)
    try:
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.get(f"{_BASE}/jeuInfos.php", params=params)
            if r.status_code != 200:
                logger.warning("SS get_game_by_id returned %d for gameid=%s - %s",
                               r.status_code, ss_game_id, r.text[:200])
                return None
            data = r.json()
            return data.get("response", {}).get("jeu")
    except Exception as e:
        logger.warning("SS get_game_by_id error for %s: %s", ss_game_id, e)
        return None


def extract_media_urls(game: dict) -> dict:
    """Extract ALL categorised media URLs from a raw SS jeu dict.

    Returns:
        {
            "covers":     [{url, type, region, label, source}],  # box art
            "fanarts":    [{url, type, label, source}],           # hero/bg
            "screenshots":[{url, type, region, label, source}],  # screenshots
            "supports":   [{url, type, label, source}],          # cart/disc
            "wheels":     [{url, type, label, source}],          # wheel/logo
            "bezels":     [{url, type, label, source}],          # bezels
            "steamgrids": [{url, type, label, source}],          # steam grid
            "videos":     [{url, type, label, source}],          # videos
        }
    """
    medias = game.get("medias") or []
    covers:      list[dict] = []
    fanarts:     list[dict] = []
    screenshots: list[dict] = []
    supports:    list[dict] = []
    wheels:      list[dict] = []
    bezels:      list[dict] = []
    steamgrids:  list[dict] = []
    videos:      list[dict] = []
    pictos:      list[dict] = []

    _type_order   = {t: i for i, t in enumerate(_BOX_TYPE_PRIORITY)}
    _region_order = {r: i for i, r in enumerate(_REGION_PREF)}

    for m in medias:
        mtype = m.get("type", "")
        url = m.get("url", "")
        if not url:
            continue
        region_raw = m.get("region") or {}
        if isinstance(region_raw, dict):
            region_short = region_raw.get("shortname", "wor")
        else:
            region_short = str(region_raw) if region_raw else "wor"
        label = _ALL_TYPE_LABELS.get(mtype, mtype)

        if mtype in _COVER_SS_TYPES:
            covers.append({"url": url, "type": mtype, "region": region_short, "label": label, "source": "ss"})
        elif mtype in ("fanart", "background"):
            fanarts.append({"url": url, "type": mtype, "label": label, "source": "ss"})
        elif mtype in _SCREENSHOT_SS_TYPES:
            screenshots.append({"url": url, "type": mtype, "region": region_short, "label": label, "source": "ss"})
        elif mtype in _SUPPORT_SS_TYPES:
            supports.append({"url": url, "type": mtype, "label": label, "source": "ss"})
        elif mtype in _WHEEL_SS_TYPES:
            wheels.append({"url": url, "type": mtype, "region": region_short, "label": label, "source": "ss"})
        elif mtype in _BEZEL_SS_TYPES:
            bezels.append({"url": url, "type": mtype, "label": label, "source": "ss"})
        elif mtype in _STEAMGRID_SS_TYPES:
            steamgrids.append({"url": url, "type": mtype, "label": label, "source": "ss"})
        elif mtype in _VIDEO_SS_TYPES:
            videos.append({"url": url, "type": mtype, "label": label, "source": "ss"})
        elif mtype in _PICTO_SS_TYPES:
            pictos.append({"url": url, "type": mtype, "label": label, "source": "ss"})

    # Sort covers: Box Front first, then by region preference
    covers.sort(key=lambda c: (
        _type_order.get(c["type"], 99),
        _region_order.get(c["region"], 99),
    ))

    return {
        "covers": covers, "fanarts": fanarts, "screenshots": screenshots,
        "supports": supports, "wheels": wheels, "bezels": bezels,
        "steamgrids": steamgrids, "videos": videos, "pictos": pictos,
    }


def _build_region_pref(preferred: str) -> list[str]:
    """Return region preference list with *preferred* moved to front."""
    return [preferred] + [r for r in _REGION_PREF if r != preferred]


def _pick_region(
    items: list[dict],
    region_field: str = "region",
    region_pref: list[str] | None = None,
) -> dict | None:
    """Pick the best item from a list based on region preference."""
    if not items:
        return None
    pref = region_pref or _REGION_PREF
    for reg in pref:
        for item in items:
            r = item.get(region_field, {})
            if isinstance(r, dict) and r.get("shortname") == reg:
                return item
            if isinstance(r, str) and r == reg:
                return item
    return items[0]


def _get_media_url(medias: list[dict], media_type: str) -> str | None:
    """Extract URL for a specific media type from SS media list."""
    for m in medias:
        if m.get("type") == media_type:
            return m.get("url")
    return None


def extract_metadata(
    game: dict,
    cover_type: str = "box-2D",
    region: str = "wor",
    extras: list[str] | None = None,
) -> dict:
    """Normalise raw SS game dict into ROM metadata fields.

    Args:
        game:       Raw jeu dict from ScreenScraper.
        cover_type: Which SS media type to use as the ROM cover image.
        region:     Preferred region shortname (put first in lookup order).
        extras:     Additional SS media types to collect URLs for (returned
                    under key ``extra_urls`` as {ss_type: url}).
    """
    # Build region lookup order from user preset
    region_pref = _build_region_pref(region)

    # Name
    names = game.get("noms", [])
    name = None
    for reg in region_pref:
        for n in names:
            if n.get("region") == reg:
                name = n.get("text")
                break
        if name:
            break
    if not name and names:
        name = names[0].get("text")

    # Summary
    synopses = game.get("synopsis", [])
    summary = None
    for s in synopses:
        if s.get("langue") in ("en", "us"):
            summary = s.get("text")
            break
    if not summary and synopses:
        summary = synopses[0].get("text")

    # Developer / publisher (+ SS company IDs for logo display)
    developer = None
    developer_ss_id = None
    publisher = None
    publisher_ss_id = None
    for dev in (game.get("developpeur") or []) if isinstance(game.get("developpeur"), list) else ([game["developpeur"]] if game.get("developpeur") else []):
        if isinstance(dev, dict):
            developer = dev.get("text")
            try: developer_ss_id = int(dev.get("id")) if dev.get("id") else None
            except (ValueError, TypeError): pass
            break
        elif isinstance(dev, str):
            developer = dev
            break
    for pub in (game.get("editeur") or []) if isinstance(game.get("editeur"), list) else ([game["editeur"]] if game.get("editeur") else []):
        if isinstance(pub, dict):
            publisher = pub.get("text")
            try: publisher_ss_id = int(pub.get("id")) if pub.get("id") else None
            except (ValueError, TypeError): pass
            break
        elif isinstance(pub, str):
            publisher = pub
            break

    # Genres
    genres_raw = game.get("genres", [])
    genres = []
    for g in genres_raw:
        g_names = g.get("noms", [])
        for gn in g_names:
            if gn.get("langue") == "en":
                genres.append(gn.get("text", ""))
                break
        else:
            if g_names:
                genres.append(g_names[0].get("text", ""))

    # Release year
    release_year = None
    dates = game.get("dates", [])
    for d in dates:
        if d.get("region") in ("wor", "us", "eu"):
            raw = d.get("text", "")
            if raw:
                release_year = int(raw[:4]) if len(raw) >= 4 else None
                break
    if not release_year and dates:
        raw = dates[0].get("text", "")
        if raw and len(raw) >= 4:
            try:
                release_year = int(raw[:4])
            except ValueError:
                pass

    # Regions
    regions_list = game.get("regions", {})
    regions = []
    if isinstance(regions_list, list):
        for r in regions_list:
            rn = r.get("shortname") or r.get("text")
            if rn:
                regions.append(rn)
    elif isinstance(regions_list, dict):
        sn = regions_list.get("shortname")
        if sn:
            regions = [sn]

    # Players
    player_count = game.get("joueurs", {})
    if isinstance(player_count, dict):
        player_count = player_count.get("text")

    # Alternative names (all names except the primary)
    alternative_names = []
    for n in names:
        txt = n.get("text", "")
        if txt and txt != name:
            alternative_names.append(txt)
    alternative_names = list(dict.fromkeys(alternative_names))  # deduplicate

    # Franchises / series
    franchises = []
    for fam in (game.get("familles") or []):
        if isinstance(fam, dict):
            txt = fam.get("text") or fam.get("shortname")
            if txt:
                franchises.append(txt)

    # Rating
    ss_score = None
    note = game.get("note", {})
    if isinstance(note, dict):
        try:
            raw_rating = float(note.get("text", 0))
            ss_score = round(raw_rating, 1)          # raw SS score 0–20
            rating = round(raw_rating / 20, 1)       # normalised 0–1 for star display
        except (ValueError, TypeError):
            rating = None
    else:
        rating = None

    # Media
    medias = game.get("medias", [])
    cover_url = None
    bg_url    = None
    screenshots: list[str] = []

    # Cover - use selected cover_type, fall back to box-2D if not found
    cover_candidates = [m for m in medias if m.get("type") == cover_type]
    if not cover_candidates:
        # fallback chain: box-2D -> box-3D -> anything box-like
        for fallback in ("box-2D", "box-3D", "box-2D-side"):
            cover_candidates = [m for m in medias if m.get("type") == fallback]
            if cover_candidates:
                break
    best_cover = _pick_region(cover_candidates, "region", region_pref)
    if best_cover:
        cover_url = best_cover.get("url")

    # Background - fanart first, then screenshot
    fanart_list = [m for m in medias if m.get("type") == "fanart"]
    bg_candidates = fanart_list or [m for m in medias if m.get("type") == "background"]
    best_bg = _pick_region(bg_candidates, "region", region_pref)
    if best_bg:
        bg_url = best_bg.get("url")
    else:
        ss_media = [m for m in medias if m.get("type") == "ss"]
        best_ss = _pick_region(ss_media, "region", region_pref)
        if best_ss:
            bg_url = best_ss.get("url")

    # All screenshots
    for m in medias:
        if m.get("type") == "ss" and m.get("url"):
            screenshots.append(m["url"])
            if len(screenshots) >= 6:
                break

    # Extra media URLs requested by user preset
    extra_urls: dict[str, str] = {}
    if extras:
        for extra_type in extras:
            # Skip types already handled above to avoid duplication
            if extra_type in (cover_type, "ss", "fanart", "background"):
                continue
            candidates = [m for m in medias if m.get("type") == extra_type]
            best = _pick_region(candidates, "region", region_pref)
            if best and best.get("url"):
                extra_urls[extra_type] = best["url"]

    return {
        "ss_id":             str(game.get("id")) if game.get("id") else None,
        "name":              name,
        "summary":           summary,
        "developer":         developer,
        "developer_ss_id":   developer_ss_id,
        "publisher":         publisher,
        "publisher_ss_id":   publisher_ss_id,
        "release_year":      release_year,
        "genres":            genres,
        "regions":           regions,
        "player_count":      str(player_count) if player_count else None,
        "rating":            rating,
        "ss_score":          ss_score,
        "alternative_names": alternative_names or None,
        "franchises":        franchises or None,
        "cover_url":         cover_url,
        "background_url":    bg_url,
        "screenshots":       screenshots,
        "extra_urls":        extra_urls,   # {ss_type: url} for extras to download
        "ss_metadata":       game,
        "is_identified":     True,
    }


# ── Platform / system info ─────────────────────────────────────────────────────

# In-memory cache: ss_system_id -> (monotonic_timestamp, raw_system_dict)
_system_cache: dict[int, tuple[float, dict]] = {}
_SYSTEM_CACHE_TTL: float = 86400.0   # 24 h


async def get_system_info(
    ss_system_id: int,
    *,
    username: str,
    password: str,
    devid: str = "",
    devpassword: str = "",
) -> dict | None:
    """Fetch SS system info for one platform (uses cached full list).

    Calls ``systemesListe.php`` once, caches the per-system entry for 24 h.
    Returns the raw system dict or None on failure / not found.
    """
    now = time.monotonic()
    cached = _system_cache.get(ss_system_id)
    if cached and now - cached[0] < _SYSTEM_CACHE_TTL:
        return cached[1]

    params = _ss_params(username, password, devid=devid, devpassword=devpassword)
    try:
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.get(f"{_BASE}/systemesListe.php", params=params)
            if r.status_code != 200:
                logger.warning("SS systemesListe returned HTTP %d", r.status_code)
                return None
            text = r.text.strip()
            if not text:
                logger.warning("SS systemesListe returned empty body (devid not registered?)")
                return None
            data = r.json()
            systems = data.get("response", {}).get("systemes", [])
            for sys in systems:
                if str(sys.get("id")) == str(ss_system_id):
                    _system_cache[ss_system_id] = (now, sys)
                    return sys
            logger.info("SS system id=%d not found in systemesListe", ss_system_id)
    except Exception as exc:
        logger.warning("SS get_system_info error for id=%d: %s", ss_system_id, exc)
    return None


def extract_system_info(
    system: dict,
    region_pref: list[str] | None = None,
) -> dict:
    """Normalise raw SS systemesListe dict into platform display fields.

    SS systemesListe structure (actual):
      noms      -> dict  {"nom_eu": "Super Nintendo", "nom_jp": "Super Famicom", ...}
      compagnie -> str   "Nintendo"
      datedebut -> str   "1990"
      medias    -> list  [{type, region, url, format, ...}, ...]

    Returns keys: name, description, manufacturer, release_year,
    generation, photo_url, icon_url, bezel_url.
    """
    pref = region_pref or _REGION_PREF

    # ── Name ─────────────────────────────────────────────────────────────────
    # noms is a flat dict: {"nom_eu": "...", "nom_jp": "...", "nom_recalbox": "snes", ...}
    noms = system.get("noms") or {}
    name = None
    if isinstance(noms, dict):
        # Priority: eu > us > jp > launchbox > hyperspin > any non-slug value
        for key in ("nom_eu", "nom_us", "nom_jp", "nom_launchbox", "nom_hyperspin"):
            v = noms.get(key)
            if v and isinstance(v, str) and len(v) > 2:
                name = v
                break
        if not name:
            # Fallback: first value that looks like a real name (has uppercase)
            for v in noms.values():
                if v and isinstance(v, str) and any(c.isupper() for c in v):
                    name = v
                    break
        if not name and noms:
            name = next(iter(noms.values()), None)
    elif isinstance(noms, str):
        name = noms

    # ── Description ───────────────────────────────────────────────────────────
    # synopsis is usually absent in systemesListe; handle gracefully
    synopses = system.get("synopsis") or []
    if isinstance(synopses, str):
        synopses = [{"langue": "xx", "text": synopses}]
    description = None
    if isinstance(synopses, list):
        for s in synopses:
            if isinstance(s, dict) and s.get("langue") in ("en", "us"):
                description = s.get("text")
                break
        if not description and synopses:
            s0 = synopses[0]
            description = s0.get("text") if isinstance(s0, dict) else None

    # ── Manufacturer ──────────────────────────────────────────────────────────
    # compagnie is the correct field; fall back to societe/compagny
    manufacturer = None
    for key in ("compagnie", "societe", "compagny"):
        raw = system.get(key)
        if isinstance(raw, dict):
            manufacturer = raw.get("text")
        elif isinstance(raw, str) and raw.strip():
            manufacturer = raw.strip()
        if manufacturer:
            break

    # ── Release year ─────────────────────────────────────────────────────────
    # datedebut is a plain string "1990"; datesortie is a list of dicts
    release_year = None
    raw_year = system.get("datedebut")
    if isinstance(raw_year, str) and len(raw_year) >= 4:
        try:
            release_year = int(raw_year[:4])
        except ValueError:
            pass
    if not release_year:
        for d in (system.get("datesortie") or []):
            raw = d.get("text", "") if isinstance(d, dict) else str(d)
            if raw and len(raw) >= 4:
                try:
                    release_year = int(raw[:4])
                    break
                except ValueError:
                    pass

    # ── End of production year ────────────────────────────────────────────────
    end_year = None
    raw_end = system.get("datefin")
    if isinstance(raw_end, str) and len(raw_end) >= 4:
        try:
            end_year = int(raw_end[:4])
        except ValueError:
            pass

    # ── Generation ───────────────────────────────────────────────────────────
    generation = None
    gen_raw = system.get("generation") or system.get("numgenerationsystem")
    if gen_raw:
        try:
            generation = int(gen_raw)
        except (ValueError, TypeError):
            generation = str(gen_raw)

    # ── Media ─────────────────────────────────────────────────────────────────
    medias = system.get("medias") or []
    if not isinstance(medias, list):
        medias = []

    # Photo: world > ss > us > japan > eu…
    _PHOTO_PREF = ["wor", "ss", "us", "jp", "eu", "uk", "fr", "de", "es"]
    photo_candidates = [m for m in medias if isinstance(m, dict) and m.get("type") == "photo"]
    best_photo = _pick_region(photo_candidates, "region", _PHOTO_PREF)
    photo_url = best_photo.get("url") if best_photo else None

    # Icon: logo-monochrome > logo-monochrome-svg > icon (all fine without region)
    _ICON_TYPE_PRIO = {"logo-monochrome": 0, "logo-monochrome-svg": 1, "logo-svg": 2, "icon": 3}
    icon_candidates = [m for m in medias if isinstance(m, dict) and m.get("type") in _ICON_TYPE_PRIO]
    icon_candidates.sort(key=lambda m: _ICON_TYPE_PRIO.get(m.get("type", ""), 99))
    best_icon = _pick_region(icon_candidates, "region", pref) if icon_candidates else None
    if not best_icon and icon_candidates:
        best_icon = icon_candidates[0]   # fallback: no region match, take first
    icon_url = best_icon.get("url") if best_icon else None

    # Bezel: 16:9 preferred
    bezel_candidates = [m for m in medias if isinstance(m, dict) and m.get("type") in ("bezel-16-9", "bezel-4-3")]
    bezel_candidates.sort(key=lambda m: 0 if m.get("type") == "bezel-16-9" else 1)
    best_bezel = _pick_region(bezel_candidates, "region", pref) if bezel_candidates else None
    if not best_bezel and bezel_candidates:
        best_bezel = bezel_candidates[0]
    bezel_url = best_bezel.get("url") if best_bezel else None

    return {
        "name":         name,
        "description":  description,
        "manufacturer": manufacturer,
        "release_year": release_year,
        "end_year":     end_year,
        "generation":   generation,
        "photo_url":    photo_url,
        "icon_url":     icon_url,
        "bezel_url":    bezel_url,
    }
