"""Nothing that changes the Games library answers to a plain user's permissions.

This is a net stretched before a fall rather than after one. The uploader is
about to be allowed to delete the games they added, and that cannot be said in
scopes: protected_route requires every scope it is given, with no way to spell
"an admin, or else the owner". The only way to allow the owner is to drop the
admin scope from the route and check ownership inside the handler, and between
those two edits the whole library is open to anyone who can upload.

The existing scope test covers the emulation routes and the saves. It would
watch that change go past without a word. So this exists first, and it fails
the moment a library route becomes reachable by someone holding nothing but
USER_SCOPES.

A route that genuinely has to lower its declared scopes has to say so out loud,
by name, in OWNER_GUARDED below. That list is the whole point: it turns a quiet
edit into a deliberate one, and it says who is expected to have checked what.
"""
from __future__ import annotations

import models.library_file  # noqa: F401 - configures the LibraryGame.files mapper
from endpoints.library.collections_router import router as collections_router
from endpoints.library.libraries_router import router as libraries_router
from endpoints.library.library_router import library_router
from endpoints.library.upload_router import upload_router
from endpoints.torrent.torrent_router import torrent_router
from handler.auth.scopes import UPLOADER_SCOPES, USER_SCOPES, Scope

ROUTERS = (
    library_router,
    libraries_router,
    collections_router,
    upload_router,
    torrent_router,
)

# Anything that reads is safe to reach; these are the verbs that write.
WRITING = {"POST", "PUT", "PATCH", "DELETE"}

# Routes deliberately declaring less than their effect suggests, because the
# handler itself decides. Each entry names what the handler must check. Adding
# to this list is how a change of this shape gets noticed in review.
OWNER_GUARDED: dict[str, str] = {
    "DELETE /library/games/{game_id}":
        "Declares LIBRARY_UPLOAD so that an uploader can undo their own bad "
        "archive, and calls assert_can_delete from handler/library/ownership.py "
        "on the loaded game. That helper is what refuses everyone else, and it "
        "is covered by test_library_ownership.py.",
    "DELETE /api/torrents/downloads/{dl_id}":
        "Declares LIBRARY_UPLOAD because the account that queued a torrent is "
        "the one that needs to be able to stop it - watching a sixty gigabyte "
        "transfer it started by mistake, and having to find an administrator, "
        "was the shape this replaced. Ownership is asked separately, by "
        "_assert_mine against the loaded row, using the same _mine_only rule "
        "the listing uses - so the transfers an account can act on are exactly "
        "the ones it can see. Somebody else's answers 404, not 403. Covered by "
        "test_an_uploader_can_stop_their_own_torrent.py. What this removes is "
        "the transfer, not the game: a finished torrent's files have already "
        "moved into the library and deleting THOSE still goes through the "
        "route above.",
    "DELETE /library/games/{game_id}/my-files":
        "Declares LIBRARY_UPLOAD because the owner decided (2026-09-17) that an "
        "uploader may add files to a game somebody else added and removes them "
        "again itself. The handler takes out ONLY the files charged to the "
        "caller (ownership.charged_to, the sentence the quota sums with), leaves "
        "the game and everybody else's files, and answers 404 for a game the "
        "caller cannot see. Covered by "
        "test_an_uploader_may_add_to_a_game_somebody_else_added.py.",
    "DELETE /library/files/{file_id}":
        "Declares LIBRARY_UPLOAD because the owner decided (2026-09-18) on a bin "
        "beside each file of a game, for administrators and for the account a "
        "file counts against. The handler answers 404 for a game the caller "
        "cannot see and asks ownership.can_remove_file of the loaded file - "
        "LIBRARY_ADMIN, or charged_to(file, game) is the caller, the sentence the "
        "quota sums with. Covered by test_a_single_file_of_a_game_can_be_removed.py.",
}

# POST that does not change the library, and is meant to be within a plain
# user's reach. Written out rather than pattern matched, so that the next one
# has to be argued for.
USER_LEVEL_BY_DESIGN: dict[str, str] = {
    "POST /library/download/{file_id}/token":
        "Mints a short lived token instead of changing anything. An anchor "
        "click cannot carry an Authorization header, so the download is a two "
        "step flow, and the second step is a GET.",
    "POST /api/torrents/seed/{file_id}":
        "Hands the user a .torrent for a file they may already download, and "
        "starts Transmission seeding it so the torrent resolves. Outward "
        "facing, and deliberate: the header above it says User.",
    "POST /api/torrents/seed/game/{game_id}":
        "The same for every file of one game.",
}

# Scopes no uploader holds, which is what "an admin decided this" means here.
# Derived rather than listed, so a new admin only scope counts automatically.
ADMIN_ONLY = {s for s in Scope} - set(UPLOADER_SCOPES)


def writing_routes() -> list[tuple[str, set[Scope]]]:
    """Every library route that changes something, as ("VERB /path", scopes)."""
    out = []
    for router in ROUTERS:
        for route in router.routes:
            verbs = route.methods - {"HEAD", "OPTIONS"}
            if not (verbs & WRITING):
                continue
            scopes = set(getattr(route.endpoint, "required_scopes", ()))
            out.append((f"{'/'.join(sorted(verbs))} {route.path}", scopes))
    return out


def reachable_by(held: set[Scope], required: set[Scope]) -> bool:
    """protected_route requires every declared scope, not any of them."""
    return bool(required) and required.issubset(held)


def test_the_routes_were_found():
    """A guard on the guard: an import that quietly produced nothing would make
    every assertion below vacuously true."""
    found = writing_routes()
    assert len(found) > 25, f"znalazlem tylko {len(found)} tras zapisujacych"


def test_no_writing_route_declares_nothing_at_all():
    """An undeclared route is not open to everyone, it is open to anyone logged
    in, which for a self registering instance is close enough to the same."""
    naked = [r for r, s in writing_routes() if not s]
    assert naked == [], f"trasy zapisujace bez zadnego zakresu: {naked}"


def test_a_plain_user_can_reach_nothing_that_writes():
    """The one that matters. USER_SCOPES is what a self registered account gets,
    and it should not be able to change one thing in the library."""
    open_to_users = [
        route for route, scopes in writing_routes()
        if reachable_by(set(USER_SCOPES), scopes)
        and route not in OWNER_GUARDED
        and route not in USER_LEVEL_BY_DESIGN
    ]
    assert open_to_users == [], (
        "zwykly uzytkownik moze zmieniac biblioteke: " + str(open_to_users)
    )


def test_deleting_asks_for_more_than_uploading():
    """Upload lets someone add. Removal is the one that cannot be undone: there
    is no bin, the row goes, the files go, and the download statistics go with
    them. Anything that deletes has to say so with a scope no uploader holds,
    or name itself as owner guarded and answer for the check itself."""
    weak = [
        route for route, scopes in writing_routes()
        if route.startswith("DELETE ")
        and not (scopes & ADMIN_ONLY)
        and route not in OWNER_GUARDED
    ]
    assert weak == [], (
        "kasowanie osiagalne dla uploadera i bez wpisu na liste straznikow: " + str(weak)
    )


def test_the_owner_guarded_list_says_why():
    """An entry with no reason is how a list like this rots into a list of
    exceptions nobody remembers granting."""
    for listing in (OWNER_GUARDED, USER_LEVEL_BY_DESIGN):
        for route, reason in listing.items():
            assert len(reason) > 20, f"{route}: wpis bez wyjasnienia"


def test_the_exception_lists_do_not_name_routes_that_are_gone():
    """A stale exception is worse than none: it silently forgives a route that
    may come back under the same name meaning something else."""
    known = {route for route, _ in writing_routes()}
    for listing, label in ((OWNER_GUARDED, "OWNER_GUARDED"),
                           (USER_LEVEL_BY_DESIGN, "USER_LEVEL_BY_DESIGN")):
        stale = sorted(set(listing) - known)
        assert stale == [], f"{label} wymienia nieistniejace trasy: {stale}"
