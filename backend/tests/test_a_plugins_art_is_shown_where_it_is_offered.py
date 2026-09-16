"""A plugin that supplies art is shown in the editor where that art is searched.

Reported by the owner on 2026-09-13 with a screenshot of the game metadata editor
(God of War, Games library) and a ring drawn round the row of source icons above
the cover search: the ROM editor shows the installed metadata plugins there, this
one does not.

Measured before anything was changed:

  * the cover, background and logo searches in `LibraryMetadataPanel` (games,
    GOG, the PC Ports catalogue) and in `CollectionMetadataPanel` DO ask the
    plugins - `source=plugins` - but the row above each of them is four hard-coded
    icons. The screenshots row in the same panel already draws every plugin.
  * on the owner's install only TheGamesDB implements the art hooks
    (`metadata_get_covers`, `_heroes`, `_logos`). PPE.pl and ProtonDB implement
    game search and nothing else - so drawing every plugin above the covers would
    promise art from two sources that have none to give.
  * the icon search asked the plugins for `asset_type=icons`, a hook that does not
    exist; the route fell back to the COVER hook, so TheGamesDB's box art was
    offered as candidate icons.

So the provider list says which art each plugin supplies, the rows draw a plugin
only above the kind of art it supplies, and nothing asks a plugin for icons.
"""

from __future__ import annotations

import io
import pathlib
import re
from types import SimpleNamespace

import pytest

from handler.auth.scopes import Scope

BACKEND = pathlib.Path(__file__).resolve().parent.parent
FRONTEND = BACKEND.parent / "frontend"
LIBRARY_PANEL = FRONTEND / "src" / "components" / "games" / "LibraryMetadataPanel.vue"
COLLECTION_PANEL = FRONTEND / "src" / "components" / "collections" / "CollectionMetadataPanel.vue"


class _Art:
    """TheGamesDB, as far as these hooks go."""

    def metadata_provider_id(self):
        return "thegamesdb"

    def metadata_provider_name(self):
        return "TheGamesDB"

    def metadata_search_game(self, query):
        return []

    def metadata_get_covers(self, query):
        return []

    def metadata_get_heroes(self, query):
        return []

    def metadata_get_logos(self, query):
        return []


class _SearchOnly:
    """PPE.pl: game search and nothing else."""

    def metadata_provider_id(self):
        return "ppe"

    def metadata_provider_name(self):
        return "PPE.pl"

    def metadata_search_game(self, query):
        return []


# ── The provider list ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_the_provider_list_says_which_art_each_plugin_supplies(monkeypatch):
    import plugins.manager as pm_mod
    from endpoints.settings import plugins_router as pr_mod
    from endpoints.settings.plugins_router import plugin_metadata_providers

    art, search_only = _Art(), _SearchOnly()
    dirs = {art: "thegamesdb", search_only: "ppe-metadata"}
    fake = SimpleNamespace(get_plugin_instances=lambda: [art, search_only],
                           id_for_instance=dirs.get)
    monkeypatch.setattr(pm_mod, "plugin_manager", fake)
    monkeypatch.setattr(pr_mod, "plugin_manager", fake)

    req = SimpleNamespace(state=SimpleNamespace(
        user=SimpleNamespace(id=1, username="u"), scopes={Scope.PLUGINS_READ}))
    out = {p["id"]: p for p in await plugin_metadata_providers(req)}

    assert out["thegamesdb"].get("art") == ["grids", "heroes", "logos"], (
        "lista dostawcow nie mowi, jakie grafiki daje TheGamesDB: %r"
        % out["thegamesdb"].get("art")
    )
    assert out["ppe"].get("art") == [], (
        "wtyczka bez hookow grafik udaje, ze je daje: %r" % out["ppe"].get("art")
    )


# ── Icons are not covers ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_asking_plugins_for_icons_does_not_return_their_covers(monkeypatch):
    import plugins.manager as pm_mod
    from handler.metadata.external_art import search_cover_options

    asked = []

    def _covers(query):
        asked.append(query)
        return [[{"url": "http://x/box.jpg", "_source": "TheGamesDB"}]]

    monkeypatch.setattr(pm_mod, "plugin_manager", SimpleNamespace(
        hook=SimpleNamespace(metadata_get_covers=_covers),
        get_plugin_instances=lambda: [],
        id_for_instance=lambda i: None,
    ))

    out = await search_cover_options("plugins", "God of War", asset_type="icons")

    assert out == [] and asked == [], (
        "zakladka ikon dostala okladki wtyczki jako propozycje ikon"
    )


@pytest.mark.asyncio
async def test_asking_plugins_for_covers_still_returns_them(monkeypatch):
    """THE LEGAL CASE: the cover hook still answers the cover search."""
    import plugins.manager as pm_mod
    from handler.metadata.external_art import search_cover_options

    monkeypatch.setattr(pm_mod, "plugin_manager", SimpleNamespace(
        hook=SimpleNamespace(metadata_get_covers=lambda query: [[
            {"url": "http://x/box.jpg", "_source": "TheGamesDB"}]]),
        get_plugin_instances=lambda: [],
        id_for_instance=lambda i: None,
    ))

    out = await search_cover_options("plugins", "God of War", asset_type="grids")

    assert [o["url"] for o in out] == ["http://x/box.jpg"]


def test_no_route_falls_back_to_the_cover_hook_for_an_unknown_kind():
    """The GOG route carries its own copy of the plugin branch."""
    for rel in ("handler/metadata/external_art.py", "endpoints/gog/gog_router.py"):
        source = io.open(BACKEND / rel, encoding="utf-8").read()
        assert '.get(asset_type, "metadata_get_covers")' not in source, (
            f"{rel}: nieznany rodzaj grafiki nadal pyta hook okladek"
        )


# ── The rows above the searches ──────────────────────────────────────────────

def _header_above(source: str, search_fn: str) -> str:
    """The source row directly above the search box that runs `search_fn`."""
    at = source.index(f'@keydown.enter="{search_fn}"')
    start = source.rindex("mep-source-header", 0, at)
    return source[start:at]


def _function(source: str, name: str) -> str:
    at = source.index(f"async function {name}(")
    nxt = re.search(r"\n(async function |function |const |onMounted)", source[at + 10:])
    return source[at:at + 10 + nxt.start()] if nxt else source[at:]


@pytest.mark.parametrize("panel, rows", [
    (LIBRARY_PANEL, {"searchAllCovers": "grids", "searchAllHeroes": "heroes",
                     "searchAllLogos": "logos"}),
    (COLLECTION_PANEL, {"searchAllCovers": "grids", "searchAllHeroes": "heroes",
                        "searchAllLogos": "logos"}),
], ids=lambda v: v.name if isinstance(v, pathlib.Path) else "")
def test_each_art_row_draws_the_plugins_that_supply_that_art(panel, rows):
    if not panel.is_file():
        pytest.skip("frontend tree not present")
    source = io.open(panel, encoding="utf-8").read()

    for search_fn, kind in rows.items():
        header = _header_above(source, search_fn)
        assert f"artProviders('{kind}')" in header, (
            f"{panel.name}: wiersz nad {search_fn} nie pokazuje wtyczek, ktore daja '{kind}'"
        )


def test_the_icon_row_promises_no_plugin_and_the_search_asks_none():
    if not LIBRARY_PANEL.is_file():
        pytest.skip("frontend tree not present")
    source = io.open(LIBRARY_PANEL, encoding="utf-8").read()

    assert "artProviders(" not in _header_above(source, "searchAllIcons"), (
        "wiersz nad ikonami obiecuje wtyczki, a zadna nie daje ikon"
    )
    assert "source=plugins" not in _function(source, "searchAllIcons"), (
        "wyszukiwanie ikon nadal pyta wtyczki"
    )


def test_the_collection_editor_knows_the_plugins_at_all():
    if not COLLECTION_PANEL.is_file():
        pytest.skip("frontend tree not present")
    source = io.open(COLLECTION_PANEL, encoding="utf-8").read()
    assert "'/plugins/metadata/providers'" in source, (
        "edytor kolekcji nie pobiera listy wtyczek, wiec nie ma czego pokazac"
    )
