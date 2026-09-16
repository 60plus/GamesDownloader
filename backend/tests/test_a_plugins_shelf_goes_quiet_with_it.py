"""Two reasons a library can be switched off, and they do not mean the same thing.

An ADMIN switches a library off to prepare it: fix a scrape, swap some files,
switch it back on ready for everybody. It has to keep being scanned while that
happens, and its scan exclusions have to stay editable, or there is nothing to
prepare with. It disappears from the navigation and answers nobody but an
administrator, and that is all "off" means there.

A PLUGIN'S SHELF is switched off because the plugin is gone from the runtime.
Nothing can refresh its listings or fetch a build, nobody chose to stage it, and
walking its folder only adds rows to a shelf with nothing behind it. So it drops
out of the scan and out of the exclusions screen entirely, and what was already
downloaded stays where it lives - in the Games library, not in the store.

One question decides both, `is_folder_scanned`, because the scan picks its
targets with it and the settings screen offers a box with it. The screen used to
work the rule out again for itself from the same two fields, which is how one
copy quietly stops matching the other - so the answer is now sent to it rather
than re-derived.
"""

from __future__ import annotations

import io
import pathlib
from types import SimpleNamespace

import pytest

BACKEND = pathlib.Path(__file__).resolve().parent.parent


def _lib(**kw):
    base = dict(slug="x", kind="custom_lib", storage_folder="X", enabled=True,
                catalog_id=None, plugin_id=None, is_store=False)
    base.update(kw)
    return SimpleNamespace(**base)


# ── What the scan walks ──────────────────────────────────────────────────────

def test_an_ordinary_library_is_walked():
    from handler.database.library_registry_handler import is_folder_scanned
    assert is_folder_scanned(_lib())


def test_a_library_an_admin_switched_off_is_still_walked():
    """The staging case. Switching it off is how an admin prepares it, so the
    scan has to keep running or there is nothing to prepare."""
    from handler.database.library_registry_handler import is_folder_scanned
    assert is_folder_scanned(_lib(enabled=False))


def test_a_plugins_shelf_is_walked_while_its_plugin_is_there():
    from handler.database.library_registry_handler import is_folder_scanned
    assert is_folder_scanned(_lib(slug="pc-ports", catalog_id="github-ports",
                                  plugin_id="pcports", is_store=True))


def test_a_plugins_shelf_is_not_walked_once_the_plugin_is_off():
    """Nothing can refresh it or download into it, and nobody chose to stage
    it. Walking it only adds rows to a shelf with nothing behind it."""
    from handler.database.library_registry_handler import is_folder_scanned
    assert not is_folder_scanned(_lib(slug="pc-ports", catalog_id="github-ports",
                                      plugin_id="pcports", is_store=True,
                                      enabled=False))


def test_an_older_shelf_without_the_owner_column_counts_too():
    """`plugin_id` was added after `catalog_id`; a store made before it and not
    yet backfilled is still a plugin's shelf."""
    from handler.database.library_registry_handler import is_folder_scanned
    assert not is_folder_scanned(_lib(catalog_id="github-ports", is_store=True,
                                      enabled=False))


def test_a_library_with_no_folder_is_never_walked():
    from handler.database.library_registry_handler import is_folder_scanned
    assert not is_folder_scanned(_lib(storage_folder=None))
    assert not is_folder_scanned(_lib(kind="collections"))


# ── What the screen offers ───────────────────────────────────────────────────

def test_the_answer_is_sent_to_the_screen_rather_than_worked_out_twice():
    source = io.open(BACKEND / "endpoints" / "library" / "libraries_router.py",
                     encoding="utf-8").read()
    assert '"folder_scanned"' in source, (
        "payload nie niesie odpowiedzi, wiec ekran musi ja wyliczac po swojemu"
    )


def test_the_screen_uses_it_instead_of_its_own_copy():
    panel = (BACKEND.parent / "frontend" / "src" / "views" / "settings"
             / "SettingsLibraries.vue")
    if not panel.exists():
        pytest.fail(f"brak {panel} - test nie ma czego sprawdzic")
    source = io.open(panel, encoding="utf-8").read()
    at = source.index("const exclusionLibraries")
    body = source[at:source.index("\n\n", at)]
    assert "folder_scanned" in body, (
        "ekran nadal wylicza regule sam, wiec moze sie rozjechac ze skanem"
    )
    assert "SCANNED_KINDS" not in body, "zostala druga kopia reguly"


def test_saving_exclusions_is_refused_where_the_scan_does_not_go():
    """The pair the shared rule exists for: a box that saves cleanly and then
    does nothing is worse than no box."""
    source = io.open(BACKEND / "endpoints" / "library" / "libraries_router.py",
                     encoding="utf-8").read()
    at = source.index("async def set_library_exclusions(")
    body = source[at:source.index("\n@", at)]
    assert "is_folder_scanned" in body


# ── What the navigation shows the moment the switch is thrown ────────────────
#
# Reported by the owner on 2026-09-02 and confirmed as wanted on 2026-09-13:
# switch a plugin off and its shelf stays in the menu until the page is
# reloaded.
#
# The server is not the problem. `disable_plugin` and `enable_plugin` await
# `set_catalog_stores_enabled` BEFORE they answer, so `/libraries` already tells
# the truth by the time the button stops spinning. What never happens is the
# screen asking again: the libraries store reads `/libraries` once, at start.
#
# And every skin already listens to that store - Classic through a `watch` on
# `libs.visible`, Vapor by re-reading it every two seconds, NEON HORIZON through
# its own poll. So all four were polling a store that was never refreshed, and
# the fix belongs in exactly one place.
#
# >>> THE SIBLINGS, because a fix to one member of a family is how the rest get
# missed. Switching on, switching off, deleting, installing and syncing a
# catalogue all change which shelves exist or are visible. All five ask again.

_SETTINGS_PLUGINS = (BACKEND.parent / "frontend" / "src" / "views" / "settings"
                     / "SettingsPlugins.vue")


def _function_body(source: str, name: str) -> str:
    at = source.index(f"async function {name}(")
    ends = [i for i in (source.find("\nasync function ", at + 1),
                        source.find("\n// ──", at + 1),
                        source.find("\n</script>", at + 1)) if i != -1]
    return source[at:min(ends)]


def _asks_again_after_the_server_answered(body: str, server_call: str) -> bool:
    """The refresh has to sit on the success path, AFTER the call it follows.

    Before it, the store reads `/libraries` while the switch is still being
    thrown and gets the old answer - which looks exactly like the bug. In the
    catch, it runs only when nothing changed. Asked about the position, not
    about the word appearing somewhere in the function.
    """
    call = body.find(server_call)
    catch = body.find("} catch")
    refresh = body.find("useLibrariesStore().fetch()", call if call != -1 else 0)
    return call != -1 and refresh != -1 and (catch == -1 or refresh < catch)


@pytest.mark.parametrize("function, server_call", [
    ("toggleEnabled", "await client.post(`/plugins/${p.plugin_id}/${action}`)"),
    ("deletePlugin", "await client.delete(`/plugins/${id}`)"),
    ("uploadFile", "await client.post('/plugins/install'"),
    ("syncCatalogue", "await catalogActions.sync(id)"),
])
def test_a_plugin_action_that_changes_shelves_asks_for_the_libraries_again(function, server_call):
    if not _SETTINGS_PLUGINS.exists():
        pytest.fail(f"brak {_SETTINGS_PLUGINS} - test nie ma czego sprawdzic")
    source = io.open(_SETTINGS_PLUGINS, encoding="utf-8").read()
    body = _function_body(source, function)

    assert server_call in body, (
        f"{function} nie wola juz {server_call!r} - test trzeba poprawic razem z kodem"
    )
    assert _asks_again_after_the_server_answered(body, server_call), (
        f"{function} zmienia polki na serwerze i nie pyta ponownie o /libraries "
        "po jego odpowiedzi, wiec menu kazdej skorki pokazuje stan sprzed "
        "przelaczenia az do przeladowania strony"
    )


def test_the_refresh_is_not_placed_before_the_switch_is_thrown():
    """THE LEGAL CASE FOR THE ORDER. A refresh fired alongside the POST instead
    of after it races the server and usually reads the old state - which is the
    reported bug wearing a fix."""
    body = ("async function toggleEnabled(p) {\n"
            "  useLibrariesStore().fetch()\n"
            "  await client.post(`/plugins/${p.plugin_id}/${action}`)\n"
            "} catch (e) {}\n")
    assert not _asks_again_after_the_server_answered(
        body, "await client.post(`/plugins/${p.plugin_id}/${action}`)"
    ), "pytanie przed odpowiedzia serwera zostalo uznane za poprawne"
