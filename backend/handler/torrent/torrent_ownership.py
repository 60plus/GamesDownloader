"""Who a transfer belongs to once its owner may no longer upload.

The owner settled this after watching a demotion do nothing to a running
torrent: the transfer stays, and it changes hands. Stopping it was rejected for
the reason the ROM download path had already been given - losing a permission is
not a reason to destroy work in progress, and Transmission cannot hand back the
hours a twenty gigabyte transfer has already spent.

Leaving it alone was rejected too, because a transfer belonging to an account
that may no longer upload is that account still spending an allowance it does
not have, on a game it will own when the transfer lands. Handing it to the
administrator who took the permission away answers all of that at once.

This is the game claim, applied to a transfer, and the important part is what it
copies: `claim_writes` next door writes ONE field, and its docstring says the
point of the function is the fields it leaves alone. Who brought a game in is
not what a claim decides. The same holds here.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

#: Transfers that have not landed yet. A finished one is already a game, and a
#: game has its own claim, with its own route. Reaching into it from here would
#: be a second way to do the same thing, ready to disagree with the first the
#: day either one changes.
#:
#: "Not landed" includes a transfer that reads "complete" and has no game yet.
#: The monitor writes "complete" before it files the game, and filing takes
#: minutes - every file virus scanned, then copied between bind mounts - so a
#: transfer in that state is still on its way, and left out of the handover its
#: game was filed under the account that had just lost the right to upload.
IN_FLIGHT = ("downloading", "paused")


def not_landed():
    """The rows still on their way, as a clause: running, paused, or finished
    and not yet a game.

    Asked in two places that must never disagree - who a transfer is handed to
    when its owner loses the right to upload, and what an account's quota
    already has spoken for. Written once so the day one of them learns about a
    new state, the other does too.
    """
    from sqlalchemy import and_, or_

    from models.torrent_download import TorrentDownload

    return or_(
        TorrentDownload.status.in_(IN_FLIGHT),
        and_(TorrentDownload.status == "complete",
             TorrentDownload.game_id.is_(None)),
    )


def hand_over_writes(*, admin_id: int | None) -> dict:
    """The fields taking a transfer over is allowed to change.

    One field, and, as with `claim_writes`, the point is the rest.
    `uploaded_by_id` records who brought the transfer in and a claim does not
    decide that; `created_by` keeps the name for display, so the transfer still
    reads as theirs on the screen that shows both.
    """
    if not admin_id:
        # Blanking the owner would not be a claim. An unowned transfer belongs
        # to nobody here and in the quota, so the bytes would leave the demoted
        # account and start counting against no one at all.
        raise ValueError("Taking a transfer over needs the id of the account taking it.")
    return {"created_by_id": int(admin_id)}


async def hand_running_torrents_to(
    previous_owner_id: int | None,
    admin_id: int | None,
    *,
    session=None,
) -> int:
    """Give this account's unfinished transfers to `admin_id`. Returns how many.

    Nothing is stopped and nothing is deleted: the bytes keep arriving, and when
    they land the game is registered to its new owner with the original account
    still named as the one who brought it in.
    """
    from sqlalchemy import select, update

    from models.torrent_download import TorrentDownload

    writes = hand_over_writes(admin_id=admin_id)   # refuses before touching a row
    if not previous_owner_id or previous_owner_id == admin_id:
        return 0

    async def _run(db) -> int:
        rows = (await db.execute(
            select(TorrentDownload.id).where(
                TorrentDownload.created_by_id == previous_owner_id,
                not_landed(),
            )
        )).scalars().all()
        if not rows:
            return 0
        await db.execute(
            update(TorrentDownload)
            .where(TorrentDownload.id.in_(rows))
            .values(**writes)
        )
        await db.commit()
        logger.info(
            "Handed %d unfinished torrent(s) from account %s to %s",
            len(rows), previous_owner_id, admin_id)
        return len(rows)

    if session is not None:
        return await _run(session)

    from handler.database.session import async_session_factory
    async with async_session_factory() as db:
        return await _run(db)
