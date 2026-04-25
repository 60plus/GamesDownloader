"""
GOG metadata scraper - enriches GogGame records with full data from GOG API v1/v2.

GOG API v1: https://api.gog.com/products/{id}?expand=description,screenshots,videos,downloads
GOG API v2: https://api.gog.com/v2/games/{id}

Neither endpoint requires authentication for publicly available games.
GOG data is the primary source; other scrapers (IGDB, RAWG…) fill gaps only.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from decorators.database import begin_session
from handler.database.base_handler import DBBaseHandler
from models.gog_game import GogGame

logger = logging.getLogger(__name__)

_GOG_V1 = "https://api.gog.com/products/{gog_id}?expand=description,screenshots,videos,downloads,system_requirements"
_GOG_V2 = "https://api.gog.com/v2/games/{gog_id}"
_IMG_BASE = "https://images.gog-statics.com/"
_HDRS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) GOGGalaxy/2.0",
    "Accept": "application/json",
    "Accept-Language": "en-US,en;q=0.9",
}


def _abs_url(url: str) -> str:
    """Normalise protocol-relative or root-relative GOG image URLs."""
    if not url:
        return ""
    if url.startswith("//"):
        return "https:" + url
    if url.startswith("/"):
        return "https://images.gog.com" + url
    return url


def _img_url(image_id: str) -> str:
    """Build a full GOG image URL from a raw image_id field."""
    if not image_id:
        return ""
    if image_id.startswith("http") or image_id.startswith("//"):
        return _abs_url(image_id)
    return f"{_IMG_BASE}{image_id}.jpg"


class GogScrapeHandler(DBBaseHandler):
    model = GogGame

    # ── Public API ────────────────────────────────────────────────────────────

    @begin_session
    async def scrape_game(self, gog_id: int, force: bool = True, preserve_ratings: bool = False, *, session: AsyncSession = None) -> bool:
        """Fetch and store full metadata for a single game. Returns True on success.

        Args:
            preserve_ratings: If True, skip re-fetching RAWG/IGDB ratings AND preserve
                              user-customised artwork/media so a manual metadata refresh
                              doesn't wipe custom covers/logos/screenshots set via the editor.
        """
        result = await session.execute(select(GogGame).where(GogGame.gog_id == gog_id))
        game = result.scalars().first()
        if not game:
            logger.warning("scrape_game: gog_id=%s not in DB", gog_id)
            return False

        try:
            v1, v2 = await asyncio.gather(
                self._fetch_v1(gog_id),
                self._fetch_v2(gog_id),
                return_exceptions=True,
            )
            v1_ok = not isinstance(v1, Exception)
            v2_ok = not isinstance(v2, Exception)
            if not v1_ok:
                logger.warning("GOG API v1 error for %s: %s", gog_id, v1)
                v1 = {}
            if not v2_ok:
                logger.warning("GOG API v2 error for %s: %s", gog_id, v2)
                v2 = {}

            # Both APIs failed - nothing to apply, don't mark as scraped so
            # the next sync will retry this game.
            if not v1_ok and not v2_ok:
                logger.warning("scrape_game(%s): both APIs failed, skipping", gog_id)
                return False

            # Debug: log raw videos and system_requirements from v1
            logger.debug(
                "scrape_game(%s) v1 keys: videos=%r sys_req type=%s",
                gog_id,
                v1.get("videos"),
                type(v1.get("system_requirements")).__name__,
            )

            # When preserve_ratings=True (user chose "GOG data only"), snapshot
            # any user-customised artwork fields so they survive the GOG refresh.
            # These are the fields users typically set via the metadata editor
            # (e.g. SGDB covers, curated screenshots, custom logos).
            saved_media: dict = {}
            if preserve_ratings:
                for field in (
                    "logo_url", "logo_path", "icon_url", "icon_path",
                    "cover_url", "cover_path",
                    "background_url", "background_path",
                    "screenshots", "videos",
                ):
                    val = getattr(game, field, None)
                    if val:
                        saved_media[field] = val

            self._apply(game, v1, v2, overwrite=force)

            # ── Steam fallback - fill in fields still missing after GOG data ──
            # Steam is a supplemental source only; it never overwrites data that
            # GOG already provided (overwrite=False is always used here).
            await self._apply_steam_fallback(game)

            # Restore user-customised media after GOG data applied.
            if saved_media:
                for field, val in saved_media.items():
                    setattr(game, field, val)
                logger.debug(
                    "scrape_game(%s): restored %d custom media fields",
                    gog_id, len(saved_media),
                )

            # Fetch external ratings (RAWG / IGDB) if API keys are configured.
            # Skip if preserve_ratings=True (user wants GOG-only refresh).
            if not preserve_ratings and (force or not game.meta_ratings):
                await self._fetch_external_ratings(game)

            # HLTB - always fetch regardless of preserve_ratings (playtime is not user-set metadata)
            if force or not game.hltb_main_s:
                try:
                    from handler.metadata import hltb_handler as _hltb
                    hltb_data = await _hltb.search_game(game.title or "")
                    if hltb_data:
                        if hltb_data.get("hltb_main_s"):
                            game.hltb_main_s = hltb_data["hltb_main_s"]
                        if hltb_data.get("hltb_complete_s"):
                            game.hltb_complete_s = hltb_data["hltb_complete_s"]
                except Exception as _e:
                    logger.debug("HLTB error for '%s': %s", game.title, _e)

            await self._download_media(game, overwrite=force)
            game.scraped = True
            game.scraped_at = datetime.now(tz=timezone.utc)
            logger.info("Scraped '%s' (gog_id=%s)", game.title, gog_id)
            return True
        except Exception as exc:
            logger.error("scrape_game(%s) failed: %s", gog_id, exc)
            return False

    @begin_session
    async def _get_unscraped_ids(self, force: bool = False, *, session: AsyncSession = None) -> list[int]:
        """Return gog_ids that need scraping (short-lived query session)."""
        query = select(GogGame.gog_id) if force else select(GogGame.gog_id).where(GogGame.scraped == False)  # noqa: E712
        result = await session.execute(query)
        return list(result.scalars().all())

    async def scrape_all_unscraped(self, force: bool = False) -> int:
        """Scrape games. force=True rescrapes already-scraped games too.

        Each game is processed in its own DB session (via scrape_game) so that:
          - metadata is committed per-game immediately (no giant open transaction)
          - a DB connection error on one game doesn't roll back all others
        """
        gog_ids = await self._get_unscraped_ids(force=force)
        if not gog_ids:
            return 0

        scraped = 0
        for gog_id in gog_ids:
            try:
                ok = await self.scrape_game(gog_id, force=force)
                if ok:
                    scraped += 1
            except Exception as exc:
                logger.warning("scrape_all: gog_id=%s error: %s", gog_id, exc)
            # Polite rate-limiting - avoid hammering GOG API
            await asyncio.sleep(0.25)

        logger.info("GOG scrape complete: %d/%d games enriched", scraped, len(gog_ids))
        return scraped

    # ── Internal fetchers ─────────────────────────────────────────────────────

    async def _fetch_v1(self, gog_id: int) -> dict:
        async with httpx.AsyncClient(headers=_HDRS, follow_redirects=True, timeout=15) as client:
            resp = await client.get(_GOG_V1.format(gog_id=gog_id))
            resp.raise_for_status()
            return resp.json()

    async def _fetch_v2(self, gog_id: int) -> dict:
        async with httpx.AsyncClient(headers=_HDRS, follow_redirects=True, timeout=15) as client:
            resp = await client.get(_GOG_V2.format(gog_id=gog_id))
            resp.raise_for_status()
            return resp.json()

    # ── Data mapper ───────────────────────────────────────────────────────────

    def _apply(self, game: GogGame, v1: dict, v2: dict, overwrite: bool = False) -> None:  # noqa: C901
        """Merge v1/v2 API data into a GogGame ORM instance (in-place)."""

        # ── Description (v1) ─────────────────────────────────────────────────
        desc = v1.get("description") or {}
        if isinstance(desc, dict):
            full = desc.get("full") or ""
            short = desc.get("short") or ""
            if full and (overwrite or not game.description):
                game.description = full
            if short and (overwrite or not game.description_short):
                game.description_short = short
        elif isinstance(desc, str) and desc and (overwrite or not game.description):
            game.description = desc

        # ── Rating (v1) ──────────────────────────────────────────────────────
        rating_raw = v1.get("rating")
        if rating_raw is not None and (overwrite or not game.rating):
            try:
                r = float(rating_raw)
                if r > 0:
                    game.rating = r
            except (ValueError, TypeError):
                pass

        # ── Release date (v1 is more precise) ────────────────────────────────
        # GOG v1 may return release_date as:
        #   - a dict:  {"date": "2019-03-14 00:00:00.000000", "timezone_type": 3, ...}
        #   - a string: "2019-03-14"
        #   - a Unix timestamp int/float
        rd = v1.get("release_date")
        if rd and (overwrite or not game.release_date):
            if isinstance(rd, dict):
                date_str = (rd.get("date") or "")[:10]
            elif isinstance(rd, (int, float)) and rd > 0:
                from datetime import datetime, timezone
                date_str = datetime.fromtimestamp(rd, tz=timezone.utc).strftime("%Y-%m-%d")
            else:
                date_str = str(rd)[:10]
            if date_str:
                game.release_date = date_str

        # ── Background image (v1) ─────────────────────────────────────────────
        images = v1.get("images") or {}
        bg = (
            images.get("background")
            or images.get("sidebarGraphicHi")
            or images.get("sidebarGraphicLo")
        )
        if bg and (overwrite or not game.background_url):
            game.background_url = _abs_url(str(bg))

        # ── Icon (v1) ─────────────────────────────────────────────────────────
        icon = images.get("icon") or images.get("logo2x") or images.get("logo")
        if icon and (overwrite or not game.icon_url):
            game.icon_url = _abs_url(str(icon))

        # ── Screenshots (v1) ──────────────────────────────────────────────────
        ss_raw = v1.get("screenshots") or []
        if ss_raw and (overwrite or not game.screenshots):
            urls = [_img_url(s.get("image_id", "")) for s in ss_raw if s.get("image_id")]
            urls = [u for u in urls if u]
            if urls:
                game.screenshots = urls

        # ── Videos (v1 + v2 fallback) ─────────────────────────────────────────
        # GOG API v1 returns camelCase keys (videoId, thumbnailId).
        # Some v1 responses wrap the list: {"items": [...]} or {"videos": [...]}.
        # Newer GOG v1 responses use "video_url" (embed URL) instead of "videoId".
        vids_raw = v1.get("videos") or []
        if isinstance(vids_raw, dict):
            vids_raw = vids_raw.get("items") or vids_raw.get("videos") or []
        vids = list(vids_raw) if isinstance(vids_raw, list) else []

        if vids and (overwrite or not game.videos):
            import re as _vre

            def _yt_id(url: str) -> str:
                """Extract YouTube video ID from embed or watch URL."""
                if not url:
                    return ""
                m = _vre.search(r"(?:youtu\.be/|/embed/|[?&]v=)([a-zA-Z0-9_-]{11})", url)
                return m.group(1) if m else ""

            parsed = []
            for v in vids:
                vid_id = (
                    v.get("videoId") or v.get("video_id")
                    or _yt_id(v.get("video_url", ""))
                    or _yt_id(v.get("url", ""))
                )
                if vid_id:
                    parsed.append({
                        "provider": v.get("provider", "youtube"),
                        "video_id": vid_id,
                        "thumbnail_id": v.get("thumbnailId") or v.get("thumbnail_id", ""),
                    })
            if parsed:
                game.videos = parsed

        # v2 fallback - extract YouTube ID from _links.trailer / _links.video href
        if not game.videos and (overwrite or True):
            import re as _re
            links_v2 = v2.get("_links") or {}
            trailer_href = (
                (links_v2.get("trailer") or {}).get("href")
                or (links_v2.get("video") or {}).get("href")
                or ""
            )
            if trailer_href:
                yt_m = _re.search(r"(?:v=|youtu\.be/)([a-zA-Z0-9_-]{11})", trailer_href)
                if yt_m:
                    logger.debug("v2 trailer fallback for gog_id=%s: %s", game.gog_id, trailer_href)
                    game.videos = [{"provider": "youtube", "video_id": yt_m.group(1), "thumbnail_id": ""}]

        # ── Features (v1) ─────────────────────────────────────────────────────
        feats = v1.get("features") or []
        if feats and (overwrite or not game.features):
            game.features = [
                f.get("name") if isinstance(f, dict) else str(f)
                for f in feats
                if f
            ]

        # ── Languages ─────────────────────────────────────────────────────────
        # v1 has a flat {"en": "English", ...} dict at the top level.
        # v2 has localizations: [{_embedded: {language: {code, name}, localizationScope: {type}}}]
        # v1 is preferred (simpler); v2 is fallback and also provides audio/text scope.
        raw_langs = v1.get("languages")
        if raw_langs and (overwrite or not game.languages):
            if isinstance(raw_langs, dict):
                game.languages = raw_langs          # {code: name}, e.g. {"en": "English"}
            elif isinstance(raw_langs, list):
                game.languages = {str(l): str(l) for l in raw_langs}

        # v2 localizations fallback (or supplement when v1 langs missing)
        if not game.languages:
            locs = v2.get("localizations") or []
            if isinstance(locs, list) and locs:
                merged: dict[str, str] = {}
                for loc in locs:
                    emb = loc.get("_embedded") or {}
                    lang = emb.get("language") or {}
                    code = lang.get("code") or ""
                    name = lang.get("name") or code
                    if code:
                        merged[code] = name
                if merged:
                    game.languages = merged

        # ── OS support (v1 content_system_compatibility) ──────────────────────
        compat = v1.get("content_system_compatibility") or {}
        if isinstance(compat, dict):
            if compat.get("windows"):
                game.os_windows = True
            if compat.get("osx"):
                game.os_mac = True
            if compat.get("linux"):
                game.os_linux = True

        # ── Installers summary (v1 downloads) ────────────────────────────────
        downloads = v1.get("downloads") or {}
        installers_raw = downloads.get("installers") or []
        extras_raw = downloads.get("bonus_content") or []

        if installers_raw and not game.installers:
            by_os: dict[str, list] = {}
            for inst in installers_raw:
                os_key = (inst.get("os") or "windows").lower()
                by_os.setdefault(os_key, []).append({
                    "language": inst.get("language") or inst.get("language_full") or "",
                    "name": inst.get("name") or "",
                    "total_size": inst.get("total_size") or 0,
                })
            game.installers = by_os

        if extras_raw and not game.extras:
            game.extras = [
                {"name": e.get("name") or "", "type": e.get("type") or ""}
                for e in extras_raw
            ]

        # ── System requirements (v1) ──────────────────────────────────────────
        # GOG API returns system_requirements in several formats:
        #   A) Dict with minimum_system_requirements / recommended_system_requirements keys
        #   B) Dict with requirement_groups list (each group: {type, requirements:[{name,description}]})
        #   C) Dict with systems list (per-OS)
        #   D) Top-level list of OS objects (wrapped as per_os)
        raw_reqs = v1.get("system_requirements")
        if raw_reqs and (overwrite or not game.requirements):
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
            elif isinstance(raw_reqs, list) and raw_reqs:
                # Format D: list of OS or requirement objects.
                # Several known sub-formats from different GOG API versions:
                #
                #  D1 - [{type:'minimum'|'recommended', requirements:[{name,description}]}]
                #       Entries have explicit type field.
                #
                #  D2 - [{description:'product_system_requirement_...', requirements:[{id,name,description}]}]
                #       GOG native expand format; no type field, uses description key.
                #       items[].requirements use id as the key (system/processor/memory/graphics)
                #
                #  D3 - [{type:'windows', requirement_groups:[...]}]
                #       Per-OS container format.
                first = raw_reqs[0] if raw_reqs else {}
                first_type = first.get("type", "").lower()

                if first_type in ("minimum", "recommended"):
                    # D1 - wrap in a windows container so frontend finds it
                    game.requirements = {"per_os": [{"type": "windows", "requirement_groups": raw_reqs}]}

                elif isinstance(first.get("requirements"), list):
                    # D2 - GOG native format: [{description:str, requirements:[{id,name,description}]}]
                    # Flatten all items' requirements into a single "minimum" dict.
                    # GOG typically returns a single requirements block without min/rec split.
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
                    # D3 - per-OS containers (type='windows'/'mac'/'linux')
                    game.requirements = {"per_os": raw_reqs}

        # ── Genres / tags / developer / publisher (v2 is more structured) ─────
        embedded = v2.get("_embedded") or {}

        all_tags = embedded.get("tags") or []
        if all_tags:
            genres = [
                t.get("name") for t in all_tags
                if isinstance(t, dict) and t.get("type") == "genre" and t.get("name")
            ]
            other_tags = [
                t.get("name") for t in all_tags
                if isinstance(t, dict) and t.get("type") != "genre" and t.get("name")
            ]
            if genres and (overwrite or not game.genres):
                game.genres = genres
            if other_tags and (overwrite or not game.tags):
                game.tags = other_tags

        devs = embedded.get("developers") or []
        if devs and (overwrite or not game.developer):
            game.developer = ", ".join(
                d.get("name") for d in devs if isinstance(d, dict) and d.get("name")
            )

        pub = embedded.get("publisher") or {}
        if isinstance(pub, dict) and pub.get("name") and (overwrite or not game.publisher):
            game.publisher = pub["name"]

        # ── Background from v2 links (higher quality, takes priority) ─────────
        # v1 images.background is the STORE banner (with title/logo overlay baked
        # in - looks washed out on a blurred hero).  v2 galaxyBackgroundImage is
        # the clean Galaxy-client hero asset.  Earlier code read v1 first then
        # checked `or not game.background_url` which always-false'd after v1 set
        # the URL, so v2 never actually won despite the "takes priority" comment.
        # Always update to v2's URL when available, and reset the cached local
        # path so download_background re-fetches the clean image.
        links = v2.get("_links") or {}
        bg_v2 = (
            (links.get("galaxyBackgroundImage") or {}).get("href")
            or (links.get("backgroundImage") or {}).get("href")
        )
        if bg_v2:
            new_bg_url = str(bg_v2)
            if game.background_url != new_bg_url:
                game.background_url = new_bg_url
                game.background_path = None  # stale file from old v1 URL - re-download

        # ── Cover URL - prefer v2 boxArtImage (authoritative box art) ──────────────
        # The embed-API image field may point to a different thumbnail hash than the
        # actual store cover. v2 boxArtImage is the canonical product box art.
        # Always update cover_url to v2's URL when it differs, and reset cover_path
        # so _download_media re-downloads the correct image.
        cover_v2 = (links.get("boxArtImage") or {}).get("href")
        if cover_v2:
            new_url = str(cover_v2)
            if game.cover_url != new_url:
                game.cover_url = new_url
                game.cover_path = None  # stale file (from old URL) - force re-download
        elif not game.cover_url:
            # No v2 box art; fallback to v1 images
            images_v1 = v1.get("images") or {}
            cover_v1 = (images_v1.get("coverLarge") or images_v1.get("cover")
                        or images_v1.get("logo2x") or images_v1.get("logo") or "")
            if cover_v1:
                game.cover_url = _abs_url(str(cover_v1))


    async def _apply_steam_fallback(self, game: GogGame) -> None:
        """
        Use Steam Store API to fill in metadata that GOG did not provide.

        Fields filled (only when absent/empty in game):
          description, description_short, developer, publisher,
          genres, features, os_windows/mac/linux, release_date,
          screenshots (when GOG provided < 3), requirements
        """
        # Check if there is anything worth fetching from Steam
        needs_desc        = not game.description
        needs_dev         = not game.developer
        needs_pub         = not game.publisher
        needs_genres      = not game.genres
        needs_features    = not game.features
        needs_os          = not (game.os_windows or game.os_mac or game.os_linux)
        needs_date        = not game.release_date
        needs_reqs        = not game.requirements
        needs_screenshots    = not game.screenshots or len(game.screenshots) < 3
        needs_steam_rating   = not (game.meta_ratings or {}).get("steam")

        if not any([needs_desc, needs_dev, needs_pub, needs_genres, needs_features,
                    needs_os, needs_date, needs_reqs, needs_screenshots, needs_steam_rating]):
            logger.debug("Steam fallback skipped for '%s' - all fields present", game.title)
            return

        try:
            from handler.gog.steam_scraper import search_steam_app, fetch_steam_app_details
        except ImportError:
            logger.debug("steam_scraper module not available - skipping Steam fallback")
            return

        title = game.title or ""
        try:
            app_id = await search_steam_app(title)
        except Exception as exc:
            logger.debug("Steam search error for '%s': %s", title, exc)
            return

        if not app_id:
            logger.debug("No Steam match for '%s'", title)
            return

        try:
            steam = await fetch_steam_app_details(app_id)
        except Exception as exc:
            logger.debug("Steam details error for app_id=%s: %s", app_id, exc)
            return

        if not steam:
            return

        applied: list[str] = []

        # Description
        if needs_desc and steam.get("description"):
            game.description = steam["description"]
            applied.append("description")
        if not game.description_short and steam.get("description_short"):
            game.description_short = steam["description_short"]
            applied.append("description_short")

        # Developer / Publisher
        if needs_dev and steam.get("developer"):
            game.developer = steam["developer"]
            applied.append("developer")
        if needs_pub and steam.get("publisher"):
            game.publisher = steam["publisher"]
            applied.append("publisher")

        # Genres / Features
        if needs_genres and steam.get("genres"):
            game.genres = steam["genres"]
            applied.append("genres")
        if needs_features and steam.get("features"):
            game.features = steam["features"]
            applied.append("features")

        # OS support
        if needs_os:
            if steam.get("os_windows"):
                game.os_windows = True
                applied.append("os_windows")
            if steam.get("os_mac"):
                game.os_mac = True
                applied.append("os_mac")
            if steam.get("os_linux"):
                game.os_linux = True
                applied.append("os_linux")

        # Release date
        if needs_date and steam.get("release_date"):
            game.release_date = steam["release_date"]
            applied.append("release_date")

        # System requirements
        if needs_reqs and steam.get("requirements"):
            game.requirements = steam["requirements"]
            applied.append("requirements")

        # Metacritic rating (via Steam)
        if steam.get("rating") is not None:
            existing = dict(game.meta_ratings or {})
            if "steam" not in existing:
                existing["steam"] = steam["rating"]
                game.meta_ratings = existing
                applied.append("rating(steam/metacritic)")

        # Screenshots - supplement only (prepend Steam screenshots to any GOG ones)
        if needs_screenshots and steam.get("screenshots"):
            existing = game.screenshots or []
            combined = list(existing) + [
                s for s in steam["screenshots"] if s not in existing
            ]
            game.screenshots = combined[:20]  # cap at 20 total
            applied.append("screenshots")

        if applied:
            logger.info(
                "Steam fallback applied for '%s' (app_id=%s): %s",
                game.title, app_id, ", ".join(applied),
            )
        else:
            logger.debug("Steam fallback: no new data for '%s' (app_id=%s)", game.title, app_id)

    async def _fetch_external_ratings(self, game: GogGame) -> None:
        """Fetch RAWG + IGDB ratings and store in game.meta_ratings (if keys are configured)."""
        try:
            from handler.config.config_handler import config_handler
            rawg_key        = await config_handler.get("rawg_api_key")
            igdb_client_id  = await config_handler.get("igdb_client_id")
            igdb_client_sec = await config_handler.get("igdb_client_secret")
        except Exception:
            return  # config not available - skip silently

        rawg_rating: float | None = None
        igdb_rating: float | None = None
        title = game.title or ""

        async with httpx.AsyncClient(headers=_HDRS, follow_redirects=True, timeout=10) as c:
            # ── RAWG ──────────────────────────────────────────────────────────
            if rawg_key:
                try:
                    r = await c.get(
                        "https://api.rawg.io/api/games",
                        params={"key": rawg_key, "search": title, "page_size": 3},
                    )
                    if r.status_code == 200:
                        results = r.json().get("results", [])
                        if results:
                            top = results[0]
                            if top.get("rating"):
                                rawg_rating = float(top["rating"])
                                logger.debug("RAWG rating for '%s': %.2f", title, rawg_rating)
                            # Fetch system requirements from RAWG if GOG didn't provide them
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
                                            logger.debug("RAWG requirements set for '%s'", title)
                                except Exception as reqs_exc:
                                    logger.debug("RAWG requirements fetch skipped for '%s': %s", title, reqs_exc)
                except Exception as exc:
                    logger.debug("RAWG rating fetch skipped for '%s': %s", title, exc)

            # ── IGDB ──────────────────────────────────────────────────────────
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
                            gr = await c.post(
                                "https://api.igdb.com/v4/games",
                                headers={
                                    "Client-ID":     igdb_client_id,
                                    "Authorization": f"Bearer {token}",
                                },
                                content=(
                                    f'fields total_rating,aggregated_rating;'
                                    f' search "{title}"; limit 3;'
                                ),
                            )
                            if gr.status_code == 200 and gr.json():
                                ig = gr.json()[0]
                                r_val = ig.get("total_rating") or ig.get("aggregated_rating")
                                if r_val:
                                    igdb_rating = float(r_val)
                                    logger.debug("IGDB rating for '%s': %.2f", title, igdb_rating)
                except Exception as exc:
                    logger.debug("IGDB rating fetch skipped for '%s': %s", title, exc)

        if rawg_rating is not None or igdb_rating is not None:
            # Merge into existing meta_ratings to preserve steam key set by _apply_steam_fallback
            existing = dict(game.meta_ratings or {})
            existing["rawg"] = rawg_rating
            existing["igdb"] = igdb_rating
            game.meta_ratings = existing

        # ── SRL fallback - last resort for system requirements ─────────────────
        # Runs only when GOG, Steam, and RAWG all failed to provide requirements.
        if not game.requirements:
            try:
                from handler.gog.srl_handler import fetch_requirements as _srl
                srl_reqs = await _srl(game.title)
                if srl_reqs:
                    game.requirements = srl_reqs
                    logger.info("SRL requirements applied for '%s'", game.title)
            except Exception as srl_exc:
                logger.debug("SRL requirements skipped for '%s': %s", game.title, srl_exc)

    async def _download_media(self, game: GogGame, overwrite: bool = False) -> None:
        """Download all media locally. Updates game fields in-place."""
        from handler.gog.media_handler import (
            download_cover, download_background, download_screenshots,
            download_logo, download_icon,
        )

        # Cover
        if game.cover_url and (overwrite or not game.cover_path):
            path = await download_cover(game.gog_id, game.cover_url, overwrite=overwrite)
            if path:
                game.cover_path = path

        # Background
        if game.background_url and (overwrite or not game.background_path):
            path = await download_background(game.gog_id, game.background_url, overwrite=overwrite)
            if path:
                game.background_path = path

        # Logo (SteamGridDB transparent logo)
        if game.logo_url and (overwrite or not game.logo_path):
            path = await download_logo(game.gog_id, game.logo_url, overwrite=overwrite)
            if path:
                game.logo_path = path

        # Icon
        if game.icon_url and (overwrite or not game.icon_path):
            path = await download_icon(game.gog_id, game.icon_url, overwrite=overwrite)
            if path:
                game.icon_path = path

        # Screenshots - replace CDN URLs with local paths if any downloaded
        if game.screenshots and (overwrite or all(s.startswith("http") for s in game.screenshots)):
            local = await download_screenshots(game.gog_id, game.screenshots, overwrite=overwrite)
            if local:
                game.screenshots = local


    # ── Metadata clearing ─────────────────────────────────────────────────────

    _METADATA_FIELDS = (
        "description", "description_short", "summary",
        "cover_url", "cover_path", "background_url", "background_path",
        "logo_url", "logo_path", "icon_url", "icon_path",
        "screenshots", "videos", "genres", "tags", "features",
        "requirements", "meta_ratings",
        "developer", "publisher", "release_date", "rating",
        "installers", "extras", "changelog", "version",
        "languages",
    )

    @begin_session
    async def clear_game_metadata(self, gog_id: int, *, session: AsyncSession = None) -> bool:
        """Reset all scraped metadata fields for a single game. Returns True if found."""
        result = await session.execute(select(GogGame).where(GogGame.gog_id == gog_id))
        game = result.scalars().first()
        if not game:
            return False
        for field in self._METADATA_FIELDS:
            if hasattr(game, field):
                setattr(game, field, None)
        game.scraped    = False
        game.scraped_at = None
        logger.info("Metadata cleared for '%s' (gog_id=%s)", game.title, gog_id)
        return True

    @begin_session
    async def clear_all_metadata(self, *, session: AsyncSession = None) -> int:
        """Reset all scraped metadata fields for every game. Returns count of affected games."""
        result = await session.execute(select(GogGame))
        games = result.scalars().all()
        for game in games:
            for field in self._METADATA_FIELDS:
                if hasattr(game, field):
                    setattr(game, field, None)
            game.scraped    = False
            game.scraped_at = None
        logger.info("Metadata cleared for %d games", len(games))
        return len(games)


gog_scrape_handler = GogScrapeHandler()
