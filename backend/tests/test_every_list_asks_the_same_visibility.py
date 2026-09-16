"""Whatever hands out games has to ask who is looking.

`visibility.py` says so in its own header: build a `Visibility` once per request
and ask it about a game, nothing else should be deciding this. The listing, the
single-game route, the file list and the download ticket all do.

Six other routes did not. They filtered the per-game deny list - which is real
and works - and never asked the question above it: whether the LIBRARY a game
sits in is hidden from this account, or switched off entirely. The owner's rule
is that a disabled library is closed even to an administrator, and these routes
were the way round it:

  GET  /home/storefront            the whole front page, built from three queries
  GET  /library/popular            the most-downloaded rail
  PATCH /library/games/{id}        reads back the game AND its file list; sending
                                   an empty body is a pure read for an editor
  GET  /collections                every collection in every container
  GET  /collections?library=slug   the same, narrowed by container kind only
  GET  /libraries/membership/{id}  which shelves a game is on

The storefront is not drawn by the core frontend - Vapor and NEON HORIZON reach
for it - but the route is registered and answers any logged-in account, and
`GET /collections` IS in the core: stores/collections.ts asks for it on load.
"""

from __future__ import annotations

import io
import pathlib

BACKEND = pathlib.Path(__file__).resolve().parent.parent

# (file, function, what it hands out)
ROUTES = [
    ("endpoints/library/home_router.py", "async def storefront(", "strona glowna"),
    ("endpoints/library/library_router.py", "async def popular_library_games(", "szyna popularnych"),
    ("endpoints/library/library_router.py", "async def update_library_game(", "PATCH gry"),
    ("endpoints/library/collections_router.py", "async def list_collections(", "kolekcje"),
    ("endpoints/library/libraries_router.py", "async def get_game_membership(", "przynaleznosc gry"),
    # Added after the first round of this fix left the WRITE beside the read
    # with nothing: a caller refused the answer could still send the change, and
    # an empty body forced the game back into the default library and deleted
    # every membership it had. A list of routes that hand games OUT was the
    # wrong shape - what matters is every route that answers about a game in a
    # library, whichever direction it moves.
    ("endpoints/library/libraries_router.py", "async def set_game_membership(", "zapis przynaleznosci"),
    ("endpoints/library/collections_router.py", "async def get_collection(", "strona kolekcji"),
]


def _body(rel: str, name: str) -> str:
    source = io.open(BACKEND / rel, encoding="utf-8").read()
    at = source.index(name)
    nxt = source.find("\n@", at)
    return source[at:nxt if nxt != -1 else len(source)]


def test_the_module_still_says_it_is_the_only_place_this_is_decided():
    """The premise. These assertions are only worth making while that holds."""
    header = io.open(BACKEND / "handler" / "library" / "visibility.py",
                     encoding="utf-8").read()[:2000]
    # Whitespace-normalised: the sentence wraps across two lines in the file.
    assert "Nothing else should be deciding this" in " ".join(header.split())


def test_every_route_that_hands_out_games_asks():
    missing = []
    for rel, name, what in ROUTES:
        body = _body(rel, name)
        # The helpers count too. Two routes ask this through one shared
        # function now, which is the point - reading the rule inline in each was
        # how the read and the write came to differ.
        if not any(k in body for k in
                   ("visibility_for", "_check_user_can_access", "user_can_access",
                    "_assert_may_see_game", "_may_see_container")):
            missing.append(f"{what} ({name.strip('async def (')})")
    assert not missing, (
        "trasy oddaja gry bez pytania o widocznosc BIBLIOTEKI - regula "
        "'wylaczone to wylaczone' jest tam do obejscia: " + "; ".join(missing)
    )


def test_the_deny_list_is_still_applied_as_well():
    """The filtering that was already there and is right. Losing it while adding
    the library check would trade one hole for another."""
    for rel, name in (("endpoints/library/home_router.py", "async def storefront("),
                      ("endpoints/library/library_router.py",
                       "async def popular_library_games(")):
        assert "get_denied_game_ids_for_user" in _body(rel, name), (
            f"{name} przestala filtrowac liste zakazow per gra"
        )


def test_the_collections_route_asks_even_without_a_container():
    """The variant the core frontend uses. `GET /collections` with no query
    string went through `get_all()` and returned every collection there is."""
    body = _body("endpoints/library/collections_router.py", "async def list_collections(")
    # The branch with no slug, which is the call stores/collections.ts makes on
    # load. It has to ask as well - it used to go through `get_all()` and hand
    # back every collection in every container.
    at = body.index("else:")
    plain = body[at:]
    assert "user_can_access" in plain or "visibility_for" in plain, (
        "wariant bez parametru omija sprawdzenie"
    )


def test_the_core_frontend_really_calls_it_without_a_container():
    """Cited in the docstring above, so it is worth pinning rather than
    trusting: if this ever stops being true the route matters less."""
    store = io.open(BACKEND.parent / "frontend" / "src" / "stores" / "collections.ts",
                    encoding="utf-8").read()
    assert "'/collections'" in store or '"/collections"' in store


# ── A game may not be created into a library the caller cannot see ───────────

def test_creating_a_game_refuses_a_target_it_could_not_show_you():
    """The other direction of the same rule. Naming a disabled library made a
    game whose only membership is one nobody can see - an orphan, and the
    library switch is not a curation tool for hiding your own uploads."""
    body = _body("endpoints/library/library_router.py", "async def create_library_game(")
    assert "user_can_access" in body or "_check_user_can_access" in body, (
        "tworzenie gry pozwala wskazac biblioteke WYLACZONA, wiec gra powstaje "
        "w miejscu, ktorego wolajacy sam by nie zobaczyl"
    )


# ── And the scan reached by slug obeys the same switch ───────────────────────

def test_the_slug_branch_of_the_scan_asks_whether_the_folder_is_scanned():
    """`scan_custom_library` has two branches. The one that takes a slug checked
    only that the library exists, so a shelf whose plugin is switched off - the
    state `is_folder_scanned` exists to describe - was scanned anyway."""
    body = _body("endpoints/library/library_router.py", "async def scan_custom_library(")
    # The SLUG branch, not the count over the whole function: the import line
    # and the other branch's call already make two, so counting passed over the
    # defect. Read the branch that handles `if library:`.
    at = body.index("if library:")
    branch = body[at:body.index("    else:", at)]
    assert "is_folder_scanned" in branch, (
        "galaz slugowa omija `is_folder_scanned`, wiec polka wylaczonej wtyczki "
        "jest skanowana mimo wylaczenia"
    )
