"""A button is offered to exactly the people the route behind it will serve.

Reported by the user as "user ma dostep do rescrape metadanych romow". The data
was never at risk: every ROM route was probed with a plain user's token against
a ROM id that does not exist, so a route letting the caller past its scope check
could only answer 404, and all seven answered 403. What the user saw was the
button, not the deed.

The routes divide on purpose. Editing one ROM's metadata, uploading media for
it and re-scraping it ask for LIBRARY_WRITE, which an editor has. Deleting,
clearing, hashing, converting and anything that sweeps a whole platform ask for
ROMS_WRITE, which only an admin has. The skins had not kept up with that split
and were wrong in both directions:

    Classic  scrape          no role check at all, so a plain user saw it
    Classic  edit metadata   admin only, so an editor lost what the API allows
    Modern   clear metadata  editor and up, but the route is admin only

Being too tight is not a security bug, but it is the same defect: the button
and the route disagree about who is being served. Both readings end with
somebody staring at a control that cannot do what it says.

Vapor keeps its own copy of this page in its own repository, out of reach from
here, and had the same clear-metadata mismatch plus a Scrape ALL that called a
route which does not exist. Both were fixed there and checked in a browser.

Modern's controls moved into one "Manage" menu (the owner, 2026-09-18): an item
there is `{ ..., show: <check>, ..., run: <handler> }`, and its `show` is what a
button's v-if was.
"""
from __future__ import annotations

import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
FRONTEND = ROOT / "frontend"

# What the backend actually asks for, and therefore who the button may be shown
# to. "canEdit" is the skins' name for admin, uploader or editor; "isAdmin" is
# admin alone.
EXPECTED = {
    "Classic": {
        "path": FRONTEND / "src" / "layouts" / "ClassicGameDetail.vue",
        "controls": {
            "onScrapeClick": "canEdit",   # POST /roms/{id}/scrape  -> LIBRARY_WRITE
            "metaOpen = true": "canEdit",  # PATCH /roms/{id}        -> LIBRARY_WRITE
            "onClearClick": "isAdmin",     # POST .../clear-metadata -> ROMS_WRITE
        },
    },
    "Games (Modern)": {
        "path": FRONTEND / "src" / "views" / "games" / "GamesGameDetail.vue",
        "controls": {
            # A library game's scrape is admin only, unlike a ROM's. The two sit
            # in views that look alike, which is how this one spent a while
            # under canEdit offering a refusal.
            "run: onScrapeClick": "isAdmin",
            "run: toggleEditPanel": "canEdit",
            "run: onClearMetadataClick": "isAdmin",
        },
    },
    "Modern (and NEON HORIZON through it)": {
        "path": FRONTEND / "src" / "views" / "emulation" / "EmulationGameDetail.vue",
        "controls": {
            "run: triggerScrape": "canEdit",
            "run: openEditPanel": "canEdit",
            "run: onClearMetadata": "isAdmin",
        },
    },
}


def _read(path: pathlib.Path) -> str:
    if not path.is_file():
        pytest.skip("drzewo frontendu nie jest obecne")
    return path.read_text(encoding="utf-8")


def _guard_of(source: str, handler: str) -> str:
    """The v-if on the element that carries this click handler, or the `show`
    of the menu item that runs it.

    Reads backwards from the handler to the opening angle bracket of its own
    tag, which is the whole element and nothing of its neighbours - or, for a
    menu item, to its opening brace; items hold no nested braces.
    """
    at = source.index(handler)
    if handler.startswith("run: "):
        item = source[source.rindex("{", 0, at):source.index("}", at)]
        match = re.search(r"show:\s*([^,]+),", item)
        return match.group(1) if match else ""
    start = source.rindex("<", 0, at)
    tag = source[start:source.index(">", at)]
    match = re.search(r'v-if="([^"]*)"', tag)
    return match.group(1) if match else ""


@pytest.mark.parametrize("skin", sorted(EXPECTED))
def test_the_skin_can_name_the_roles_the_api_serves(skin):
    """A skin that only knows admin cannot express "editor and up", which is
    how Classic ended up with no check at all on one button and too strict a
    check on the one beside it."""
    source = _read(EXPECTED[skin]["path"])
    assert re.search(r"canEdit\s*=\s*computed", source), (
        f"{skin}: brak pojecia canEdit, skorka zna tylko admina"
    )
    for role in ("uploader", "editor"):
        assert role in source, f"{skin}: canEdit nie wymienia roli {role}"


@pytest.mark.parametrize("skin", sorted(EXPECTED))
def test_every_control_is_offered_to_exactly_who_the_route_serves(skin):
    surface = EXPECTED[skin]
    source = _read(surface["path"])
    for handler, expected in surface["controls"].items():
        guard = _guard_of(source, handler)
        assert expected in guard, (
            f"{skin}: przycisk {handler!r} ma warunek {guard!r}, a trasa za nim "
            f"obsluguje {expected}"
        )


@pytest.mark.parametrize("skin", sorted(EXPECTED))
def test_nothing_that_needs_an_admin_is_offered_more_widely(skin):
    """The direction that matters most: a control the route will refuse should
    not be dangled in front of anyone."""
    surface = EXPECTED[skin]
    source = _read(surface["path"])
    for handler, expected in surface["controls"].items():
        if expected != "isAdmin":
            continue
        guard = _guard_of(source, handler)
        assert "canEdit" not in guard, (
            f"{skin}: {handler!r} jest pod canEdit, a trasa wymaga admina, "
            "wiec redaktor zobaczy przycisk i dostanie 403"
        )
