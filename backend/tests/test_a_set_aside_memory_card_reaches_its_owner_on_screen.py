"""A set-aside memory card has to reach its owner on screen, in every layout.

The server half sets the card aside and tells the owner over the socket
(test_a_rename_does_not_cost_anybody_their_saves, test_two_memory_cards_are_the_
owners_to_choose_between). This is the half a person sees:

  a badge on the avatar     every layout draws the notification store - the
                            built-in ones directly, Vapor and NEON HORIZON
                            through __GD__.notifications - and its action goes
                            to /dashboard, which is the core page in all three;
  the saves panel           GameSavesPanel on that page, the one place saves are
                            managed, shows both cards and keeps the chosen one.

The badge is asked for on every sign-in as well as on the socket message, or a
person who was away when the scan ran would never be told.

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


def _function(source: str, name: str) -> str:
    at = re.search(rf"(async )?function {name}\(", source)
    assert at, f"brak funkcji {name}"
    nxt = re.search(r"\n(export )?(async )?function |\nconst [a-zA-Z]+ = |\nonMounted|\nonUnmounted", source[at.end():])
    return source[at.start():at.end() + (nxt.start() if nxt else len(source))]


# ── The API the panel and the themes use ─────────────────────────────────────

def test_the_actions_speak_to_the_routes_the_server_has():
    source = _read("lib/dashboardActions.ts")
    assert '"/savestates/conflicts"' in source
    assert "`/savestates/conflicts/${id}/resolve`" in source
    assert "`/savestates/conflicts/${id}/export`" in source


def test_the_actions_are_in_the_object_themes_receive():
    """`__GD__.dashboard` is the object at the end of the file, not the module's
    exports - a function exported and left out of it is invisible to a theme."""
    source = _read("lib/dashboardActions.ts")
    obj = source[source.index("const dashboardActions = {"):source.index("export default dashboardActions")]
    for name in ("saveConflicts", "resolveSaveConflict", "exportSaveConflict"):
        assert re.search(rf"\b{name}\b", obj), f"{name} nie trafia do __GD__.dashboard"


# ── The badge ────────────────────────────────────────────────────────────────

def test_the_socket_message_reaches_a_registry_that_survives_reconnecting():
    source = _read("stores/socket.ts")
    bound = source[source.index('socket.value.on("saves:conflict"'):]
    assert "saveConflictCallbacks.forEach" in bound[:200], (
        "wiadomosc o odlozonej karcie nie trafia do zarejestrowanych odbiorcow"
    )
    returned = source[source.rindex("return {"):]
    assert "onSaveConflict" in returned


def test_the_badge_is_asked_for_on_sign_in_and_on_the_message():
    source = _read("lib/saveConflictBadge.ts")
    watcher = _function(source, "watchSaveConflicts")
    assert "auth.user?.id" in watcher and "immediate: true" in watcher, (
        "znaczek pytany tylko przy wiadomosci - kto byl nieobecny podczas skanu, "
        "nigdy sie nie dowie"
    )
    assert "onSaveConflict(" in watcher


def test_the_badge_leads_to_the_panel_and_goes_when_nothing_is_left():
    refresh = _function(_read("lib/saveConflictBadge.ts"), "refreshSaveConflictBadge")
    assert 'action: "/dashboard"' in refresh, "znaczek nie prowadzi do panelu zapisow"
    assert "notifications.remove(SAVE_CONFLICT_BADGE)" in refresh, (
        "znaczek zostaje po rozstrzygnieciu ostatniej karty"
    )
    assert "count: list.length" in refresh
    # A failed request must not clear the badge.
    at_catch = refresh.index("catch")
    assert "return" in refresh[at_catch:at_catch + 60] and refresh.index("remove(") > at_catch


def test_the_app_wires_the_badge_up_at_start():
    source = _read("main.ts")
    assert 'import { watchSaveConflicts } from "./lib/saveConflictBadge"' in source
    assert re.search(r"^watchSaveConflicts\(\);", source, re.M), "znaczek nigdy nie jest podlaczony"


# ── The panel ────────────────────────────────────────────────────────────────

def test_the_panel_lists_both_cards_and_keeps_the_chosen_one():
    source = _read("components/GameSavesPanel.vue")
    assert 'v-for="c in conflicts"' in source
    assert "keepCard(c, 'current')" in source and "keepCard(c, 'set_aside')" in source
    assert "exportConflict(c.id)" in source, "odlozonej karty nie da sie pobrac przed wyborem"
    keep = _function(source, "keepCard")
    assert "dashboardActions.resolveSaveConflict(c.id, keep)" in keep
    assert "refreshSaveConflictBadge()" in keep, "znaczek zostaje po wyborze"


def test_choosing_asks_first_with_a_tick():
    """The card that goes has no copy behind it unless it was downloaded."""
    keep = _function(_read("components/GameSavesPanel.vue"), "keepCard")
    assert "gdConfirm(" in keep and "requireTick: true" in keep
    assert keep.index("gdConfirm(") < keep.index("resolveSaveConflict("), (
        "karta kasowana przed zapytaniem"
    )


def test_the_panel_loads_the_cards_and_follows_the_message():
    source = _read("components/GameSavesPanel.vue")
    mounted = source[source.index("const loadError = ref(false);"):]
    assert "loadConflicts()" in mounted[:400]
    assert "onSaveConflict(" in source and "onUnmounted(stopConflictWatch)" in source


# ── Every language ───────────────────────────────────────────────────────────

KEYS = ["card_conflict_badge", "card_conflict_open", "card_conflict_title", "card_conflict_why",
        "card_in_use", "card_set_aside", "card_none_in_use", "card_keep", "card_confirm_title",
        "card_confirm", "card_confirm_go", "card_kept"]


@pytest.mark.parametrize("lang", ["en", "de", "es", "fr", "it", "pl", "pt", "ru"])
def test_every_language_can_say_it(lang):
    path = SRC / "i18n" / "en.json" if lang == "en" else FRONT / "public" / "i18n" / f"{lang}.json"
    if not path.is_file():
        pytest.skip("frontend tree not present")
    strings = json.load(io.open(path, encoding="utf-8"))
    for key in KEYS:
        assert strings.get(f"profile.{key}"), f"{lang}: brak profile.{key}"
    assert "{game}" in strings["profile.card_conflict_title"]
    confirm = strings["profile.card_confirm"]
    assert all(p in confirm for p in ("{game}", "{kept}", "{dropped}")), (
        f"{lang}: pytanie o wybor gubi, ktora karta jest ktora"
    )
