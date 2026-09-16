"""How much room an uploader has left for the games they add.

There were two byte limits before this and neither was a quota. The upload size
limit is a ceiling on one file: it counts bytes as they stream past and stops,
remembering nothing, so an account allowed 50 GB per file could add a thousand
of them. The save quota is a real running total, but only for save states and
memory cards. Nothing had ever added up what an uploader's games take.

What counts is what they brought in. A game published from a linked GOG account
is recorded against the account that owns it and can be tens of gigabytes
nobody uploaded, so it is left out; the admin decides whether those appear at
all. Everything else the account owns counts, including games fetched from a
plugin catalogue, which are stored as custom exactly like a hand upload.

The total is a sum over the games an account owns, never a number kept in a
column. That is what makes an admin claiming a game free the space with no code
to run: the owner changes and the next sum is smaller. A stored counter would
have to be adjusted here, in the claim, in every delete and in every failed
upload, and would be wrong the first time one of those paths was missed.

Zero keeps the meaning it already has for the two fields beside it when set on
an account: use the global default. Set globally it means no limit, because
there is no sane figure to invent for somebody else's disk, and because a
release that began enforcing one nobody chose would lock out uploaders who are
already past it.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func, select

from handler.auth.scopes import Scope
from handler.library.ownership import can_delete_rom_set

CONFIG_KEY = "upload_quota_bytes"
PERMISSION_KEY = "upload_quota_bytes"

#: The permissions the delete flag on a ROM row is computed with. See the note
#: beside `_may_remove`: the answer wanted here is "may the account this list
#: belongs to remove this", and an administrator's yes-to-everything is not it.
_AS_AN_UPLOADER = frozenset({Scope.LIBRARY_UPLOAD})


def resolve_limit(per_user: Any, global_value: Any) -> int:
    """The figure that applies, in bytes, or 0 for no limit.

    Both arguments arrive as text: one from a JSON column, the other from a
    config table. Anything that is not a positive whole number is treated as
    unset rather than as a limit of nothing, which is the difference between
    falling back and locking somebody out.
    """
    for candidate in (per_user, global_value):
        try:
            value = int(candidate)
        except (TypeError, ValueError):
            continue
        if value > 0:
            return value
    return 0


def fits(*, used: int, incoming: int, limit: int) -> bool:
    """Whether `incoming` more bytes may be added. A limit is a ceiling to
    reach, not one to stay under, so filling it exactly is allowed."""
    if limit <= 0:
        return True
    return used + incoming <= limit


async def used_bytes(user_id: int | None) -> int:
    """Bytes held by what this account owns, GOG publications excluded.

    Two sums, because the library keeps its content in two shapes. A game is a
    LibraryGame with LibraryFile rows hanging off it; a ROM is a single row in
    its own table with its size on it. The quota used to be only the first, which
    made every ROM ever fetched invisible to it - reported as "pobralem jako
    gdtest gre na amige i nie zostala zaliczona", and true of the whole domain
    rather than of one download.

    Still summed in SQL and never off the disk, and still never a stored counter:
    that is what lets an admin claiming something free the space with nothing to
    run. Two sums keep that property; a cached column would not.
    """
    if not user_id:
        return 0
    from handler.database.session import async_session_factory
    from models.library_file import LibraryFile
    from models.library_game import LibraryGame
    from models.rom import Rom

    async with async_session_factory() as session:
        games = await session.scalar(
            select(func.coalesce(func.sum(LibraryFile.size_bytes), 0))
            .select_from(LibraryFile)
            .join(LibraryGame, LibraryGame.id == LibraryFile.library_game_id)
            .where(
                # The account that brought THIS file in, and only when nothing
                # says, the account that owns the game it hangs off. A game can
                # hold files from two people: a catalogue entry downloaded a
                # second time reuses the first account's game on purpose,
                # because it is the same game, and asking only the game charged
                # the second person's gigabytes to the first. The fallback is
                # what keeps every row written before this column counting
                # exactly as it did.
                func.coalesce(LibraryFile.published_by,
                              LibraryGame.published_by) == user_id,
                _counts_towards_quota(LibraryGame.source),
            )
        )
        roms = await session.scalar(
            select(func.coalesce(func.sum(Rom.fs_size_bytes), 0))
            .where(
                Rom.published_by == user_id,
                # A vanished file keeps its row so the library can say it is
                # missing rather than forgetting it. Charging somebody for bytes
                # that are not on the disk would be charging them for a notice.
                Rom.missing_from_fs.is_(False),
            )
        )
    return int(games or 0) + int(roms or 0)


def _counts_towards_quota(source_column):
    """The one sentence that decides what a quota is a quota of.

    Written once and used by both the total and the listing, so the figure on
    the bar can never disagree with the rows underneath it.
    """
    from sqlalchemy import func as _func

    return _func.coalesce(source_column, "custom") != "gog"


async def owned_games(user_id: int | None) -> list[dict]:
    """The games counted against this account, largest first.

    Ordered by size because the reason to look at this list is to find what to
    remove, and the answer is nearly always at the top.

    THE SAME RULE AS THE BAR, per file. This asked the game's owner and summed
    every file hanging off it, while `used_bytes` above had moved to the account
    that brought each FILE - so on the one shape the release added, a catalogue
    entry fetched twice, the two disagreed in both directions at once: the
    second account was charged for bytes its list did not mention, and the first
    was shown a row totalling somebody else's gigabytes. Three routes hand the
    figure and the list out together and promise in writing that they agree.
    """
    if not user_id:
        return []
    from sqlalchemy import and_, or_
    from handler.database.session import async_session_factory
    from models.library_file import LibraryFile
    from models.library_game import LibraryGame

    # Read twice, and it has to be the same sentence both times: in the join, to
    # decide which files this account is charged for, and in the WHERE through
    # the sub-select, to decide which games it sees at all.
    charged = func.coalesce(LibraryFile.published_by,
                            LibraryGame.published_by) == user_id
    theirs = (select(LibraryFile.library_game_id)
              .where(LibraryFile.published_by == user_id))

    size = func.coalesce(func.sum(LibraryFile.size_bytes), 0).label("size_bytes")
    async with async_session_factory() as session:
        rows = (await session.execute(
            select(
                LibraryGame.id, LibraryGame.title, LibraryGame.slug,
                LibraryGame.cover_path, LibraryGame.source,
                LibraryGame.in_default_library,
                LibraryGame.metadata_locked, LibraryGame.published_by,
                size, func.count(LibraryFile.id).label("file_count"),
            )
            # Outer, so a game whose files are all gone still appears. That is
            # exactly the wreckage somebody would come here to clear away. The
            # ownership half rides in the ON rather than the WHERE for the same
            # reason: as a filter it would drop those games entirely.
            .select_from(LibraryGame)
            .outerjoin(LibraryFile,
                       and_(LibraryFile.library_game_id == LibraryGame.id, charged))
            .where(
                or_(LibraryGame.published_by == user_id, LibraryGame.id.in_(theirs)),
                _counts_towards_quota(LibraryGame.source),
            )
            .group_by(LibraryGame.id)
            .order_by(size.desc())
        )).all()
    games = [
        {
            "kind": "game",
            "id": r.id, "title": r.title, "slug": r.slug,
            "cover_path": r.cover_path, "source": r.source,
            "size_bytes": int(r.size_bytes or 0), "file_count": int(r.file_count or 0),
            "in_default_library": bool(r.in_default_library),
            "metadata_locked": bool(r.metadata_locked),
            # Charged for it is not the same as allowed to remove it. A game can
            # now appear here because one file in it is this account's, and
            # deleting the game takes everybody's - so the delete rule reads the
            # GAME's owner, and the row says which kind it is rather than
            # leaving the screen to draw a button that can only answer 403.
            "can_delete": r.published_by == user_id,
        }
        for r in rows
    ]
    await _attach_library(games)
    games.extend(await _owned_roms(user_id))
    # One order over both kinds, because the reason to open this list is to find
    # what to remove and the answer does not care which table a thing lives in.
    games.sort(key=lambda g: g["size_bytes"], reverse=True)
    return games


async def _sets_the_route_would_take(session, rows) -> dict[int, list]:
    """For each listed ROM, the rows that deleting it would take with it.

    The same set `rom_handler.disk_set` builds, and built the same way, because
    the flag beside a bin means nothing unless it was computed from the list the
    bin acts on. Three steps, and a question asked by `disk_group` alone reaches
    neither end of them:

      UP      a track file belongs to its sheet, and acting on it acts on that
              disc. A track carries no group, so from a group it is invisible.
      ACROSS  a sheet that is one disc of several brings its siblings.
      DOWN    every one of those discs brings its own track files, which is how
              a sheet with somebody else's data file behind it is not, in fact,
              a title of one.

    Three queries for the whole list rather than three per row. The listed rows
    are one account's uploads, so this is a handful of names in practice, but a
    query per row would make opening the page cost one round trip per ROM.
    """
    from models.rom import Rom

    cols = (Rom.id, Rom.platform_id, Rom.fs_name, Rom.published_by,
            Rom.track_of, Rom.disk_group)

    sheet_names = {r.track_of for r in rows if r.track_of}
    sheets: dict[tuple[int, str], Any] = {}
    if sheet_names:
        for row in (await session.execute(
            select(*cols).where(Rom.fs_name.in_(sorted(sheet_names)))
        )).all():
            sheets[(row.platform_id, row.fs_name)] = row

    def _sheet_of(row):
        # Falling back to the row itself is what `_sheet_of` in the handler
        # does: a track whose sheet has gone is still something, and losing it
        # from the list would be worse than treating it as its own title.
        if not row.track_of:
            return row
        return sheets.get((row.platform_id, row.track_of), row)

    groups = {s.disk_group for s in (_sheet_of(r) for r in rows) if s.disk_group}
    by_group: dict[tuple[int, str], list] = {}
    if groups:
        for row in (await session.execute(
            select(*cols).where(Rom.disk_group.in_(sorted(groups)))
        )).all():
            by_group.setdefault((row.platform_id, row.disk_group), []).append(row)

    discs: dict[int, list] = {}
    for row in rows:
        sheet = _sheet_of(row)
        discs[row.id] = (
            by_group.get((sheet.platform_id, sheet.disk_group), [sheet])
            if sheet.disk_group else [sheet]
        )

    disc_names = {d.fs_name for members in discs.values() for d in members}
    by_sheet: dict[tuple[int, str], list] = {}
    if disc_names:
        for row in (await session.execute(
            select(*cols).where(Rom.track_of.in_(sorted(disc_names)))
        )).all():
            by_sheet.setdefault((row.platform_id, row.track_of), []).append(row)

    return {
        rom_id: members + [
            track
            for disc in members
            for track in by_sheet.get((disc.platform_id, disc.fs_name), ())
        ]
        for rom_id, members in discs.items()
    }


async def _owned_roms(user_id: int) -> list[dict]:
    """The ROMs counted against this account, shaped like the games beside them.

    Marked with a kind, because a row here is not interchangeable: a game has
    files and an editor behind it, a ROM is one file on a platform shelf. A
    caller that cannot tell them apart would offer the wrong buttons.

    Grouped by platform rather than by library. That IS the shelf a ROM sits on,
    and it is what somebody scanning this list for something to delete is
    looking for.
    """
    from handler.database.session import async_session_factory
    from models.rom import Rom
    from models.rom_platform import RomPlatform

    async with async_session_factory() as session:
        rows = (await session.execute(
            select(
                Rom.id, Rom.name, Rom.fs_name, Rom.slug, Rom.cover_path,
                Rom.fs_size_bytes, Rom.metadata_locked,
                # `track_of` and `published_by` are here for the delete rule
                # below, not for the row it returns: without them a listed row
                # cannot be walked to its sheet and cannot be handed to
                # `can_delete_rom_set`, which reads the owner off it.
                Rom.platform_id, Rom.disk_group, Rom.track_of, Rom.published_by,
                RomPlatform.slug.label("platform_slug"),
                RomPlatform.name.label("platform_name"),
                RomPlatform.custom_name,
            )
            .select_from(Rom)
            .outerjoin(RomPlatform, RomPlatform.id == Rom.platform_id)
            .where(
                Rom.published_by == user_id,
                Rom.missing_from_fs.is_(False),
            )
        )).all()

        # Whether the bin beside each row would actually work.
        #
        # It used to be written as True on every ROM without asking, and the
        # route behind the button asks a harder question: a deletion takes the
        # whole disc set, so `can_delete_rom_set` refuses unless every disc of
        # the title is this account's. For a single-disc ROM - the common case -
        # the set is itself and True was right; for an account that supplied the
        # one disc a set was missing, the row offered a button that could only
        # answer 403.
        sets = await _sets_the_route_would_take(session, rows)

    def _may_remove(row) -> bool:
        # THE RULE ITSELF, not a second spelling of it. The first attempt at
        # this wrote out the ownership walk again here and compared members
        # gathered by `disk_group` - which is not the list the route acts on,
        # and cannot be: a track file never carries a group. So a sheet with
        # somebody else's data file behind it, and a data file of mine under
        # somebody else's sheet, both read as "a title of one, and it is mine".
        #
        # An administrator is deliberately not modelled. `can_delete_rom` says
        # yes to any row for one, so passing real admin scopes here would flip
        # rows to True - and this list is drawn for one account, including by an
        # admin looking at somebody else's holdings, where "yes, because I am an
        # admin" is not the answer the page is asking for. The cost is a bin
        # hidden from an admin who could have used it, which breaks no promise;
        # the case this fixes is the opposite one, a bin offered to somebody the
        # route will refuse.
        return can_delete_rom_set(_AS_AN_UPLOADER, user_id, row, sets.get(row.id, [row]))

    return [
        {
            "kind": "rom",
            "id": r.id,
            # The scraped title when there is one, and the file name when there
            # is not. A row with no name at all would be the hardest one to act
            # on, and those are exactly the ones somebody comes here to clear.
            "title": r.name or r.fs_name,
            "slug": r.slug,
            "cover_path": r.cover_path,
            "source": "rom",
            "size_bytes": int(r.fs_size_bytes or 0),
            "file_count": 1,
            # Computed, not assumed. A ROM has one owner, but a DELETION takes
            # the whole disc set - so a disc of mine inside somebody else's set
            # is charged to me and still not mine to remove.
            "can_delete": _may_remove(r),
            "in_default_library": False,
            "metadata_locked": bool(r.metadata_locked),
            "library": {
                "slug": r.platform_slug or "roms",
                "name": r.custom_name or r.platform_name or "ROMs",
                "icon": None, "color": None, "order": 50,
            },
        }
        for r in rows
    ]


async def _attach_library(games: list[dict]) -> None:
    """Say which shelf each game sits on, so the list can be grouped by it.

    A game can belong to several libraries at once. The one named here is the
    first by the order an admin arranged them in, because a game has to appear
    under one heading and picking the same one every time matters more than
    which one it is.
    """
    if not games:
        return
    from handler.database.session import async_session_factory
    from models.library import Library, LibraryMembership

    ids = [g["id"] for g in games]
    async with async_session_factory() as session:
        memberships = (await session.execute(
            select(LibraryMembership.library_game_id, LibraryMembership.library_id)
            .where(LibraryMembership.library_game_id.in_(ids))
        )).all()
        shelves = {
            row.id: {"slug": row.slug, "name": row.name,
                     "icon": row.icon, "color": row.color, "order": row.sort_order}
            for row in (await session.execute(
                select(Library.id, Library.slug, Library.name,
                       Library.icon, Library.color, Library.sort_order)
            )).all()
        }

    by_game: dict[int, list[int]] = {}
    for m in memberships:
        by_game.setdefault(m.library_game_id, []).append(m.library_id)

    for game in games:
        options = [shelves[i] for i in by_game.get(game["id"], []) if i in shelves]
        options.sort(key=lambda s: (s["order"], s["name"]))
        if options:
            game["library"] = options[0]
        elif game["in_default_library"]:
            # The built-in Games library is membership by absence, not by a row.
            game["library"] = {"slug": "games", "name": "Games", "icon": None,
                               "color": None, "order": 0}
        else:
            # Nothing claims it. Naming the source beats an "Other" heading that
            # says only that the code did not know.
            game["library"] = {"slug": game["source"] or "custom",
                               "name": (game["source"] or "custom").title(),
                               "icon": None, "color": None, "order": 99}


async def limit_for(user: Any) -> int:
    """The quota this account is held to, in bytes, or 0 for no limit."""
    per_user = (getattr(user, "permissions", None) or {}).get(PERMISSION_KEY)
    from handler.config.config_handler import config_handler

    return resolve_limit(per_user, await config_handler.get(CONFIG_KEY))


def narrow(*, max_bytes: int, limit: int, used: int) -> int:
    """The per-file ceiling, brought down to whatever the account has spare.

    The two limits answer different questions and both have to hold, so the
    binding one is simply the smaller. Expressing the quota as a lower ceiling
    is what lets the byte counting that already guards every download enforce
    it too, instead of a second count living beside the first and disagreeing
    with it.
    """
    if limit <= 0:
        return max_bytes
    return max(0, min(max_bytes, limit - used))


async def ceiling_for(user: Any, max_bytes: int) -> int:
    """`narrow` against this account, refusing outright when nothing is spare.

    Two of the three ways in fetch in the background, where the size is not
    known until the bytes arrive. Handing the job a lower ceiling puts the
    quota inside the loop that was already counting.
    """
    limit = await limit_for(user)
    if limit <= 0:
        return max_bytes
    used = await used_bytes(getattr(user, "id", None))
    room = narrow(max_bytes=max_bytes, limit=limit, used=used)
    if room <= 0:
        from fastapi import HTTPException, status

        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Upload quota reached: {used} of {limit} bytes already used.",
        )
    return room
