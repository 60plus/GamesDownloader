"""An account holds games AND ROMs, and the two are numbered separately.

`quota.owned_games` deliberately returns one list of both, each row carrying a
`kind`, because somebody looking for something to clear up does not care which
table it lives in. The admin screen dropped that field and posted every ticked
id to `/library/games/claim`, which resolves an id against the LibraryGame
table: ticking ROM 12 took over library game 12 - an unrelated game, quite
possibly somebody else's - and reported success.

Two sides, and both are needed. The screen has to send each kind to the route
that understands it, and the route has to refuse an id the account it was told
about does not hold, so a stale or wrong list cannot move a stranger's game.
"""

from __future__ import annotations

import io
import pathlib
import re
from types import SimpleNamespace

import pytest

_FRONTEND = pathlib.Path(__file__).resolve().parent.parent.parent / "frontend" / "src"
_ADMIN_USERS = _FRONTEND / "views" / "admin" / "AdminUsers.vue"


# ── the route ─────────────────────────────────────────────────────────────────

class _Games:
    def __init__(self, rows):
        self.rows = rows
        self.written = []

    async def get_by_id(self, game_id):
        return self.rows.get(game_id)

    async def update(self, game, writes):
        self.written.append((game.id, writes))
        return game


@pytest.fixture
def route(monkeypatch):
    from endpoints.library import library_router as R

    games = _Games({
        1: SimpleNamespace(id=1, published_by=7),
        2: SimpleNamespace(id=2, published_by=9),
    })
    async def _release(_game_id, _previous_owner):
        # A claim now hands the game's own files over with it, so the account it
        # came from gets its quota back. Not what these tests are about; stubbed
        # because the route asks unconditionally.
        return 0

    monkeypatch.setattr(R._lib, "get_by_id", games.get_by_id)
    monkeypatch.setattr(R._lib, "update", games.update)
    monkeypatch.setattr(R._lib, "release_files_of", _release)
    return R, games


def _request(admin_id=1):
    """The route is decorated, so the scope it declares has to be carried."""
    from handler.auth.scopes import Scope

    return SimpleNamespace(state=SimpleNamespace(
        user=SimpleNamespace(id=admin_id, username="admin"),
        scopes={Scope.LIBRARY_ADMIN},
    ))


@pytest.mark.asyncio
async def test_a_game_the_account_does_not_hold_is_left_alone(route):
    R, games = route
    out = await R.claim_library_games(
        _request(), R.ClaimBody(game_ids=[1, 2], from_user_id=7),
    )
    assert [w[0] for w in games.written] == [1], "przejeto gre nalezaca do kogos innego"
    assert out["claimed"] == 1 and out["skipped"] == 1


@pytest.mark.asyncio
async def test_the_games_that_account_does_hold_still_go_through(route):
    """The other half: a guard that skipped everything would pass the test
    above and break the screen."""
    R, games = route
    out = await R.claim_library_games(
        _request(), R.ClaimBody(game_ids=[1], from_user_id=7),
    )
    assert [w[0] for w in games.written] == [1]
    assert out["claimed"] == 1 and out["skipped"] == 0


@pytest.mark.asyncio
async def test_an_id_that_is_gone_is_counted_not_raised(route):
    """The list is drawn a moment earlier, and one game deleted in between
    should not lose the other nineteen."""
    R, _games = route
    out = await R.claim_library_games(
        _request(), R.ClaimBody(game_ids=[1, 404], from_user_id=7),
    )
    assert out["claimed"] == 1 and out["missing"] == 1


@pytest.mark.asyncio
async def test_a_caller_that_names_no_account_is_not_broken_by_the_guard(route):
    """`from_user_id` is optional so an older client keeps working. When it is
    absent the route behaves as it always did."""
    R, games = route
    out = await R.claim_library_games(_request(), R.ClaimBody(game_ids=[1, 2]))
    assert [w[0] for w in games.written] == [1, 2]
    assert out["claimed"] == 2


# ── the screen ────────────────────────────────────────────────────────────────
#
# There is no JS test runner in this project, so the screen is read. The
# assertions are about what it sends, not about how it is written.

def _source():
    if not _ADMIN_USERS.exists():
        pytest.fail(f"brak {_ADMIN_USERS} - test nie ma czego sprawdzic")
    return io.open(_ADMIN_USERS, encoding="utf-8").read()


def _claim_function():
    source = _source()
    start = source.index("async function claimPicked")
    return source[start:source.index("\nasync function", start + 10)]


def test_the_screen_keeps_the_kind_of_each_row():
    source = _source()
    interface = source[source.index("interface UploadedGame"):]
    interface = interface[:interface.index("}")]
    assert "kind" in interface, (
        "ekran gubi rodzaj wiersza, wiec nie odrozni ROM-u od gry"
    )


def test_the_screen_sends_roms_to_the_rom_route():
    body = _claim_function()
    assert re.search(r"/roms/\$\{[^}]+\}/claim", body), (
        "ROM-y nadal ida do trasy przejmowania gier"
    )


def test_the_screen_no_longer_posts_the_ticked_ids_as_game_ids():
    """The exact line that caused it: `game_ids: [...picked.value]`."""
    body = _claim_function()
    assert "game_ids: [...picked.value]" not in body
    assert "from_user_id" in body, (
        "ekran nie mowi serwerowi, czyja lista to byla, wiec zapora nie zadziala"
    )


def test_a_game_and_a_rom_of_the_same_number_are_different_rows():
    """Both tables number from 1. Keyed by id alone, ticking a game ticked a
    ROM as well, and the checkbox showed it."""
    source = _source()
    assert "function rowKey" in source
    assert ':key="rowKey(g)"' in source
    assert 'picked.has(rowKey(g))' in source


# ── The ROM claim asks the same question ─────────────────────────────────────
#
# The game claim learned to check whose game it was; the ROM claim beside it did
# not. The screen draws one account's things and acts on them a moment later,
# and in between another administrator can claim one. Without the check the
# click takes it from whoever holds it now and reports success.

@pytest.fixture
def rom_claim(monkeypatch):
    from endpoints.roms import roms_router as R

    state = SimpleNamespace(row=SimpleNamespace(id=5, published_by=7), written=[])

    async def _get_by_id(_rom_id):
        return state.row

    async def _set_published_by(rom_id, user_id):
        state.written.append((rom_id, user_id))

    monkeypatch.setattr(R.rom_handler, "get_by_id", _get_by_id)
    monkeypatch.setattr(R.rom_handler, "set_published_by", _set_published_by)
    return R, state


def _admin_request():
    from handler.auth.scopes import Scope
    return SimpleNamespace(state=SimpleNamespace(
        user=SimpleNamespace(id=1, username="admin"), scopes={Scope.ROMS_WRITE},
    ))


@pytest.mark.asyncio
async def test_a_rom_that_moved_since_the_list_was_drawn_is_left_alone(rom_claim):
    R, state = rom_claim
    state.row = SimpleNamespace(id=5, published_by=9)     # somebody else's now

    out = await R.claim_rom(_admin_request(), rom_id=5, from_user_id=7)

    assert out.get("skipped") is True
    assert state.written == [], "przejeto ROM, ktory w miedzyczasie zmienil wlasciciela"


@pytest.mark.asyncio
async def test_a_rom_still_held_by_that_account_is_claimed(rom_claim):
    R, state = rom_claim
    out = await R.claim_rom(_admin_request(), rom_id=5, from_user_id=7)

    assert not out.get("skipped")
    assert state.written == [(5, 1)]


@pytest.mark.asyncio
async def test_claiming_without_naming_an_account_is_unchanged(rom_claim):
    """Optional, so nothing that already calls this route breaks."""
    R, state = rom_claim
    state.row = SimpleNamespace(id=5, published_by=9)
    await R.claim_rom(_admin_request(), rom_id=5)
    assert state.written == [(5, 1)]


def test_the_screen_names_the_account_for_roms_too():
    import io
    import pathlib

    panel = (pathlib.Path(__file__).resolve().parent.parent.parent
             / "frontend" / "src" / "views" / "admin" / "AdminUsers.vue")
    if not panel.exists():
        pytest.fail(f"brak {panel}")
    source = io.open(panel, encoding="utf-8").read()
    at = source.index("async function claimPicked")
    body = source[at:source.index("\nasync function", at + 10)]
    assert "/roms/${id}/claim" in body
    assert body.count("from_user_id") >= 2, (
        "ekran mowi, czyja lista to byla, tylko przy grach"
    )


def test_one_rom_that_will_not_move_does_not_abandon_the_rest():
    """The ROMs are claimed one request at a time, and the loop was a plain
    `for ... await`: the first refusal threw out of it and left every ROM after
    it untouched.

    Every way that request fails is ordinary here. The list is a snapshot of one
    account's things and the screen acts on it a moment later, so a ROM deleted
    in between answers 404; the server also refuses one whose owner changed. An
    administrator selecting thirty and seeing "Could not take these games over"
    has no way to tell that four moved and twenty-six did not, and the re-read
    underneath shows a list that is partly done.

    So each one is asked for on its own, and the ones that would not move are
    counted and named on screen.
    """
    import io
    import pathlib

    panel = (pathlib.Path(__file__).resolve().parent.parent.parent
             / "frontend" / "src" / "views" / "admin" / "AdminUsers.vue")
    source = io.open(panel, encoding="utf-8").read()
    at = source.index("async function claimPicked")
    body = source[at:source.index("\nasync function", at + 10)]

    loop = body.index("for (const id of romIds)")
    rest = body[loop:]
    assert "catch" in rest[:rest.index("picked.value = new Set()")], (
        "petla przejmowania ROM-ow urywa sie na pierwszym bledzie i reszta "
        "zaznaczenia zostaje po cichu nietknieta"
    )
    assert "claim_partial" in body, (
        "czesciowe przejecie konczy sie komunikatem, ktory sugeruje, ze nie "
        "przeszlo nic"
    )


def test_the_screen_counts_a_refusal_that_arrives_as_a_success():
    """Both claim routes answer a stale row with 200 and a count, not an error.

    The games route returns `skipped` and `missing`; the ROM route returns
    `skipped: true`. The screen counted thrown exceptions only, so an
    administrator acting on a list drawn a moment earlier - which is the whole
    reason those counters were added - was told everything had moved.
    """
    import io as _io
    import pathlib

    panel = (pathlib.Path(__file__).resolve().parent.parent.parent
             / "frontend" / "src" / "views" / "admin" / "AdminUsers.vue")
    source = _io.open(panel, encoding="utf-8").read()
    at = source.index("async function claimPicked")
    body = source[at:source.index("\nasync function", at + 10)]

    assert "data?.skipped" in body or "data.skipped" in body, (
        "ekran liczy tylko wyjatki, a serwer odmawia kodem 200 z licznikiem - "
        "czesciowe przejecie melduje sie jako pelny sukces"
    )
    at_games = body.index("/library/games/claim")
    assert "skipped" in body[at_games:at_games + 400], (
        "polowa gier nie czyta licznikow z odpowiedzi"
    )
