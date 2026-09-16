"""A plugin's shelf cannot be switched back on while the plugin is off.

Disabling a catalogue plugin hides the shelf it registered - out of the store,
out of the scan, out of the exclusions screen. But the library list in Settings
still drew a switch beside it, and the switch worked: one click and the shelf
was back in the navigation with no plugin behind it, unable to refresh its
listings or download anything. The plugin toggle put it away and the library
toggle took it out again.

So the shelf follows its plugin and the library switch is refused for it while
the plugin is not in the runtime. Refused on the server rather than only greyed
out on the screen, because a greyed-out control is a suggestion.

Switching such a shelf OFF by hand is still allowed. It is already the direction
the plugin would take it, and refusing it would be refusing somebody the tidier
state they are asking for.
"""

from __future__ import annotations

import io
import pathlib
from types import SimpleNamespace

import pytest

BACKEND = pathlib.Path(__file__).resolve().parent.parent


def _lib(**kw):
    base = dict(slug="pc-ports", name="PC Ports", kind="custom_lib",
                storage_folder="PC Ports", enabled=False, is_store=True,
                catalog_id="github-ports", plugin_id="pcports", icon=None,
                color=None, sort_order=0, is_builtin=False, id=37,
                visibility="public", adds_to_default_library=False)
    base.update(kw)
    return SimpleNamespace(**base)


@pytest.fixture
def loaded(monkeypatch):
    """Control which plugins the runtime is holding."""
    from plugins import manager as mgr

    ids: set[str] = set()

    class _PM:
        def get_instance(self, plugin_id):
            return object() if plugin_id in ids else None

        def get_plugin_instances(self):
            return []

    monkeypatch.setattr(mgr, "plugin_manager", _PM())
    import handler.library.catalog_sync_handler as csh
    monkeypatch.setattr(csh, "plugin_manager", _PM())
    return ids


def test_a_shelf_whose_plugin_is_off_is_waiting(loaded):
    from handler.library.catalog_sync_handler import shelf_waiting_for_its_plugin
    assert shelf_waiting_for_its_plugin(_lib())


def test_a_shelf_whose_plugin_is_loaded_is_not(loaded):
    from handler.library.catalog_sync_handler import shelf_waiting_for_its_plugin
    loaded.add("pcports")
    assert not shelf_waiting_for_its_plugin(_lib())


def test_an_ordinary_library_never_waits_for_anything(loaded):
    """The switch on a library nobody's plugin owns is the admin's alone."""
    from handler.library.catalog_sync_handler import shelf_waiting_for_its_plugin
    assert not shelf_waiting_for_its_plugin(
        _lib(slug="games", catalog_id=None, plugin_id=None, is_store=False))


def test_an_older_shelf_without_the_owner_column_is_read_the_same_way(loaded):
    """`plugin_id` came after `catalog_id`. A store made before it is owned by
    whichever loaded plugin claims that catalogue, and none does when the plugin
    is off - which is the same answer, reached the other way."""
    from handler.library.catalog_sync_handler import shelf_waiting_for_its_plugin
    assert shelf_waiting_for_its_plugin(_lib(plugin_id=None))


# ── The switch itself ────────────────────────────────────────────────────────

class _FakeRequest:
    def __init__(self):
        from handler.auth.scopes import Scope
        self.state = SimpleNamespace(
            user=SimpleNamespace(id=1, username="admin"),
            scopes={Scope.SETTINGS_WRITE, Scope.SETTINGS_READ},
        )


@pytest.mark.asyncio
async def test_turning_it_on_is_refused_while_the_plugin_is_off(loaded, monkeypatch):
    from fastapi import HTTPException

    from endpoints.library import libraries_router as R

    async def _get_by_slug(_slug):
        return _lib()

    written: list = []

    async def _update(*a, **k):
        written.append(k)
        return _lib(enabled=True)

    monkeypatch.setattr(R.library_registry_handler, "get_by_slug", _get_by_slug)
    monkeypatch.setattr(R.library_registry_handler, "update", _update)

    with pytest.raises(HTTPException) as raised:
        await R.update_library(_FakeRequest(), "pc-ports",
                               R.LibraryUpdateBody(enabled=True))

    assert raised.value.status_code == 400
    assert "plugin" in str(raised.value.detail).lower()
    assert written == [], "odmowa, a polka i tak wrocila"


@pytest.mark.asyncio
async def test_turning_it_on_works_once_the_plugin_is_back(loaded, monkeypatch):
    """The other half. A guard that refused always would strand the shelf."""
    from endpoints.library import libraries_router as R

    loaded.add("pcports")
    written: list = []

    async def _get_by_slug(_slug):
        return _lib()

    async def _update(*a, **k):
        written.append(k)
        return _lib(enabled=True)

    monkeypatch.setattr(R.library_registry_handler, "get_by_slug", _get_by_slug)
    monkeypatch.setattr(R.library_registry_handler, "update", _update)

    await R.update_library(_FakeRequest(), "pc-ports", R.LibraryUpdateBody(enabled=True))
    assert written and written[0].get("enabled") is True


@pytest.mark.asyncio
async def test_turning_it_off_by_hand_is_still_allowed(loaded, monkeypatch):
    """Already the direction the plugin would take it. Refusing would be
    refusing somebody the tidier state they asked for."""
    from endpoints.library import libraries_router as R

    written: list = []

    async def _get_by_slug(_slug):
        return _lib(enabled=True)

    async def _update(*a, **k):
        written.append(k)
        return _lib()

    monkeypatch.setattr(R.library_registry_handler, "get_by_slug", _get_by_slug)
    monkeypatch.setattr(R.library_registry_handler, "update", _update)

    await R.update_library(_FakeRequest(), "pc-ports", R.LibraryUpdateBody(enabled=False))
    assert written and written[0].get("enabled") is False


# ── And the screen is told, so the control is not a lie ──────────────────────

def test_the_payload_says_the_shelf_is_waiting():
    source = io.open(BACKEND / "endpoints" / "library" / "libraries_router.py",
                     encoding="utf-8").read()
    assert '"waiting_for_plugin"' in source, (
        "ekran nie wie, ze polka czeka na wtyczke, wiec rysuje przelacznik, "
        "ktory serwer odrzuci"
    )


def test_the_screen_does_not_offer_a_switch_the_server_will_refuse():
    panel = (BACKEND.parent / "frontend" / "src" / "views" / "settings"
             / "SettingsLibraries.vue")
    if not panel.exists():
        pytest.fail(f"brak {panel} - test nie ma czego sprawdzic")
    source = io.open(panel, encoding="utf-8").read()
    assert "waiting_for_plugin" in source, "przelacznik nie pyta o stan wtyczki"


# ── And nothing put the two in step at startup ───────────────────────────────
#
# Every guard above is about the two SWITCHES agreeing while somebody is
# looking at them. `set_catalog_stores_enabled` is called from exactly two
# places, the plugin's enable and disable buttons, so the pair only stays in
# step while GD is running.
#
# Disable a plugin while GD is down - a database restored from a backup, a
# plugin row edited, an upgrade that turns one off - and the shelf comes back up
# with `enabled=True` and no plugin behind it. Every guard then stands down,
# because they all read `not library.enabled` or `!lib.enabled` first: the shelf
# is scanned, it gets a field on the exclusions screen, and it sits in the
# navigation offering a store with nothing serving it. `reconcile_catalog_stores`
# runs at startup for exactly this class of drift and looked only at plugins
# that had been UNINSTALLED.

@pytest.mark.asyncio
async def test_a_shelf_whose_plugin_was_disabled_while_gd_was_down_comes_up_off(
        monkeypatch):
    import handler.library.catalog_sync_handler as csh

    shelf = _lib(enabled=True)
    other = _lib(id=38, slug="romdl", plugin_id="romdownloader", enabled=True)

    class _PM:
        def get_instance(self, plugin_id):
            return None
        def installed_external_ids(self):
            return {"pcports", "romdownloader"}
        def disabled_external_ids(self):
            return {"pcports"}
        def all_external_plugins_loaded(self):
            return False

    monkeypatch.setattr(csh, "plugin_manager", _PM())
    monkeypatch.setattr(csh, "_catalog_owners", lambda: {})
    changed = await csh.reconcile_shelf_switches([shelf, other])

    assert shelf.enabled is False, (
        "polka wylaczonej wtyczki wstaje wlaczona, wiec kazdy straznik, ktory "
        "pyta najpierw o `enabled`, przepuszcza ja jako zywa"
    )
    assert changed == 1


@pytest.mark.asyncio
async def test_a_shelf_somebody_switched_off_by_hand_is_left_off(monkeypatch):
    """One direction only. Turning shelves back on at every boot would undo an
    administrator who hid one deliberately - and the plugin's own enable button
    already brings it back, which is the path a person actually uses."""
    import handler.library.catalog_sync_handler as csh

    shelf = _lib(enabled=False)

    class _PM:
        def get_instance(self, plugin_id):
            return object()
        def installed_external_ids(self):
            return {"pcports"}
        def disabled_external_ids(self):
            return set()
        def all_external_plugins_loaded(self):
            return True

    monkeypatch.setattr(csh, "plugin_manager", _PM())
    monkeypatch.setattr(csh, "_catalog_owners", lambda: {})
    assert await csh.reconcile_shelf_switches([shelf]) == 0
    assert shelf.enabled is False


@pytest.mark.asyncio
async def test_a_plugin_that_merely_failed_to_load_does_not_lose_its_shelf(
        monkeypatch):
    """The caution that makes this safe to run at every boot. A plugin can be
    enabled and still absent from the runtime - it threw on import, or its
    volume mounted late. Reading THAT as "switched off" would hide a shelf for
    good on one bad boot, and nothing would ever switch it back."""
    import handler.library.catalog_sync_handler as csh

    shelf = _lib(enabled=True)

    class _PM:
        def get_instance(self, plugin_id):
            return None          # not in the runtime...
        def installed_external_ids(self):
            return {"pcports"}
        def disabled_external_ids(self):
            return set()         # ...but nobody switched it off
        def all_external_plugins_loaded(self):
            return False

    monkeypatch.setattr(csh, "plugin_manager", _PM())
    monkeypatch.setattr(csh, "_catalog_owners", lambda: {})
    assert await csh.reconcile_shelf_switches([shelf]) == 0
    assert shelf.enabled is True


def test_the_manager_can_be_asked_which_plugins_are_switched_off(monkeypatch):
    """Asked of the manager rather than read off its private cache, so the
    reconcile above is not reaching into another module's attribute.

    Against the REAL class, with only the two things it reads stubbed. Every
    test above hands the reconcile a hand-written stand-in, so all of them
    passed while the live call raised on the first boot: the state it reads is
    a property and this asked for it like a method, which fetched the set and
    then tried to call it.
    """
    from plugins.manager import PluginManager

    manager = PluginManager.__new__(PluginManager)
    monkeypatch.setattr(PluginManager, "_disabled_ids",
                        property(lambda self: {"pcports", "gone"}))
    monkeypatch.setattr(PluginManager, "installed_external_ids",
                        lambda self: {"pcports", "romdownloader"})

    # Only what is BOTH switched off and still on disk. An uninstalled plugin
    # leaves a stale row behind, and its shelf is the other reconcile's to
    # remove entirely rather than this one's to hide.
    assert manager.disabled_external_ids() == {"pcports"}


def test_startup_actually_runs_it():
    """A reconcile nothing calls is a comment.

    The CALL, not the name. This asked whether the string appears anywhere in
    main.py, and the import line alone satisfied that - so deleting the one line
    that runs it left the test green over a reconcile that never happens.
    """
    source = io.open(BACKEND / "main.py", encoding="utf-8").read()
    assert "await reconcile_shelf_switches(" in source, (
        "uzgodnienie polek z wtyczkami nie jest WOLANE przy starcie - sama "
        "linia importu nie robi niczego"
    )


def test_it_runs_after_the_plugins_are_loaded():
    """Order decides the answer. `disabled_external_ids` reads what is on disk
    and what the database says, so running this before the plugin set is up
    would judge every shelf against a runtime that is not there yet."""
    source = io.open(BACKEND / "main.py", encoding="utf-8").read()
    assert source.index("lifecycle_on_startup") < source.index(
        "await reconcile_shelf_switches("), (
        "uzgodnienie polek leci przed zaladowaniem wtyczek"
    )


def test_a_failure_there_does_not_stop_the_server():
    """It is a tidying pass. A database hiccup in it must not stop GD coming up."""
    source = io.open(BACKEND / "main.py", encoding="utf-8").read()
    at = source.index("await reconcile_shelf_switches(")
    around = source[at - 200:at + 200]
    assert "try:" in around and "except" in around, (
        "wyjatek w uzgodnieniu polek zatrzymuje start serwera"
    )


# ── The shelves that predate the plugin_id column ────────────────────────────
#
# `reconcile_shelf_switches` matches a shelf to a plugin by `plugin_id`. That
# column arrived later, so a store made before it carries only `catalog_id` -
# and those are exactly the oldest installs, the ones most likely to have a
# plugin switched off at some point.
#
# The owner cannot simply be looked up: `_catalog_owners()` asks the LOADED
# plugins, and a disabled plugin is not loaded. What CAN be said is this - if
# every installed plugin is either loaded or explicitly switched off, then a
# legacy shelf whose catalogue no loaded plugin claims must belong to one of the
# switched-off ones. When that does not hold, some plugin failed to load for
# reasons of its own and the shelf is left alone, because hiding it would be
# hiding it for good on one bad boot.

def _pm(*, installed, loaded, disabled, owners):
    """A stand-in manager, and the catalogue map built FROM it.

    The instances are made out of `owners` rather than listed separately,
    because the reconcile now asks a second question - did every loaded plugin
    manage to answer - and a stub that offers the map without the plugins
    behind it can answer one and not the other.
    """
    class _Inst:
        def __init__(self, plugin_id, catalog_id):
            self.plugin_id = plugin_id
            self._catalog_id = catalog_id

        def library_catalog_id(self):
            return self._catalog_id

    instances = [_Inst(pid, cid) for cid, pid in owners.items()]

    class _PM:
        def get_instance(self, plugin_id):
            return object() if plugin_id in loaded else None
        def installed_external_ids(self):
            return set(installed)
        def disabled_external_ids(self):
            return set(disabled)
        def all_external_plugins_loaded(self):
            return bool(installed) and set(installed) <= set(loaded)
        def get_plugin_instances(self):
            return instances
        def id_for_instance(self, inst):
            return inst.plugin_id
    return _PM(), (lambda: dict(owners))


@pytest.mark.asyncio
async def test_a_legacy_shelf_of_a_switched_off_plugin_is_hidden(monkeypatch):
    import handler.library.catalog_sync_handler as csh

    shelf = _lib(enabled=True, plugin_id=None, catalog_id="github-ports")
    pm, owners = _pm(installed={"pcports", "romdl"}, loaded={"romdl"},
                     disabled={"pcports"}, owners={"other-catalog": "romdl"})
    monkeypatch.setattr(csh, "plugin_manager", pm)
    monkeypatch.setattr(csh, "_catalog_owners", owners)

    assert await csh.reconcile_shelf_switches([shelf]) == 1
    assert shelf.enabled is False


@pytest.mark.asyncio
async def test_a_legacy_shelf_whose_plugin_is_running_is_left_alone(monkeypatch):
    import handler.library.catalog_sync_handler as csh

    shelf = _lib(enabled=True, plugin_id=None, catalog_id="github-ports")
    pm, owners = _pm(installed={"pcports"}, loaded={"pcports"},
                     disabled=set(), owners={"github-ports": "pcports"})
    monkeypatch.setattr(csh, "plugin_manager", pm)
    monkeypatch.setattr(csh, "_catalog_owners", owners)

    assert await csh.reconcile_shelf_switches([shelf]) == 0
    assert shelf.enabled is True


@pytest.mark.asyncio
async def test_a_legacy_shelf_is_left_alone_when_a_plugin_merely_failed(monkeypatch):
    """The caution. One plugin installed, enabled, and not in the runtime: it
    threw on import, or its volume mounted late. Nothing here can tell which
    catalogue belonged to it, and hiding a shelf on a guess would hide it for
    good - nothing switches it back."""
    import handler.library.catalog_sync_handler as csh

    shelf = _lib(enabled=True, plugin_id=None, catalog_id="github-ports")
    pm, owners = _pm(installed={"pcports", "broken"}, loaded={"pcports"},
                     disabled=set(), owners={"other": "pcports"})
    monkeypatch.setattr(csh, "plugin_manager", pm)
    monkeypatch.setattr(csh, "_catalog_owners", owners)

    assert await csh.reconcile_shelf_switches([shelf]) == 0
    assert shelf.enabled is True


@pytest.mark.asyncio
async def test_a_shelf_with_no_catalogue_at_all_is_not_touched(monkeypatch):
    """An ordinary library - Games, a collection - has neither column and has
    nothing to do with plugins."""
    import handler.library.catalog_sync_handler as csh

    shelf = _lib(enabled=True, plugin_id=None, catalog_id=None, is_store=False)
    pm, owners = _pm(installed={"pcports"}, loaded=set(),
                     disabled={"pcports"}, owners={})
    monkeypatch.setattr(csh, "plugin_manager", pm)
    monkeypatch.setattr(csh, "_catalog_owners", owners)

    assert await csh.reconcile_shelf_switches([shelf]) == 0
    assert shelf.enabled is True
