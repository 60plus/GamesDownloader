"""An admin takes a game over, and what that is allowed to change.

The owner asked for this alongside letting an uploader delete their own games:
"admin moze zrobic claim, zdejmie to z quota uploadera wielkosc gry ale straci
on mozliwosc usuniecia gry, zmieni sie published_by". Three effects, and two of
them already happen on their own. The delete rule reads published_by, so the
uploader loses the game the moment it stops being theirs; the quota is a sum
over the games an account owns rather than a stored counter, so the next sum is
simply smaller. Only the third needed writing.

The fourth effect was the one that needed a new column. Asked whether the
uploader disappears, the owner said no: "wpisac oba uploadera i ownera, wtedy
admin moze przejac owner a uploader dalej bedzie wymieniony i zejdzie mu quota".
So who brought a game in and who owns it are two different questions, and a
claim answers only the second. published_by moves; uploaded_by is written once,
when the game arrives, and never again.

That distinction is the whole reason for this file. Everything a claim must not
touch is invisible in a diff that adds a field to a write, which is why the
write is a function returning what it changes and the test below asserts what
is absent from it rather than what is present.
"""
from __future__ import annotations

import io
import pathlib
import re

from dataclasses import dataclass

import pytest

BACKEND = pathlib.Path(__file__).resolve().parent.parent
ROUTER = BACKEND / "endpoints" / "library" / "library_router.py"


def _source(path: pathlib.Path) -> str:
    return io.open(path, encoding="utf-8").read()


@dataclass
class _Game:
    id: int = 1
    published_by: int | None = 7
    uploaded_by: int | None = 7


ADMIN_ID = 2
UPLOADER_ID = 7


# ── What a claim writes ──────────────────────────────────────────────────────

def test_a_claim_moves_the_owner():
    from handler.library.ownership import claim_writes

    assert claim_writes(admin_id=ADMIN_ID)["published_by"] == ADMIN_ID


def test_a_claim_writes_nothing_else():
    """The uploader stays named after a claim, so a claim may not touch the
    field that names them. Asserting on the whole write rather than on one key
    is what makes a later "while we are here" addition fail here."""
    from handler.library.ownership import claim_writes

    assert set(claim_writes(admin_id=ADMIN_ID)) == {"published_by"}


def test_a_claim_needs_somebody_to_claim_for():
    """An admin with no id would blank the owner and hand the game to the next
    uploader who looks, because an unowned game reads as nobody's."""
    from handler.library.ownership import claim_writes

    with pytest.raises(ValueError):
        claim_writes(admin_id=None)


# ── The two effects that fall out of it ──────────────────────────────────────

def test_the_uploader_loses_the_delete_button():
    from handler.auth.scopes import UPLOADER_SCOPES
    from handler.library.ownership import can_delete_game

    game = _Game(published_by=UPLOADER_ID, uploaded_by=UPLOADER_ID)
    assert can_delete_game(UPLOADER_SCOPES, UPLOADER_ID, game)

    for field, value in claimed(game).items():
        setattr(game, field, value)
    assert not can_delete_game(UPLOADER_SCOPES, UPLOADER_ID, game)


def claimed(game) -> dict:
    from handler.library.ownership import claim_writes

    return claim_writes(admin_id=ADMIN_ID)


def test_the_quota_counts_by_owner_not_by_uploader():
    """The sum is what frees the space, so it has to read the field a claim
    moves. If it ever reads uploaded_by instead, a claim stops giving anything
    back and the whole feature is silently pointless."""
    source = _source(BACKEND / "handler" / "library" / "quota.py")
    assert "LibraryGame.published_by == user_id" in source
    assert "uploaded_by" not in source


# ── The route ────────────────────────────────────────────────────────────────

def test_the_route_exists_and_only_an_admin_may_call_it():
    match = re.search(
        r'@protected_route\(\s*library_router\.post,\s*"/games/\{game_id\}/claim",'
        r'\s*scopes=\[([^\]]*)\]',
        _source(ROUTER),
    )
    assert match, "brak trasy POST /games/{game_id}/claim"
    assert "LIBRARY_ADMIN" in match.group(1)


def test_a_whole_shelf_can_be_claimed_at_once():
    """An admin clearing out an uploader is doing one thing to twenty games,
    and twenty confirmations is how you get somebody to stop reading them."""
    match = re.search(
        r'@protected_route\(\s*library_router\.post,\s*"/games/claim",'
        r'\s*scopes=\[([^\]]*)\]',
        _source(ROUTER),
    )
    assert match, "brak trasy zbiorczej POST /games/claim"
    assert "LIBRARY_ADMIN" in match.group(1)


def test_an_admin_can_list_what_one_account_holds():
    """The bulk claim needs something to pick from, and my-uploads answers only
    for the caller. Same permission as the dialog that edits the account, which
    is the screen this list appears on."""
    match = re.search(
        r'@protected_route\(\s*library_router\.get,\s*"/uploads/\{user_id\}",'
        r'\s*scopes=\[([^\]]*)\]',
        _source(ROUTER),
    )
    assert match, "brak trasy GET /uploads/{user_id}"
    assert "USERS_WRITE" in match.group(1)


def test_the_bulk_claim_survives_a_game_that_vanished():
    """It runs against a list drawn a moment earlier. One game deleted in
    between must not cost the other nineteen."""
    source = _source(ROUTER)
    start = source.index('"/games/claim"')
    body = source[start:source.index("\n@", start)]
    assert "missing" in body, "trasa zbiorcza nie liczy brakujacych"
    assert "404" not in body, "trasa zbiorcza przerywa na pierwszej brakujacej grze"


def test_the_claim_does_not_delete_and_recreate():
    """A rebuild would give the game a new id, and every collection, download
    link and save that names the old one would be pointing at nothing."""
    source = _source(ROUTER)
    start = source.index('"/games/{game_id}/claim"')
    body = source[start:source.index("\n@", start)]
    for forbidden in ("delete(", "session.delete", "LibraryGame("):
        assert forbidden not in body, f"claim wykonuje {forbidden}"


# ── The column that remembers who brought it in ──────────────────────────────

def test_the_game_remembers_who_uploaded_it():
    from models.library_game import LibraryGame

    assert "uploaded_by" in LibraryGame.__table__.columns


def test_the_column_is_created_on_an_existing_install():
    """Alembic is kept for form; this is the list that actually runs."""
    source = _source(BACKEND / "main.py")
    assert '"library_games", "uploaded_by"' in source.replace(", \n", ", ")


def test_an_upload_records_the_uploader():
    """Set where the game is created, beside the owner it starts out equal to.
    A game whose uploader was never recorded shows nobody after a claim."""
    source = _source(ROUTER)
    start = source.index('@protected_route(library_router.post, "/games"')
    body = source[start:source.index("\n@protected_route", start + 10)]
    assert "uploaded_by" in body, "POST /games nie zapisuje uploaded_by"


# ── What the page can show ───────────────────────────────────────────────────

def test_the_api_names_both_people():
    """Owner and uploader sit in the same block on the detail page, so the
    answer to "who brought this in" survives an admin taking it over."""
    source = _source(ROUTER)
    assert '"uploader_username"' in source
    assert '"owner_username"' in source


# ── The same, for a ROM ──────────────────────────────────────────────────────
#
# A ROM gained an owner when the quota learned to count one, so an admin needs
# the same way to take it off somebody's total. The rule is already shared; only
# the permission that means "administrator" differs in this corner of the API.

ROMS_ROUTER = BACKEND / "endpoints" / "roms" / "roms_router.py"


def test_a_rom_can_be_taken_over_too():
    match = re.search(
        r'@protected_route\(\s*router\.post,\s*"/\{rom_id\}/claim",'
        r'\s*scopes=\[([^\]]*)\]',
        _source(ROMS_ROUTER),
    )
    assert match, "brak trasy POST /roms/{rom_id}/claim"
    assert "ROMS_WRITE" in match.group(1), "przejmowanie ROM-u nie jest admin-only"


def test_the_rom_claim_writes_the_same_fields():
    """One rule for what a claim changes, so the uploader keeps their name on a
    ROM for the same reason they keep it on a game."""
    source = _source(ROMS_ROUTER)
    start = source.index('"/{rom_id}/claim"')
    body = source[start:source.index("\n@", start)]
    assert "claim_writes" in body, "trasa ma wlasny zapis zamiast wspolnej reguly"


def test_the_rom_page_says_who_owns_it():
    """The detail page cannot draw a row for something the API does not send.
    Reported by the owner from a screenshot: the game page had both names and
    the ROM page had neither."""
    source = _source(ROMS_ROUTER)
    for field in ('"owner_username"', '"uploader_username"',
                  '"published_by"', '"uploaded_by"'):
        assert field in source, f"trasa ROM-u nie zwraca {field}"
