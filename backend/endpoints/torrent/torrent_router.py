"""Torrent endpoints.

Admin endpoints (Scope.LIBRARY_UPLOAD):
  POST /api/torrents/download        - add torrent to server (magnet/url/file)
  GET  /api/torrents/downloads       - list all admin download jobs
  GET  /api/torrents/downloads/{id}  - single download job
  DELETE /api/torrents/downloads/{id} - cancel + remove

User endpoints (authenticated):
  POST /api/torrents/seed/game/{game_id} - generate .torrent for ALL files in a game
  POST /api/torrents/seed/{file_id}      - generate .torrent for a single library file
  GET  /api/torrents/seed/{file_id}/status - check seed status

Shared:
  GET  /api/torrents/status          - Transmission availability
"""
from __future__ import annotations

import logging
import os
from pathlib import Path
import re
import unicodedata

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse
from pydantic import BaseModel

from config import BASE_PATH
from decorators.auth import protected_route
from utils.errors import RefusalError
from utils.sizes import human_bytes
from utils.uploads import read_upload_capped
from handler.auth.scopes import Scope
from handler.config.config_handler import config_handler
from handler.torrent.transmission_handler import transmission_handler

logger = logging.getLogger(__name__)

torrent_router = APIRouter(prefix="/api/torrents", tags=["torrents"])

_TORRENT_DIR = "/data/downloads/torrents"
_MAX_TORRENT_BYTES = 10 * 1024 * 1024   # a .torrent is metadata, not the payload
_SEED_DIR    = "/data/config/torrents"     # generated .torrent files for seeding

#: What a transfer somebody has DISMISSED is left as, and the one status the
#: listing hides. Deliberately NOT what a refusal writes: see REFUSED_STATUS in
#: handler/torrent/seed_monitor.py, which records what it cost when these two
#: meanings shared a word.
DISMISSED_STATUS = "removed"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _slugify(title: str) -> str:
    t = unicodedata.normalize("NFKD", title).lower()
    t = t.encode("ascii", errors="ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-") or "game"


async def _assert_game_visible(user, library_game_id: int) -> None:
    """Whether this account may have the files of that game at all.

    The three seed routes took an id and went straight to the disk: build a
    .torrent, hand it back, and set the server serving those bytes to anybody
    who asks for them. Nothing asked whether the caller was allowed the file.
    The download route two files away does ask, through `_assert_file_visible`,
    which exists because its two callers each kept their own copy of the check
    and neither knew about restricted libraries.

    Seeding is that same act with more reach. It does not send the file to one
    caller; it puts the server to work serving it, and the .torrent keeps
    working after the account that asked for it is gone.

    NOT a question about scope. These routes sit at LIBRARY_DOWNLOAD on purpose
    and it is written down - `USER_LEVEL_BY_DESIGN` in test_library_scopes.py
    names both of them. Seeding is something an ordinary account may do. What
    was missing is which FILES, and the visibility rules already know.

    404 rather than 403, matching the download route: saying "you may not have
    this" also says that it exists.
    """
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    from handler.database.session import async_session_factory
    from handler.library.visibility import membership_map, visibility_for
    from models.library_game import LibraryGame

    async with async_session_factory() as db:
        game = await db.get(LibraryGame, library_game_id)
    if not game:
        raise HTTPException(status_code=404, detail="File not available")

    vis = await visibility_for(user)
    if not vis.allows(game, (await membership_map([game.id])).get(game.id)):
        raise HTTPException(status_code=404, detail="File not available")


async def _assert_shelf_allowed(user, slug: str | None) -> None:
    """Whether this account may file a game onto that shelf.

    Both queue routes take a library slug and keep it on the row; when the
    transfer lands hours later, `_resolve_target_library` turns it into a folder
    and files the game there, having checked only that the library is
    folder-backed. Not whether the account that asked may reach it. So any shelf
    on the server could be named, restricted ones included.

    ASKED HERE, at queue time, rather than at landing. A refusal now reaches
    somebody who is standing there and can choose a different shelf; the same
    check at landing would arrive after the bytes, and would strand a legitimate
    transfer any time an administrator changed access while it ran. The case
    that would argue for re-checking - an account losing its upload right
    mid-transfer - is already answered elsewhere: the transfer changes hands to
    an administrator, who can reach everything.

    An empty slug is the built-in Games library, where nearly every torrent
    goes. It is ASKED like any other: this used to wave it through by name, on
    the grounds that nobody is on an allowlist for Games, and since then Games
    can be switched off - closed to administrators too - and made restricted. A
    torrent filed there landed on a shelf nobody could see, charged to the
    account that queued it (1.0.34 audit, #5).

    `user_can_access` is the registry's own rule, the one the library screens
    ask. Nothing new is decided here.
    """
    target = (slug or "").strip() or "games"

    from handler.database.library_registry_handler import library_registry_handler

    lib = await library_registry_handler.get_by_slug(target)
    if lib is None:
        if target == "games":
            # Seeded on every boot, so missing only on a database nothing has
            # started against. Nothing is closed that does not exist.
            return
        raise HTTPException(404, f"There is no library called '{target}'.")
    if not await library_registry_handler.user_can_access(user, lib):
        # 404 rather than 403, as everywhere else here: refusing by name would
        # tell somebody which shelves exist.
        raise HTTPException(404, f"There is no library called '{target}'.")


def _refusal(code: str, message: str, **figures) -> dict:
    """The body of a refusal: a name the screen can translate, the figures it
    needs, and a sentence for every reader that does not know the name.

    The sentence is not a courtesy. `detail` is read by three dialogs, by
    plugins and by anyone with curl, and a bare code would leave all of them
    with nothing to print.
    """
    return {"code": code, "message": message, **figures}


def _daemon_refusal(reason: str | None) -> dict:
    """What the daemon said, passed on rather than swallowed.

    "Transmission rejected the torrent" was all a caller ever got, while the
    daemon had said "invalid or corrupt torrent file" - the difference between
    a shrug and an answer. The owner read the shrug as a size problem.
    """
    said = (reason or "").strip()
    return _refusal(
        "daemon_refused",
        f"Transmission rejected the torrent: {said}" if said
        else "Transmission rejected the torrent.",
        reason=said)


_ALREADY_ADDED = ("already_added",
                  "This torrent is already in Transmission, so it was not added again.")


async def _what_holds(info_hash: str):
    """What in this application already has this torrent, or None.

    Three answers, looked for in this order:

      ("on_its_way", row)   a transfer still fetching it, or filing it now;
      ("in_library", game)  a library file a seed was made from, or the game a
                            finished transfer of it became;
      None                  nothing - whatever the daemon holds is a leftover.

    A hash names the content, the same way the daemon does, which is exactly
    why a second account's add is answered with the first one's torrent. So a
    seed counts whether or not it is still seeding: its hash is the file's
    content, and that file is in the library either way. Only a published game
    counts - an unpublished GOG game is not on anybody's shelf.
    """
    from sqlalchemy import select

    from handler.database.session import async_session_factory
    from handler.torrent.torrent_ownership import not_landed
    from models.library_file import LibraryFile
    from models.library_game import LibraryGame
    from models.library_torrent import LibraryTorrent
    from models.torrent_download import TorrentDownload

    wanted = (info_hash or "").strip()
    if not wanted:
        return None
    async with async_session_factory() as db:
        running = (await db.execute(
            select(TorrentDownload)
            .where(TorrentDownload.info_hash == wanted, not_landed())
            .order_by(TorrentDownload.id).limit(1)
        )).scalars().first()
        if running is not None:
            return "on_its_way", running
        seeded = (await db.execute(
            select(LibraryGame)
            .join(LibraryFile, LibraryFile.library_game_id == LibraryGame.id)
            .join(LibraryTorrent, LibraryTorrent.file_id == LibraryFile.id)
            .where(LibraryTorrent.info_hash == wanted,
                   LibraryGame.is_active.is_(True))
            .limit(1)
        )).scalars().first()
        if seeded is not None:
            return "in_library", seeded
        # Joined to the game, so a finished transfer whose game has been
        # deleted since holds nothing - which is the case this exists for.
        # A transfer gets its game only when it lands, so no status is asked.
        landed = (await db.execute(
            select(LibraryGame)
            .join(TorrentDownload, TorrentDownload.game_id == LibraryGame.id)
            .where(TorrentDownload.info_hash == wanted,
                   LibraryGame.is_active.is_(True))
            .order_by(TorrentDownload.id.desc()).limit(1)
        )).scalars().first()
        if landed is not None:
            return "in_library", landed
    return None


def _inside_the_download_area(path: str | None) -> bool:
    """Whether a daemon's folder is one of ours for downloads.

    By path components, not by the start of the string: a folder called
    `torrents-old` begins with the same letters and is somewhere else.
    """
    if not path:
        return False
    area = os.path.realpath(_TORRENT_DIR)
    here = os.path.realpath(path)
    return here == area or here.startswith(area + os.sep)


async def _answer_a_duplicate(request, info: dict) -> bool:
    """Say what already holds a torrent the daemon answered an add with.

    Returns True when the daemon's copy was a leftover and has been taken off,
    so the caller can add the torrent again. Raises the refusal otherwise.

    WHY IT IS REFUSED AT ALL. The torrent the daemon holds is somebody else's
    transfer, or a library file being seeded. Writing a row for the caller on
    top of it handed them a transfer that was not theirs: weighed against their
    quota, a refusal removed it with its data; its buttons acted on it; and when
    it finished, whichever row got there first filed the download as its game.

    WHY IT SAYS WHERE. "Already in Transmission" was true and gave nobody
    anything to do; the owner asked whether a digit on the torrent would get
    past it. Content is what the daemon goes by, so the answer is to name the
    game it became, or the transfer fetching it.

    WHY A LEFTOVER IS TAKEN OFF. The daemon keeps a finished torrent after its
    files have been filed into the library. Once that game is deleted nothing
    here holds the torrent any more, and it blocked the game from ever being
    downloaded again. Only when its files sit in the download area, and never
    with its data: a whole game seeded for somebody's client has no row at all,
    lives in the library folder, and taking it off would cut them off.

    NAMED ONLY WHAT THE CALLER MAY SEE. A game in a library they cannot reach,
    or a transfer bound for one, answers with the plain refusal: its title would
    say what that library holds, and "the game appears when it finishes" would
    be a promise about a screen it will never reach.
    """
    if not info.get("duplicate"):
        return False
    user = getattr(request.state, "user", None)
    held = str(info.get("hashString") or "").strip()
    holder = await _what_holds(held)

    if holder is None:
        daemon_copy = await transmission_handler.get_torrent(held) if held else None
        if (daemon_copy
                and _inside_the_download_area(daemon_copy.get("downloadDir"))
                and await transmission_handler.remove_torrent(held, delete_data=False)):
            logger.info("Took a leftover torrent off the daemon so it can be added again")
            return True
        raise RefusalError(409, _refusal(*_ALREADY_ADDED))

    kind, thing = holder
    if kind == "on_its_way":
        try:
            await _assert_shelf_allowed(user, getattr(thing, "library", None))
        except HTTPException:
            raise RefusalError(409, _refusal(*_ALREADY_ADDED))
        if getattr(thing, "created_by_id", None) == getattr(user, "id", None):
            raise RefusalError(409, _refusal(
                "already_downloading",
                "You are already downloading this torrent; it is in your transfers.",
                mine=True))
        raise RefusalError(409, _refusal(
            "already_downloading",
            "Somebody is already downloading this torrent. The game will appear "
            "in the library when it finishes.",
            mine=False))

    try:
        await _assert_game_visible(user, thing.id)
    except HTTPException:
        raise RefusalError(409, _refusal(*_ALREADY_ADDED))
    raise RefusalError(409, _refusal(
        "already_in_library",
        f"This game is already in the library: {thing.title}.",
        game_id=thing.id, title=thing.title))


def _live_figures(t: dict) -> dict:
    """What the daemon knows about a transfer and the row does not.

    Reported by the owner: "nie widac ilosci peer/seed itd podczas pobierania
    torrent". A torrent is the one transfer in this application that can sit at
    the same percentage for an hour and be perfectly healthy, or be dead, and
    the only thing that tells those apart is how many peers it has found.

    NOTHING NEW IS ASKED OF THE DAEMON. `_TORRENT_FIELDS` requests every one of
    these on every call already, and `list_seeds` below and the "All torrents"
    tab have been rendering them for releases - `_fmt_download`, which feeds the
    two screens the owner actually watches, was the one place throwing them away.

    Empty when the daemon has nothing to say about this row, which is the normal
    state of every finished, refused and abandoned transfer in the list.
    """
    return {
        "peers":       t.get("peersConnected") or 0,
        # The peers actually sending to us. This is the one a person means by
        # "seeds" while a transfer is running, and the one that answers whether
        # a stuck percentage is a dead torrent or a slow one.
        "peers_from":  t.get("peersSendingToUs") or 0,
        "peers_to":    t.get("peersGettingFromUs") or 0,
        "rate_upload": t.get("rateUpload") or 0,
        "uploaded":    t.get("uploadedEver") or 0,
        "downloaded":  t.get("downloadedEver") or 0,
        # Transmission answers -1 for "no ratio yet" and -2 for "nothing was
        # downloaded, so it is infinite". Both are sentinels rather than
        # measurements, and printed as they are they read as a negative ratio.
        # Both become 0 here: these rows are downloads, so the second cannot
        # arise - a transfer that has received nothing has no ratio to show.
        "ratio":       max(0.0, round(float(t.get("uploadRatio") or 0), 2)),
        "stalled":     bool(t.get("isStalled")),
        "queue":       t.get("queuePosition") or 0,
        # Whether the daemon knows this transfer at all. Without it a finished
        # row is indistinguishable from a running one that has found nobody:
        # both answer zero to every question above, and only one of those zeros
        # is a measurement. `list_seeds` below carries the same flag.
        "live":        bool(t),
    }


async def _live_by_hash() -> dict[str, dict]:
    """Everything the daemon holds, keyed by the identity that outlives it.

    >>> BY HASH, NEVER BY `transmission_id`. That number is handed out per
    daemon session and reused after a restart, so the one remembered on a
    months-old row can belong to a completely different torrent today. Keyed on
    it, this account's transfer would be shown a stranger's peers and speed, and
    nothing about the screen would look wrong. `_is_the_torrent_we_queued` in the
    monitor guards the same door for the same reason.

    One call for the whole page: the alternative is a round trip per row against
    a daemon in this same container. A failure here costs the figures and must
    not cost the list - the tray is the only place an uploader sees their own
    transfers, and the reason a transfer was refused is on those rows.
    """
    try:
        torrents = await transmission_handler.get_all_torrents(label="")
    except Exception:
        logger.debug("Could not read live torrent figures", exc_info=True)
        return {}
    return {
        str(t.get("hashString") or "").lower(): t
        for t in torrents if t.get("hashString")
    }


def _live_for(td, live: dict[str, dict]) -> dict:
    """The daemon's entry for this row, matched the way that cannot go wrong."""
    return live.get(str(getattr(td, "info_hash", "") or "").strip().lower(), {})


def _fmt_download(td, live: dict | None = None) -> dict:
    return {
        **_live_figures(live or {}),
        "id":              td.id,
        "title":           td.title,
        "os":              td.os,
        "status":          td.status,
        "percent":         round(td.percent_done * 100, 1),
        "total_size":      td.total_size,
        "rate_download":   td.rate_download,
        "eta":             td.eta,
        "error_msg":       td.error_msg,
        # The reason as a name, so the screen can say it in the reader's
        # language, plus the one value that name is read with. `error_msg`
        # above stays: it is the fallback for a reader that does not know
        # the code, and the only thing carrying text written outside this
        # application.
        "error_code":      getattr(td, "error_code", None),
        "error_detail":    getattr(td, "error_detail", None),
        "game_id":         td.game_id,
        "library":         td.library,
        "created_by":      td.created_by,
        "created_at":      td.created_at.isoformat() if td.created_at else None,
        "completed_at":    td.completed_at.isoformat() if td.completed_at else None,
    }


# ── Transmission status ───────────────────────────────────────────────────────

@protected_route(torrent_router.get, "/enabled", scopes=[Scope.LIBRARY_READ])
async def torrent_enabled(request: Request) -> dict:
    """Return whether Transmission is enabled in settings (config flag, not live check)."""
    import json as _json
    # Primary: dedicated bool key (set on every settings save)
    enabled = await config_handler.get_bool("transmission_enabled", default=False)
    if not enabled:
        # Fallback: read from full settings JSON (covers configs saved before the key existed)
        raw = await config_handler.get("transmission_settings")
        if raw:
            try:
                enabled = bool(_json.loads(raw).get("enabled", False))
            except Exception:
                pass
    return {"enabled": enabled}


@protected_route(torrent_router.get, "/status", scopes=[Scope.LIBRARY_READ])
async def torrent_status(request: Request) -> dict:
    available = await transmission_handler.is_available()
    stats     = await transmission_handler.get_stats() if available else None
    return {"available": available, "engine": "transmission", "stats": stats}


# ── Admin: add download to server ─────────────────────────────────────────────

class AddTorrentByUrl(BaseModel):
    url:   str
    title: str
    os:    str = "windows"
    # Optional target library slug; NULL / "games" => built-in Games library.
    library: str | None = None


_FETCH_FAILED = ("url_fetch_failed",
                 "The torrent file could not be downloaded from that address.")

#: The longest a .torrent may take to arrive from an address, start to finish.
_FETCH_DEADLINE_SECONDS = 60


async def _fetch_torrent_file(url: str, *, transport=None) -> bytes:
    """The .torrent at an http(s) address, fetched here and not by the daemon.

    Transmission fetches an address itself, through libcurl, which follows
    redirects and resolves names on its own - so an address handed to it
    reached anything the container can: 127.0.0.1, 169.254.169.254, whatever a
    redirect pointed at. Uploaders may add torrents from 1.0.34, which made
    that reachable by a non-admin. Fetched here instead, through the guard the
    upload-by-address route uses on every hop - loopback, link-local, reserved
    and unspecified always refused, the home network allowed - and capped at
    the size a .torrent file can be.

    Failures are named, not quoted. What the other end answered - its status,
    its body - is exactly what would turn a refusal into a probe.
    """
    import asyncio

    import httpx

    from utils.net_guard import UnsafeURLError, make_request_guard

    try:
        # One deadline for the whole fetch. The httpx timeout is per phase and
        # its clock starts again with every chunk, so a server trickling a byte
        # at a time held the request - and the uploader's dialog - open for as
        # long as it liked.
        async with asyncio.timeout(_FETCH_DEADLINE_SECONDS):
            async with httpx.AsyncClient(
                follow_redirects=True,
                timeout=httpx.Timeout(20.0),
                event_hooks={"request": [make_request_guard(allow_private_lan=True)]},
                transport=transport,
            ) as client:
                async with client.stream("GET", url) as resp:
                    if resp.status_code != 200:
                        raise RefusalError(502, _refusal(*_FETCH_FAILED))
                    content = bytearray()
                    async for chunk in resp.aiter_bytes():
                        content.extend(chunk)
                        if len(content) > _MAX_TORRENT_BYTES:
                            raise RefusalError(
                                status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                                _refusal("url_too_large",
                                         "That address serves something far larger "
                                         "than a torrent file."))
                    return bytes(content)
    except HTTPException:
        raise
    except UnsafeURLError:
        raise RefusalError(400, _refusal(
            "url_blocked",
            "That address points inside the server's own network, so it "
            "cannot be used."))
    except Exception as exc:
        logger.info("Fetching a .torrent from an address failed: %s",
                    type(exc).__name__)
        raise RefusalError(502, _refusal(*_FETCH_FAILED))


async def _refuse_if_it_does_not_fit(request: Request, content: bytes) -> int | None:
    """Weigh a .torrent against the account's quota before anything downloads.

    A torrent counts against the quota once it lands, which on its own means a
    40 GB transfer onto a 10 GB allowance succeeds and then sits over the
    limit. A .torrent carries its own metadata, so the total can be read here
    and the refusal can come before anything is downloaded - whether the file
    was uploaded or fetched from an address. A magnet link is a hash and
    nothing else, so it is weighed later, when its size arrives.

    Weighed against what has landed AND what this account's other transfers are
    still bringing. Against the first alone, five 9 GB torrents onto a 10 GB
    allowance each fitted.

    Returns the size it read, so the row can be written with it at once. The
    monitor writes the size on its first tick, ten seconds on, and a second
    .torrent added inside those ten seconds would not have seen this one.

    An unreadable file is let through rather than refused. "No idea" is not
    "too big", and a limit that fired on a parse failure would start rejecting
    valid torrents the day a client writes a field the reader does not expect.
    """
    from handler.library import quota
    from handler.torrent.torrent_size import total_bytes

    user = getattr(request.state, "user", None)
    size = total_bytes(content)
    if size is not None and user is not None:
        limit = await quota.limit_for(user)
        used = await quota.committed_bytes(getattr(user, "id", None))
        if not quota.fits(used=used, incoming=size, limit=limit):
            room = max(0, limit - used)
            raise RefusalError(
                status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                _refusal(
                    "quota_refused",
                    f"This torrent is {human_bytes(size)} and only "
                    f"{human_bytes(room)} is left of this account's upload quota.",
                    size=size, room=room),
            )
    return size


@protected_route(torrent_router.post, "/download/url", scopes=[Scope.LIBRARY_UPLOAD])
async def add_torrent_url(request: Request, body: AddTorrentByUrl) -> dict:
    """Add a torrent by magnet link, or by the http(s) address of a .torrent.

    A magnet goes to the daemon as it is: it is a hash, with no address in it
    to fetch. An http(s) address is fetched HERE and only its bytes reach the
    daemon - see _fetch_torrent_file. Anything else is refused, because the
    daemon also reads a local path given to it as a file name.
    """
    await _assert_shelf_allowed(getattr(request.state, "user", None), body.library)
    url = (body.url or "").strip()
    scheme = url.split(":", 1)[0].lower() if ":" in url else ""
    if scheme not in ("magnet", "http", "https"):
        raise RefusalError(400, _refusal(
            "url_unsupported",
            "Only a magnet link or the http(s) address of a .torrent file can be "
            "added."))

    content = None
    size = None
    if scheme != "magnet":
        content = await _fetch_torrent_file(url)
        size = await _refuse_if_it_does_not_fit(request, content)

    slug = _slugify(body.title)
    download_dir = os.path.join(_TORRENT_DIR, slug)
    os.makedirs(download_dir, exist_ok=True)

    async def _add():
        if content is None:
            return await transmission_handler.add_torrent_url(url, download_dir)
        return await transmission_handler.add_torrent_metainfo(content, download_dir)

    info = await _add_to_the_daemon(request, _add)

    td = await _create_torrent_download(
        request, body.title, body.os, download_dir,
        transmission_id=info.get("id"),
        info_hash=info.get("hashString"),
        library=body.library,
        total_size=size,
    )
    return _fmt_download(td)


@protected_route(torrent_router.post, "/download/file", scopes=[Scope.LIBRARY_UPLOAD])
async def add_torrent_file(
    request: Request,
    title:   str = Form(...),
    target_os: str = Form("windows"),
    library: str = Form(None),
    file:    UploadFile = File(...),
) -> dict:
    """Upload a .torrent file and add it to Transmission."""
    await _assert_shelf_allowed(getattr(request.state, "user", None), library)
    os.makedirs(_SEED_DIR, exist_ok=True)
    safe_name = Path(file.filename or "upload.torrent").name  # strip path traversal
    tmp_path = os.path.join(_SEED_DIR, f"upload_{safe_name}")
    content = await read_upload_capped(file, _MAX_TORRENT_BYTES, what="Torrent file")
    size = await _refuse_if_it_does_not_fit(request, content)

    with open(tmp_path, "wb") as f:
        f.write(content)

    slug = _slugify(title)
    download_dir = os.path.join(_TORRENT_DIR, slug)
    os.makedirs(download_dir, exist_ok=True)

    async def _add():
        return await transmission_handler.add_torrent_file(tmp_path, download_dir)

    try:
        info = await _add_to_the_daemon(request, _add)
    finally:
        # After a second try, not after the first: clearing a leftover adds
        # the same file again.
        try:
            os.remove(tmp_path)
        except OSError:
            pass

    td = await _create_torrent_download(
        request, title, target_os, download_dir,
        transmission_id=info.get("id"),
        info_hash=info.get("hashString"),
        library=library,
        total_size=size,
    )
    return _fmt_download(td)


async def _add_to_the_daemon(request, add) -> dict:
    """Hand a torrent to the daemon through `add`, and answer what it says.

    A duplicate is explained by `_answer_a_duplicate`. When that turns out to be
    a leftover it has taken off, the add is made once more - once, because a
    torrent that is a duplicate again straight away was put back by something
    else, and going round would be arguing with it.
    """
    info, why = await add()
    if not info:
        raise RefusalError(502, _daemon_refusal(why))
    if await _answer_a_duplicate(request, info):
        info, why = await add()
        if not info:
            raise RefusalError(502, _daemon_refusal(why))
        if info.get("duplicate"):
            raise RefusalError(409, _refusal(*_ALREADY_ADDED))
    return info


async def _create_torrent_download(request, title, os_name, download_dir, *, transmission_id, info_hash, library=None, total_size=None):
    from handler.database.session import async_session_factory
    from models.torrent_download import TorrentDownload
    user = request.state.user
    username = user.username if user else "admin"
    target_lib = (library or "").strip() or None
    if target_lib == "games":
        target_lib = None  # built-in Games library is the default (CUSTOM)
    async with async_session_factory() as db:
        td = TorrentDownload(
            title=title,
            os=os_name,
            download_dir=download_dir,
            transmission_id=transmission_id,
            info_hash=info_hash,
            status="downloading",
            created_by=username,
            created_by_id=getattr(user, "id", None),
            # The same account, until it loses the right to upload and an
            # administrator takes the transfer over. Only the first one moves
            # then, so the game this becomes still names who brought it in.
            uploaded_by_id=getattr(user, "id", None),
            library=target_lib,
            # Known now for a .torrent, which the route has already weighed.
            # Zero for a magnet, which the monitor weighs when its size arrives:
            # the stored size is what tells it that has not happened yet.
            total_size=int(total_size or 0),
        )
        db.add(td)
        await db.commit()
        await db.refresh(td)
    return td


# ── Admin: list / manage downloads ───────────────────────────────────────────

def _mine_only(request) -> int | None:
    """The account whose transfers this caller may see, or None for all of them.

    Declared against the permission that ADDS a torrent rather than the
    administrative one, because the account that started a transfer is the one
    that needs to read what happened to it. A refusal for want of quota writes
    its reason into `error_msg`, and that column was readable only through an
    admin route - so the person who was refused had no way to learn why, or how
    much room to free. The live event does not cover it: the views subscribe
    inside the submit handler and lose the subscription with the component, and
    a torrent runs for hours.
    """
    scopes = set(getattr(request.state, "scopes", ()) or ())
    if Scope.LIBRARY_ADMIN in scopes:
        return None
    return getattr(getattr(request.state, "user", None), "id", None)


@protected_route(torrent_router.get, "/downloads", scopes=[Scope.LIBRARY_UPLOAD])
async def list_downloads(request: Request) -> list:
    from handler.database.session import async_session_factory
    from models.torrent_download import TorrentDownload
    from sqlalchemy import select
    async with async_session_factory() as db:
        rows = (await db.execute(
            select(TorrentDownload)
            # "removed" is the one status that means a person said they were
            # done with this transfer, and `cancel_download` below promises
            # exactly that in its first line: "drop a finished one from the
            # list". The row stays in the database, because the game it became
            # is in the library and this row is what ties the two together -
            # but the list stopped showing it. Without this, a transfer
            # somebody dismissed came back at the next fetch, for ever, which
            # went unnoticed while the only screen reading this was an
            # administrator's log-shaped one.
            #
            # Nothing else is hidden. Complete, error and paused are things
            # that happened rather than things somebody dismissed, and the
            # reason a transfer was refused lives on one of them.
            .where(TorrentDownload.status != DISMISSED_STATUS)
            .order_by(TorrentDownload.id.desc())
        )).scalars().all()
    owner = _mine_only(request)
    if owner is not None:
        rows = [r for r in rows if getattr(r, "created_by_id", None) == owner]
    # Nothing to merge figures onto, and this route is polled every thirty
    # seconds by every open page: on the live install every row is finished, so
    # the answer is the empty list and the round trip would buy nothing.
    if not rows:
        return []
    live = await _live_by_hash()
    return [_fmt_download(r, _live_for(r, live)) for r in rows]


@protected_route(torrent_router.get, "/downloads/{dl_id}", scopes=[Scope.LIBRARY_UPLOAD])
async def get_download(request: Request, dl_id: int) -> dict:
    from handler.database.session import async_session_factory
    from models.torrent_download import TorrentDownload
    async with async_session_factory() as db:
        td = await db.get(TorrentDownload, dl_id)
    if not td:
        raise HTTPException(404, "Download not found")
    owner = _mine_only(request)
    if owner is not None and getattr(td, "created_by_id", None) != owner:
        # 404 rather than 403, so the answer does not confirm that a transfer
        # with this id exists to somebody who may not see it.
        raise HTTPException(404, "Download not found")
    # The same shape the listing produces. No screen in this repo reads this
    # route - it is here for plugins and for anybody with curl - and a reply
    # that quietly loses nine fields depending on which route produced it is how
    # a reader ends up printing "0 peers" against a healthy transfer.
    return _fmt_download(td, _live_for(td, await _live_by_hash()))


@protected_route(torrent_router.delete, "/downloads/{dl_id}", scopes=[Scope.LIBRARY_UPLOAD])
async def cancel_download(request: Request, dl_id: int) -> dict:
    from handler.database.session import async_session_factory
    from models.torrent_download import TorrentDownload
    from sqlalchemy import update
    async with async_session_factory() as db:
        td = await db.get(TorrentDownload, dl_id)
        if not td:
            raise HTTPException(404, "Download not found")
        # Before anything is removed. Not through `_own_download`, because that
        # refuses a row with no transmission id and dropping exactly those from
        # the list is half of what this button does.
        _assert_mine(request, td)
        ref = _daemon_ref(td)
        from handler.torrent.seed_monitor import held_by_another

        # Not while another transfer or a seed holds the same torrent: a hash
        # names the content, and the cross on an old row took the new transfer
        # of the same game off the daemon. The row is dismissed either way.
        if ref and not await held_by_another(td):
            await transmission_handler.remove_torrent(ref, delete_data=False)
        await db.execute(
            update(TorrentDownload).where(TorrentDownload.id == dl_id)
            .values(status=DISMISSED_STATUS)
        )
        await db.commit()
    return {"ok": True}


# ── Controlling a download in flight ─────────────────────────────────────────
# Transmission has always been able to do these - the client wrapper had the
# calls - but nothing exposed them, so pausing a 60 GB torrent meant either
# cancelling it outright and starting again, or opening Transmission's own web
# interface on a port that is now deliberately shut.

async def _download_or_404(dl_id: int):
    from handler.database.session import async_session_factory
    from models.torrent_download import TorrentDownload
    async with async_session_factory() as db:
        td = await db.get(TorrentDownload, dl_id)
    if not td:
        raise HTTPException(404, "Download not found")
    if not td.transmission_id:
        raise HTTPException(409, "This download has not reached Transmission yet")
    return td


async def _own_download(request: Request, dl_id: int, *, changes_the_torrent: bool = True):
    """The transfer, if this caller may act on it.

    An uploader may queue a torrent, and from this release can see it in the
    transfer tray - but every button on it wanted LIBRARY_ADMIN, so the account
    that started a sixty gigabyte transfer could watch it and nothing else. That
    bit hardest where the quota stops one: only an administrator could let it go
    again, so the person who could actually free the space could not then act on
    the result.

    Two questions in the order the ROM download routes already ask them: the
    scope says who may reach the queue at all, and this says whose transfer it
    is. `_mine_only` is the same rule the listing uses, so the set of transfers
    somebody can act on is exactly the set they can see.

    404 rather than 403 for somebody else's, matching the single-row read above:
    the answer must not confirm that a transfer with this number exists.
    """
    td = await _download_or_404(dl_id)
    _assert_mine(request, td)
    if changes_the_torrent:
        from handler.torrent.seed_monitor import held_by_another

        # A hash names the content, not the row. While another transfer or a
        # seed holds the same torrent, pausing, resuming, verifying or choosing
        # files from this row would do it to theirs.
        if await held_by_another(td):
            raise HTTPException(
                409, "Another transfer or a seed is using this same torrent, so it "
                     "cannot be changed from this row.")
    return td


def _assert_mine(request: Request, td) -> None:
    """Whose transfer this is, asked on a row somebody else has already loaded.

    Split out because cancelling has to work on a row that never reached
    Transmission - dropping a finished or failed entry from the list is half of
    what that button is for - and `_download_or_404` refuses those with a 409.
    """
    owner = _mine_only(request)
    if owner is not None and getattr(td, "created_by_id", None) != owner:
        raise HTTPException(404, "Download not found")


def _daemon_ref(td):
    """How to name this transfer to the daemon: by its hash, when the row has one.

    `transmission_id` is handed out per daemon session and starts again from 1
    after every restart, and nothing rewrites it on the row - so after a deploy
    the number can belong to somebody else's torrent. Uploaders hold these
    buttons from 1.0.34, which turned a stale number into one account acting on
    another's transfer. The hash is the torrent's own name, and Transmission
    takes it wherever it takes an id (measured on the test server, 2026-09-13).
    Rows written before hashes were recorded have only the number.
    """
    return getattr(td, "info_hash", None) or getattr(td, "transmission_id", None)


async def _set_download_status(dl_id: int, status: str, **extra) -> None:
    from handler.database.session import async_session_factory
    from models.torrent_download import TorrentDownload
    from sqlalchemy import update
    async with async_session_factory() as db:
        await db.execute(
            update(TorrentDownload).where(TorrentDownload.id == dl_id)
            .values(status=status, **extra)
        )
        await db.commit()


@protected_route(torrent_router.post, "/downloads/{dl_id}/pause", scopes=[Scope.LIBRARY_UPLOAD])
async def pause_download(request: Request, dl_id: int) -> dict:
    """Stop fetching. What has arrived stays on disk and resume carries on."""
    td = await _own_download(request, dl_id)
    ok = await transmission_handler.pause_torrent(_daemon_ref(td))
    if not ok:
        raise HTTPException(502, "Transmission refused to pause this torrent")
    await _set_download_status(dl_id, "paused")
    return {"ok": True, "status": "paused"}


@protected_route(torrent_router.post, "/downloads/{dl_id}/resume", scopes=[Scope.LIBRARY_UPLOAD])
async def resume_download(request: Request, dl_id: int) -> dict:
    """Let a stopped transfer go again, if it may.

    THE LIMIT IS ASKED HERE, and this is the only place left that can ask. The
    monitor weighs a transfer exactly once, on the tick its size arrives, and
    the stored size is what records that it has been asked - so a transfer that
    is already past that moment is never weighed again by anything. Without
    this, pressing Resume was a one-click permanent exemption from the quota,
    which is how a 52.5 GB magnet came to be running on a 4 GB allowance.

    Refused rather than allowed when the limit cannot be read: allowing is the
    silent bypass this closes, and a refusal here is something to try again.
    """
    from handler.torrent.seed_monitor import _over_quota

    td = await _own_download(request, dl_id)

    size = int(getattr(td, "total_size", 0) or 0)
    over = await _over_quota(td, size)
    if over is None:
        raise HTTPException(
            503, "This account's upload quota could not be checked just now, so "
                 "the transfer was left stopped. Try again in a moment.")
    if over:
        raise HTTPException(
            status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            f"This transfer is {human_bytes(size)}, which is more than that "
            "account has left of its upload quota, so it stays stopped. Free "
            "some space, or claim the games it already owns, and try again.")

    ok = await transmission_handler.resume_torrent(_daemon_ref(td))
    if not ok:
        raise HTTPException(502, "Transmission refused to resume this torrent")
    # The reason it stopped goes with the stopping. Leaving it behind is how the
    # live row came to read "Refused: this torrent is larger than ..." while
    # downloading at full speed.
    await _set_download_status(dl_id, "downloading", error_msg=None,
                               error_code=None, error_detail=None)
    return {"ok": True, "status": "downloading"}


@protected_route(torrent_router.post, "/downloads/{dl_id}/verify", scopes=[Scope.LIBRARY_UPLOAD])
async def verify_download(request: Request, dl_id: int) -> dict:
    """Re-check what is on disk against the torrent, piece by piece.

    The answer to a transfer that stalled or came back looking wrong: it finds
    the bad pieces and fetches those again instead of the whole thing.
    Transmission stops the torrent while it reads, so a large one goes quiet
    for a while and then carries on.

    Only while the download is still in progress. Once it completes, its files
    are MOVED out of the download directory and into the library, so
    Transmission would find nothing there, decide every piece was missing, and
    start the entire torrent again. A finished game that will not install is a
    job for the library, not for this button.
    """
    td = await _own_download(request, dl_id)
    if td.status not in ("downloading", "paused"):
        raise HTTPException(
            409,
            "This download has already finished and its files have moved into "
            "the library, so there is nothing here left to check.",
        )
    ok = await transmission_handler.verify_torrent(_daemon_ref(td))
    if not ok:
        raise HTTPException(502, "Transmission refused to verify this torrent")
    return {"ok": True, "status": "verifying"}


class TorrentFilesBody(BaseModel):
    wanted:   list[int] = []
    unwanted: list[int] = []


@protected_route(torrent_router.get, "/downloads/{dl_id}/files", scopes=[Scope.LIBRARY_UPLOAD])
async def list_download_files(request: Request, dl_id: int) -> list:
    """What is inside the torrent, and which parts are being fetched."""
    td = await _own_download(request, dl_id, changes_the_torrent=False)
    return await transmission_handler.get_files(_daemon_ref(td))


@protected_route(torrent_router.put, "/downloads/{dl_id}/files", scopes=[Scope.LIBRARY_UPLOAD])
async def choose_download_files(request: Request, dl_id: int, body: TorrentFilesBody) -> dict:
    """Pick which files to fetch from a torrent that holds more than one game.

    Deselecting everything is refused rather than obeyed: Transmission would
    accept it and sit at zero per cent for ever, which looks exactly like a
    torrent with no seeds.
    """
    td = await _own_download(request, dl_id)
    files = await transmission_handler.get_files(_daemon_ref(td))
    if not files:
        raise HTTPException(409, "Transmission does not know this torrent's contents yet")

    valid = {f["index"] for f in files}
    wanted   = [i for i in body.wanted if i in valid]
    unwanted = [i for i in body.unwanted if i in valid]
    if len(unwanted) >= len(valid) and not wanted:
        raise HTTPException(400, "At least one file has to be selected")

    ok = await transmission_handler.set_files_wanted(_daemon_ref(td), wanted, unwanted)
    if not ok:
        raise HTTPException(502, "Transmission refused the file selection")
    return {"ok": True, "files": await transmission_handler.get_files(_daemon_ref(td))}


# ── Everything the daemon holds ──────────────────────────────────────────────
# The two views above only know what this application put there. Transmission
# also holds the seeds, and anything added by hand before the control port was
# shut. Without this the daemon's own interface is still the only way to see it.

@protected_route(torrent_router.get, "/all", scopes=[Scope.LIBRARY_ADMIN])
async def list_all_torrents(request: Request) -> list:
    """Every torrent Transmission is holding, ours or not."""
    from handler.torrent.transmission_handler import STATUS
    torrents = await transmission_handler.get_all_torrents(label="")
    out = []
    for t in torrents:
        total = t.get("totalSize") or 0
        out.append({
            "id":          t.get("id"),
            "name":        t.get("name") or "",
            "status":      STATUS.get(t.get("status", 0), "unknown"),
            "percent":     round(float(t.get("percentDone") or 0) * 1000) / 10,
            "total_size":  total,
            "downloaded":  t.get("downloadedEver") or 0,
            "uploaded":    t.get("uploadedEver") or 0,
            "ratio":       round(float(t.get("uploadRatio") or 0), 2),
            "rate_down":   t.get("rateDownload") or 0,
            "rate_up":     t.get("rateUpload") or 0,
            "peers":       t.get("peersConnected") or 0,
            "peers_from":  t.get("peersSendingToUs") or 0,
            "peers_to":    t.get("peersGettingFromUs") or 0,
            "eta":         t.get("eta", -1),
            "queue":       t.get("queuePosition", 0),
            "stalled":     bool(t.get("isStalled")),
            "error":       t.get("errorString") or "",
            # Ours carry the application's label; anything else was added by
            # hand and is worth saying so, because removing it is not something
            # this application can undo.
            "ours":        bool(t.get("labels")),
            "added_at":    t.get("addedDate") or 0,
            "download_dir": t.get("downloadDir") or "",
        })
    out.sort(key=lambda r: (r["queue"], r["name"].lower()))
    return out


@protected_route(torrent_router.get, "/stats", scopes=[Scope.LIBRARY_ADMIN])
async def torrent_stats(request: Request) -> dict:
    """Session and lifetime totals, straight from the daemon."""
    raw = await transmission_handler.get_stats()
    if not raw:
        raise HTTPException(502, "Transmission did not answer")

    def _blok(d: dict) -> dict:
        return {
            "downloaded": d.get("downloadedBytes", 0),
            "uploaded":   d.get("uploadedBytes", 0),
            "files_added": d.get("filesAdded", 0),
            "seconds":    d.get("secondsActive", 0),
            "sessions":   d.get("sessionCount", 0),
        }

    return {
        "torrents":        raw.get("torrentCount", 0),
        "active":          raw.get("activeTorrentCount", 0),
        "paused":          raw.get("pausedTorrentCount", 0),
        "rate_down":       raw.get("downloadSpeed", 0),
        "rate_up":         raw.get("uploadSpeed", 0),
        "current":         _blok(raw.get("current-stats") or {}),
        "cumulative":      _blok(raw.get("cumulative-stats") or {}),
    }


class TorrentActionBody(BaseModel):
    # Per-torrent overrides, all optional. Transmission's own names and units.
    download_limit:    int | None = None      # KB/s, needs the flag below
    download_limited:  bool | None = None
    upload_limit:      int | None = None
    upload_limited:    bool | None = None
    seed_ratio_limit:  float | None = None
    seed_ratio_mode:   int | None = None      # 0 global, 1 own, 2 unlimited
    peer_limit:        int | None = None


@protected_route(torrent_router.post, "/all/{tid}/{action}", scopes=[Scope.LIBRARY_ADMIN])
async def act_on_torrent(request: Request, tid: int, action: str) -> dict:
    """pause | resume | verify | top | up | down | bottom

    By Transmission's own id rather than by a row of ours, because the point of
    this view is the torrents we have no row for.
    """
    if action in ("pause", "resume", "verify"):
        fn = {
            "pause":  transmission_handler.pause_torrent,
            "resume": transmission_handler.resume_torrent,
            "verify": transmission_handler.verify_torrent,
        }[action]
        if not await fn(tid):
            raise HTTPException(502, f"Transmission refused to {action} this torrent")
        return {"ok": True}

    if action in ("top", "up", "down", "bottom"):
        if not await transmission_handler.move_in_queue(tid, action):
            raise HTTPException(502, "Transmission refused to reorder this torrent")
        return {"ok": True}

    raise HTTPException(400, f"Unknown action: {action}")


@protected_route(torrent_router.put, "/all/{tid}/limits", scopes=[Scope.LIBRARY_ADMIN])
async def set_torrent_limits(request: Request, tid: int, body: TorrentActionBody) -> dict:
    """Caps for one torrent, overriding the session-wide ones."""
    mapa = {
        "download_limit":   "downloadLimit",
        "download_limited": "downloadLimited",
        "upload_limit":     "uploadLimit",
        "upload_limited":   "uploadLimited",
        "seed_ratio_limit": "seedRatioLimit",
        "seed_ratio_mode":  "seedRatioMode",
        "peer_limit":       "peer-limit",
    }
    values = {mapa[k]: v for k, v in body.model_dump().items() if v is not None}
    if not values:
        raise HTTPException(400, "Nothing to set")
    if not await transmission_handler.set_torrent_limits(tid, values):
        raise HTTPException(502, "Transmission refused those limits")
    return {"ok": True}


@protected_route(torrent_router.delete, "/all/{tid}", scopes=[Scope.LIBRARY_ADMIN])
async def remove_torrent(request: Request, tid: int, delete_data: bool = False) -> dict:
    """Drop a torrent from Transmission.

    `delete_data` also removes what it downloaded, which for a seed means the
    library file it was sharing. Off unless asked for, and the interface asks
    twice.
    """
    if not await transmission_handler.remove_torrent(tid, delete_data=delete_data):
        raise HTTPException(502, "Transmission refused to remove this torrent")
    return {"ok": True, "deleted_data": delete_data}


@protected_route(torrent_router.get, "/seeds", scopes=[Scope.LIBRARY_ADMIN])
async def list_seeds(request: Request) -> list:
    """What this server is sharing, with live figures from the daemon."""
    from handler.database.session import async_session_factory
    from models.library_torrent import LibraryTorrent
    from models.library_file import LibraryFile
    from sqlalchemy import select

    async with async_session_factory() as db:
        rows = (await db.execute(
            select(LibraryTorrent).order_by(LibraryTorrent.id.desc())
        )).scalars().all()
        nazwy: dict[int, str] = {}
        ids = [r.file_id for r in rows if r.file_id]
        if ids:
            for f in (await db.execute(
                select(LibraryFile).where(LibraryFile.id.in_(ids))
            )).scalars().all():
                nazwy[f.id] = f.display_name or f.filename

    live = {t.get("id"): t for t in await transmission_handler.get_all_torrents(label="")}
    out = []
    for r in rows:
        t = live.get(r.transmission_id) or {}
        out.append({
            "id":              r.id,
            "transmission_id": r.transmission_id,
            "filename":        nazwy.get(r.file_id, "") or (r.torrent_path or "").split("/")[-1],
            "status":          r.status,
            "file_size":       r.file_size or 0,
            "created_by":      r.created_by,
            "uploaded":        t.get("uploadedEver") or 0,
            "ratio":           round(float(t.get("uploadRatio") or 0), 2),
            "rate_up":         t.get("rateUpload") or 0,
            "peers_to":        t.get("peersGettingFromUs") or 0,
            # A row whose torrent is gone from the daemon can still say seeding.
            "live":            r.transmission_id in live,
        })
    return out


# ── User: generate seed .torrent for an entire game (all files) ───────────────

class SeedGameBody(BaseModel):
    file_ids: list[int] = []   # empty = all available files


@protected_route(torrent_router.post, "/seed/game/{game_id}", scopes=[Scope.LIBRARY_DOWNLOAD])
async def generate_game_torrent(request: Request, game_id: int, body: SeedGameBody):
    """Generate a single .torrent for selected files (or all if none specified).

    Files are staged in a temp directory so multi-directory selections work
    regardless of where each file lives on disk.
    """
    import shutil
    import tempfile
    from handler.database.session import async_session_factory
    from handler.torrent.torrent_generator import create_torrent
    from models.library_file import LibraryFile
    from models.library_game import LibraryGame
    from sqlalchemy import select

    # Before anything is read off the disk or handed to Transmission.
    await _assert_game_visible(getattr(request.state, "user", None), game_id)

    async with async_session_factory() as db:
        game = await db.get(LibraryGame, game_id)
        if not game:
            raise HTTPException(404, "Game not found")
        rows = (await db.execute(
            select(LibraryFile).where(
                LibraryFile.library_game_id == game_id,
                LibraryFile.is_available == True,  # noqa: E712
            )
        )).scalars().all()

    # Filter to requested selection (empty body = all)
    files = [f for f in rows if f.id in body.file_ids] if body.file_ids else list(rows)
    if not files:
        raise HTTPException(404, "No matching files for this game")

    abs_paths = [p for p in (os.path.join(BASE_PATH, f.file_path) for f in files) if os.path.exists(p)]
    if not abs_paths:
        raise HTTPException(404, "No files found on disk")

    game_slug = _slugify(game.title)
    os.makedirs(_SEED_DIR, exist_ok=True)

    if len(abs_paths) == 1:
        # Single file - no staging needed
        try:
            torrent_path = await create_torrent(abs_paths[0], _SEED_DIR)
        except RuntimeError as exc:
            logger.error("Torrent creation failed for game %d: %s", game_id, exc)
            raise HTTPException(500, f"Torrent creation failed: {exc}")
        seed_dir = os.path.dirname(abs_paths[0])
    else:
        # Multiple files - stage with symlinks in a temp tree that MIRRORS the
        # on-disk layout, so the generated torrent preserves subdirectories
        # (e.g. gra/DATA/file03.bin) instead of flattening every file into one
        # folder. Using os.path.basename() used to drop the subdirectory and
        # collapse the whole game into a flat root.
        #
        # The staging root is named after the files' common ancestor directory
        # so the torrent's top-level folder matches the data on disk; that also
        # lets Transmission seed the existing files without re-hashing, because
        # it can find <seed_dir>/<root_name>/... exactly where the torrent says.
        common = os.path.commonpath(abs_paths)
        if not os.path.isdir(common):
            common = os.path.dirname(common)
        root_name = os.path.basename(common) or game_slug
        staging_parent = tempfile.mkdtemp(prefix="seed_", dir=_SEED_DIR)
        root_dir = os.path.join(staging_parent, root_name)
        os.makedirs(root_dir, exist_ok=True)
        try:
            for ap in abs_paths:
                rel = os.path.relpath(ap, common)
                link = os.path.join(root_dir, rel)
                if os.path.lexists(link):
                    continue  # identical path listed twice - skip duplicate
                os.makedirs(os.path.dirname(link), exist_ok=True)
                os.symlink(ap, link)
            try:
                torrent_path = await create_torrent(root_dir, _SEED_DIR)
            except RuntimeError as exc:
                logger.error("Torrent creation failed for game %d: %s", game_id, exc)
                raise HTTPException(500, f"Torrent creation failed: {exc}")
        finally:
            shutil.rmtree(staging_parent, ignore_errors=True)
        # Transmission must find <seed_dir>/<root_name>/... on disk to seed the
        # already-present data, so point it at the common ancestor's parent.
        seed_dir = os.path.dirname(common)

    await transmission_handler.add_torrent_file(torrent_path, seed_dir)  # (info, powod)

    return FileResponse(
        torrent_path,
        media_type="application/x-bittorrent",
        filename=f"{game_slug}.torrent",
    )


# ── User: generate seed .torrent for a library file ──────────────────────────

@protected_route(torrent_router.post, "/seed/{file_id}", scopes=[Scope.LIBRARY_DOWNLOAD])
async def generate_seed_torrent(request: Request, file_id: int):
    """Generate (or return existing active) .torrent for a library file.

    Returns the .torrent file as a download.
    """
    from handler.database.session import async_session_factory
    from handler.torrent.torrent_generator import create_torrent
    from models.library_file import LibraryFile
    from models.library_game import LibraryGame
    from models.library_torrent import LibraryTorrent
    from sqlalchemy import select

    # Load file record + game title for a friendly download filename
    async with async_session_factory() as db:
        lf = await db.get(LibraryFile, file_id)
        if not lf or not lf.is_available:
            raise HTTPException(404, "File not found")

    # The file names its game, and the game is what visibility is about. Asked
    # before the .torrent is built and before Transmission is told to serve it.
    await _assert_game_visible(getattr(request.state, "user", None), lf.library_game_id)

    async with async_session_factory() as db:
        game = await db.get(LibraryGame, lf.library_game_id)
        game_slug = _slugify(game.title) if game else f"game-{file_id}"

        # Check for existing active seed
        existing = (await db.execute(
            select(LibraryTorrent)
            .where(LibraryTorrent.file_id == file_id, LibraryTorrent.status == "seeding")
            .order_by(LibraryTorrent.id.desc())
        )).scalar_one_or_none()

        if existing and existing.torrent_path and os.path.exists(existing.torrent_path):
            return FileResponse(
                existing.torrent_path,
                media_type="application/x-bittorrent",
                filename=f"{game_slug}.torrent",
            )

    # Generate new .torrent
    abs_path = os.path.join(BASE_PATH, lf.file_path)
    if not os.path.exists(abs_path):
        raise HTTPException(404, "Physical file not found on disk")

    os.makedirs(_SEED_DIR, exist_ok=True)

    try:
        torrent_path = await create_torrent(abs_path, _SEED_DIR)
    except RuntimeError as exc:
        logger.error("Failed to create torrent for file %d: %s", file_id, exc)
        raise HTTPException(500, f"Torrent creation failed: {exc}")

    # Add to Transmission for seeding (file already downloaded, just seed)
    file_dir = os.path.dirname(abs_path)
    info, _why = await transmission_handler.add_torrent_file(torrent_path, file_dir)

    tr_id     = info.get("id")   if info else None
    info_hash = info.get("hashString") if info else None
    file_size = lf.size_bytes or (os.path.getsize(abs_path) if os.path.exists(abs_path) else None)
    username  = request.state.user.username if request.state.user else "unknown"

    async with async_session_factory() as db:
        lt = LibraryTorrent(
            file_id=file_id,
            transmission_id=tr_id,
            info_hash=info_hash,
            torrent_path=torrent_path,
            status="seeding",
            file_size=file_size,
            created_by=username,
        )
        db.add(lt)
        await db.commit()

    return FileResponse(
        torrent_path,
        media_type="application/x-bittorrent",
        filename=f"{game_slug}.torrent",
    )


@protected_route(torrent_router.get, "/seed/{file_id}/status", scopes=[Scope.LIBRARY_DOWNLOAD])
async def seed_status(request: Request, file_id: int) -> dict:
    """Return current seed status for a file.

    Gated the same way as the two routes that create a seed. It answers whether
    a file is being served, how large it is and how much has gone out - facts
    about a file, readable by any account that could guess an id.
    """
    from handler.database.session import async_session_factory
    from models.library_file import LibraryFile
    from models.library_torrent import LibraryTorrent
    from sqlalchemy import select

    async with async_session_factory() as db:
        lf = await db.get(LibraryFile, file_id)
    if not lf:
        raise HTTPException(404, "File not found")
    await _assert_game_visible(getattr(request.state, "user", None), lf.library_game_id)

    async with async_session_factory() as db:
        lt = (await db.execute(
            select(LibraryTorrent)
            .where(LibraryTorrent.file_id == file_id)
            .order_by(LibraryTorrent.id.desc())
        )).scalar_one_or_none()

    if not lt:
        return {"status": "none"}

    result: dict = {
        "status":     lt.status,
        "created_at": lt.created_at.isoformat() if lt.created_at else None,
    }

    if lt.status == "seeding" and lt.transmission_id:
        info = await transmission_handler.get_torrent(lt.transmission_id)
        if info:
            result["uploaded"]    = info.get("uploadedEver", 0)
            result["file_size"]   = lt.file_size
            result["upload_ratio"] = round(
                info.get("uploadedEver", 0) / max(lt.file_size or 1, 1), 4
            )

    return result
