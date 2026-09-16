"""Who may delete a game, when the answer is not a permission alone.

Everything else in the project answers "may this role do this", which the route
decorator settles before the handler runs. This is the first rule that also
asks "is this row yours", and a decorator cannot express it: it requires every
scope it is given, so there is no way to spell "an admin, or else the owner".

So the rule lives here, once, and the routes ask it. The alternative is the
same sentence written out at each call site, which is how handler/library/
visibility.py came to exist: that file's own header describes what happened
when one copy was updated and the other was not.

The uploader is allowed this because of what it is for. They asked for it to
undo their own mistake, a bad archive or a broken upload, without an admin
having to clean up after them. That is also why an admin claiming a game takes
the ability away: after a claim the game is the admin's, and the rule below
says so without needing to know what a claim is.
"""
from __future__ import annotations

from dataclasses import dataclass

import pytest

from handler.auth.scopes import ADMIN_SCOPES, EDITOR_SCOPES, UPLOADER_SCOPES, USER_SCOPES
from handler.library.ownership import can_delete_game


@dataclass
class _Game:
    """Only the two fields the rule reads."""
    id: int = 1
    published_by: int | None = 7


UPLOADER_ID = 7
SOMEONE_ELSE = 8


def test_an_admin_may_delete_anything():
    assert can_delete_game(ADMIN_SCOPES, SOMEONE_ELSE, _Game(published_by=UPLOADER_ID))


def test_an_uploader_may_delete_their_own():
    """The whole point of the change."""
    assert can_delete_game(UPLOADER_SCOPES, UPLOADER_ID, _Game(published_by=UPLOADER_ID))


def test_an_uploader_may_not_delete_someone_elses():
    assert not can_delete_game(UPLOADER_SCOPES, UPLOADER_ID, _Game(published_by=SOMEONE_ELSE))


def test_an_uploader_may_not_delete_a_game_with_no_owner():
    """Games registered from a torrent are recorded with no owner at all. Read
    as "not mine" rather than "anyone's", or the first uploader to look would
    inherit every one of them."""
    assert not can_delete_game(UPLOADER_SCOPES, UPLOADER_ID, _Game(published_by=None))


def test_an_uploader_may_not_delete_after_an_admin_claims_it():
    """A claim writes the admin as the owner, and that is the entire mechanism:
    the rule needs no notion of claiming."""
    claimed = _Game(published_by=99)
    assert not can_delete_game(UPLOADER_SCOPES, UPLOADER_ID, claimed)


def test_an_editor_may_not_delete_even_their_own():
    """An editor cannot upload, so a game recorded as theirs did not get there
    by uploading, and deleting is not among what that role is for."""
    assert not can_delete_game(EDITOR_SCOPES, UPLOADER_ID, _Game(published_by=UPLOADER_ID))


def test_a_plain_user_may_not_delete_anything():
    assert not can_delete_game(USER_SCOPES, UPLOADER_ID, _Game(published_by=UPLOADER_ID))


def test_the_rule_survives_a_permission_being_revoked():
    """Permissions can be taken away per account, not only granted. An admin
    with the Games library switched off holds no LIBRARY_ADMIN and must be
    refused, or the checkbox means nothing here."""
    stripped = {s for s in ADMIN_SCOPES
                if s.name not in {"LIBRARY_ADMIN", "LIBRARY_UPLOAD"}}
    assert not can_delete_game(stripped, UPLOADER_ID, _Game(published_by=UPLOADER_ID))


@pytest.mark.parametrize("owner", [0, None])
def test_a_falsy_owner_is_not_treated_as_a_match(owner):
    """user id 0 and a missing owner both read as false in a careless check."""
    assert not can_delete_game(UPLOADER_SCOPES, 0, _Game(published_by=owner))


# ── The same rule, for a ROM ─────────────────────────────────────────────────
#
# Extended on the owner's word: "tak. konsystencja." A ROM now has an owner and
# counts against the same quota, so the account that fetched one can clear it up
# the same way it can clear up a game it uploaded. The rule is not copied - the
# only thing that differs is which permission means "administrator" in that
# corner of the API, so it is a parameter rather than a second function.
#
# Where the button lives follows the same precedent too. Even for a game, the
# delete on the detail page is admin-only; an uploader removes their own things
# from the uploads panel. So nothing is added to a detail page here.

import io as _io
import pathlib as _pathlib

from handler.library.ownership import can_delete_rom

_BACKEND = _pathlib.Path(__file__).resolve().parent.parent


@dataclass
class _Rom:
    """Only the field the rule reads. A ROM found by the disk scanner has none."""
    id: int = 1
    published_by: int | None = 7


def test_an_admin_may_delete_any_rom():
    assert can_delete_rom(ADMIN_SCOPES, SOMEONE_ELSE, _Rom(published_by=UPLOADER_ID))


def test_an_uploader_may_delete_a_rom_they_fetched():
    assert can_delete_rom(UPLOADER_SCOPES, UPLOADER_ID, _Rom(published_by=UPLOADER_ID))


def test_an_uploader_may_not_delete_someone_elses_rom():
    assert not can_delete_rom(UPLOADER_SCOPES, UPLOADER_ID, _Rom(published_by=SOMEONE_ELSE))


def test_an_uploader_may_not_delete_a_rom_nobody_fetched():
    """Almost every ROM on a real install: found on the disk by a scan, owned by
    nobody. Reading that as "not mine" is what stops the first uploader who
    looks from inheriting the whole library."""
    assert not can_delete_rom(UPLOADER_SCOPES, UPLOADER_ID, _Rom(published_by=None))


def test_an_editor_may_not_delete_a_rom():
    """An editor edits what is here. Removing it is not editing, and an editor
    never fetched anything to clear up."""
    assert not can_delete_rom(EDITOR_SCOPES, UPLOADER_ID, _Rom(published_by=UPLOADER_ID))


def test_a_plain_account_may_not_delete_a_rom():
    assert not can_delete_rom(USER_SCOPES, UPLOADER_ID, _Rom(published_by=UPLOADER_ID))


def test_the_route_declares_the_weaker_permission_and_asks_in_the_handler():
    """`protected_route` requires every scope it is given, so "an admin, or else
    the owner" cannot be spelled in the decorator. The declaration and the line
    that completes it belong together, and this is the pair."""
    source = _io.open(_BACKEND / "endpoints" / "roms" / "roms_router.py", encoding="utf-8").read()
    start = source.index('@protected_route(router.delete, "/{rom_id}"')
    body = source[start:source.index("\n@", start)]
    assert "ROMS_WRITE" not in body.split("\n")[0], (
        "trasa nadal wymaga admina, wiec uploader nie usunie wlasnego ROM-u"
    )
    # The set-wide form, because that is what the route deletes. The narrower
    # assert_can_delete_rom asked about one row and took the whole disc set with
    # it; test_deleting_a_set_asks_about_every_disc.py drives the behaviour.
    assert "assert_can_delete_rom_set" in body, "trasa nie pyta o wlasnosc calego kompletu"
