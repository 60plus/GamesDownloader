"""Two halves of a gate, one of which was fitted.

MEMBERSHIP. `GET /libraries/membership/{id}` learned to ask whether this account
may be told about this game at all - it names the shelves a game sits on, which
is a fact about a game in a library. The twin that WRITES the same thing was
left with nothing but the metadata lock, which passes anything not explicitly
locked, and locked is not the default.

So an editor refused the read could still send the write. With an empty body it
takes the shortest path through it: no collections wanted, so
`in_default_library` is forced true to avoid orphaning the game, and
`set_memberships(id, [])` removes every membership row it had. One request
moves a game out of a restricted or disabled library into the public Games
library and destroys the record of where it used to be.

COLLECTIONS. The listing learned to ask whether the container shelf may be
shown; the page for one collection did not. A collection's slug comes straight
from its name, the frontend routes on it, and a bookmark is enough - so
switching a collections shelf off hid it from the grid and left every collection
on it answering in full: name, description, artwork, aggregates and the whole
member list.

Both are the same rule the rest of this release states as "switched off is
switched off, for an administrator too".
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from handler.auth.scopes import Scope

ME = 5


def _request(scopes=(Scope.LIBRARY_WRITE, Scope.LIBRARY_READ)):
    return SimpleNamespace(state=SimpleNamespace(
        user=SimpleNamespace(id=ME, username="u"), scopes=set(scopes)))


# ── Writing a game's shelves ─────────────────────────────────────────────────

class _Session:
    def __init__(self, game):
        self.game = game

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    def begin(self):
        return self

    async def get(self, _model, _id):
        return self.game


@pytest.fixture
def membership(monkeypatch):
    from endpoints.library import libraries_router as R

    game = SimpleNamespace(id=412, title="Gra", in_default_library=False,
                           metadata_locked=False, is_active=True)
    written: list = []

    async def _set(game_id, ids):
        written.append((game_id, list(ids)))

    monkeypatch.setattr(R, "async_session_factory", lambda: _Session(game))
    monkeypatch.setattr(R.library_registry_handler, "get_all",
                        _async([SimpleNamespace(id=3, slug="closed", kind="custom_lib")]))
    monkeypatch.setattr(R.library_registry_handler, "set_memberships", _set)
    return R, game, written


def _async(value):
    async def _f(*a, **k):
        return value
    return _f


def _refuse_everything(monkeypatch):
    from handler.library import visibility as V

    monkeypatch.setattr(V, "membership_map", _async({}))
    monkeypatch.setattr(V, "visibility_for",
                        _async(V.Visibility(is_admin=False,
                                            default_library_hidden=True)))


def _allow_everything(monkeypatch):
    from handler.library import visibility as V

    monkeypatch.setattr(V, "membership_map", _async({}))
    monkeypatch.setattr(V, "visibility_for", _async(V.Visibility(is_admin=True)))


@pytest.mark.asyncio
async def test_a_game_i_may_not_see_is_not_a_game_i_may_re_shelve(membership, monkeypatch):
    from fastapi import HTTPException

    R, game, written = membership
    _refuse_everything(monkeypatch)
    body = R.MembershipBody(collections=[], in_default_library=False)

    with pytest.raises(HTTPException) as refused:
        await R.set_game_membership(_request(), 412, body)

    assert refused.value.status_code == 404
    assert written == [], (
        "puste cialo PUT skasowalo przynaleznosci gry, ktorej wolajacy nie ma "
        "prawa nawet zobaczyc"
    )
    assert game.in_default_library is False, (
        "gra wyciagnieta do publicznej biblioteki Games jednym zadaniem"
    )


@pytest.mark.asyncio
async def test_a_game_i_may_see_is_still_mine_to_re_shelve(membership, monkeypatch):
    """The gate must not close the editor's Save. This is what the route is
    for."""
    R, game, written = membership
    _allow_everything(monkeypatch)
    body = R.MembershipBody(collections=["closed"], in_default_library=False)

    out = await R.set_game_membership(_request(), 412, body)

    assert out["ok"] is True
    assert written == [(412, [3])]


def test_both_halves_ask_the_same_question():
    """Read and write, one spelling. They were two, and only one was fitted."""
    import inspect

    from endpoints.library import libraries_router as R

    read = inspect.getsource(R.get_game_membership)
    write = inspect.getsource(R.set_game_membership)
    for body in (read, write):
        assert "_assert_may_see_game(" in body, (
            "trasy czlonkostwa nie pytaja jedna regula, wiec znowu rozjada sie "
            "przy nastepnej zmianie"
        )


# ── Reading one collection ───────────────────────────────────────────────────

@pytest.fixture
def collections(monkeypatch):
    from endpoints.library import collections_router as R

    # Every column `_agg_meta` reads. Inventing the names instead made the route
    # raise AttributeError and the tests fail for a reason unconnected with
    # access.
    coll = SimpleNamespace(
        id=9, slug="klasyki", name="Klasyki", library_id=4,
        description=None, description_short=None, cover_path=None,
        cover_animated=False, hero_path=None, logo_path=None,
        rating=None, hltb_main_s=None, hltb_complete_s=None,
        start_year=None, end_year=None, sort_order=0, created_by=None,
    )
    shelf = SimpleNamespace(id=4, slug="polka", kind="collections")

    monkeypatch.setattr(R.collection_handler, "get_by_slug", _async(coll))
    monkeypatch.setattr(R.collection_handler, "get_members", _async([]))
    monkeypatch.setattr(R.library_registry_handler, "get_all", _async([shelf]))
    return R, coll, shelf


@pytest.mark.asyncio
async def test_a_collection_on_a_shelf_i_cannot_see_is_not_there(collections, monkeypatch):
    from fastapi import HTTPException

    R, _coll, _shelf = collections
    monkeypatch.setattr(R.library_registry_handler, "user_can_access", _async(False))

    with pytest.raises(HTTPException) as refused:
        await R.get_collection(_request(), "klasyki")
    assert refused.value.status_code == 404, (
        "wylaczenie polki kolekcji ukrywa je tylko na siatce - strona kazdej "
        "kolekcji nadal wydaje pelne metadane i liste gier"
    )


@pytest.mark.asyncio
async def test_a_collection_on_a_shelf_i_can_see_still_opens(collections, monkeypatch):
    R, _coll, _shelf = collections
    monkeypatch.setattr(R.library_registry_handler, "user_can_access", _async(True))

    out = await R.get_collection(_request(), "klasyki")
    assert out["slug"] == "klasyki"


@pytest.mark.asyncio
async def test_a_collection_with_no_shelf_at_all_still_opens(collections, monkeypatch):
    """`library_id` is nullable because the column arrived by an ALTER, so
    collections made before it have none - and a collection with no shelf has no
    shelf to be hidden by. The listing already answers this way."""
    R, coll, _shelf = collections
    coll.library_id = None
    monkeypatch.setattr(R.library_registry_handler, "user_can_access", _async(False))

    out = await R.get_collection(_request(), "klasyki")
    assert out["slug"] == "klasyki"
