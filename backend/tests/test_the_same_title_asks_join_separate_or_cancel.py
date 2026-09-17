"""Uploading under a title that is already on the shelf is a question with three answers.

THE OWNER DECIDED, 2026-09-17: "zawsze pytac bo uploader doda gre a admin moze
dodac dlc na przyklad" - always ask - and an uploader may join somebody else's
game too (test_an_uploader_may_add_to_a_game_somebody_else_added). The dialog
asked "add this file to it?" and "no" gave up, so two different games with one
title - Doom 1993 and Doom 2016 - could not both be uploaded without retyping
the title (1.0.34 audit, #13). The three answers:

  Add to the existing game   the file joins it - a DLC, an extra, another build;
  Separate entry             a new game with the same title, in its own folder;
  Cancel                     nothing is made and nothing is sent.

ASKED IN ONE PLACE. Four dialogs upload - Modern, Classic, Vapor, NEON HORIZON -
and the themes ship separately, so `chooseUploadTarget` in the core finds the
game, asks, and creates when that is the answer. The themes call it through
`__GD__.library`.

THE THIRD BUTTON is an option on the one confirm dialog rather than a third way
of opening it: a single opener is what keeps one question from swallowing
another (test_one_question_at_a_time).

And "My uploads" learns the other half of the decision: an uploader removes the
files it added to somebody else's game, and the owner deleting a game is told
how many files from other accounts go with it.

These read the source, as the other frontend tests here do: the frontend has no
test runner of its own.
"""
from __future__ import annotations

import io
import json
import pathlib
import re

import pytest

BACKEND = pathlib.Path(__file__).resolve().parent.parent
FRONT = BACKEND.parent / "frontend"
SRC = FRONT / "src"


def _read(rel: str) -> str:
    path = SRC / rel
    if not path.is_file():
        pytest.skip("frontend tree not present")
    return io.open(path, encoding="utf-8").read()


def _block(source: str, start: str) -> str:
    """From `start` to the next top-level function or const."""
    at = source.index(start)
    nxt = re.search(r"\n(export )?(async )?function |\nconst [A-Za-z]+ = |\nonMounted",
                    source[at + len(start):])
    return source[at:at + len(start) + (nxt.start() if nxt else len(source))]


# ── The dialog gets a third button ───────────────────────────────────────────

def test_a_choice_is_a_confirm_with_one_more_answer():
    source = _read("composables/useDialog.ts")
    choose = _block(source, "  async function gdChoose(")
    assert "gdConfirm(" in choose, "wybor otwiera okno po swojemu zamiast przez gdConfirm"
    # The statements, not the words: all three answers are also in the type.
    assert re.search(r"onAlt: \(\) => \{ alt = true \}", choose), "drugi wybor nie jest zapamietany"
    assert re.search(r"if \(ok\) return 'confirm'", choose)
    assert re.search(r"return alt \? 'alt' : 'cancel'", choose), (
        "drugi wybor wraca jako anulowanie"
    )
    assert "return { gdConfirm, gdAlert, gdChoose }" in source


def test_every_open_resets_the_third_button():
    """The state is a singleton: a third button left from one question would sit
    under the next, unrelated one."""
    source = _read("composables/useDialog.ts")
    for opener in ("function gdConfirm(", "function gdAlert("):
        body = source[source.index(opener):]
        body = body[:body.index("\n  }\n")]
        assert "dialogState.altText" in body and "dialogState.onAlt" in body, (
            f"{opener} nie czysci trzeciego przycisku"
        )


def test_the_dialog_draws_the_third_button_only_when_asked():
    source = _read("components/GdDialog.vue")
    assert re.search(r'v-if="dialogState\.type === \'confirm\' && dialogState\.altText"', source)
    assert '@click="choseAlt"' in source
    alt = source[source.index("function choseAlt("):]
    alt = alt[:alt.index("\n}\n")]
    assert "dialogState.onAlt = null" in alt and "cancel()" in alt
    assert alt.index("dialogState.onAlt = null") < alt.index("pick?.()") < alt.index("cancel()"), (
        "przycisk drugiego wyboru nie mowi pytajacemu, ze go wybrano"
    )


# ── One function asks it ─────────────────────────────────────────────────────

def test_the_question_is_asked_in_one_shared_place():
    lib = _read("lib/libraryActions.ts")
    fn = _block(lib, "export async function chooseUploadTarget(")
    assert fn.index("findGameByTitle(") < fn.index("gdChoose("), "pyta, zanim sprawdzi"
    assert 'confirmText: t("upload.add_to_existing")' in fn
    assert 'altText:     t("upload.separate_entry")' in fn
    joined = fn[fn.index("gdChoose("):]
    assert re.search(r'if \(answer === "confirm"\) return existing', joined), (
        "'dodaj do istniejacej' nie oddaje istniejacej gry"
    )
    assert re.search(r'if \(answer !== "alt"\) return null', joined), (
        "anulowanie nie przerywa"
    )
    assert joined.index("return null") < joined.index("createGame("), (
        "osobny wpis tworzony tez po anulowaniu"
    )


def test_the_themes_are_handed_it():
    lib = _read("lib/libraryActions.ts")
    at = lib.index("const libraryActions = {")
    assert re.search(r"^\s*chooseUploadTarget,\s*$", lib[at:lib.index("}", at)], re.M)
    main = _read("main.ts")
    doc = main[main.index("Unified, library-aware"):main.index("library: libraryActions")]
    assert "library.chooseUploadTarget({title, library})" in doc, (
        "spis wolan dla motywow nie mowi, ktora funkcje wola okno wgrywania"
    )


def test_the_helper_for_plugins_asks_the_same_question():
    """`addByUpload` is the other way a theme uploads: find-or-create plus one
    file. It created without asking, which is the bug this whole file is about."""
    lib = _read("lib/libraryActions.ts")
    fn = _block(lib, "export async function addByUpload(")
    assert "chooseUploadTarget(" in fn and "createGame(" not in fn
    assert re.search(r"if \(!game\) return null;", fn)
    assert fn.index("if (!game) return null;") < fn.index("uploadFile("), "plik wyslany mimo anulowania"


CORE_DIALOGS = ["views/games/GamesLibrary.vue", "layouts/ClassicLayout.vue"]


@pytest.mark.parametrize("rel", CORE_DIALOGS)
def test_each_core_dialog_asks_through_it_and_stops_on_cancel(rel):
    source = _read(rel)
    at = source.index("chooseUploadTarget(")
    branch = source[at:at + 400]
    assert re.search(r"if \(!game\) \{ uUploading\.value = false; return \}", branch), (
        f"{rel}: anulowanie pytania nie przerywa wgrywania"
    )
    submit = source[source.rindex("\n", 0, at):]
    submit = submit[:submit.index("uploadFile(")]
    assert "findGameByTitle(" not in submit and "gdConfirm(" not in submit, (
        f"{rel}: okno nadal pyta po swojemu obok wspolnej funkcji"
    )


# ── My uploads ───────────────────────────────────────────────────────────────

def test_an_uploader_takes_its_files_out_of_somebody_elses_game():
    panel = _read("components/MyUploadsPanel.vue")
    fn = _block(panel, "async function removeMine(")
    assert "`/library/games/${g.id}/my-files`" in fn
    assert "gdConfirm(" in fn and "requireTick: true" in fn
    assert fn.index("gdConfirm(") < fn.index("if (!ok) return;") < fn.index("client.delete("), (
        "pliki usuwane przed pytaniem albo mimo odpowiedzi 'nie'"
    )
    assert "load()" in fn


def test_the_bin_on_such_a_row_is_no_longer_locked():
    panel = _read("components/MyUploadsPanel.vue")
    assert "function onBin(" in panel and '@click="onBin(g)"' in panel
    bin_ = _block(panel, "function onBin(")
    assert re.search(r"""g\.kind === ["']game["'] && g\.can_delete === false\) return removeMine\(g\)""", bin_)
    assert "return remove(g)" in bin_
    button = panel[:panel.index('@click="onBin(g)"')]
    button = button[button.rindex("<button"):]
    locked = re.search(r':disabled="([^"]+)"', button)
    assert locked and "g.kind === 'rom' && g.can_delete === false" in locked.group(1), (
        "kosz zablokowany takze dla gry, z ktorej konto moze zabrac swoje pliki"
    )


def test_deleting_a_game_says_how_many_other_accounts_files_go():
    panel = _read("components/MyUploadsPanel.vue")
    detail = _block(panel, "async function removalDetail(")
    assert "others_file_count" in detail and "uploads.delete_others_files" in detail
    assert detail.index("others_file_count") < detail.index('if (g.kind !== "rom")'), (
        "zdanie o cudzych plikach nie trafia do pytania o gre"
    )


# ── Every language ───────────────────────────────────────────────────────────

KEYS = ["upload.separate_entry", "upload.same_title", "upload.game_exists_choice",
        "uploads.remove_mine", "uploads.remove_mine_body", "uploads.delete_others_files"]


@pytest.mark.parametrize("lang", ["en", "de", "es", "fr", "it", "pl", "pt", "ru"])
def test_every_language_can_say_it(lang):
    path = SRC / "i18n" / "en.json" if lang == "en" else FRONT / "public" / "i18n" / f"{lang}.json"
    if not path.is_file():
        pytest.skip("frontend tree not present")
    strings = json.load(io.open(path, encoding="utf-8"))
    for key in KEYS:
        assert strings.get(key), f"{lang}: brak {key}"
    assert "{title}" in strings["upload.game_exists_choice"]
    assert "{name}" in strings["uploads.remove_mine_body"] and "{n}" in strings["uploads.remove_mine_body"]
    assert "{n}" in strings["uploads.delete_others_files"]
