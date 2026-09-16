"""Who may pull new content onto the server from a store plugin.

The owner separated two things that had been looking like one: "blokada i
dawanie dostepu do bibliotek sluzy do czego innego. jesli na przyklad jest
dziecko, chce zrobic biblioteke z samymi grami dla dzieci, to wtedy w
bibliotece daje dostep uzytkownikowi. to dwie rozne funkcje."

Library access is about what somebody SEES. It is content curation, it lives in
Settings > Libraries, and nothing here touches it. Store access is about whether
somebody may FETCH NEW CONTENT ONTO THE SERVER, which is a permission rather
than a visibility, so it belongs on the account.

And the rule that decides the shape: "uzykownik nigdy nie moze pobierac gier na
serwer". Never, not even if an admin ticks the box by hand. A switch that is
only enforced by not being shown is not that rule, so it is not enforced that
way. Every store route asks for two permissions at once, and `protected_route`
requires all of them: the upload permission, which an ordinary account does not
have and cannot be given without becoming an uploader, and the store permission
on top. Ticking the box on a plain account grants the second and leaves the
first missing, so the answer is still no.

Store access is off by default for everybody below an admin. An admin hands it
out, which is what "admin przydziela dostep" means, and it is the reason this
is not simply implied by being an uploader.
"""
from __future__ import annotations

import io
import pathlib
import re

import pytest

from handler.auth.scopes import (
    ADMIN_SCOPES,
    EDITOR_SCOPES,
    UPLOADER_SCOPES,
    USER_SCOPES,
    Scope,
    apply_permission_overrides,
)

BACKEND = pathlib.Path(__file__).resolve().parent.parent
ROM_SOURCES = BACKEND / "endpoints" / "roms" / "rom_sources_router.py"
PLUGINS = BACKEND / "endpoints" / "settings" / "plugins_router.py"


def _source(path: pathlib.Path) -> str:
    return io.open(path, encoding="utf-8").read()


def _declared(source: str, verb: str, path: str) -> set[str]:
    pattern = (r'@protected_route\([a-z_]+\.' + verb + r',\s*"' + re.escape(path)
               + r'",\s*scopes=\[([^\]]*)\]')
    match = re.search(pattern, source)
    assert match, f"nie znalazlem trasy {verb.upper()} {path}"
    return {s.strip().split(".")[-1] for s in match.group(1).split(",") if s.strip()}


# ── The permission itself ────────────────────────────────────────────────────

def test_the_permission_exists_and_nobody_below_an_admin_starts_with_it():
    assert Scope.STORE_ACCESS in ADMIN_SCOPES
    for name, scopes in (("uploader", UPLOADER_SCOPES),
                         ("editor", EDITOR_SCOPES),
                         ("user", USER_SCOPES)):
        assert Scope.STORE_ACCESS not in scopes, f"{name} dostaje sklepy bez przydzialu"


def test_an_admin_can_hand_it_to_an_uploader():
    granted = apply_permission_overrides({"store_access": True}, UPLOADER_SCOPES)
    assert Scope.STORE_ACCESS in granted
    assert Scope.LIBRARY_UPLOAD in granted, "przydzial nie moze zabierac tego, co bylo"


def test_an_admin_can_take_it_back():
    revoked = apply_permission_overrides({"store_access": False}, ADMIN_SCOPES)
    assert Scope.STORE_ACCESS not in revoked


# ── The rule that has no exception ───────────────────────────────────────────

def test_a_plain_account_stays_out_even_with_the_box_ticked():
    """The whole reason every store route asks for two permissions rather than
    one. Granting the store permission to somebody who cannot upload leaves
    them holding half of what the route requires, and half is a refusal."""
    granted = apply_permission_overrides({"store_access": True}, USER_SCOPES)
    assert Scope.STORE_ACCESS in granted
    assert Scope.LIBRARY_UPLOAD not in granted


def test_an_editor_stays_out_too():
    """An editor edits what is already here. Bringing new things in is the
    uploader's, which is the line the quota is drawn along as well."""
    granted = apply_permission_overrides({"store_access": True}, EDITOR_SCOPES)
    assert Scope.LIBRARY_UPLOAD not in granted


# ── Every route on both stores ───────────────────────────────────────────────

def test_every_rom_source_route_asks_for_the_same_three():
    """The ROM downloader is one screen. Browsing, fetching and the queue on it
    are the same permission, so a granted uploader is not handed a page with
    half its buttons refusing them.

    Three, not two: ROMS_READ is the emulation permission, and pulling a ROM
    onto the server is an emulation act. Without it an account with emulation
    revoked could still fetch ROMs, which the ROM upload route beside these
    declares against explicitly."""
    source = _source(ROM_SOURCES)
    routes = re.findall(r'@protected_route\(router\.(\w+),\s*"([^"]*)",\s*scopes=\[([^\]]*)\]',
                        source)
    assert len(routes) >= 12, f"znalazlem tylko {len(routes)} tras, wzorzec sie rozjechal"
    for verb, path, scopes in routes:
        names = {s.strip().split(".")[-1] for s in scopes.split(",") if s.strip()}
        assert names == {"LIBRARY_UPLOAD", "STORE_ACCESS", "ROMS_READ"}, (
            f"{verb.upper()} {path or '/'} deklaruje {names}"
        )


def test_pulling_a_catalogue_entry_onto_the_server_asks_for_both():
    """The other store. It was already the uploader's, which is exactly why the
    store permission had to be added rather than assumed."""
    declared = _declared(_source(PLUGINS), "post",
                         "/library/catalog-entries/{entry_id}/download")
    assert declared == {"LIBRARY_UPLOAD", "STORE_ACCESS"}


def test_reading_a_catalogue_is_left_alone():
    """Seeing a shelf is the other question, the one that stays in the library
    settings. Store access is about fetching, so it does not narrow browsing."""
    declared = _declared(_source(PLUGINS), "get", "/library/catalogs")
    assert "STORE_ACCESS" not in declared


# ── The switch on the account ────────────────────────────────────────────────

def test_the_store_pages_are_reachable_by_whoever_is_shown_the_tile():
    """Showing the tile is only half of it. The router turned these two pages
    away from anyone who is not an admin, which is what they were when the
    routes behind them were admin-only, so a granted uploader could see the
    entrance and be bounced to the library on the way in.

    The token cannot answer this: it carries the scopes of the ROLE, not the
    per-account overrides, so a granted uploader's token looks like any other
    uploader's. The guard asks the account instead.
    """
    router = io.open(BACKEND.parent / "frontend" / "src" / "plugins" / "router.ts",
                     encoding="utf-8").read()
    start = router.index('path: "rom-sources/:sourceId"')
    # Both store pages and nothing else: the second one's meta is the last thing
    # before the block closes.
    block = router[start:router.index('path: "rom-sources/:sourceId/:fsSlug"', start) + 700]
    assert "requiresAdmin" not in block, (
        "trasy sklepu nadal wymagaja admina, wiec uploader zobaczy kafel "
        "i zostanie odeslany do biblioteki"
    )
    assert block.count("requiresStoreAccess") == 2, "obie strony sklepu maja to deklarowac"


def test_the_guard_asks_the_account_and_not_the_token():
    """The token carries the scopes of the role, not the per-account overrides,
    so a granted uploader's token is indistinguishable from any other
    uploader's. Asking it would refuse exactly the people this exists for."""
    router = io.open(BACKEND.parent / "frontend" / "src" / "plugins" / "router.ts",
                     encoding="utf-8").read()
    at = router.index("if (to.meta.requiresStoreAccess")
    # This block only. The admin check sits right below it and does read the
    # token, legitimately, so a window wide enough to reach it fails on its own
    # neighbour rather than on anything true.
    guard = router[at:router.index("\n    }\n", at)]
    assert "canUseStores" in guard, "straznik nie pyta o to samo, co reszta interfejsu"
    assert "payload" not in guard, "straznik czyta token, ktory nie zna przydzialu"


def test_the_switch_is_not_offered_to_a_role_that_could_never_use_it():
    """Showing it to a plain account would promise something the server refuses,
    which is the same defect as a button with no route behind it."""
    source = io.open(BACKEND.parent / "frontend" / "src" / "views" / "admin"
                     / "AdminUsers.vue", encoding="utf-8").read()
    assert "store_access" in source, "brak przelacznika w zarzadzaniu uzytkownikami"
    at = source.index("store_access")
    window = source[max(0, at - 900):at + 900]
    assert "uploader" in window, "przelacznik nie jest ograniczony do uploadera"
