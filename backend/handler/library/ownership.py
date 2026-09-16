"""Who may remove a game, decided once.

Every other rule in this codebase is "may this role do this", and the route
decorator settles it before the handler runs. This one also asks "is this row
yours", which the decorator cannot express: `protected_route` requires every
scope it is given, so there is no way to spell "an admin, or else the owner".

That leaves the route declaring the weaker permission and the handler deciding
the rest, which is only safe while the deciding happens in one place. It is the
same shape as `visibility.py` next door, and that file's header records what
happened the last time one rule lived in two places and only one was asked.

The uploader is allowed this because of what it is for: undoing their own bad
archive or broken upload without an admin having to clean up after them. It
also explains why an admin claiming a game takes the ability away. A claim
writes the admin as the owner, and the rule below then says no on its own,
without needing to know that claiming exists.
"""

from __future__ import annotations

from typing import Any, Iterable

from fastapi import HTTPException, status

from handler.auth.scopes import Scope


def _may_delete(
    scopes: Iterable[Scope], user_id: int | None, obj: Any, *, admin_scope: Scope,
    owner_attr: str = "published_by",
) -> bool:
    """An administrator, or else the account that brought this in.

    `scopes` is what the request actually carries, not what the role implies:
    per-account overrides can revoke as well as grant, so an admin with the
    Games library switched off is refused here like anybody else.

    One rule for three kinds of thing. What differs is the permission that means
    "administrator" and the field that records the owner, which is why both are
    arguments rather than the reason for a third copy of this.
    """
    held = set(scopes)
    if admin_scope in held:
        return True
    if Scope.LIBRARY_UPLOAD not in held:
        return False
    # Both sides must be a real id. A game registered from a torrent, nearly
    # every ROM on a real install, and a download started by the server itself
    # carry no owner at all; reading that as a match rather than as "not mine"
    # would hand every one of them to the first uploader who looked.
    owner = getattr(obj, owner_attr, None)
    return bool(owner) and bool(user_id) and owner == user_id


def can_delete_game(scopes: Iterable[Scope], user_id: int | None, game: Any) -> bool:
    """True when this caller may remove this game, files and all."""
    return _may_delete(scopes, user_id, game, admin_scope=Scope.LIBRARY_ADMIN)


def can_delete_rom(scopes: Iterable[Scope], user_id: int | None, rom: Any) -> bool:
    """The same question for a ROM.

    A ROM gained an owner when the upload quota learned to count one, and the
    account that fetched it can now clear it up for the same reason an uploader
    can remove a game they added: undoing their own mistake without an admin
    having to tidy up after them.

    ROMS_WRITE rather than LIBRARY_ADMIN, because that is the permission the
    rest of the ROM API treats as administrative.
    """
    return _may_delete(scopes, user_id, rom, admin_scope=Scope.ROMS_WRITE)


def can_delete_rom_set(
    scopes: Iterable[Scope], user_id: int | None, named: Any, members: Iterable[Any],
) -> bool:
    """The same question about a ROM and everything that goes with it.

    A ROM is deleted as a set. Naming one sheet takes every disc of the title,
    every track file behind every disc, the media, and every account's saves for
    all of them - so asking about one row and acting on the list is asking the
    wrong question. The route did exactly that, and because `disk_set` returns
    the group sorted by disc number, the row it asked about was the lowest disc
    rather than the one the caller named: fetching disc 1 was enough to delete
    disc 2 and everybody's saves for it.

    Two halves, and both are needed:

      the named row      says whether this is the caller's to remove at all. An
                         unowned ROM is nobody's, and an uploader does not
                         acquire one by naming it beside a disc that is theirs.

      the other discs    must each be the caller's as well. A TRACK FILE is the
                         exception: it belongs to its sheet and has no life of
                         its own, and ownership is stamped on the file that was
                         fetched, so the .bin behind an uploaded .cue carries no
                         name. Refusing that would stop an uploader removing
                         their own upload, which is what this route is for.

    A DISC with no owner is NOT that exception, which this rule first got wrong.
    A set scanned in years ago carries no owner and carries several people's
    saves; an uploader who supplies the one disc that was missing would then
    remove the other three, and their savestates, by deleting their own. So an
    unowned disc means the set is not wholly theirs, and the whole call is
    refused rather than quietly taking the rest.

    An administrator passes every half, because `can_delete_rom` says yes to any
    row for one.
    """
    if not can_delete_rom(scopes, user_id, named):
        return False
    for member in members:
        if getattr(member, "track_of", None) and not getattr(member, "published_by", None):
            continue        # a track file of a sheet in this set
        if not can_delete_rom(scopes, user_id, member):
            return False
    return True


def can_upload_into_game(scopes: Iterable[Scope], user_id: int | None, game: Any) -> bool:
    """Whether this caller may add files to this game.

    The same question as removing it, and for a reason worth writing down: the
    upload route never asked, so an uploader who owned nothing had a quota that
    read zero for ever. They could name any game id - listing games is a read
    everybody has - and push files into it at no cost, while the account that
    owned it was pushed over its own limit by uploads it never made.

    Keeping the two rules identical also keeps the pair honest: the bytes you
    are charged for sit on a game you are allowed to clear up.
    """
    return _may_delete(scopes, user_id, game, admin_scope=Scope.LIBRARY_ADMIN)


def can_touch_download(scopes: Iterable[Scope], user_id: int | None, job: Any) -> bool:
    """Whether this caller may pause, resume, retry or cancel this download.

    The ROM Downloader was admin-only until this release. Opening it to every
    account with the store permission handed all four of those verbs to
    everybody, over a registry keyed by a small integer, and cancelling deletes
    the half-written file. So the question is the same one asked of a ROM: an
    administrator, or the account that started it.

    The job records `actor_id` because the quota had to charge downloads to
    somebody, so nothing new is stored to answer this.
    """
    return _may_delete(scopes, user_id, job, admin_scope=Scope.ROMS_WRITE,
                       owner_attr="actor_id")


def claim_writes(*, admin_id: int | None) -> dict:
    """The fields an admin taking a game over is allowed to change.

    One field, and the point of the function is the rest. A claim answers who
    owns a game, not who brought it in, so `uploaded_by` stays as it was and the
    uploader keeps their name on the detail page. That is invisible in a diff
    which adds a key to a dict, so the write is spelled out here where a test
    can assert on the whole of it.

    The other two effects the owner asked for need nothing written. The rule
    above reads `published_by`, so the uploader loses the game the moment it
    stops being theirs, and the quota is a sum over owned games rather than a
    stored counter, so the space comes back on the next read.
    """
    if not admin_id:
        # Blanking the owner would not be a claim. An unowned game reads as
        # nobody's here and in the quota, so the game would leave the uploader's
        # total while belonging to no one at all.
        raise ValueError("A claim needs the id of the account claiming.")
    return {"published_by": int(admin_id)}


def _assert(request: Any, obj: Any, *, rule, what: str, verb: str = "remove") -> None:
    """Refuse the request unless the rule allows it.

    Raises the same 403 the decorator would have raised, so the caller sees one
    answer whether the permission or the ownership was what stopped them.

    `verb` because the same rule now guards two different acts. Every caller
    here was about removing something until the upload gate started using it,
    and an uploader adding a file to somebody else's game was told they may not
    REMOVE it - an answer to a question nobody had asked, which leaves them no
    idea what was actually refused.
    """
    user = getattr(request.state, "user", None)
    scopes = getattr(request.state, "scopes", set())
    if not rule(scopes, getattr(user, "id", None), obj):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Only an administrator, or the account that added this {what}, "
                   f"may {verb} it.",
        )


def assert_can_delete(request: Any, game: Any) -> None:
    _assert(request, game, rule=can_delete_game, what="game")


def assert_can_delete_rom(request: Any, rom: Any) -> None:
    _assert(request, rom, rule=can_delete_rom, what="ROM")


def assert_can_touch_download(request: Any, job: Any) -> None:
    _assert(request, job, rule=can_touch_download, what="download")


def assert_can_upload_into(request: Any, game: Any) -> None:
    _assert(request, game, rule=can_upload_into_game, what="game",
            verb="add files to")


def assert_can_delete_rom_set(request: Any, named: Any, members: Iterable[Any]) -> None:
    """Refuse unless the caller may remove every row this deletion will take."""
    _assert(
        request, named,
        rule=lambda scopes, uid, obj: can_delete_rom_set(scopes, uid, obj, members),
        what="ROM",
    )
