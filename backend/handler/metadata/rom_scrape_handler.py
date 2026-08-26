"""ROM metadata scraper - orchestrates IGDB, ScreenScraper, LaunchBox.

Priority order (fills only fields still missing after each source):
  1. ScreenScraper - ROM-specific, best for box art and regional info
  2. IGDB          - game database, covers, screenshots, genres, ratings
  3. LaunchBox     - large community database, good descriptions and genres

Images are downloaded to /data/resources/roms/{platform_slug}/{rom_id}/
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import httpx

from utils.http import fetch_media_bytes, loggable_error

from config import RESOURCES_PATH
from config import config_manager
from handler.config.config_handler import config_handler
from handler.database.rom_handler import rom_handler
from handler.metadata import hltb_handler, igdb_rom_handler, launchbox_handler, screenscraper_handler
from handler.metadata.rom_platform_map import (
    get_hltb_name, get_igdb_id, get_launchbox_name, get_ss_id,
)
from models.rom import Rom
from models.rom_platform import RomPlatform

logger = logging.getLogger(__name__)


# Standard box-art proportions a cover is snapped to. Snapping (rather than
# storing the exact ratio) keeps a shelf of the same platform's boxes aligned
# instead of jittering by a few pixels per scan.
_COVER_RATIOS: tuple[tuple[str, float], ...] = (
    ("16/9",  16 / 9),    # 1.778  widescreen / box-3D perspective
    ("16/11", 16 / 11),   # 1.455  SNES / PC Engine horizontal box
    ("4/3",   4 / 3),     # 1.333  Genesis / Mega Drive, Saturn
    ("7/6",   7 / 6),     # 1.167  near-square, e.g. PlayStation jewel case
    ("1/1",   1.0),       # square (GB, GBC, Atari)
    ("4/5",   0.8),       # slightly portrait
    ("3/4",   0.75),      # standard modern portrait
    ("2/3",   2 / 3),     # tall movie-style box
)


def _detect_cover_aspect(path: Path) -> str | None:
    """Read image dimensions and snap to the nearest standard CSS aspect-ratio.

    This used to be a ladder of thresholds, and three of its rungs returned a
    ratio that lay outside the range that selected it - so the "nearest" ratio
    was sometimes the worst of the list. A 3/4 cover, the commonest portrait
    box there is, came out as 4/5; a 792x680 PlayStation box (1.165) came out
    as 16/11 (1.455), a quarter too wide. The grid draws its box from this
    value and fits the art with object-fit: cover, so the difference was eaten
    off the top and bottom of the art; the detail page fits with contain, so
    the same mismatch showed up there as bars down the sides.

    Picking the closest entry outright cannot drift like that.
    """
    try:
        from PIL import Image
        with Image.open(path) as img:
            w, h = img.size
        if not w or not h:
            return None
        ratio = w / h
        return min(_COVER_RATIOS, key=lambda rv: abs(rv[1] - ratio))[0]
    except Exception as e:
        logger.debug("Could not detect cover aspect from %s: %s", path, e)
        return None


_CT_EXT = {
    "image/png":  "png", "image/jpeg": "jpg", "image/jpg": "jpg",
    "image/webp": "webp", "image/gif": "gif", "image/bmp": "bmp",
    "video/mp4":  "mp4", "video/webm": "webm",
}

async def _download_image(url: str, dest: Path, *, replace: bool = False) -> Path | None:
    """Download *url* to *dest*.

    If the destination extension looks ambiguous (e.g. '.php', '.aspx'),
    the actual extension is detected from the response Content-Type header
    and the file is written with the correct extension instead.

    Without *replace* a file already at *dest* is left alone and handed back:
    this is the gap-filling pass, which fetches nothing it already has.

    With *replace* the media slot is being deliberately refreshed, and the two
    halves of that are what this function exists to get right:

      * whatever is there is not consulted, so a forced re-scrape actually
        re-fetches. Callers used to arrange this by deleting the old files
        first, which is the other half of the problem;

      * the old files go only once the new bytes are in hand. A timeout, a 404
        or a provider having a bad afternoon costs nothing at all. Deleting
        first cost the picture, and the row went on pointing at a path that no
        longer existed - which nothing later noticed, because every "does it
        already have one" test reads the column and not the disk.

    The whole body is read before anything is written (fetch_media_bytes streams
    it under a ceiling), so a failure raises before a single old file is touched.

    Returns the actual Path where the file was saved, or None on failure.
    """
    _REAL_EXTS = {"png", "jpg", "jpeg", "webp", "gif", "bmp", "mp4", "webm", "svg"}
    if not url:
        return None
    if dest.exists() and not replace:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    try:
        content, ctype = await fetch_media_bytes(
            url, headers={"User-Agent": "GamesDownloader/3.0"}, timeout=30
        )
        # Detect real extension from Content-Type when URL ext is ambiguous
        url_ext = dest.suffix.lstrip(".").lower()
        if url_ext not in _REAL_EXTS:
            ct = ctype.split(";")[0].strip()
            real_ext = _CT_EXT.get(ct)
            if real_ext:
                dest = dest.with_suffix(f".{real_ext}")
        if replace:
            # After the extension is settled, so a cover arriving as a .png
            # takes the .jpg with it rather than leaving a directory with two
            # covers in it that serves whichever the glob reaches first. Only
            # files: a directory that happens to match must not take the whole
            # request down.
            for old in dest.parent.glob(f"{dest.stem}.*"):
                if old != dest and old.is_file():
                    old.unlink(missing_ok=True)
        dest.write_bytes(content)
        return dest
    except Exception as e:
        logger.warning("Failed to download %s: %s", url, e)
        return None


def _media_slot(url: str, media_dir: Path, stem: str) -> Path:
    """Where a media slot's file goes, named from the URL's extension.

    The extension is a guess until the response arrives; _download_image
    corrects it from the Content-Type when the URL ends in something a server
    made up, like .php.
    """
    ext = url.rsplit(".", 1)[-1].split("?")[0] or "jpg"
    return media_dir / f"{stem}.{ext}"


def _rom_media_dir(platform_slug: str, rom_id: int) -> Path:
    return Path(RESOURCES_PATH) / "roms" / platform_slug / str(rom_id)


def _resource_url(platform_slug: str, rom_id: int, filename: str) -> str:
    return f"/resources/roms/{platform_slug}/{rom_id}/{filename}"


def _numeric_rating(provider_id: str, raw) -> float | None:
    """A provider's rating as a number out of ten, or None if it is not one.

    Returns None rather than raising, so one provider answering with a word
    cannot discard the ratings of every other provider in the same scrape.

    Infinities and NaN are refused along with the words. A NaN reaching the
    database is worse than a missing rating: it is not valid JSON, so it can
    break the response that carries it rather than merely look wrong.
    """
    if raw is None or isinstance(raw, bool):
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        logger.info(
            "[Plugins] %s gave %r as a rating, which is not a number, so it "
            "is ignored. A rating is a score out of ten; a provider whose "
            "field means something else (an age rating, a tier) should not "
            "send it as one.", provider_id, raw,
        )
        return None
    if value != value or value in (float("inf"), float("-inf")):
        logger.info("[Plugins] %s gave a rating of %r, which is ignored",
                    provider_id, raw)
        return None
    return round(value, 1)


def clean_plugin_ratings(stored) -> dict | None:
    """A stored ratings map with the entries that are not numbers removed.

    Returns None when nothing usable is left, so the column goes back to NULL
    rather than holding an empty object. Returns the original object unchanged
    when every entry is fine, which is how the startup pass tells the rows it
    has to rewrite from the rows it can leave alone.
    """
    if not isinstance(stored, dict) or not stored:
        return stored if stored else None
    cleaned = {}
    for provider, entry in stored.items():
        if not isinstance(entry, dict):
            continue
        value = _numeric_rating(str(provider), entry.get("rating"))
        if value is None:
            continue
        cleaned[provider] = {**entry, "rating": value}
    if not cleaned:
        return None
    return cleaned


def keep_existing_cover(rom, fill_missing: bool) -> bool:
    """Whether the cover already on disk stays rather than being replaced.

    Two rules, and they are not the same rule. A gap-filling pass replaces
    nothing that is already there. A forced pass replaces what a provider gave
    us and keeps what a person chose: the scrape can be run again at any time,
    and the file they went and found cannot be got back.

    Which of the two a cover is has to be recorded, and now is. It used to be
    read off an empty `cover_url`, on the reasoning that the upload route
    clears that field - true, but so does every ScreenScraper cover, because
    those URLs carry the developer and account passwords and are deliberately
    never stored. Our main provider left exactly the same trace as an upload.
    So a forced re-scrape could not replace any cover ScreenScraper had ever
    fetched, and re-identifying a ROM that had matched the wrong game moved the
    title and the description onto the right one while the wrong game's artwork
    stayed where it was.
    """
    return keep_existing_media(rom, "cover_path", fill_missing)


#: The columns that hold a picture the scrape can write. Keyed by column name
#: rather than by a nickname, because the two are not the same word everywhere:
#: the pictoliste is written to a file called "pictoliste" and stored in
#: picto_path, and a map keyed on one of those and read with the other records
#: nothing while looking as though it does.
MEDIA_COLUMNS: frozenset[str] = frozenset({
    "cover_path", "background_path", "support_path", "wheel_path",
    "bezel_path", "steamgrid_path", "video_path", "picto_path",
    # A list rather than a path, and marked as a whole: there is nowhere to
    # record which of six pictures a person put there, so one uploaded by hand
    # makes the set theirs and a forced pass leaves all of them.
    "screenshots",
})


def media_origin(rom, column: str) -> str | None:
    """Where the file in *column* came from: "manual", "scrape", or None if the
    row predates our recording it. The cover keeps a column of its own, from
    when it was the only slot that could tell."""
    if column == "cover_path":
        return rom.cover_source
    return (getattr(rom, "media_source", None) or {}).get(column)


def with_manual(rom, *columns: str) -> dict:
    """The row's media origins, with *columns* marked as chosen by a person.

    Merged rather than replaced, and returned rather than written: recording
    that somebody has just uploaded a background must not forget that they
    uploaded the wheel last week. Every caller writes the whole column, so
    anything that built its value from nothing would quietly drop the rest.

    The cover is not kept here. It has a column of its own, filled in for every
    existing row by a migration, and two places claiming to know where one
    picture came from is how they come to disagree.
    """
    origins = dict(getattr(rom, "media_source", None) or {})
    for column in columns:
        if column == "cover_path":
            raise KeyError("the cover's origin lives in cover_source")
        origins[column] = "manual"
    return origins


def keep_existing_media(rom, column: str, fill_missing: bool) -> bool:
    """Whether the file already in *slot* stays rather than being replaced.

    Two rules, and they are not the same rule. A gap-filling pass replaces
    nothing that is already there. A forced pass replaces what a provider gave
    us and keeps what a person chose: the scrape can be run again at any time,
    and the file they went and found cannot be got back.

    An unrecorded origin is read differently for the cover than for the rest,
    and deliberately. Every existing row was given a cover origin by a
    migration, so a null there means the row genuinely has no cover. Nothing
    filled in the other slots, so a null there means we do not know - and not
    knowing has to mean leaving it alone, or the first forced pass on an
    upgraded library deletes every background and wheel anybody uploaded.
    """
    if column not in MEDIA_COLUMNS:
        raise KeyError(f"not a media column: {column}")
    if not getattr(rom, column, None):
        return False
    if fill_missing:
        return True
    origin = media_origin(rom, column)
    if column == "cover_path":
        return origin == "manual"
    return origin != "scrape"


async def scrape_rom(
    rom: Rom,
    platform: RomPlatform,
    forced_ss_id: str | None = None,
    forced_launchbox_id: str | None = None,
    fill_missing: bool = False,
) -> dict:
    """Scrape metadata for *rom* from all configured scrapers.

    If *forced_ss_id* or *forced_launchbox_id* is provided, the respective
    source is queried directly by ID (bypassing hash/name search) - used by
    the "Scrape this version" flow in Edit Metadata.  When a forced source
    is specified, it is inserted first so it wins the merge.

    Merges results (first scraper wins for each field) and downloads images.
    Returns a dict suitable for rom_handler.update_metadata().
    """
    # Load API credentials
    ss_user  = await config_handler.get("screenscraper_username") or ""
    ss_pass  = await config_handler.get("screenscraper_password") or ""
    ss_devid = await config_handler.get("screenscraper_devid") or ""
    ss_devpw = await config_handler.get("screenscraper_devpassword") or ""
    igdb_id  = await config_handler.get("igdb_client_id") or ""
    igdb_sec = await config_handler.get("igdb_client_secret") or ""
    lb_en_raw = await config_handler.get("launchbox_enabled") or "true"
    lb_enabled = lb_en_raw.lower() in ("1", "true", "yes")
    parallel_media = await config_handler.get_bool("metadata_parallel_media", default=True)

    search_name   = rom.fs_name_no_ext or rom.fs_name
    fs_slug       = platform.fs_slug
    igdb_platform = get_igdb_id(fs_slug)
    ss_system     = get_ss_id(fs_slug)
    lb_platform   = get_launchbox_name(fs_slug)
    hltb_platform = get_hltb_name(fs_slug)

    # ── Load per-platform scrape preset ──────────────────────────────────────
    all_presets = config_manager.get_section("rom_scrape_presets") or {}
    preset      = all_presets.get(platform.fs_slug, {})
    ss_cover_type = preset.get("cover_type", "box-2D")
    ss_region     = preset.get("region",     "ss")
    ss_extras     = preset.get("extras",     [])

    results: list[dict] = []

    # ── 1. ScreenScraper ──────────────────────────────────────────────────────
    if ss_user and ss_pass:
        try:
            if forced_ss_id:
                # Direct lookup by SS game ID - skips hash/name search entirely
                logger.info("[SS] Forced ss_id=%s for ROM %s", forced_ss_id, search_name)
                ss_raw = await screenscraper_handler.get_game_by_id(
                    forced_ss_id,
                    username=ss_user,
                    password=ss_pass,
                    devid=ss_devid,
                    devpassword=ss_devpw,
                    ss_system_id=ss_system,
                )
            else:
                ss_raw = await screenscraper_handler.search_game(
                    search_name,
                    ss_system,
                    fs_name=rom.fs_name,
                    file_size=rom.fs_size_bytes,
                    crc=rom.crc_hash or "",
                    md5=rom.md5_hash or "",
                    sha1=getattr(rom, "sha1_hash", None) or "",
                    username=ss_user,
                    password=ss_pass,
                    devid=ss_devid,
                    devpassword=ss_devpw,
                )
            if ss_raw:
                results.append(screenscraper_handler.extract_metadata(
                    ss_raw,
                    cover_type=ss_cover_type,
                    region=ss_region,
                    extras=ss_extras,
                ))
        except Exception as e:
            logger.warning("[SS] Error scraping %s: %s", search_name, e)

    # ── 2. IGDB ───────────────────────────────────────────────────────────────
    if igdb_id and igdb_sec:
        try:
            igdb_raw = await igdb_rom_handler.search_game(
                search_name,
                igdb_platform,
                client_id=igdb_id,
                client_secret=igdb_sec,
            )
            if igdb_raw:
                results.append(igdb_rom_handler.extract_metadata(igdb_raw))
        except Exception as e:
            # The IGDB token endpoint takes client_id and client_secret in the
            # query string, and httpx puts the request URL into the message of
            # an HTTP error - so the exception itself must never reach the log.
            logger.warning("[IGDB] Error scraping %s: %s", search_name, loggable_error(e))

    # ── 3. LaunchBox ──────────────────────────────────────────────────────────
    if lb_enabled or forced_launchbox_id:
        try:
            if forced_launchbox_id:
                logger.info("[LB] Forced launchbox_id=%s for ROM %s", forced_launchbox_id, search_name)
                lb_data = await launchbox_handler.get_game_by_id(forced_launchbox_id)
            else:
                lb_data = await launchbox_handler.search_game(
                    search_name, lb_platform, enabled=lb_enabled
                )
            if lb_data:
                if forced_launchbox_id:
                    # Forced LB wins merge - insert at beginning
                    results.insert(0, lb_data)
                else:
                    results.append(lb_data)
        except Exception as e:
            logger.warning("[LaunchBox] Error scraping %s: %s", search_name, e)

    if not results:
        logger.info("No metadata found for ROM id=%d name=%s", rom.id, search_name)
        return {}

    # ── Extract per-source ratings before merge ─────────────────────────────
    # Each scraper returns a generic "rating" key - extract to separate fields
    for r in results:
        _src_rating = r.get("rating")
        if _src_rating is not None:
            if r.get("igdb_metadata") or r.get("igdb_id"):
                # IGDB handler already divided by 10 (0-100 -> 0-10), restore to 0-100
                r["igdb_rating"] = round(float(_src_rating) * 10, 1)
            elif r.get("launchbox_metadata") or r.get("launchbox_id"):
                r["lb_rating"] = round(float(_src_rating), 1)

    # ── Merge: first scraper wins for scalar fields; lists are combined ──────
    merged: dict = {}
    all_screenshots: list[str] = []
    for r in results:
        # Collect screenshots from ALL scrapers (SS + IGDB)
        src_ss = r.pop("screenshots", None) or []
        logger.debug("[scrape] source screenshots: %d urls", len(src_ss))
        for ss_url in src_ss:
            if ss_url and ss_url not in all_screenshots:
                all_screenshots.append(ss_url)
        for k, v in r.items():
            if v and k not in merged:
                merged[k] = v

    # ── 4. HowLongToBeat ──────────────────────────────────────────────────────
    try:
        hltb_data = await hltb_handler.search_game(search_name, hltb_platform)
        if hltb_data:
            for k, v in hltb_data.items():
                merged[k] = v
    except Exception as e:
        logger.warning("[HLTB] Error scraping %s: %s", search_name, e)

    # ── 5. Plugin ratings ────────────────────────────────────────────────────
    #
    # A rating is a number out of ten and nothing else. Providers do not all
    # agree with that: TheGamesDB's `rating` field is the age rating, so it
    # answers with "E - Everyone", and a plugin is free to send anything at
    # all. Two things used to go wrong with such an answer.
    #
    # It reached the browser. The core themes coerce a rating through a guard
    # that turns nonsense into zero, but a theme that trusts the value renders
    # `Number("E - Everyone").toFixed(1)`, which is the literal text "NaN/10"
    # sitting on the game's page.
    #
    # And it took every other provider down with it. `float()` on that string
    # raised inside the one try that wraps the whole loop, so a library with
    # PPE.pl ratings on every game lost all of them the moment one unrelated
    # plugin answered with a word. That is why the check sits per provider.
    try:
        from plugins.manager import plugin_manager
        _p_search = plugin_manager.hook.metadata_search_game(query=search_name)
        _p_ratings: dict = {}
        for _pr in _p_search:
            if not isinstance(_pr, list) or not _pr:
                continue
            _best = _pr[0]
            _pid = _best.get("provider_id", "")
            _gid = _best.get("provider_game_id", "")
            if not _pid or not _gid:
                continue
            try:
                _gd_list = plugin_manager.hook.metadata_get_game(provider_game_id=_gid)
            except Exception as _one:
                # One provider failing is one provider's rating missing.
                logger.info("[Plugins] %s could not be asked for a rating: %s",
                            _pid, _one)
                continue
            for _gd in _gd_list:
                if isinstance(_gd, dict) and _gd.get("provider_id") == _pid:
                    _r = _numeric_rating(_pid, _gd.get("rating"))
                    if _r is not None:
                        from pathlib import Path as _P
                        from config import PLUGINS_PATH as _PP2
                        _plid = _pid
                        if not _P(_PP2, _pid).is_dir():
                            for _sfx in ["-metadata", "-scraper", "-plugin"]:
                                if _P(_PP2, _pid + _sfx).is_dir():
                                    _plid = _pid + _sfx
                                    break
                        # The label names the SOURCE, not the game. `_best`
                        # comes from metadata_search_game, whose contract says
                        # `name` is the matched game's title - storing that put
                        # a game title where the provider belongs, so a rating
                        # from PPE.pl read as "GLORY OF HERACLES II". The
                        # provider's own name has a dedicated hook.
                        _pname = None
                        try:
                            for _plug in plugin_manager.get_plugin_instances():
                                _idf = getattr(_plug, "metadata_provider_id", None)
                                if callable(_idf) and _idf() == _pid:
                                    _nf = getattr(_plug, "metadata_provider_name", None)
                                    _pname = _nf() if callable(_nf) else None
                                    break
                        except Exception:
                            _pname = None
                        _p_ratings[_pid] = {
                            # Only the fallback is upper-cased: a provider name
                            # is already in its presentation form ("PPE.pl").
                            "name": _pname or _pid.upper(),
                            "rating": _r,
                            "logo_url": f"/api/plugins/{_plid}/logo",
                        }
                    break
        if _p_ratings:
            merged["plugin_ratings"] = _p_ratings
    except Exception as _pe:
        logger.debug("[Plugins] Rating extraction error: %s", _pe)

    # ── Download images ───────────────────────────────────────────────────────
    media_dir  = _rom_media_dir(platform.slug, rom.id)
    cover_url  = merged.pop("cover_url", None)
    bg_url     = merged.pop("background_url", None)
    ss_urls    = all_screenshots[:8]  # Combined SS + IGDB screenshots (max 8)
    merged.pop("extra_urls", None)  # no longer used - replaced by ES-style download below

    if keep_existing_cover(rom, fill_missing):
        cover_url = None  # keep the existing cover file untouched
    if keep_existing_media(rom, "background_path", fill_missing):
        bg_url = None     # and the same question for the background

    # Started from what the row already says rather than from nothing: a pass
    # that fetches a background must not forget that the wheel beside it was
    # uploaded by hand.
    _origins: dict[str, str] = dict(getattr(rom, "media_source", None) or {})

    def _from_scrape(column: str) -> None:
        """Record that a provider gave us this slot, so a later forced pass
        knows it may replace it. Only ever called after bytes have arrived."""
        _origins[column] = "scrape"
        merged["media_source"] = dict(_origins)

    from utils.async_utils import gather_bounded

    async def _dl_cover():
        if not cover_url:
            return
        # replace: this pass has already decided it may have the slot -
        # keep_existing_cover said so above, and fill_missing nulls the url when
        # a cover is already there. Nothing on disk goes until the bytes arrive.
        saved = await _download_image(cover_url, _media_slot(cover_url, media_dir, "cover"),
                                      replace=True)
        if saved:
            merged["cover_path"] = _resource_url(platform.slug, rom.id, saved.name)
            # Said outright, because an empty cover_url below cannot say it.
            merged["cover_source"] = "scrape"
            # Keep the original source URL so notifications can fall back to it
            # when public_base_url is unset (parity with GogGame.cover_url) - but
            # only when it is credential-free. ScreenScraper media URLs embed the
            # dev + account passwords, so they are never stored (and never sent).
            from handler.notifications.recently_added import _is_leaky_url
            if not _is_leaky_url(cover_url):
                merged["cover_url"] = cover_url
            merged["cover_type"] = ss_cover_type
            detected = _detect_cover_aspect(saved)
            if detected:
                merged["cover_aspect"] = detected

    async def _dl_bg():
        if not bg_url:
            return
        # replace, for the same reason as the cover, and here it is the only
        # thing that makes the download happen at all: nothing cleared the old
        # background first, so _download_image saw a file already at the name
        # and handed it straight back. A forced re-scrape, including one onto a
        # different game entirely, left the previous background in place.
        saved = await _download_image(bg_url, _media_slot(bg_url, media_dir, "background"),
                                      replace=True)
        if saved:
            merged["background_path"] = _resource_url(platform.slug, rom.id, saved.name)
            _from_scrape("background_path")

    # Cover and background write disjoint fields, so they download together
    # (bounded) when enabled or one at a time otherwise, like the screenshots.
    await gather_bounded([_dl_cover(), _dl_bg()], parallel=parallel_media)

    if keep_existing_media(rom, "screenshots", fill_missing):
        ss_urls = []

    async def _one_shot(idx: int, ss_url: str) -> str | None:
        # replace, like every other slot this pass has decided it may have. A
        # gap-filling pass empties ss_urls above when the ROM already has
        # screenshots, so reaching here means these are wanted; without it the
        # numbered name already on disk was handed back and a forced re-scrape
        # kept the previous game's pictures.
        saved = await _download_image(
            ss_url, _media_slot(ss_url, media_dir, f"screenshot_{idx}"), replace=True)
        return _resource_url(platform.slug, rom.id, saved.name) if saved else None

    # Screenshots come from ScreenScraper, whose media host counts simultaneous
    # requests, so the fan-out is off by config default-on but bounded and can be
    # turned off entirely; order is preserved regardless.
    _shot_results = await gather_bounded(
        [_one_shot(idx, ss_url) for idx, ss_url in enumerate(ss_urls[:6])],
        parallel=parallel_media,
    )
    saved_ss = [r for r in _shot_results if r]
    if saved_ss:
        merged["screenshots"] = saved_ss
        _from_scrape("screenshots")

    # ── ES-style: always download support, wheel, steamgrid, video, bezel ────
    # Use extract_media_urls to get all categorised media from raw SS response,
    # then pick the best item per category and save to proper DB columns.
    # This mirrors what EmulationStation downloads automatically.
    ss_raw_for_extra = None
    for r in results:
        if r.get("is_identified") and r.get("ss_metadata"):
            ss_raw_for_extra = r["ss_metadata"]
            break

    if ss_raw_for_extra:
        region_pref = screenscraper_handler._build_region_pref(ss_region)
        all_media   = screenscraper_handler.extract_media_urls(ss_raw_for_extra)

        # (category_in_extract, filename_base, merged_key)
        _es_media = [
            ("supports",      "support",   "support_path"),
            ("bezels",        "bezel",     "bezel_path"),
            ("steamgrids",    "steamgrid", "steamgrid_path"),
            ("videos",        "video",     "video_path"),
            ("pictos",        "pictoliste","picto_path"),
        ]
        downloaded = 0

        # ── Wheel: wheel-hd (wor→ss→usa→eu) then wheel (same order) ─────────
        if not merged.get("wheel_path") and not keep_existing_media(rom, "wheel_path", fill_missing):
            _wheel_region_pref = ["wor", "ss", "usa", "eu"]
            wheels = all_media.get("wheels", [])
            wheel_best = None
            for wtype in ("wheel-hd", "wheel"):
                typed = [w for w in wheels if w.get("type") == wtype]
                if typed:
                    wheel_best = next(
                        (w for rp in _wheel_region_pref for w in typed if w.get("region") == rp),
                        typed[0],
                    )
                    break
            if not wheel_best and wheels:
                wheel_best = wheels[0]
            if wheel_best:
                url = wheel_best.get("url", "")
                if url:
                    saved = await _download_image(
                        url, _media_slot(url, media_dir, "wheel"), replace=True)
                    if saved:
                        merged["wheel_path"] = _resource_url(platform.slug, rom.id, saved.name)
                        _from_scrape("wheel_path")
                        downloaded += 1

        for cat, fname, col in _es_media:
            if merged.get(col):
                continue
            if keep_existing_media(rom, col, fill_missing):
                continue
            items = all_media.get(cat, [])
            if not items:
                continue
            best = next(
                (m for rp in region_pref for m in items if m.get("region") == rp),
                items[0],
            )
            url = best.get("url", "")
            if not url:
                continue
            # Each of these is guarded above by the same two questions the cover
            # asks, so arriving here is the decision to fetch. Without replace
            # the file already at the name was handed straight back and support,
            # bezel, Steam Grid, video and picto stayed at whatever the last
            # scrape left, forced pass or not.
            saved = await _download_image(
                url, _media_slot(url, media_dir, fname), replace=True)
            if saved:
                merged[col] = _resource_url(platform.slug, rom.id, saved.name)
                _from_scrape(col)
                downloaded += 1
        if downloaded:
            logger.info("[ROM] Downloaded %d ES-style media files for rom id=%d", downloaded, rom.id)

    # ── SteamGridDB fallback - grid cover + hero background ──────────────────
    # Runs when SS didn't provide steamgrid_path and/or background_path.
    need_grid = (not merged.get("steamgrid_path")
                 and not keep_existing_media(rom, "steamgrid_path", fill_missing))
    need_bg   = (not merged.get("background_path")
                 and not keep_existing_media(rom, "background_path", fill_missing))
    if need_grid or need_bg:
        try:
            _sgdb_key = await config_handler.get("steamgriddb_api_key")
            if _sgdb_key:
                _hdrs = {"Authorization": f"Bearer {_sgdb_key}"}
                async with httpx.AsyncClient(timeout=15) as _c:
                    _rs = await _c.get(
                        f"https://www.steamgriddb.com/api/v2/search/autocomplete/{search_name}",
                        headers=_hdrs,
                    )
                    if _rs.status_code == 200 and _rs.json().get("data"):
                        _sgdb_id = _rs.json()["data"][0]["id"]
                        if need_grid:
                            _rg = await _c.get(
                                f"https://www.steamgriddb.com/api/v2/grids/game/{_sgdb_id}",
                                params={"dimensions": "342x482,600x900", "limit": 5},
                                headers=_hdrs,
                            )
                            if _rg.status_code == 200:
                                _items = _rg.json().get("data", [])
                                if _items:
                                    _url  = _items[0]["url"]
                                    _saved = await _download_image(
                                        _url, _media_slot(_url, media_dir, "steamgrid"),
                                        replace=True)
                                    if _saved:
                                        merged["steamgrid_path"] = _resource_url(platform.slug, rom.id, _saved.name)
                                        _from_scrape("steamgrid_path")
                                        logger.info("[ROM] SGDB grid downloaded for rom id=%d", rom.id)
                        if need_bg:
                            _rh = await _c.get(
                                f"https://www.steamgriddb.com/api/v2/heroes/game/{_sgdb_id}",
                                params={"limit": 5},
                                headers=_hdrs,
                            )
                            if _rh.status_code == 200:
                                _items = _rh.json().get("data", [])
                                if _items:
                                    _url  = _items[0]["url"]
                                    # The same slot _dl_cover's neighbour writes.
                                    # Without replace this handed back whatever
                                    # background was already there and then said
                                    # in the log that it had downloaded one.
                                    _saved = await _download_image(
                                        _url, _media_slot(_url, media_dir, "background"),
                                        replace=True)
                                    if _saved:
                                        merged["background_path"] = _resource_url(platform.slug, rom.id, _saved.name)
                                        _from_scrape("background_path")
                                        logger.info("[ROM] SGDB hero downloaded as background for rom id=%d", rom.id)
        except Exception as _e:
            logger.debug("[SGDB] ROM scrape fallback error for rom id=%d: %s", rom.id, _e)

    # Fill-missing mode: keep every field the ROM already has - only the gaps
    # (per FIELD, not per ROM) get the freshly scraped values.
    if fill_missing:
        def _empty(v) -> bool:
            return v is None or v == "" or v == [] or v == {}
        merged = {k: v for k, v in merged.items() if _empty(getattr(rom, k, None))}

    return merged


async def scrape_roms_batch(rom_ids: list[int], platform: RomPlatform, fill_missing: bool = False) -> dict:
    """Scrape a list of ROMs sequentially (rate-limit friendly).

    Returns { scraped, skipped, errors }.
    """
    stats = {"scraped": 0, "skipped": 0, "errors": 0}
    for rom_id in rom_ids:
        rom = await rom_handler.get_by_id(rom_id)
        if rom is None:
            stats["skipped"] += 1
            continue
        try:
            data = await scrape_rom(rom, platform, fill_missing=fill_missing)
            if data:
                await rom_handler.update_metadata(rom_id, data)
                stats["scraped"] += 1
                # ROM now has (usually) a cover -> fire the one-shot recently-added
                # card. Idempotent per ROM; burst-capped so a bulk platform scrape
                # of a fresh library can't flood the webhook.
                try:
                    from handler.notifications.recently_added import schedule_rom
                    schedule_rom(rom_id)
                except Exception:
                    pass
            else:
                stats["skipped"] += 1
        except Exception as e:
            logger.error("Error scraping ROM id=%d: %s", rom_id, e)
            stats["errors"] += 1
        # Small delay between requests to be polite to scrapers
        await asyncio.sleep(0.5)

    return stats


async def scrape_platform_info(platform: RomPlatform) -> dict:
    """Fetch ScreenScraper system info (photo, description, etc.) for a platform.

    Downloads the platform photo to
    ``/data/resources/platforms/{fs_slug}/photo.{ext}``
    and returns a dict suitable for storing in config_manager["platform_info"].
    """
    from handler.metadata.rom_platform_map import get_ss_id

    ss_user  = await config_handler.get("screenscraper_username") or ""
    ss_pass  = await config_handler.get("screenscraper_password") or ""
    ss_devid = await config_handler.get("screenscraper_devid") or ""
    ss_devpw = await config_handler.get("screenscraper_devpassword") or ""
    if not ss_user or not ss_pass:
        logger.warning("[Platform] SS credentials not configured - cannot scrape platform info")
        return {}

    ss_id = get_ss_id(platform.fs_slug)
    if not ss_id:
        logger.info("[Platform] No SS system ID for fs_slug=%s", platform.fs_slug)
        return {}

    system_raw = await screenscraper_handler.get_system_info(
        ss_id, username=ss_user, password=ss_pass,
        devid=ss_devid, devpassword=ss_devpw,
    )
    if not system_raw:
        logger.warning("[Platform] SS returned no system info for id=%d fs_slug=%s", ss_id, platform.fs_slug)
        return {}

    info = screenscraper_handler.extract_system_info(system_raw)

    # ── Wikipedia description ─────────────────────────────────────────────────
    # Use LaunchBox name (most complete) → eu → fallback name for best title match
    noms = system_raw.get("noms") or {}
    wiki_name = (
        noms.get("nom_launchbox") or noms.get("nom_eu") or noms.get("nom_us") or info.get("name") or ""
    )
    wiki_description: str | None = None
    wiki_url: str | None = None
    if wiki_name:
        try:
            import urllib.parse as _up
            _title = _up.quote(wiki_name.replace(" ", "_"), safe="")
            _wiki_api = f"https://en.wikipedia.org/api/rest_v1/page/summary/{_title}"
            async with httpx.AsyncClient(timeout=10, follow_redirects=True,
                                          headers={"User-Agent": "GamesDownloader/3.0 (emulation library)"}) as _c:
                _r = await _c.get(_wiki_api)
                if _r.status_code == 200:
                    _data = _r.json()
                    wiki_description = _data.get("extract") or None
                    _page_url = (_data.get("content_urls") or {}).get("desktop", {}).get("page")
                    wiki_url = _page_url or None
                    logger.info("[Platform] Wikipedia description fetched for %r (%d chars)",
                                wiki_name, len(wiki_description or ""))
                else:
                    logger.info("[Platform] Wikipedia 404/error for %r (status=%d)", wiki_name, _r.status_code)
        except Exception as _e:
            logger.warning("[Platform] Wikipedia fetch failed for %r: %s", wiki_name, _e)

    # Common media dir for this platform
    photo_dir = Path(RESOURCES_PATH) / "platforms" / platform.fs_slug
    photo_dir.mkdir(parents=True, exist_ok=True)

    async def _dl_platform_media(url: str | None, fname: str) -> str | None:
        if not url:
            return None
        saved = await _download_image(url, _media_slot(url, photo_dir, fname), replace=True)
        if saved:
            return f"/resources/platforms/{platform.fs_slug}/{saved.name}"
        return None

    # Download platform photo (world > ss/Monde > usa > japan)
    photo_path = await _dl_platform_media(info.get("photo_url"), "photo")

    # Download platform icon (logo-monochrome or logo) - in background, no rush
    icon_path  = await _dl_platform_media(info.get("icon_url"),  "icon")

    # Download platform bezel - may be None if SS doesn't include it
    bezel_path = await _dl_platform_media(info.get("bezel_url"), "bezel")

    result = {
        "photo_path":   photo_path,
        "icon_path":    icon_path,
        "bezel_path":   bezel_path,
        "description":  wiki_description or info.get("description"),
        "wiki_url":     wiki_url,
        "manufacturer": info.get("manufacturer"),
        "release_year": info.get("release_year"),
        "end_year":     info.get("end_year"),
        "generation":   info.get("generation"),
    }
    logger.info("[Platform] Scraped info for %s: manufacturer=%s year=%s",
                platform.fs_slug, result["manufacturer"], result["release_year"])
    return result
