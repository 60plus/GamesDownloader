"""A storefront belongs to its plugin, and goes quiet when the plugin does.

Uninstalling a catalogue plugin removed the shelf it registered and kept the
games already downloaded from it. Disabling one did not: the plugin was unloaded
so nothing could refresh the listings or fetch a build, and the shelf stayed in
the navigation, in the library settings and in the scan-exclusions list,
offering a store with nothing behind it.

Hidden rather than removed, because disabling is meant to be reversible: the
listings stay, so enabling brings the shelf back as it was instead of needing a
full re-sync of the catalogue. Games already downloaded are untouched either
way - they live in the Games library, not in the store.
"""

from __future__ import annotations

import io
import pathlib

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from models.library import Library

BACKEND = pathlib.Path(__file__).resolve().parent.parent


@pytest_asyncio.fixture
async def db(monkeypatch):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(Library.__table__.create)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async with maker() as session:
        # The plugin's shelf.
        session.add(Library(id=1, slug="pc-ports", name="PC Ports", kind="custom_lib",
                            storage_folder="PC Ports", is_store=True,
                            catalog_id="github-ports", plugin_id="pcports",
                            enabled=True))
        # Another plugin's shelf, which must not move.
        session.add(Library(id=2, slug="other", name="Other", kind="custom_lib",
                            storage_folder="Other", is_store=True,
                            catalog_id="other", plugin_id="somethingelse",
                            enabled=True))
        # An ordinary library that happens to belong to nobody.
        session.add(Library(id=3, slug="games", name="Games", kind="custom",
                            storage_folder="CUSTOM", is_store=False, enabled=True))
        await session.commit()

    import handler.library.catalog_sync_handler as csh
    monkeypatch.setattr(csh, "async_session_factory", maker)
    return maker


async def _enabled(maker) -> dict[str, bool]:
    async with maker() as session:
        rows = (await session.execute(select(Library.slug, Library.enabled))).all()
    return {slug: bool(en) for slug, en in rows}


@pytest.mark.asyncio
async def test_disabling_a_plugin_hides_its_shelf(db):
    from handler.library.catalog_sync_handler import set_catalog_stores_enabled

    changed = await set_catalog_stores_enabled("pcports", False)

    assert changed == 1
    assert await _enabled(db) == {"pc-ports": False, "other": True, "games": True}


@pytest.mark.asyncio
async def test_enabling_it_again_brings_the_shelf_back(db):
    from handler.library.catalog_sync_handler import set_catalog_stores_enabled

    await set_catalog_stores_enabled("pcports", False)
    changed = await set_catalog_stores_enabled("pcports", True)

    assert changed == 1
    assert await _enabled(db) == {"pc-ports": True, "other": True, "games": True}


@pytest.mark.asyncio
async def test_doing_it_twice_changes_nothing_the_second_time(db):
    """Idempotent, so a re-run of the enable route does not report work it did
    not do."""
    from handler.library.catalog_sync_handler import set_catalog_stores_enabled

    assert await set_catalog_stores_enabled("pcports", False) == 1
    assert await set_catalog_stores_enabled("pcports", False) == 0


@pytest.mark.asyncio
async def test_a_plugin_with_no_shelf_is_a_no_op(db):
    from handler.library.catalog_sync_handler import set_catalog_stores_enabled

    assert await set_catalog_stores_enabled("gd3-translator", False) == 0
    assert await _enabled(db) == {"pc-ports": True, "other": True, "games": True}


@pytest.mark.asyncio
async def test_the_listings_are_kept(db):
    """The difference between hiding and uninstalling. Removing the listings
    would make enabling the plugin again a full re-sync of the catalogue."""
    from handler.library.catalog_sync_handler import set_catalog_stores_enabled

    await set_catalog_stores_enabled("pcports", False)
    async with db() as session:
        store = (await session.execute(
            select(Library).where(Library.slug == "pc-ports")
        )).scalars().first()
    assert store is not None, "polka zostala usunieta, a miala tylko zniknac"
    assert store.catalog_id == "github-ports", "polka stracila swoj katalog"


# ── Both routes have to do it, or the pair only works one way ────────────────

@pytest.mark.parametrize("route,value", [("disable_plugin", "False"),
                                         ("enable_plugin", "True")])
def test_both_plugin_routes_move_the_shelf(route, value):
    source = io.open(BACKEND / "endpoints" / "settings" / "plugins_router.py",
                     encoding="utf-8").read()
    at = source.index(f"async def {route}(")
    body = source[at:source.index("\n@", at)]
    assert f"set_catalog_stores_enabled(plugin_id, {value})" in body, (
        f"{route} nie rusza polki, wiec przelacznik dziala tylko w jedna strone"
    )


def test_uninstalling_still_removes_rather_than_hides():
    """Hiding is for the reversible one. An uninstalled plugin's shelf and its
    listings go, because nothing will ever refresh them again."""
    source = io.open(BACKEND / "endpoints" / "settings" / "plugins_router.py",
                     encoding="utf-8").read()
    at = source.index("async def delete_plugin(")
    body = source[at:source.index("\n@", at)]
    assert "remove_catalog_stores_for_plugin" in body
    assert "set_catalog_stores_enabled" not in body
