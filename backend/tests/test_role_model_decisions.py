"""Two permissions the owner moved, and the reasons they gave.

Both were found by a sweep comparing every button against the route behind it,
and both turned out to be questions about what the roles are for rather than
mistakes in the wiring. So the answer changed the server, not the button.

Queueing a torrent asked for the admin permission while the button offering it
asked only for the uploader. The owner settled it the other way from the usual
fix: an uploader adds games, and a torrent is a game arriving, which is also
how they described the upload quota, counting a torrent against the person who
brought it in. So the route came down to the uploader rather than the button
going up to the admin. Managing the queue afterwards stays with the admin, and
nothing in the interface asks for it: the browser only ever calls enabled and
the two that add.

Moderating the wishlist went the other way. Accepting and refusing a request
asked for a permission an editor already holds, while the column offering it
was admin only. "Only an admin accepts and moderates wishlists", so the
permission left the editor rather than the column widening. It guards nothing
else, so it could simply move rather than needing a new one.

Moving it meant naming it in the admin set as well. The sets are built on each
other, admin from uploader from editor, so a permission taken out of the editor
disappears from all three, which would have left nobody able to moderate at all.
"""
from __future__ import annotations

import io
import pathlib
import re

from handler.auth.scopes import (
    ADMIN_SCOPES,
    EDITOR_SCOPES,
    UPLOADER_SCOPES,
    USER_SCOPES,
    Scope,
)

ROUTERS = pathlib.Path(__file__).resolve().parent.parent / "endpoints"


def scopes_of(router_file: str, verb: str, path: str) -> set[str]:
    """What one route declares, read off the decorator."""
    source = io.open(ROUTERS / router_file, encoding="utf-8").read()
    pattern = (r'@protected_route\([a-z_]+\.' + verb
               + r',\s*"' + re.escape(path) + r'",\s*scopes=\[([^\]]*)\]')
    match = re.search(pattern, source)
    assert match, f"nie znalazlem trasy {verb.upper()} {path} w {router_file}"
    return {s.strip().split(".")[-1] for s in match.group(1).split(",") if s.strip()}


# ── Adding a torrent is adding a game ────────────────────────────────────────

def test_an_uploader_may_queue_a_torrent():
    for path in ("/download/url", "/download/file"):
        declared = scopes_of("torrent/torrent_router.py", "post", path)
        assert declared == {"LIBRARY_UPLOAD"}, (
            f"{path} deklaruje {declared}, a torrent to gra przynoszona przez uploadera"
        )


def test_acting_on_your_own_transfer_moved_for_the_same_reason_reading_it_did():
    """This one moved too, and its stated reason stopped being true the same
    way the one below it did.

    It read: "acting on a transfer - pausing it, cancelling it - reaches
    everybody's, so it stays where it was". That premise was about the code, not
    about the rule, and the code changed: `_assert_mine` now asks whose transfer
    it is, using the same `_mine_only` the listing uses. Acting reaches exactly
    the transfers the caller can see, which for an uploader is their own and
    nothing else.

    What forced it was the release that made the transfer visible. An uploader
    could suddenly watch a sixty gigabyte transfer they had started by mistake
    and could not stop it. Sharper still where the quota stops one: only an
    administrator could let it go again, so the person who could actually free
    the space could not act on the result.

    Somebody else's still answers 404, not 403 - the same answer the single-row
    read gives, so the reply does not confirm that a transfer with that number
    exists. Measured in test_an_uploader_can_stop_their_own_torrent.py.
    """
    for verb, path in (("post", "/downloads/{dl_id}/pause"),
                       ("post", "/downloads/{dl_id}/resume"),
                       ("post", "/downloads/{dl_id}/verify"),
                       ("delete", "/downloads/{dl_id}")):
        declared = scopes_of("torrent/torrent_router.py", verb, path)
        assert declared == {"LIBRARY_UPLOAD"}, (
            f"{verb.upper()} {path} deklaruje {declared}; konto, ktore zaczelo "
            "transfer, ma moc go zatrzymac"
        )

    # And the ownership question is what replaced the administrative scope. A
    # scope loosened with nothing put in its place is how a gate becomes a hole.
    source = io.open(ROUTERS / "torrent" / "torrent_router.py", encoding="utf-8").read()
    assert source.count("_assert_mine(request, td)") >= 1
    assert "_own_download(request, dl_id)" in source


def test_reading_your_own_transfer_does_not():
    """This one moved, and the reason it was admin-only stopped being true.

    It was listed with "they act on everybody's transfers rather than on one's
    own" - and now the list does act on one's own: a caller without
    LIBRARY_ADMIN is shown the transfers they started and nothing else. The
    reason to move it is that a transfer refused for want of quota writes why
    into `error_msg`, and that column was reachable only through this route. The
    account that was refused could not read it, and the live event does not
    cover the case: the views subscribe inside the submit handler, so a reload
    during a transfer that runs for hours loses it.

    It is the same rule the rest of this model already uses - an uploader may
    see and undo what they brought in - applied to the one thing that was left
    out.
    """
    for verb, path in (("get", "/downloads"), ("get", "/downloads/{dl_id}")):
        declared = scopes_of("torrent/torrent_router.py", verb, path)
        assert declared == {"LIBRARY_UPLOAD"}, (
            f"{path} deklaruje {declared}, a konto, ktore zaczelo transfer, ma "
            "prawo przeczytac, co sie z nim stalo"
        )


# ── Moderating a wishlist is the admin's ─────────────────────────────────────

def test_an_editor_cannot_moderate_the_wishlist():
    assert Scope.REQUESTS_WRITE not in EDITOR_SCOPES
    assert Scope.REQUESTS_WRITE not in UPLOADER_SCOPES
    assert Scope.REQUESTS_WRITE not in USER_SCOPES


def test_an_admin_still_can():
    """The sets are built on each other, so taking a permission out of the
    editor removes it from the admin too unless it is named again."""
    assert Scope.REQUESTS_WRITE in ADMIN_SCOPES


def test_everybody_can_still_ask_for_a_game():
    """Wishing is not moderating. Taking the moderation permission away must
    not take away the reading and the asking that go with an ordinary account."""
    assert Scope.REQUESTS_READ in USER_SCOPES


# ── The ladder still holds ───────────────────────────────────────────────────

def test_each_role_still_contains_the_one_below_it():
    """Every change here edits one rung. This is the ladder itself."""
    assert USER_SCOPES < EDITOR_SCOPES
    assert EDITOR_SCOPES < UPLOADER_SCOPES
    assert UPLOADER_SCOPES < ADMIN_SCOPES


# ── Refusing a torrent before it lands ───────────────────────────────────────

def test_a_torrent_file_is_weighed_before_anything_is_downloaded():
    """A torrent counts against the quota once it has landed, which on its own
    means a transfer larger than the allowance succeeds and then sits over it.
    Asked whether the refusal should come first, the owner said yes.
    """
    source = io.open(ROUTERS / "torrent" / "torrent_router.py", encoding="utf-8").read()
    start = source.index('"/download/file"')
    route = source[start:source.index("\n@", start)]
    # The weighing lives in a helper since the address route began using it too
    # (1.0.34 audit, finding #18). The route has to call it, and before it hands
    # anything to the daemon.
    assert "_refuse_if_it_does_not_fit(" in route, "trasa nie wazy pliku .torrent"
    assert route.index("_refuse_if_it_does_not_fit(") < route.index("transmission_handler."), (
        "plik .torrent trafia do demona, zanim ktokolwiek go zwazy"
    )
    start = source.index("async def _refuse_if_it_does_not_fit(")
    body = source[start:source.index("\n@", start)]
    assert "total_bytes" in body, "trasa nie czyta rozmiaru z pliku .torrent"
    assert "quota.fits" in body, "rozmiar jest czytany, ale z niczym nie porownywany"
    # And it refuses rather than trimming: half a torrent is not a game.
    assert "413" in body or "REQUEST_ENTITY_TOO_LARGE" in body


def test_a_magnet_link_is_deliberately_not_weighed():
    """It carries a hash and nothing else; the sizes arrive from peers minutes
    later. Refusing one up front would be refusing on a guess, so that half
    still counts afterwards - which the owner's own example already describes.
    """
    source = io.open(ROUTERS / "torrent" / "torrent_router.py", encoding="utf-8").read()
    start = source.index('"/download/url"')
    body = source[start:source.index("\n@", start)]
    assert "total_bytes" not in body, "magnet nie ma jak znac swojego rozmiaru"
