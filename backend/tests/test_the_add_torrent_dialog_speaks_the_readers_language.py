"""The refusal shown while adding a torrent, in the reader's language.

Reported by the owner with a screenshot of the dialog: the quota refusal for an
uploaded .torrent was still English after the tray had been translated. He was
right and the scoping was mine: I had counted this one among "the other 448
elsewhere", when it is the SAME refusal in the SAME flow, only shown earlier.
A .torrent carries its own size so the route answers 413 on the spot; a magnet
cannot be weighed until later, which is why one of them lands in the dialog and
the other in the tray. Splitting them by which screen they happen to reach is
exactly the split he objected to.

THE SECOND MESSAGE IN THIS DIALOG IS FIXED WITH IT, and it earned its place.
"Transmission rejected the torrent" is what he saw after pasting a link that
served a web page instead of a torrent, and he read it as a size problem. The
daemon had said precisely what was wrong - "invalid or corrupt torrent file",
in the log the whole time - and the route threw that away. A refusal that
withholds the reason it was given is worse than no refusal.

THREE DIALOGS DRAW THIS. Checked before writing any of it, because a fix in the
core was invisible to the owner twice already in this release: the core's
GamesLibrary, Vapor's VaporTorrentDialog, and NEON HORIZON's NeonHorizonLibrary
each keep their own copy. The composing lives in one shared function, handed to
the themes through `window.__GD__.utils` the way `describeUpload` already is.

SHAPE, AND WHY IT IS SAFE. `detail` becomes an object carrying a reason name and
its numbers. Every reader that does not understand it - an older theme, a plugin,
somebody with curl - still gets a sentence, because the object carries one.
"""

from __future__ import annotations

import io
import pathlib

import pytest

BACKEND = pathlib.Path(__file__).resolve().parent.parent
#: The frontend sits beside the backend, in the repo AND in the test container -
#: the first version reached a level higher and every frontend check here
#: SKIPPED instead of running, which is worse than failing because nothing says
#: so. Copied from the path the tray tests already use.
FRONTEND = BACKEND.parent / "frontend"
#: The two themes are sibling checkouts, absent from the image and from CI, so
#: those genuinely do skip there.
THEMES = BACKEND.parent.parent


def _src(rel: str) -> str:
    return io.open(BACKEND / rel, encoding="utf-8").read()


# ── The route answers with a reason, not only a sentence ─────────────────────

def test_the_quota_refusal_carries_its_reason_and_figures():
    """The dialog cannot translate a sentence. It can translate a name.

    Asked as "do the words code, size and room appear in this function" first,
    and that was letters again: the code is a positional argument and the figures
    are keywords, so none of those words are written the way the test looked for
    them. It asks about the CALL now. The fifth time this round.
    """
    body = _src("endpoints/torrent/torrent_router.py")
    at = body.index("async def add_torrent_file(")
    assert "_refuse_if_it_does_not_fit(" in body[at:body.index("\n@", at)], (
        "trasa wgrania .torrenta juz nie wazy pliku"
    )
    # The refusal itself lives in the helper both torrent routes share since the
    # address route began weighing what it fetches (1.0.34 audit, finding #18).
    at = body.index("async def _refuse_if_it_does_not_fit(")
    fn = body[at:body.index("\n@", at)]

    assert "_refusal(" in fn, (
        "odmowa za limit oddaje samo zdanie, wiec okno nie ma czego przetlumaczyc"
    )
    assert "size=size" in fn and "room=room" in fn, (
        "odmowa nie podaje liczb osobno, wiec okno musialoby je wydlubywac z tekstu"
    )

    # And the shared shape always carries a sentence, for every reader that does
    # not know the name: an older theme, a plugin, somebody with curl.
    at2 = body.index("def _refusal(")
    assert '"message": message' in body[at2:at2 + 700], (
        "brak zdania awaryjnego - czytelnik, ktory nie zna kodu, zostanie z niczym"
    )


def test_the_daemons_own_reason_is_passed_on():
    """It said "invalid or corrupt torrent file" and we showed "Transmission
    rejected the torrent". The owner read that as a size problem, which is what
    a refusal that hides its reason invites."""
    body = _src("endpoints/torrent/torrent_router.py")
    # Both routes hand the add to one helper since a duplicate can be a leftover
    # worth one more try (test_a_torrent_somebody_already_has_says_where_it_is).
    for marker in ("async def add_torrent_url(", "async def add_torrent_file("):
        at = body.index(marker)
        fn = body[at:body.index("\n@", at)]
        assert "_add_to_the_daemon(" in fn, f"{marker} nie idzie przez wspolne dodanie"
    at = body.index("async def _add_to_the_daemon(")
    fn = body[at:body.index("\n@", at)]
    assert fn.count("_daemon_refusal(why)") == 2, (
        "dodanie (albo jego ponowienie) nie przekazuje dalej powodu, ktory podal demon"
    )
    # The two-value answer has to be unpacked, or there is no reason to pass.
    assert fn.count("info, why = await add()") == 2, "odpowiedz demona gubi powod"


@pytest.mark.asyncio
async def test_the_client_hands_back_what_the_daemon_said():
    """`_rpc` logged the daemon's wording and returned None, so the reason
    existed and was thrown away at the door."""
    from handler.torrent import transmission_handler as TH

    client = TH.TransmissionHandler()

    async def _post(_url, **_k):
        class _R:
            status_code = 200

            @staticmethod
            def json():
                return {"result": "invalid or corrupt torrent file"}
        return _R()

    class _Client:
        def __init__(self, *_a, **_k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_a):
            return False

        post = staticmethod(_post)

    import httpx
    orig, httpx.AsyncClient = httpx.AsyncClient, _Client
    try:
        info, reason = await client.add_torrent_url("magnet:?xt=1", "/tmp", )
    finally:
        httpx.AsyncClient = orig

    assert info is None
    assert reason == "invalid or corrupt torrent file", (
        f"powod od demona zginal po drodze: {reason!r}"
    )


# ── The screen can say it, in every language ─────────────────────────────────

REASONS = [
    "quota_refused", "daemon_refused",
    # Named when adding by address fetches the .torrent itself (1.0.34 audit,
    # finding #18). None carries a figure: what the other end answered is
    # exactly what must not come back to the screen.
    "url_unsupported", "url_blocked", "url_fetch_failed", "url_too_large",
    # The daemon already holds this torrent (test_a_torrent_already_in_
    # transmission_is_not_added_twice.py), and what holds it
    # (test_a_torrent_somebody_already_has_says_where_it_is.py).
    "already_added", "already_downloading", "already_in_library",
]


@pytest.mark.parametrize("reason", REASONS)
def test_every_language_has_a_sentence_for_it(reason):
    import json

    en = FRONTEND / "src" / "i18n" / "en.json"
    if not en.is_file():
        pytest.skip("frontend tree not present")
    langs = sorted((FRONTEND / "public" / "i18n").glob("*.json"))
    for path in [en, *langs]:
        d = json.load(io.open(path, encoding="utf-8"))
        assert f"torrent.add_err_{reason}" in d, f"{path.name}: brak {reason}"


def _codes_the_add_routes_refuse_with() -> set[str]:
    """Every reason name the two add routes, and the helpers they call, can
    answer with - read from the calls, including a name kept in a constant."""
    import re

    body = _src("endpoints/torrent/torrent_router.py")
    codes: set[str] = set()
    for name in ("add_torrent_url", "add_torrent_file", "_fetch_torrent_file",
                 "_refuse_if_it_does_not_fit", "_daemon_refusal", "_answer_a_duplicate",
                 "_add_to_the_daemon"):
        at = body.index(f"def {name}(")
        nxt = re.search(r"\n(@|async def |def )", body[at + 10:])
        fn = body[at:at + 10 + nxt.start()] if nxt else body[at:]
        codes |= set(re.findall(r'_refusal\(\s*"(\w+)"', fn))
        for const in re.findall(r"_refusal\(\*(\w+)\)", fn):
            named = re.search(rf'^{const} = \(\s*"(\w+)"', body, re.M)
            assert named, f"{const} nie zaczyna sie od nazwy powodu"
            codes.add(named.group(1))
    return codes


def test_the_reason_list_here_is_the_routes_own():
    """REASONS above is written by hand. A reason added to a route and not to
    that list would never be checked for its sentences at all."""
    codes = _codes_the_add_routes_refuse_with()
    assert "quota_refused" in codes, "odczyt nazw powodow z trasy nic nie znalazl"
    assert codes <= set(REASONS), (
        f"trasa odmawia z powodem, ktorego ta lista nie zna: {sorted(codes - set(REASONS))}"
    )


def test_the_dialog_composes_every_reason_the_routes_name():
    """A reason with keys in every language and no branch in the dialog still
    reaches the reader as the server's English sentence."""
    lib = FRONTEND / "src" / "lib" / "transferError.ts"
    if not lib.is_file():
        pytest.skip("frontend tree not present")
    body = io.open(lib, encoding="utf-8").read()
    at = body.index("export function describeAddRefusal")
    fn = body[at:body.index("\nexport function", at + 10)]
    missing = sorted(c for c in _codes_the_add_routes_refuse_with()
                     if f"case '{c}':" not in fn)
    assert not missing, f"okno dodawania torrenta nie sklada zdania dla: {missing}"


# ── One function, and all three skins reach it ───────────────────────────────

def test_the_composing_lives_in_one_place():
    lib = FRONTEND / "src" / "lib" / "transferError.ts"
    if not lib.is_file():
        pytest.skip("frontend tree not present")
    body = io.open(lib, encoding="utf-8").read()
    assert "export function describeAddRefusal" in body


def test_the_themes_are_handed_it():
    """They cannot import from `@/lib`; `window.__GD__` is all they have. Same
    door `describeUpload` went through yesterday."""
    main = FRONTEND / "src" / "main.ts"
    if not main.is_file():
        pytest.skip("frontend tree not present")
    body = io.open(main, encoding="utf-8").read()
    at = body.index("utils: {")
    assert "describeAddRefusal" in body[at:at + 1200], (
        "motywy nie dostaja tej funkcji, wiec Vapor i NH zostana przy angielskim"
    )


SKINS = [
    FRONTEND / "src" / "views" / "games" / "GamesLibrary.vue",
    THEMES / "vapor_build" / "gd3-vapor" / "VaporTorrentDialog.vue",
    THEMES / "nh_build" / "neon-horizon" / "NeonHorizonLibrary.vue",
]


@pytest.mark.parametrize("path", SKINS, ids=lambda p: p.name)
def test_each_dialog_composes_rather_than_printing_detail(path):
    """`detail` is now an object. A screen still printing it renders
    "[object Object]" - so this is not only about language."""
    if not path.is_file():
        pytest.skip(f"{path.name} not present here")
    body = io.open(path, encoding="utf-8").read()
    assert "describeAddRefusal" in body, (
        f"{path.name} nadal drukuje `detail` wprost"
    )
