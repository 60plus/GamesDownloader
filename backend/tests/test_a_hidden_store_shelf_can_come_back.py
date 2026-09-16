"""Hiding a shelf by one key and un-hiding it by another is a one-way door.

A catalogue plugin's shelf follows its plugin: switch the plugin off and the
shelf goes away, switch it on and the shelf returns. That is one switch
controlling the other, and it is the reason nothing here deletes anything.

The two halves did not use the same key. Hiding asks about `plugin_id` OR, for a
shelf made before that column existed, about `catalog_id`. Un-hiding asks about
`plugin_id` alone - and a legacy shelf has none. So switching the plugin off hid
it and switching the plugin back on left it hidden, with no message anywhere.
The only way back was for an administrator to guess that Settings > Libraries
still lists it and to flip it by hand.

There is a second way in, which nobody reported: `_catalog_owners` skips a
loaded plugin whose `library_catalog_id()` hook raises. A legacy shelf belonging
to THAT plugin then looks like a shelf whose plugin is gone, and is hidden while
the plugin is enabled and running - so the return path above, which needs
somebody to press Enable, never fires at all.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

CATALOG = "retro-store"
PLUGIN = "gd3-retro"


@pytest_asyncio.fixture
async def shelves(monkeypatch):
    from models.library import Library

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(Library.__table__.create)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    from handler.library import catalog_sync_handler as H
    monkeypatch.setattr(H, "async_session_factory", maker)

    async with maker() as session:
        # The shelf that predates the owner column: a catalogue and nothing else.
        session.add(Library(id=1, slug="retro", name="Retro", kind="store",
                            is_store=True, enabled=False,
                            plugin_id=None, catalog_id=CATALOG))
        # A shelf of another plugin, which must not move.
        session.add(Library(id=2, slug="inne", name="Inne", kind="store",
                            is_store=True, enabled=False,
                            plugin_id="gd3-inne", catalog_id="inne"))
        await session.commit()
    yield maker, H
    await engine.dispose()


def _owners(mapping):
    return lambda: dict(mapping)


@pytest.mark.asyncio
async def test_enabling_the_plugin_brings_its_legacy_shelf_back(shelves, monkeypatch):
    from models.library import Library

    maker, H = shelves
    monkeypatch.setattr(H, "_catalog_owners", _owners({CATALOG: PLUGIN}))

    changed = await H.set_catalog_stores_enabled(PLUGIN, True)

    async with maker() as session:
        shelf = (await session.execute(
            select(Library).where(Library.id == 1))).scalars().first()

    assert changed == 1, (
        "wlaczenie wtyczki nie przywraca polki sprzed kolumny wlasciciela - "
        "chowana jest po katalogu, a odchowywana po plugin_id"
    )
    assert shelf.enabled is True


@pytest.mark.asyncio
async def test_it_records_the_owner_so_this_cannot_happen_twice(shelves, monkeypatch):
    """A one-time trap on an upgrade rather than a standing one: once the shelf
    knows its plugin, both halves ask the same question again."""
    from models.library import Library

    maker, H = shelves
    monkeypatch.setattr(H, "_catalog_owners", _owners({CATALOG: PLUGIN}))

    await H.set_catalog_stores_enabled(PLUGIN, True)

    async with maker() as session:
        shelf = (await session.execute(
            select(Library).where(Library.id == 1))).scalars().first()

    assert shelf.plugin_id == PLUGIN, "polka nadal nie wie, czyja jest"


@pytest.mark.asyncio
async def test_another_plugins_shelf_is_left_where_it_is(shelves, monkeypatch):
    from models.library import Library

    maker, H = shelves
    monkeypatch.setattr(H, "_catalog_owners", _owners({CATALOG: PLUGIN}))

    await H.set_catalog_stores_enabled(PLUGIN, True)

    async with maker() as session:
        other = (await session.execute(
            select(Library).where(Library.id == 2))).scalars().first()

    assert other.enabled is False, "wlaczenie jednej wtyczki odslonilo cudza polke"


@pytest.mark.asyncio
async def test_switching_the_plugin_off_still_hides_it(shelves, monkeypatch):
    """The half that worked. The shelf offers a store with nothing behind it
    while its plugin is unloaded."""
    from models.library import Library

    maker, H = shelves
    monkeypatch.setattr(H, "_catalog_owners", _owners({CATALOG: PLUGIN}))
    await H.set_catalog_stores_enabled(PLUGIN, True)

    changed = await H.set_catalog_stores_enabled(PLUGIN, False)

    async with maker() as session:
        shelf = (await session.execute(
            select(Library).where(Library.id == 1))).scalars().first()

    assert changed == 1 and shelf.enabled is False


# ── The shelf of a plugin whose hook throws ──────────────────────────────────

def _store(plugin_id=None, catalog_id=CATALOG, enabled=True):
    return SimpleNamespace(plugin_id=plugin_id, catalog_id=catalog_id,
                           enabled=enabled)


OFF = "gd3-wylaczona"


def _runtime(monkeypatch, instances, ids):
    """One plugin switched off - otherwise the reconcile has nothing to do and
    returns before it looks at anything - plus whatever else is loaded."""
    from handler.library import catalog_sync_handler as H

    monkeypatch.setattr(H.plugin_manager, "disabled_external_ids", lambda: {OFF})
    monkeypatch.setattr(H.plugin_manager, "installed_external_ids",
                        lambda: list(ids) + [OFF])
    monkeypatch.setattr(H.plugin_manager, "get_plugin_instances", lambda: instances)
    monkeypatch.setattr(H.plugin_manager, "id_for_instance",
                        lambda inst: inst.plugin_id)
    monkeypatch.setattr(H.plugin_manager, "get_instance",
                        lambda pid: None if pid == OFF else object())
    return H


class _Plugin:
    def __init__(self, plugin_id, catalog_id=None, raises=False):
        self.plugin_id = plugin_id
        self._catalog_id = catalog_id
        self._raises = raises

    def library_catalog_id(self):
        if self._raises:
            raise RuntimeError("wtyczka wystawia zepsuty hook")
        return self._catalog_id


@pytest.mark.asyncio
async def test_a_plugin_whose_hook_throws_does_not_condemn_its_shelf(monkeypatch):
    """`_catalog_owners` skips a plugin whose `library_catalog_id()` raises, so
    the map is incomplete - and an incomplete map cannot be read as "nobody
    claims this catalogue". The plugin here is enabled and running, so nobody
    will ever press Enable and the only way back never fires."""
    H = _runtime(monkeypatch, [_Plugin(PLUGIN, raises=True)], [PLUGIN])

    store = _store()
    changed = await H.reconcile_shelf_switches([store])

    assert changed == 0 and store.enabled is True, (
        "polka wtyczki, ktorej hook rzucil, zostala schowana mimo ze wtyczka "
        "jest wlaczona i dziala"
    )


@pytest.mark.asyncio
async def test_a_shelf_whose_plugin_is_switched_off_is_still_hidden(monkeypatch):
    """The case this rule exists for has to go on working: a legacy shelf whose
    catalogue no loaded plugin claims, with every installed plugin accounted
    for, belongs to one of the switched-off ones."""
    H = _runtime(monkeypatch, [_Plugin("gd3-inne", "cos-innego")], ["gd3-inne"])

    store = _store()
    changed = await H.reconcile_shelf_switches([store])

    assert changed == 1 and store.enabled is False


@pytest.mark.asyncio
async def test_a_shelf_that_knows_its_owner_is_unaffected_by_a_broken_hook(monkeypatch):
    """The narrower reading: only the LEGACY question needs a complete map. A
    shelf carrying `plugin_id` is decided by that alone."""
    H = _runtime(monkeypatch, [_Plugin(PLUGIN, raises=True)], [PLUGIN])

    store = _store(plugin_id=OFF)
    changed = await H.reconcile_shelf_switches([store])

    assert changed == 1 and store.enabled is False
