"""Background tasks for torrent lifecycle management.

seed_monitor_loop():
  Runs every 60 s. For each "seeding" LibraryTorrent:
    - Asks Transmission for current stats.
    - If uploadedEver >= file_size → the file has been fully delivered to at
      least one peer → mark torrent as expired and remove it from Transmission.
    - If Transmission no longer knows about the torrent → mark as error.

download_monitor_loop():
  Runs every 10 s. For each "downloading" TorrentDownload:
    - Updates percent_done / rate / eta / total_size in DB.
    - If percentDone == 1.0 → auto-register as LibraryGame+LibraryFile, mark complete.
    - If error → mark as error.
    - Emits Socket.IO events for real-time UI updates.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


async def seed_monitor_loop() -> None:
    """Check seeding torrents every 60 s and expire when fully uploaded."""
    await asyncio.sleep(30)   # give Transmission time to settle on startup
    while True:
        try:
            await _check_seeds()
        except Exception as exc:
            logger.warning("seed_monitor error: %s", exc)
        await asyncio.sleep(60)


async def download_monitor_loop() -> None:
    """Poll in-progress admin torrent downloads every 10 s."""
    await asyncio.sleep(15)
    while True:
        try:
            await _check_downloads()
        except Exception as exc:
            logger.warning("download_monitor error: %s", exc)
        await asyncio.sleep(10)


# ── Seed monitor ──────────────────────────────────────────────────────────────

async def _check_seeds() -> None:
    from handler.database.session import async_session_factory
    from handler.torrent.transmission_handler import transmission_handler
    from models.library_torrent import LibraryTorrent
    from sqlalchemy import select

    async with async_session_factory() as db:
        rows = (await db.execute(
            select(LibraryTorrent).where(LibraryTorrent.status == "seeding")
        )).scalars().all()

    for lt in rows:
        # By the hash when the row has one. The number is renumbered by every
        # daemon restart, and after a deploy it named whatever torrent held it
        # next - an uploader's download, taken off the daemon here once its
        # upload passed this seed's size. Rows from before hashes were recorded
        # have only the number.
        ref = getattr(lt, "info_hash", None) or lt.transmission_id
        if ref is None:
            continue
        info = await transmission_handler.get_torrent(ref)
        if info is None:
            # "Not holding it" and "did not answer" arrive identically, and only
            # the first is a lost seed. Nothing brings a failed seed back.
            if not await transmission_handler.is_available():
                continue
            await _update_seed_status(lt.id, "error")
            logger.info("Seed torrent %d lost from Transmission - marked error", lt.id)
            continue
        if getattr(lt, "info_hash", None) and not _is_the_torrent_we_queued(lt, info):
            logger.warning(
                "Seed torrent %d now points at a different torrent in the daemon; "
                "not following it", lt.id)
            continue

        uploaded = info.get("uploadedEver", 0)
        file_size = lt.file_size or 1

        if uploaded >= file_size:
            # Full upload detected - expire the seed. The torrent stays in the
            # daemon while a live transfer is fetching the same one: the seed
            # row is done, the torrent is theirs to finish.
            if not (getattr(lt, "info_hash", None)
                    and await _live_transfer_holds(lt.info_hash)):
                await transmission_handler.remove_torrent(ref, delete_data=False)
            await _update_seed_status(lt.id, "expired")
            if lt.torrent_path and os.path.exists(lt.torrent_path):
                try:
                    os.remove(lt.torrent_path)
                except OSError:
                    pass
            logger.info(
                "Seed torrent %d expired (uploaded %d / %d bytes)",
                lt.id, uploaded, file_size,
            )


async def _update_seed_status(torrent_id: int, status: str) -> None:
    from handler.database.session import async_session_factory
    from models.library_torrent import LibraryTorrent
    from sqlalchemy import update

    async with async_session_factory() as db:
        await db.execute(
            update(LibraryTorrent)
            .where(LibraryTorrent.id == torrent_id)
            .values(status=status)
        )
        await db.commit()


# ── Download monitor ──────────────────────────────────────────────────────────



async def _emit_to_owner(td, event: str, payload: dict) -> None:
    """Tell the account that queued this, and administrators. Nobody else.

    The first version broadcast, which puts a game title and a job id in front
    of every logged-in account. Same audience rule as the ROM download path,
    borrowed rather than restated.
    """
    from handler.roms.rom_source_handler import _download_audience
    from handler.socket_handler import sio
    from types import SimpleNamespace

    for room in _download_audience(
            SimpleNamespace(actor_id=getattr(td, "created_by_id", None)))["rooms"]:
        try:
            await sio.emit(event, payload, room=room)
        except Exception:   # noqa: BLE001 - a notice, never the transfer
            logger.debug("Could not emit %s", event, exc_info=True)


def _size_just_arrived(td, total_size: int) -> bool:
    """Whether this is the first tick that knows how big this transfer is.

    The weighing below is three queries, and when a limit is in force two of
    them are aggregate sums - one over `roms`, whose `published_by` column
    arrived by an ALTER with no index behind it. The monitor wakes every ten
    seconds for every transfer, and asked the same question each time about a
    number that does not change: `totalSize` is fixed once the metadata is in.

    The stored column is what says whether it has been asked. It is written on
    every tick, so "was nothing, is something now" is exactly the first tick
    that could weigh anything.

    Asking once is also the more careful reading, not only the cheaper one. The
    allowance moves while a transfer runs, so asking again and again lets an
    ordinary upload by the same account condemn a download that was legal when
    it started - halfway through, with hours already spent.
    """
    return total_size > 0 and not int(getattr(td, "total_size", 0) or 0)


async def _over_quota(td, total_size: int) -> bool | None:
    """Whether this transfer would take the account past its upload allowance.

    Three answers, not two. True is over, False is a decided "it fits", and
    None is "could not tell" - which is NOT the same as "it fits", though this
    function used to say so.

    That conflation was the whole of a hole. The caller weighs a transfer
    exactly once, on the tick its size arrives, and the stored size is what
    records that it has been asked. So a lookup that failed used to answer
    "fits", the same tick wrote the size, and the limit was gone for that
    transfer for good - reported nowhere above DEBUG. A failed measurement now
    leaves the question open and the next tick asks again.

    Charged to `created_by_id`, which is the same account the finished game is
    published under further down, so the answer here and the bytes counted
    later are about the same person. No account recorded, the account deleted
    since, or no limit in force are all decided answers of False: nothing is
    being guessed at in those cases.

    Weighed against what has landed and what the account's OTHER transfers are
    still bringing - never this one, whose size may already be stored when the
    resume button asks, and which would otherwise be counted twice.
    """
    owner_id = getattr(td, "created_by_id", None)
    if not owner_id:
        return False
    try:
        from handler.database.users_handler import UsersHandler
        from handler.library import quota

        user = await UsersHandler().get_by_id(owner_id)
        if user is None:
            return False
        limit = await quota.limit_for(user)
        if not limit or limit <= 0:
            return False
        used = await quota.committed_bytes(owner_id, except_torrent_id=getattr(td, "id", None))
        return not quota.fits(used=used, incoming=total_size, limit=limit)
    except Exception:  # noqa: BLE001 - a failed reading is not a verdict
        logger.warning(
            "Could not weigh torrent %s against a quota; will ask again",
            getattr(td, "id", "?"), exc_info=True)
        return None


def _is_the_torrent_we_queued(td, info: dict) -> bool:
    """Whether the daemon's torrent is really the one this row was written for.

    `transmission_id` is handed out by the daemon and starts again from 1 every
    time it restarts, so the same number points at different torrents over a
    machine's life - two rows on the live install already share id 1. It is
    fine for asking after progress and hopeless as the identity behind
    anything destructive.

    `info_hash` is the content's own name and both queue routes have always
    written it. Nothing had ever read it back. This is the one place that has
    to be certain, so this is where it starts being read.
    """
    ours = str(getattr(td, "info_hash", "") or "").strip().lower()
    theirs = str(info.get("hashString") or "").strip().lower()
    return bool(ours) and ours == theirs


#: A row whose torrent is still being fetched, stopped or not.
LIVE_STATUSES = ("downloading", "paused")


async def held_by_another(td) -> bool:
    """Whether another live transfer, or a seed, holds the torrent this row names.

    A hash names the CONTENT, not the row, and two rows can carry the same one:
    a refused magnet stays listed with its reason while the same magnet, added
    again, runs under a new row; an old finished row sits beside a new transfer
    of the same game; a library file being seeded is the same torrent as a
    download of it. Reaching the daemon by hash from the wrong one of those
    stops, removes or deletes the other's transfer - so nothing touches the
    daemon from a row while this says yes.

    A row without a hash has nothing to compare and is not looked up.
    """
    ours = str(getattr(td, "info_hash", "") or "").strip()
    if not ours:
        return False
    return (await _live_transfer_holds(ours, except_id=getattr(td, "id", None))
            or await _seed_holds(ours))


async def _live_transfer_holds(info_hash: str, *, except_id: int | None = None) -> bool:
    """Whether a download row that is still fetching this torrent, stopped or
    not, exists - other than the one named by `except_id`."""
    from handler.database.session import async_session_factory
    from models.torrent_download import TorrentDownload
    from sqlalchemy import select

    query = select(TorrentDownload.id).where(
        TorrentDownload.info_hash == info_hash,
        TorrentDownload.status.in_(LIVE_STATUSES),
    )
    if except_id is not None:
        query = query.where(TorrentDownload.id != except_id)
    async with async_session_factory() as db:
        return (await db.execute(query.limit(1))).first() is not None


async def _seed_holds(info_hash: str) -> bool:
    """Whether a library file is seeding this torrent."""
    from handler.database.session import async_session_factory
    from models.library_torrent import LibraryTorrent
    from sqlalchemy import select

    query = select(LibraryTorrent.id).where(
        LibraryTorrent.info_hash == info_hash,
        LibraryTorrent.status == "seeding",
    )
    async with async_session_factory() as db:
        return (await db.execute(query.limit(1))).first() is not None


#: Every reason a transfer can stop, as a name rather than a sentence.
#:
#: The sentence is composed here as well and kept on the row, but only as the
#: fallback: the screen writes its own in the reader's language from the name
#: and the numbers. That is the shape the refused-upload message already uses
#: (`library.reject_*`), and it is what lets this be done a piece at a time -
#: a reason nobody has written a sentence for yet still shows the English one
#: rather than nothing.
#:
#: Spelled once, here, because a code written as a bare string at each site is
#: how the writer and the reader come to disagree about one of them.
REASONS = {
    "quota_refused": "over the account's upload quota; taken off the daemon",
    "quota_stopped": "over the quota, but the daemon's torrent could not be "
                     "confirmed as ours, so it was only stopped",
    "lost":          "the daemon answered and does not know this torrent",
    "daemon":        "the daemon's own error text, which is not ours to write",
    "no_game":       "finished, and no game came of it, with no reason recorded",
    "no_folder":     "the download folder was gone when it finished",
    "no_files":      "the folder held nothing that could be filed",
    "threat":        "the virus scanner stopped one of its files",
    "move_failed":   "the files could not be moved into the library",
}


def reason(name: str) -> str:
    """The code for `name`, checked against the list above as it is used.

    The dictionary maps a code to what it MEANS, so reading `REASONS[name]`
    hands back the explanation rather than the code - which is how the
    explanation came to be written into a database column, caught by the test
    that asked what actually landed there. Going through here also means a
    misspelled reason fails at the call rather than reaching a screen that
    cannot match it.
    """
    if name not in REASONS:
        raise KeyError(f"unknown transfer reason: {name!r}")
    return name


#: What a transfer turned away for want of quota is left as.
#:
#: NOT "removed", which is what the cancel route writes and what the listing
#: hides. Those two meanings shared a word for a few hours and it cost exactly
#: what it sounds like: the row whose entire purpose is to explain itself was
#: the one row nobody could see. A person pressing the cross means "I am done
#: with this"; the monitor means "this was turned away, here is why", and only
#: the first is a dismissal.
#:
#: "error" also carries its weight in the tray, which already draws that state
#: in red and prints `error_msg` beside it, and it is not "downloading", so the
#: monitor stops polling a transfer that is no longer there.
REFUSED_STATUS = "error"


def _refusal_message(size: int, room: int, *, removed: bool = True) -> str:
    """What the row says about a transfer that did not fit.

    Both figures, in units people read. "larger than what is left" was true and
    useless: it never said larger by how much, so the account could not tell
    whether to free one game or twenty. The owner asked for this after reading
    the first version off his own screen.
    """
    from utils.sizes import human_bytes

    head = "Refused" if removed else "Stopped"
    tail = ("" if removed else
            " It was left on the disk because the daemon could not confirm it "
            "is the same torrent this download started.")
    return (f"{head}: this torrent is {human_bytes(size)} and only "
            f"{human_bytes(room)} is left of this account's upload quota.{tail}")


async def _room_left(td) -> int:
    """How much of the allowance is unspent, for the message only.

    Answers zero when it cannot tell. This runs after the transfer has already
    been refused, so a failure here costs a number in a sentence rather than a
    decision.
    """
    try:
        from handler.database.users_handler import UsersHandler
        from handler.library import quota

        user = await UsersHandler().get_by_id(getattr(td, "created_by_id", None))
        if user is None:
            return 0
        limit = await quota.limit_for(user)
        if not limit or limit <= 0:
            return 0
        # The same total `_over_quota` refused against, or the message would
        # quote more room than the decision it explains had.
        used = await quota.committed_bytes(
            td.created_by_id, except_torrent_id=getattr(td, "id", None))
        return max(0, limit - used)
    except Exception:  # noqa: BLE001 - a figure in a message, never a verdict
        logger.debug("Could not work out the room left for the refusal message",
                     exc_info=True)
        return 0


async def _refuse_over_quota(td, info: dict, total_size: int) -> None:
    """Turn away a transfer that does not fit, at the first moment anyone knows.

    THE OWNER CHOSE THIS SHAPE, against the previous one: "myslalem ze jak jest
    za duzy to poprostu go nie przyjmie". A .torrent is already refused up
    front, because the file carries its size. A magnet is a hash and the totals
    arrive from peers minutes later, so this tick is the earliest refusal
    available - and it is a refusal, not a cancellation of work in progress.

    An earlier version deleted over-quota transfers and was reverted. All three
    of its faults are answered here rather than repeated:

      * "an ordinary upload could condemn a transfer that was legal when it
        started" - the weighing happens once, on the tick the size arrives.
        Nothing already admitted is ever reconsidered.
      * "`transmission_id` can point at a DIFFERENT torrent after a restart" -
        the real danger, and the reason nothing is deleted unless `info_hash`
        says the daemon is holding ours. When it cannot be confirmed, the
        transfer is stopped and left alone, and the row says why.
      * "hours of transfer thrown away" - by construction this is the first
        tick that could tell, so the disk holds at most one poll interval of a
        transfer this account was never allowed to have.

    A daemon that did not accept the instruction leaves the row untouched, and
    that is deliberate: the row leaving "downloading" is what takes it out of
    the only set this monitor ever looks at, so writing it on the strength of
    an unread answer would mean the database saying stopped while the bytes
    kept coming, with nothing left to notice.
    """
    from handler.torrent.transmission_handler import transmission_handler

    room = await _room_left(td)
    mine = _is_the_torrent_we_queued(td, info)
    if mine and await held_by_another(td):
        # The torrent is also another transfer's, or a seed's: its data is their
        # partial download, or the library folder being shared. This row is
        # refused; the torrent is left to whoever else is using it.
        logger.warning(
            "Torrent %s is over quota but another transfer or a seed holds the "
            "same torrent; refusing the row and leaving the torrent alone",
            getattr(td, "id", "?"))
        done = True
        status = REFUSED_STATUS
    elif mine:
        # By the hash, which is exactly what `mine` just confirmed. The tick
        # finds this torrent by its hash, so the check says nothing about the
        # number on the row - after a restart that number can name somebody
        # else's torrent, and this call deletes data.
        done = await transmission_handler.remove_torrent(
            td.info_hash, delete_data=True)
        status = REFUSED_STATUS
    else:
        logger.warning(
            "Torrent %s does not match the hash this download recorded; "
            "stopping it instead of removing it", getattr(td, "id", "?"))
        done = await transmission_handler.pause_torrent(td.transmission_id)
        status = "paused"
    message = _refusal_message(total_size, room, removed=mine)

    if not done:
        logger.warning(
            "Transmission did not accept the refusal of torrent %s; leaving the "
            "row alone so the next tick tries again", getattr(td, "id", "?"))
        return

    await _update_download(td.id, {
        "status": status,
        "error_msg": message,
        "error_code": REASONS["quota_refused" if mine else "quota_stopped"],
        "error_detail": str(room),
        "total_size": total_size,
    })
    await _emit_to_owner(td, "torrent:download_refused",
                         {"id": td.id, "reason": "quota", "removed": mine})


async def _as_it_is_now(td):
    """This transfer's row as the database holds it at this moment, or None.

    For the decisions that depend on who owns a transfer. The monitor reads its
    rows at the start of a tick, and an administrator taking the upload right
    away hands the account's transfers over (`hand_running_torrents_to`) in the
    database, not in the rows a tick is already holding.
    """
    from handler.database.session import async_session_factory
    from models.torrent_download import TorrentDownload
    from sqlalchemy import select

    async with async_session_factory() as db:
        found = (await db.execute(
            select(TorrentDownload).where(TorrentDownload.id == td.id)
        )).scalars().all()
    return next((row for row in found if row.id == td.id), None)


async def _check_downloads() -> None:
    from handler.database.session import async_session_factory
    # STATUS is a constant of the MODULE, not a field of the client, and reading
    # it off the instance raised on the last line of every tick that had a
    # transfer in progress - for six months, and in the released 1.0.33. The
    # loop caught it, logged a warning and slept, so the only symptom was that
    # progress never reached a screen and no row after the first was ever
    # looked at. `torrent_router` imports it the right way; this is the same
    # import, spelled the same.
    from handler.torrent.transmission_handler import STATUS, transmission_handler
    from handler.socket_handler import sio
    from models.torrent_download import TorrentDownload
    from sqlalchemy import select, update

    async with async_session_factory() as db:
        rows = (await db.execute(
            select(TorrentDownload).where(TorrentDownload.status == "downloading")
        )).scalars().all()

    for held in rows:
        # As the row is NOW, not as the tick read it. One transfer landing takes
        # minutes, and meanwhile a transfer can be taken over or paused: the one
        # after it was weighed against the demoted account's allowance and, if
        # it landed, filed as that account's game.
        td = await _as_it_is_now(held)
        if td is None or td.status != "downloading":
            continue
        if td.transmission_id is None:
            continue

        # By the hash when the row has one. The number is renumbered by every
        # daemon restart, so following it after a deploy either lost the row or
        # stopped at the mismatch check below for good.
        info = await transmission_handler.get_torrent(
            getattr(td, "info_hash", None) or td.transmission_id)
        if info is None:
            # "The daemon says it is not holding this" and "the daemon did not
            # answer" arrive here identically, and they are opposite facts. The
            # row is written to "error" below, and nothing brings it back: this
            # loop only ever selects "downloading" and no route moves a row out
            # of "error". So a ten second hiccup used to kill a healthy
            # transfer's bookkeeping for good while Transmission carried on
            # downloading it into a folder nobody would ever file.
            if not await transmission_handler.is_available():
                logger.warning(
                    "Transmission did not answer about torrent %s; leaving the "
                    "row alone until it does", td.id)
                continue
            await _update_download(td.id, {
                "status": "error",
                "error_msg": "Torrent lost from Transmission",
                "error_code": reason("lost"),
            })
            await _emit_to_owner(td, "torrent:download_error", {"id": td.id, "error": "Torrent lost"})
            continue

        # The daemon hands out `transmission_id` and starts again from 1 when it
        # restarts, so after one the number on this row can belong to somebody
        # else's torrent - two rows on the live install already share id 1.
        # Following it would report their progress as this transfer's and end
        # with their files registered as this account's game. Rows written
        # before the hash was recorded have nothing to compare and keep
        # following their number, which is all they ever had.
        if getattr(td, "info_hash", None) and not _is_the_torrent_we_queued(td, info):
            logger.warning(
                "Torrent %s now points at a different torrent in the daemon; "
                "not following it", td.id)
            continue

        tr_status = info.get("status", 0)
        percent   = float(info.get("percentDone", 0.0))

        # The size, as soon as anybody knows it.
        #
        # A .torrent is weighed before anything moves - uploaded as a file, or
        # fetched by the route from an http(s) address through the network
        # guard - because it carries its own metadata. A magnet cannot be: it is
        # a hash, and the totals arrive from peers minutes later.
        #
        # So it is weighed at the first moment there is anything to weigh. The
        # torrent already counts against this account once it lands (the game
        # gets `published_by=created_by_id` below); without this, a 40 GB
        # transfer onto a 10 GB allowance simply succeeded and then sat over the
        # limit, and a magnet was the way round the limit altogether.
        #
        # A size of zero is "not known yet", not "empty": every magnet looks
        # like that on its first tick, and refusing on it would refuse them all.
        total_size = int(info.get("totalSize", 0) or 0)
        if _size_just_arrived(td, total_size):
            over = await _over_quota(td, total_size)
            if over is None:
                # The stored size is the latch that records this transfer as
                # weighed, and it is written a few lines below. Closing it on
                # the strength of a measurement that failed is how one bad
                # lookup used to lift the limit for good, so the size stays
                # unwritten and the next tick asks the question again. The cost
                # is one missed progress event.
                continue
            if over:
                await _refuse_over_quota(td, info, total_size)
                continue

        updates: dict = {
            "percent_done":  percent,
            "total_size":    total_size,
            "rate_download": info.get("rateDownload", 0),
            "eta":           info.get("eta", -1),
        }

        if info.get("error", 0) != 0:
            updates["status"]    = "error"
            # The daemon's own wording, which we cannot write in anybody's
            # language. Named all the same, so the screen can frame it as
            # "the daemon said:" and show the text after it.
            #
            # `or` rather than a dict default: Transmission sends the key
            # with an empty string as often as it omits it, and a default
            # only applies to the second, which left the row marked failed
            # with nothing to show for it.
            updates["error_msg"] = info.get("errorString") or "Unknown error"
            updates["error_code"] = reason("daemon")
            await _update_download(td.id, updates)
            await _emit_to_owner(td, "torrent:download_error", {"id": td.id, "error": updates["error_msg"]})
            continue

        if percent >= 1.0:
            updates["status"]       = "complete"
            updates["completed_at"] = datetime.now(timezone.utc)
            await _update_download(td.id, updates)
            # "complete" is written BEFORE the registration on purpose: it takes
            # the row out of the set this loop polls, which is what stops the
            # next tick, ten seconds later, starting a second registration while
            # the first is still copying gigabytes.
            game_id, why_not, why_code, why_detail = await _auto_register_game(td)
            if game_id:
                await _update_download(td.id, {"game_id": game_id})
            else:
                # A transfer that finished and became nothing has to say so, and
                # say WHICH nothing. It reads as a plain success otherwise: no
                # game on the shelf, no message anywhere, and no way to tell this
                # apart from a title somebody deleted. Blocked by the scanner and
                # "the files are still sitting in the download folder" call for
                # completely different things from whoever reads it.
                await _update_download(td.id, {
                    "status": "error",
                    "error_msg": why_not or "The transfer finished but no game came of it.",
                    "error_code": why_code or reason("no_game"),
                    "error_detail": why_detail,
                })
            await _emit_to_owner(td, "torrent:download_complete", {"id": td.id, "game_id": game_id})
            continue

        await _update_download(td.id, updates)
        await _emit_to_owner(td, "torrent:download_progress", {
            "id":      td.id,
            "percent": round(percent * 100, 1),
            "speed":   info.get("rateDownload", 0),
            "eta":     info.get("eta", -1),
            "status":  STATUS.get(tr_status, "unknown"),
            # The tray refetches every thirty seconds and this ticks every ten,
            # so between fetches these numbers are all it has. Left out, the
            # peer count sits frozen beside a percentage that is moving, which
            # reads as a broken screen rather than a stale one.
            "peers":      info.get("peersConnected", 0),
            "peers_from": info.get("peersSendingToUs", 0),
        })


async def _update_download(torrent_id: int, values: dict) -> None:
    from handler.database.session import async_session_factory
    from models.torrent_download import TorrentDownload
    from sqlalchemy import update

    async with async_session_factory() as db:
        await db.execute(
            update(TorrentDownload)
            .where(TorrentDownload.id == torrent_id)
            .values(**values)
        )
        await db.commit()


async def _resolve_target_library(td):
    """Resolve the finished torrent's destination.

    Returns (storage_folder, target_lib_id) where:
      - a folder-backed custom library (kind "custom_lib" with a storage_folder)
        routes files into that folder and yields its id for a membership row;
      - anything else (no library, "games", GOG, emulation, or a folder-less lib)
        falls back to the built-in Games library (CUSTOM), target_lib_id=None.
    """
    slug = (getattr(td, "library", None) or "").strip()
    if not slug or slug == "games":
        return "CUSTOM", None
    try:
        from handler.database.library_registry_handler import library_registry_handler
        lib = await library_registry_handler.get_by_slug(slug)
    except Exception as exc:
        logger.warning("Torrent target library lookup failed for '%s': %s", slug, exc)
        return "CUSTOM", None
    if lib is not None and lib.kind == "custom_lib" and lib.storage_folder:
        return lib.storage_folder, lib.id
    return "CUSTOM", None


def _slug_for(title: str) -> str:
    """The folder a finished torrent lands in, derived from its title.

    THE FALLBACK IS THE POINT. Everything that is not ASCII alphanumeric is
    stripped, so a title written entirely in Cyrillic, Chinese or Japanese - or
    one that is only punctuation - used to leave the empty string, and nothing
    looked. `os.path.join(root, "games", folder, "")` is the library folder
    ITSELF, so the torrent's files went straight into the library root, on top
    of whatever was already there. The slugify in the torrent router has ended
    with `or "game"` all along; this copy never got it.
    """
    import re
    import unicodedata

    flat = unicodedata.normalize("NFKD", title or "").lower()
    flat = flat.encode("ascii", errors="ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", flat).strip("-") or "game"


def _collect_files(download_dir: str) -> list[str]:
    """Every real file the torrent left behind. Blocking; call in a thread.

    Symlinks are skipped. What is on the disk here was named by whoever made
    the torrent, and `os.walk` will not descend a symlinked directory but does
    list symlinked FILES - one of those moved into the library is a pointer to
    somewhere else entirely, standing behind the library's own file server.
    """
    found = []
    for root, dirs, fnames in os.walk(download_dir):
        dirs[:] = [d for d in dirs if not os.path.islink(os.path.join(root, d))]
        for fname in fnames:
            path = os.path.join(root, fname)
            if fname.startswith(".") or os.path.islink(path):
                continue
            found.append(path)
    return found


async def _threat_in(files: list[str]) -> str | None:
    """The first threat found in what the torrent brought, or None.

    A torrent was the one way into this library that nothing ever looked at, and
    it is the one where the bytes come from anonymous peers rather than from the
    account's own machine or from a shop. The other three paths all scan: the
    library upload and the ROM upload on `clamav_auto_scan_upload`, a GOG
    download on `clamav_auto_scan_download`. This is the second of those - a
    download that finishes and then becomes library content - so it reads the
    same setting, which means an admin who already asked for this gets it here
    without being asked again.

    Called BEFORE the files are moved, so a threat never reaches the library
    folder at all.

    FAILS OPEN, and never silently. `scan_file` states the rule: network and IO
    errors come back as "skipped" and FOUND is the only rejection. A daemon that
    cannot answer must not turn every torrent into a failure - but the admin
    asked for scanning, so being told it did not happen is the least this owes
    them.
    """
    from handler.clamav import clamav_handler as _clam

    try:
        if not await _clam.is_download_scanning_enabled():
            return None
    except Exception:  # noqa: BLE001 - unreadable settings are not a verdict
        logger.debug("Could not read the ClamAV settings", exc_info=True)
        return None

    for fpath in files:
        try:
            result = await _clam.scan_file(fpath)
        except Exception:  # noqa: BLE001
            logger.warning(
                "ClamAV scan of %s raised; the file is being filed UNSCANNED",
                fpath, exc_info=True)
            continue
        status = result.get("status")
        if status == "FOUND":
            threat = result.get("threat") or "unknown"
            action = await _clam.quarantine_or_delete(fpath, threat)
            logger.warning(
                "ClamAV blocked a torrent file (%s, threat=%s, action=%s)",
                fpath, threat, (action or {}).get("action"))
            return threat
        if status in ("skipped", "error"):
            logger.warning(
                "ClamAV did not scan %s (status=%s): %s - filed UNSCANNED",
                fpath, status, result.get("message") or "no detail")
    return None


def _move_into_library(
    files: list[str], download_dir: str, dest_root: str,
) -> list[tuple[str, int]]:
    """Move a finished torrent into the library and drop its download dir.

    Blocking, and not briefly: docker-compose mounts /data/games and
    /data/downloads as separate binds, so rename(2) between them returns EXDEV
    and shutil.move always degrades to a full copy. On a 60 GB torrent that is
    minutes of solid I/O, which is why this belongs in a thread and not on the
    event loop where it used to sit - holding a database session open the whole
    time and stopping every request, the health check and Socket.IO with it.
    """
    import shutil

    root = os.path.realpath(dest_root)
    # Every destination is decided and checked before a single file moves. The
    # refusal used to come at the colliding file, after the ones before it had
    # gone: those sat in the library with no rows, outside the quota and out of
    # sight, the torrent's folder was left incomplete so seeding broke, and the
    # caller told the person the files were still in the download folder.
    plan: list[tuple[str, str]] = []
    for fpath in files:
        dest = os.path.join(dest_root, os.path.relpath(fpath, download_dir))
        # Inside the folder it belongs in. Not reachable through `relpath` as
        # this is written, and asserted anyway: the names came from a torrent
        # somebody else made, and there is nothing between this function and
        # the file system if the destination is ever derived differently.
        if os.path.commonpath([root, os.path.realpath(os.path.dirname(dest) or root)]) != root:
            raise ValueError(f"Torrent file would land outside its folder: {dest}")
        # `shutil.move` replaces what it finds. Everything else written in this
        # release refuses instead of destroying - the ROM upload writes a .part
        # and renames it, the quota turns a transfer away rather than deleting
        # one - and the library is somebody's collection.
        if os.path.exists(dest):
            raise FileExistsError(
                f"A file is already in the library at {dest}; the torrent was "
                "left in its download folder rather than written over it.")
        plan.append((fpath, dest))

    os.makedirs(dest_root, exist_ok=True)
    moved = []
    done: list[tuple[str, str]] = []
    current: tuple[str, str] | None = None
    try:
        for fpath, dest in plan:
            current = (fpath, dest)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.move(fpath, dest)
            done.append(current)
            # Sized here, in the thread, so the caller does not stat every file
            # back on the event loop.
            moved.append((dest, os.path.getsize(dest)))
            logger.debug("Moved torrent file %s -> %s", fpath, dest)
    except BaseException:
        _put_torrent_files_back(done, current, dest_root)
        raise
    try:
        shutil.rmtree(download_dir)
    except Exception:
        pass  # ignore cleanup errors
    return moved


def _put_torrent_files_back(done, current, dest_root) -> None:
    """Undo a move that broke off, so the download folder is whole again.

    A full disk or a mount going away can stop the move after some files have
    gone, and the caller then says the files are still in the download folder.
    This makes that true: what had been moved goes back, and a copy that broke
    off halfway - across the bind mounts a move is a copy - is removed from the
    library while its original is still in place. Nothing at those destinations
    was anybody else's: every one was checked to be free before the first move.
    """
    import shutil

    if current is not None and current not in done:
        source, dest = current
        if os.path.exists(source) and os.path.lexists(dest):
            try:
                os.remove(dest)
            except OSError:
                logger.warning("Could not remove the partial copy at %s", dest, exc_info=True)
    touched = {os.path.dirname(dest) for _s, dest in done}
    if current is not None:
        touched.add(os.path.dirname(current[1]))
    for source, dest in reversed(done):
        try:
            os.makedirs(os.path.dirname(source), exist_ok=True)
            shutil.move(dest, source)
        except OSError:
            logger.warning("Could not put %s back into the download folder", dest, exc_info=True)
    # And the folders the move made, now empty. Only empty ones: the
    # destination can be a folder a deleted game left behind, with its own files.
    root = os.path.realpath(dest_root)
    for directory in sorted(touched, key=len, reverse=True):
        here = os.path.realpath(directory)
        while here != root and os.path.commonpath([root, here]) == root:
            try:
                os.rmdir(here)
            except OSError:
                break
            here = os.path.dirname(here)
    try:
        os.rmdir(root)
    except OSError:
        pass


async def _auto_register_game(td) -> tuple[int | None, str | None, str | None, str | None]:
    """Scan download_dir, move files to /data/games/{storage_folder}/{slug}/,
    register as LibraryGame. When the download targets a folder-backed custom
    library, files land in that library's folder and the game is added to it
    (membership) instead of the default Games library.

    Returns (game_id, sentence, code, detail). The last three are what the
    transfer's row says when no game came of it: a sentence to fall back on,
    a name the screen can translate, and the one value that name needs to be
    read with. They exist because "finished, nothing on the shelf, no message
    anywhere" is indistinguishable from a title somebody deleted.
    """
    from handler.database.session import async_session_factory
    from models.library_game import LibraryGame
    from models.library_file import LibraryFile
    from config import BASE_PATH

    download_dir = td.download_dir
    if not os.path.isdir(download_dir):
        return (None, "The download folder is gone, so there was nothing to file.",
                reason("no_folder"), None)

    files_found = await asyncio.to_thread(_collect_files, download_dir)
    if not files_found:
        return (None, "The transfer left no files to add to the library.",
                reason("no_files"), None)

    # Before anything moves, so a threat never reaches the library folder.
    threat = await _threat_in(files_found)
    if threat:
        return None, f"Blocked by ClamAV: {threat}", reason("threat"), threat

    # Resolve destination library (folder + optional membership target).
    storage_folder, target_lib_id = await _resolve_target_library(td)
    is_custom_lib = target_lib_id is not None

    # Slugify title. Never empty - see `_slug_for`, where an empty one meant the
    # library root and files written on top of other people's games.
    title = td.title or "Unknown Game"
    slug_base = _slug_for(title)

    # Whose game this is, read now. The virus scan above can take minutes, and
    # a transfer taken over meanwhile carries its new owner in the database, not
    # in the row the monitor handed in. Who brought it in stays as it was.
    current = await _as_it_is_now(td)
    owner_id = current.created_by_id if current is not None else td.created_by_id

    # Claim the slug and the row first, in a session that closes immediately.
    # The copy below can run for minutes, and it used to run inside this
    # session, which meant a database connection sat open and idle for all of
    # it. Owning the row up front also means the slug cannot be taken by a
    # second torrent finishing while this one is still copying.
    async with async_session_factory() as db:
        from sqlalchemy import select
        slug = slug_base
        n = 1
        while (await db.execute(
            select(LibraryGame).where(LibraryGame.slug == slug)
        )).scalar_one_or_none():
            slug = f"{slug_base}-{n}"
            n += 1

        game = LibraryGame(
            title=title,
            slug=slug,
            source="torrent",
            is_active=True,
            # A torrent is a game arriving, so it belongs to whoever queued it
            # and counts against their upload quota like anything else they
            # add. This was None until the route came down to the uploader,
            # which turned a dormant gap into the one way in that ignored the
            # limit. Still None for a download queued before the account was
            # recorded and whose uploader has since been deleted.
            published_by=owner_id,
            # Who brought it in, which is only different once an administrator
            # has taken the transfer over from an account that lost the right
            # to upload. Falls back to the owner for every row written before
            # the second column existed, where the two were the same by
            # definition.
            uploaded_by=getattr(td, "uploaded_by_id", None) or td.created_by_id,
            # A game routed into a custom library lives only there by default.
            in_default_library=not is_custom_lib,
        )
        db.add(game)
        await db.commit()
        game_id = game.id

    # Move files from torrent download dir → /data/games/{storage_folder}/{slug}/
    dest_root = os.path.join(BASE_PATH, "games", storage_folder, slug)
    try:
        moved_files = await asyncio.to_thread(
            _move_into_library, files_found, download_dir, dest_root
        )
    except Exception as exc:
        # Never leave a game row behind with no files under it: it would show on
        # the shelf as a title that cannot be downloaded and cannot be explained.
        logger.error("Torrent files could not be moved into %s: %s", dest_root, exc)
        async with async_session_factory() as db:
            orphan = await db.get(LibraryGame, game_id)
            if orphan is not None:
                await db.delete(orphan)
                await db.commit()
        return (None,
                "The transfer finished, but its files could not be added to the "
                "library. They are still in the download folder.",
                reason("move_failed"), None)

    async with async_session_factory() as db:
        game = await db.get(LibraryGame, game_id)
        for fpath, size in moved_files:
            lib_file = LibraryFile(
                library_game_id=game.id,
                filename=os.path.basename(fpath),
                file_path=os.path.relpath(fpath, BASE_PATH),
                size_bytes=size,
                os=td.os,
                file_type="game",
                source="torrent",
                is_available=True,
            )
            db.add(lib_file)

        await db.commit()
        from plugins import events as _plugin_events
        _plugin_events.game_added(game)
        _plugin_events.download_complete(
            game, os.path.dirname(moved_files[0][0]) if moved_files else dest_root
        )
        # Recently-added card: no-op unless the torrent game already has a cover
        # (usually it does not until an admin scrapes it, which announces then).
        try:
            from handler.notifications.recently_added import schedule_library_game
            schedule_library_game(game_id)
        except Exception:
            pass

    # Membership is written through the registry handler (its own session), so
    # it must happen after the game row is committed above.
    if is_custom_lib:
        try:
            from handler.database.library_registry_handler import library_registry_handler
            await library_registry_handler.set_memberships(game_id, [target_lib_id])
        except Exception as exc:
            logger.warning("Torrent membership assignment failed for game %d: %s", game_id, exc)

    logger.info(
        "Auto-registered game '%s' (id=%d) from torrent → %s/%s%s",
        title, game_id, storage_folder, slug,
        " (custom library)" if is_custom_lib else "",
    )
    return game_id, None, None, None
