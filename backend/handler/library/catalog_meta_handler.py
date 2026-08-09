"""Work out which real game a catalogue entry is a port of, and describe it.

A catalogue names ports, not games. "Ship of Harkinian" is a program; the thing
a shelf wants to show is Ocarina of Time - its cover, its year, its studio. The
sync cannot do this: it runs on a timer over the whole catalogue, and this is
two searches per entry against rate-limited third parties. So it is a separate
pass, resumable, and re-runnable for one entry when it guesses wrong.

It does guess wrong. Some entries name a game no database lists under that name
("Zelda 64"), and a few name no original at all - "SM64 Co-op DX" is a mod. The
design follows from that: record what was matched and how sure the match was, so
a mistake is visible in a list rather than buried in a plausible description, and
give an admin a search phrase of their own to override it with.

Nothing here overwrites a field that already has something in it. A scrape is a
guess; whatever is already there was either a better guess or a person's choice.
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timezone
from typing import Any

import httpx
from sqlalchemy import select

from handler.library.catalog_sync_handler import store_catalog_media
from models.catalog_entry import CatalogEntry

logger = logging.getLogger(__name__)

COVER_DIR_NAME = "catalog-covers"
_MAX_COVER_BYTES = 8 * 1024 * 1024
_MAX_SHOTS = 8
_HDRS = {"User-Agent": "Mozilla/5.0 GamesDownloader"}

# IGDB names languages in full; the theme's flag list keys on short codes. Map
# the common ones so they render as flags, and keep any unmapped name as its own
# key so it still shows as text.
_LANG_NAME_TO_CODE = {
    "English": "en", "French": "fr", "Italian": "it", "German": "de",
    "Spanish (Spain)": "es", "Spanish": "es", "Japanese": "ja", "Russian": "ru",
    "Polish": "pl", "Portuguese (Brazil)": "pt-BR", "Portuguese": "pt",
    "Korean": "ko", "Chinese (Simplified)": "zh-Hans",
    "Chinese (Traditional)": "zh-Hant", "Dutch": "nl", "Czech": "cs",
    "Hungarian": "hu", "Danish": "da", "Finnish": "fi", "Norwegian": "no",
    "Swedish": "sv", "Turkish": "tr", "Arabic": "ar", "Greek": "el",
    "Thai": "th", "Ukrainian": "uk",
}

# One in-flight pass per catalogue, for the same reason the sync has one: an
# admin whose first click seemed to hang will click again, and two passes
# racing means two sets of API calls writing the same rows.
_meta_locks: dict[str, asyncio.Lock] = {}


class MetaScrapeInProgress(RuntimeError):
    """A metadata pass over this catalogue is already running."""


# ── Matching ─────────────────────────────────────────────────────────────────
# Kept free of network and database calls so the rules below can be tested
# against the cases that motivated them instead of against a live API.

# Words that carry no identity. Dropping them stops "Legend of Dragoon" from
# matching "Legend of Zelda" on the strength of "legend" and "of".
_STOPWORDS = {
    "the", "of", "a", "an", "and", "for", "to", "in", "on",
    "edition", "version", "remake", "remaster", "remastered", "hd",
    "port", "ported", "recompiled", "recompilation", "recomp", "decompilation",
    "native", "project", "fan", "unofficial", "definitive", "collection",
    # Console tags a source appends to disambiguate a re-used name - "Dinosaur
    # Planet (N64)". They are how the RIGHT entry is told apart from a same-named
    # mobile game, so they must not read as a word the port's name is missing.
    # "64" is left out on purpose: in "Mario 64" it is part of the name, and it
    # is already kept out of the identity check for being a bare number.
    "n64", "nes", "snes", "gamecube", "ngc", "wii", "wiiu",
    "ps1", "ps2", "ps3", "psx", "psp", "playstation",
    "xbox", "dreamcast", "saturn", "genesis", "gba", "gbc", "nds", "3ds", "pc",
}

# A number alone rarely identifies a game - "64" appears in a dozen N64 ports -
# but it is not noise either, so it still counts towards the overlap score. It
# just cannot be the ONLY thing two names have in common.
_NUMERIC = re.compile(r"^\d+$")

# Category text to the platform slugs RAWG reports. Keyed on words rather than
# on a catalogue's exact category names, so this keeps working for a catalogue
# that calls its section "Nintendo 64" instead of "N64 Ports". A category that
# matches nothing simply gets no platform constraint, which is the honest
# answer for a heading like "Other Ports".
_PLATFORM_KEYWORDS: list[tuple[tuple[str, ...], set[str]]] = [
    (("n64", "nintendo 64"),        {"nintendo-64"}),
    (("gamecube", "ngc"),           {"gamecube"}),
    (("wii",),                      {"wii", "wii-u"}),
    (("playstation 2", "ps2"),      {"playstation2"}),
    (("playstation", "ps1", "psx"), {"playstation1", "playstation2", "psp"}),
    (("saturn",),                   {"sega-saturn"}),
    (("dreamcast",),                {"dreamcast"}),
    (("genesis", "mega drive"),     {"genesis"}),
    (("xbox",),                     {"xbox", "xbox360"}),
    (("gba", "game boy advance"),   {"game-boy-advance"}),
    (("nds", "nintendo ds"),        {"nintendo-ds"}),
]


def tokens(text: str) -> list[str]:
    """Lowercase word tokens, punctuation removed."""
    return re.sub(r"[^\w\s]", " ", (text or "").lower()).split()


def distinctive(toks) -> set[str]:
    """The tokens that actually identify a game - no stopwords, no bare numbers."""
    return {t for t in toks if t not in _STOPWORDS and not _NUMERIC.match(t)}


def name_score(query: str, result: str) -> float:
    """How much two game names look like the same game, 0.0 to 1.0.

    Containment is scored carefully. "Bomberman 64" sits inside "Bomberman 64:
    The Second Attack", which is a different game - its sequel - so a result
    that adds identifying words of its own is penalised for each one. Without
    that, every sequel outranks the game it is a sequel to.
    """
    q_all, r_all = tokens(query), tokens(result)
    q, r = set(q_all), set(r_all)
    if not q or not r:
        return 0.0
    if q == r:
        return 1.0

    q_dist, r_dist = distinctive(q_all), distinctive(r_all)
    if q <= r:
        # Extra stopwords and years are free; extra distinctive words are not.
        extra = len(r_dist - q_dist)
        return max(0.4, 0.95 - 0.25 * extra)
    if r <= q:
        extra = len(q_dist - r_dist)
        return max(0.4, 0.95 - 0.25 * extra)

    shorter = min(len(q), len(r))
    return (len(q & r) / shorter) if shorter else 0.0


def platforms_for_category(category: str | None) -> set[str]:
    """RAWG platform slugs implied by a catalogue category, if any."""
    text = (category or "").lower()
    for words, slugs in _PLATFORM_KEYWORDS:
        if any(w in text for w in words):
            return set(slugs)
    return set()


# The same reading of a category, but in GD's own platform vocabulary, so the
# ScreenScraper lookup can name the system. A port's category IS its original
# console, which is exactly the axis ScreenScraper indexes on - naming it turns
# a hopeful title search into a system-scoped one.
_SS_SLUG_KEYWORDS: list[tuple[tuple[str, ...], str]] = [
    (("n64", "nintendo 64"),        "n64"),
    (("gamecube", "ngc"),           "gc"),
    (("wii",),                      "wii"),
    (("playstation 2", "ps2"),      "ps2"),
    (("playstation", "ps1", "psx"), "psx"),
    (("saturn",),                   "saturn"),
    (("dreamcast",),                "dreamcast"),
    (("genesis", "mega drive"),     "genesis"),
    (("xbox",),                     "xbox"),
    (("gba", "game boy advance"),   "gba"),
    (("nds", "nintendo ds"),        "nds"),
]


def ss_system_for_category(category: str | None) -> int | None:
    """The ScreenScraper system id a catalogue category implies, if any."""
    from handler.metadata.rom_platform_map import get_ss_id

    text = (category or "").lower()
    for words, slug in _SS_SLUG_KEYWORDS:
        if any(w in text for w in words):
            return get_ss_id(slug)
    return None


def pick_match(
    query: str, candidates: list[dict], wanted_platforms: set[str],
) -> tuple[dict, str] | None:
    """Choose the candidate that is the game this port is a port of.

    Each candidate is {"name": str, "platforms": set[str], ...}. Returns the
    winner and a confidence, or None when nothing is convincing enough.

    A similarity score cannot do this on its own. "Jak & Daxter Trilogy" ->
    "Jak and Daxter Collection" is right, "Legend of Dragoon" -> "The Legend of
    Zelda" is wrong, and "SM64 Co-op DX" -> "CO-OP: Decrypted" is wrong, and all
    three score the same. What separates them is two counts:

      covered - how much of the query's identity the candidate accounts for
      foreign - identifying words the candidate brings that the query has none of

    A candidate is only plausible if it accounts for the whole query, or adds
    nothing of its own. "Zelda" instead of "Dragoon" fails both and is thrown
    out; dropping "Trilogy" for "Collection" fails neither and is kept.
    """
    q_dist = distinctive(tokens(query))
    scored: list[tuple[float, float, bool, bool, dict]] = []

    for cand in candidates:
        name = str(cand.get("name") or "")
        r_dist = distinctive(tokens(name))
        if q_dist and not (q_dist & r_dist):
            # No shared identifying word at all: "Doom 64" for "Goemon 64",
            # which overlap scoring likes because both are a word plus a number.
            continue
        covered = len(q_dist & r_dist) / len(q_dist) if q_dist else 1.0
        foreign = bool(r_dist - q_dist)
        if covered < 1.0 and foreign:
            # Missing part of the query AND introducing something else. That is
            # a different game wearing a similar name.
            continue

        score = name_score(query, name)
        on_console = bool(wanted_platforms & set(cand.get("platforms") or ()))
        # The console is a tie-breaker, not a score in its own right. Ranking on
        # it directly promoted any same-console game over a better-named one.
        scored.append(
            (score + (0.15 if on_console else 0.0), score, on_console, foreign, cand)
        )

    if not scored:
        return None
    scored.sort(reverse=True, key=lambda t: t[0])
    _rank, score, on_console, foreign, cand = scored[0]

    # A console port whose best match is not on that console is suspect even when
    # the name is exact - two different games share the name "Dinosaur Planet",
    # and only one is the N64 game this is a port of. High confidence is reserved
    # for a match nothing argues against; everything else is worth a second look.
    console_disagrees = bool(wanted_platforms) and not on_console

    if score >= 0.75 and not console_disagrees:
        return cand, "high"
    if score >= 0.75:
        # Strong name, wrong or absent console for a console port. Accepted, but
        # flagged - this is where a same-named stranger slips in.
        return cand, "low"
    if not foreign:
        # Same words, fewer of them - a variant of the same name.
        return cand, "low"
    if on_console:
        # The name is only half convincing; the console is what carries it.
        return cand, "low"
    return None


# ── Sources ──────────────────────────────────────────────────────────────────

async def _rawg_candidates(client, key: str, term: str) -> list[dict]:
    r = await client.get(
        "https://api.rawg.io/api/games",
        params={"key": key, "search": term, "page_size": 8},
    )
    if r.status_code != 200:
        logger.info("RAWG search for %r returned %s", term, r.status_code)
        return []
    out = []
    for item in r.json().get("results", []):
        out.append({
            "name": item.get("name") or "",
            "slug": item.get("slug") or "",
            "released": item.get("released") or "",
            "rating": item.get("rating"),
            "platforms": {
                (p.get("platform") or {}).get("slug", "")
                for p in (item.get("platforms") or [])
            },
        })
    return out


async def _rawg_detail(client, key: str, slug: str) -> dict:
    r = await client.get(f"https://api.rawg.io/api/games/{slug}", params={"key": key})
    return r.json() if r.status_code == 200 else {}


async def _rawg_screenshots(client, key: str, slug: str) -> list[str]:
    """RAWG screenshot URLs for a game (the detail call does not carry them)."""
    try:
        r = await client.get(
            f"https://api.rawg.io/api/games/{slug}/screenshots", params={"key": key},
        )
        if r.status_code != 200:
            return []
        return [s["image"] for s in r.json().get("results", []) if s.get("image")]
    except Exception:
        return []


async def _ss_lookup(term: str, category: str | None, clients: dict) -> dict | None:
    """Ask ScreenScraper what this port is a port OF, scoped to its console.

    A catalogue entry is a PC port of a console game, so ScreenScraper - which
    indexes exactly those consoles - is often the best-informed source for it,
    and the one with proper box art. Returns normalised metadata or None.

    The cover it hands back is a box-2D in the user's preferred region. Its URLs
    carry the account credentials as query parameters, so they are downloaded
    server-side and stored locally; a raw ScreenScraper URL never reaches a page.
    """
    user, pwd = clients.get("ss_user"), clients.get("ss_pass")
    if not user or not pwd:
        return None
    system_id = ss_system_for_category(category)
    try:
        from handler.metadata import screenscraper_handler as ss

        raw = await ss.search_game(term, system_id, username=user, password=pwd)
        if not raw:
            return None
        return ss.extract_metadata(raw, cover_type="box-2D", region="ss")
    except Exception as exc:
        logger.info("ScreenScraper lookup failed for %r: %s", term, exc)
        return None


def _apply_ss_entry(entry: CatalogEntry, meta: dict) -> list[str]:
    """Fill an entry's blanks from a ScreenScraper match (text fields only).

    Media is handled by the caller, which has to download it before it can be
    stored. Like every other source here, this only fills what is empty - a
    scrape is a guess and whatever is already there was a better one.
    """
    applied = []
    if not entry.description and meta.get("summary"):
        entry.description = meta["summary"]
        applied.append("description")
    if not entry.developer and meta.get("developer"):
        entry.developer = str(meta["developer"])[:255]
        applied.append("developer")
    if not entry.publisher and meta.get("publisher"):
        entry.publisher = str(meta["publisher"])[:255]
        applied.append("publisher")
    if not entry.release_date and meta.get("release_year"):
        entry.release_date = str(meta["release_year"])[:32]
        applied.append("release_date")
    if not entry.genres and meta.get("genres"):
        entry.genres = list(meta["genres"])
        applied.append("genres")
    # ScreenScraper's note is a 0-20 score; the entry rating is a 0-5 star, so it
    # always divides by 4 (a 3/20 game is 0.8 stars, not 3 - the old `val > 5`
    # guard passed low scores through verbatim and inverted them). extract_metadata
    # also exposes `rating` already normalised to 0-1; that one scales up by 5.
    if not entry.rating:
        star = None
        try:
            if meta.get("ss_score"):
                star = round(min(5.0, float(meta["ss_score"]) / 4), 1)
            elif meta.get("rating") is not None:
                star = round(min(5.0, float(meta["rating"]) * 5), 1)
        except (TypeError, ValueError):
            star = None
        if star:
            entry.rating = star
            applied.append("rating")
    if meta.get("ss_score"):
        try:
            ratings = dict(entry.meta_ratings or {})
            if "screenscraper" not in ratings:
                ratings["screenscraper"] = round(float(meta["ss_score"]) / 2, 1)
                entry.meta_ratings = ratings
                applied.append("ratings")
        except (TypeError, ValueError):
            pass
    return applied


def _igdb_shot_urls(raw: dict) -> list[str]:
    """Full-size https screenshot URLs from an IGDB game record.

    IGDB hands back protocol-relative thumbnails; swap the size token for the
    big one and prefix https so they load and look like screenshots, not stamps.
    """
    out = []
    for s in (raw.get("screenshots") or []):
        u = (s.get("url") or "").strip()
        if not u:
            continue
        u = u.replace("t_thumb", "t_1080p")
        if u.startswith("//"):
            u = "https:" + u
        out.append(u)
    return out


async def _igdb_token(client, cid: str, secret: str) -> str:
    r = await client.post(
        "https://id.twitch.tv/oauth2/token",
        params={"client_id": cid, "client_secret": secret,
                "grant_type": "client_credentials"},
    )
    return r.json().get("access_token", "") if r.status_code == 200 else ""


async def _igdb_candidates(client, cid: str, token: str, term: str) -> list[dict]:
    safe = term.replace('"', "").replace("'", "").replace(";", "").strip()[:128]
    if not safe:
        return []
    r = await client.post(
        "https://api.igdb.com/v4/games",
        headers={"Client-ID": cid, "Authorization": f"Bearer {token}"},
        content=(
            'fields name,summary,first_release_date,genres.name,'
            'involved_companies.company.name,involved_companies.developer,'
            'involved_companies.publisher,total_rating,cover.url,'
            'screenshots.url,platforms.name,language_supports.language.name;'
            f' search "{safe}"; limit 8;'
        ),
    )
    if r.status_code != 200:
        logger.info("IGDB search for %r returned %s", term, r.status_code)
        return []
    out = []
    for item in r.json():
        out.append({
            "name": item.get("name") or "",
            # IGDB platform names do not line up with RAWG slugs, and teaching
            # this one mapping table two vocabularies is not worth it - IGDB is
            # the fallback, reached only when RAWG has nothing.
            "platforms": set(),
            "raw": item,
        })
    return out


async def _sgdb_art(client, key: str, term: str) -> dict[str, str]:
    """SteamGridDB art for a title: {cover, hero, logo}, any of which may be
    absent. One name search, then one fetch per asset kind.

    The cover is 600x900 specifically - the catalogue's own icon is a square
    launcher badge and a square image is no improvement. The hero is the wide
    background the storefront needs, and the logo the transparent wordmark for
    the hero and spotlight; without a hero the tile block stretches full-width
    and the covers balloon.
    """
    hdr = {"Authorization": f"Bearer {key}"}
    r = await client.get(
        "https://www.steamgriddb.com/api/v2/search/autocomplete/"
        + httpx.URL(path=term).path.lstrip("/"),
        headers=hdr,
    )
    if r.status_code != 200:
        return {}
    data = r.json().get("data") or []
    if not data:
        return {}
    gid = data[0]["id"]

    async def first(kind: str, params: dict | None = None) -> str | None:
        resp = await client.get(
            f"https://www.steamgriddb.com/api/v2/{kind}/game/{gid}",
            headers=hdr, params=params or {},
        )
        if resp.status_code != 200:
            return None
        items = resp.json().get("data") or []
        return items[0].get("url") if items else None

    out: dict[str, str] = {}
    cover = await first("grids", {"dimensions": "600x900"})
    if cover:
        out["cover"] = cover
    hero = await first("heroes")
    if hero:
        out["hero"] = hero
    logo = await first("logos")
    if logo:
        out["logo"] = logo
    return out


# ── Applying ─────────────────────────────────────────────────────────────────
# The target is the catalog ENTRY, not a game: a listing carries its own cover,
# description and metadata (the GogGame equivalent) so the store and the entry
# detail look right before anything is downloaded, and a download copies these
# onto the new game. Only fields the entry has are written; the entry keeps the
# release date as a plain string (a store label, not a queried Date column).

def _pc_requirements(detail: dict) -> dict | None:
    """RAWG per-platform requirements for the PC entry, {minimum, recommended}."""
    for p in (detail.get("platforms") or []):
        plat = (p.get("platform") or {})
        if plat.get("slug") == "pc" or "PC" in str(plat.get("name") or ""):
            req = p.get("requirements_en") or p.get("requirements") or {}
            out = {}
            if req.get("minimum"):
                out["minimum"] = req["minimum"]
            if req.get("recommended"):
                out["recommended"] = req["recommended"]
            return out or None
    return None


def _apply_rawg_entry(entry: CatalogEntry, detail: dict, cand: dict) -> list[str]:
    applied = []
    desc = (detail.get("description_raw") or "").strip()
    if desc and not entry.description:
        entry.description = desc
        applied.append("description")
    if not entry.release_date:
        rd = str(cand.get("released") or detail.get("released") or "").strip()
        if rd:
            entry.release_date = rd[:32]
            applied.append("release_date")
    if not entry.genres:
        names = [g.get("name") for g in (detail.get("genres") or []) if g.get("name")]
        if names:
            entry.genres = names
            applied.append("genres")
    if not entry.developer:
        devs = [d.get("name") for d in (detail.get("developers") or []) if d.get("name")]
        if devs:
            entry.developer = ", ".join(devs)[:255]
            applied.append("developer")
    if not entry.publisher:
        pubs = [p.get("name") for p in (detail.get("publishers") or []) if p.get("name")]
        if pubs:
            entry.publisher = ", ".join(pubs)[:255]
            applied.append("publisher")
    if cand.get("rating") and not entry.rating:
        entry.rating = round(float(cand["rating"]), 1)
        applied.append("rating")
    # Per-source scores for the capsule: RAWG's own 0-5, Metacritic 0-100 stored
    # under "steam" x10 like the GOG detail reads it.
    ratings = dict(entry.meta_ratings or {})
    if cand.get("rating") and "rawg" not in ratings:
        ratings["rawg"] = round(float(cand["rating"]), 1)
    if detail.get("metacritic") and "steam" not in ratings:
        ratings["steam"] = round(float(detail["metacritic"]) / 10, 1)
    if ratings and ratings != (entry.meta_ratings or {}):
        entry.meta_ratings = ratings
        applied.append("ratings")
    if not entry.requirements:
        req = _pc_requirements(detail)
        if req:
            entry.requirements = req
            applied.append("requirements")
    return applied


def _apply_igdb_entry(entry: CatalogEntry, raw: dict) -> list[str]:
    applied = []
    if not entry.description and raw.get("summary"):
        entry.description = raw["summary"]
        applied.append("description")
    if not entry.genres:
        names = [g.get("name") for g in (raw.get("genres") or []) if g.get("name")]
        if names:
            entry.genres = names
            applied.append("genres")
    if not entry.release_date and raw.get("first_release_date"):
        try:
            dt = datetime.fromtimestamp(raw["first_release_date"], tz=timezone.utc)
            entry.release_date = dt.strftime("%Y-%m-%d")
            applied.append("release_date")
        except (ValueError, OSError, OverflowError, TypeError):
            pass
    companies = raw.get("involved_companies") or []
    if not entry.developer:
        devs = [c.get("company", {}).get("name") for c in companies
                if c.get("developer") and isinstance(c.get("company"), dict)]
        devs = [d for d in devs if d]
        if devs:
            entry.developer = ", ".join(devs)[:255]
            applied.append("developer")
    if not entry.publisher:
        pubs = [c.get("company", {}).get("name") for c in companies
                if c.get("publisher") and isinstance(c.get("company"), dict)]
        pubs = [p for p in pubs if p]
        if pubs:
            entry.publisher = ", ".join(pubs)[:255]
            applied.append("publisher")
    if raw.get("total_rating") and not entry.rating:
        entry.rating = round(float(raw["total_rating"]) / 20, 1)
        applied.append("rating")
    # IGDB's aggregate as a 0-100 capsule score, the way the GOG detail shows it.
    if raw.get("total_rating"):
        ratings = dict(entry.meta_ratings or {})
        if "igdb" not in ratings:
            ratings["igdb"] = round(float(raw["total_rating"]), 0)
            entry.meta_ratings = ratings
            applied.append("ratings")
    # Supported languages -> {code: name} for the flag row. IGDB gives names;
    # map the common ones to codes the theme's flag list understands, else keep
    # the name as its own key so it still shows.
    if not entry.languages:
        langs = {}
        for ls in (raw.get("language_supports") or []):
            name = ((ls.get("language") or {}).get("name") or "").strip()
            if name:
                langs[_LANG_NAME_TO_CODE.get(name, name)] = name
        if langs:
            entry.languages = langs
            applied.append("languages")
    return applied


# ── The pass ─────────────────────────────────────────────────────────────────

async def scrape_entry(
    entry: CatalogEntry, *, clients: dict, stats: dict,
) -> dict[str, Any]:
    """Match one catalogue entry to a real game and fill the entry's metadata.

    ``clients`` carries the shared HTTP client and the resolved API keys, so a
    batch pays for one IGDB token and one connection pool rather than one per
    entry.
    """
    client = clients["client"]
    # The parsed title first, the catalogue's original name second. The parsed
    # one is a game name and usually right; the raw one is the port's name and
    # occasionally the only thing a database knows.
    term = (entry.meta_search_term or entry.title or "").strip()
    fallback = (entry.catalog_title or "").strip()
    wanted = platforms_for_category(entry.category)

    result = {"entry_id": entry.id, "title": entry.title, "term": term,
              "source": None, "matched": None, "confidence": None, "applied": []}

    match = None
    source = None
    confidence = None
    detail: dict = {}

    if clients.get("rawg_key"):
        for attempt in [t for t in (term, fallback) if t]:
            cands = await _rawg_candidates(client, clients["rawg_key"], attempt)
            picked = pick_match(attempt, cands, wanted)
            if picked:
                match, confidence = picked
                source = "rawg"
                detail = await _rawg_detail(client, clients["rawg_key"], match["slug"])
                break

    if match is None and clients.get("igdb_token"):
        for attempt in [t for t in (term, fallback) if t]:
            cands = await _igdb_candidates(
                client, clients["igdb_cid"], clients["igdb_token"], attempt,
            )
            picked = pick_match(attempt, cands, set())
            if picked:
                match, confidence = picked
                source = "igdb"
                break

    # ScreenScraper last in the cascade, but often best placed: a port's category
    # names the console it came from, and that is the axis ScreenScraper indexes
    # on. Its answer goes through the same name check as the others, so a
    # system-scoped search cannot smuggle in a wrong game unchallenged.
    ss_meta: dict | None = None
    if match is None:
        for attempt in [t for t in (term, fallback) if t]:
            ss_meta = await _ss_lookup(attempt, entry.category, clients)
            if not ss_meta or not ss_meta.get("name"):
                continue
            picked = pick_match(attempt, [{"name": ss_meta["name"], "platforms": set()}], set())
            if picked:
                match, confidence = picked
                source = "screenscraper"
                break
            ss_meta = None

    if match is None:
        entry.meta_scraped_at = datetime.now(timezone.utc).replace(tzinfo=None)
        entry.meta_source = "none"
        entry.meta_matched_title = None
        entry.meta_confidence = None
        stats["unmatched"] += 1
        logger.info("Catalogue metadata: no match for %r", term)
        return result

    if source == "rawg":
        applied = _apply_rawg_entry(entry, detail, match)
    elif source == "igdb":
        applied = _apply_igdb_entry(entry, match["raw"])
    else:
        applied = _apply_ss_entry(entry, ss_meta or {})

    # Whatever matched, ScreenScraper still gets a word in: it knows these
    # console games better than the PC-facing databases do, so it fills what is
    # still blank. Skipped when it was the matcher (already applied above).
    if source != "screenscraper" and clients.get("ss_user"):
        try:
            extra = await _ss_lookup(match["name"], entry.category, clients)
            if extra and extra.get("name"):
                # Only trust it about this game if the name still agrees.
                if pick_match(match["name"], [{"name": extra["name"], "platforms": set()}], set()):
                    ss_meta = extra
                    applied += _apply_ss_entry(entry, extra)
        except Exception as exc:
            logger.info("ScreenScraper top-up failed for %r: %s", match["name"], exc)

    # Art last: it is the only step that writes files, so a match that turns out
    # unusable has not left any behind. Only fetched when the entry has no cover
    # yet - force_refresh clears it first when an admin wants a redo.
    if clients.get("sgdb_key") and not entry.cover_path:
        try:
            art = await _sgdb_art(client, clients["sgdb_key"], match["name"])
            if art.get("cover"):
                stored = await store_catalog_media(
                    COVER_DIR_NAME, f"entry-{entry.id}", art["cover"],
                    max_bytes=_MAX_COVER_BYTES,
                )
                if stored:
                    entry.cover_path = stored
                    applied.append("cover")
                    stats["covers"] += 1
            if art.get("hero"):
                stored = await store_catalog_media(
                    COVER_DIR_NAME, f"hero-{entry.id}", art["hero"],
                    max_bytes=_MAX_COVER_BYTES,
                )
                if stored:
                    entry.background_path = stored
                    applied.append("hero")
            if art.get("logo"):
                stored = await store_catalog_media(
                    COVER_DIR_NAME, f"logo-{entry.id}", art["logo"],
                    max_bytes=_MAX_COVER_BYTES,
                )
                if stored:
                    entry.logo_path = stored
                    applied.append("logo")
        except Exception as exc:
            logger.info("Art lookup failed for %r: %s", match["name"], exc)

    # ScreenScraper art where SteamGridDB had none. Its box-2D is the real case
    # art for the console original, which for a port is usually the better
    # cover anyway. Stored locally - a ScreenScraper URL carries the account
    # credentials and must never reach a page.
    if ss_meta:
        try:
            if not entry.cover_path and ss_meta.get("cover_url"):
                stored = await store_catalog_media(
                    COVER_DIR_NAME, f"entry-{entry.id}", ss_meta["cover_url"],
                    max_bytes=_MAX_COVER_BYTES,
                )
                if stored:
                    entry.cover_path = stored
                    applied.append("cover (ss)")
                    stats["covers"] += 1
            if not entry.background_path and ss_meta.get("background_url"):
                stored = await store_catalog_media(
                    COVER_DIR_NAME, f"hero-{entry.id}", ss_meta["background_url"],
                    max_bytes=_MAX_COVER_BYTES,
                )
                if stored:
                    entry.background_path = stored
                    applied.append("hero (ss)")
        except Exception as exc:
            logger.info("ScreenScraper art failed for %r: %s", match["name"], exc)

    # Screenshots, stored locally like GOG's (the house rule: no page hot-links
    # a CDN). Only when the entry has none yet - a redo clears them first.
    if not entry.screenshots:
        try:
            if source == "rawg" and clients.get("rawg_key"):
                shot_urls = await _rawg_screenshots(client, clients["rawg_key"], match["slug"])
            elif source == "igdb":
                shot_urls = _igdb_shot_urls(match.get("raw", {}))
            else:
                shot_urls = []
            # ScreenScraper's shots stand in when the matched source had none.
            if not shot_urls and ss_meta:
                shot_urls = [u for u in (ss_meta.get("screenshots") or []) if u]
            stored_shots = []
            for i, url in enumerate(shot_urls[:_MAX_SHOTS]):
                path = await store_catalog_media(
                    COVER_DIR_NAME, f"shot-{entry.id}-{i}", url, max_bytes=_MAX_COVER_BYTES,
                )
                if path:
                    stored_shots.append(path)
            if stored_shots:
                entry.screenshots = stored_shots
                applied.append(f"{len(stored_shots)} screenshots")
        except Exception as exc:
            logger.info("Screenshots failed for %r: %s", match["name"], exc)

    # Time to beat (HowLongToBeat), the same row the GOG detail shows.
    if not entry.hltb_main_s and not entry.hltb_complete_s:
        try:
            from handler.metadata import hltb_handler
            hltb = await hltb_handler.search_game(match["name"])
            if hltb:
                if hltb.get("hltb_main_s"):
                    entry.hltb_main_s = int(hltb["hltb_main_s"])
                if hltb.get("hltb_complete_s"):
                    entry.hltb_complete_s = int(hltb["hltb_complete_s"])
                if entry.hltb_main_s or entry.hltb_complete_s:
                    applied.append("time-to-beat")
        except Exception as exc:
            logger.info("HLTB lookup failed for %r: %s", match["name"], exc)

    entry.meta_scraped_at = datetime.now(timezone.utc).replace(tzinfo=None)
    entry.meta_source = source
    entry.meta_matched_title = str(match["name"])[:255]
    entry.meta_confidence = confidence
    stats["matched"] += 1
    stats[confidence] = stats.get(confidence, 0) + 1

    result.update({"source": source, "matched": match["name"],
                   "confidence": confidence, "applied": applied})
    logger.info(
        "Catalogue metadata: %r -> %r (%s, %s): %s",
        term, match["name"], source, confidence, ", ".join(applied) or "nothing new",
    )
    return result


async def _open_clients() -> dict:
    """Resolve the API keys once and hand back a client the batch can share."""
    from handler.config.config_handler import config_handler

    rawg = await config_handler.get("rawg_api_key")
    cid = await config_handler.get("igdb_client_id")
    secret = await config_handler.get("igdb_client_secret")
    sgdb = await config_handler.get("steamgriddb_api_key")
    ss_user = await config_handler.get("screenscraper_username") or ""
    ss_pass = await config_handler.get("screenscraper_password") or ""

    client = httpx.AsyncClient(headers=_HDRS, follow_redirects=True, timeout=20)
    token = ""
    if cid and secret:
        try:
            token = await _igdb_token(client, cid, secret)
        except Exception as exc:
            logger.info("IGDB token unavailable: %s", exc)
    return {"client": client, "rawg_key": rawg, "igdb_cid": cid,
            "igdb_token": token, "sgdb_key": sgdb,
            "ss_user": ss_user, "ss_pass": ss_pass}


async def scrape_catalog(
    catalog_id: str, *, limit: int | None = None, only_missing: bool = True,
    entry_ids: list[int] | None = None, force_refresh: bool = False, session=None,
) -> dict[str, Any]:
    """Run the metadata pass over a catalogue.

    ``only_missing`` skips entries a previous run already looked at, which is
    what makes a long pass resumable - and what makes a nightly re-run cheap
    instead of a full re-scrape of everything.

    ``limit`` bounds one run. A catalogue of a few hundred entries is a few
    hundred API calls against somebody else's rate limit, and an admin who wants
    to see whether this works at all should not have to wait for all of it.

    ``entry_ids`` narrows the pass to specific entries, which is how a single
    wrong match gets corrected without touching the rest.

    ``force_refresh`` clears each entry's scraped fields before re-deriving them,
    turning "fill the blanks" into "redo from scratch". The correction path uses
    it; the bulk pass does not, so a bulk re-run never wipes an admin's edit.
    """
    lock = _meta_locks.setdefault(catalog_id, asyncio.Lock())
    if lock.locked():
        raise MetaScrapeInProgress(f"A metadata pass over {catalog_id!r} is already running")

    async with lock:
        if session is not None:
            return await _scrape_locked(
                session, catalog_id, limit, only_missing, entry_ids, force_refresh,
            )
        from handler.database.session import async_session_factory
        async with async_session_factory() as own:
            async with own.begin():
                return await _scrape_locked(
                    own, catalog_id, limit, only_missing, entry_ids, force_refresh,
                )


async def _scrape_locked(
    session, catalog_id: str, limit: int | None,
    only_missing: bool, entry_ids: list[int] | None, force_refresh: bool = False,
) -> dict[str, Any]:
    query = select(CatalogEntry).where(CatalogEntry.catalog_id == catalog_id)
    if entry_ids:
        query = query.where(CatalogEntry.id.in_(entry_ids))
    elif only_missing:
        query = query.where(CatalogEntry.meta_scraped_at.is_(None))
    query = query.order_by(CatalogEntry.title)
    if limit:
        query = query.limit(limit)

    entries = (await session.execute(query)).scalars().all()
    stats = {"considered": len(entries), "matched": 0, "unmatched": 0,
             "skipped": 0, "covers": 0, "high": 0, "low": 0}
    if not entries:
        return {**stats, "results": []}

    clients = await _open_clients()
    if not clients["rawg_key"] and not clients["igdb_token"]:
        await clients["client"].aclose()
        raise ValueError(
            "No metadata source is configured - set a RAWG API key or IGDB "
            "credentials in Settings before running this"
        )

    results = []
    try:
        for entry in entries:
            if force_refresh:
                _clear_scraped_fields(entry)
            try:
                results.append(await scrape_entry(
                    entry, clients=clients, stats=stats,
                ))
                # The store is the source: a listing that has already been
                # downloaded hands its fresh presentation to the game it
                # produced, instead of the two drifting apart from the moment
                # of the download. Nothing happens for a listing nobody owns.
                from handler.library.catalog_sync_handler import push_entry_to_game
                await push_entry_to_game(session, entry)
            except Exception:
                # One entry's bad day is not the batch's. The timestamp is left
                # unset so the next run picks this one up again.
                stats["skipped"] += 1
                logger.warning(
                    "Catalogue metadata failed for entry %s (%s)",
                    entry.id, entry.title, exc_info=True,
                )
            # Deliberate. RAWG's free tier and IGDB both meter this, and a pass
            # is a background job - being slower than necessary costs nothing,
            # being throttled halfway costs the run.
            await asyncio.sleep(0.35)
    finally:
        await clients["client"].aclose()

    logger.info("Catalogue %s metadata pass: %s", catalog_id, stats)
    return {**stats, "results": results}


# The fields the pass derives from a match, on the entry. Clearing exactly these
# on a correction lets the next run re-derive them, without touching the title,
# subtitle or category the catalogue owns. The scrape only fills a blank, so on
# a correction the old value has to go first or the fix cannot land.
_SCRAPED_FIELDS = (
    "description", "developer", "publisher", "release_date", "rating", "genres",
    "meta_ratings", "languages", "requirements", "hltb_main_s", "hltb_complete_s",
)


def _clear_scraped_fields(entry: CatalogEntry) -> None:
    for field in _SCRAPED_FIELDS:
        setattr(entry, field, None)
    # The scraped art is the pass's to redo; the catalogue's square icon
    # (icon_path) is a different field and is left alone.
    entry.cover_path = None
    entry.background_path = None
    entry.logo_path = None
    entry.screenshots = None


async def set_search_term(entry_id: int, term: str | None, *, session=None) -> None:
    """Record an admin's own search phrase for one entry and reopen it.

    Clearing the timestamp is what makes the next run act on the new phrase. But
    a re-run only fills blanks, so a correction also has to clear what the last
    match wrote onto the entry - otherwise the wrong developer and year the first
    guess left behind would outlive the fix.
    """
    from handler.database.session import async_session_factory

    async def _do(s):
        row = (await s.execute(
            select(CatalogEntry).where(CatalogEntry.id == entry_id)
        )).scalars().first()
        if row is None:
            raise LookupError(f"No catalogue entry {entry_id}")
        row.meta_search_term = (term or "").strip()[:255] or None
        row.meta_scraped_at = None
        _clear_scraped_fields(row)

    if session is not None:
        await _do(session)
        return
    async with async_session_factory() as own:
        async with own.begin():
            await _do(own)
