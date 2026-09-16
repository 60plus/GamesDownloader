"""A locked game is the admin's to edit and nobody else's.

A padlock in the corner of every Edit Metadata window: open means editable,
closed means not, for every kind of thing that window opens on, a ROM, a GOG
game, something from a plugin catalogue or a torrent alike.

It is a rule about permission, not a guard on the database, and that is what
keeps it small. A guard on writes would have to know about the container start
that stamps an animated-cover flag, the catalogue sync, the reconcile pass, and
the separate table where a GOG game's fields actually live. This asks one
question, "is the person doing this an admin", and none of those has a person
at all, so none is affected and none had to be listed.

It also settles the awkward case by itself: an admin is never refused, so the
lock can never lock out the only person who can undo it.
"""

from __future__ import annotations

from typing import Any, Iterable

from fastapi import HTTPException, status

from handler.auth.scopes import Scope


def is_locked(obj: Any) -> bool:
    """Whether this row is closed to everyone but an admin.

    Anything but a true reads as open. The column arrives on a live database
    and every row already there answers NULL until it is written, so treating
    NULL as locked would freeze the whole library on upgrade.
    """
    return getattr(obj, "metadata_locked", False) is True


def may_edit_metadata(scopes: Iterable[Scope], obj: Any) -> bool:
    """Whether this caller may change this row's metadata.

    The scopes the request actually carries, not the role it claims: an account
    can have the Games permission revoked individually, and then it is not an
    admin for this purpose however it is labelled.
    """
    if not is_locked(obj):
        return True
    return Scope.LIBRARY_ADMIN in set(scopes)


def assert_unlocked(request: Any, obj: Any) -> None:
    """Refuse the request unless `may_edit_metadata` allows it."""
    if may_edit_metadata(getattr(request.state, "scopes", set()), obj):
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="This entry is locked. Only an administrator can change it, "
               "or unlock it from the metadata editor.",
    )
