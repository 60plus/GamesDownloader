"""Where every picture other than the cover came from, and who may replace it.

The cover learned this first: a forced re-scrape replaces what a provider gave
us and keeps what a person chose, because the scrape can be run again at any
time and the file they went and found cannot be got back. Every other slot -
background, wheel, support, bezel, Steam Grid, video, pictoliste, screenshots -
had no way to tell, and for a while that did not matter, because those slots
were never replaced at all: the downloader handed back whatever file was already
at the name.

Then they were made to refresh, and refreshing deletes. For the length of one
afternoon a forced re-scrape took every background and wheel anybody had
uploaded by hand. This is the column that tells them apart.

The default for an unrecorded slot is the opposite of the cover's, and on
purpose. Every existing row was given a cover origin by a migration, so a null
there is a real answer. Nothing filled these in, so a null here means we do not
know - and on a library that upgraded overnight, reading "do not know" as "a
provider gave us this" is exactly the afternoon described above.
"""
from __future__ import annotations

import inspect
from types import SimpleNamespace

import pytest

from handler.metadata import rom_scrape_handler
from handler.metadata.rom_scrape_handler import (
    MEDIA_COLUMNS, keep_existing_cover, keep_existing_media, media_origin, with_manual,
)


def _rom(**kw):
    base = dict(
        cover_path="/r/cover.jpg", cover_source="scrape",
        background_path="/r/background.jpg", wheel_path="/r/wheel.png",
        support_path=None, bezel_path=None, steamgrid_path=None,
        video_path=None, picto_path=None, screenshots=None,
        media_source=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


# ── The rule ─────────────────────────────────────────────────────────────────


def test_a_background_somebody_uploaded_survives_a_forced_rescrape():
    rom = _rom(media_source={"background_path": "manual"})
    assert keep_existing_media(rom, "background_path", fill_missing=False)


def test_a_background_a_provider_gave_us_does_not():
    rom = _rom(media_source={"background_path": "scrape"})
    assert not keep_existing_media(rom, "background_path", fill_missing=False)


def test_a_slot_we_know_nothing_about_is_left_alone():
    """The upgrade case, and the whole reason the default runs this way. A
    library that existed before the column did has an empty map and a disk full
    of pictures, and some of them are somebody's."""
    assert keep_existing_media(_rom(), "background_path", fill_missing=False)
    assert keep_existing_media(_rom(), "wheel_path", fill_missing=False)


def test_the_cover_reads_an_unknown_origin_the_other_way():
    """Stated next to the one above, because the two defaults disagree and the
    disagreement is the point: a migration filled in every cover, so a null
    there is an answer rather than a gap."""
    assert not keep_existing_cover(_rom(cover_source=None), fill_missing=False)


def test_filling_gaps_replaces_nothing_that_is_already_there():
    for origin in (None, "manual", "scrape"):
        rom = _rom(media_source={"background_path": origin} if origin else None)
        assert keep_existing_media(rom, "background_path", fill_missing=True)


def test_an_empty_slot_has_nothing_to_keep():
    for fill in (True, False):
        assert not keep_existing_media(_rom(support_path=None), "support_path", fill)


def test_the_cover_goes_through_the_same_function():
    """One place decides, so the two cannot drift apart. keep_existing_cover is
    the same question asked about one column."""
    assert keep_existing_cover(_rom(cover_source="manual"), False)
    assert not keep_existing_cover(_rom(cover_source="scrape"), False)
    assert media_origin(_rom(cover_source="manual"), "cover_path") == "manual"


def test_a_column_that_is_not_a_media_slot_is_refused():
    """A typo in a column name would otherwise read as "nothing there" and let
    a scrape replace a slot it was told to leave."""
    with pytest.raises(KeyError):
        keep_existing_media(_rom(), "name", fill_missing=False)


# ── Recording it ─────────────────────────────────────────────────────────────


def test_marking_one_slot_does_not_forget_the_others():
    """Every caller writes the whole column, so a value built from nothing would
    quietly drop what was already recorded."""
    rom = _rom(media_source={"wheel_path": "manual", "bezel_path": "scrape"})

    out = with_manual(rom, "background_path")

    assert out == {"wheel_path": "manual", "bezel_path": "scrape",
                   "background_path": "manual"}
    assert rom.media_source == {"wheel_path": "manual", "bezel_path": "scrape"}, \
        "the row's own value was mutated rather than copied"


def test_several_slots_at_once():
    out = with_manual(_rom(), "background_path", "wheel_path")
    assert out == {"background_path": "manual", "wheel_path": "manual"}


def test_the_cover_is_not_recorded_here():
    """It has a column of its own. Two places claiming to know where one picture
    came from is how they come to disagree."""
    with pytest.raises(KeyError):
        with_manual(_rom(), "cover_path")


# ── The slots, and the routes that write them ────────────────────────────────


def test_every_path_column_the_scrape_writes_is_a_known_slot():
    """A slot the scrape can write but keep_existing_media has never heard of
    is a slot with no protection at all."""
    from models.rom import Rom

    written = {"background_path", "support_path", "wheel_path", "bezel_path",
               "steamgrid_path", "video_path", "picto_path", "cover_path",
               "screenshots"}
    assert written <= MEDIA_COLUMNS, f"unprotected: {written - MEDIA_COLUMNS}"
    columns = {c.key for c in Rom.__mapper__.columns} | {"screenshots"}
    assert MEDIA_COLUMNS <= columns, f"not columns at all: {MEDIA_COLUMNS - columns}"


def test_clearing_the_metadata_forgets_the_origins():
    """The way back for somebody who wants a scrape to replace what they chose.
    The paths go with it, so the next pass fetches and records afresh."""
    from handler.database.rom_handler import SCRAPED_METADATA_FIELDS, cleared_metadata_values

    assert "media_source" in SCRAPED_METADATA_FIELDS
    assert cleared_metadata_values()["media_source"] is None


@pytest.mark.parametrize("route", ["upload_rom_media", "update_rom_metadata"])
def test_the_routes_a_person_uses_say_so(route):
    """A route that writes a picture and records nothing leaves the slot
    unrecorded, which reads as "do not know" - safe today and wrong the moment
    somebody clears the metadata and the slot is written by hand again."""
    from endpoints.roms import roms_router

    assert "with_manual" in inspect.getsource(getattr(roms_router, route))


def test_the_scrape_records_what_it_fetched():
    source = inspect.getsource(rom_scrape_handler.scrape_rom)
    assert "_from_scrape" in source
    # Every slot it can write, not just the one that was noticed first.
    for column in ("background_path", "wheel_path", "steamgrid_path", "screenshots"):
        assert f'_from_scrape("{column}")' in source, f"{column} is fetched and not recorded"
