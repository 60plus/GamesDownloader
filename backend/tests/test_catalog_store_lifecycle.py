"""A catalogue store, and the games downloaded from it, across a plugin's life.

Two rules matter enough to pin, and both are the kind a live e2e proves once but
a refactor can quietly break:

- Uninstalling a catalogue plugin reads the catalogue id off the still-loaded
  instance, so the right store is the one that gets removed - and nothing else
  is, when the plugin offers no catalogue at all.
- A reinstall re-links each entry to the game already downloaded from it by an
  EXACT match on the stored origin. A near-miss must not adopt a stranger, or a
  reinstall would silently repoint a game at the wrong listing.

Both are tested without a database: the matching is a pure function, and the id
lookup is driven through a stand-in plugin instance.
"""
from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import plugins.manager as pm_module
from handler.library.catalog_sync_handler import (
    _catalog_owners,
    _copy_game_meta_to_entry,
    _relink_targets,
    catalog_ids_for_plugin,
)
from plugins.manager import plugin_manager


# ── Re-link matching (_relink_targets) ───────────────────────────────────────

def test_each_entry_maps_to_the_game_with_its_own_external_id():
    games = [(10, "owner/repo-a"), (11, "owner/repo-b")]
    got = _relink_targets(["owner/repo-a", "owner/repo-b"], games)
    assert got == {"owner/repo-a": 10, "owner/repo-b": 11}


def test_an_entry_with_no_matching_game_is_left_out():
    """Never downloaded, so no game - the entry stays unlinked, not guessed."""
    games = [(10, "owner/repo-a")]
    got = _relink_targets(["owner/repo-a", "owner/never-downloaded"], games)
    assert got == {"owner/repo-a": 10}
    assert "owner/never-downloaded" not in got


def test_a_near_miss_external_id_never_adopts_the_wrong_game():
    """The whole point of matching on external_id and not the title."""
    games = [(10, "owner/repo-a")]
    assert _relink_targets(["owner/repo-a-fork"], games) == {}


def test_the_lowest_id_wins_when_two_games_share_an_origin():
    """A pre-fix duplicate download could leave two games with one origin. The
    mapping has to be stable, so the lowest id (the first ordered row) wins."""
    games = [(10, "owner/repo-a"), (14, "owner/repo-a")]
    assert _relink_targets(["owner/repo-a"], games) == {"owner/repo-a": 10}


def test_games_without_an_origin_are_ignored():
    """A GOG or hand-added game has no catalogue origin; a NULL must never
    become the target for an entry that happens to carry no external id."""
    games = [(10, None), (11, "owner/repo-b")]
    assert _relink_targets(["owner/repo-b"], games) == {"owner/repo-b": 11}


def test_empty_inputs_map_to_nothing():
    assert _relink_targets([], [(10, "owner/repo-a")]) == {}
    assert _relink_targets(["owner/repo-a"], []) == {}


# ── Re-link carries the game's metadata back to the entry (_copy_game_meta_to_entry)
# A reinstall's fresh entry is blank; the game it links to still holds what was
# scraped onto it, so the store shows metadata again instead of an empty listing.

def _blank_entry(**over):
    fields = dict(
        cover_path=None, background_path=None, logo_path=None, description=None,
        developer=None, publisher=None, release_date=None, rating=None,
        genres=None, screenshots=None, meta_ratings=None, languages=None,
        requirements=None, hltb_main_s=None, hltb_complete_s=None,
        meta_scraped_at=None, meta_matched_title=None,
    )
    fields.update(over)
    return SimpleNamespace(**fields)


def _scraped_game(**over):
    fields = dict(
        cover_path="/c.jpg", background_path="/bg.jpg", logo_path="/logo.png",
        description="A great port", developer="Dev", publisher="Pub",
        release_date=date(2001, 5, 1), rating=4.5, genres=["Action"],
        screenshots=["/s1.jpg"], meta_ratings={"rawg": 80},
        languages={"en": "English"}, requirements={"minimum": "x"},
        hltb_main_s=3600, hltb_complete_s=7200, title="Game X",
    )
    fields.update(over)
    return SimpleNamespace(**fields)


def test_metadata_is_copied_from_the_game_onto_a_blank_entry():
    e = _blank_entry()
    _copy_game_meta_to_entry(e, _scraped_game())
    assert e.cover_path == "/c.jpg"
    assert e.description == "A great port"
    assert e.release_date == "2001-05-01"      # Date becomes the entry's string
    assert e.rating == 4.5
    assert e.genres == ["Action"]
    assert e.meta_ratings == {"rawg": 80}
    assert e.hltb_main_s == 3600
    assert e.meta_scraped_at is not None        # stamped: the game holds the meta
    assert e.meta_matched_title == "Game X"


def test_metadata_the_entry_already_has_is_not_overwritten():
    e = _blank_entry(cover_path="/own.jpg", description="own", meta_scraped_at="set")
    _copy_game_meta_to_entry(e, _scraped_game())
    assert e.cover_path == "/own.jpg"
    assert e.description == "own"
    assert e.meta_scraped_at == "set"


def test_an_unscraped_game_leaves_the_entry_open_for_the_metadata_pass():
    """A game downloaded but never scraped must not stamp its entry as done, or
    the entry would sit blank forever."""
    e = _blank_entry()
    bare = _scraped_game(cover_path=None, description=None, rating=None,
                         genres=None, screenshots=None, meta_ratings=None,
                         background_path=None, logo_path=None)
    _copy_game_meta_to_entry(e, bare)
    assert e.cover_path is None
    assert e.meta_scraped_at is None            # left for the metadata pass


# ── Which store an uninstall removes (catalog_ids_for_plugin) ─────────────────

class _CataloguePlugin:
    def __init__(self, cid):
        self._cid = cid

    def library_catalog_id(self):
        return self._cid


class _PlainPlugin:
    """A plugin that offers no catalogue - a theme, a metadata provider."""


def test_uninstall_reads_the_catalogue_id_from_the_live_instance(monkeypatch):
    monkeypatch.setitem(plugin_manager._instances, "pcports",
                        _CataloguePlugin("github-ports"))
    assert catalog_ids_for_plugin("pcports") == ["github-ports"]


def test_a_non_catalogue_plugin_owns_no_store(monkeypatch):
    monkeypatch.setitem(plugin_manager._instances, "some-theme", _PlainPlugin())
    assert catalog_ids_for_plugin("some-theme") == []


def test_an_unloaded_plugin_yields_no_catalogue():
    """Uninstalling a plugin that is not loaded finds no store to remove here;
    the startup reconcile is the safety net for that case."""
    assert catalog_ids_for_plugin("not-loaded-xyz") == []


def test_a_blank_catalogue_id_is_not_a_catalogue(monkeypatch):
    monkeypatch.setitem(plugin_manager._instances, "empty", _CataloguePlugin(""))
    assert catalog_ids_for_plugin("empty") == []


# ── Which plugin owns which catalogue (_catalog_owners) ───────────────────────
# The reconcile backfills a store's owner and judges a legacy store from this
# map, so it must pair each catalogue with the exact plugin that offers it.

def _fake_registry(monkeypatch, mapping):
    """Point the plugin manager at a fake {plugin_id: instance} registry so both
    get_plugin_instances() and id_for_instance() agree."""
    monkeypatch.setattr(plugin_manager, "_instances", dict(mapping))
    monkeypatch.setattr(plugin_manager, "get_plugin_instances",
                        lambda: list(mapping.values()))


def test_catalog_owners_pairs_each_catalogue_with_its_plugin(monkeypatch):
    _fake_registry(monkeypatch, {
        "p-cat": _CataloguePlugin("cat-x"), "p-theme": _PlainPlugin(),
    })
    assert _catalog_owners() == {"cat-x": "p-cat"}


def test_catalog_owners_skips_a_plugin_whose_hook_raises(monkeypatch):
    class _Boom:
        def library_catalog_id(self):
            raise RuntimeError("plugin blew up reporting its id")

    _fake_registry(monkeypatch, {"g": _CataloguePlugin("cat-x"), "b": _Boom()})
    # The crashing one is left out; its own store already carries plugin_id, so
    # omitting it here cannot condemn it.
    assert _catalog_owners() == {"cat-x": "g"}


def test_catalog_owners_skips_a_blank_catalogue_id(monkeypatch):
    _fake_registry(monkeypatch, {"e": _CataloguePlugin("")})
    assert _catalog_owners() == {}


def test_catalog_owners_is_empty_without_catalogue_plugins(monkeypatch):
    _fake_registry(monkeypatch, {"t1": _PlainPlugin(), "t2": _PlainPlugin()})
    assert _catalog_owners() == {}


# ── The reconcile gate must not trust a missing/empty plugin directory ────────
# An absent or empty plugin dir usually means the plugin volume is unmounted (a
# migrated/restored DB whose plugin files are not in place). Reading that as
# "all loaded" once let the reconcile delete every storefront and its overrides.

def _plugin_dirs(tmp_path, names):
    for n in names:
        (tmp_path / n).mkdir()
    return tmp_path


def test_gate_false_when_the_plugin_directory_is_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(pm_module, "PLUGINS_PATH", str(tmp_path / "not-there"))
    monkeypatch.setattr(plugin_manager, "_instances", {})
    assert plugin_manager.all_external_plugins_loaded() is False


def test_gate_false_when_the_plugin_directory_is_empty(monkeypatch, tmp_path):
    monkeypatch.setattr(pm_module, "PLUGINS_PATH", str(tmp_path))
    monkeypatch.setattr(plugin_manager, "_instances", {})
    assert plugin_manager.all_external_plugins_loaded() is False


def test_gate_true_when_every_present_plugin_is_loaded(monkeypatch, tmp_path):
    _plugin_dirs(tmp_path, ["alpha", "beta"])
    monkeypatch.setattr(pm_module, "PLUGINS_PATH", str(tmp_path))
    monkeypatch.setattr(plugin_manager, "_instances",
                        {"alpha": object(), "beta": object()})
    assert plugin_manager.all_external_plugins_loaded() is True


def test_gate_false_when_a_present_plugin_is_unloaded(monkeypatch, tmp_path):
    """beta is on disk but not in _instances - disabled or failed to load."""
    _plugin_dirs(tmp_path, ["alpha", "beta"])
    monkeypatch.setattr(pm_module, "PLUGINS_PATH", str(tmp_path))
    monkeypatch.setattr(plugin_manager, "_instances", {"alpha": object()})
    assert plugin_manager.all_external_plugins_loaded() is False


def test_installed_ids_are_empty_when_the_directory_is_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(pm_module, "PLUGINS_PATH", str(tmp_path / "not-there"))
    assert plugin_manager.installed_external_ids() == set()


def test_installed_ids_list_present_dirs_loaded_or_not(monkeypatch, tmp_path):
    """A disabled plugin is still installed - its directory is still there."""
    _plugin_dirs(tmp_path, ["alpha", "beta"])
    monkeypatch.setattr(pm_module, "PLUGINS_PATH", str(tmp_path))
    monkeypatch.setattr(plugin_manager, "_instances", {"alpha": object()})
    assert plugin_manager.installed_external_ids() == {"alpha", "beta"}
