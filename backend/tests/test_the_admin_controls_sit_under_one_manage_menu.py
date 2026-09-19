"""Everything a plain user is not offered sits under one "Manage" menu.

THE OWNER, 2026-09-18, from screenshots of a GOG game in Modern and Neon
Horizon: next to what a user sees (Download, Torrent, Play, Manual), an
administrator's row of buttons was a mess. Decided the same evening:

  * the row keeps what every account sees - Download, Torrent, Play, Manual,
    Show details, a disc's own buttons - and everything else goes under one
    button, "Manage";
  * a menu dropping down under that button, not a window;
  * in groups: metadata, files, publishing, and Delete on its own at the
    foot, in red;
  * an uploader and an editor get the same button with fewer items. Each item
    keeps the role check its button had, so the menu hands nobody anything
    the button did not;
  * Modern and Neon Horizon only (Neon Horizon renders the core's pages).
    Classic and Vapor keep what they have.

These read the source, as the other frontend tests here do.
"""
from __future__ import annotations

import json
import pathlib
import re

import pytest

REPO = pathlib.Path(__file__).resolve().parent.parent.parent
SRC = REPO / "frontend" / "src"
MENU = SRC / "components" / "common" / "ManageMenu.vue"
TYPES = SRC / "lib" / "manageMenu.ts"
GAME = SRC / "views" / "games" / "GamesGameDetail.vue"
ROM = SRC / "views" / "emulation" / "EmulationGameDetail.vue"


def _read(path: pathlib.Path) -> str:
    if not path.is_file():
        pytest.skip(f"{path.name} nie jest obecny w tym drzewie")
    return path.read_text(encoding="utf-8")


def _template(source: str) -> str:
    return source[:source.index("<script")]


def _item(source: str, handler: str) -> str:
    """The menu item that runs this handler, from its opening brace to its
    closing one. Items hold no nested braces, so the nearest pair is the item."""
    at = source.index(f"run: {handler}")
    start = source.rindex("{", 0, at)
    return source[start:source.index("}", at) + 1]


def _shown_when(item: str) -> str:
    match = re.search(r"show:\s*([^,]+),", item)
    assert match, f"pozycja nie mowi, komu ja pokazac: {item}"
    return match.group(1)


# ── The menu ─────────────────────────────────────────────────────────────────

def test_the_menu_shows_only_what_the_account_is_offered_and_nothing_when_that_is_nothing():
    menu = _read(MENU)
    assert re.search(r"\.filter\(\s*i\s*=>\s*i\.show\s*\)", menu), "menu pokazuje pozycje bez sprawdzenia roli"
    assert re.search(r'<div v-if="visible\.length"', menu), (
        "zwykly uzytkownik zobaczylby pusty przycisk Manage"
    )


def test_the_menu_is_a_menu_to_a_keyboard_and_a_screen_reader():
    menu = _read(MENU)
    assert 'aria-haspopup="menu"' in menu and ':aria-expanded="open"' in menu
    assert 'role="menu"' in menu and 'role="menuitem"' in menu
    for key in ("'Escape'", "'ArrowDown'", "'ArrowUp'", "'Tab'"):
        assert key in menu, f"menu nie obsluguje klawisza {key}"
    # A click anywhere else closes it; the list lives in <body> so that no
    # clipped ancestor can cut it short, and so has to be checked on its own.
    assert '<Teleport to="body">' in menu
    assert "addEventListener('mousedown'" in menu and "popEl.value?.contains(" in menu


def test_opening_the_menu_puts_the_keyboard_on_its_first_item():
    """The list is first drawn out of sight, to be measured, and an element out
    of sight cannot take focus: moving the focus before the list was drawn in
    its place left it on the button, and the arrow keys did nothing (found on
    85 the day it went in)."""
    menu = _read(MENU)
    fn = menu[menu.index("async function openMenu("):]
    fn = fn[:fn.index("\n}\n")]
    placed = fn.index("reposition()")
    assert "await nextTick()" in fn[placed:fn.index("focusItem(")], (
        "fokus idzie na liste, zanim zostala narysowana na swoim miejscu"
    )


def test_the_groups_come_in_one_order_with_delete_last_and_set_apart():
    types = _read(TYPES)
    assert re.search(
        r"MANAGE_GROUPS[^=]*=\s*\[\s*'metadata',\s*'files',\s*'publishing',\s*'danger'\s*\]", types
    )
    menu = _read(MENU)
    assert 'role="separator"' in menu, "Delete nie jest oddzielone od reszty"
    assert "mm-item--danger" in menu


def test_the_button_says_when_something_behind_it_is_still_running():
    """A scrape or a conversion runs on after the menu is closed. The spinner
    that used to turn on its own button has to show somewhere."""
    menu = _read(MENU)
    assert re.search(r"anyBusy\s*=\s*computed\(\(\)\s*=>\s*visible\.value\.some\(i\s*=>\s*i\.busy\)", menu)
    trigger = menu[menu.index('aria-haspopup="menu"'):]
    trigger = trigger[:trigger.index("</button>")]
    assert 'v-if="anyBusy"' in trigger


def test_an_item_closes_the_menu_before_it_runs():
    """Most items open a question (gdConfirm) or a panel of their own; the menu
    must not sit on top of it."""
    menu = _read(MENU)
    fn = menu[menu.index("function choose("):]
    fn = fn[:fn.index("\n}\n")]
    assert fn.index("open.value = false") < fn.index("item.run()")
    # And the keyboard goes back to the button, not to <body>: the list lives
    # at the end of the page, so a focus left there is lost (1.0.36 audit).
    assert fn.index("triggerEl.value?.focus()") < fn.index("item.run()")


def test_tab_out_of_the_menu_lands_on_its_button():
    menu = _read(MENU)
    fn = menu[menu.index("function onMenuKey("):]
    fn = fn[:fn.index("\n}\n")]
    tab = fn[fn.index("case 'Tab'"):]
    tab = tab[:tab.index("break")]
    assert "preventDefault()" in tab and "close(true)" in tab


def test_the_button_takes_the_themes_look_for_a_secondary_button():
    """Neon Horizon restyles `.gd-btn-ghost`; the trigger carries it too."""
    menu = _read(MENU)
    trigger = menu[menu.rindex("<button", 0, menu.index('aria-haspopup="menu"')):]
    assert "gd-btn-ghost" in trigger[:trigger.index(">")]


# ── The pages ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("page", [GAME, ROM], ids=["game", "rom"])
def test_the_row_keeps_only_what_a_user_sees(page):
    source = _read(page)
    at = source.index('<div class="gd-actions">')
    row = source[at:source.index("</div>", at)]
    for cls in ("gd-btn-ghost", "gd-btn-danger", "gd-btn-unpublish", "gd-btn-publish"):
        assert cls not in row, f"w rzedzie zostal przycisk {cls}"
    assert '<ManageMenu :items="manageItems"' in row
    if page is GAME:
        assert 'class="gd-btn-dl"' in row and 'class="gd-btn-torrent"' in row


GAME_ITEMS = {
    "toggleEditPanel": "canEdit",
    "onScrapeClick": "isAdmin",
    "onClearMetadataClick": "isAdmin",
    "openAddFile": "isUploader",
    "openPackage": "isAdmin",
    "unpublishGame": "isAdmin",
    "republishGame": "isAdmin",
    "claimGame": "isAdmin",
    "deleteGame": "isAdmin",
}
ROM_ITEMS = {
    "openEditPanel": "canEdit",
    "triggerScrape": "canEdit",
    "onClearMetadata": "isAdmin",
    "openAddFile": "canUpload",
    "computeHashes": "isAdmin",
    "writePlaylist": "isAdmin",
    "convertToChd": "isAdmin",
    "claimRom": "isAdmin",
    "onDelete": "isAdmin",
}
CASES = [(GAME, h, g) for h, g in GAME_ITEMS.items()] + [(ROM, h, g) for h, g in ROM_ITEMS.items()]


@pytest.mark.parametrize("page,handler,guard", CASES,
                         ids=[f"{p.stem}-{h}" for p, h, _ in CASES])
def test_each_item_keeps_the_role_check_its_button_had(page, handler, guard):
    source = _read(page)
    shown = _shown_when(_item(source, handler))
    assert guard in shown, f"{handler}: pokazywane gdy {shown!r}, a przycisk mial {guard}"
    if guard == "isAdmin":
        for wider in ("canEdit", "canUpload", "isUploader"):
            assert wider not in shown, f"{handler} wymaga admina, a menu daje go {wider}"


@pytest.mark.parametrize("page,handler,guard", CASES,
                         ids=[f"{p.stem}-{h}" for p, h, _ in CASES])
def test_nothing_the_menu_holds_is_left_on_the_page(page, handler, guard):
    template = _template(_read(page))
    assert f'@click="{handler}"' not in template, f"{handler} nadal stoi na stronie obok menu"


@pytest.mark.parametrize("page", [GAME, ROM], ids=["game", "rom"])
def test_take_over_moved_from_the_owners_name_into_the_menu(page):
    assert 'class="gd-claim"' not in _read(page)


@pytest.mark.parametrize("page,handler", [(GAME, "deleteGame"), (ROM, "onDelete")], ids=["game", "rom"])
def test_delete_is_on_its_own_at_the_foot(page, handler):
    item = _item(_read(page), handler)
    assert "group: 'danger'" in item and "danger: true" in item


def test_the_conditions_that_were_on_the_buttons_came_along():
    """Beyond the role: a button that was only offered when it could do
    something still is only offered then."""
    game = _read(GAME)
    assert "packablePlatforms.value.length" in _shown_when(_item(game, "openPackage"))
    assert "is_active" in _shown_when(_item(game, "unpublishGame"))
    assert "is_active" in _shown_when(_item(game, "republishGame"))
    assert "published_by !== auth.user?.id" in _shown_when(_item(game, "claimGame"))
    assert "disabled: metaLocked.value" in _item(game, "toggleEditPanel")

    rom = _read(ROM)
    assert "has_hashes === false" in _shown_when(_item(rom, "computeHashes"))
    playlist = _shown_when(_item(rom, "writePlaylist"))
    assert "diskSet.value.length > 1" in playlist and ".playlist" in playlist
    assert "chd_convertible" in _shown_when(_item(rom, "convertToChd"))
    assert "published_by !== auth.user?.id" in _shown_when(_item(rom, "claimRom"))
    assert "disabled: metaLocked.value" in _item(rom, "openEditPanel")


# ── In every language ────────────────────────────────────────────────────────

KEYS = ["manage.button", "manage.group_metadata", "manage.group_files", "manage.group_publishing"]


def test_the_menu_speaks_every_language():
    en = json.loads(_read(SRC / "i18n" / "en.json"))
    for key in KEYS:
        assert en.get(key), f"brak {key} w en.json"
    for path in sorted((REPO / "frontend" / "public" / "i18n").glob("*.json")):
        other = json.loads(path.read_text(encoding="utf-8"))
        for key in KEYS:
            assert other.get(key), f"brak {key} w {path.name}"
