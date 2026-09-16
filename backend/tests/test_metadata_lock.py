"""A locked game is the admin's to edit and nobody else's.

Asked for as a padlock in the corner of every Edit Metadata window: open means
editable, closed means not, for every kind of thing that window opens on, a
ROM, a GOG game, something from a plugin catalogue or a torrent alike.

It is a rule about permission, not a guard on the database. That distinction
came from the owner and it is what makes this small. A guard on writes would
have to know about the container start that stamps an animated-cover flag, the
catalogue sync, the reconcile pass, and the GOG table where a GOG game's fields
actually live. A rule about permission asks one question, "is the person doing
this an admin", and every one of those has no person at all, so none of them is
affected and none had to be listed.

That also settles the awkward case by itself: an admin is never refused, so the
lock can never lock the person who holds the key.

The panel's Save button posts to four different routes, not one: the fields,
the libraries the game is on, the collections it is in, and the per-user access
list. The last is already admin only. The other three are all guarded here,
because a lock that left two of the four open would look broken to the one
person who tried it.
"""
from __future__ import annotations

from dataclasses import dataclass

import pytest

from handler.auth.scopes import ADMIN_SCOPES, EDITOR_SCOPES, UPLOADER_SCOPES, USER_SCOPES
from handler.library.metadata_lock import may_edit_metadata


@dataclass
class _Thing:
    """Only the field the rule reads. A ROM and a game both carry it."""
    metadata_locked: bool = False


def test_an_unlocked_game_is_editable_by_anyone_the_route_admitted():
    """The lock adds a refusal; it does not become the only thing that decides.
    Whoever the route let in keeps what the route gave them."""
    for scopes in (ADMIN_SCOPES, UPLOADER_SCOPES, EDITOR_SCOPES):
        assert may_edit_metadata(scopes, _Thing(metadata_locked=False))


def test_a_locked_game_is_the_admins_alone():
    assert may_edit_metadata(ADMIN_SCOPES, _Thing(metadata_locked=True))


@pytest.mark.parametrize("role,scopes", [
    ("uploader", UPLOADER_SCOPES), ("editor", EDITOR_SCOPES), ("user", USER_SCOPES),
])
def test_a_locked_game_refuses_everybody_else(role, scopes):
    assert not may_edit_metadata(scopes, _Thing(metadata_locked=True))


def test_an_admin_who_lost_the_games_permission_is_not_an_admin_here():
    """Permissions are revocable per account, so the scopes the request carries
    are asked, not the role it claims."""
    stripped = {s for s in ADMIN_SCOPES if s.name != "LIBRARY_ADMIN"}
    assert not may_edit_metadata(stripped, _Thing(metadata_locked=True))


def test_a_row_from_before_the_column_existed_is_unlocked():
    """The column arrives on a live database. Anything already there reads as
    NULL until it is written, and NULL has to mean open, or an upgrade would
    silently freeze every game on the server."""
    @dataclass
    class _Old:
        metadata_locked: None = None
    assert may_edit_metadata(EDITOR_SCOPES, _Old())


def test_something_with_no_such_field_is_unlocked():
    """Belt and braces for the routes that hand this whatever they loaded."""
    assert may_edit_metadata(EDITOR_SCOPES, object())
