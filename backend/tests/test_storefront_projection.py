"""The home route asks for the whole library, so it must ask for little of it.

Three separate over-fetches met on one endpoint.

The GOG fallback took full `GogGame` entities for every linked row - eight
hundred of them on a real account - to build twelve tiles, dragging the
description HTML, the changelog, the installer manifests, the extras and the
DLC lists along. The rails read nine columns.

The rails also padded their limit by the number of games the caller may not see
and filtered afterwards, so every denied game cost a fetched row plus its
LibraryFile rows through the selectin relationship - and the rail still came
back short whenever the padding did not cover the denies.

And the ROM ranking selected whole `Rom` entities including the raw provider
payloads: `ss_metadata` is the entire ScreenScraper `jeu` object with its full
media array.
"""
from __future__ import annotations

import inspect
import re

from endpoints.library.library_router import _gog_meta_map
from endpoints.roms.roms_router import _rom_tile_dict
from handler.database.library_handler import LibraryHandler
from handler.database.rom_handler import RomHandler

# The raw provider blobs. Deferred, so they are not fetched for a tile.
BLOBS = ("ss_metadata", "igdb_metadata", "launchbox_metadata")


# ── The GOG fallback projection ──────────────────────────────────────────────

def test_the_projection_covers_every_field_the_storefront_falls_back_on():
    """The silent-failure guard. `_row_fb` is getattr with a default, so a
    field added to the storefront and forgotten in the projection would return
    the default instead of the value - no error, just a tile quietly missing
    its cover or its trailer."""
    from endpoints.library import home_router

    used = set(re.findall(r'_row_fb\(\s*\w+\s*,\s*\w+\s*,\s*"(\w+)"',
                          inspect.getsource(home_router)))
    # `meta_ratings` is read straight off the row, not through _row_fb.
    used.add("meta_ratings")
    projected = set(re.findall(r"_GG\.(\w+)", inspect.getsource(_gog_meta_map)))
    missing = used - projected
    assert missing == set(), f"read by the storefront, not in the projection: {missing}"


def test_the_projection_leaves_out_the_heavy_columns():
    source = inspect.getsource(_gog_meta_map)
    for column in ("description", "changelog", "installers", "extras", "dlcs",
                   "screenshots"):
        assert f"_GG.{column}," not in source, column


def test_the_full_entity_loader_is_still_there_for_the_tiles():
    """_game_to_tile reads far more than nine columns, and three other routes
    use it. Only the whole-library call was narrowed."""
    from endpoints.library.library_router import _gog_fallback_map

    assert "select" in inspect.getsource(_gog_fallback_map).lower()


# ── Denies pushed into SQL ───────────────────────────────────────────────────

def test_the_popular_rail_can_exclude_in_sql():
    source = inspect.getsource(LibraryHandler.get_popular)
    assert "exclude_ids" in source
    assert "notin_" in source


def test_excluding_stays_optional():
    """/api/library/popular has no denies to apply and must keep working."""
    parameters = inspect.signature(LibraryHandler.get_popular).parameters
    assert parameters["exclude_ids"].default is None


def test_the_storefront_no_longer_pads_and_filters():
    from endpoints.library import home_router

    source = inspect.getsource(home_router)
    assert "rail_limit * 2 + len(denied)" not in source
    assert "exclude_ids=denied" in source
    assert "g for g in recent if g.id not in denied" not in source


# ── The ROM ranking ──────────────────────────────────────────────────────────

def test_the_ranking_defers_the_provider_blobs():
    source = inspect.getsource(RomHandler.get_rated)
    for blob in BLOBS:
        assert f"defer(Rom.{blob})" in source, blob


def test_the_ranking_does_not_defer_what_it_reads():
    """plugin_ratings feeds the blended score and is written by
    steam-deck-compatibility. Deferring a column that is then read raises
    MissingGreenlet in async context - a hard 500, not bad data."""
    source = inspect.getsource(RomHandler.get_rated)
    assert "defer(Rom.plugin_ratings)" not in source


def test_the_tile_never_touches_a_deferred_column():
    """If it did, every load of the rail would 500."""
    source = inspect.getsource(_rom_tile_dict)
    for blob in BLOBS:
        assert blob not in source, blob


def test_the_rating_helper_never_touches_a_deferred_column():
    from utils.ratings import rom_rating_agg_of

    source = inspect.getsource(rom_rating_agg_of)
    for blob in BLOBS:
        assert blob not in source, blob
