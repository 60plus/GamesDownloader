"""Which covers a re-scrape may replace, and which it may not.

A cover somebody went and chose survives even a forced pass: the scrape can be
run again at any time and their file cannot be got back. A cover a provider
gave us is exactly what a forced pass is for.

Telling them apart was inferred rather than recorded, and inferred wrongly. The
rule read "has a file and no remote source", on the reasoning that the upload
route clears cover_url - which it does. So does every ScreenScraper cover: those
URLs carry the developer and account passwords, so they are deliberately never
stored. Our main provider therefore left the same trace as an upload, and a
forced re-scrape could not replace any cover ScreenScraper had ever fetched.
Re-identifying a ROM that had matched the wrong game moved the title and the
description onto the right one and left the wrong game's artwork in place.

The previous version of this file read the source of `scrape_rom` looking for
the string "not rom.cover_url", and passed the whole time.
"""
from __future__ import annotations

import inspect
from types import SimpleNamespace

import httpx
import pytest

from handler.metadata import rom_scrape_handler
from handler.metadata.rom_scrape_handler import keep_existing_cover


def _rom(**kw):
    base = dict(cover_path="/resources/roms/psx/1/cover.jpg", cover_url=None,
                cover_source=None)
    base.update(kw)
    return SimpleNamespace(**base)


def test_a_cover_somebody_uploaded_survives_a_forced_rescrape():
    assert keep_existing_cover(_rom(cover_source="manual"), fill_missing=False)


def test_a_cover_a_provider_gave_us_does_not():
    """The defect. This is the ordinary case - most covers in a ROM library
    come from ScreenScraper - and forcing could not touch any of them."""
    assert not keep_existing_cover(_rom(cover_source="scrape"), fill_missing=False)


def test_a_screenscraper_cover_is_not_mistaken_for_a_chosen_one():
    """Stated separately because this is the exact shape it had: a file, no
    remote source, and nothing hand-picked about it."""
    rom = _rom(cover_source="scrape", cover_url=None)
    assert not keep_existing_cover(rom, fill_missing=False)


def test_filling_gaps_replaces_nothing_that_is_already_there():
    """Whatever it is and wherever it came from."""
    for source in (None, "manual", "scrape"):
        assert keep_existing_cover(_rom(cover_source=source), fill_missing=True)


def test_a_rom_with_no_cover_at_all_has_nothing_to_keep():
    for fill in (True, False):
        assert not keep_existing_cover(_rom(cover_path=None, cover_source="manual"), fill)


def test_an_unplaceable_cover_is_treated_as_chosen():
    """What the migration leaves behind for rows it cannot classify.

    Getting this wrong in one direction costs a forced re-scrape that declines
    to replace a picture. In the other it costs a picture, permanently.
    """
    assert keep_existing_cover(_rom(cover_source=None), fill_missing=False) is False
    # ...which is to say: unplaceable rows are given "manual" at migration time
    # rather than being left null and read as replaceable here.
    assert "cover_source" in _migration_text()
    assert "'manual'" in _migration_text()


def _migration_text() -> str:
    import pathlib
    main = pathlib.Path(rom_scrape_handler.__file__).resolve().parent.parent.parent / "main.py"
    return main.read_text(encoding="utf-8", errors="ignore")


@pytest.mark.parametrize("writer,expected", [
    ("upload_rom_media", "manual"),
    ("update_rom_metadata", "manual"),
])
def test_every_route_that_writes_a_cover_says_where_it_came_from(writer, expected):
    """A route that writes a cover and says nothing leaves the column null, and
    a null cover is replaceable - which for an upload would be the old bug
    running the other way."""
    from endpoints.roms import roms_router

    source = inspect.getsource(getattr(roms_router, writer))
    assert f'"cover_source"] = "{expected}"' in source


def test_the_scrape_records_where_its_cover_came_from():
    source = inspect.getsource(rom_scrape_handler.scrape_rom)
    assert '"cover_source"] = "scrape"' in source


@pytest.mark.parametrize("writer", ["upload_rom_media", "update_rom_metadata"])
def test_a_hand_picked_cover_drops_the_providers_word_for_it(writer):
    """cover_type says what kind of picture a provider sent - box-2D, box-3D.
    A cover chosen by hand is not that picture, and the word outlived it: the
    upload route never wrote one and never cleared one, so the trace stayed put
    while the cover it described was replaced.

    Reads the source, so it only shows the routes ask for it. Whether asking for
    it does anything is the next test, and the two are not the same question."""
    from endpoints.roms import roms_router

    source = inspect.getsource(getattr(roms_router, writer))
    assert '"cover_type"] = None' in source


@pytest.mark.asyncio
async def test_asking_for_it_actually_clears_the_column():
    """The half the test above cannot see.

    Both routes hand a dict to rom_handler.update_metadata, which copies only
    the keys it recognises. A writer that dropped None values, or a field
    missing from that allow-list, would leave the routes above reading exactly
    as they do and change nothing in the database - and the source-reading test
    would pass the whole time. That shape of test has been wrong here before.
    """
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import StaticPool

    from handler.database.rom_handler import rom_handler
    from models.rom import Rom

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", poolclass=StaticPool)
    async with engine.begin() as conn:
        await conn.run_sync(Rom.__table__.create)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with maker() as session:
            session.add(Rom(id=1, platform_id=1, fs_name="g.iso", fs_name_no_ext="g",
                            fs_extension="iso", fs_path="/roms/psx",
                            cover_type="box-3D", cover_path="/resources/x/cover.jpg"))
            await session.commit()

            out = await rom_handler.update_metadata(
                1, {"cover_path": "/resources/x/cover.png",
                    "cover_source": "manual",
                    "cover_type": None},
                session=session,
            )

            assert out.cover_type is None, "the provider's word outlived its cover"
            assert out.cover_source == "manual"
    finally:
        await engine.dispose()


def test_the_stale_word_was_not_only_a_bookkeeping_problem():
    """It is read for the shape of the box as well, so a scraped 3D cover
    replaced by hand with a flat one went on being drawn wide and cropped."""
    from handler.metadata.rom_platform_map import rom_cover_aspect

    assert rom_cover_aspect("box-3D", "3/4", "snes") == "16/9"
    assert rom_cover_aspect(None, "3/4", "snes") == "3/4"


def test_the_migration_no_longer_reads_a_trace_that_outlives_its_cover():
    """The rule that claimed twenty-four of thirty covers on the library this
    was written against. It asked whether cover_type was set, which is true of
    every ROM ever scraped, including the ones later given a cover by hand."""
    assert "cover_type` IS NOT NULL" not in _migration_text()


def test_the_scrape_still_asks_before_replacing_a_cover():
    """A tripwire, not a behaviour test: the rule above is only worth anything
    while the scrape actually consults it."""
    assert "keep_existing_cover(rom, fill_missing)" in inspect.getsource(
        rom_scrape_handler.scrape_rom
    )


# ── A scrape that fails costs nothing ────────────────────────────────────────
#
# Everything above decides whether a cover MAY be replaced. This decides what
# happens once the answer is yes and the download then does not arrive. The old
# files were deleted before the request went out, so a timeout took the cover
# with it and left the game with none - a cover the rules above had just spent
# some trouble deciding was replaceable, not disposable.


@pytest.fixture
def fetch(monkeypatch):
    """Stand in for the network. `.reply` is what the next fetch returns, or an
    exception instance to raise instead."""
    state = SimpleNamespace(reply=(b"NEW", "image/jpeg"), calls=0)

    async def _fetch(url, **_kw):
        state.calls += 1
        if isinstance(state.reply, Exception):
            raise state.reply
        return state.reply

    monkeypatch.setattr(rom_scrape_handler, "fetch_media_bytes", _fetch)
    return state


async def _get(tmp_path, url="http://x/art.jpg", stem="cover", replace=True):
    return await rom_scrape_handler._download_image(
        url, tmp_path / f"{stem}.{url.rsplit('.', 1)[-1]}", replace=replace)


@pytest.mark.asyncio
async def test_a_download_that_fails_leaves_the_file_that_is_there(tmp_path, fetch):
    """The defect, and the only one of these that ever cost anybody anything."""
    (tmp_path / "cover.jpg").write_bytes(b"OLD")
    fetch.reply = httpx.ReadTimeout("took too long")

    assert await _get(tmp_path) is None
    assert (tmp_path / "cover.jpg").read_bytes() == b"OLD"


@pytest.mark.asyncio
async def test_a_download_that_arrives_takes_the_place_of_the_old_one(tmp_path, fetch):
    (tmp_path / "cover.jpg").write_bytes(b"OLD")

    out = await _get(tmp_path)

    assert out == tmp_path / "cover.jpg"
    assert out.read_bytes() == b"NEW"
    assert [p.name for p in tmp_path.iterdir()] == ["cover.jpg"]


@pytest.mark.asyncio
async def test_the_old_file_goes_even_when_the_new_one_is_a_different_kind(tmp_path, fetch):
    """Two covers of different extensions in one directory is how a game ends up
    showing whichever the glob happens to reach first. The old one can only be
    cleared after the response arrives, because until then the extension of the
    new one is a guess off the URL."""
    (tmp_path / "cover.jpg").write_bytes(b"OLD")
    fetch.reply = (b"NEW", "image/png")

    out = await _get(tmp_path, "http://x/art.php")

    assert out == tmp_path / "cover.png"
    assert [p.name for p in tmp_path.iterdir()] == ["cover.png"]


@pytest.mark.asyncio
async def test_a_slot_being_refreshed_is_fetched_even_though_a_file_is_there(tmp_path, fetch):
    """The background's defect, which is the cover's read backwards.

    Nothing cleared the old background first, so the "it is already there,
    nothing to do" check handed the existing file straight back and a forced
    re-scrape - including one that had just moved the ROM onto a different game -
    left the previous background in place. The covers only escaped this by
    deleting first, which is what cost them.
    """
    (tmp_path / "background.jpg").write_bytes(b"OLD")

    out = await _get(tmp_path, stem="background")

    assert fetch.calls == 1, "it handed back the old file instead of fetching"
    assert out.read_bytes() == b"NEW"


@pytest.mark.asyncio
async def test_a_gap_filling_pass_fetches_nothing_it_already_has(tmp_path, fetch):
    """The other half: without replace, what is there stays and no request is
    made at all. This is the pass that fills in what is missing."""
    (tmp_path / "cover.jpg").write_bytes(b"OLD")

    out = await _get(tmp_path, replace=False)

    assert fetch.calls == 0
    assert out.read_bytes() == b"OLD"


def test_every_media_slot_the_scrape_writes_says_whether_it_may_replace():
    """A tripwire for the thing this codebase keeps doing to itself.

    The cover was fixed first and alone, which left the background never
    refreshing at all, the SteamGridDB hero writing into that same slot and
    logging a download it had not made, and the screenshots, wheel, support,
    bezel, Steam Grid, video and picto quietly serving whatever the last scrape
    left. A release note saying media now refreshes would have been false for
    six of the eight.

    Reading the source, so it catches the next slot being added without the
    flag rather than a mistake inside one. The behaviour itself is covered
    above, against a stubbed network.
    """
    import re

    from endpoints.roms import roms_router

    for module in (rom_scrape_handler, roms_router):
        text = inspect.getsource(module)
        calls = re.findall(r"_download_image\((?!url:|self)(.*?)\)\s*\n", text, re.S)
        # The definition itself is not a call, and neither is the import line.
        calls = [c for c in calls if "def " not in c]
        assert calls, f"nie znalazlem wywolan w {module.__name__}"
        bare = [c for c in calls if "replace=" not in c]
        assert not bare, (
            f"{module.__name__}: media slot written without saying whether it may "
            f"replace what is there: {bare}"
        )
