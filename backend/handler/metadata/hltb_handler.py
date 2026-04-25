"""HowLongToBeat metadata handler.

No API key required - uses HLTB's public search endpoint.
The endpoint URL is fetched from RomM's maintained GitHub fixture.
The security token + honeypot keys are fetched from HLTB's init endpoint.
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
from difflib import SequenceMatcher

import httpx

logger = logging.getLogger(__name__)

_HLTB_URL_SOURCE = (
    "https://raw.githubusercontent.com/rommapp/romm/refs/heads/master"
    "/backend/handler/metadata/fixtures/hltb_api_url"
)
_BASE_URL = "https://howlongtobeat.com"
_search_url: str = f"{_BASE_URL}/api/find"
# Init endpoint returns {token, hpKey, hpVal}
_security_token: str | None = None
_hp_key: str | None = None
_hp_val: str | None = None
_init_done: bool = False
_init_lock = asyncio.Lock()
_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"


def _normalise(title: str) -> str:
    title = title.lower()
    title = re.sub(r"^(the|a|an)\s+", "", title)
    title = re.sub(r"[^\w\s]", " ", title)
    return re.sub(r"\s+", " ", title).strip()


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, _normalise(a), _normalise(b)).ratio()


async def _fetch_security_data() -> None:
    """Fetch search URL + security token/keys from HLTB."""
    global _search_url, _security_token, _hp_key, _hp_val

    # 1. Get security token + honeypot keys from /api/find/init
    try:
        async with httpx.AsyncClient(timeout=10, follow_redirects=True) as c:
            r = await c.get(
                f"{_BASE_URL}/api/find/init",
                params={"t": int(time.time())},
                headers={"Referer": _BASE_URL, "User-Agent": _UA},
            )
            if r.status_code == 200:
                data = r.json()
                _security_token = data.get("token")
                _hp_key = data.get("hpKey")
                _hp_val = data.get("hpVal")
                logger.debug(
                    "HLTB: security token obtained (hpKey=%s)", _hp_key
                )
            else:
                logger.debug("HLTB: init returned %d", r.status_code)
    except Exception as e:
        logger.debug("HLTB: could not fetch security token: %s", e)


async def _ensure_init() -> None:
    global _init_done
    if _init_done:
        return
    async with _init_lock:
        if _init_done:
            return
        await _fetch_security_data()
        _init_done = True


async def search_game(
    name: str,
    platform_name: str | None = None,
) -> dict | None:
    """Search HLTB for *name*, return timing data dict or None.

    Returned dict keys: hltb_id, hltb_main_s, hltb_extra_s, hltb_complete_s
    All times are in seconds.
    """
    await _ensure_init()

    if not _security_token:
        logger.debug("HLTB: no security token - skipping search for '%s'", name)
        return None

    payload = {
        "searchType": "games",
        "searchTerms": name.split(),
        "searchPage": 1,
        "size": 20,
        "searchOptions": {
            "games": {
                "userId": 0,
                "platform": platform_name or "",
                "sortCategory": "popular",
                "rangeCategory": "main",
                "rangeTime": {"min": None, "max": None},
                "gameplay": {
                    "perspective": "",
                    "flow": "",
                    "genre": "",
                    "difficulty": "",
                },
                "rangeYear": {"min": "", "max": ""},
                "modifier": "",
            },
            "users": {"sortCategory": "postcount"},
            "lists": {"sortCategory": "follows"},
            "filter": "",
            "sort": 0,
            "randomizer": 0,
        },
        "useCache": True,
    }
    # Honeypot: hpKey/hpVal must also be in the request body
    if _hp_key and _hp_val:
        payload[_hp_key] = _hp_val

    headers = {
        "Content-Type": "application/json",
        "Referer": _BASE_URL,
        "User-Agent": _UA,
        "x-auth-token": _security_token,
        "x-hp-key": _hp_key or "",
        "x-hp-val": _hp_val or "",
    }

    try:
        async with httpx.AsyncClient(timeout=20, follow_redirects=True) as c:
            r = await c.post(_search_url, json=payload, headers=headers)
            if r.status_code == 401:
                # Token expired - refresh once and retry
                logger.debug("HLTB: token expired, refreshing…")
                global _init_done
                _init_done = False
                await _ensure_init()
                if not _security_token:
                    return None
                headers["x-auth-token"] = _security_token
                headers["x-hp-key"] = _hp_key or ""
                headers["x-hp-val"] = _hp_val or ""
                r = await c.post(_search_url, json=payload, headers=headers)
            if r.status_code != 200:
                logger.debug("HLTB: search returned %d for '%s'", r.status_code, name)
                return None
            games = r.json().get("data", [])
    except Exception as e:
        logger.debug("HLTB: search error for '%s': %s", name, e)
        return None

    if not games:
        return None

    # Find best name match
    best: dict | None = None
    best_score = 0.0
    for game in games:
        score = _similarity(name, game.get("game_name", ""))
        if score > best_score:
            best_score = score
            best = game

    if not best or best_score < 0.75:
        logger.debug("HLTB: no good match for '%s' (best=%.2f)", name, best_score)
        return None

    result: dict = {"hltb_id": best.get("game_id")}
    if best.get("comp_main", 0) > 0:
        result["hltb_main_s"] = best["comp_main"]
    if best.get("comp_plus", 0) > 0:
        result["hltb_extra_s"] = best["comp_plus"]
    if best.get("comp_100", 0) > 0:
        result["hltb_complete_s"] = best["comp_100"]

    if len(result) == 1:  # only hltb_id, no timing data
        return None

    logger.info(
        "HLTB: '%s' matched '%s' (score=%.2f) - main=%s extra=%s 100%%=%s",
        name,
        best.get("game_name", ""),
        best_score,
        result.get("hltb_main_s"),
        result.get("hltb_extra_s"),
        result.get("hltb_complete_s"),
    )
    return result
