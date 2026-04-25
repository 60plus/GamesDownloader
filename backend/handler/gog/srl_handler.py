"""
System Requirements Lab (systemrequirementslab.com) - async scraper.

Used as a last-resort fallback for system requirements when GOG, Steam,
and RAWG provide no data.  No API key required - plain HTTP scraping.

Returns requirements in Format 1 (same as GOG API):
  {"minimum": {"processor": ..., "memory": ..., "graphics": ...},
   "recommended": {...}}

Keys match what GogGameDetail.vue minReqSummary already handles via KEY_MAP:
  processor / memory / graphics / os / storage / directx / sound / network
"""
from __future__ import annotations

import logging
import re
from urllib.parse import urljoin

import httpx
from bs4 import BeautifulSoup, Tag

logger = logging.getLogger(__name__)

_BASE = "https://www.systemrequirementslab.com"
_HDRS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

# Raw SRL label → standard internal key (matching frontend KEY_MAP)
_LABEL_MAP: dict[str, str] = {
    "OS":                  "os",
    "OPERATING SYSTEM":    "os",
    "CPU":                 "processor",
    "PROCESSOR":           "processor",
    "RAM":                 "memory",
    "MEMORY":              "memory",
    "VIDEO CARD":          "graphics",
    "GRAPHICS":            "graphics",
    "GPU":                 "graphics",
    "GRAPHICS CARD":       "graphics",
    "STORAGE":             "storage",
    "HDD SPACE":           "storage",
    "HARD DRIVE":          "storage",
    "DISK SPACE":          "storage",
    "FREE DISK SPACE":     "storage",
    "FREE SPACE":          "storage",
    "DIRECTX":             "directx",
    "DIRECT X":            "directx",
    "SOUND CARD":          "sound",
    "AUDIO":               "sound",
    "SOUND":               "sound",
    "NETWORK":             "network",
    "INTERNET CONNECTION": "network",
}


# ── Helpers ────────────────────────────────────────────────────────────────────

def _normalize(title: str) -> str:
    t = title.lower().strip()
    t = t.replace("&", "and")
    t = re.sub(r"[^a-z0-9\s-]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def _score(query: str, candidate: str) -> float:
    q = _normalize(query)
    c = _normalize(candidate)
    if not q or not c:
        return 0.0
    if q == c:
        return 1.0
    q_set, c_set = set(q.split()), set(c.split())
    score = len(q_set & c_set) / max(len(q_set), 1) * 0.6
    if q_set.issubset(c_set):  score += 0.25
    if q in c:                  score += 0.15
    if c.startswith(q):         score += 0.10
    score -= min(len(c_set - q_set) * 0.03, 0.15)
    score -= min(len(q_set - c_set) * 0.20, 0.60)
    return max(min(score, 0.99), 0.0)


def _canon_label(raw: str) -> str | None:
    return _LABEL_MAP.get(raw.upper().strip())


# ── Parsers (same 3-strategy approach as the standalone script) ────────────────

def _parse_li_block(container: Tag) -> dict[str, str]:
    result: dict[str, str] = {}
    for li in container.find_all("li"):
        strong = li.find("strong")
        if not strong:
            continue
        raw = strong.get_text(" ", strip=True).rstrip(":")
        canon = _canon_label(raw)
        if not canon or canon in result:
            continue
        full = li.get_text(" ", strip=True)
        value = re.sub(
            rf"^\s*{re.escape(strong.get_text(' ', strip=True))}\s*:?\s*",
            "", full, flags=re.IGNORECASE,
        ).strip()
        if value:
            result[canon] = value
    return result


def _parse_named_divs(container: Tag) -> dict[str, str]:
    result: dict[str, str] = {}
    label_re = re.compile(r"(name|label|title|key)", re.I)
    value_re = re.compile(r"(value|data|info|detail)", re.I)
    for node in container.find_all(True):
        cls = " ".join(node.get("class") or [])
        if not label_re.search(cls):
            continue
        canon = _canon_label(node.get_text(" ", strip=True).rstrip(":"))
        if not canon:
            continue
        sib = node.find_next_sibling()
        if sib and value_re.search(" ".join(sib.get("class") or [])):
            value = sib.get_text(" ", strip=True)
            if value and canon not in result:
                result[canon] = value
    return result


def _parse_text_fallback(container: Tag) -> dict[str, str]:
    result: dict[str, str] = {}
    text = container.get_text("\n", strip=True)
    for raw_label, canon in _LABEL_MAP.items():
        if canon in result:
            continue
        m = re.search(
            rf"(?:^|\n)\s*{re.escape(raw_label)}\s*[:\-]\s*(.+)",
            text, re.IGNORECASE,
        )
        if m:
            value = m.group(1).strip()
            if value:
                result[canon] = value
    return result


def _extract_section(container: Tag) -> dict[str, str]:
    reqs: dict[str, str] = {}

    def _merge(extra: dict[str, str]) -> None:
        for k, v in extra.items():
            if k not in reqs:
                reqs[k] = v

    _merge(_parse_li_block(container))
    if not reqs:
        _merge(_parse_named_divs(container))
    if not reqs:
        _merge(_parse_text_fallback(container))
    return reqs


def _find_container(soup: BeautifulSoup, keywords: list[str]) -> Tag | None:
    kw_re = re.compile("|".join(keywords), re.I)
    for tag in soup.find_all(True):
        tag_id  = (tag.get("id") or "").lower()
        tag_cls = " ".join(tag.get("class") or []).lower()
        if kw_re.search(tag_id) or kw_re.search(tag_cls):
            if tag.find("li") or len(tag.get_text(strip=True)) > 30:
                return tag
    for hdr in soup.find_all(["h2", "h3", "h4"]):
        if kw_re.search(hdr.get_text(strip=True)):
            parent = hdr.parent
            if parent and (parent.find("li") or parent.find("ul")):
                return parent
            sib = hdr.find_next_sibling()
            while sib:
                if isinstance(sib, Tag) and sib.find("li"):
                    return sib
                sib = sib.find_next_sibling()
    return None


# ── Public API ─────────────────────────────────────────────────────────────────

async def fetch_requirements(title: str) -> dict | None:
    """
    Search SRL for *title* and return its system requirements, or None if not found.

    Result format:
        {
            "minimum":     {"processor": "...", "memory": "...", "graphics": "..."},
            "recommended": {"processor": "...", "memory": "...", "graphics": "..."},
        }
    """
    norm = _normalize(title)
    if not norm:
        return None

    filter_val = norm[0] if norm[0].isalnum() else "a"

    async with httpx.AsyncClient(headers=_HDRS, follow_redirects=True, timeout=25) as client:

        # ── Step 1: game list for this letter ─────────────────────────────────
        try:
            r = await client.get(f"{_BASE}/all-games-list/?filter={filter_val}")
            r.raise_for_status()
        except Exception as exc:
            logger.debug("SRL: game-list fetch failed (%s)", exc)
            return None

        soup = BeautifulSoup(r.text, "html.parser")
        games: list[dict] = []
        seen: set[tuple] = set()

        for a in soup.find_all("a", href=True):
            href  = (a.get("href") or "").strip()
            gtitle = a.get_text(" ", strip=True)
            if not href or not gtitle:
                continue
            full_url = urljoin(_BASE, href)
            if "/requirements/" not in full_url:
                continue
            if not re.search(r"/requirements/.+/\d+$", full_url):
                continue
            key = (_normalize(gtitle), full_url)
            if key in seen:
                continue
            seen.add(key)
            # prefer /cyri/ variant
            if "/cyri/" not in full_url:
                full_url = full_url.replace("/requirements/", "/cyri/requirements/", 1)
            games.append({"title": gtitle, "url": full_url})

        if not games:
            logger.debug("SRL: no games for filter '%s'", filter_val)
            return None

        # ── Step 2: pick best match ────────────────────────────────────────────
        scored = sorted(
            [(_score(title, g["title"]), g) for g in games],
            key=lambda x: x[0], reverse=True,
        )
        best_score, best_game = scored[0]

        if best_score < 0.45:
            logger.debug(
                "SRL: no confident match for '%s' (best %.2f → '%s')",
                title, best_score, best_game["title"],
            )
            return None

        logger.debug(
            "SRL: '%s' → '%s' (score %.2f)", title, best_game["title"], best_score
        )

        # ── Step 3: fetch requirements page ───────────────────────────────────
        try:
            pr = await client.get(best_game["url"])
            pr.raise_for_status()
        except Exception as exc:
            logger.debug("SRL: requirements page failed for '%s': %s", best_game["title"], exc)
            return None

        page = BeautifulSoup(pr.text, "html.parser")

        min_cont = _find_container(page, ["minimum", "min-req", "minreq"])
        minimum  = _extract_section(min_cont) if min_cont else _extract_section(page)

        rec_cont    = _find_container(page, ["recommended", "rec-req", "recreq", "suggest"])
        recommended = (
            _extract_section(rec_cont)
            if rec_cont and rec_cont is not min_cont
            else {}
        )

        if not minimum:
            logger.debug("SRL: empty requirements parsed for '%s'", best_game["title"])
            return None

        logger.info(
            "SRL: requirements found for '%s' via '%s'", title, best_game["title"]
        )
        return {"minimum": minimum, "recommended": recommended}
