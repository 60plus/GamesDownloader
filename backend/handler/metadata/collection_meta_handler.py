"""Collection metadata search / fetch orchestration.

Mirrors the game metadata search, but for collections (franchises / series).
Aggregates the built-in providers - Wikipedia (prose description + lead image)
and IGDB (franchise / collection cover, year range and rating derived from its
games) - plus any metadata plugins that implement the
`metadata_search_collection` / `metadata_get_collection` hooks.

A candidate dict has: provider_id, provider_collection_id, name, snippet?,
cover_url?, start_year?, end_year?. A full result (from `get`) has:
provider_id, name, description?, description_short?, cover_url?, hero_url?,
logo_url?, start_year?, end_year?, rating? (0-5 scale), source_url?.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from urllib.parse import quote

import httpx

from handler.config.config_handler import config_handler
from handler.metadata import igdb_rom_handler, wikipedia_handler
from plugins.manager import plugin_manager

logger = logging.getLogger(__name__)


async def _igdb_creds() -> tuple[str, str]:
    cid = await config_handler.get("igdb_client_id") or ""
    sec = await config_handler.get("igdb_client_secret") or ""
    return cid, sec


async def search(query: str) -> list[dict[str, Any]]:
    """Search every available provider for collections matching `query`."""
    q = (query or "").strip()
    if not q:
        return []
    results: list[dict[str, Any]] = []

    # Wikipedia (no key) - the description source.
    try:
        results.extend(await wikipedia_handler.search(q))
    except Exception as e:
        logger.warning("Wikipedia collection search error: %s", e)

    # IGDB franchises / collections (needs credentials) - the structured source.
    cid, sec = await _igdb_creds()
    if cid and sec:
        try:
            results.extend(await igdb_rom_handler.search_collections(
                q, client_id=cid, client_secret=sec))
        except Exception as e:
            logger.warning("IGDB collection search error: %s", e)

    # Metadata plugins.
    try:
        for pr in plugin_manager.hook.metadata_search_collection(query=q):
            if isinstance(pr, list):
                results.extend(pr)
    except Exception as e:
        logger.warning("Plugin collection search error: %s", e)

    return results


async def get(provider_id: str, provider_collection_id: str) -> dict[str, Any] | None:
    """Fetch full collection metadata from one provider."""
    pid = (provider_id or "").strip()
    cid_arg = provider_collection_id or ""

    if pid == "wikipedia":
        return await wikipedia_handler.get(cid_arg)

    if pid == "igdb":
        cid, sec = await _igdb_creds()
        if not (cid and sec):
            return None
        return await igdb_rom_handler.get_collection(
            cid_arg, client_id=cid, client_secret=sec)

    # Metadata plugins.
    try:
        for r in plugin_manager.hook.metadata_get_collection(provider_collection_id=cid_arg):
            if isinstance(r, dict) and r.get("provider_id") == pid:
                return r
    except Exception as e:
        logger.warning("Plugin collection fetch error: %s", e)
    return None


async def _sgdb_art(query: str, kind: str = "grids") -> list[dict[str, Any]]:
    """SteamGridDB art for a name (autocomplete -> {grids|heroes|logos}). The
    richest art source, since IGDB / Wikipedia return few images for a franchise."""
    key = await config_handler.get("steamgriddb_api_key")
    if not key:
        return []
    hdrs = {"Authorization": f"Bearer {key}"}
    out: list[dict[str, Any]] = []
    try:
        async with httpx.AsyncClient(timeout=12) as c:
            r = await c.get(
                f"https://www.steamgriddb.com/api/v2/search/autocomplete/{quote(query)}",
                headers=hdrs)
            if r.status_code != 200:
                return []
            games = r.json().get("data", [])[:4]
            for g in games:
                params: dict[str, Any] = {"limit": 8}
                if kind == "grids":
                    params["dimensions"] = "600x900,342x482"
                try:
                    rg = await c.get(
                        f"https://www.steamgriddb.com/api/v2/{kind}/game/{g['id']}",
                        params=params, headers=hdrs)
                    if rg.status_code == 200:
                        for item in rg.json().get("data", []):
                            if item.get("url"):
                                out.append({
                                    "url":    item["url"],
                                    "thumb":  item.get("thumb") or item["url"],
                                    "label":  g.get("name") or query,
                                    "source": "steamgriddb",
                                })
                except Exception:
                    pass
    except Exception as e:
        logger.warning("SteamGridDB %s error: %s", kind, e)
    return out


async def _plugin_art(query: str, hook_name: str) -> list[dict[str, Any]]:
    """Collect art from metadata plugins via the given game-art hook."""
    out: list[dict[str, Any]] = []
    hook = getattr(plugin_manager.hook, hook_name, None)
    if hook is None:
        return out
    try:
        for pr in hook(query=query):
            if isinstance(pr, list):
                for it in pr:
                    if isinstance(it, dict) and it.get("url"):
                        out.append({
                            "url":    it["url"],
                            "thumb":  it.get("thumb") or it["url"],
                            "label":  it.get("label") or query,
                            "source": it.get("_source") or "plugin",
                        })
    except Exception as e:
        logger.warning("Plugin %s error: %s", hook_name, e)
    return out


async def heroes(query: str) -> list[dict[str, Any]]:
    """Hero / background art for a collection name (SteamGridDB heroes + plugins)."""
    q = (query or "").strip()
    if not q:
        return []
    out = await _sgdb_art(q, "heroes")
    out.extend(await _plugin_art(q, "metadata_get_heroes"))
    return out


async def logos(query: str) -> list[dict[str, Any]]:
    """Logo / clearlogo art for a collection name (SteamGridDB logos + plugins)."""
    q = (query or "").strip()
    if not q:
        return []
    out = await _sgdb_art(q, "logos")
    out.extend(await _plugin_art(q, "metadata_get_logos"))
    return out


async def covers(query: str) -> list[dict[str, Any]]:
    """Aggregate cover-art candidates for a collection name from IGDB game
    covers, SteamGridDB grids, the Wikipedia lead image and metadata plugins.
    Each item: {url, thumb, label, source} - the editor renders a pick grid."""
    q = (query or "").strip()
    if not q:
        return []

    async def _igdb() -> list[dict]:
        cid, sec = await _igdb_creds()
        if not (cid and sec):
            return []
        try:
            games = await igdb_rom_handler.search_games(q, None, client_id=cid, client_secret=sec)
            return [{"url": g["cover_url"], "thumb": g["cover_url"],
                     "label": g.get("name") or q, "source": "igdb"}
                    for g in games if g.get("cover_url")]
        except Exception as e:
            logger.warning("IGDB covers error: %s", e)
            return []

    async def _wiki() -> list[dict]:
        try:
            hits = await wikipedia_handler.search(q)
            return [{"url": h["cover_url"], "thumb": h["cover_url"],
                     "label": h.get("name") or q, "source": "wikipedia"}
                    for h in hits if h.get("cover_url")]
        except Exception:
            return []

    parts = await asyncio.gather(_sgdb_art(q, "grids"), _igdb(), _wiki(), return_exceptions=True)
    out: list[dict[str, Any]] = []
    for p in parts:
        if isinstance(p, list):
            out.extend(p)
    out.extend(await _plugin_art(q, "metadata_get_covers"))
    return out
