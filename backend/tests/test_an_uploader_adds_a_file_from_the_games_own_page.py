"""An uploader adds a file to a game from that game's own page, in every skin.

THE OWNER DECIDED, 2026-09-17: "tak dla admina tez" - the "Add file" form on a
game's page, which sat inside the administrator's file management, is for an
uploader too, now that an uploader may add files to any game they can see
(test_an_uploader_may_add_to_a_game_somebody_else_added).

Only Modern had that form, inline in its admin section; NEON HORIZON leaves game
pages to the core, so it had what Modern had. Vapor and Classic draw their own
game pages and had nothing. So the form becomes one core component:

  AddFileForm            the file, the platform, the type, progress and the
                         server's refusal; it only ever uploads into the game it
                         is given, never creates one;
  Modern, Vapor, Classic open it as a dialog, `__GD__.ui.openAddFileDialog` -
                         the same door the metadata editors go through. Modern
                         showed it inline at the foot of the page until the
                         owner asked for a button like the others (2026-09-18),
                         and the same evening that button went into the page's
                         one "Manage" menu with the other editing controls.

These read the source, as the other frontend tests here do.
"""
from __future__ import annotations

import io
import pathlib
import re

import pytest

BACKEND = pathlib.Path(__file__).resolve().parent.parent
SRC = BACKEND.parent / "frontend" / "src"
THEMES = BACKEND.parent.parent


def _read(path: pathlib.Path) -> str:
    if not path.is_file():
        pytest.skip(f"{path.name} not present here")
    return io.open(path, encoding="utf-8").read()


FORM = SRC / "components" / "games" / "AddFileForm.vue"


# ── One form ─────────────────────────────────────────────────────────────────

def test_the_form_uploads_into_the_game_it_is_given_and_nothing_else():
    body = _read(FORM)
    at = body.index("async function submit(")
    fn = body[at:body.index("\n}\n", at)]
    assert "libActions.uploadFile(props.gameId" in fn
    assert "createGame" not in body and "chooseUploadTarget" not in body, (
        "formularz na stronie gry tworzy gre - to jest usterka, ktora strona gry miala omijac"
    )
    assert fn.index("uploadFile(") < fn.index("emit('added')"), "zglasza dodanie przed wyslaniem"


def test_the_form_clears_the_picker_and_shows_the_servers_refusal():
    """A file input keeps the old name, so a second add looks like it is about
    to send the file that already went. And a refusal - somebody else's file
    under that name, no room left - has to reach the person."""
    body = _read(FORM)
    at = body.index("async function submit(")
    fn = body[at:body.index("\n}\n", at)]
    assert "input.value.value = ''" in fn
    assert "error.value = e?.response?.data?.detail" in fn
    assert re.search(r'v-if="error"', body)


# ── Where it is shown ────────────────────────────────────────────────────────

def test_modern_offers_it_to_an_uploader_and_an_admin():
    """THE OWNER, 2026-09-18: a button, the way the ROM pages and Vapor have
    it, rather than a form at the foot of the page - now an item of the page's
    "Manage" menu. It opens the one dialog every skin uses."""
    body = _read(SRC / "views" / "games" / "GamesGameDetail.vue")
    assert "<AddFileForm" not in body, "formularz nadal stoi na dole strony"
    at = body.index("run: openAddFile")
    item = body[body.rindex("{", 0, at):at]
    assert "show: isUploader.value," in item, "pozycja nie jest dla uploadera"
    assert "const isUploader = computed(() => ['admin','uploader']" in body
    fn = body[body.index("function openAddFile("):]
    fn = fn[:fn.index("\n}\n")]
    assert "openAddFileDialog(" in fn and "onAdded: refreshGame" in fn
    assert "submitAddFile" not in body, "stara kopia formularza zostala obok wspolnego"


def test_the_dialog_is_one_door_for_every_skin():
    ui = _read(SRC / "lib" / "pluginUi.ts")
    opener = ui[ui.index("export function openAddFileDialog("):]
    opener = opener[:opener.index("\n}\n")]
    assert "pluginUiState.addFileDialog = { ...req }" in opener, "okna nie da sie otworzyc"
    assert "addFileDialog:" in ui
    host = _read(SRC / "components" / "common" / "PluginUiHost.vue")
    assert re.search(r'<AddFileForm[^>]*:game-id="addFileGame\?\.id"', host)
    assert "onFileAdded" in host
    added = host[host.index("function onFileAdded("):]
    added = added[:added.index("\n}\n")]
    assert "req?.onAdded?.()" in added and "gd-game-updated" in added
    main = _read(SRC / "main.ts")
    ui_block = main[main.index("  ui: {"):]
    ui_block = ui_block[:ui_block.index("\n  },")]
    assert re.search(r"^\s*openAddFileDialog,\s*$", ui_block, re.M)


def test_classic_offers_it_on_a_games_page_to_an_uploader():
    body = _read(SRC / "layouts" / "ClassicGameDetail.vue")
    # An editor may edit metadata and may not upload.
    assert re.search(r"const canUpload = computed\(\(\) =>\s*\['admin', 'uploader'\]\.includes\(", body), (
        "Classic pokazuje dodawanie pliku komus bez prawa wgrywania"
    )
    button = body[:body.index('@click="openAddFile"')]
    button = button[button.rindex("<button"):]
    assert "activeLib === 'games'" in button and "canUpload" in button
    fn = body[body.index("function openAddFile("):]
    fn = fn[:fn.index("\n}\n")]
    assert "openAddFileDialog(" in fn and "loadGame(" in fn


def test_vapor_offers_it_to_an_uploader():
    body = _read(THEMES / "vapor_build" / "gd3-vapor" / "VaporGameDetail.vue")
    assert re.search(r'canUpload = computed\(\(\) => \["admin", "uploader"\]', body)
    button = body[:body.index('@click="openAddFile"')]
    button = button[button.rindex("<button"):]
    assert 'v-if="canUpload' in button
    fn = body[body.index("function openAddFile("):]
    fn = fn[:fn.index("\n}\n")]
    assert "_gd.ui?.openAddFileDialog?.(" in fn and "load()" in fn
