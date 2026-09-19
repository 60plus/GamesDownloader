"""Uploading a second file for a game that is already there.

Reported by the owner: "uploadowalem przez ui gre Ion Fury. wyslala sie ok.
nastepnie wyslalem dlc do tej gry. Podalem ten sam tytul, zmienilem File type na
DLC. i ono uploadowalo sie jako osobna pozycja a nie dlc wewnatrz gry".

>>> MEASURED ON HIS OWN INSTALL BEFORE READING ANY CODE. Two rows, fifteen
seconds apart:

    id=129  'Ion Fury'  slug='ion-fury'    -> Ion Fury/windows/setup_ion_fury...exe   game
    id=130  'Ion Fury'  slug='ion-fury-1'  -> Ion Fury/dlc/setup_..._aftershock.exe   dlc

THE FILE WENT TO THE RIGHT PLACE. Both are under one `Ion Fury/` folder, the DLC
in its own `dlc/` subfolder - exactly the layout he described wanting. The
damage is entirely in the database: a second library entry where the file should
have joined the first.

>>> AND THERE WAS NO OTHER DOOR. `uploadFile(gameId, ...)` - the call that adds a
file to an existing game - is invoked from exactly four places in the whole
interface, and all four are the upload dialog, which begins by CREATING a game:

    const game = await libActions.createGame({ title, library })
    await libActions.uploadFile(game.id, file, { fileType })

`POST /library/games` always makes a new row and appends `-1`, `-2` to the slug
when one is taken. So the same title always produced a second entry, for any
file type, and nothing anywhere let him add a file to a game he already had. He
did not click the wrong thing; there was no right thing to click.

>>> NOTHING IS AT RISK, and that was worth checking before proposing anything:
deleting a game removes only the files recorded against it and prunes
directories with `os.rmdir`, which refuses a directory that is not empty. So
deleting either Ion Fury leaves the other one's file where it is.

THE OWNER CHOSE: ask on a collision, and give the game's own page a way to add a
file. This file covers the first half - the dialog. Silent merging was offered
and refused, and rightly: two genuinely different games can share a title, and
unpicking a merge afterwards is hand work in the database.
"""

from __future__ import annotations

import io
import json
import pathlib
import re

import pytest

BACKEND = pathlib.Path(__file__).resolve().parent.parent
FRONTEND = BACKEND.parent / "frontend"
THEMES = BACKEND.parent.parent

CORE_DIALOGS = [
    FRONTEND / "src" / "layouts" / "ClassicLayout.vue",
    FRONTEND / "src" / "views" / "games" / "GamesLibrary.vue",
]
THEME_DIALOGS = [
    THEMES / "vapor_build" / "gd3-vapor" / "VaporUploadDialog.vue",
    THEMES / "nh_build" / "neon-horizon" / "NeonHorizonLibrary.vue",
]


def _read(path: pathlib.Path) -> str:
    if not path.is_file():
        pytest.skip(f"{path.name} not present here")
    return io.open(path, encoding="utf-8").read()


# ── The rule lives in one place ──────────────────────────────────────────────

def test_the_question_is_asked_in_one_shared_place():
    """Four dialogs need this answer. Four copies of "is this title taken" is
    four chances to disagree, and the themes ship separately, so a copy inside
    one of them cannot be corrected with the core."""
    lib = _read(FRONTEND / "src" / "lib" / "libraryActions.ts")
    assert "export async function findGameByTitle" in lib, (
        "brak wspolnej funkcji pytajacej, czy gra o tym tytule juz jest na polce"
    )

    at = lib.index("export async function findGameByTitle")
    fn = lib[at:lib.index("\n}", at)]
    assert "/library/games" in fn, "funkcja nie pyta serwera"

    # >>> BOTH OF THESE WERE LETTER-MATCHES AND BOTH MUTATIONS WALKED THROUGH.
    # "library" survives in the SIGNATURE (`library?: string | null`) after the
    # parameter is dropped from the request, and `.toLowerCase()` survives on
    # the line that computes `wanted` after the comparison stops using it. They
    # ask about the request and about the comparison now.
    at_params = fn.index("params:")
    params = fn[at_params:fn.index("}", at_params)]
    assert "library" in params, (
        "zapytanie nie jest zawezone do polki, wiec gra z innej biblioteki "
        "zablokuje tytul tutaj"
    )

    at_cmp = fn.index("rows.find")
    # To the end of the function, not to the next newline: this is its LAST
    # line, so there is no newline after it and asking for one raised instead
    # of asserting.
    compare = fn[at_cmp:]
    assert "toLowerCase()" in compare and "wanted" in compare, (
        "porownanie tytulow jest wrazliwe na wielkosc liter, wiec `Ion Fury` i "
        "`ion fury` beda dwiema grami: " + compare.strip()
    )


def test_the_themes_can_reach_it_and_are_told_so():
    """They cannot import from `@/lib`; `window.__GD__` is all they have.

    The whole module is handed over as `library: libraryActions`, so the
    function is reachable the moment it exists - which is why this asks about
    the DOCUMENTED surface instead. That comment block is the only place a theme
    author learns what they may call, and a call nobody knows about is a call
    nobody makes.
    """
    main = _read(FRONTEND / "src" / "main.ts")
    assert "library: libraryActions" in main, (
        "motywy nie dostaja juz tego obiektu - ten test bada cos innego"
    )

    # >>> THIS IS THE ASSERTION THAT WAS MISSING, AND IT COST THE OWNER A BROKEN
    # UPLOAD. `libraryActions.ts` ends in a HAND-WRITTEN object listing every
    # function a theme may call, and `export async function ...` does not put
    # anything in it. The core screens import the module as a namespace and saw
    # the new function; Vapor calls `__GD__.library.findGameByTitle`, got
    # `undefined`, and threw before a single request left the browser - the
    # access log showed no `?search=` and no POST at all, only "Upload failed".
    #
    # The old version of this test asked whether the DOC COMMENT mentioned the
    # name. It did. Documentation is not an export.
    lib = _read(FRONTEND / "src" / "lib" / "libraryActions.ts")
    at = lib.index("const libraryActions = {")
    exported = lib[at:lib.index("}", at)]
    assert "findGameByTitle" in exported, (
        "funkcja nie jest w obiekcie oddawanym motywom - w Modern i Classic "
        "zadziala, a w Vaporze i NH rzuci `undefined is not a function`"
    )

    at_doc = main.index("Unified, library-aware")
    block = main[at_doc:main.index("library: libraryActions", at_doc)]
    assert "findGameByTitle" in block, (
        "spis wolan dla motywow nie wymienia tej funkcji, wiec autor motywu jej "
        "nie znajdzie i zostanie przy tworzeniu duplikatow"
    )


def test_nothing_a_theme_may_call_is_only_a_named_export():
    """The general shape of the same trap, so the next one is caught too.

    Anything the core screens reach through `libActions.<name>` is something a
    theme will sooner or later reach through `__GD__.library.<name>` - and that
    only works if it is in the hand-written object at the bottom of the module.
    """
    lib = _read(FRONTEND / "src" / "lib" / "libraryActions.ts")
    at = lib.index("const libraryActions = {")
    exported = lib[at:lib.index("}", at)]

    import re
    published = set(re.findall(r"^export async function (\w+)", lib, re.M))
    published |= set(re.findall(r"^export function (\w+)", lib, re.M))

    #: Deliberately internal, or listed under a different name in the object.
    RENAMED = {"packageGame": "package", "packablePlatforms": "packable"}

    missing = sorted(
        name for name in published
        if name not in exported and RENAMED.get(name, name) not in exported
    )
    assert not missing, (
        "te funkcje sa wyeksportowane, ale nie ma ich w obiekcie dla motywow, "
        "wiec w Vaporze i NH rzuca `undefined is not a function`: %s" % missing
    )


# ── Every dialog asks before it creates ──────────────────────────────────────

# SINCE 2026-09-17 THE QUESTION HAS THREE ANSWERS AND ONE HOME. The owner asked
# for it always to be asked, and for a separate entry to be one of the answers
# (test_the_same_title_asks_join_separate_or_cancel). The finding, the asking and
# the creating moved into `chooseUploadTarget` in the core, so the four dialogs
# below are asked only whether they go through it, before anything is created,
# and stop when it answers nothing.

@pytest.mark.parametrize("path", CORE_DIALOGS + THEME_DIALOGS, ids=lambda p: p.name)
def test_a_dialog_looks_before_it_creates(path):
    """Asked per DIALOG. All four had the same two lines, and one of them left
    unchanged is the whole bug still present for whoever uses that skin."""
    body = _read(path)
    assert "chooseUploadTarget(" in body, (
        f"{path.name} nadal tworzy nowa gre bez sprawdzenia, czy taka juz jest"
    )
    # And nothing is created before the question: the one place a new row is
    # made is inside it.
    assert "createGame(" not in body, (
        f"{path.name} tworzy gre sam, obok wspolnego pytania"
    )


@pytest.mark.parametrize("path", CORE_DIALOGS + THEME_DIALOGS, ids=lambda p: p.name)
def test_nothing_is_merged_without_being_asked(path):
    """THE HALF THE OWNER SPECIFICALLY CHOSE. Two different games can share a
    title - a remaster, another platform, another edition - and joining them
    silently is undone by hand in the database. The asking is in the core now;
    a dialog must not join a game it found by itself."""
    body = _read(path)
    assert "findGameByTitle(" not in body, (
        f"{path.name} szuka gry po swojemu i moze ja dopiac bez pytania"
    )
    assert "window.confirm(" not in body and "window.alert(" not in body, (
        f"{path.name} uzywa natywnego okna przegladarki - w tym projekcie zakazane"
    )


@pytest.mark.parametrize("path", CORE_DIALOGS + THEME_DIALOGS, ids=lambda p: p.name)
def test_saying_no_uploads_nothing(path):
    """Answering "cancel" has to leave the shelf exactly as it was, and send no
    file. A dialog that uploads anyway after the question would be worse than one
    that never asked."""
    body = _read(path)
    at = body.index("chooseUploadTarget(")
    branch = body[at:at + 400]
    assert re.search(r"if \(!game\)[^\n]*return", branch), (
        f"{path.name} nie przerywa po anulowaniu, wiec pytanie niczego nie zmienia"
    )


# ── The way round that never has to ask ──────────────────────────────────────

DETAIL = FRONTEND / "src" / "views" / "games" / "GamesGameDetail.vue"
#: Since 1.0.35 the form is one core component, shown on Modern's page and opened
#: as a dialog by the skins that draw their own game page - and it is for an
#: uploader as well as an admin
#: (test_an_uploader_adds_a_file_from_the_games_own_page).
FORM = FRONTEND / "src" / "components" / "games" / "AddFileForm.vue"


def _submit(body: str) -> str:
    at = body.index("async function submit(")
    return body[at:body.index("\n}\n", at)]


def test_a_game_can_be_given_a_file_from_its_own_page():
    """The other half of what the owner asked for, and the half that removes the
    need to type a title at all: the game is the one on screen. A button on the
    page opens the core dialog with this game in it (a form at the foot of the
    page until 2026-09-18, when the owner asked for a button like the others)."""
    assert "openAddFileDialog(" in _read(DETAIL), (
        "strona gry nadal nie ma sposobu na dodanie do niej pliku"
    )
    assert "uploadFile(" in _submit(_read(FORM)), "przycisk nie wysyla pliku"


def test_that_way_can_never_make_a_second_entry():
    """The point of this door. Adding a file from the game's own page has a game
    id in hand, so `createGame` has no business being anywhere near it - and if
    it ever appears, this way round grows the very bug it was built to avoid."""
    fn = _submit(_read(FORM))
    assert "createGame" not in fn, (
        "dodawanie pliku ze strony gry tworzy nowa gre - to jest ta sama usterka, "
        "tylko innymi drzwiami"
    )
    assert "uploadFile(props.gameId" in fn, "plik nie jest celowany w te gre"
    detail = _read(DETAIL)
    opener = detail[detail.index("function openAddFile("):]
    opener = opener[:opener.index("\n}\n")]
    assert "game: { id: game.value.id" in opener, "okno nie dostaje gry, ktora jest na ekranie"


def test_the_picker_is_cleared_after_a_send():
    """A file input keeps the old name, so a second add looks like it is about
    to send the file that already went."""
    fn = _submit(_read(FORM))
    assert "input.value.value = ''" in fn


# ── In every language ────────────────────────────────────────────────────────

KEYS = ["upload.game_exists", "upload.add_to_existing", "detail.add_file"]


@pytest.mark.parametrize("key", KEYS)
def test_every_language_asks_the_question(key):
    en = FRONTEND / "src" / "i18n" / "en.json"
    if not en.is_file():
        pytest.skip("frontend tree not present")
    langs = sorted((FRONTEND / "public" / "i18n").glob("*.json"))
    assert len(langs) == 7
    for path in [en, *langs]:
        d = json.load(io.open(path, encoding="utf-8"))
        assert key in d, f"{path.name}: brak {key}"


def test_the_question_names_the_game():
    """"A game with this title already exists" is a worse question than "Ion
    Fury is already here": the second one lets the reader notice it is not the
    game they meant."""
    en = json.load(io.open(FRONTEND / "src" / "i18n" / "en.json", encoding="utf-8"))
    assert "{title}" in en["upload.game_exists"], (
        "pytanie nie podaje tytulu, wiec czytelnik nie wie, z czym to scala"
    )
