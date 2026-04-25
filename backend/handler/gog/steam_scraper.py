"""
Steam Store scraper - searches Steam for a game by title and fetches
metadata via the public Steam Store API (no key required).

Used as a supplemental/fallback source when GOG does not provide:
  - description
  - system requirements
  - screenshots (if very few from GOG)
  - genres / categories
  - developer / publisher

Steam Store APIs used:
  Search:  https://store.steampowered.com/api/storesearch/?term=...&cc=US&l=en
  Details: https://store.steampowered.com/api/appdetails?appids={id}&cc=US&l=en
"""
from __future__ import annotations

import logging
import re
from difflib import SequenceMatcher

import httpx

logger = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

_TIMEOUT = 15


def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def parse_steam_app_id(value: str) -> int | None:
    """Extract a Steam App ID from a raw string.

    Accepts:
      - A numeric string: "1718460"
      - A full store URL: "https://store.steampowered.com/app/1718460/Terminator_2D_NO_FATE/"
      - A partial URL: "store.steampowered.com/app/1718460"
    Returns the integer App ID, or None if not detected.
    """
    if not value:
        return None
    value = value.strip()
    # Numeric-only → direct app ID
    if value.isdigit():
        return int(value)
    # URL with /app/{id}
    m = re.search(r"/app/(\d+)", value)
    if m:
        return int(m.group(1))
    return None


async def search_steam_app(title: str) -> int | None:
    """
    Search Steam Store for a game matching *title*.
    Returns the Steam App ID (integer) or None if not found.
    """
    if not title:
        return None
    try:
        async with httpx.AsyncClient(headers=_HEADERS, timeout=_TIMEOUT, follow_redirects=True) as c:
            r = await c.get(
                "https://store.steampowered.com/api/storesearch/",
                params={"term": title, "cc": "US", "l": "en"},
            )
            if r.status_code != 200:
                return None
            items = r.json().get("items") or []
            if not items:
                return None

            # Pick the best-matching result by title similarity
            best_id: int | None = None
            best_score = 0.0
            for item in items[:5]:
                name = item.get("name") or ""
                score = _similarity(title, name)
                if score > best_score:
                    best_score = score
                    best_id = item.get("id")

            # Require at least 60% title similarity to avoid wrong matches
            if best_score < 0.60 or best_id is None:
                return None
            return best_id
    except Exception as exc:
        logger.debug("Steam search failed for %r: %s", title, exc)
        return None


async def fetch_steam_app_details(app_id: int) -> dict | None:
    """
    Fetch game details from Steam Store API for the given *app_id*.
    Returns a normalised dict with GOG-compatible keys, or None on failure.

    Returned dict keys (all optional / may be absent):
      description, description_short, developer, publisher,
      genres (list[str]), features (list[str]),
      screenshots (list[str] - full HD URLs),
      requirements (dict - {"minimum": {...}, "recommended": {...}}),
      os_windows, os_mac, os_linux (bool),
      release_date (str - "YYYY-MM-DD" or raw date string)
    """
    if not app_id:
        return None
    try:
        async with httpx.AsyncClient(headers=_HEADERS, timeout=_TIMEOUT, follow_redirects=True) as c:
            r = await c.get(
                "https://store.steampowered.com/api/appdetails",
                params={"appids": str(app_id), "cc": "US", "l": "en"},
            )
            if r.status_code != 200:
                return None
            wrapper = r.json().get(str(app_id)) or {}
            if not wrapper.get("success"):
                return None
            data = wrapper.get("data") or {}
    except Exception as exc:
        logger.debug("Steam appdetails failed for %s: %s", app_id, exc)
        return None

    result: dict = {}

    # ── Name ──────────────────────────────────────────────────────────────────
    if data.get("name"):
        result["name"] = data["name"]

    # ── Descriptions ──────────────────────────────────────────────────────────
    detail_desc = (data.get("detailed_description") or "").strip()
    short_desc  = (data.get("short_description") or "").strip()
    about       = (data.get("about_the_game") or "").strip()
    if detail_desc:
        result["description"] = detail_desc
    elif about:
        result["description"] = about
    if short_desc:
        result["description_short"] = short_desc

    # ── Developer / Publisher ─────────────────────────────────────────────────
    devs = data.get("developers") or []
    pubs = data.get("publishers") or []
    if devs:
        result["developer"] = devs[0]
    if pubs:
        result["publisher"] = pubs[0]

    # ── Supported Languages ───────────────────────────────────────────────────
    # Steam returns HTML like "English<strong>*</strong>, French<strong>*</strong>, German"
    raw_langs = (data.get("supported_languages") or "").strip()
    if raw_langs:
        clean = re.sub(r"<[^>]+>", "", raw_langs)
        langs = [l.strip() for l in clean.split(",") if l.strip()]
        if langs:
            result["languages"] = {l: l for l in langs}

    # ── Genres ───────────────────────────────────────────────────────────────
    genres = [g["description"] for g in (data.get("genres") or []) if g.get("description")]
    if genres:
        result["genres"] = genres

    # ── Features / Categories ─────────────────────────────────────────────────
    cats = [c["description"] for c in (data.get("categories") or []) if c.get("description")]
    if cats:
        result["features"] = cats

    # ── Platform support ──────────────────────────────────────────────────────
    platforms = data.get("platforms") or {}
    result["os_windows"] = bool(platforms.get("windows"))
    result["os_mac"]     = bool(platforms.get("mac"))
    result["os_linux"]   = bool(platforms.get("linux"))

    # ── Release date ──────────────────────────────────────────────────────────
    rd = data.get("release_date") or {}
    if not rd.get("coming_soon") and rd.get("date"):
        raw = rd["date"]   # e.g. "24 Oct, 2017" or "October 24, 2017"
        parsed = _parse_steam_date(raw)
        if parsed:
            result["release_date"] = parsed
        else:
            result["release_date"] = raw

    # ── Metacritic score ──────────────────────────────────────────────────────
    mc = data.get("metacritic") or {}
    if isinstance(mc, dict) and mc.get("score") is not None:
        try:
            result["rating"] = float(mc["score"]) / 10.0   # 0-100 → 0-10
        except (ValueError, TypeError):
            pass

    # ── Screenshots ───────────────────────────────────────────────────────────
    ss_list: list[str] = []
    for ss in (data.get("screenshots") or []):
        url = ss.get("path_full") or ss.get("path_thumbnail") or ""
        if url:
            # Steam CDN URLs sometimes have ?t= cache busters - strip them
            url = url.split("?")[0]
            ss_list.append(url)
    if ss_list:
        result["screenshots"] = ss_list

    # ── System requirements ───────────────────────────────────────────────────
    reqs: dict = {}
    pc_reqs = data.get("pc_requirements") or {}
    if isinstance(pc_reqs, dict) and (pc_reqs.get("minimum") or pc_reqs.get("recommended")):
        win_reqs: dict = {}
        if pc_reqs.get("minimum"):
            win_reqs["minimum"] = _parse_steam_req_html(pc_reqs["minimum"])
        if pc_reqs.get("recommended"):
            win_reqs["recommended"] = _parse_steam_req_html(pc_reqs["recommended"])
        if win_reqs:
            reqs["Windows PC"] = win_reqs

    mac_reqs = data.get("mac_requirements") or {}
    if isinstance(mac_reqs, dict) and (mac_reqs.get("minimum") or mac_reqs.get("recommended")):
        mac_r: dict = {}
        if mac_reqs.get("minimum"):
            mac_r["minimum"] = _parse_steam_req_html(mac_reqs["minimum"])
        if mac_reqs.get("recommended"):
            mac_r["recommended"] = _parse_steam_req_html(mac_reqs["recommended"])
        if mac_r:
            reqs["macOS"] = mac_r

    linux_reqs = data.get("linux_requirements") or {}
    if isinstance(linux_reqs, dict) and (linux_reqs.get("minimum") or linux_reqs.get("recommended")):
        lin_r: dict = {}
        if linux_reqs.get("minimum"):
            lin_r["minimum"] = _parse_steam_req_html(linux_reqs["minimum"])
        if linux_reqs.get("recommended"):
            lin_r["recommended"] = _parse_steam_req_html(linux_reqs["recommended"])
        if lin_r:
            reqs["Linux"] = lin_r

    if reqs:
        result["requirements"] = reqs

    return result


# ── Helpers ───────────────────────────────────────────────────────────────────

_TAG_RE = re.compile(r"<[^>]+>")
_LABEL_RE = re.compile(
    r"(OS|Processor|Memory|Graphics|DirectX|Storage|Sound|Network|Additional Notes|Minimum|Recommended)\s*:",
    re.IGNORECASE,
)
_LABEL_MAP = {
    "os": "system", "processor": "processor", "cpu": "processor",
    "memory": "memory", "ram": "memory",
    "graphics": "graphics", "gpu": "graphics", "video": "graphics",
    "directx": "directx",
    "storage": "storage", "disk space": "storage",
    "network": "network",
    "sound": "sound", "audio": "sound",
    "additional notes": "notes",
}


def _parse_steam_req_html(html: str) -> dict:
    """
    Steam requirement fields are HTML like:
      <strong>OS:</strong> Windows 7 / 8 / 10<br><strong>Processor:</strong> Intel Core i5…
    or list-style:
      <ul><li><strong>OS:</strong> Windows Vista</li><li><strong>Processor:</strong> 1GHz</li>…
    Extract as {key: value} dict.
    """
    # Treat list items and <br> as line separators
    text = re.sub(r"<li\b[^>]*>",  "\n", html, flags=re.IGNORECASE)
    text = re.sub(r"</li>",         "",   text,  flags=re.IGNORECASE)
    text = re.sub(r"<br\s*/?>",    "\n", text,   flags=re.IGNORECASE)
    text = _TAG_RE.sub("", text)   # strip all remaining tags
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&lt;",  "<", text)
    text = re.sub(r"&gt;",  ">", text)
    text = re.sub(r"&nbsp;", " ", text)

    result: dict = {}
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        # Split on first colon (e.g. "OS: Windows 7")
        parts = line.split(":", 1)
        if len(parts) == 2:
            raw_key = parts[0].strip().lower()
            val = parts[1].strip()
            key = _LABEL_MAP.get(raw_key, raw_key.replace(" ", "_"))
            if val:
                result[key] = val
    return result


def _parse_steam_date(raw: str) -> str | None:
    """
    Try to parse Steam date strings like "24 Oct, 2017" → "2017-10-24".
    Returns ISO string or None if not parseable.
    """
    try:
        from datetime import datetime
        for fmt in ("%d %b, %Y", "%B %d, %Y", "%b %d, %Y", "%Y-%m-%d"):
            try:
                dt = datetime.strptime(raw.strip(), fmt)
                return dt.date().isoformat()
            except ValueError:
                continue
    except Exception:
        pass
    return None


# Singleton alias used by other modules
steam_scraper = type("_SteamScraper", (), {
    "search_app": staticmethod(search_steam_app),
    "fetch_details": staticmethod(fetch_steam_app_details),
})()
