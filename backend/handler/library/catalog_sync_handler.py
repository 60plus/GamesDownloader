"""Turn what a catalogue plugin describes into rows the rest of GD understands.

The plugin says what exists somewhere else; this decides what that means here.
Keeping the split at that line is the point: a plugin cannot write to the
database, cannot hot-link a CDN image into the UI, and cannot put a game into a
library the admin did not name. It hands over a list and core does the rest.

Nothing here downloads a game. An entry becomes a LibraryGame with no files -
present in the storefront, visibly not on the server yet - and only an explicit
download turns its builds into LibraryFile rows.
"""

from __future__ import annotations

import asyncio
import glob
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import func, select

from config import RESOURCES_PATH
from handler.database.library_registry_handler import library_registry_handler
from handler.database.session import async_session_factory
from models.catalog_entry import CatalogEntry
from models.library import Library
from models.library_file import LibraryFile  # noqa: F401 - resolves LibraryGame.files mapper
from models.library_game import LibraryGame
from plugins.manager import plugin_manager
from utils.http import fetch_media_bytes

logger = logging.getLogger(__name__)

ICON_DIR_NAME = "catalog-icons"
# Same set the library icon upload accepts. An entry whose artwork is something
# else keeps no cover rather than storing a file the browser will not render.
_ICON_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
_MAX_ICON_BYTES = 4 * 1024 * 1024

# One in-flight sync per catalogue. In-process only, which is the right scope
# here: there is one application process, and a lock in the database would
# outlive a crash with nothing to release it.
_sync_locks: dict[str, asyncio.Lock] = {}

# One in-flight download per catalogue entry, same reasoning as the sync lock: a
# double-clicked download otherwise races itself, and the two runs either make
# the same game twice or one rolls back the empty game the other is still filling.
_download_locks: dict[int, asyncio.Lock] = {}


class SyncInProgress(RuntimeError):
    """A sync of this catalogue is already running."""


class DownloadInProgress(RuntimeError):
    """A download of this catalogue entry is already running."""


def _slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", (name or "").lower()).strip("-")
    return s or "entry"


def list_catalogs() -> list[dict[str, str]]:
    """Every catalogue a loaded plugin offers."""
    out: list[dict[str, str]] = []
    for inst in plugin_manager.get_plugin_instances():
        id_fn = getattr(inst, "library_catalog_id", None)
        if not callable(id_fn):
            continue
        try:
            cid = id_fn()
        except Exception:
            logger.warning("A catalogue plugin failed to report its id", exc_info=True)
            continue
        if not cid:
            continue
        name_fn = getattr(inst, "library_catalog_name", None)
        try:
            name = name_fn() if callable(name_fn) else cid
        except Exception:
            name = cid
        out.append({"id": str(cid), "name": str(name)})
    return out


def _instance_for(catalog_id: str):
    for inst in plugin_manager.get_plugin_instances():
        fn = getattr(inst, "library_catalog_id", None)
        try:
            if callable(fn) and fn() == catalog_id:
                return inst
        except Exception:
            continue
    return None


def _parse_date_str(value):
    """The entry's string release date ("2001-05-01" or "2001") into a Date.

    The entry keeps the date as a string (a store label); the game's column is a
    Date. A bare year or an empty string yields None rather than raising when the
    game is inserted.
    """
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").date()
    except ValueError:
        pass
    try:
        return datetime.strptime(text[:4], "%Y").date()
    except ValueError:
        return None


def _parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    try:
        txt = str(value).replace("Z", "+00:00")
        dt = datetime.fromisoformat(txt)
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt
    except ValueError:
        return None


async def store_catalog_media(
    dir_name: str, stem: str, url: str, *, max_bytes: int = _MAX_ICON_BYTES,
) -> str | None:
    """Download catalogue artwork and return a local /resources URL.

    Through the shared media fetcher, so the SSRF guard applies here exactly as
    it does to a scraper's cover - a catalogue is external input like any other.
    Serving it locally afterwards is a house rule: no page in GD hot-links a CDN.

    Shared with the metadata pass, which stores covers the same way into a
    different directory. One copy of the write-then-sweep ordering below is
    enough - it is the part that is easy to get subtly wrong.

    A picked ScreenScraper image arrives as an opaque /api/media/proxy token -
    its real URL carries the account password, so it never reached the browser.
    Resolve it back to that credentialed URL here, server-side, and fetch it the
    same way as any public one. A public URL passes through unchanged; a token
    that will not decode yields None, and we store nothing rather than try to
    fetch the relative proxy path.
    """
    from utils.media_proxy import resolve_proxy_url
    url = resolve_proxy_url(url)
    if not url:
        logger.info("No artwork for %s/%s (unresolvable media url)", dir_name, stem)
        return None
    ext = os.path.splitext(url.split("?")[0].split("#")[0])[1].lower()
    if ext not in _ICON_EXTS:
        ext = ".png"
    try:
        # The ceiling is enforced while the bytes arrive rather than after the
        # whole body is in memory, so a catalogue pointing icon_url at a huge
        # file costs a rejected request instead of the container.
        content, _ctype = await fetch_media_bytes(url, max_bytes=max_bytes)
    except Exception as exc:
        logger.info("No artwork for %s/%s (%s)", dir_name, stem, exc)
        return None
    if not content:
        return None

    media_dir = os.path.join(RESOURCES_PATH, dir_name)
    os.makedirs(media_dir, exist_ok=True)
    dest = os.path.join(media_dir, f"{stem}{ext}")
    try:
        # Written first, then the stale siblings go. Deleting up front left the
        # game pointing at a file that no longer existed whenever the write - or
        # the surrounding transaction - failed afterwards.
        with open(dest, "wb") as fh:
            fh.write(content)
    except OSError as exc:
        logger.warning("Could not write artwork %s/%s: %s", dir_name, stem, exc)
        return None
    for old in glob.glob(os.path.join(media_dir, f"{stem}.*")):
        if os.path.abspath(old) == os.path.abspath(dest):
            continue
        try:
            os.remove(old)
        except OSError:
            pass
    return f"/resources/{dir_name}/{stem}{ext}?v={int(os.path.getmtime(dest))}"


async def _store_icon(catalog_id: str, external_id: str, url: str) -> str | None:
    """The sync's own artwork, named after the catalogue entry it belongs to."""
    return await store_catalog_media(
        ICON_DIR_NAME, f"{_slugify(catalog_id)}-{_slugify(external_id)}", url,
    )


async def _unique_slug(session, entry: dict, own_game_id: int | None) -> str:
    """A readable slug, falling back to the catalogue identity on a clash.

    Two ports can share a title (a remake and its original), and the slug is a
    URL, so the first one there keeps the pretty one.
    """
    base = _slugify(entry["title"])
    alt = _slugify(entry["external_id"].replace("/", "-"))
    # The numbered tail is not decoration: two entries whose title-slug AND
    # external-slug are both taken used to get the same "unique" fallback, and
    # the second one failed the slug constraint - taking the whole sync with it.
    candidates = [base, alt] + [f"{alt[:110]}-{n}" for n in range(2, 60)]
    for candidate in candidates:
        row = (await session.execute(
            select(LibraryGame).where(LibraryGame.slug == candidate)
        )).scalars().first()
        if row is None or row.id == own_game_id:
            return candidate
    raise ValueError(f"could not find a free slug for {entry['external_id']!r}")


def _clip(value: Any, limit: int) -> str | None:
    """Trim a catalogue string to what its column can hold, or None if empty."""
    text = str(value or "").strip()
    return text[:limit] or None


def _valid(entry: Any) -> bool:
    return (
        isinstance(entry, dict)
        and str(entry.get("external_id") or "").strip() != ""
        and str(entry.get("title") or "").strip() != ""
    )


def entry_to_dict(
    row: CatalogEntry, downloaded_game_ids: set[int] | None = None
) -> dict[str, Any]:
    # library_game_id is set the moment a download is queued; the store only
    # calls an entry owned once a build has actually landed as a LibraryFile. The
    # async caller passes the ids of entries whose game has one (this builder
    # cannot query). With no set given it falls back to the weaker "a game
    # exists" - every caller that can query passes the set.
    downloaded = row.library_game_id is not None and (
        downloaded_game_ids is None or row.library_game_id in downloaded_game_ids
    )
    return {
        "id":            row.id,
        "external_id":   row.external_id,
        "title":         row.title,
        "subtitle":      row.subtitle,
        "catalog_title": row.catalog_title,
        "category":      row.category,
        "homepage":      row.homepage,
        # The scraped 3:4 cover for the store and detail; the square catalogue
        # icon is the fallback. Both served locally, per the house rule.
        "cover_path":    row.cover_path or row.icon_path,
        "icon_path":     row.icon_path,
        # Hero + logo drive the storefront's hero carousel and spotlight banner.
        "background_path": row.background_path,
        "logo_path":     row.logo_path,
        # Scraped presentation the entry detail shows before a download.
        "description":   row.description,
        "developer":     row.developer,
        "publisher":     row.publisher,
        "release_date":  row.release_date,
        "rating":        row.rating,
        "genres":        list(row.genres) if row.genres else [],
        # The rest of the GogGame-equivalent presentation, so the entry detail
        # reads as full as a GOG game.
        "screenshots":   list(row.screenshots) if row.screenshots else [],
        "meta_ratings":  dict(row.meta_ratings) if row.meta_ratings else {},
        "languages":     dict(row.languages) if row.languages else {},
        "requirements":  dict(row.requirements) if row.requirements else None,
        "hltb_main_s":     row.hltb_main_s,
        "hltb_complete_s": row.hltb_complete_s,
        "available":     bool(row.available),
        "unavailable_reason": row.unavailable_reason,
        "release_tag":   row.release_tag,
        "released_at":   row.released_at.isoformat() if row.released_at else None,
        "is_prerelease": bool(row.is_prerelease),
        "assets":        list(row.assets or []),
        # The download turns a listing into a game (GOG model). library_game_id
        # is set when the download is queued; `downloaded` (computed above) waits
        # for a build to actually land, so a failed download reads as on offer.
        "library_game_id": row.library_game_id,
        "downloaded":    downloaded,
        "checked_at":    row.checked_at.isoformat() if row.checked_at else None,
        # The metadata pass, surfaced so a wrong match is visible in the list -
        # a low confidence or a matched_title that reads wrong is the cue to fix
        # the search term and re-scrape the one entry.
        "meta_scraped_at":   row.meta_scraped_at.isoformat() if row.meta_scraped_at else None,
        "meta_search_term":  row.meta_search_term,
        "meta_source":       row.meta_source,
        "meta_matched_title": row.meta_matched_title,
        "meta_confidence":   row.meta_confidence,
    }


async def downloaded_entry_game_ids(session, entries) -> set[int]:
    """Which of these entries' games hold at least one downloaded file.

    An entry gets a library_game_id the moment its download is queued, but a
    LibraryFile row only appears once a build has finished landing on disk. The
    store treats the first as "download started" and the second as "owned", so an
    entry whose download failed - a game with no files - reads as on offer again.
    """
    game_ids = {e.library_game_id for e in entries if e.library_game_id is not None}
    if not game_ids:
        return set()
    rows = (await session.execute(
        select(LibraryFile.library_game_id)
        .where(LibraryFile.library_game_id.in_(game_ids))
        .distinct()
    )).scalars().all()
    return {gid for gid in rows if gid is not None}


async def list_entries(catalog_id: str) -> list[dict[str, Any]]:
    async with async_session_factory() as session:
        rows = (await session.execute(
            select(CatalogEntry)
            .where(CatalogEntry.catalog_id == catalog_id)
            .order_by(CatalogEntry.title)
        )).scalars().all()
        downloaded = await downloaded_entry_game_ids(session, rows)
        return [entry_to_dict(r, downloaded) for r in rows]


async def count_entries(catalog_id: str) -> int:
    """How many entries a catalogue holds, without building any of them.

    The home page shows this number on a store's card. It was calling list_entries
    and reading its length - the whole catalogue, every entry's description,
    screenshots and assets, serialised only to be counted. A COUNT keeps that hot
    path flat as the catalogue grows.
    """
    async with async_session_factory() as session:
        return int((await session.execute(
            select(func.count()).select_from(CatalogEntry).where(
                CatalogEntry.catalog_id == catalog_id
            )
        )).scalar_one())


async def get_entry(entry_id: int, *, session=None) -> CatalogEntry | None:
    if session is not None:
        return (await session.execute(
            select(CatalogEntry).where(CatalogEntry.id == entry_id)
        )).scalars().first()
    async with async_session_factory() as own:
        return (await own.execute(
            select(CatalogEntry).where(CatalogEntry.id == entry_id)
        )).scalars().first()


async def _ensure_game_for_entry(session, entry: CatalogEntry) -> tuple[LibraryGame, str]:
    """Return the game an entry downloads into, creating it on the first download.

    The GOG shape: the catalogue lists, and a download turns one listing into a
    real game in the Games library. Before that first download the entry is not
    a game at all - it has no LibraryGame, so it never showed to a user, was
    never editable as a game, and never counted anywhere. Returns the game and
    the on-disk folder its files belong under.
    """
    # The store library names the folder its downloads live under, the way GOG
    # puts installers under /GOG. Read from the store, not the game's library
    # membership, because the game lives in Games while its files live here.
    store = (await session.execute(
        select(Library).where(
            Library.catalog_id == entry.catalog_id, Library.is_store.is_(True)
        )
    )).scalars().first()
    folder = (store.storage_folder if store and store.storage_folder else "CUSTOM")

    if entry.library_game_id:
        game = (await session.execute(
            select(LibraryGame).where(LibraryGame.id == entry.library_game_id)
        )).scalars().first()
        if game is not None:
            return game, folder

    # Born now, straight into the Games library (in_default_library), which is
    # what a GOG publish does too. Its metadata is COPIED from the entry, which
    # the metadata pass has already scraped - so the game arrives fully dressed
    # without a second round of API calls, the way a GOG publish copies from the
    # GogGame. The scraped 3:4 cover is preferred; the square icon is a fallback.
    game = LibraryGame(
        # "custom" so the dashboard and library totals bucket it - an unknown
        # source made these games invisible to both. Which catalogue it came
        # from is recorded on the catalog_entry, where it belongs.
        source="custom",
        title=entry.title,
        subtitle=entry.subtitle,
        slug=await _unique_slug(
            session, {"title": entry.title, "external_id": entry.external_id}, None,
        ),
        cover_path=entry.cover_path or entry.icon_path,
        background_path=entry.background_path or None,
        logo_path=entry.logo_path or None,
        description=entry.description or None,
        developer=entry.developer or None,
        publisher=entry.publisher or None,
        release_date=_parse_date_str(entry.release_date),
        rating=entry.rating,
        genres=list(entry.genres) if entry.genres else None,
        tags=[entry.category] if entry.category else None,
        # The rest of the scraped presentation, copied so the downloaded game is
        # as dressed as the listing was - the GOG publish shape.
        screenshots=list(entry.screenshots) if entry.screenshots else None,
        meta_ratings=dict(entry.meta_ratings) if entry.meta_ratings else None,
        languages=dict(entry.languages) if entry.languages else None,
        requirements=dict(entry.requirements) if entry.requirements else None,
        hltb_main_s=entry.hltb_main_s,
        hltb_complete_s=entry.hltb_complete_s,
        is_active=True,
        in_default_library=True,
    )
    session.add(game)
    await session.flush()
    entry.library_game_id = game.id
    return game, folder


async def _unique_storage_title(session, game_id: int, storage_folder: str, title: str) -> str:
    """The folder name a catalogue game's builds land under, disambiguated only
    when it would otherwise be another game's.

    Two catalogue entries can carry the same title, and _dest_dir_for keys the
    on-disk folder on the title, so their builds would share a folder - a
    re-download overwriting the other's, a delete stranding it. A game first to a
    title, or re-downloading into its own, keeps the clean title; a game whose
    title-folder already holds a different game's files gets its id appended.

    The check reads committed LibraryFile rows, and a build writes one only once
    it has finished landing. So it resolves the common case - a title downloaded,
    then a second entry of the same title downloaded later - but two same-titled
    entries whose downloads are in flight at the same instant can still both take
    the clean folder, and deleting one then re-downloading the other can move it
    (no data is lost either way; files cascade by library_game_id). Closing those
    fully would mean persisting the chosen folder on the game at creation rather
    than deriving it from disk on each download.
    """
    from config import BASE_PATH, GAMES_PATH
    from endpoints.library.upload_router import _sanitize

    base_dir = os.path.join(GAMES_PATH, storage_folder, _sanitize(title))
    rel = os.path.relpath(base_dir, BASE_PATH).replace(os.sep, "/")
    # A stray %/_ in the path is a LIKE wildcard; escape so the prefix cannot
    # match beyond this exact folder.
    esc = rel.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    clash = (await session.execute(
        select(LibraryFile.id)
        .where(
            LibraryFile.file_path.like(f"{esc}/%", escape="\\"),
            LibraryFile.library_game_id != game_id,
        )
        .limit(1)
    )).first()
    return f"{title} [{game_id}]" if clash else title


async def queue_entry_downloads(
    entry_id: int, asset_names: list[str] | None, *,
    actor: str | None, max_bytes: int,
) -> dict[str, Any]:
    """Pull a catalogue entry's builds onto the server.

    On the first download the entry becomes a game in the Games library, then
    the builds arrive. Each build is its own download through the shared URL
    path, so the SSRF guard, the size ceiling and the virus scan all apply
    exactly as they do to a link an admin pastes in by hand. Sizes are known
    from the catalogue, so an oversized build is refused before a byte moves.

    One download per entry at a time. A second click while the first is still
    running would otherwise race on making the game and on the empty-game
    rollback below - the loser could delete the game the winner is filling.
    """
    lock = _download_locks.setdefault(entry_id, asyncio.Lock())
    if lock.locked():
        raise DownloadInProgress(f"A download of entry {entry_id} is already running")
    async with lock:
        return await _queue_entry_downloads_locked(
            entry_id, asset_names, actor=actor, max_bytes=max_bytes,
        )


async def _queue_entry_downloads_locked(
    entry_id: int, asset_names: list[str] | None, *,
    actor: str | None, max_bytes: int,
) -> dict[str, Any]:
    from endpoints.library.upload_router import queue_url_download
    from handler.database.library_handler import LibraryHandler

    # Creation and validation share one transaction, so a rejected download
    # never leaves a half-made game behind.
    async with async_session_factory() as session:
        async with session.begin():
            entry = await get_entry(entry_id, session=session)
            if entry is None:
                raise LookupError(f"No catalogue entry {entry_id}")
            if not entry.available:
                raise ValueError(entry.unavailable_reason or "this entry is not available")
            assets = list(entry.assets or [])
            if not assets:
                raise ValueError("this entry has no downloadable build")

            if asset_names is not None:
                wanted = set(asset_names)
                assets = [a for a in assets if a.get("name") in wanted]
                missing = wanted - {a.get("name") for a in assets}
                if missing:
                    raise ValueError(f"not offered by this entry: {', '.join(sorted(missing))}")
            if not assets:
                raise ValueError("no build selected")

            oversized = [a for a in assets if int(a.get("size") or 0) > max_bytes]
            if oversized:
                raise ValueError(
                    "larger than the upload limit: "
                    + ", ".join(str(a.get("name")) for a in oversized)
                )

            # A game made by THIS call is the only one safe to undo if nothing
            # queues - an entry already pointing at a game has real files from an
            # earlier download.
            game_was_new = entry.library_game_id is None
            game, folder = await _ensure_game_for_entry(session, entry)
            game_id = game.id
            game_was_new = game_was_new and entry.library_game_id is not None
            entry_title = entry.title
            release_tag = entry.release_tag
            # Keep two same-titled entries out of one on-disk folder.
            storage_title = await _unique_storage_title(session, game_id, folder, game.title)

    # No scrape here: the entry was already scraped, and the game copied its
    # cover and metadata on creation - the way a GOG publish copies from the
    # GogGame. The download stays self-contained, with no third-party call.
    game = await LibraryHandler().get_by_id(game_id)
    started, failed = [], []
    for asset in assets:
        url = str(asset.get("url") or "")
        if not url:
            failed.append({"name": asset.get("name"), "error": "no download URL"})
            continue
        try:
            job = await queue_url_download(
                game, url,
                os_platform=str(asset.get("os") or "all"),
                file_type="game",
                # The release tag, not a version number - see the model. It is
                # what the project itself calls this build, which beats
                # inventing something tidier that matches nothing upstream.
                version=release_tag or None,
                actor=actor, max_bytes=max_bytes,
                # Files under the store's folder (/data/games/PC Ports/...),
                # even though the game shows in the Games library.
                storage_folder=folder,
                storage_title=storage_title,
                # Surface the pull in the global download tray, the way a GOG
                # download shows there - a catalogue download otherwise queued
                # silently and only appeared after a manual refresh.
                tray=True,
            )
            started.append({"name": asset.get("name"), **job})
        except ValueError as exc:
            failed.append({"name": asset.get("name"), "error": str(exc)})

    # Every build was refused before a byte moved and this call is what created
    # the game: undo it, so the entry goes back on offer instead of sitting in
    # the store as an owned game with nothing in it and no way to re-trigger the
    # download.
    if game_was_new and not started:
        await _discard_empty_game(entry_id, game_id)
        logger.warning(
            "Catalogue entry %s (%s): no build could be queued, rolled back the empty game %s",
            entry_id, entry_title, game_id,
        )
        return {"started": started, "failed": failed, "title": entry_title}

    logger.info(
        "Catalogue entry %s (%s): %d build(s) queued, %d refused",
        entry_id, entry_title, len(started), len(failed),
    )
    return {"started": started, "failed": failed, "title": entry_title}


async def _discard_empty_game(entry_id: int, game_id: int) -> None:
    """Undo a download that made a game and then queued nothing onto it.

    Only ever reached for a game created in the same call, under the entry's
    download lock, so no other download is filling it. The file count is checked
    all the same, belt and braces: a game that somehow holds a file is left
    standing rather than deleted out from under it.
    """
    async with async_session_factory() as session:
        async with session.begin():
            entry = await get_entry(entry_id, session=session)
            if entry is not None and entry.library_game_id == game_id:
                entry.library_game_id = None
            game = (await session.execute(
                select(LibraryGame).where(LibraryGame.id == game_id)
            )).scalars().first()
            if game is None:
                return
            file_count = (await session.execute(
                select(func.count()).select_from(LibraryFile).where(
                    LibraryFile.library_game_id == game_id
                )
            )).scalar_one()
            if file_count == 0:
                await session.delete(game)


async def push_entry_to_game(session, entry: CatalogEntry) -> bool:
    """Copy a listing's presentation onto the game its download produced.

    The store is the source. An edit or a re-scrape there is meant to be what
    the game shows too, and without this the two drifted from the moment of the
    download: the game was scraped again on its own and ended up with another
    description, another screenshot set, and a rating on a different scale
    (4.4 out of 5 on the listing against 8.76 on the game, for the same title).

    What moves is exactly the set the metadata pass derives plus the art it
    fetches - the same set ``_clear_scraped_fields`` resets. Title, subtitle and
    category stay put on purpose: the catalogue sync stamps those on the entry
    from upstream every few hours, so pushing them would stamp over an admin's
    rename of the game on the next run, which is the very thing a separately
    named game exists to allow.

    Returns whether a game was there to write to.
    """
    if not entry.library_game_id:
        return False
    game = (await session.execute(
        select(LibraryGame).where(LibraryGame.id == entry.library_game_id)
    )).scalars().first()
    if game is None:
        return False

    game.description = entry.description or None
    game.developer = entry.developer or None
    game.publisher = entry.publisher or None
    # Free-form text on the listing, a Date column on the game.
    game.release_date = _parse_date_str(entry.release_date)
    game.rating = entry.rating
    game.hltb_main_s = entry.hltb_main_s
    game.hltb_complete_s = entry.hltb_complete_s
    game.genres = list(entry.genres) if entry.genres else None
    game.screenshots = list(entry.screenshots) if entry.screenshots else None
    game.meta_ratings = dict(entry.meta_ratings) if entry.meta_ratings else None
    game.languages = dict(entry.languages) if entry.languages else None
    game.requirements = dict(entry.requirements) if entry.requirements else None
    # The square catalogue icon stands in for a cover the scrape never found,
    # the same fallback the game was created with.
    game.cover_path = entry.cover_path or entry.icon_path or None
    game.background_path = entry.background_path or None
    game.logo_path = entry.logo_path or None
    logger.info(
        "Catalogue entry %s (%s): presentation pushed to game %s",
        entry.id, entry.title, game.id,
    )
    return True


async def _ensure_catalog_store(inst, catalog_id: str) -> Library:
    """Create or confirm the store library this catalogue lives in.

    Its details come from the plugin's ``library_catalog_library`` hook, or from
    the catalogue name when the plugin does not declare one. This is the only
    way a plugin store comes into being - an admin cannot hand-make one - which
    is the whole point of the split: the catalogue owns its shelf.
    """
    decl: dict[str, Any] = {}
    fn = getattr(inst, "library_catalog_library", None)
    if callable(fn):
        try:
            decl = fn() or {}
        except Exception:
            logger.warning("Catalogue %s: library_catalog_library failed", catalog_id, exc_info=True)
    if not isinstance(decl, dict):
        decl = {}

    name_fn = getattr(inst, "library_catalog_name", None)
    try:
        default_name = (name_fn() if callable(name_fn) else catalog_id) or catalog_id
    except Exception:
        default_name = catalog_id
    return await library_registry_handler.ensure_store_library(
        catalog_id,
        slug=_slugify(str(decl.get("slug") or catalog_id)),
        name=str(decl.get("name") or default_name),
        color=decl.get("color"),
        icon=decl.get("icon"),
        storage_folder=decl.get("storage_folder"),
    )


async def sync_catalog(
    catalog_id: str, library_slug: str | None = None, *, session=None,
) -> dict[str, Any]:
    """Fetch a catalogue and reconcile it into its store library.

    The store library is the plugin's own (created on first sync); ``library_slug``
    is accepted for backward compatibility and ignored. Returns counts the admin
    can act on - "unavailable" is reported rather than hidden, because a catalogue
    that quietly shrinks looks like a working sync.

    Passing ``session`` runs the reconcile inside a transaction the caller owns,
    which is what lets a full sync be exercised against the real database and
    then rolled back instead of tested against an agreeable mock.
    """
    lock = _sync_locks.setdefault(catalog_id, asyncio.Lock())
    if lock.locked():
        # A sync is minutes of network round trips, so an admin whose first
        # click seemed to hang will click again. Two runs racing insert the same
        # entries twice and the loser rolls everything back, which is a worse
        # answer than telling them one is already going.
        raise SyncInProgress(f"A sync of {catalog_id!r} is already running")

    async with lock:
        return await _sync_catalog_locked(catalog_id, session=session)


async def _sync_catalog_locked(catalog_id: str, *, session=None) -> dict[str, Any]:
    inst = _instance_for(catalog_id)
    if inst is None:
        raise LookupError(f"No loaded plugin offers the catalogue {catalog_id!r}")
    fetch = getattr(inst, "library_catalog_fetch", None)
    if not callable(fetch):
        raise LookupError(f"Catalogue {catalog_id!r} does not implement library_catalog_fetch")

    # The store exists before its entries do. Idempotent, so a sync is also how
    # the shelf gets created the first time round.
    store = await _ensure_catalog_store(inst, catalog_id)

    # Blocking HTTP in the plugin, off the event loop. A slow catalogue must not
    # stall the server it is being fetched for.
    entries = await asyncio.to_thread(fetch)
    if not isinstance(entries, list):
        raise ValueError(f"Catalogue {catalog_id!r} returned {type(entries).__name__}, expected a list")

    if session is not None:
        stats = await _reconcile(session, catalog_id, entries)
    else:
        async with async_session_factory() as own:
            async with own.begin():
                stats = await _reconcile(own, catalog_id, entries)

    logger.info("Catalogue %s synced into %s: %s", catalog_id, store.slug, stats)
    return stats


async def _reconcile(session, catalog_id: str, entries: list) -> dict[str, Any]:
    stats = {
        "fetched": len(entries), "created": 0, "updated": 0,
        "unavailable": 0, "skipped": 0, "retired": 0, "artwork": 0,
    }
    seen: set[str] = set()

    existing_rows = (await session.execute(
        select(CatalogEntry).where(CatalogEntry.catalog_id == catalog_id)
    )).scalars().all()
    by_external = {r.external_id: r for r in existing_rows}

    for raw in entries:
        if not _valid(raw):
            stats["skipped"] += 1
            logger.warning(
                "Catalogue %s: entry without an external_id or title, skipped: %r",
                catalog_id, raw,
            )
            continue

        entry = {
            "external_id": str(raw["external_id"]).strip()[:255],
            "title": str(raw["title"]).strip()[:255],
        }
        if entry["external_id"] in seen:
            # The same repository listed under two categories. A second insert
            # breaks the (catalog_id, external_id) unique constraint, and since
            # the whole reconcile is one transaction that would roll back every
            # other entry along with it.
            stats["skipped"] += 1
            logger.warning(
                "Catalogue %s: %r listed more than once, keeping the first",
                catalog_id, entry["external_id"],
            )
            continue
        seen.add(entry["external_id"])
        row = by_external.get(entry["external_id"])
        is_new = row is None
        if is_new:
            row = CatalogEntry(catalog_id=catalog_id, external_id=entry["external_id"])
            session.add(row)
            by_external[entry["external_id"]] = row

        available = bool(raw.get("available", True))
        reason = _clip(raw.get("unavailable_reason"), 255)
        if not available and not reason:
            reason = "no reason given by the catalogue"

        # The catalogue is authoritative for the storefront listing. Every field
        # is trimmed to its column width so one over-long upstream value cannot
        # raise on flush and roll the whole sync back. A title an admin wants
        # changed is changed on the downloaded game, which the sync never
        # touches, so there is nothing here to guard against being overwritten.
        row.title = entry["title"]
        row.subtitle = _clip(raw.get("subtitle"), 255)
        row.catalog_title = _clip(raw.get("catalog_title"), 255) or entry["title"]
        row.category = _clip(raw.get("category"), 128)
        row.homepage = _clip(raw.get("homepage"), 512)
        row.available = available
        row.unavailable_reason = None if available else reason
        row.checked_at = datetime.now(timezone.utc).replace(tzinfo=None)

        release = raw.get("release") if isinstance(raw.get("release"), dict) else None
        if release:
            row.release_tag = _clip(release.get("tag"), 128)
            row.released_at = _parse_dt(release.get("published_at"))
            row.is_prerelease = bool(release.get("prerelease"))
            assets = release.get("assets")
            row.assets = assets if isinstance(assets, list) else None
        else:
            row.assets = None

        if not available:
            stats["unavailable"] += 1
            # A downloaded game keeps its files and its place in the library -
            # the entry is only the storefront listing, and a catalogue having a
            # bad day does not reach into what is already on the server.
            continue

        # The catalogue's own square launcher icon, downloaded locally for the
        # store view. No page in GD hot-links a CDN, and the store is a page. A
        # real 3:4 cover is not fetched here: it arrives when the entry is
        # downloaded and the resulting game is scraped, which is the GOG shape -
        # the catalogue lists, a download turns a listing into a game.
        icon_url = _clip(raw.get("icon_url"), 1024)
        if icon_url and (icon_url != row.icon_url or not row.icon_path):
            stored = await _store_icon(catalog_id, entry["external_id"], icon_url)
            if stored:
                row.icon_path = stored
                row.icon_url = icon_url
                stats["artwork"] += 1

        stats["created" if is_new else "updated"] += 1

    # Entries the catalogue stopped offering. Marked, never deleted: the
    # admin may have downloaded one, and a vanished row would take the
    # only record of where it came from with it.
    for external_id, row in by_external.items():
        if external_id in seen or not row.available:
            continue
        row.available = False
        row.unavailable_reason = "no longer listed in the catalogue"
        row.assets = None
        stats["retired"] += 1

    return stats
