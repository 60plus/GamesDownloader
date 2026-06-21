"""Wikipedia metadata provider for collections / franchises.

No API key required. Uses the public MediaWiki action API for search and the
REST summary endpoint for the description + lead image. A collection is a
franchise / series, and Wikipedia's prose summary is the natural "About"
source (the structured fields - years, rating - are already derived from a
collection's member games, so Wikipedia only supplies the description + image).
"""

from __future__ import annotations

import logging
import re
from typing import Any
from urllib.parse import quote

import httpx

logger = logging.getLogger(__name__)

_API      = "https://en.wikipedia.org/w/api.php"
_REST     = "https://en.wikipedia.org/api/rest_v1/page/summary"
_HDRS     = {"User-Agent": "GamesDownloader/1.0 (collection metadata)"}
_PROVIDER = "wikipedia"


async def search(query: str) -> list[dict[str, Any]]:
    """Search Wikipedia for candidate pages, each with a thumbnail + a short
    extract (one generator query, so the editor can preview covers in the list)."""
    q = (query or "").strip()
    if not q:
        return []
    try:
        async with httpx.AsyncClient(headers=_HDRS, timeout=12, follow_redirects=True) as c:
            r = await c.get(_API, params={
                "action": "query", "generator": "search", "gsrsearch": q,
                "gsrlimit": 6, "prop": "pageimages|extracts",
                "piprop": "thumbnail", "pithumbsize": 240,
                "exintro": 1, "explaintext": 1, "exsentences": 2,
                "format": "json",
            })
            r.raise_for_status()
            pages = r.json().get("query", {}).get("pages", {})
    except Exception as exc:
        logger.warning("Wikipedia search failed for %r: %s", q, exc)
        return []

    out: list[dict[str, Any]] = []
    # `generator=search` keys results by page id; `index` preserves the rank.
    for p in sorted(pages.values(), key=lambda x: x.get("index", 999)):
        title = p.get("title") or ""
        if not title:
            continue
        out.append({
            "provider_id":            _PROVIDER,
            "provider_collection_id": title,
            "name":                   title,
            "snippet":                (p.get("extract") or "").strip(),
            "cover_url":              (p.get("thumbnail") or {}).get("source"),
        })
    return out


async def get(provider_collection_id: str) -> dict[str, Any] | None:
    """Fetch a page summary: prose description + lead image."""
    title = (provider_collection_id or "").strip()
    if not title:
        return None
    try:
        async with httpx.AsyncClient(headers=_HDRS, timeout=12, follow_redirects=True) as c:
            r = await c.get(f"{_REST}/{quote(title.replace(' ', '_'), safe='')}")
            if r.status_code != 200:
                return None
            d = r.json()
    except Exception as exc:
        logger.warning("Wikipedia summary failed for %r: %s", title, exc)
        return None

    extract = (d.get("extract") or "").strip()
    img = (d.get("originalimage") or {}).get("source") or (d.get("thumbnail") or {}).get("source")
    short = ""
    if extract:
        m = re.match(r"^(.*?[.!?])(\s|$)", extract)
        short = (m.group(1) if m else extract)[:300]
    return {
        "provider_id":       _PROVIDER,
        "name":              d.get("title") or title,
        "description":       extract or None,
        "description_short": short or None,
        "cover_url":         img,
        "source_url":        (d.get("content_urls") or {}).get("desktop", {}).get("page"),
    }
